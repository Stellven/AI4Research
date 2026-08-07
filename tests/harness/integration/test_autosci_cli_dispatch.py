from __future__ import annotations

from pathlib import Path

from .autosci_product_smoke_helpers import prepare_isolated_harness, run_autosci


def test_product_autosci_review_help_reaches_shim(tmp_path: Path) -> None:
    harness_dir = prepare_isolated_harness(tmp_path)

    proc = run_autosci(harness_dir, "$review --help")

    assert "usage: autosci_skill_shim.py skill" in proc.stdout
    assert "--review-llm-evidence" in proc.stdout
    assert "--run-id" in proc.stdout
    assert not (harness_dir / "artifacts" / "autosci" / "runs").exists()
