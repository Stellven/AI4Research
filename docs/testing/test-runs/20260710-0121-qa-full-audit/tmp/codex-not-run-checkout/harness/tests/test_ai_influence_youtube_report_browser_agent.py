import json
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from ai_influence_youtube_report.browser_agent import BrowserAgentClient, LocalModelSubstitutionError  # noqa: E402


class FakeProvider:
    def call(self, stage, payload, *, requested_model):
        return {
            "schema_version": f"{stage}.fake",
            "model_call_id": f"{stage}-1",
            "browser_session_id": "session-1",
            "chatgpt_url": "https://chatgpt.com/c/fake",
            "resolved_model": requested_model,
        }


def test_browser_agent_client_writes_ledger_for_each_phase(tmp_path: Path) -> None:
    ledger = tmp_path / "model_call_ledger.jsonl"
    client = BrowserAgentClient(FakeProvider(), ledger_path=ledger, sprint_id="sprint-1")

    client.plan({}, requested_model="chatgpt-5.5-thinking-high", run_id="run-1")
    client.write_chapter({}, requested_model="chatgpt-5.5-thinking-high", run_id="run-1", chapter_id="c1")
    client.synthesize([], requested_model="chatgpt-5.5-thinking-high", run_id="run-1")

    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert [row["stage"] for row in rows] == ["phase1", "phase2", "phase3"]


def test_browser_agent_client_rejects_local_model_substitution(tmp_path: Path) -> None:
    client = BrowserAgentClient(FakeProvider(), ledger_path=tmp_path / "ledger.jsonl", sprint_id="sprint-1")

    with pytest.raises(LocalModelSubstitutionError):
        client.plan({}, requested_model="ThunderOMLX", run_id="run-1")


def test_phase2_duplicate_chapter_call_is_rejected(tmp_path: Path) -> None:
    client = BrowserAgentClient(FakeProvider(), ledger_path=tmp_path / "ledger.jsonl", sprint_id="sprint-1")
    client.write_chapter({}, requested_model="chatgpt-5.5-thinking-high", run_id="run-1", chapter_id="c1")

    with pytest.raises(ValueError, match="duplicate"):
        client.write_chapter({}, requested_model="chatgpt-5.5-thinking-high", run_id="run-1", chapter_id="c1")
