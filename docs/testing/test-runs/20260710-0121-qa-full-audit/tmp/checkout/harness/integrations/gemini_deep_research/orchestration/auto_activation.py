"""U1 — auto-activation + role routing for Gemini Deep Research DAG nodes.

Two concerns, both additive (no PROTECTED_CORE edits):

1. DAG auto-activation: which graph nodes are ready to dispatch right now,
   computed from the existing graph scheduler readiness (read-only).
2. Role routing: which harness role (planner / builder_main / evaluator /
   human) should handle the next step — for sprint-level nodes via the existing
   ``workflow_guard.route``; for an in-flight DR run via its controller state.

The autopilot integrates by importing ``decide_run_role`` / ``ready_nodes``;
it does not require modifying the autopilot or scheduler source.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# core capability package lives under lib/capabilities
_HARNESS_DIR = Path(__file__).resolve().parents[3]
_LIB = _HARNESS_DIR / "lib"
_CAP = _LIB / "capabilities"
for _p in (str(_LIB), str(_CAP)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from gemini_deep_research.core.state_machine import ControllerState  # noqa: E402

# Harness role vocabulary (mirror of workflow_guard.route outputs).
ROLE_PLANNER = "planner"
ROLE_BUILDER = "builder_main"
ROLE_EVALUATOR = "evaluator"
ROLE_HUMAN = "human"


@dataclass(frozen=True)
class ActivationDecision:
    ready: bool
    role: str | None
    reason: str


# DR-run lifecycle -> next responsible role.
_RUN_ROLE_MAP: dict[ControllerState, tuple[str, str]] = {
    ControllerState.INPUT: (ROLE_BUILDER, "intake_and_optimize"),
    ControllerState.OPTIMIZE: (ROLE_BUILDER, "optimizing_prompt"),
    ControllerState.SUBMIT: (ROLE_BUILDER, "submitting_to_operator"),
    ControllerState.CONFIRM: (ROLE_BUILDER, "confirming_plan"),
    ControllerState.MONITOR: (ROLE_BUILDER, "monitoring_run"),
    ControllerState.RETRY: (ROLE_BUILDER, "retry_pending"),
    ControllerState.DONE: (ROLE_EVALUATOR, "verify_activation_proof"),
    ControllerState.FAIL: (ROLE_EVALUATOR, "review_failure"),
}


def decide_run_role(state: ControllerState, blocker: str | None = None) -> ActivationDecision:
    """Route an in-flight DR run to the next harness role.

    A waiting_human/reauth blocker overrides the lifecycle mapping: the run is
    not auto-ready; a human must act (NB1/NB2).
    """
    if blocker and blocker.startswith("waiting_human"):
        return ActivationDecision(ready=False, role=ROLE_HUMAN, reason=blocker)
    role, reason = _RUN_ROLE_MAP[state]
    # terminal controller states are "ready" for the evaluator to act;
    # in-flight states are ready for the builder to continue.
    return ActivationDecision(ready=True, role=role, reason=reason)


def _import_graph_scheduler() -> Any:
    if str(_LIB) not in sys.path:
        sys.path.insert(0, str(_LIB))
    import graph_scheduler  # type: ignore

    return graph_scheduler


def ready_nodes(graph_path: str | Path) -> list[str]:
    """Return graph node ids that are ready to dispatch (deps satisfied, open).

    Read-only: derived from the task_graph; does not mutate scheduler state.
    """
    import json

    data = json.loads(Path(graph_path).read_text(encoding="utf-8"))
    nodes = data.get("nodes", [])
    status_by_id = {}
    for n in nodes:
        nr = data.get("node_results", {}).get(n["id"], {})
        status_by_id[n["id"]] = nr.get("status", n.get("status", "pending"))
    done_states = {"reviewing", "passed", "done", "completed"}
    ready: list[str] = []
    for n in nodes:
        nid = n["id"]
        if status_by_id.get(nid) in done_states:
            continue
        deps = n.get("depends_on", [])
        if all(status_by_id.get(d) in done_states for d in deps):
            ready.append(nid)
    return ready


def route_sprint(sid: str) -> dict[str, Any]:
    """Delegate sprint-level role routing to the existing workflow_guard.

    Pure pass-through to the harness extension point; no behavior change.
    """
    if str(_LIB) not in sys.path:
        sys.path.insert(0, str(_LIB))
    import workflow_guard  # type: ignore

    return workflow_guard.route(sid)
