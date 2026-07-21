"""Gemini Deep Research integration layer (S04).

Wires the core capability package (lib/capabilities/gemini_deep_research) into
the harness autopilot/DAG, status UI, and runtime-evidence surfaces. Additive
integration only — never modifies PROTECTED_CORE; reuses existing extension
points (workflow_guard role routing, graph scheduler readiness, event log).

Layout:
- orchestration/  auto-activation + role routing (U1)
- ui/             status surfacing of epic/child tree + blockers (U2)
- evidence/       structured runtime completion evidence (U3)
"""

__all__ = ["orchestration", "ui", "evidence"]
