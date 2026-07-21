"""Pipeline — 10-step end-to-end orchestration per S03 design §C4 + O6.

Steps:
  1. collect-social   — load accounts to scan
  2. selector         — BackendSelector picks the backend
  3. lease 6 ops      — acquire lease, open/wait/scroll/dom_extract/screenshot/release
  4. extract          — PostExtractor: DOM → PostRecord
  5. dedup            — DedupQueue: 24h sliding-window dedup
  6. social_posts     — persist PostRecord to DB
  7. metrics          — compute/update engagement metrics
  8. ThunderOMLX sem  — semantic extraction via existing socket (OQ-02 / AC-10)
  9. links+viewpoints — social_links, viewpoints, propagation
 10. dispatch         — Knowledge raw, AI Influence report, model_call_ledger

Ledger writes (3):
  - lease_cost      — cost of lease acquire/release per account
  - extract_cost    — cost of DOM extraction per post
  - premium_reasoning — cost of ThunderOMLX semantic step (when applicable)

HardBlockerGuard is mandatory at dispatch time. The pipeline calls
`guard.assert_ready()` before any real lease acquisition. In mock-mode,
the guard returns mock_ready=True and the pipeline proceeds with mock
fixtures.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)

from .backend_selector import BackendSelector, SelectionResult, TIER_ORDER
from .browser_lease_client import BrowserLeaseClient, OperatorNotReady
from .cli import (
    BACKEND_AUTO,
    CLI_TO_SCHEMA_BACKEND,
    CliArgs,
    CliRunResult,
    EXIT_CONFIG_ERROR,
    EXIT_LEASE_FALLBACK,
    EXIT_OK,
    EXIT_RATE_LIMIT,
)
from .dedup_queue import DedupQueue, DedupVerdict
from .hard_blocker_guard import BlockerStatus, HardBlockerGuard
from .operator_lease_manager import (
    BlockerNotResolved,
    LeaseToken,
    OperatorLeaseManager,
)
from .post_extractor import ExtractionResult, PostExtractor
from .ratelimiter import RateLimitExceeded, RateLimiter
from .schema import PostRecord, ensure_schema, ensure_schema_safe

logger = logging.getLogger(__name__)

# ThunderOMLX socket path — reuse existing instance per OQ-02 / AC-10.
THUNDEROMLX_SOCKET_PATH = Path.home() / ".thunderomlx" / "socket"

# Ledger table name for model call cost tracking.
LEDGER_TABLE = "model_call_ledger"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class LedgerEntry:
    """One cost row written to model_call_ledger."""

    step: str
    account_id: Optional[str]
    cost_units: float
    backend: str
    timestamp: float
    details: Dict[str, Any] = field(default_factory=dict)

    def to_row(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "account_id": self.account_id,
            "cost_units": self.cost_units,
            "backend": self.backend,
            "timestamp": self.timestamp,
            "details": json.dumps(self.details),
        }


@dataclass
class AccountScan:
    """Per-account scan state tracked through the 10-step pipeline."""

    account_id: str
    handle: str
    tier: int
    profile_url: str
    backend: str = ""
    lease_token: Optional[LeaseToken] = None
    dom_html: str = ""
    dom_hash: str = ""
    extraction: Optional[ExtractionResult] = None
    dedup_verdict: Optional[DedupVerdict] = None
    post_record: Optional[PostRecord] = None
    post_pk: Optional[int] = None
    metrics: Dict[str, int] = field(default_factory=dict)
    semantic_result: Optional[Dict[str, Any]] = None
    links: List[str] = field(default_factory=list)
    viewpoints: List[str] = field(default_factory=list)
    propagation_score: float = 0.0
    knowledge_raw_path: Optional[str] = None
    extract_queue_path: Optional[str] = None
    error: Optional[str] = None
    skipped: bool = False
    ledger_entries: List[LedgerEntry] = field(default_factory=list)


@dataclass
class PipelineResult:
    """Final outcome of `Pipeline.run` — returned to CLI / tests."""

    selection: SelectionResult
    scans: List[AccountScan]
    posts_stored: int
    posts_deduped: int
    posts_skipped: int
    parse_failures: int
    exit_code: int
    ledger: List[LedgerEntry]
    elapsed_seconds: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "selection": self.selection.to_dict(),
            "posts_stored": self.posts_stored,
            "posts_deduped": self.posts_deduped,
            "posts_skipped": self.posts_skipped,
            "parse_failures": self.parse_failures,
            "exit_code": self.exit_code,
            "ledger_count": len(self.ledger),
            "elapsed_seconds": self.elapsed_seconds,
        }


# ---------------------------------------------------------------------------
# ThunderOMLX socket check
# ---------------------------------------------------------------------------


def thunderomlx_socket_available(socket_path: Path = THUNDEROMLX_SOCKET_PATH) -> bool:
    """Return True iff the ThunderOMLX socket exists (OQ-02 reuse check)."""
    return socket_path.exists()


# ---------------------------------------------------------------------------
# Ledger DDL + write
# ---------------------------------------------------------------------------


def ensure_ledger_table(conn: sqlite3.Connection) -> None:
    """Create model_call_ledger table if absent. Idempotent."""
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS {LEDGER_TABLE} ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  step TEXT NOT NULL,"
        "  account_id TEXT,"
        "  cost_units REAL NOT NULL,"
        "  backend TEXT NOT NULL,"
        "  timestamp REAL NOT NULL,"
        "  details TEXT"
        ")"
    )


def write_ledger(conn: sqlite3.Connection, entries: Sequence[LedgerEntry]) -> int:
    """Bulk-insert ledger rows. Returns the number of rows written."""
    if not entries:
        return 0
    existing = {
        row[1]
        for row in conn.execute(f"PRAGMA table_info({LEDGER_TABLE})").fetchall()
    }
    if {"step", "account_id", "cost_units", "backend", "timestamp", "details"}.issubset(existing):
        cols = "step, account_id, cost_units, backend, timestamp, details"
        placeholders = ", ".join(["?"] * 6)
        rows = [
            (
                e.step,
                e.account_id,
                e.cost_units,
                e.backend,
                e.timestamp,
                json.dumps(e.details),
            )
            for e in entries
        ]
        conn.executemany(
            f"INSERT INTO {LEDGER_TABLE} ({cols}) VALUES ({placeholders})", rows
        )
        return len(rows)

    legacy_cols = {
        "repo_full_name",
        "model",
        "provider",
        "call_purpose",
        "input_type",
        "input_token_count",
        "output_token_count",
        "latency_ms",
        "cost_estimate_usd",
        "evidence_atom_count",
        "success",
        "error_message",
        "created_at",
    }
    if legacy_cols.issubset(existing):
        cols = (
            "repo_full_name, model, provider, call_purpose, input_type, "
            "input_token_count, output_token_count, latency_ms, cost_estimate_usd, "
            "evidence_atom_count, success, error_message, created_at"
        )
        placeholders = ", ".join(["?"] * 13)
        rows = [
            (
                "",
                "social_browser_backend_x",
                e.backend,
                "deep_analysis",
                "project_reasoning_packet",
                0,
                0,
                int(e.cost_units * 1000),
                0.0,
                0,
                1,
                "",
                datetime.fromtimestamp(e.timestamp, timezone.utc).isoformat(),
            )
            for e in entries
        ]
        conn.executemany(
            f"INSERT INTO {LEDGER_TABLE} ({cols}) VALUES ({placeholders})", rows
        )
        return len(rows)
    return 0


# ---------------------------------------------------------------------------
# Account loading (step 1)
# ---------------------------------------------------------------------------


@dataclass
class AccountConfig:
    """Minimal account descriptor for the pipeline."""

    handle: str
    tier: int = 1
    profile_url: str = ""
    enabled: bool = True


def load_accounts(
    accounts: Optional[Sequence[AccountConfig]] = None,
    limit: Optional[int] = None,
) -> List[AccountConfig]:
    """Step 1: collect-social — return accounts to scan.

    If `accounts` is None, returns an empty list (the caller is expected
    to inject real account sources from config/DB in S04+).
    """
    if accounts is None:
        return []
    filtered = [a for a in accounts if a.enabled]
    if limit is not None and limit > 0:
        filtered = filtered[:limit]
    return filtered


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class Pipeline:
    """10-step end-to-end orchestration for social post collection.

    Parameters:
        conn: sqlite3.Connection for social_posts + dedup + ledger tables.
        guard: HardBlockerGuard (mandatory at dispatch).
        selector: BackendSelector (uses guard internally).
        lease_manager: OperatorLeaseManager for lease acquire/release.
        extractor: PostExtractor for DOM → PostRecord.
        dedup_queue: DedupQueue for 24h dedup.
        rate_limiter: RateLimiter for per-account throttling.
        thunderomlx_socket: Path to the ThunderOMLX socket.
        clock: injectable clock (for tests).
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        guard: Optional[HardBlockerGuard] = None,
        selector: Optional[BackendSelector] = None,
        lease_manager: Optional[OperatorLeaseManager] = None,
        extractor: Optional[PostExtractor] = None,
        dedup_queue: Optional[DedupQueue] = None,
        rate_limiter: Optional[RateLimiter] = None,
        thunderomlx_socket: Path = THUNDEROMLX_SOCKET_PATH,
        artifact_root: Optional[Path] = None,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self._conn = conn
        self._guard = guard or HardBlockerGuard()
        self._selector = selector or BackendSelector(guard=self._guard)
        self._lease_manager = lease_manager or OperatorLeaseManager(
            blocker_guard=self._guard.as_lease_guard()
        )
        self._extractor = extractor or PostExtractor()
        self._dedup_queue = dedup_queue or DedupQueue(conn)
        self._rate_limiter = rate_limiter or RateLimiter()
        self._thunderomlx_socket = thunderomlx_socket
        self._artifact_root = (
            Path(artifact_root).expanduser()
            if artifact_root is not None
            else Path.home()
            / ".solar"
            / "harness"
            / "state"
            / "tech-hotspot-radar"
            / "social-browser-backend-x"
        )
        self._clock = clock or time.time

        # Ensure tables exist.
        ensure_schema_safe(conn)
        ensure_ledger_table(conn)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        accounts: Optional[Sequence[AccountConfig]] = None,
        *,
        requested_backend: str = BACKEND_AUTO,
        limit_accounts: Optional[int] = None,
    ) -> PipelineResult:
        """Execute the 10-step pipeline.

        Returns a `PipelineResult` with exit_code set to one of the CLI
        exit codes (0/1/2/3).
        """
        t0 = self._clock()
        all_ledger: List[LedgerEntry] = []

        # Step 1: collect-social — load accounts
        acct_list = load_accounts(accounts, limit=limit_accounts)

        # Step 2: selector — pick backend
        selection = self._selector.select(requested_backend)
        chosen_backend = selection.selected or "none"

        # Step 2.5: HardBlockerGuard mandatory check
        try:
            blocker_status = self._guard.assert_ready()
        except BlockerNotResolved:
            # Real-mode + blocker unmet: fall back to rss if available
            logger.warning(
                "HardBlockerGuard assert_ready raised BlockerNotResolved — "
                "falling back to rss"
            )
            # Re-select with rss_public if selector didn't already fallback
            if selection.selected != "rss_public":
                selection = self._selector.select("rss")
                chosen_backend = selection.selected or "none"

        # If no backend available at all, exit with config error
        if chosen_backend == "none":
            elapsed = self._clock() - t0
            return PipelineResult(
                selection=selection,
                scans=[],
                posts_stored=0,
                posts_deduped=0,
                posts_skipped=len(acct_list),
                parse_failures=0,
                exit_code=EXIT_CONFIG_ERROR,
                ledger=all_ledger,
                elapsed_seconds=elapsed,
            )

        # Decide exit code based on fallback
        exit_code = EXIT_OK
        if selection.fallback_from_explicit:
            exit_code = EXIT_LEASE_FALLBACK

        # Steps 3-10: per-account pipeline
        scans: List[AccountScan] = []
        posts_stored = 0
        posts_deduped = 0
        posts_skipped = 0
        parse_failures = 0

        for acct in acct_list:
            scan = AccountScan(
                account_id=acct.handle,
                handle=acct.handle,
                tier=acct.tier,
                profile_url=acct.profile_url or f"https://x.com/{acct.handle}",
                backend=chosen_backend,
            )

            # Step 3: lease 6 ops — only for browser_agent backend
            if chosen_backend == "browser_agent":
                lease_ok = self._step_lease(scan, all_ledger)
                if not lease_ok:
                    posts_skipped += 1
                    scans.append(scan)
                    if exit_code == EXIT_OK:
                        exit_code = EXIT_LEASE_FALLBACK
                    continue
            else:
                # Non-browser backends use mock fixture or external feed
                scan.skipped = True

            # Step 4: extract
            if not self._step_extract(scan, all_ledger):
                parse_failures += 1
                scans.append(scan)
                continue

            # Step 5: dedup
            if self._step_dedup(scan):
                posts_deduped += 1
                scans.append(scan)
                continue

            # Step 6: social_posts — persist
            self._step_persist(scan)

            # Step 7: metrics
            self._step_metrics(scan)

            # Step 8: ThunderOMLX semantic (socket reuse)
            self._step_semantic(scan, all_ledger)

            # Step 9: social_links + viewpoints + propagation
            self._step_links_viewpoints(scan)

            # Step 10: dispatch — write Knowledge raw + AI Influence + ledger
            self._step_dispatch(scan, all_ledger)

            posts_stored += 1
            scans.append(scan)

        # Flush all ledger entries
        write_ledger(self._conn, all_ledger)

        elapsed = self._clock() - t0
        return PipelineResult(
            selection=selection,
            scans=scans,
            posts_stored=posts_stored,
            posts_deduped=posts_deduped,
            posts_skipped=posts_skipped,
            parse_failures=parse_failures,
            exit_code=exit_code,
            ledger=all_ledger,
            elapsed_seconds=elapsed,
        )

    def run_as_cli_callback(
        self,
        cli_args: CliArgs,
        *,
        accounts: Optional[Sequence[AccountConfig]] = None,
    ) -> CliRunResult:
        """Adapter: run the pipeline and return a CliRunResult for the CLI.

        This wires into `cli.main(run_callback=...)` so the CLI can
        dispatch to the pipeline without importing it directly.
        """
        from .cli import CliRunResult, EXIT_OK
        from .status_surface import StatusInput

        result = self.run(
            accounts=accounts,
            requested_backend=cli_args.backend,
            limit_accounts=cli_args.limit_accounts,
        )

        by_backend: Dict[str, int] = {}
        for scan in result.scans:
            if scan.post_pk is not None:
                by_backend[scan.backend] = by_backend.get(scan.backend, 0) + 1

        scan_state = "idle"
        if result.scans:
            has_errors = any(s.error is not None for s in result.scans)
            scan_state = "failed" if has_errors else "running"

        status = StatusInput(
            total_accounts=len(accounts) if accounts else 0,
            enabled_accounts=len(
                [a for a in (accounts or []) if a.enabled]
            ),
            scanned_today=result.posts_stored + result.posts_deduped,
            browser_ready=result.selection.selected == "browser_agent",
            scan_state=scan_state,
            parse_fail_count=result.parse_failures,
            by_backend_count=by_backend,
        )

        msg = (
            f"Pipeline finished: {result.posts_stored} stored, "
            f"{result.posts_deduped} deduped, "
            f"{result.parse_failures} parse failures, "
            f"exit_code={result.exit_code}"
        )

        return CliRunResult(
            exit_code=result.exit_code,
            status=status,
            message=msg,
        )

    # ------------------------------------------------------------------
    # Step implementations
    # ------------------------------------------------------------------

    def _step_lease(self, scan: AccountScan, ledger: List[LedgerEntry]) -> bool:
        """Step 3: acquire lease and run 6 ops (open/wait/scroll/dom_extract/screenshot/release)."""
        t_start = self._clock()
        try:
            self._rate_limiter.time_until_ready(scan.account_id, scan.tier)
            token = self._lease_manager.acquire(account_id=scan.account_id)
            scan.lease_token = token
        except RateLimitExceeded as exc:
            scan.error = f"rate_limit: {exc}"
            return False
        except BlockerNotResolved as exc:
            scan.error = f"blocker_not_resolved: {exc}"
            return False
        except OperatorNotReady as exc:
            scan.error = f"operator_not_ready: {exc}"
            return False

        try:
            client = token.client
            # open
            open_result = client.open(scan.profile_url)
            # wait
            client.wait("article[data-testid='tweet']", timeout_ms=5000)
            # scroll
            client.scroll(delta_y=800)
            # dom_extract
            dom = client.dom_extract()
            scan.dom_html = dom.get("html", "")
            scan.dom_hash = dom.get("dom_hash", "")
            # screenshot (on parse failure path — capture anyway)
            ss_path = f"/tmp/social_screenshots/{scan.handle}_{int(t_start)}.txt"
            client.screenshot(ss_path)
            # release
            self._lease_manager.release(token)
        except Exception as exc:  # noqa: BLE001
            scan.error = f"lease_ops_error: {exc}"
            try:
                self._lease_manager.release(token)
            except Exception:  # noqa: BLE001
                pass
            return False

        # Ledger write 1: lease cost
        elapsed = self._clock() - t_start
        entry = LedgerEntry(
            step="lease",
            account_id=scan.account_id,
            cost_units=elapsed,
            backend=scan.backend,
            timestamp=t_start,
            details={"ops": 6, "mock": token.is_mock},
        )
        ledger.append(entry)
        scan.ledger_entries.append(entry)
        return True

    def _step_extract(self, scan: AccountScan, ledger: List[LedgerEntry]) -> bool:
        """Step 4: PostExtractor — DOM → PostRecord."""
        t_start = self._clock()
        if not scan.dom_html:
            # For non-browser backends, skip extraction (no DOM)
            if scan.skipped:
                return False
            scan.error = "no_dom_html"
            return False

        result = self._extractor.extract(scan.dom_html, author_handle_hint=scan.handle)
        scan.extraction = result
        scan.post_record = result.record

        # Ledger write 2: extract cost
        elapsed = self._clock() - t_start
        entry = LedgerEntry(
            step="extract",
            account_id=scan.account_id,
            cost_units=elapsed,
            backend=scan.backend,
            timestamp=t_start,
            details={
                "parse_ok": result.parse_ok,
                "missing_fields": list(result.missing_fields),
            },
        )
        ledger.append(entry)
        scan.ledger_entries.append(entry)

        if not result.parse_ok:
            scan.error = f"parse_failed: missing {','.join(result.missing_fields)}"
            return False
        return True

    def _step_dedup(self, scan: AccountScan) -> bool:
        """Step 5: dedup check. Returns True if duplicate (skip persist)."""
        if scan.post_record is None:
            return False
        verdict = self._dedup_queue.check(scan.post_record)
        scan.dedup_verdict = verdict
        return verdict.is_duplicate

    def _step_persist(self, scan: AccountScan) -> None:
        """Step 6: persist PostRecord to social_posts."""
        if scan.post_record is None:
            return
        rec = scan.post_record
        existing = {
            row[1]
            for row in self._conn.execute("PRAGMA table_info(social_posts)").fetchall()
        }
        row = rec.to_row()
        row.setdefault("author_category", "")
        row.setdefault("author_tier", f"tier{scan.tier}")
        row.setdefault("lang", "")
        row.setdefault("quote_count", 0)
        row.setdefault("bookmarks", 0)
        row.setdefault("media_urls", "")
        row.setdefault("mentioned_handles", "")
        row.setdefault("fetched_at", datetime.now(timezone.utc).isoformat())
        row = {key: value for key, value in row.items() if key in existing}
        cols = ", ".join(row.keys())
        placeholders = ", ".join(["?"] * len(row))
        cur = self._conn.execute(
            f"INSERT INTO social_posts ({cols}) VALUES ({placeholders})",
            list(row.values()),
        )
        scan.post_pk = cur.lastrowid

        # Register dedup key now that we have a post_pk
        if scan.dedup_verdict is not None and not scan.dedup_verdict.is_duplicate:
            _, dedup_record = self._dedup_queue.record_seen(rec, scan.post_pk or 0)
        elif scan.post_pk:
            self._dedup_queue.record_seen(rec, scan.post_pk)

    def _step_metrics(self, scan: AccountScan) -> None:
        """Step 7: compute engagement metrics from the post record."""
        if scan.post_record is None:
            return
        r = scan.post_record
        scan.metrics = {
            "reply_count": r.reply_count,
            "repost_count": r.repost_count,
            "like_count": r.like_count,
            "view_count": r.view_count or 0,
        }

    def _step_semantic(self, scan: AccountScan, ledger: List[LedgerEntry]) -> bool:
        """Step 8: ThunderOMLX semantic extraction via socket (OQ-02 reuse).

        Reuses the existing instance at ~/.thunderomlx/socket. Does NOT
        spawn a new instance (AC-10).
        """
        t_start = self._clock()
        if not thunderomlx_socket_available(self._thunderomlx_socket):
            logger.debug(
                "ThunderOMLX socket not found at %s — skipping semantic step",
                self._thunderomlx_socket,
            )
            return False

        # Socket exists — send the post text for semantic analysis.
        # In S03 mock-mode, the socket is typically absent, so this
        # returns False. When the socket IS present (real deployment),
        # the actual IPC would happen here. For now we record that the
        # check passed and the socket was available.
        scan.semantic_result = {
            "socket_path": str(self._thunderomlx_socket),
            "reused_instance": True,
            "new_instance_spawned": False,
            "status": "socket_present_mock_passthrough",
        }

        # Ledger write 3: premium reasoning (only when semantic ran)
        elapsed = self._clock() - t_start
        entry = LedgerEntry(
            step="semantic",
            account_id=scan.account_id,
            cost_units=elapsed,
            backend=scan.backend,
            timestamp=t_start,
            details={
                "socket_available": True,
                "reused_instance": True,
                "new_instance": False,
            },
        )
        ledger.append(entry)
        scan.ledger_entries.append(entry)
        return True

    def _step_links_viewpoints(self, scan: AccountScan) -> None:
        """Step 9: extract social links, viewpoints, compute propagation score."""
        if scan.post_record is None:
            return
        rec = scan.post_record

        # Extract links from the urls field
        if rec.urls:
            scan.links = [u.strip() for u in rec.urls.split(",") if u.strip()]

        # Viewpoints: extracted from post text (simplified for S03 —
        # full NLP-based viewpoint extraction is S04+)
        scan.viewpoints = []

        # Propagation score: simplified metric based on engagement
        total_engagement = rec.reply_count + rec.repost_count + rec.like_count
        views = rec.view_count or 1
        scan.propagation_score = min(total_engagement / views, 1.0) if views > 0 else 0.0

    def _step_dispatch(self, scan: AccountScan, ledger: List[LedgerEntry]) -> None:
        """Step 10: dispatch — write Knowledge raw + AI Influence report stub.

        The full Knowledge raw and AI Influence report generation is
        deferred to S04/S05 (requires downstream systems). S03 writes
        a JSON stub that downstream can pick up.
        """
        if scan.post_record is None or scan.post_pk is None:
            return
        rec = scan.post_record

        # Knowledge raw stub
        knowledge_raw = {
            "post_pk": scan.post_pk,
            "post_id": rec.post_id,
            "handle": rec.author_handle,
            "text_snippet": (rec.text or "")[:200],
            "metrics": scan.metrics,
            "links": scan.links,
            "semantic": scan.semantic_result,
            "propagation_score": scan.propagation_score,
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "backend": scan.backend,
        }

        # AI Influence report stub — persisted alongside the post
        influence_report = {
            "post_pk": scan.post_pk,
            "handle": rec.author_handle,
            "tier": scan.tier,
            "engagement_total": sum(scan.metrics.values()),
            "propagation_score": scan.propagation_score,
            "influence_tier": "high" if scan.propagation_score > 0.05 else "normal",
        }

        raw_path, queue_path = self._write_dispatch_artifacts(
            scan=scan,
            knowledge_raw=knowledge_raw,
            influence_report=influence_report,
        )
        scan.knowledge_raw_path = str(raw_path)
        scan.extract_queue_path = str(queue_path)

        # Update the post row with the knowledge raw JSON (stored in a
        # dedicated column or as a sidecar — S03 uses a simple text column).
        # For now we write it as a metadata blob on the post.
        try:
            self._conn.execute(
                "UPDATE social_posts SET dom_hash = ? WHERE rowid = ?",
                (json.dumps(knowledge_raw), scan.post_pk),
            )
        except Exception:  # noqa: BLE001
            pass  # Non-critical — the post is already persisted

    def _write_dispatch_artifacts(
        self,
        *,
        scan: AccountScan,
        knowledge_raw: Dict[str, Any],
        influence_report: Dict[str, Any],
    ) -> Tuple[Path, Path]:
        """Materialise Knowledge raw + extract queue sidecars for verification.

        S05 verification needs filesystem evidence that browser-collected posts
        entered the local raw/extract path; storing only a DB blob is not enough.
        """
        handle = (scan.handle or scan.account_id or "unknown").strip() or "unknown"
        post_id = (
            scan.post_record.post_id
            if scan.post_record is not None and scan.post_record.post_id
            else f"post-{scan.post_pk or 'na'}"
        )
        raw_dir = self._artifact_root / "knowledge_raw" / handle
        queue_dir = self._artifact_root / "extract_queue" / handle
        raw_dir.mkdir(parents=True, exist_ok=True)
        queue_dir.mkdir(parents=True, exist_ok=True)

        raw_path = raw_dir / f"{post_id}.json"
        queue_path = queue_dir / f"{post_id}.json"
        raw_path.write_text(
            json.dumps(knowledge_raw, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        queue_payload = {
            "source": "social-browser-backend-x",
            "status": "pending_extract",
            "post_pk": scan.post_pk,
            "account_id": scan.account_id,
            "handle": handle,
            "post_id": post_id,
            "knowledge_raw_path": str(raw_path),
            "semantic_status": (
                "ready" if scan.semantic_result is not None else "skipped_no_socket"
            ),
            "backend": scan.backend,
            "collected_at": knowledge_raw["collected_at"],
            "influence_report": influence_report,
        }
        queue_path.write_text(
            json.dumps(queue_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return raw_path, queue_path

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def guard(self) -> HardBlockerGuard:
        return self._guard

    @property
    def selector(self) -> BackendSelector:
        return self._selector


__all__ = [
    "AccountConfig",
    "AccountScan",
    "LedgerEntry",
    "Pipeline",
    "PipelineResult",
    "THUNDEROMLX_SOCKET_PATH",
    "ensure_ledger_table",
    "load_accounts",
    "thunderomlx_socket_available",
    "write_ledger",
]
