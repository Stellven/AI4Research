from __future__ import annotations

from pathlib import Path

from .autosci_product_smoke_helpers import load_stdout_json, prepare_isolated_harness, run_autosci


def test_product_autosci_routes_list(tmp_path: Path) -> None:
    harness_dir = prepare_isolated_harness(tmp_path)

    proc = run_autosci(harness_dir, "$skills")
    payload = load_stdout_json(proc)

    assert payload["ok"] is True
    assert payload["count"] == 28
    skills = {item["skill"]: item for item in payload["skills"]}
    assert {"ingest", "review", "research", "paper-draft", "exp-run"} <= set(skills)
    assert skills["exp-run"]["side_effect_policy"] == "approval_required"
    assert any(item["coverage_status"] != "full" for item in payload["skills"])
