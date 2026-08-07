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


def test_product_autosci_research_scheduler_writes_scientific_lifecycle(tmp_path: Path) -> None:
    harness_dir = prepare_isolated_harness(tmp_path)
    paper = write_demo_paper(harness_dir)
    run_id = unique_run_id("phase-c-research")

    proc = run_autosci(
        harness_dir,
        f"$research phase-c scheduler --paper {paper} --scheduler-run --scheduler-timeout 20 --run-id {run_id}",
    )
    summary = load_stdout_json(proc)

    assert summary["skill"] == "research"
    assert summary["scheduler_dispatch_boundary_status"] == "generic_workflow_runner"
    assert summary["scheduler_lifecycle_status"] == "passed"
    lifecycle_path = assert_under(summary["scheduler_lifecycle_summary_path"], harness_dir)
    lifecycle = json.loads(lifecycle_path.read_text(encoding="utf-8"))
    assert lifecycle["schema"] == "scientific_lifecycle.v1"
    assert lifecycle["lifecycle_status"] == "passed"
    assert "paper_ingest" in lifecycle["node_results"]
    assert not repo_run_dir(run_id).exists()
