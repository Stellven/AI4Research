from __future__ import annotations

import json
from pathlib import Path

from .autosci_product_smoke_helpers import (
    assert_under,
    load_stdout_json,
    prepare_isolated_harness,
    repo_run_dir,
    run_autosci,
    unique_run_id,
    write_demo_paper,
)


def test_product_autosci_ingest_writes_research_paper_evidence(tmp_path: Path) -> None:
    harness_dir = prepare_isolated_harness(tmp_path)
    paper = write_demo_paper(harness_dir)
    run_id = unique_run_id("phase-c-ingest")

    proc = run_autosci(harness_dir, f"$ingest --paper {paper} --run-id {run_id}")
    summary = load_stdout_json(proc)

    assert summary["skill"] == "ingest"
    assert summary["execution_status"] in {"completed", "partial"}
    evidence_path = assert_under(summary["evidence_path"], harness_dir)
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    actions = payload["outputs"]["skill_run"]["actions"]
    assert "ingest_paper" in {action["action"] for action in actions}

    ingest_action = next(action for action in actions if action["action"] == "ingest_paper")
    research_paper_path = assert_under(ingest_action["evidence_path"], harness_dir)
    research_paper = json.loads(research_paper_path.read_text(encoding="utf-8"))
    assert research_paper["schema"] == "research_paper.v1"
    assert research_paper["status"] == "completed"
    assert not repo_run_dir(run_id).exists()
