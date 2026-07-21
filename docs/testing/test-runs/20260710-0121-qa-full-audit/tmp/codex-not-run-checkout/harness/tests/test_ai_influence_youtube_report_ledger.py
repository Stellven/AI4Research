import json
import pytest
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from ai_influence_youtube_report.ledger import append_model_call_ledger  # noqa: E402


def test_append_model_call_ledger_is_jsonl_append_only(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    row = {
        "schema_version": "model_call_ledger.v1",
        "call_id": "c1",
        "stage": "phase1",
        "cost_estimate_usd": 0.0,
        "sprint_id": "sprint",
        "browser_session_id": "session",
        "chatgpt_url": "https://chatgpt.com/c/fake",
        "latency_ms": 1,
    }

    append_model_call_ledger(path, row)
    append_model_call_ledger(path, {**row, "call_id": "c2"})

    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert [r["call_id"] for r in rows] == ["c1", "c2"]


def test_append_model_call_ledger_requires_contract_fields(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="missing required"):
        append_model_call_ledger(tmp_path / "ledger.jsonl", {"call_id": "c1"})
