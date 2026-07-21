"""Backward-compat adapters for Gemini Deep Research browser execution.

The capability package is Gemini-specific, but it runs through the generic
``browser_job_runtime`` substrate.  Keep ``DeepResearchBrowserAdapter`` for
older callers, and expose ``DeepResearchGeminiAdapter`` so the logical operator
binding can be proven without relying on comments/config convention.

Does NOT modify PROTECTED_CORE. Integrates only through public functions of
the existing operator runtime (submit/poll/collect_browser_job). Real Gemini
web consumption is gated behind a human-authorization switch (default OFF):
set GEMINI_DR_REAL_CALLS=1 to use the real browser; otherwise a mock job
sequence drives the state machine so wiring can be proven without spending
real Deep Research quota (S02 A4 / NB1 / NB2).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from ..core.ports import BrowserOperatorPort  # noqa: F401  (documents the contract)
from ..schemas.models import (
    AsyncState,
    DRPlan,
    DRResult,
    DRRunHandle,
    OptimizedPrompt,
    Reference,
    ResearchRequest,
    ResultStatus,
)

# 李教授 prompt template (O2). Embeds the mandatory classified-reference
# directive so OptimizedPrompt.has_reference_directive is structurally true.
LI_PROFESSOR_TEMPLATE_ID = "li-professor-v1"
_REFERENCE_DIRECTIVE = (
    "Organize all cited sources by category (papers / news / blogs / docs), "
    "and for every source provide its title and a working URL."
)

_GEMINI_URL = "https://gemini.google.com/app"


def _harness_lib_dir() -> Path:
    # .../lib/capabilities/gemini_deep_research/compat/operator_adapter.py
    return Path(__file__).resolve().parents[3]


def _import_runtime() -> Any:
    lib_dir = str(_harness_lib_dir())
    if lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)
    import browser_job_runtime  # type: ignore

    return browser_job_runtime


def _real_calls_enabled() -> bool:
    return os.environ.get("GEMINI_DR_REAL_CALLS", "0").strip() == "1"


_STATE_MAP = {
    "submitted": AsyncState.SUBMITTED,
    "planning": AsyncState.PLANNING,
    "running": AsyncState.RUNNING,
    "reauth_required": AsyncState.REAUTH_REQUIRED,
    "waiting_human": AsyncState.WAITING_HUMAN,
    "done": AsyncState.DONE,
    "failed": AsyncState.FAILED,
    "timeout": AsyncState.TIMEOUT,
}


def _map_state(raw: dict[str, Any]) -> AsyncState:
    if str(raw.get("projected_state", "")).upper() == "WAITING_HUMAN":
        return AsyncState.WAITING_HUMAN
    return _STATE_MAP.get(str(raw.get("state", "")).lower(), AsyncState.RUNNING)


class DeepResearchBrowserAdapter:
    """Concrete BrowserOperatorPort over the existing operator runtime."""

    def __init__(
        self,
        actor_id: str = "gemini_deep_research",
        mock_sequence: list[str] | None = None,
        logical_operator: str = "DeepResearchBrowser",
        ingress_channel: str = "gemini_deep_research",
        artifact_kind: str = "gemini_deep_research",
    ) -> None:
        self.actor_id = actor_id
        self.logical_operator = logical_operator
        self.ingress_channel = ingress_channel
        self.artifact_kind = artifact_kind
        # default safe mock trajectory; ignored when real calls are enabled
        self.mock_sequence = mock_sequence or ["planning", "running", "done"]
        self._rt = _import_runtime()
        self._jobs: dict[str, str] = {}  # run_ref -> started_at iso

    # ---- O2 ------------------------------------------------------------
    def optimize_prompt(self, req: ResearchRequest, template_id: str) -> OptimizedPrompt:
        prompt_text = (
            f"[{template_id}] Act as a senior research professor.\n"
            f"Research question: {req.question}\n"
            f"{_REFERENCE_DIRECTIVE}"
        )
        return OptimizedPrompt(
            request_id=req.request_id,
            prompt_text=prompt_text,
            chat_session_ref=f"chat-{req.request_id}",
            has_reference_directive=True,
            optimizer_template_id=template_id,
        )

    def _build_envelope(self, prompt: OptimizedPrompt) -> dict[str, Any]:
        return {
            "task_type": "RESEARCH",
            "logical_operator": self.logical_operator,
            "objective": (
                "Run Gemini Deep Research for the optimized research prompt and "
                "return a classified, sourced research report."
            ),
            "url": _GEMINI_URL,
            "target_url": _GEMINI_URL,
            "allowed_domains": ["gemini.google.com"],
            "ingress_channel": self.ingress_channel,
            "raw_request": prompt.prompt_text,
            "artifact_kind": self.artifact_kind,
            "capture_policy": {"mode": "whole_conversation", "messages_required": True},
        }

    # ---- O3 ------------------------------------------------------------
    def submit(self, prompt: OptimizedPrompt) -> DRPlan:
        envelope = self._build_envelope(prompt)
        mock = None if _real_calls_enabled() else self.mock_sequence
        job_id = self._rt.submit_browser_job(self.actor_id, envelope, mock_sequence=mock)
        return DRPlan(run_ref=job_id, plan_detected=True, confirm_control_ref="gemini-start-research")

    # ---- O4 ------------------------------------------------------------
    def confirm(self, plan: DRPlan) -> DRRunHandle:
        raw = self._rt.poll_browser_job(plan.run_ref)
        return DRRunHandle(
            run_ref=plan.run_ref,
            async_state=_map_state(raw),
            confirmed=True,
            started_at=str(raw.get("created_at") or raw.get("updated_at") or ""),
            attempt=1,
        )

    # ---- O5 poll -------------------------------------------------------
    def poll(self, handle: DRRunHandle) -> DRRunHandle:
        raw = self._rt.poll_browser_job(handle.run_ref)
        return DRRunHandle(
            run_ref=handle.run_ref,
            async_state=_map_state(raw),
            confirmed=handle.confirmed,
            started_at=handle.started_at,
            attempt=handle.attempt,
            next_poll_at=handle.next_poll_at,
        )

    # ---- O5 collect ----------------------------------------------------
    def collect(self, handle: DRRunHandle) -> DRResult:
        raw = self._rt.collect_browser_job(handle.run_ref)
        evidence_refs = [
            str(a.get("name"))
            for a in raw.get("artifacts", [])
            if isinstance(a, dict) and a.get("name")
        ]
        report_text, references = self._extract_report(raw)
        if handle.async_state == AsyncState.DONE and report_text and references:
            return DRResult(
                run_ref=handle.run_ref,
                status=ResultStatus.SUCCEEDED,
                report_text=report_text,
                references=references,
                evidence_refs=evidence_refs,
            )
        # Honest boundary: without real DR output we do not fabricate references.
        reason = (
            "real_calls_disabled_no_research_output"
            if not _real_calls_enabled()
            else f"no_structured_result(state={handle.async_state.value})"
        )
        return DRResult(
            run_ref=handle.run_ref,
            status=ResultStatus.FAILED,
            evidence_refs=evidence_refs,
            failure_reason=reason,
        )

    @staticmethod
    def _extract_report(raw: dict[str, Any]) -> tuple[str | None, list[Reference]]:
        result = raw.get("result") if isinstance(raw.get("result"), dict) else raw
        report_text = result.get("report_text") or result.get("summary")
        refs: list[Reference] = []
        for r in result.get("references", []) or []:
            if isinstance(r, dict) and r.get("category") and r.get("title") and r.get("url"):
                refs.append(Reference(category=r["category"], title=r["title"], url=r["url"]))
        return report_text, refs


class DeepResearchGeminiAdapter(DeepResearchBrowserAdapter):
    """Gemini-specific adapter bound to the DeepResearchGemini logical operator."""

    def __init__(
        self,
        actor_id: str = "gemini_deep_research",
        mock_sequence: list[str] | None = None,
    ) -> None:
        super().__init__(
            actor_id=actor_id,
            mock_sequence=mock_sequence,
            logical_operator="DeepResearchGemini",
            ingress_channel="gemini_deep_research",
            artifact_kind="gemini_deep_research",
        )
