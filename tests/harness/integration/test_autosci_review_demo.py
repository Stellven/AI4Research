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
)


def test_product_autosci_review_writes_artifact_review_evidence(tmp_path: Path) -> None:
    harness_dir = prepare_isolated_harness(tmp_path)
    wiki_root = harness_dir / "artifacts" / "autosci" / "workspace" / "wiki"
    target = wiki_root / "outputs" / "phase-c-review-target.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "# Phase C Review Target\n\n"
        "The method section names a dataset, metric, baseline, evidence artifact, and limitation.\n",
        encoding="utf-8",
    )
    run_id = unique_run_id("phase-c-review")

    proc = run_autosci(harness_dir, f"$review {target} --focus method --run-id {run_id}")
    summary = load_stdout_json(proc)

    assert summary["skill"] == "review"
    assert summary["execution_status"] == "partial"
    evidence_path = assert_under(summary["evidence_path"], harness_dir)
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    actions = payload["outputs"]["skill_run"]["actions"]
    assert [action["action"] for action in actions] == ["review_artifact"]

    review_path = assert_under(actions[0]["evidence_path"], harness_dir)
    review = json.loads(review_path.read_text(encoding="utf-8"))
    assert review["schema"] == "artifact_review.v1"
    assert review["outputs"]["review"]["review_available"] is False
    assert review["outputs"]["review"]["review_mode"] == "local_surrogate"
    assert not repo_run_dir(run_id).exists()
