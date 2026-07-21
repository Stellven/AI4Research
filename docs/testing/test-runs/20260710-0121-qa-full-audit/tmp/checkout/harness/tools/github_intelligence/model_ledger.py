"""GitHub Project Intelligence — model call ledger.

Sprint: sprint-20260524-p0-ai-influence-github-project-intelligence-system-upgrade-s03-core-runtime
Node:   C1_schema_contract

Records every model API call (provider/model/usage/cost) made by the GitHub
intelligence pipeline. Independent from `harness/lib/model_call_runtime.py`,
which records pane-level dispatch events. Both can coexist without conflict.

Acceptance:
- model ledger records provider/model/usage metadata
- no backward incompatible import changes

Routing policy (S02 §A3): Local Qwen3.6 for preprocessing/verification;
Gemini Pro for long-context synthesis; Claude Opus for editorial; Codex for
architecture. Cost cap enforced: ≤ MAX_PREMIUM_CALLS_PER_DAY premium calls/day.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import uuid
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from typing import Any, ClassVar

# Robust import: works both as package (`from harness.lib.github_intelligence import ...`)
# and as standalone module (`python model_ledger.py`).
try:  # package import path
    from .schema import utc_now_iso  # type: ignore
except ImportError:  # script execution fallback
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from schema import utc_now_iso  # type: ignore

LEDGER_TABLE = "model_call_ledger"

# Hard daily cap on premium calls (S02 §R4)
MAX_PREMIUM_CALLS_PER_DAY = 20

PROVIDER_TIER = {
    "thunderomlx": "local",
    "qwen3.6-thunderomlx": "local",
    "ollama": "local",
    "gemini-pro": "premium",
    "claude-opus": "premium",
    "claude-sonnet": "premium",
    "codex": "premium",
}

CALL_TYPES: tuple[str, ...] = (
    "preprocess",
    "reasoning",
    "verification",
    "editorial",
    "architecture",
)


def _date_only(iso_ts: str) -> str:
    """Extract YYYY-MM-DD from ISO-8601 UTC string."""
    return iso_ts[:10]


def _now_date_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


@dataclass
class ModelCall:
    """One observed model API call.

    Fields:
        call_id: deterministic-or-uuid identifier
        full_name: GitHub repo full_name (owner/name) the call relates to (nullable for global calls)
        model_name: e.g. 'qwen3.6-thunderomlx', 'gemini-pro', 'claude-opus'
        provider: e.g. 'thunderomlx', 'google', 'anthropic', 'openai'
        call_type: one of CALL_TYPES
        input_tokens: prompt tokens billed
        output_tokens: completion tokens billed
        cost_estimate: USD; 0.0 for local calls
        usage_extra: provider-specific usage payload (cache hit, ttft, etc.)
        created_at: ISO-8601 UTC
    """

    call_id: str
    full_name: str | None
    model_name: str
    provider: str
    call_type: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_estimate: float = 0.0
    usage_extra: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)

    JSON_FIELDS: ClassVar[tuple[str, ...]] = ("usage_extra",)
    TABLE: ClassVar[str] = LEDGER_TABLE

    def __post_init__(self) -> None:
        if self.call_type not in CALL_TYPES:
            raise ValueError(
                f"call_type must be one of {CALL_TYPES}, got {self.call_type!r}"
            )
        if self.input_tokens < 0 or self.output_tokens < 0:
            raise ValueError("token counts must be >= 0")
        if self.cost_estimate < 0:
            raise ValueError("cost_estimate must be >= 0")

    @property
    def tier(self) -> str:
        return PROVIDER_TIER.get(self.model_name, PROVIDER_TIER.get(self.provider, "premium"))

    @property
    def is_premium(self) -> bool:
        return self.tier == "premium"

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        row["usage_extra"] = json.dumps(self.usage_extra, ensure_ascii=False, sort_keys=True)
        row["tier"] = self.tier
        return row

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "ModelCall":
        kwargs = {f.name: row.get(f.name) for f in fields(cls)}
        raw_usage = row.get("usage_extra")
        kwargs["usage_extra"] = json.loads(raw_usage) if raw_usage else {}
        return cls(**kwargs)


DDL_LEDGER: tuple[str, ...] = (
    f"""CREATE TABLE IF NOT EXISTS {LEDGER_TABLE} (
        call_id        TEXT PRIMARY KEY,
        full_name      TEXT,
        model_name     TEXT NOT NULL,
        provider       TEXT NOT NULL,
        call_type      TEXT NOT NULL,
        tier           TEXT NOT NULL,
        input_tokens   INTEGER NOT NULL DEFAULT 0,
        output_tokens  INTEGER NOT NULL DEFAULT 0,
        cost_estimate  REAL NOT NULL DEFAULT 0.0,
        usage_extra    TEXT,
        created_at     TEXT NOT NULL
    )""",
    f"CREATE INDEX IF NOT EXISTS idx_{LEDGER_TABLE}_created_at ON {LEDGER_TABLE}(created_at)",
    f"CREATE INDEX IF NOT EXISTS idx_{LEDGER_TABLE}_full_name ON {LEDGER_TABLE}(full_name)",
)


class BudgetExceeded(RuntimeError):
    """Raised when premium-call cap would be exceeded for the UTC day."""


class ModelLedger:
    """SQLite-backed ledger; cheap to instantiate, single-writer recommended."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        cur = self.conn.cursor()
        for stmt in DDL_LEDGER:
            cur.execute(stmt)
        self.conn.commit()

    @staticmethod
    def make_call_id(model_name: str, full_name: str | None, created_at: str) -> str:
        """Stable id from (model, repo, ts)."""
        seed = f"{model_name}|{full_name or '-'}|{created_at}"
        digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
        return f"mc-{digest}"

    def record(self, call: ModelCall, *, enforce_budget: bool = True) -> ModelCall:
        """Insert a ModelCall row. Enforces premium daily cap by default."""
        if enforce_budget and call.is_premium:
            day = _date_only(call.created_at)
            count = self.premium_count_on(day)
            if count >= MAX_PREMIUM_CALLS_PER_DAY:
                raise BudgetExceeded(
                    f"premium cap reached: {count}/{MAX_PREMIUM_CALLS_PER_DAY} on {day}"
                )
        row = call.to_row()
        cols = list(row.keys())
        placeholders = ",".join("?" for _ in cols)
        col_list = ",".join(cols)
        self.conn.execute(
            f"INSERT OR REPLACE INTO {LEDGER_TABLE}({col_list}) VALUES ({placeholders})",
            [row[c] for c in cols],
        )
        self.conn.commit()
        return call

    def record_event(
        self,
        *,
        model_name: str,
        provider: str,
        call_type: str,
        full_name: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_estimate: float = 0.0,
        usage_extra: dict[str, Any] | None = None,
        enforce_budget: bool = True,
        created_at: str | None = None,
        call_id: str | None = None,
    ) -> ModelCall:
        """Convenience: build + record a ModelCall in one call."""
        created_at = created_at or utc_now_iso()
        call_id = call_id or self.make_call_id(model_name, full_name, created_at + uuid.uuid4().hex[:8])
        call = ModelCall(
            call_id=call_id,
            full_name=full_name,
            model_name=model_name,
            provider=provider,
            call_type=call_type,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_estimate=cost_estimate,
            usage_extra=usage_extra or {},
            created_at=created_at,
        )
        return self.record(call, enforce_budget=enforce_budget)

    def premium_count_on(self, date_str: str) -> int:
        cur = self.conn.cursor()
        cur.execute(
            f"SELECT COUNT(*) FROM {LEDGER_TABLE} WHERE tier='premium' AND substr(created_at,1,10)=?",
            (date_str,),
        )
        return int(cur.fetchone()[0])

    def total_cost(self, since: str | None = None, until: str | None = None) -> float:
        cur = self.conn.cursor()
        clauses, params = [], []
        if since:
            clauses.append("created_at >= ?")
            params.append(since)
        if until:
            clauses.append("created_at < ?")
            params.append(until)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        cur.execute(f"SELECT COALESCE(SUM(cost_estimate),0) FROM {LEDGER_TABLE}{where}", params)
        return float(cur.fetchone()[0])

    def usage_by_model(self, since: str | None = None) -> dict[str, dict[str, float | int]]:
        cur = self.conn.cursor()
        clause = " WHERE created_at >= ?" if since else ""
        params: list[Any] = [since] if since else []
        cur.execute(
            f"""SELECT model_name,
                       COUNT(*) AS calls,
                       COALESCE(SUM(input_tokens),0)  AS input_tokens,
                       COALESCE(SUM(output_tokens),0) AS output_tokens,
                       COALESCE(SUM(cost_estimate),0) AS cost
                  FROM {LEDGER_TABLE}{clause}
              GROUP BY model_name""",
            params,
        )
        out: dict[str, dict[str, float | int]] = {}
        for r in cur.fetchall():
            out[r[0]] = {
                "calls": int(r[1]),
                "input_tokens": int(r[2]),
                "output_tokens": int(r[3]),
                "cost": float(r[4]),
            }
        return out

    def list_calls(
        self,
        *,
        full_name: str | None = None,
        call_type: str | None = None,
        since: str | None = None,
        limit: int = 1000,
    ) -> list[ModelCall]:
        clauses, params = [], []
        if full_name:
            clauses.append("full_name = ?")
            params.append(full_name)
        if call_type:
            clauses.append("call_type = ?")
            params.append(call_type)
        if since:
            clauses.append("created_at >= ?")
            params.append(since)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = (
            f"SELECT * FROM {LEDGER_TABLE}{where} ORDER BY created_at DESC LIMIT ?"
        )
        params.append(limit)
        self.conn.row_factory = sqlite3.Row
        cur = self.conn.cursor()
        cur.execute(sql, params)
        return [ModelCall.from_row(dict(r)) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def _self_test() -> dict[str, Any]:
    """Exercise schema, budget enforcement, aggregation. Returns metrics."""
    import tempfile, os as _os

    metrics: dict[str, Any] = {"tests_run": 0, "tests_passed": 0, "models": []}

    def _ok(name: str) -> None:
        metrics["tests_run"] += 1
        metrics["tests_passed"] += 1
        metrics["models"].append(name)

    # Round-trip ModelCall
    call = ModelCall(
        call_id="mc-test-1",
        full_name="owner/repo",
        model_name="qwen3.6-thunderomlx",
        provider="thunderomlx",
        call_type="preprocess",
        input_tokens=351,
        output_tokens=460,
        cost_estimate=0.0,
        usage_extra={"ttft": 8.17, "tps_out": 74.48},
    )
    row = call.to_row()
    restored = ModelCall.from_row(row)
    assert restored == call, "ModelCall row roundtrip failed"
    assert row["tier"] == "local"
    _ok("ModelCall.row_contract_roundtrip")

    # Validation guards
    for bad_kwargs, label in [
        (dict(call_type="not_a_call_type"), "bad call_type"),
        (dict(input_tokens=-1), "negative input tokens"),
        (dict(cost_estimate=-0.01), "negative cost"),
    ]:
        try:
            ModelCall(
                call_id="x",
                full_name=None,
                model_name="m",
                provider="p",
                call_type=bad_kwargs.get("call_type", "preprocess"),
                input_tokens=bad_kwargs.get("input_tokens", 0),
                output_tokens=0,
                cost_estimate=bad_kwargs.get("cost_estimate", 0.0),
            )
            raise AssertionError(f"expected ValueError for {label}")
        except ValueError:
            _ok(f"ModelCall.validation_{label.replace(' ', '_')}")

    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
        db_path = tf.name
    try:
        conn = sqlite3.connect(db_path)
        ledger = ModelLedger(conn)
        # Re-init must be idempotent
        ModelLedger(conn)
        _ok("ModelLedger.schema_idempotent")

        # Record a local call → no budget effect
        local_call = ledger.record_event(
            model_name="qwen3.6-thunderomlx",
            provider="thunderomlx",
            call_type="preprocess",
            full_name="owner/repo",
            input_tokens=100,
            output_tokens=50,
        )
        assert local_call.tier == "local"
        _ok("ModelLedger.record_local_call")

        # Record premium calls up to cap
        for i in range(MAX_PREMIUM_CALLS_PER_DAY):
            ledger.record_event(
                model_name="claude-opus",
                provider="anthropic",
                call_type="editorial",
                full_name="owner/repo",
                input_tokens=200,
                output_tokens=200,
                cost_estimate=0.05,
                created_at=f"2026-05-27T0{i % 10}:00:0{i % 10}Z",
                call_id=f"premium-{i}",
            )
        _ok("ModelLedger.record_premium_up_to_cap")

        # 21st premium call must fail
        try:
            ledger.record_event(
                model_name="claude-opus",
                provider="anthropic",
                call_type="editorial",
                created_at="2026-05-27T09:00:00Z",
                call_id="premium-overflow",
            )
            raise AssertionError("expected BudgetExceeded")
        except BudgetExceeded:
            _ok("ModelLedger.budget_cap_enforced")

        # Cap is per-day: a call on a different date is allowed
        ledger.record_event(
            model_name="claude-opus",
            provider="anthropic",
            call_type="editorial",
            created_at="2026-05-28T00:00:00Z",
            call_id="next-day",
            cost_estimate=0.05,
        )
        _ok("ModelLedger.cap_resets_per_day")

        # enforce_budget=False bypass
        ledger.record_event(
            model_name="claude-opus",
            provider="anthropic",
            call_type="editorial",
            created_at="2026-05-27T23:00:00Z",
            call_id="bypass",
            cost_estimate=0.05,
            enforce_budget=False,
        )
        _ok("ModelLedger.bypass_when_enforce_false")

        # Aggregations
        assert ledger.premium_count_on("2026-05-27") == MAX_PREMIUM_CALLS_PER_DAY + 1
        _ok("ModelLedger.premium_count_aggregation")

        usage = ledger.usage_by_model()
        assert "claude-opus" in usage and usage["claude-opus"]["calls"] >= MAX_PREMIUM_CALLS_PER_DAY
        assert "qwen3.6-thunderomlx" in usage
        _ok("ModelLedger.usage_by_model")

        total = ledger.total_cost()
        assert total > 0
        _ok("ModelLedger.total_cost")

        listed = ledger.list_calls(full_name="owner/repo", call_type="preprocess")
        assert any(c.model_name == "qwen3.6-thunderomlx" for c in listed)
        _ok("ModelLedger.list_calls_filter")

        conn.close()
    finally:
        _os.unlink(db_path)

    return metrics


if __name__ == "__main__":
    import sys as _sys

    m = _self_test()
    print(json.dumps(m, indent=2))
    if m["tests_run"] != m["tests_passed"]:
        _sys.exit(1)
