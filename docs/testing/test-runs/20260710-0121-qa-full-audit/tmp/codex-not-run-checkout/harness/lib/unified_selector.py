#!/usr/bin/env python3
"""Shared selector utilities for actor bindings and physical operators."""
from __future__ import annotations

import json
import re
from typing import Any
from selector_runtime_store import actor_load_snapshot, record_selection, round_robin_start_index


def _normalize_bound_candidates(candidates: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        if isinstance(candidate, dict):
            actor_id = str(candidate.get("actor_id") or "").strip()
            if not actor_id:
                continue
            normalized.append(
                {
                    "actor_id": actor_id,
                    "priority": int(candidate.get("priority", index + 1) or index + 1),
                    "condition": str(candidate.get("condition") or "always"),
                    "_order": index,
                }
            )
            continue
        actor_id = str(candidate or "").strip()
        if not actor_id:
            continue
        normalized.append(
            {
                "actor_id": actor_id,
                "priority": index + 1,
                "condition": "always",
                "_order": index,
            }
        )
    return normalized


def _candidate_priority(candidate: dict[str, Any]) -> tuple[int, int]:
    return int(candidate.get("priority", 9999) or 9999), int(candidate.get("_order", 9999) or 9999)


def _actor_cost_tier(actor: dict[str, Any]) -> int:
    raw = (
        (actor.get("cost_profile") or {}).get("cost_tier")
        or actor.get("cost_tier")
        or (actor.get("routing") or {}).get("cost_tier")
        or "medium"
    )
    return {"low": 1, "medium": 2, "high": 3}.get(str(raw).lower(), 2)


def _actor_runtime_load(actor: dict[str, Any]) -> float:
    runtime = actor.get("runtime_state") if isinstance(actor.get("runtime_state"), dict) else {}
    observability = actor.get("observability") if isinstance(actor.get("observability"), dict) else {}
    lease = actor.get("lease") if isinstance(actor.get("lease"), dict) else {}
    for container in (runtime, observability):
        for key in ("active_count", "load", "busy_count", "current_tasks"):
            value = container.get(key)
            if isinstance(value, (int, float)):
                return float(value)
    if lease.get("holder_sprint") or lease.get("lease_id"):
        return 1.0
    return 0.0


def _actor_load_rank(actor_id: str, actor: dict[str, Any]) -> tuple[float, int, str]:
    runtime_load = _actor_runtime_load(actor)
    snapshot = actor_load_snapshot(actor_id)
    active_lease = float(snapshot.get("active_lease_count", 0) or 0)
    selection_count = int(snapshot.get("selection_count", 0) or 0)
    last_selected_at = str(snapshot.get("last_selected_at") or "")
    return max(runtime_load, active_lease), selection_count, last_selected_at


def _order_bound_candidates(
    candidates: list[Any],
    *,
    selection_policy: str = "priority_first",
    actor_registry: dict[str, dict[str, Any]] | None = None,
    operator_type: str = "",
) -> list[dict[str, Any]]:
    normalized = _normalize_bound_candidates(candidates)
    if not normalized:
        return []
    actors = actor_registry or {}
    policy = str(selection_policy or "priority_first").strip().lower()
    ordered = sorted(normalized, key=_candidate_priority)
    if policy == "cost_optimal":
        return sorted(
            ordered,
            key=lambda candidate: (
                _actor_cost_tier(actors.get(candidate["actor_id"], {})),
                *_candidate_priority(candidate),
            ),
        )
    if policy == "least_loaded":
        return sorted(
            ordered,
            key=lambda candidate: (
                *_actor_load_rank(candidate["actor_id"], actors.get(candidate["actor_id"], {})),
                *_candidate_priority(candidate),
            ),
        )
    if policy == "round_robin" and len(ordered) > 1:
        cursor = round_robin_start_index(operator_type or "__global__", len(ordered))
        return ordered[cursor:] + ordered[:cursor]
    return ordered


def select_bound_candidate(
    candidates: list[Any],
    *,
    selection_policy: str = "priority_first",
    actor_registry: dict[str, dict[str, Any]] | None = None,
    operator_type: str = "",
    unavailable: set[str] | None = None,
    quota_blocked: set[str] | None = None,
    risk_denied: set[str] | None = None,
) -> tuple[str | None, list[dict[str, str]]]:
    unavail = unavailable or set()
    blocked = quota_blocked or set()
    denied = risk_denied or set()
    rejected: list[dict[str, str]] = []
    ordered = _order_bound_candidates(
        candidates,
        selection_policy=selection_policy,
        actor_registry=actor_registry,
        operator_type=operator_type,
    )
    for item in ordered:
        candidate = str(item.get("actor_id") or "")
        if candidate in unavail:
            rejected.append({"actor_id": candidate, "reason": "unavailable"})
            continue
        if candidate in blocked:
            rejected.append({"actor_id": candidate, "reason": "quota_blocked"})
            continue
        if candidate in denied:
            rejected.append({"actor_id": candidate, "reason": "risk_denied"})
            continue
        if operator_type:
            record_selection(
                operator_type,
                candidate,
                selection_policy=selection_policy,
            )
        return candidate, rejected
    return None, rejected


def _is_true(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in {"true", "yes", "1"}
    if isinstance(val, int):
        return val != 0
    return False


def expand_selector_str(val: str) -> set[str]:
    text = str(val or "").lower()
    parts = [p for p in re.split(r"[^a-z0-9]+", text) if p]
    return {text}.union(parts)


def selector_values(selector: Any) -> list[str]:
    def expand(val: str) -> list[str]:
        return [p for p in re.split(r"[^a-z0-9]+", val.lower()) if p] + [val.lower()]

    if isinstance(selector, list):
        values: list[str] = []
        for v in selector:
            if str(v).strip():
                values.extend(expand(str(v)))
        return values
    if isinstance(selector, dict):
        values: list[str] = []
        for key in ("operator_id", "task_type", "task_class", "role", "provider", "vendor", "model", "cost_tier", "latency_tier"):
            raw = selector.get(key)
            if raw:
                values.extend(expand(str(raw)))
        for key in ("capabilities", "required_capabilities", "best_for", "preferred_for"):
            raw = selector.get(key)
            if isinstance(raw, list):
                for v in raw:
                    if str(v).strip():
                        values.extend(expand(str(v)))
            elif raw:
                values.extend(expand(str(raw)))
        return values
    return expand(str(selector))


def role_from_node(node: dict[str, Any], fallback_role: str = "builder") -> str:
    role = str(
        node.get("role")
        or node.get("target_role")
        or node.get("persona")
        or fallback_role
    ).strip().lower()
    return role or fallback_role


def operator_supports_task_type(operator: dict[str, Any], task_type: str) -> bool:
    if not task_type:
        return True
    task_type_lower = task_type.lower()
    avoid_list: list[str] = []
    if "avoid_for" in operator:
        avoid_list.extend([str(x).lower() for x in operator["avoid_for"]])
    if "routing" in operator and isinstance(operator["routing"], dict):
        avoid_list.extend([str(x).lower() for x in operator["routing"].get("avoid_task_types", [])])
    task_type_parts = expand_selector_str(task_type)
    for avoid_item in avoid_list:
        if task_type_parts & expand_selector_str(avoid_item):
            return False

    allowed_list: list[str] = []
    if "task_classes" in operator:
        allowed_list.extend([str(x).lower() for x in operator["task_classes"]])
    if "preferred_for" in operator:
        allowed_list.extend([str(x).lower() for x in operator["preferred_for"]])
    if "routing" in operator and isinstance(operator["routing"], dict):
        allowed_list.extend([str(x).lower() for x in operator["routing"].get("primary_task_types", [])])
    if not allowed_list:
        return True
    for allowed_item in allowed_list:
        if task_type_parts & expand_selector_str(allowed_item):
            return True
    return any(task_type_lower in allowed_item or allowed_item in task_type_lower for allowed_item in allowed_list)


def get_operator_capability_score(operator: dict[str, Any], capability_name: str) -> float:
    capability_name_lower = capability_name.lower().replace("_", "-")
    caps = operator.get("capability") or operator.get("capabilities")
    if isinstance(caps, dict):
        for k, v in caps.items():
            if str(k).lower().replace("_", "-") == capability_name_lower:
                try:
                    return float(v)
                except (ValueError, TypeError):
                    pass
    strengths = [str(x).lower().replace("_", "-") for x in operator.get("strengths") or []]
    if capability_name_lower in strengths:
        return 5.0
    preferred = [str(x).lower().replace("_", "-") for x in operator.get("preferred_for") or []]
    if capability_name_lower in preferred:
        return 4.0
    task_classes = [str(x).lower().replace("_", "-") for x in operator.get("task_classes") or []]
    if capability_name_lower in task_classes:
        return 4.0
    return 1.0


def check_capability_score(operator_score_value: float | int, constraint_str_or_val: Any) -> bool:
    if constraint_str_or_val is None:
        return True
    if isinstance(constraint_str_or_val, (int, float)):
        return operator_score_value >= constraint_str_or_val
    val_str = str(constraint_str_or_val).strip()
    if not val_str:
        return True
    match = re.match(r"^([><=]=?|!=)\s*([0-9.]+)$", val_str)
    if match:
        op, val_num_str = match.groups()
        val_num = float(val_num_str)
        if op == ">=":
            return operator_score_value >= val_num
        if op == ">":
            return operator_score_value > val_num
        if op == "<=":
            return operator_score_value <= val_num
        if op == "<":
            return operator_score_value < val_num
        if op == "==":
            return operator_score_value == val_num
        if op == "!=":
            return operator_score_value != val_num
    else:
        try:
            return operator_score_value >= float(val_str)
        except ValueError:
            pass
    return True


def operator_satisfies_constraints(operator: dict[str, Any], constraints: dict[str, Any]) -> bool:
    if not constraints or not isinstance(constraints, dict):
        return True
    tier_map = {"low": 1, "medium": 2, "high": 3}
    for key, val in constraints.items():
        if key == "max_cost_tier":
            if tier_map.get(str(operator.get("cost_tier") or "medium").lower(), 2) > tier_map.get(str(val).lower(), 2):
                return False
        elif key == "max_latency_tier":
            if tier_map.get(str(operator.get("latency_tier") or "medium").lower(), 2) > tier_map.get(str(val).lower(), 2):
                return False
        elif key == "min_context_tier":
            context_map = {"low": 1, "medium": 2, "high": 3}
            if context_map.get(str(operator.get("context_tier") or "medium").lower(), 2) < context_map.get(str(val).lower(), 2):
                return False
        else:
            op_val = operator.get(key)
            if op_val is None and isinstance(operator.get("policy"), dict):
                op_val = operator["policy"].get(key)
            if op_val is None and isinstance(operator.get("routing"), dict):
                op_val = operator["routing"].get(key)
            if op_val is not None and str(op_val).lower() != str(val).lower():
                return False
    return True


def check_quota_reserve(operator: dict[str, Any], task_type: str) -> bool:
    quota = operator.get("quota")
    if not isinstance(quota, dict):
        return True
    reserve_for = quota.get("reserve_for")
    if not reserve_for:
        return True
    reserve_list = [reserve_for] if not isinstance(reserve_for, list) else reserve_for
    reserve_for_lower = [str(x).lower() for x in reserve_list]
    return bool(task_type and task_type.lower() in reserve_for_lower)


def operator_matches_class(operator: dict[str, Any], class_name: str) -> bool:
    op_class = operator.get("operator_class")
    if not op_class and isinstance(operator.get("routing"), dict):
        op_class = operator["routing"].get("operator_class")
    if not op_class:
        return False
    if isinstance(op_class, list):
        return any(str(c).lower() == class_name.lower() for c in op_class)
    return str(op_class).lower() == class_name.lower()


def operator_has_any(operator: dict[str, Any], needles: set[str]) -> bool:
    values: list[str] = []
    for key in ("task_classes", "strengths", "preferred_for", "capabilities", "input_modalities", "output_modalities", "artifact_types"):
        raw = operator.get(key) or []
        if isinstance(raw, str):
            values.append(raw.lower())
        else:
            values.extend(str(v).lower() for v in raw)
    return any(needle in value or value in needle for needle in needles for value in values if value)


def score_operator(operator: dict[str, Any], node: dict[str, Any], selector: Any, *, fallback_role: str = "builder") -> int:
    values = set(selector_values(selector))
    role = role_from_node(node, fallback_role=fallback_role)
    values.add(role.lower())
    req_caps = node.get("required_capabilities") or []
    if isinstance(req_caps, dict):
        values.update(str(item).lower() for item in req_caps.keys())
    else:
        values.update(str(item).lower() for item in req_caps)
    for item in node.get("required_skills") or []:
        values.add(str(item).lower())
    for key in ("goal", "title", "description"):
        text = str(node.get(key) or "").lower()
        for marker in (
            "implementation", "debug", "tests", "planning", "architecture", "review",
            "knowledge", "thunder", "gemini", "image", "vision", "multimodal",
            "screenshot", "ui", "mockup", "diagram", "ocr",
        ):
            if marker in text:
                values.add(marker)

    score = 0
    haystacks = [
        str(operator.get("operator_id") or "").lower(),
        str(operator.get("role") or "").lower(),
        str(operator.get("provider") or "").lower(),
        str(operator.get("vendor") or "").lower(),
        str(operator.get("model") or "").lower(),
        str(operator.get("profile") or "").lower(),
    ]
    for key in ("task_classes", "roles", "strengths", "preferred_for", "capabilities", "input_modalities", "output_modalities", "artifact_types"):
        raw = operator.get(key) or []
        if isinstance(raw, str):
            haystacks.append(raw.lower())
        else:
            haystacks.extend(str(v).lower() for v in raw)
    for value in values:
        if value and any(value == h or value in h or h in value for h in haystacks if h):
            score += 10
    if str(operator.get("role") or "").lower() == role.lower():
        score += 8
    tier_bias = {"low": 3, "medium": 2, "high": 1}
    score += tier_bias.get(str(operator.get("cost_tier") or "").lower(), 0)
    score += tier_bias.get(str(operator.get("latency_tier") or "").lower(), 0)
    return score


def rank_physical_operators(
    *,
    operators: list[dict[str, Any]],
    node: dict[str, Any],
    selector: Any,
    dispatchable_fn,
    role: str,
    task_type: str = "",
    required_capabilities: dict[str, Any] | None = None,
    preferred_operator_classes: list[str] | str | None = None,
    constraints: dict[str, Any] | None = None,
    verifier_required: bool = False,
    prior_operator: str = "",
    modality_required: bool = False,
    modality_values: set[str] | None = None,
    preferred_operator_ids: set[str] | None = None,
    default_operator_profile: str = "",
    kind_priority_bias: bool = False,
) -> list[tuple[int, dict[str, Any]]]:
    scored: list[tuple[int, dict[str, Any]]] = []
    selector_value_set = set(selector_values(selector))
    if task_type:
        selector_value_set.update(expand_selector_str(task_type))
    modalities = modality_values or set()
    preferred_ids = preferred_operator_ids or set()

    for operator in operators:
        ok, _reason = dispatchable_fn(operator)
        if not ok:
            continue
        if verifier_required and prior_operator:
            prior_clean = str(prior_operator).strip().lower()
            op_id_clean = str(operator.get("operator_id")).strip().lower()
            op_prof_clean = str(operator.get("profile") or "").strip().lower()
            if prior_clean in {op_id_clean, op_prof_clean}:
                continue
        if task_type and not operator_supports_task_type(operator, task_type):
            continue
        if required_capabilities and isinstance(required_capabilities, dict):
            if any(
                not check_capability_score(
                    get_operator_capability_score(operator, cap_name),
                    cap_constraint,
                )
                for cap_name, cap_constraint in required_capabilities.items()
            ):
                continue
        if constraints and not operator_satisfies_constraints(operator, constraints):
            continue
        if not check_quota_reserve(operator, task_type):
            continue
        if modality_required and not operator_has_any(operator, selector_value_set & modalities):
            continue
        score = score_operator(operator, node, selector, fallback_role=role or "builder")
        if kind_priority_bias:
            kind = str(operator.get("launch_cmd_kind", "") or operator.get("backend", ""))
            if "print_once" in kind or "print" in kind:
                score += 10
            elif "command" in kind:
                score += 5
            else:
                score += 1
        if preferred_operator_classes:
            classes_list = [preferred_operator_classes] if isinstance(preferred_operator_classes, str) else list(preferred_operator_classes)
            for class_name in classes_list:
                if operator_matches_class(operator, str(class_name)):
                    score += 100
        if preferred_ids and str(operator.get("operator_id") or "") in preferred_ids:
            score += 20
        if default_operator_profile and (
            str(operator.get("operator_id") or "") == default_operator_profile
            or str(operator.get("profile") or "") == default_operator_profile
        ):
            score += 8
        scored.append((score, operator))
    scored.sort(key=lambda item: (item[0], str(item[1].get("operator_id") or "")), reverse=True)
    return scored


def dump_ranked_operators(ranked: list[tuple[int, dict[str, Any]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for score, operator in ranked:
        rows.append(
            {
                "operator_id": str(operator.get("operator_id") or ""),
                "score": score,
                "role": str(operator.get("role") or ""),
                "profile": str(operator.get("profile") or ""),
                "provider": str(operator.get("provider") or ""),
                "model": str(operator.get("model") or ""),
                "task_classes": json.loads(json.dumps(operator.get("task_classes") or [])),
                "preferred_for": json.loads(json.dumps(operator.get("preferred_for") or [])),
            }
        )
    return rows
