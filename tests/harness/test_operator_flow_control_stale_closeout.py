from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path


LIB = Path(__file__).resolve().parents[2] / "harness" / "lib"
sys.path.insert(0, str(LIB))

import operator_flow_control as flow  # noqa: E402


def test_contract_closeout_freshness_uses_attributed_result_time(monkeypatch, tmp_path: Path) -> None:
    runtime = tmp_path / "harness"
    result_path = runtime / "run" / "operator-results" / "worker" / "old" / "result.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text(
        json.dumps({"finished_at": "2026-08-30T01:00:00Z"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(flow, "HARNESS_DIR", runtime)
    evidence = {"result_json": str(result_path)}
    now = dt.datetime(2026, 8, 30, 2, 0, tzinfo=dt.timezone.utc)

    assert flow.contract_closeout_evidence_is_stale(evidence, now=now, max_age_seconds=900)
    assert not flow.contract_closeout_evidence_is_stale(evidence, now=now, max_age_seconds=7200)


def test_pruner_clears_stale_closeout_registry_and_dynamic_status(monkeypatch, tmp_path: Path) -> None:
    runtime = tmp_path / "harness"
    result_path = runtime / "run" / "operator-results" / "worker" / "old" / "result.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text(json.dumps({"finished_at": "2026-08-30T01:00:00Z"}), encoding="utf-8")
    registry_path = runtime / "config" / "physical-operators.json"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(
        json.dumps(
            {
                "operators": {
                    "worker": {
                        "quota_guard_state": "cooldown",
                        "quota_refresh_at": "2026-08-30T03:00:00Z",
                        "state": {"runtime_state": "cooldown", "cooldown_until": "2026-08-30T03:00:00Z"},
                        "flow_control": {
                            "last_block_reason": "contract_closeout_failed",
                            "last_block_source": "graph_node_dispatcher",
                            "last_block_excerpt": json.dumps({"result_json": str(result_path)}),
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    class Runtime:
        OPERATOR_STATUS_DIR = runtime / "run" / "operator-status"
        cleared: list[str] = []

        @classmethod
        def clear_operator_status(cls, operator_id: str) -> None:
            cls.cleared.append(operator_id)

    monkeypatch.setattr(flow, "HARNESS_DIR", runtime)
    monkeypatch.setattr(flow, "PHYSICAL_OPERATORS_PATH", registry_path)
    monkeypatch.setattr(flow, "_operator_runtime_module", lambda: Runtime)
    monkeypatch.setattr(flow, "_now", lambda: dt.datetime(2026, 8, 30, 2, 0, tzinfo=dt.timezone.utc))

    result = flow.prune_expired_operator_config_blocks()
    saved = json.loads(registry_path.read_text(encoding="utf-8"))["operators"]["worker"]

    assert result["pruned"][0]["expired_at"] == "stale_contract_closeout_evidence"
    assert saved["quota_guard_state"] == "ok"
    assert Runtime.cleared == ["worker"]
