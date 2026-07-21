from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from knowledge_ingest_dispatcher_closeout import build_eval_payload, verify  # noqa: E402


def test_build_eval_payload_pass_shape(tmp_path: Path) -> None:
    runtime_root = tmp_path
    (runtime_root / "lib").mkdir()
    (runtime_root / "tests").mkdir()
    (runtime_root / "sprints").mkdir()
    (runtime_root / "lib" / "knowledge_ingest_dispatcher.py").write_text("x\n", encoding="utf-8")
    (runtime_root / "tests" / "test-knowledge-ingest-dispatcher.sh").write_text("x\n", encoding="utf-8")
    (runtime_root / "solar-harness.sh").write_text("x\n", encoding="utf-8")
    traceability = runtime_root / "sprints" / "sprint-20260524-105859.traceability.json"
    traceability.write_text("{}\n", encoding="utf-8")

    verification = {
        "ok": True,
        "summary": "ok",
        "status_result": {"returncode": 0},
        "dispatcher_result": {"returncode": 0},
        "missing_paths": [],
    }
    payload = build_eval_payload(verification)
    assert payload["verdict"] == "PASS"
    assert payload["node_id"] == "N2_dispatcher_cli"


def test_verify_creates_traceability_and_detects_missing(monkeypatch, tmp_path: Path) -> None:
    runtime_root = tmp_path
    (runtime_root / "lib").mkdir()
    (runtime_root / "tests").mkdir()
    (runtime_root / "sprints").mkdir()
    (runtime_root / "lib" / "knowledge_ingest_dispatcher.py").write_text("x\n", encoding="utf-8")
    (runtime_root / "tests" / "test-knowledge-ingest-dispatcher.sh").write_text("x\n", encoding="utf-8")
    (runtime_root / "solar-harness.sh").write_text("x\n", encoding="utf-8")

    calls = []

    def _fake_run(_runtime_root: Path, args: list[str]) -> dict[str, object]:
        calls.append(args)
        return {"returncode": 0, "stdout": "{}", "stderr": "", "command": " ".join(args)}

    monkeypatch.setattr("knowledge_ingest_dispatcher_closeout._run", _fake_run)
    result = verify(runtime_root)
    assert result["ok"] is True
    traceability = runtime_root / "sprints" / "sprint-20260524-105859.traceability.json"
    assert traceability.exists()
    data = json.loads(traceability.read_text(encoding="utf-8"))
    assert "N2_dispatcher_cli" in data["nodes"]
    assert any("knowledge-ingest" in " ".join(call) for call in calls)
