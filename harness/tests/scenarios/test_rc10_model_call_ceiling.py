"""The adapter's call ceiling must track the operators' declared bounds.

The ceiling was `MAX_REVISION_ATTEMPTS * 2 if node_id == "report_revision" else 1`.
The moment `evidence_synthesis` grew a bounded grounding-repair loop, that
hardcoded 1 forbade it: the operator retried once, as designed, and the adapter
refused the stage with "model stage exceeded the fixed Codex call ceiling". The
stage had done exactly what it was built to do.

This is the same shape as nine other defects in this workflow -- one component
imposing a limit that another component's design necessarily breaks -- so the
ceiling is now READ from the operators rather than restated, and this test fails
if anyone restates it.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[2]
REPO = HARNESS.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from harness.plugins.autosci.operators.research_synthesis.evidence_synthesis import (  # noqa: E402
    MAX_SYNTHESIS_ATTEMPTS,
)
from harness.plugins.autosci.operators.research_synthesis.report_revision import (  # noqa: E402
    MAX_REVISION_ATTEMPTS,
)

ADAPTER_PATH = HARNESS / "plugins" / "autosci" / "bin" / "fixed_research_node_adapter.py"


def _adapter():
    spec = importlib.util.spec_from_file_location("_adapter_ceiling", ADAPTER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_evidence_synthesis_may_use_its_whole_repair_budget() -> None:
    """The regression, stated directly."""
    assert _adapter().MAX_CALLS_BY_NODE["evidence_synthesis"] == MAX_SYNTHESIS_ATTEMPTS
    assert MAX_SYNTHESIS_ATTEMPTS > 1, "a repair loop that cannot repair is not a loop"


def test_report_revision_pairs_each_attempt_with_a_review() -> None:
    assert _adapter().MAX_CALLS_BY_NODE["report_revision"] == MAX_REVISION_ATTEMPTS * 2


def test_an_undeclared_stage_still_gets_exactly_one_call() -> None:
    """The default must stay tight: only a declared loop earns extra calls."""
    ceilings = _adapter().MAX_CALLS_BY_NODE
    assert ceilings.get("report_draft") is None
    assert ceilings.get("independent_review") is None


def test_the_ceiling_is_derived_not_restated() -> None:
    """Guard against someone writing the numbers back in as literals.

    The source must reference the operators' constants, so raising an attempt
    bound in one place cannot leave the other behind.
    """
    source = ADAPTER_PATH.read_text(encoding="utf-8")
    assert "MAX_SYNTHESIS_ATTEMPTS" in source
    assert "MAX_REVISION_ATTEMPTS" in source
    assert '"evidence_synthesis": 3' not in source
    assert '"report_revision": 4' not in source
