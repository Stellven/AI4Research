"""Gemini Deep Research capability package.

Independent capability package implementing the O1->O6 orchestration of the
existing ``DeepResearchBrowser`` logical operator. Does NOT modify harness
PROTECTED_CORE; integrates only through documented extension points (compat/).

Layout:
- schemas/   stage handoff data models + append-only event persistence (C1)
- core/      state machine + O1-O6 controller API + event-replay (C2)
- compat/    backward-compat adapter to wake/dispatch/status (C3)
- tests/     unit tests + event-replay proof (C4)
"""

__all__ = ["schemas", "core", "compat"]
