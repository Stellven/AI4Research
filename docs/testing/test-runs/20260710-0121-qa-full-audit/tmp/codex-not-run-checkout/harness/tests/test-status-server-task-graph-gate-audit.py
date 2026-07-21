#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "lib" / "symphony" / "status-server.py"


def load_module():
    spec = importlib.util.spec_from_file_location("solar_status_server_gate_audit_test", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {MODULE_PATH}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    mod = load_module()
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "Task Graph Gate Audit" in source
    assert "gate-audit-json" in source
    assert "gate-audit-md" in source
    assert "overview-gate-audit" in source
    assert "renderTaskGraphGateAudit" in source
    with tempfile.TemporaryDirectory(prefix="solar-status-gate-audit-") as td:
        base = Path(td)
        harness = base / "harness"
        sprints = harness / "sprints"
        reports = harness / "reports"
        sid = "sprint-test-gate-audit"

        write(
            sprints / f"{sid}.status.json",
            json.dumps(
                {
                    "sprint_id": sid,
                    "status": "active",
                    "phase": "reviewing",
                    "title": "Gate Audit Status Test",
                }
            ),
        )
        write(
            reports / "task-graph-gate-backfill-audit-20990101T000000Z.json",
            json.dumps(
                {
                    "generated_at": "2099-01-01T00:00:00Z",
                    "graphs_changed": 51,
                    "graphs_unresolved": 4,
                    "markdown_report": str(reports / "task-graph-gate-backfill-audit-20990101T000000Z.md"),
                }
            ),
        )
        write(
            reports / "task-graph-gate-backfill-audit-20990101T000000Z.md",
            "# report\n",
        )

        mod.HARNESS_DIR = harness
        mod.SPRINTS_DIR = sprints
        mod.REPORTS_DIR = reports

        current = mod._current_sprint()
        audit = current["task_graph_gate_audit"]
        assert audit["present"] is True
        assert audit["status"] == "warn"
        assert audit["graphs_changed"] == 51
        assert audit["graphs_unresolved"] == 4
        assert audit["summary"] == "51 changed / 4 unresolved"

        payload = mod._status_payload(limit=5, sprint_id=sid)
        assert payload["task_graph_gate_audit"]["present"] is True
        assert payload["current_sprint"]["task_graph_gate_audit"]["graphs_unresolved"] == 4

    print("PASS status-server task-graph gate audit summary")


if __name__ == "__main__":
    main()
