#!/usr/bin/env python3
"""Durable provider route proof for graph/runtime sprints."""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path
from typing import Any

from task_lifecycle import ACTIVE_TASK_STATUSES, TERMINAL_TASK_STATUSES

RUNTIME_DEFAULT_ALLOWED_PROVIDERS = {
    "codex": {"openai"},
    "claude": {"anthropic"},
}


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _normalize_provider(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    aliases = {
        "openai": "openai",
        "codex": "openai",
        "gpt": "openai",
        "anthropic": "anthropic",
        "claude": "anthropic",
        "claude-cli": "anthropic",
        "zhipu": "zhipu",
        "zhipuai": "zhipu",
        "glm": "zhipu",
        "google": "google",
        "gemini": "google",
    }
    return aliases.get(raw, raw)


def _provider_policy_values(value: Any) -> set[str]:
    out: set[str] = set()
    if isinstance(value, (list, tuple, set)):
        items = value
    else:
        items = str(value or "").replace(";", ",").split(",")
    for item in items:
        normalized = _normalize_provider(item)
        if normalized:
            out.add(normalized)
    return out


def _load_operator_registry(harness_dir: Path) -> dict[str, dict[str, Any]]:
    data = _read_json(harness_dir / "config" / "physical-operators.json")
    operators = data.get("operators")
    if isinstance(operators, dict):
        return {str(k): v for k, v in operators.items() if isinstance(v, dict)}
    if isinstance(operators, list):
        result: dict[str, dict[str, Any]] = {}
        for item in operators:
            if not isinstance(item, dict):
                continue
            op_id = str(item.get("id") or item.get("operator_id") or "").strip()
            if op_id:
                result[op_id] = item
        return result
    return {}


def _iter_pm_records(harness_dir: Path, sid: str) -> list[tuple[Path, dict[str, Any]]]:
    inbox = harness_dir / "run" / "pm-inbox"
    rows: list[tuple[Path, dict[str, Any]]] = []
    if not inbox.exists():
        return rows
    for path in sorted(inbox.glob("*.json")):
        data = _read_json(path)
        if str(data.get("sprint_id") or "") == sid or sid in str(data.get("task_id") or path.name):
            rows.append((path, data))
    return rows


def _iter_operator_results(harness_dir: Path, sid: str) -> list[tuple[Path, dict[str, Any]]]:
    root = harness_dir / "run" / "operator-results"
    rows: list[tuple[Path, dict[str, Any]]] = []
    if not root.exists():
        return rows
    for path in sorted(root.glob("*/*/result.json")):
        data = _read_json(path)
        if str(data.get("sprint_id") or "") == sid or sid in str(data.get("task_id") or path.parent.name):
            rows.append((path, data))
    return rows


def _node_id_from_model_call(sid: str, payload: dict[str, Any]) -> str:
    instruction = Path(str(payload.get("instruction_file") or "")).name
    prefix = f"{sid}."
    if instruction.startswith(prefix):
        remainder = instruction[len(prefix) :]
        if "-eval-dispatch" in remainder:
            return remainder.split("-eval-dispatch", 1)[0]
        if remainder.endswith("-dispatch.md"):
            return remainder[: -len("-dispatch.md")]

    dispatch_id = str(payload.get("dispatch_id") or "").strip()
    for dispatch_prefix in (f"graph-eval-{sid}-", f"graph-{sid}-"):
        if not dispatch_id.startswith(dispatch_prefix):
            continue
        remainder = dispatch_id[len(dispatch_prefix) :]
        return re.sub(r"-\d{8}T\d{6}Z(?:-q\d+)?$", "", remainder)
    return ""


def _iter_succeeded_model_calls(harness_dir: Path, sid: str) -> list[tuple[Path, dict[str, Any]]]:
    path = harness_dir / "sessions" / sid / "events.jsonl"
    rows: list[tuple[Path, dict[str, Any]]] = []
    if not path.is_file():
        return rows
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return rows
    for line in lines:
        try:
            event = json.loads(line)
        except Exception:
            continue
        if not isinstance(event, dict):
            continue
        if str(event.get("type") or "") != "model_call_succeeded":
            continue
        if str(event.get("source") or "") != "model_call_runtime":
            continue
        event_sid = str(event.get("sprint_id") or event.get("session_id") or "")
        if event_sid != sid:
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        model = payload.get("model") if isinstance(payload.get("model"), dict) else {}
        dispatch_id = str(payload.get("dispatch_id") or event.get("activity_id") or "").strip()
        if not dispatch_id:
            continue
        role = str(model.get("persona") or "").strip().lower()
        rows.append(
            (
                path,
                {
                    "task_id": dispatch_id,
                    "sprint_id": sid,
                    "node_id": _node_id_from_model_call(sid, payload),
                    "requested_role": role,
                    "runtime_mode": str(model.get("pane_runtime") or "").strip().lower(),
                    "status": str(payload.get("status") or "runtime_accepted"),
                    "provider": model.get("provider"),
                    "model": model.get("model"),
                    "pane": payload.get("pane"),
                    "dispatch_mode": "direct_pane_eval" if role == "evaluator" else "direct_pane",
                    "runtime_evidence": "model_call_succeeded",
                    "runtime_metadata_source": model.get("metadata_source"),
                    "event_id": event.get("event_id"),
                },
            )
        )
    return rows


def _artifact_path(harness_dir: Path, value: Any) -> Path | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = harness_dir / "sprints" / raw
    return path


def _iter_task_graph_nodes(harness_dir: Path, sid: str) -> list[dict[str, Any]]:
    graph = _read_json(harness_dir / "sprints" / f"{sid}.task_graph.json")
    nodes = graph.get("nodes")
    return [node for node in nodes if isinstance(node, dict)] if isinstance(nodes, list) else []


def _physical_selected_operator_ids(harness_dir: Path, node: dict[str, Any]) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []

    def add(value: Any, source: str) -> None:
        operator_id = str(value or "").strip()
        if operator_id:
            selected.append({"operator_id": operator_id, "source": source})

    artifacts = node.get("artifacts") if isinstance(node.get("artifacts"), dict) else {}
    add(artifacts.get("suggested_operator_id"), "task_graph.artifacts.suggested_operator_id")
    add(artifacts.get("selected_operator_id"), "task_graph.artifacts.selected_operator_id")

    inline = node.get("physical_plan_ir") if isinstance(node.get("physical_plan_ir"), dict) else {}
    add(inline.get("suggested_operator_id"), "task_graph.physical_plan_ir.suggested_operator_id")
    add(inline.get("selected_operator_id"), "task_graph.physical_plan_ir.selected_operator_id")

    physical_path = _artifact_path(harness_dir, artifacts.get("physical_plan_ir"))
    if physical_path is not None:
        physical = _read_json(physical_path)
        add(physical.get("suggested_operator_id"), f"physical_plan_ir.suggested_operator_id:{physical_path}")
        add(physical.get("selected_operator_id"), f"physical_plan_ir:{physical_path}")

    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in selected:
        key = (item["operator_id"], item["source"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _stage_key(data: dict[str, Any], path: Path) -> str:
    task_id = str(data.get("task_id") or "").strip()
    if task_id:
        return task_id
    return str(path)


def _merge_stage(stage: dict[str, Any], data: dict[str, Any], *, source_path: Path, source: str) -> None:
    stage.setdefault("sources", [])
    stage["sources"].append({"source": source, "path": str(source_path)})

    for key in ("task_id", "sprint_id", "node_id", "operator_id"):
        value = str(data.get(key) or "").strip()
        if value and not stage.get(key):
            stage[key] = value
    role = str(data.get("requested_role") or data.get("role") or "").strip()
    if role and not stage.get("role"):
        stage["role"] = role

    if str(data.get("runtime_mode") or "").strip() and not stage.get("runtime_mode"):
        stage["runtime_mode"] = str(data["runtime_mode"]).strip()
    if str(data.get("provider_policy") or "").strip() and not stage.get("provider_policy"):
        stage["provider_policy"] = str(data["provider_policy"]).strip()

    for key in ("pane", "dispatch_mode", "runtime_evidence", "runtime_metadata_source", "event_id"):
        value = str(data.get(key) or "").strip()
        if value and not stage.get(key):
            stage[key] = value

    status = str(data.get("status") or "").strip()
    if status:
        stage["status"] = status

    provider = (
        data.get("effective_provider")
        or data.get("operator_provider")
        or data.get("provider")
        or data.get("vendor")
    )
    normalized_provider = _normalize_provider(provider)
    if normalized_provider:
        stage["provider"] = normalized_provider
        stage["provider_raw"] = str(provider)

    model = data.get("effective_model") or data.get("operator_model") or data.get("model") or data.get("routing_model")
    if str(model or "").strip():
        stage["model"] = str(model).strip()
    requested_model = data.get("requested_model")
    if str(requested_model or "").strip():
        stage["requested_model"] = str(requested_model).strip()
    if source == "operator_result":
        stage["result_json"] = str(source_path)
        stage["exit_code"] = data.get("exit_code")


def build_route_proof(
    harness_dir: str | Path,
    sid: str,
    *,
    selected_runtime: str | None = None,
) -> dict[str, Any]:
    """Build route proof from PM/results plus verified direct-pane model calls."""
    harness = Path(harness_dir)
    sid = str(sid or "").strip()
    operators = _load_operator_registry(harness)
    stages: dict[str, dict[str, Any]] = {}
    runtime_values: set[str] = set()
    provider_policy_values: set[str] = set()

    for path, data in _iter_pm_records(harness, sid):
        key = _stage_key(data, path)
        stage = stages.setdefault(key, {})
        _merge_stage(stage, data, source_path=path, source="pm_record")
        runtime = str(data.get("runtime_mode") or "").strip().lower()
        if runtime:
            runtime_values.add(runtime)
        provider_policy_values.update(_provider_policy_values(data.get("provider_policy")))

    for path, data in _iter_operator_results(harness, sid):
        key = _stage_key(data, path)
        stage = stages.setdefault(key, {})
        _merge_stage(stage, data, source_path=path, source="operator_result")

    for path, data in _iter_succeeded_model_calls(harness, sid):
        key = _stage_key(data, path)
        stage = stages.setdefault(key, {})
        _merge_stage(stage, data, source_path=path, source="model_call_succeeded")
        runtime = str(data.get("runtime_mode") or "").strip().lower()
        if runtime:
            runtime_values.add(runtime)

    for stage in stages.values():
        op_id = str(stage.get("operator_id") or "").strip()
        op = operators.get(op_id, {})
        if not stage.get("provider"):
            provider = _normalize_provider(op.get("provider") or op.get("vendor") or op.get("backend"))
            if provider:
                stage["provider"] = provider
                stage["provider_raw"] = str(op.get("provider") or op.get("vendor") or op.get("backend") or "")
        if not stage.get("model") and str(op.get("model") or "").strip():
            stage["model"] = str(op["model"]).strip()
        if not stage.get("role") and str(op.get("role") or "").strip():
            stage["role"] = str(op["role"]).strip()

    runtime = str(selected_runtime or "").strip().lower()
    if not runtime and runtime_values:
        runtime = sorted(runtime_values)[0]
    allowed = set(provider_policy_values)
    if not allowed and runtime in RUNTIME_DEFAULT_ALLOWED_PROVIDERS:
        allowed = set(RUNTIME_DEFAULT_ALLOWED_PROVIDERS[runtime])

    violations: list[dict[str, Any]] = []
    incomplete_stages: list[dict[str, Any]] = []
    enforce = bool(allowed)
    for stage in sorted(stages.values(), key=lambda item: str(item.get("task_id") or item.get("node_id") or "")):
        provider = _normalize_provider(stage.get("provider"))
        status = str(stage.get("status") or "").strip().lower()
        has_result = bool(stage.get("result_json"))
        has_succeeded_call = stage.get("runtime_evidence") == "model_call_succeeded"
        if enforce and status in ACTIVE_TASK_STATUSES and not has_result and not has_succeeded_call:
            incomplete_stages.append(
                {
                    "task_id": stage.get("task_id"),
                    "node_id": stage.get("node_id"),
                    "status": status,
                    "reason": "route_record_incomplete",
                }
            )
        should_check = enforce and (
            has_result
            or status in TERMINAL_TASK_STATUSES
            or has_succeeded_call
        )
        if not should_check:
            continue
        if not provider:
            violations.append({
                "task_id": stage.get("task_id"),
                "node_id": stage.get("node_id"),
                "reason": "missing_provider",
            })
        elif provider not in allowed:
            violations.append({
                "task_id": stage.get("task_id"),
                "node_id": stage.get("node_id"),
                "provider": provider,
                "allowed_providers": sorted(allowed),
                "reason": "provider_policy_violation",
            })

    stage_list = sorted(
        stages.values(),
        key=lambda item: (str(item.get("node_id") or ""), str(item.get("task_id") or "")),
    )
    actual_operator_ids_by_node: dict[str, set[str]] = {}
    for stage in stage_list:
        node_id = str(stage.get("node_id") or "").strip()
        operator_id = str(stage.get("operator_id") or "").strip()
        if node_id and operator_id:
            actual_operator_ids_by_node.setdefault(node_id, set()).add(operator_id)

    attribution_warnings: list[dict[str, Any]] = []
    for node in _iter_task_graph_nodes(harness, sid):
        node_id = str(node.get("id") or "").strip()
        if not node_id:
            continue
        actual_operator_ids = actual_operator_ids_by_node.get(node_id, set())
        if not actual_operator_ids:
            continue
        for selected in _physical_selected_operator_ids(harness, node):
            selected_operator_id = selected["operator_id"]
            if selected_operator_id in actual_operator_ids:
                continue
            attribution_warnings.append(
                {
                    "node_id": node_id,
                    "reason": "stale_physical_plan_selected_operator",
                    "selected_operator_id": selected_operator_id,
                    "selected_operator_source": selected["source"],
                    "actual_operator_ids": sorted(actual_operator_ids),
                    "trusted_sources": ["operator_result", "pm_record"],
                    "diagnostic": "physical_plan_selected_operator_untrusted_for_route_proof",
                }
            )

    complete = not incomplete_stages
    return {
        "ok": not violations and complete,
        "complete": complete,
        "generated_at": _utc_now(),
        "sprint_id": sid,
        "selected_runtime": runtime,
        "allowed_providers": sorted(allowed),
        "enforced": enforce,
        "violations": violations,
        "incomplete_stages": incomplete_stages,
        "diagnostics": {
            "attribution_warnings": attribution_warnings,
        },
        "stage_count": len(stage_list),
        "stages": stage_list,
    }


def write_route_proof(
    harness_dir: str | Path,
    sid: str,
    *,
    selected_runtime: str | None = None,
    sprints_dir: str | Path | None = None,
) -> dict[str, Any]:
    proof = build_route_proof(harness_dir, sid, selected_runtime=selected_runtime)
    out_dir = Path(sprints_dir) if sprints_dir is not None else Path(harness_dir) / "sprints"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{sid}.route-proof.json"
    proof["path"] = str(out)
    out.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return proof
