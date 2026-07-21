#!/usr/bin/env python3
"""Shared prerequisite evaluation for Solar Harness control plane.

Single source of truth for normalize / evaluate / iter_blocked so that
workflow_guard, graph_scheduler, epic_decomposer, and solar-autopilot-monitor
all use one implementation.

Public API
----------
normalize_prerequisite(entry)            -> dict | None
evaluate_prerequisite(entry, sprints_dir) -> (bool, detail_dict)
iter_blocked(graph, sprints_dir)          -> list[detail_dict]
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_DEFAULT_SPRINTS_DIR = Path(
    os.environ.get("SPRINTS_DIR", Path.home() / ".solar" / "harness" / "sprints")
)

SUCCESS_STATUSES = {"passed", "completed", "done", "finalized"}
SUCCESS_PHASES = {"eval_passed", "passed", "completed", "done", "finalized"}
MILESTONE_REQUIREMENTS = {
    "drafting",
    "queued",
    "planning",
    "planner_plan",
    "plan_reviewed",
    "planning_complete",
    "graph_dispatch_active",
    "build_complete",
    "ready_for_review",
    "reviewing",
    "eval_passed",
}
PHASE_ORDER = [
    "queued",
    "drafting",
    "planning",
    "planner_plan",
    "plan_reviewed",
    "planning_complete",
    "graph_dispatch_active",
    "build_complete",
    "ready_for_review",
    "reviewing",
    "eval_passed",
    "completed",
    "finalized",
    "done",
    "passed",
]
PHASE_RANK = {value: idx for idx, value in enumerate(PHASE_ORDER)}


def _is_success_terminal(current_status: str, current_phase: str) -> bool:
    return current_status in SUCCESS_STATUSES or current_phase in SUCCESS_PHASES


def _phase_progress_satisfies(required: str, current_phase: str) -> bool:
    required_rank = PHASE_RANK.get(required)
    current_rank = PHASE_RANK.get(current_phase)
    if required_rank is None or current_rank is None:
        return False
    return current_rank >= required_rank


def _status_or_phase_satisfies(
    required: str, current_status: str, current_phase: str
) -> bool:
    if current_status == required or current_phase == required:
        return True
    if required == "passed":
        return _is_success_terminal(current_status, current_phase)
    if required in MILESTONE_REQUIREMENTS:
        return _is_success_terminal(current_status, current_phase) or _phase_progress_satisfies(
            required, current_phase
        )
    return False


def normalize_prerequisite(entry: Any) -> dict | None:
    """Return a canonical dict, or None if entry is empty / unparseable.

    Canonical fields (all optional except sprint_id):
      sprint_id, required_status, required_phase,
      required_node_id, required_node_status
    """
    if entry is None:
        return None
    if isinstance(entry, dict):
        sid = str(
            entry.get("sprint_id")
            or entry.get("sid")
            or entry.get("child_sprint_id")
            or ""
        ).strip()
        if not sid:
            return None
        norm: dict[str, Any] = {"sprint_id": sid}
        if entry.get("required_status"):
            norm["required_status"] = str(entry["required_status"]).strip().lower() or "passed"
        elif entry.get("status"):
            norm["required_status"] = str(entry["status"]).strip().lower() or "passed"
        elif entry.get("required"):
            norm["required_status"] = str(entry["required"]).strip().lower() or "passed"
        if entry.get("required_phase"):
            norm["required_phase"] = str(entry["required_phase"]).strip().lower()
        if entry.get("required_node_id"):
            norm["required_node_id"] = str(entry["required_node_id"]).strip()
            norm["required_node_status"] = (
                str(entry.get("required_node_status") or "passed").strip().lower() or "passed"
            )
        if not any(k in norm for k in ("required_status", "required_phase", "required_node_id")):
            norm["required_status"] = "passed"
        return norm

    entry = str(entry).strip()
    if not entry:
        return None
    if entry.startswith("external:"):
        entry = entry.removeprefix("external:").strip()
        if not entry:
            return None
    if ":" in entry:
        sid, required = entry.rsplit(":", 1)
        sid = sid.strip()
        required = required.strip().lower() or "passed"
    else:
        sid = entry
        required = "passed"
    return {"sprint_id": sid, "required_status": required} if sid else None


def _node_effective_status(graph: dict, node_id: str) -> str | None:
    node_results: dict = graph.get("node_results") or {}
    nr = node_results.get(node_id)
    if isinstance(nr, dict):
        s = str(nr.get("status") or "").lower()
        if s:
            return s
    for node in graph.get("nodes") or []:
        if str(node.get("id") or "") == node_id:
            return str(node.get("status") or "pending").lower()
    return None


def evaluate_prerequisite(
    entry: Any, sprints_dir: Path | None = None
) -> tuple[bool, dict[str, Any]]:
    """Evaluate a single prerequisite entry.

    Returns (ok, detail). detail always contains:
      requirement, sprint_id, required (legacy compat), required_status,
      required_phase, required_node_id, required_node_status,
      current_status, current_phase, current_node_status, status_path
    Plus 'reason' when ok is False.
    """
    if sprints_dir is None:
        sprints_dir = _DEFAULT_SPRINTS_DIR

    norm = normalize_prerequisite(entry)
    if norm is None:
        return False, {
            "requirement": str(entry),
            "sprint_id": "",
            "required": "passed",
            "required_status": None,
            "required_phase": None,
            "required_node_id": None,
            "required_node_status": None,
            "current_status": None,
            "current_phase": None,
            "current_node_status": None,
            "status_path": None,
            "reason": "empty_sprint_id",
        }

    sid = norm["sprint_id"]
    required_status: str | None = norm.get("required_status")
    required_phase: str | None = norm.get("required_phase")
    required_node_id: str | None = norm.get("required_node_id")
    required_node_status: str | None = norm.get("required_node_status")

    if isinstance(entry, dict):
        requirement = json.dumps(entry, ensure_ascii=False, sort_keys=True)
    else:
        requirement = str(entry).strip()

    status_path = sprints_dir / f"{sid}.status.json"

    detail: dict[str, Any] = {
        "requirement": requirement,
        "sprint_id": sid,
        # legacy 'required' field kept for backward compat with downstream callers
        "required": required_status or required_phase or "passed",
        "required_status": required_status,
        "required_phase": required_phase,
        "required_node_id": required_node_id,
        "required_node_status": required_node_status,
        "current_status": None,
        "current_phase": None,
        "current_node_status": None,
        "status_path": str(status_path),
    }

    if not sid:
        detail["reason"] = "empty_sprint_id"
        return False, detail

    if not status_path.exists():
        detail["reason"] = "missing_status"
        return False, detail

    try:
        status_data = json.loads(status_path.read_text(encoding="utf-8"))
    except Exception as exc:
        detail["reason"] = "status_corrupt"
        detail["error"] = str(exc)
        return False, detail

    current_status = str(status_data.get("status") or "").lower()
    current_phase = str(status_data.get("phase") or "").lower()
    detail["current_status"] = current_status
    detail["current_phase"] = current_phase

    failures: list[str] = []

    if required_status is not None:
        if not _status_or_phase_satisfies(required_status, current_status, current_phase):
            failures.append(
                f"required_status={required_status} "
                f"current_status={current_status} current_phase={current_phase}"
            )

    if required_phase is not None:
        if not _status_or_phase_satisfies(required_phase, current_status, current_phase):
            failures.append(
                f"required_phase={required_phase} current_phase={current_phase}"
            )

    if required_node_id is not None:
        want = required_node_status or "passed"
        graph_path = sprints_dir / f"{sid}.task_graph.json"
        if not graph_path.exists():
            detail["reason"] = "upstream_task_graph_missing"
            return False, detail
        try:
            graph_data = json.loads(graph_path.read_text(encoding="utf-8"))
        except Exception as exc:
            detail["reason"] = "upstream_task_graph_corrupt"
            detail["error"] = str(exc)
            return False, detail
        effective = _node_effective_status(graph_data, required_node_id)
        if effective is None:
            detail["reason"] = f"upstream_node_missing:{required_node_id}"
            return False, detail
        detail["current_node_status"] = effective
        node_ok = (
            effective in ("passed", "skipped") if want == "passed" else effective == want
        )
        if not node_ok:
            failures.append(
                f"required_node_id={required_node_id} "
                f"required_node_status={want} effective={effective}"
            )

    if required_status is None and required_phase is None and required_node_id is None:
        if not _status_or_phase_satisfies("passed", current_status, current_phase):
            failures.append(
                f"default_required_status=passed current_status={current_status}"
            )

    if failures:
        detail["reason"] = "status_not_satisfied"
        return False, detail

    return True, detail


def iter_blocked(
    graph: dict[str, Any], sprints_dir: Path | None = None
) -> list[dict[str, Any]]:
    """Walk graph['prerequisites'] and graph['dependency_policy']['blocks_until'].

    Returns list of failing detail dicts. Dedupes by
    (sprint_id, required_status, required_phase, required_node_id, required_node_status).
    """
    if sprints_dir is None:
        sprints_dir = _DEFAULT_SPRINTS_DIR

    entries: list[Any] = []
    for raw in graph.get("prerequisites") or []:
        if str(raw).strip():
            entries.append(raw)
    policy = graph.get("dependency_policy") or {}
    if isinstance(policy, dict):
        for raw in policy.get("blocks_until") or []:
            if str(raw).strip():
                entries.append(raw)

    blocked: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    for entry in entries:
        norm = normalize_prerequisite(entry)
        if norm is None:
            continue
        dedupe_key = (
            norm["sprint_id"],
            norm.get("required_status"),
            norm.get("required_phase"),
            norm.get("required_node_id"),
            norm.get("required_node_status"),
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        ok, detail = evaluate_prerequisite(entry, sprints_dir)
        if not ok:
            blocked.append(detail)

    return blocked
