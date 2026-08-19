"""The recorded provider must be the provider that was actually selected.

A live Haiku run failed four times at ``evidence_synthesis``. Each retry made a
real, successful Claude call and wrote a good artifact; each was then rejected
by the adapter with "model stage used a non-Codex provider". The service was
fine and the guard was fine. The seam between them was not: the Claude service
overrode ``__call__`` without the three lines its Codex parent uses to stamp
provenance onto the returned payload, so ``provider_usage_from`` fell back to a
synthesised row labelled ``injected``.

That fallback is why this test exists at the seam rather than on either side of
it. A service that reports no provenance does not fail loudly -- it reports
plausible-looking provenance for a call that recorded none, and the two are
indistinguishable to anything that only checks a run went green.

So the assertions here are deliberately paired: the guard must accept a real
Claude invocation under a Claude selection, and must reject that same
invocation under a Codex selection. A test that only asserted the first would
pass just as well on a build where the guard had been deleted.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

HARNESS = Path(__file__).resolve().parents[2]
REPO = HARNESS.parent

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from harness.plugins.autosci.operators.research_synthesis.base import (  # noqa: E402
    provider_usage_from,
)
from harness.plugins.autosci.services.claude_research import (  # noqa: E402
    CLAUDE_USAGE_PROVIDER,
    ClaudeResearchModelService,
)
from harness.plugins.autosci.services.codex_research import (  # noqa: E402
    CodexResearchModelService,
)

ADAPTER_PATH = HARNESS / "plugins" / "autosci" / "bin" / "fixed_research_node_adapter.py"


def _adapter():
    """Load the adapter as the bare module it is dispatched as.

    It is not importable as ``harness.plugins.autosci.bin.fixed_research_node_adapter``
    from a normal test run: it configures its own ``sys.path`` at import time.
    Loading it by location is what the dispatcher effectively does, so a defect
    that only appears under that entry path is still in scope here -- which is
    the class of defect this whole file is about.
    """
    spec = importlib.util.spec_from_file_location("_fixed_research_node_adapter", ADAPTER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _FakeCompleted:
    def __init__(self, stdout: str) -> None:
        self.stdout = stdout
        self.stderr = ""
        self.returncode = 0


@pytest.fixture()
def claude_usage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """The usage an operator would read after one real Claude invocation.

    The CLI is faked, not the service: everything between the process boundary
    and the operator -- schema handling, invocation recording, payload stamping
    -- is the code under test.
    """
    import harness.plugins.autosci.services.claude_research as claude_research

    node_id = "evidence_synthesis"
    body = json.dumps({"node_id": node_id, "limitations": [], "claims": []})

    monkeypatch.setattr(claude_research.shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.setattr(
        claude_research.subprocess,
        "run",
        lambda *a, **k: _FakeCompleted(json.dumps({"result": body})),
    )

    service = ClaudeResearchModelService(tmp_path, model="claude-haiku-4-5-20251001", role="writer")
    payload = service(node_id=node_id)
    return provider_usage_from(payload, usage_kind="llm")


def test_claude_service_reports_its_own_provider_not_the_inherited_one(
    claude_usage: list[dict[str, Any]],
) -> None:
    assert claude_usage, "the Claude service reported no provenance at all"
    providers = {str(item.get("provider") or "") for item in claude_usage}
    assert providers == {CLAUDE_USAGE_PROVIDER}
    # The exact failure that shipped: an unstamped payload reads as "injected",
    # and a payload stamped by the inherited literal reads as Codex. Both are
    # wrong, and only one of them is loud.
    assert "injected" not in providers
    assert "codex_subscription" not in providers


def test_codex_and_claude_services_do_not_share_a_provenance_label() -> None:
    assert CodexResearchModelService.usage_provider == "codex_subscription"
    assert ClaudeResearchModelService.usage_provider == "claude_subscription"
    assert CodexResearchModelService.usage_provider != ClaudeResearchModelService.usage_provider


def test_guard_accepts_a_claude_run_under_a_claude_selection(
    claude_usage: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = _adapter()
    monkeypatch.setenv("SOLAR_RESEARCH_MODEL_PROVIDER", "claude")
    adapter._verify_model_usage(
        node_id="evidence_synthesis",
        result={"model_provider_usage": claude_usage},
    )


def test_guard_rejects_a_claude_run_under_a_codex_selection(
    claude_usage: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Widening the guard must not have emptied it.

    This is the assertion that fails if someone "fixes" a future provider by
    relabelling it, or by dropping the provider check entirely.
    """
    adapter = _adapter()
    monkeypatch.setenv("SOLAR_RESEARCH_MODEL_PROVIDER", "codex")
    with pytest.raises(adapter.AdapterError) as excinfo:
        adapter._verify_model_usage(
            node_id="evidence_synthesis",
            result={"model_provider_usage": claude_usage},
        )
    message = str(excinfo.value)
    # The old message named only the expectation, which is what sent the
    # investigation after the CLI instead of the seam. Both sides must appear.
    assert "codex_subscription" in message
    assert "claude_subscription" in message


def test_guard_rejects_a_stage_that_reported_no_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pre-fix behaviour, asserted as a regression.

    ``provider_usage_from`` turns a payload with no provenance keys into a row
    labelled "injected" rather than raising. Until that fallback is removed, the
    guard is the only thing standing between an unattested call and a green run.
    """
    adapter = _adapter()
    monkeypatch.setenv("SOLAR_RESEARCH_MODEL_PROVIDER", "claude")
    unstamped = provider_usage_from({"node_id": "evidence_synthesis"}, usage_kind="llm")
    assert {str(item.get("provider") or "") for item in unstamped} == {"injected"}
    with pytest.raises(adapter.AdapterError):
        adapter._verify_model_usage(
            node_id="evidence_synthesis",
            result={"model_provider_usage": unstamped},
        )


def test_unknown_provider_selection_stops_the_run(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter()
    monkeypatch.setenv("SOLAR_RESEARCH_MODEL_PROVIDER", "gemini")
    with pytest.raises(adapter.AdapterError):
        adapter._expected_usage_provider()


def test_codex_return_path_still_stamps_its_own_provider(tmp_path: Path) -> None:
    """The shared helper must not have changed what a Codex run reports.

    The Codex ``__call__`` had three literal assignments replaced by one call to
    ``_attach_provider_usage``. Faking that CLI end to end is heavy, so this
    covers the specific regression risk of that edit: the return path still
    stamps codex_subscription, and an operator reading the payload still sees it.
    """
    service = CodexResearchModelService(tmp_path, model="gpt-5.5", role="writer")
    usage_row = {"invocation_id": "i1", "provider": service.usage_provider}
    payload = service._attach_provider_usage({"node_id": "report_draft"}, usage_row)
    assert payload["provider"] == "codex_subscription"
    assert payload["model"] == "gpt-5.5"
    assert payload["provider_usage"] == [usage_row]
    # The row's own provider field is written by _record_invocation, not by the
    # helper; that path is covered end to end by the Claude fixture above, which
    # is the one that proves the attribute rather than a literal is used.
