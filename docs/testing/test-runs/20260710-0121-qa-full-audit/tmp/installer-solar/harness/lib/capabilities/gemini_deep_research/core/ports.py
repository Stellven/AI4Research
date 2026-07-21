"""Operator port (hexagonal boundary).

Core depends on this abstract port; the real binding to the existing
``DeepResearchBrowser`` logical operator is wired in compat/ (C3). Tests (C4)
supply a fake. This keeps the controller's call-chain real while honoring A1:
"Controller does not click/type, it delegates to the operator".
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..schemas.models import DRPlan, DRResult, DRRunHandle, OptimizedPrompt, ResearchRequest


@runtime_checkable
class BrowserOperatorPort(Protocol):
    def optimize_prompt(self, req: ResearchRequest, template_id: str) -> OptimizedPrompt:
        """O2: produce optimized prompt via a fresh DeepResearchBrowser chat."""
        ...

    def submit(self, prompt: OptimizedPrompt) -> DRPlan:
        """O3: submit in Deep Research mode, return planning handle."""
        ...

    def confirm(self, plan: DRPlan) -> DRRunHandle:
        """O4: click 'start research', planning -> running."""
        ...

    def poll(self, handle: DRRunHandle) -> DRRunHandle:
        """O5: refresh async_state."""
        ...

    def collect(self, handle: DRRunHandle) -> DRResult:
        """O5 terminal: extract report + classified references + evidence refs."""
        ...
