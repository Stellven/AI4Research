from __future__ import annotations

from pathlib import Path


HARNESS = Path(__file__).resolve().parents[3]


def test_manifest_declares_phase12_experiment_lifecycle_capabilities() -> None:
    manifest = (HARNESS / "plugins" / "autosci" / "manifest.yaml").read_text(encoding="utf-8")
    for capability in [
        "cap.research-experiment-design",
        "cap.research-experiment-run",
        "cap.research-experiment-monitor",
    ]:
        assert capability in manifest


def test_manifest_declares_phase13_claim_verification_capability() -> None:
    manifest = (HARNESS / "plugins" / "autosci" / "manifest.yaml").read_text(encoding="utf-8")
    assert "cap.research-claim-verify" in manifest


def test_manifest_declares_phase14_report_publication_capabilities() -> None:
    manifest = (HARNESS / "plugins" / "autosci" / "manifest.yaml").read_text(encoding="utf-8")
    for capability in [
        "cap.research-report-plan",
        "cap.research-report-draft",
        "cap.research-publication-produce",
    ]:
        assert capability in manifest


def test_manifest_declares_phase16_workflow_evolution_capability() -> None:
    manifest = (HARNESS / "plugins" / "autosci" / "manifest.yaml").read_text(encoding="utf-8")
    assert "cap.research-workflow-evolve" in manifest
