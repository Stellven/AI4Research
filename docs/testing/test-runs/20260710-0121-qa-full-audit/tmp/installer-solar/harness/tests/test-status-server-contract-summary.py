#!/usr/bin/env python3
"""Regression tests for final contract summary exposure in status-server."""

import importlib.util
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / "lib" / "symphony" / "status-server.py"
spec = importlib.util.spec_from_file_location("status_server", MODULE)
status_server = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(status_server)


def test_final_contract_summary_status_prefers_docs_copy():
    data = status_server._final_contract_summary_status()
    assert data["status"] == "ok"
    assert data["route"] == "/contract-summary"
    assert data["source"] in {"docs", "sprint-artifact"}
    assert "PM -> Planner -> Headless Pool DAG Flow" in data["title"]


def test_final_contract_summary_html_contains_back_link_and_title():
    html = status_server._final_contract_summary_html()
    assert "Final Contract Summary" in html
    assert "/contract-summary" not in html  # self route should render content, not depend on nested fetch
    assert "Back to 8765 Status" in html
