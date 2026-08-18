"""Lane 1 workflow-contract tests: pinned-environment conftest.

R9 pins: HARNESS_DIR points at THIS checkout's harness tree, SPRINTS_DIR at a
throwaway temp dir, and PYTHONPATH (sys.path) at this checkout's lib — so no
test can silently import the installed ~/.solar/harness copy or write into the
repo.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

HARNESS_DIR = Path(__file__).resolve().parents[2]
LIB_DIR = HARNESS_DIR / "lib"
CONFIG_DIR = HARNESS_DIR / "config"
WORKFLOWS_DIR = CONFIG_DIR / "workflows"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
GOLDENS_DIR = Path(__file__).resolve().parent / "goldens"

_SPRINTS_DIR = Path(tempfile.mkdtemp(prefix="workflow-contract-tests-sprints-"))

os.environ["HARNESS_DIR"] = str(HARNESS_DIR)
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

import workflow_contract as wc  # noqa: E402


@pytest.fixture(autouse=True)
def _pinned_env(monkeypatch):
    """Per-test env pins (R9), reverted after each test so a full-tree pytest
    run never leaks this suite's SPRINTS_DIR into sibling suites (several lib
    modules read SPRINTS_DIR/PYTHONPATH from env at import time)."""
    monkeypatch.setenv("HARNESS_DIR", str(HARNESS_DIR))
    monkeypatch.setenv("SPRINTS_DIR", str(_SPRINTS_DIR))
    monkeypatch.setenv("PYTHONPATH", str(LIB_DIR) + os.pathsep + os.environ.get("PYTHONPATH", ""))


@pytest.fixture(scope="session")
def capsule_registry():
    registry = wc.load_capsule_registry(CONFIG_DIR)
    assert "cap.requirement-compiler-audit" in registry
    assert "cap.requirement-compiler-implementation" in registry
    return registry


@pytest.fixture(scope="session")
def operator_registry():
    registry = wc.load_operator_registry(CONFIG_DIR / "physical-operators.json")
    assert registry, "shipped physical-operators.json must not be empty"
    return registry


@pytest.fixture(scope="session")
def shipped_contracts():
    contracts = wc.load_all_contracts(WORKFLOWS_DIR)
    indexed = {contract["workflow_id"]: contract for contract in contracts}
    assert set(indexed) == {
        "code.cli_smoke",
        "code.cli_smoke_anthropic",
        "pm.generic.v1",
        "research.autosci.v1",
        "research.evidence_to_poc.v1",
        "research.deepdive.rsi_demo",
    }
    return indexed


@pytest.fixture()
def clean_trigger_env(monkeypatch):
    """Trigger tests must not inherit demo-mode env from the invoking shell."""
    monkeypatch.delenv("SOLAR_DEMO_REPORT_MODE", raising=False)
    return {}
