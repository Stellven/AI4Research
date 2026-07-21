#!/usr/bin/env python3
"""PM -> Planner -> task_graph workflow guard.

This module is intentionally read-only.  It answers one question for wake and
coordinator entrypoints: which role is allowed to receive a sprint next?

Default lifecycle:
  PM writes PRD -> Planner writes design/plan/task_graph -> DAG builders run.
Legacy metadata such as bypass_pm or handoff_to=builder is treated as a
violation unless the sprint already has planner artifacts.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from prerequisite_resolver import iter_blocked
try:
    from task_graph_io import spec_valid as _tgio_spec_valid, triface_parent_ready as _tgio_parent_ready
except Exception:  # pragma: no cover - fail-open if module not yet available
    _tgio_spec_valid = None  # type: ignore
    _tgio_parent_ready = None  # type: ignore
del _sys, _os


HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", Path.home() / ".solar" / "harness"))
SPRINTS_DIR = Path(os.environ.get("SPRINTS_DIR", HARNESS_DIR / "sprints"))


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _nonempty(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _artifact_path(sid: str, suffix: str, *, node_level: bool = True) -> Path:
    direct = SPRINTS_DIR / f"{sid}.{suffix}"
    if _nonempty(direct):
        return direct
    if not node_level:
        return direct
    matches = sorted(
        SPRINTS_DIR.glob(f"{sid}.*-{suffix}"),
        key=lambda path: path.stat().st_mtime if path.exists() else 0,
        reverse=True,
    )
    for candidate in matches:
        if _nonempty(candidate):
            return candidate
    return direct


def _graph_valid(path: Path) -> tuple[bool, str]:
    if not _nonempty(path):
        return False, "missing"
    try:
        graph = json.loads(path.read_text())
    except Exception as exc:
        return False, f"parse_error:{exc}"
    nodes = graph.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return False, "nodes_missing"
    seen: set[str] = set()
    for idx, node in enumerate(nodes):
        if not isinstance(node, dict):
            return False, f"node_{idx}_not_object"
        node_id = str(node.get("id") or "").strip()
        if not node_id:
            return False, f"node_{idx}_missing_id"
        if node_id in seen:
            return False, f"duplicate_node:{node_id}"
        seen.add(node_id)
        if not str(node.get("goal") or "").strip():
            return False, f"node_{node_id}_missing_goal"
        depends_on = node.get("depends_on", [])
        if depends_on is None or not isinstance(depends_on, list):
            return False, f"node_{node_id}_invalid_depends_on"
    return True, "ok"


def _graph_parent_ready(path: Path) -> bool:
    if not _nonempty(path):
        return False
    try:
        graph = json.loads(path.read_text())
    except Exception:
        return False
    nodes = [n for n in graph.get("nodes", []) if isinstance(n, dict)]
    if not nodes:
        return False
    statuses = {str(n.get("status") or "").lower() for n in nodes}
    if any(st in {"failed", "error"} for st in statuses):
        return False
    if any(st not in {"passed", "skipped"} for st in statuses):
        return False
    required = set(str(x) for x in graph.get("required_gates", []) or [] if str(x))
    if not required:
        return True
    results = graph.get("node_results") if isinstance(graph.get("node_results"), dict) else {}
    passed_gates = set()
    for node in nodes:
        node_id = str(node.get("id") or "")
        gate = str(node.get("gate") or "")
        result = results.get(node_id) if isinstance(results, dict) else None
        result_status = str((result or {}).get("status") or node.get("status") or "").lower()
        if gate and result_status in {"passed", "skipped"}:
            passed_gates.add(gate)
    return required.issubset(passed_gates)


def _triface_graph_valid(sid: str) -> tuple[bool, str]:
    """Check spec validity first, fall back to legacy task_graph.json."""
    if _tgio_spec_valid is not None:
        ok, reason = _tgio_spec_valid(sid)
        if ok:
            return True, "spec_ok"
        if reason != "missing":
            return False, f"spec:{reason}"
    # Spec not present — fall through to legacy path
    return None, "spec_missing"  # type: ignore[return-value]


def _triface_parent_ready(sid: str) -> bool:
    """Check parent readiness via spec+state+closure, fall back to legacy."""
    if _tgio_parent_ready is not None:
        try:
            result = _tgio_parent_ready(sid)
            if result.get("source") in {"closure", "spec+state"}:
                return bool(result.get("ready"))
        except Exception:
            pass
    return False


def _blocked_external_prerequisites(path: Path) -> list[dict[str, Any]]:
    if not _nonempty(path):
        return []
    try:
        graph = json.loads(path.read_text())
    except Exception as exc:
        return [{"requirement": "task_graph", "reason": "parse_error", "error": str(exc)}]
    return iter_blocked(graph, SPRINTS_DIR)


def _contract_text(sid: str) -> str:
    path = SPRINTS_DIR / f"{sid}.contract.md"
    try:
        return path.read_text(errors="ignore")
    except Exception:
        return ""


def _contract_flag(text: str, key: str) -> bool:
    key_norm = key.lower().replace("_", " ")
    for raw in text.splitlines():
        if ":" not in raw:
            continue
        k, v = raw.split(":", 1)
        if k.strip().lower().replace("_", " ") == key_norm:
            return v.strip().lower() in {"true", "yes", "1", "ok"}
    return False


def _contract_value(text: str, key: str) -> str:
    key_norm = key.lower().replace("_", " ")
    for raw in text.splitlines():
        if ":" not in raw:
            continue
        k, v = raw.split(":", 1)
        if k.strip().lower().replace("_", " ") == key_norm:
            return v.strip()
    return ""


def route(sid: str) -> dict[str, Any]:
    sf = SPRINTS_DIR / f"{sid}.status.json"
    status = _read_json(sf)
    st = str(status.get("status") or "").strip()
    phase = str(status.get("phase") or "").strip()
    handoff_to = str(status.get("handoff_to") or "").strip()
    target_role = str(status.get("target_role") or "").strip()
    text = _contract_text(sid)

    prd = _artifact_path(sid, "prd.md", node_level=False)
    product_brief = _artifact_path(sid, "product-brief.md", node_level=False)
    design = _artifact_path(sid, "design.md")
    plan = _artifact_path(sid, "plan.md")
    graph = SPRINTS_DIR / f"{sid}.task_graph.json"
    prd_html = SPRINTS_DIR / f"{sid}.prd.html"
    design_html = SPRINTS_DIR / f"{sid}.design.html"
    planning_html = SPRINTS_DIR / f"{sid}.planning.html"
    handoff = _artifact_path(sid, "handoff.md")
    eval_md = _artifact_path(sid, "eval.md")
    eval_json = _artifact_path(sid, "eval.json")

    # Try triface (spec/state/closure) first; fall back to legacy task_graph.json
    _triface_ok, _triface_reason = _triface_graph_valid(sid)
    if _triface_ok is True:
        graph_ok, graph_reason = True, _triface_reason
    else:
        graph_ok, graph_reason = _graph_valid(graph)
        if _triface_ok is None and _triface_reason == "spec_missing":
            # spec just not created yet — use legacy result
            pass

    # Parent-ready: prefer triface (closure/state), fall back to legacy
    triface_ready = _triface_parent_ready(sid)
    graph_parent_ready = triface_ready or _graph_parent_ready(graph)
    blocked_prerequisites = _blocked_external_prerequisites(graph)
    artifacts = {
        "prd": _nonempty(prd),
        "product_brief": _nonempty(product_brief),
        "design": _nonempty(design),
        "plan": _nonempty(plan),
        "prd_html": _nonempty(prd_html),
        "design_html": _nonempty(design_html),
        "planning_html": _nonempty(planning_html),
        "task_graph": graph_ok,
        "task_graph_parent_ready": graph_parent_ready,
        "handoff": _nonempty(handoff),
        "eval": _nonempty(eval_md) or _nonempty(eval_json),
    }
    planner_ready = artifacts["prd"] and artifacts["design"] and artifacts["plan"] and artifacts["task_graph"]
    requirements_ready = artifacts["prd"]

    contract_bypass = _contract_flag(text, "bypass_pm") or _contract_flag(text, "bypass pm")
    operator_bypass = _contract_flag(text, "operator_bypass_pm") or bool(status.get("operator_bypass_pm"))
    contract_handoff = _contract_value(text, "handoff_to")
    contract_target = _contract_value(text, "target_role")

    violations: list[str] = []
    builder_claim = (
        contract_bypass
        or handoff_to in {"builder", "builder_main"}
        or target_role in {"builder", "builder_main"}
        or contract_handoff in {"builder", "builder_main"}
        or contract_target in {"builder", "builder_main"}
        or phase in {"planning_complete", "graph_dispatch_active"}
    )
    if contract_bypass and not operator_bypass:
        violations.append("legacy_bypass_pm_ignored")
    if builder_claim and not planner_ready and not operator_bypass:
        violations.append("builder_route_without_prd_design_plan_task_graph")
    if phase in {"prd_ready", "contract_ready"} and not requirements_ready:
        violations.append("phase_requires_pm_prd")
    if _nonempty(graph) and not graph_ok:
        violations.append(f"invalid_task_graph:{graph_reason}")

    if st in {"passed", "done", "eval_pass", "finalized", "superseded"} or graph_parent_ready:
        role, stage, reason = "none", "done", "terminal_status"
    elif st in {"reviewing", "ready_for_review"} or (artifacts["handoff"] and handoff_to == "evaluator"):
        role, stage, reason = "evaluator", "build_complete", "handoff_ready_for_eval"
    elif planner_ready and blocked_prerequisites and not operator_bypass:
        role, stage, reason = "none", "dependency_blocked", "external_prerequisite_blocked"
    elif planner_ready or operator_bypass:
        role, stage, reason = "builder_main", "planning_complete", "planner_artifacts_and_task_graph_ready"
    elif requirements_ready:
        role, stage, reason = "planner", "prd_ready", "pm_prd_ready"
    else:
        role, stage, reason = "pm", "intake", "missing_pm_prd"

    return {
        "ok": not violations,
        "sid": sid,
        "route_role": role,
        "stage": stage,
        "reason": reason,
        "status": st,
        "phase": phase,
        "handoff_to": handoff_to,
        "target_role": target_role,
        "artifacts": artifacts,
        "graph_reason": graph_reason,
        "blocked_prerequisites": blocked_prerequisites,
        "violations": violations,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("route")
    r.add_argument("sid")
    r.add_argument("--json", action="store_true")
    r.add_argument("--field", default="")
    args = ap.parse_args()

    if args.cmd == "route":
        out = route(args.sid)
        if args.field:
            value: Any = out
            for part in args.field.split("."):
                value = value.get(part) if isinstance(value, dict) else None
            if isinstance(value, (dict, list)):
                print(json.dumps(value, ensure_ascii=False))
            elif value is None:
                print("")
            else:
                print(value)
            return 0
        print(json.dumps(out, ensure_ascii=False, indent=2 if args.json else None))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
