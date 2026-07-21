from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from remote_dispatch_productization_closeout import _build_eval_payload, verify  # noqa: E402


def test_build_eval_payload_marks_pass() -> None:
    payload = _build_eval_payload(
        {
            "ok": True,
            "summary": "ok",
            "pytest": {"returncode": 0},
            "missing_paths": [],
        }
    )
    assert payload["verdict"] == "PASS"
    assert payload["node_id"] == "N3"


def test_verify_writes_handoff_and_traceability(monkeypatch, tmp_path: Path) -> None:
    runtime_root = tmp_path
    (runtime_root / "lib").mkdir()
    (runtime_root / "tests" / "graph").mkdir(parents=True)
    (runtime_root / "sprints").mkdir()
    (runtime_root / "lib" / "graph_node_dispatcher.py").write_text("x\n", encoding="utf-8")
    (runtime_root / "tests" / "graph" / "test_graph_dispatch_submit.py").write_text("x\n", encoding="utf-8")
    (runtime_root / "tests" / "graph" / "test_parent_ready_closeout.py").write_text("x\n", encoding="utf-8")

    monkeypatch.setattr(
        "remote_dispatch_productization_closeout._run_pytest",
        lambda _runtime_root: {"returncode": 0, "stdout": "32 passed", "stderr": "", "command": "pytest ..."},
    )
    result = verify(runtime_root)
    assert result["ok"] is True
    handoff = runtime_root / "sprints" / "sprint-20260510-remote-dispatch-productization.N3-handoff.md"
    traceability = runtime_root / "sprints" / "sprint-20260510-remote-dispatch-productization.traceability.json"
    assert handoff.exists()
    assert traceability.exists()
    data = json.loads(traceability.read_text(encoding="utf-8"))
    assert "N3" in data["nodes"]
