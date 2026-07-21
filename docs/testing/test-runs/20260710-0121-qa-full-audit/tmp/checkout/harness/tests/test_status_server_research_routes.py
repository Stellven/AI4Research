from __future__ import annotations

import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "status-server" / "research_routes.py"
SPEC = importlib.util.spec_from_file_location("solar_research_routes_test", str(MODULE_PATH))
assert SPEC and SPEC.loader
research_routes = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(research_routes)


def test_discover_eval_files_finds_reports_projection(tmp_path, monkeypatch):
    sprints_dir = tmp_path / "sprints"
    reports_dir = tmp_path / "reports"
    sprints_dir.mkdir()
    reports_dir.mkdir()
    monkeypatch.setattr(research_routes, "REPORTS_DIR", reports_dir)

    sid = "deepdive-cais2026-demo"
    report_dir = reports_dir / sid
    report_dir.mkdir()
    eval_path = report_dir / f"{sid}-research_eval.json"
    eval_path.write_text(json.dumps({"run_id": sid}), encoding="utf-8")

    files = research_routes.discover_eval_files(sprints_dir, sid)

    assert files == [eval_path]
