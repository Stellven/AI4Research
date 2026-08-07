from __future__ import annotations

from pathlib import Path

import pytest
import yaml


AUDIT_ROOT = Path(__file__).resolve().parents[3]
CHECKOUT = AUDIT_ROOT / "tmp" / "codex-not-run-checkout"
WORKFLOW_DIR = CHECKOUT / ".github" / "workflows"
WORKFLOWS = ["desktop-build", "install-matrix", "solar-ci", "windows-wsl2-install"]


def load(name: str) -> dict:
    # BaseLoader avoids YAML 1.1 converting the GitHub key `on` to boolean True.
    return yaml.load((WORKFLOW_DIR / f"{name}.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def all_steps(workflow: dict) -> list[dict]:
    return [
        step
        for job in (workflow.get("jobs") or {}).values()
        for step in (job.get("steps") or [])
        if isinstance(step, dict)
    ]


@pytest.mark.parametrize("name", WORKFLOWS)
def test_ci_trigger_matrix_contract(name: str) -> None:
    workflow = load(name)
    assert workflow.get("on"), "workflow must declare at least one trigger"
    jobs = workflow.get("jobs") or {}
    assert jobs, "workflow must declare jobs"
    for job_name, job in jobs.items():
        assert job.get("runs-on"), f"{job_name} has no runner"
        assert job.get("steps") or job.get("uses"), f"{job_name} has no executable steps"
        matrix = (job.get("strategy") or {}).get("matrix")
        if matrix is not None:
            assert matrix, f"{job_name} has an empty matrix"
    if name == "desktop-build":
        assert any((job.get("strategy") or {}).get("matrix") for job in jobs.values())
    if name == "install-matrix":
        install = jobs.get("install") or {}
        assert (install.get("strategy") or {}).get("matrix", {}).get("os")
    if name == "windows-wsl2-install":
        assert any("windows" in str(job.get("runs-on", "")).lower() for job in jobs.values())


@pytest.mark.parametrize("name", ["desktop-build", "install-matrix", "solar-ci"])
def test_ci_setup_steps_are_explicit(name: str) -> None:
    steps = all_steps(load(name))
    assert any("checkout" in str(step.get("uses", "")) for step in steps)
    setup_markers = ("setup-node", "setup-python", "setup-bun", "npm ci", "bun install", "pip install")
    corpus = "\n".join(str(step) for step in steps).lower()
    assert any(marker in corpus for marker in setup_markers)


@pytest.mark.parametrize("name", WORKFLOWS)
def test_ci_job_gate_does_not_hide_failures_and_preserves_logs(name: str) -> None:
    workflow = load(name)
    jobs = workflow.get("jobs") or {}
    assert not any(str(job.get("continue-on-error", "false")).lower() == "true" for job in jobs.values())
    steps = all_steps(workflow)
    assert not any(str(step.get("continue-on-error", "false")).lower() == "true" for step in steps)
    corpus = "\n".join(str(step) for step in steps)
    assert "upload-artifact" in corpus or "GITHUB_STEP_SUMMARY" in corpus, (
        "failure contract requires an uploaded diagnostic artifact or an explicit job summary"
    )


@pytest.mark.parametrize("name", WORKFLOWS)
def test_ci_expected_artifact_or_status_summary(name: str) -> None:
    steps = all_steps(load(name))
    corpus = "\n".join(str(step) for step in steps)
    assert "upload-artifact" in corpus or "GITHUB_STEP_SUMMARY" in corpus
