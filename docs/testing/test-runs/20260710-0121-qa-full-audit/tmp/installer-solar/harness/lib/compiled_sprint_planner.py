from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")
    return path


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _title_from_prd(prd_text: str, sprint_id: str) -> str:
    for line in prd_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return re.sub(r"^#+\s*", "", stripped).strip() or sprint_id
    return sprint_id


def _extract_bullets(text: str, header: str) -> list[str]:
    lines = text.splitlines()
    out: list[str] = []
    capture = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## ") and stripped[3:].strip().lower() == header.lower():
            capture = True
            continue
        if capture and stripped.startswith("## "):
            break
        if capture and stripped.startswith("- "):
            out.append(stripped[2:].strip())
    return out


def _waves(nodes: list[dict[str, Any]]) -> list[list[str]]:
    remaining = {str(node.get("id")): list(node.get("depends_on") or []) for node in nodes}
    done: set[str] = set()
    waves: list[list[str]] = []
    while remaining:
        ready = sorted([node_id for node_id, deps in remaining.items() if all(dep in done for dep in deps)])
        if not ready:
            ready = sorted(remaining)
        waves.append(ready)
        for node_id in ready:
            done.add(node_id)
            remaining.pop(node_id, None)
    return waves


def _requirement_map(graph: dict[str, Any]) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for node in graph.get("nodes") or []:
        node_id = str(node.get("id") or "")
        for req_id in node.get("requirement_ids") or []:
            row = rows.setdefault(
                str(req_id),
                {"requirement_id": str(req_id), "mapped_nodes": [], "acceptance_ids": []},
            )
            row["mapped_nodes"].append(node_id)
            row["acceptance_ids"].extend([str(x) for x in node.get("acceptance_ids") or []])
    for row in rows.values():
        row["mapped_nodes"] = sorted(set(row["mapped_nodes"]))
        row["acceptance_ids"] = sorted(set(row["acceptance_ids"]))
    return [rows[key] for key in sorted(rows)]


def build_design_markdown(*, sprint_id: str, prd_text: str, contract_text: str, graph: dict[str, Any]) -> str:
    title = _title_from_prd(prd_text, sprint_id)
    goals = _extract_bullets(prd_text, "Goals / Non-goals")
    success_metrics = _extract_bullets(contract_text, "Product Contract")
    nodes = graph.get("nodes") or []
    node_lines = []
    for node in nodes:
        node_id = str(node.get("id") or "")
        operator_name = str(node.get("logical_operator") or "N/A")
        capsule = str(node.get("capability_capsule_id") or "N/A")
        task_type = str(node.get("dispatch_task_type") or node.get("type") or "N/A")
        goal = str(node.get("goal") or "")
        node_lines.append(f"- `{node_id}` / `{operator_name}` / `{task_type}` / `{capsule}`: {goal}")
    write_scope = sorted({item for node in nodes for item in (node.get('write_scope') or [])})
    read_scope = sorted({item for node in nodes for item in (node.get('read_scope') or [])})
    return f"""# Design: {title}

sprint_id: `{sprint_id}`
status: planning_complete
generated_at: {_now()}
source_of_truth: compiled PRD / contract / task_graph

## 目标

{chr(10).join(f"- {item}" for item in goals) or "- 将编译型需求推进为可执行 planner contract。"}

## 设计原则

- Requirement IR / compiled contract 仍是事实源，planner 产物只做执行视图。
- 不绕过 `task_graph.json` 直接派 builder。
- 每条 requirement / acceptance 都必须能映射到节点和验证门。
- capability capsule 与 logical operator 绑定必须保留，不能在 planner 层丢失。

## 执行面分层

- **Planning layer**: `S1` 锁定实现边界与文件范围。
- **Implementation layer**: `S2` 做受约束实现，严格限制在声明写范围。
- **Verification layer**: `S3` 输出测试与证据。
- **Review layer**: `S4` / `S5` 负责 verifier 决策与 rollout note。

## 逻辑算子 / capsule 绑定

{chr(10).join(node_lines)}

## 产物边界

### Write Scope
{chr(10).join(f"- `{item}`" for item in write_scope) or "- N/A"}

### Read Scope
{chr(10).join(f"- `{item}`" for item in read_scope) or "- N/A"}

## requirement 映射

{chr(10).join(f"- `{row['requirement_id']}` -> {', '.join(row['mapped_nodes'])}" for row in _requirement_map(graph)) or "- N/A"}

## 风险

- 当前 sprint 先前只有 PRD / contract / task_graph，没有稳定的 planner 视图，容易导致 workflow_guard 与 acceptance closeout 对状态理解不一致。
- review 失败应优先回退到 planner，而不是误派 builder。
- `task_graph` 中的 capability capsule 必须与 runtime operator surface 保持一致，否则后续 builder 会出现旁路执行。

## 成功标志

{chr(10).join(f"- {item}" for item in success_metrics) or "- 设计/计划/任务图一致并可路由到 builder_main。"}
"""


def build_plan_markdown(*, sprint_id: str, contract_text: str, graph: dict[str, Any]) -> str:
    waves = _waves(graph.get("nodes") or [])
    wave_lines = [f"- Wave {idx}: {', '.join(nodes)}" for idx, nodes in enumerate(waves, start=1)]
    stop_rules = _extract_bullets(contract_text, "Agent Execution Contract")
    node_rows = []
    for node in graph.get("nodes") or []:
        node_rows.append(
            f"- `{node.get('id')}` depends_on={node.get('depends_on') or []} "
            f"acceptance={node.get('acceptance') or []} outputs={node.get('outputs') or []}"
        )
    return f"""# Plan: {sprint_id}

gate: `{sprint_id}:passed`
generated_at: {_now()}

## DAG Waves

{chr(10).join(wave_lines)}

## 节点清单

{chr(10).join(node_rows)}

## 路由约束

- `planning_complete` 前不得路由 builder。
- `task_graph` validate 失败不得推进状态。
- 失败评审默认回退给 planner，重新产出 design/plan，而不是直接返工 builder。

## Stop Rules

{chr(10).join(f"- {item}" for item in stop_rules) or "- 缺少可验证 acceptance 不得标记完成。"}
"""


def build_traceability_payload(*, sprint_id: str, graph: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "solar.compiled_sprint.traceability.v1",
        "sprint_id": sprint_id,
        "generated_at": _now(),
        "requirements": _requirement_map(graph),
        "nodes": [
            {
                "id": str(node.get("id") or ""),
                "logical_operator": str(node.get("logical_operator") or ""),
                "dispatch_task_type": str(node.get("dispatch_task_type") or node.get("type") or ""),
                "capability_capsule_id": str(node.get("capability_capsule_id") or ""),
                "depends_on": [str(dep) for dep in (node.get("depends_on") or [])],
                "acceptance_ids": [str(x) for x in (node.get("acceptance_ids") or [])],
            }
            for node in (graph.get("nodes") or [])
        ],
    }


def generate_planner_artifacts(*, runtime_root: Path, sprint_id: str) -> dict[str, Any]:
    sprint_root = runtime_root / "sprints"
    prd_path = sprint_root / f"{sprint_id}.prd.md"
    contract_path = sprint_root / f"{sprint_id}.contract.md"
    graph_path = sprint_root / f"{sprint_id}.task_graph.json"
    status_path = sprint_root / f"{sprint_id}.status.json"
    design_path = sprint_root / f"{sprint_id}.design.md"
    plan_path = sprint_root / f"{sprint_id}.plan.md"
    traceability_path = sprint_root / f"{sprint_id}.traceability.json"

    prd_text = _read_text(prd_path)
    contract_text = _read_text(contract_path)
    graph = _read_json(graph_path)

    from graph_scheduler import validate_graph  # noqa: WPS433
    from runtime_status import transition_status  # noqa: WPS433

    validation = validate_graph(graph)
    if not validation.get("ok"):
        return {"ok": False, "reason": "invalid_task_graph", "validation": validation, "sprint_id": sprint_id}

    _write_text(design_path, build_design_markdown(sprint_id=sprint_id, prd_text=prd_text, contract_text=contract_text, graph=graph))
    _write_text(plan_path, build_plan_markdown(sprint_id=sprint_id, contract_text=contract_text, graph=graph))
    _write_json(traceability_path, build_traceability_payload(sprint_id=sprint_id, graph=graph))

    updated, message = transition_status(
        status_path,
        "active",
        "compiled_sprint_planning_complete",
        "compiled_sprint_planner",
        extra={
            "graph_path": str(graph_path),
            "design_md": str(design_path),
            "plan_md": str(plan_path),
            "traceability_json": str(traceability_path),
            "route_role": "builder_main",
            "reason": "planner_artifacts_and_task_graph_ready",
            "status_fields": {
                "phase": "planning_complete",
                "stage": "planning_complete",
                "handoff_to": "builder_main",
                "target_role": "builder_main",
                "task_graph_status": "active",
                "active_node": None,
            },
        },
    )
    return {
        "ok": True,
        "sprint_id": sprint_id,
        "design_md": str(design_path),
        "plan_md": str(plan_path),
        "traceability_json": str(traceability_path),
        "validation": validation,
        "status": updated,
        "message": message,
    }
