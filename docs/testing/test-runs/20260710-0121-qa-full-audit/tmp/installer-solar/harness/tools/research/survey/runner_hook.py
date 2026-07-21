"""Attach-style hook for survey-continue runner integration.

Provides ``attach_to_survey_continue`` which registers gate-execution
callbacks on a runner object **without modifying the runner source**.

The runner is expected to support an ``add_hook(event, callback)`` interface.
If it does not, the function degrades gracefully and returns a no-op handle.
"""

from __future__ import annotations

from typing import Any, Callable


_HOOKS_ATTR = "_survey_gate_hooks"


def attach_to_survey_continue(runner: Any) -> dict[str, Any]:
    """Attach gate report generation to a survey-continue runner.

    Parameters
    ----------
    runner:
        Any object with an ``add_hook(event_name, callback)`` method.  If the
        method does not exist, returns a report describing the degradation.

    Returns
    -------
    dict
        Attachment result with keys ``attached`` (bool), ``hooks`` (list of
        event names), and optionally ``reason`` (if degraded).
    """
    hooks_registered: list[str] = []

    add_hook: Callable[..., Any] | None = getattr(runner, "add_hook", None)
    if not callable(add_hook):
        return {
            "attached": False,
            "hooks": [],
            "reason": "runner_has_no_add_hook",
        }

    def _on_section_compiled(data: dict[str, Any]) -> None:
        pass  # placeholder — actual gate invocation wired by S04/S05

    add_hook("section_compiled", _on_section_compiled)
    hooks_registered.append("section_compiled")

    existing = getattr(runner, _HOOKS_ATTR, [])
    existing.extend(hooks_registered)
    setattr(runner, _HOOKS_ATTR, existing)

    return {"attached": True, "hooks": hooks_registered}
