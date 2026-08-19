"""A provider call that fails must still declare the evidence it wrote.

When a research operator fails, its result carries no `model_provider_usage`.
The adapter recovers the missing rows from each service's `invocation_journal`
-- `_merge_codex_invocation_usage` exists for exactly that, and its docstring
says so. Provider evidence files are allowed past the "operator changed
unreported files" check only through those rows.

It could never work. `default_production_resolver` hands operators
`deepcopy(services)`, so the objects an operator calls are copies with copied
journals, while the adapter reads the originals. On success the payload carries
its own usage and nothing is noticed; on failure -- the one case the merge is
for -- the recovery finds an empty list, the four service-evidence files of the
failed call go undeclared, and the node dies reporting an undeclared-files
violation instead of the provider error that actually happened.

That is what made a transient Claude failure cost two dispatches and report a
misleading cause on the second.
"""
from __future__ import annotations

import importlib.util
import sys
from copy import deepcopy
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parents[2]
REPO = HARNESS.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import harness.plugins.autosci.services.claude_research as claude_research  # noqa: E402
from harness.plugins.autosci.operators.research_synthesis.base import (  # noqa: E402
    ResearchOperatorError,
)
from harness.plugins.autosci.services.claude_research import (  # noqa: E402
    ClaudeResearchModelService,
)
from harness.plugins.autosci.services.codex_research import (  # noqa: E402
    SharedInvocationJournal,
)

ADAPTER_PATH = HARNESS / "plugins" / "autosci" / "bin" / "fixed_research_node_adapter.py"


def _adapter():
    spec = importlib.util.spec_from_file_location("_adapter_evidence", ADAPTER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _FailedProcess:
    stdout = ""
    stderr = "provider exploded"
    returncode = 1


@pytest.fixture()
def failing_service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(claude_research.shutil, "which", lambda _n: "/usr/bin/claude")
    monkeypatch.setattr(claude_research.subprocess, "run", lambda *a, **k: _FailedProcess())
    journal = SharedInvocationJournal()
    service = ClaudeResearchModelService(
        tmp_path, model="claude-haiku-4-5-20251001", role="writer",
        invocation_journal=journal,
    )
    return service, journal


def test_a_failed_call_is_recorded_before_the_error_propagates(failing_service) -> None:
    service, journal = failing_service
    with pytest.raises(ResearchOperatorError):
        service(node_id="report_revision")
    assert len(journal) == 1
    # The four files the failed call wrote, plus the schema, must be declarable.
    assert len(journal[0]["evidence_paths"]) >= 4


def test_the_journal_survives_the_resolver_deepcopy(failing_service) -> None:
    """The regression, stated as the seam rather than either side of it.

    Both halves work alone: the service records the failure, and the merge reads
    journals correctly. `deepcopy` between them is what broke it, so that is what
    is asserted here.
    """
    service, journal = failing_service
    services = {"model_generate": service}
    operator_view = deepcopy(services)  # what default_production_resolver hands the operator

    assert operator_view["model_generate"].invocation_journal is journal

    with pytest.raises(ResearchOperatorError):
        operator_view["model_generate"](node_id="report_revision")

    # The adapter reads the ORIGINAL services dict.
    assert len(services["model_generate"].invocation_journal) == 1


def test_the_adapter_recovers_usage_the_operator_failure_hid(failing_service) -> None:
    service, _journal = failing_service
    services = {"model_generate": service}
    operator_view = deepcopy(services)
    with pytest.raises(ResearchOperatorError):
        operator_view["model_generate"](node_id="report_revision")

    adapter = _adapter()
    # error_result carries no provider usage; this is that shape.
    result = {"status": "failed", "model_provider_usage": []}
    merged = adapter._merge_codex_invocation_usage(result, services)
    assert len(merged) == 1
    assert result["model_provider_usage"][0]["provider"] == "claude_subscription"
    assert result["model_provider_usage"][0]["status"] == "failed"


def test_a_plain_list_journal_would_not_survive_the_copy(tmp_path: Path,
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    """Why the journal needs its own type, asserted rather than asserted-in-prose."""
    monkeypatch.setattr(claude_research.shutil, "which", lambda _n: "/usr/bin/claude")
    monkeypatch.setattr(claude_research.subprocess, "run", lambda *a, **k: _FailedProcess())
    plain: list = []
    service = ClaudeResearchModelService(
        tmp_path, model="claude-haiku-4-5-20251001", role="writer", invocation_journal=plain,
    )
    operator_view = deepcopy({"model_generate": service})
    with pytest.raises(ResearchOperatorError):
        operator_view["model_generate"](node_id="report_revision")
    assert plain == [], "a plain list must be the broken case this fix exists for"
