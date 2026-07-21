#!/usr/bin/env python3
"""Epic decomposer for large Solar-Harness requirements.

Large asks must not be pushed into one pane as a single vague contract. This
module creates an epic envelope, bounded child PRDs/contracts, and a parent DAG
that can be activated by dependency instead of by manual prompting.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from prerequisite_resolver import iter_blocked
del _sys, _os

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
SPRINTS_DIR = Path(os.environ.get("SPRINTS_DIR", HARNESS_DIR / "sprints"))

DEFAULT_SLICES: list[dict[str, Any]] = [
    {
        "suffix": "requirements",
        "title": "需求拆解与追踪矩阵",
        "goal": "把用户原始大需求拆成可验收 outcomes、边界、非目标和追踪矩阵。",
        "depends_on": [],
        "write_scope": ["sprints/*prd.md", "sprints/*traceability.json"],
        "acceptance": [
            "每个 outcome 都有验收标准和风险边界",
            "明确哪些工作不能直接派 builder",
            "生成父 epic 到子 sprint 的 traceability map",
        ],
        "required_capabilities": ["product.requirements", "workflow.planning"],
    },
    {
        "suffix": "architecture",
        "title": "架构设计与接口契约",
        "goal": "基于需求矩阵产出系统分层、接口、数据模型、兼容策略和迁移方案。",
        "depends_on": ["requirements"],
        "write_scope": ["sprints/*design.md", "sprints/*architecture.md"],
        "acceptance": [
            "设计覆盖 control/data plane、状态、失败恢复和观测",
            "写清楚接口边界和旧系统兼容方式",
            "列出冲突、依赖和降级策略",
        ],
        "required_capabilities": ["architecture", "distributed-systems"],
    },
    {
        "suffix": "core-runtime",
        "title": "核心实现与数据模型",
        "goal": "实现核心库、状态机、schema、持久化和向后兼容适配层。",
        "depends_on": ["architecture"],
        "write_scope": ["lib/", "types/", "schemas/"],
        "acceptance": [
            "核心 API 有单测覆盖",
            "旧路径兼容，不破坏现有 wake/dispatch/status",
            "状态变更可由元数据或事件重建",
        ],
        "required_capabilities": ["python", "state-machine", "testing"],
    },
    {
        "suffix": "orchestration-ui",
        "title": "调度、自动化与可视化",
        "goal": "把核心能力接入 autopilot、DAG 调度、status UI、pane 可视化和运行时证据。",
        "depends_on": ["architecture"],
        "write_scope": ["tools/", "status-server/", "ui/", "state/"],
        "acceptance": [
            "ready 子任务能自动激活并派到正确角色",
            "UI 显示 epic、child sprint、能力使用和阻塞原因",
            "pane 输出不再只靠自然语言声称完成",
        ],
        "required_capabilities": ["workflow.planning", "observability", "frontend"],
    },
    {
        "suffix": "verification-release",
        "title": "验证、回归与发布证据",
        "goal": "建立端到端测试、负控、回归报告、文档和验收证据，防止半截完成。",
        "depends_on": ["core-runtime", "orchestration-ui"],
        "write_scope": ["tests/", "reports/", "README.md"],
        "acceptance": [
            "单测、集成测、负控和 activation-proof 全部可复现",
            "父 epic 不能在所有 required gate 通过前关闭",
            "产出最终 handoff/eval/report 并写入知识库 raw",
        ],
        "required_capabilities": ["evaluation", "testing", "documentation"],
    },
]


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def date_slug() -> str:
    return _dt.datetime.now().strftime("%Y%m%d")


def slugify(text: str, fallback: str = "large-requirement") -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:72] or fallback


def read_text_arg(value: str | None, file_value: str | None) -> str:
    if file_value:
        return Path(file_value).expanduser().read_text(encoding="utf-8", errors="replace").strip()
    return (value or "").strip()


def unique_path(prefix: str, suffix: str) -> Path:
    base = SPRINTS_DIR / f"{prefix}{suffix}"
    if not base.exists():
        return base
    for idx in range(2, 1000):
        candidate = SPRINTS_DIR / f"{prefix}-{idx}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"cannot allocate unique path for {prefix}{suffix}")


def derive_epic_id(title: str, slug: str | None = None) -> str:
    base = f"epic-{date_slug()}-{slugify(slug or title)}"
    path = unique_path(base, ".epic.json")
    return path.name.removesuffix(".epic.json")


def child_sid(epic_id: str, slice_suffix: str, idx: int) -> str:
    base = epic_id.replace("epic-", "sprint-", 1)
    return f"{base}-s{idx:02d}-{slugify(slice_suffix)}"


def node_id_for(slice_suffix: str, idx: int) -> str:
    return f"S{idx:02d}_{slugify(slice_suffix).replace('-', '_')}"


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def write_json(path: Path, data: dict[str, Any]) -> None:
    write_atomic(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def prd_markdown(epic_id: str, sid: str, title: str, raw_request: str, item: dict[str, Any]) -> str:
    return f"""# PRD: {item['title']}

epic_id: `{epic_id}`
sprint_id: `{sid}`
slice: `{item['suffix']}`

## 用户原始需求

{raw_request}

## 本切片目标

{item['goal']}

## 范围

- 只交付本切片，不允许声称父 Epic 已完成。
- 必须读取 `{epic_id}.epic.md`、`{epic_id}.traceability.json` 和父级 task_graph。
- 必须在 handoff 中写明上游依赖、下游影响和未闭环项。

## 验收标准

{chr(10).join(f"- {x}" for x in item['acceptance'])}

## 非目标

- 不直接绕过 planner 派 builder。
- 不用单个大 PRD 覆盖所有实现细节。
- 不用“已完成”替代可复现证据。

## 交付物

- `{sid}.design.md`
- `{sid}.plan.md`
- `{sid}.task_graph.json`
- `{sid}.handoff.md`
- `{sid}.eval.md` 或 `{sid}.eval.json`
"""


def contract_markdown(epic_id: str, sid: str, item: dict[str, Any], priority: str) -> str:
    return f"""# Contract: {item['title']}

priority: `{priority}`
epic_id: `{epic_id}`
sprint_id: `{sid}`
handoff_to: `planner`

## Intent

{item['goal']}

## Required Capabilities

{chr(10).join(f"- {x}" for x in item.get('required_capabilities', []))}

## Acceptance

{chr(10).join(f"- {x}" for x in item['acceptance'])}

## Stop Rules

- 缺 `.task_graph.json` 不得派 builder。
- 缺可复现验证不得标记 passed。
- 发现 scope 冲突必须回写父级 traceability。
"""


def status_payload(epic_id: str, sid: str, item: dict[str, Any], priority: str, active: bool) -> dict[str, Any]:
    return {
        "id": sid,
        "sprint_id": sid,
        "epic_id": epic_id,
        "title": item["title"],
        "status": "active" if active else "queued",
        "phase": "prd_ready" if active else "epic_waiting_dependency",
        "handoff_to": "planner" if active else "",
        "target_role": "planner" if active else "",
        "priority": priority,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "dependency_policy": "activated_by_epic_dag",
    }


def build_graph(epic_id: str, title: str, children: list[dict[str, Any]]) -> dict[str, Any]:
    suffix_to_node = {c["slice"]["suffix"]: c["node_id"] for c in children}
    nodes = []
    for child in children:
        item = child["slice"]
        deps = [suffix_to_node[d] for d in item.get("depends_on", []) if d in suffix_to_node]
        nodes.append(
            {
                "id": child["node_id"],
                "goal": item["goal"],
                "child_sprint_id": child["sid"],
                "depends_on": deps,
                "write_scope": item.get("write_scope", []),
                "read_scope": [f"{epic_id}.epic.md", f"{epic_id}.traceability.json"],
                "required_capabilities": item.get("required_capabilities", []),
                "preferred_model": "auto",
                "gate": f"{child['sid']}:passed",
                "acceptance": item.get("acceptance", []),
                "estimated_cost": "M",
                "status": "pending",
            }
        )
    return {
        "schema_version": "solar.epic.task_graph.v1",
        "epic_id": epic_id,
        "title": title,
        "nodes": nodes,
        "activation_policy": {
            "ready_child_status": "active/prd_ready/planner",
            "passed_child_statuses": ["passed", "completed", "eval_passed"],
            "max_activate_per_scan": 2,
        },
    }


def create_epic(args: argparse.Namespace) -> dict[str, Any]:
    title = args.title.strip()
    request = read_text_arg(args.request, args.request_file)
    if not title:
        raise SystemExit("--title is required")
    if not request:
        raise SystemExit("--request or --request-file is required")
    priority = args.priority
    epic_id = derive_epic_id(title, args.slug)
    slices = DEFAULT_SLICES[: max(3, min(args.slices, len(DEFAULT_SLICES)))]
    children: list[dict[str, Any]] = []
    first_ready_suffixes = {s["suffix"] for s in slices if not s.get("depends_on")}

    for idx, item in enumerate(slices, start=1):
        sid = child_sid(epic_id, item["suffix"], idx)
        node_id = node_id_for(item["suffix"], idx)
        active = bool(args.activate_ready and item["suffix"] in first_ready_suffixes)
        children.append({"sid": sid, "node_id": node_id, "slice": item, "active": active})
        if args.dry_run:
            continue
        write_atomic(SPRINTS_DIR / f"{sid}.prd.md", prd_markdown(epic_id, sid, title, request, item))
        write_atomic(SPRINTS_DIR / f"{sid}.contract.md", contract_markdown(epic_id, sid, item, priority))
        write_json(SPRINTS_DIR / f"{sid}.status.json", status_payload(epic_id, sid, item, priority, active))

    graph = build_graph(epic_id, title, children)
    traceability = {
        "schema_version": "solar.epic.traceability.v1",
        "epic_id": epic_id,
        "title": title,
        "created_at": utc_now(),
        "raw_request_chars": len(request),
        "children": [
            {
                "node_id": c["node_id"],
                "sprint_id": c["sid"],
                "slice": c["slice"]["suffix"],
                "title": c["slice"]["title"],
                "depends_on": c["slice"].get("depends_on", []),
                "status": "active" if c["active"] else "queued",
            }
            for c in children
        ],
    }
    epic_meta = {
        "schema_version": "solar.epic.v1",
        "epic_id": epic_id,
        "title": title,
        "priority": priority,
        "created_at": utc_now(),
        "request": request,
        "child_sprints": [c["sid"] for c in children],
        "task_graph": f"{epic_id}.task_graph.json",
        "traceability": f"{epic_id}.traceability.json",
        "status": "active" if args.activate_ready else "drafted",
    }
    epic_md = f"""# Epic: {title}

epic_id: `{epic_id}`
priority: `{priority}`
status: `{epic_meta['status']}`

## 目标

把一个大需求拆成互相关联的 PRD/Contract/TaskGraph，按依赖自动激活，避免单 pane 半截完成。

## 用户原始需求

{request}

## 子任务图

| Node | Sprint | Slice | Depends |
| --- | --- | --- | --- |
{chr(10).join(f"| {c['node_id']} | `{c['sid']}` | {c['slice']['title']} | {', '.join(c['slice'].get('depends_on', [])) or '-'} |" for c in children)}

## 调度规则

- 父级只负责拆解、依赖和验收，不直接编码。
- 子 sprint 必须走 PRD -> Planner design/plan/task_graph -> Builder -> Evaluator。
- 依赖未 passed 的子 sprint 保持 queued，不得提前派发。
"""
    if not args.dry_run:
        write_atomic(SPRINTS_DIR / f"{epic_id}.epic.md", epic_md)
        write_json(SPRINTS_DIR / f"{epic_id}.epic.json", epic_meta)
        write_json(SPRINTS_DIR / f"{epic_id}.task_graph.json", graph)
        write_json(SPRINTS_DIR / f"{epic_id}.traceability.json", traceability)
    return {
        "ok": True,
        "epic_id": epic_id,
        "title": title,
        "dry_run": args.dry_run,
        "paths": {
            "epic_md": str(SPRINTS_DIR / f"{epic_id}.epic.md"),
            "epic_json": str(SPRINTS_DIR / f"{epic_id}.epic.json"),
            "task_graph": str(SPRINTS_DIR / f"{epic_id}.task_graph.json"),
            "traceability": str(SPRINTS_DIR / f"{epic_id}.traceability.json"),
        },
        "children": [{"sid": c["sid"], "node_id": c["node_id"], "active": c["active"]} for c in children],
    }


def child_passed(sid: str) -> bool:
    status = child_status(sid)
    return str(status.get("status", "")).lower() in {"passed", "completed", "eval_passed"}


def child_status(sid: str) -> dict[str, Any]:
    path = SPRINTS_DIR / f"{sid}.status.json"
    status: dict[str, Any] = {}
    if not path.exists():
        return _child_status_from_graph(sid, status)
    try:
        status = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        status = {}
    if str(status.get("status") or "").lower() not in {"passed", "completed", "eval_passed"}:
        status = _child_status_from_graph(sid, status)
    return status


def _child_status_from_graph(sid: str, fallback: dict[str, Any]) -> dict[str, Any]:
    """Use child task_graph as source of truth when legacy status drifted."""
    graph_path = SPRINTS_DIR / f"{sid}.task_graph.json"
    if not graph_path.exists():
        return fallback
    try:
        from graph_scheduler import parent_ready_check, sync_status_cache_from_graph  # noqa: WPS433

        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        parent = parent_ready_check(graph)
        if not parent.get("ready"):
            return fallback
        sync = sync_status_cache_from_graph(
            graph,
            graph_path,
            actor="epic_decomposer",
            event="child_graph_parent_ready_status_sync",
        )
        if isinstance(sync.get("status"), dict):
            return sync["status"]
        return {
            **fallback,
            "id": sid,
            "sprint_id": sid,
            "status": "passed",
            "phase": "completed",
            "graph_parent_ready": parent,
            "status_sync": sync,
        }
    except Exception:
        return fallback


def sync_graph_from_children(graph: dict[str, Any]) -> bool:
    """Project child sprint status into the parent epic DAG.

    The epic graph is a projection, not a second source of truth. Keeping it in
    sync prevents stale `pending` parent nodes from blocking dependency release
    after a child sprint has already passed evaluator review.
    """
    changed = False
    for node in graph.get("nodes", []) or []:
        if not isinstance(node, dict):
            continue
        sid = str(node.get("child_sprint_id") or "")
        if not sid:
            continue
        status = child_status(sid)
        child_state = str(status.get("status", "")).lower()
        before = str(node.get("status") or "")
        if child_state in {"passed", "completed", "eval_passed"}:
            after = "passed"
        elif child_state == "active":
            after = "active"
        elif child_state in {"queued", "drafting"}:
            after = "pending"
        else:
            after = before or "pending"
        if before != after:
            node["status"] = after
            node["updated_at"] = utc_now()
            changed = True
    return changed


def activate_child(sid: str, epic_id: str) -> dict[str, Any]:
    path = SPRINTS_DIR / f"{sid}.status.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"id": sid, "sprint_id": sid}
    before = dict(data)
    data.update(
        {
            "status": "active",
            "phase": "prd_ready",
            "handoff_to": "planner",
            "target_role": "planner",
            "epic_id": epic_id,
            "updated_at": utc_now(),
        }
    )
    hist = data.setdefault("history", [])
    if isinstance(hist, list):
        hist.append({"ts": utc_now(), "event": "epic_activate_ready_child", "by": "epic_decomposer", "epic_id": epic_id})
    write_json(path, data)
    return {"sid": sid, "before": before.get("status"), "after": "active"}


def blocked_child_graph_prerequisites(sid: str) -> list[dict[str, Any]]:
    graph_path = SPRINTS_DIR / f"{sid}.task_graph.json"
    if not graph_path.exists():
        return []
    try:
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [{"requirement": "task_graph", "reason": "parse_error", "error": str(exc)}]
    return iter_blocked(graph, SPRINTS_DIR)


def activate_ready(args: argparse.Namespace) -> dict[str, Any]:
    epic_id = args.epic_id
    graph_path = SPRINTS_DIR / f"{epic_id}.task_graph.json"
    if not graph_path.exists():
        raise SystemExit(f"missing epic task graph: {graph_path}")
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    graph_changed = sync_graph_from_children(graph)
    node_by_id = {str(n.get("id")): n for n in graph.get("nodes", []) if n.get("id")}
    activated: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for node_id in sorted(node_by_id):
        node = node_by_id[node_id]
        sid = str(node.get("child_sprint_id") or "")
        if not sid:
            continue
        status_path = SPRINTS_DIR / f"{sid}.status.json"
        st = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
        if str(st.get("status", "")).lower() not in {"queued", "drafting"}:
            continue
        deps = [str(d) for d in node.get("depends_on", [])]
        missing = []
        for dep in deps:
            dep_sid = str(node_by_id.get(dep, {}).get("child_sprint_id") or "")
            if dep_sid and not child_passed(dep_sid):
                missing.append(dep_sid)
        child_graph_blocked = blocked_child_graph_prerequisites(sid)
        if missing:
            blocked.append({"sid": sid, "node_id": node_id, "blocked_by": missing})
            continue
        if child_graph_blocked:
            blocked.append({"sid": sid, "node_id": node_id, "blocked_by": child_graph_blocked})
            continue
        if len(activated) >= args.max:
            break
        if not args.dry_run:
            activated.append(activate_child(sid, epic_id))
            node["status"] = "active"
            node["updated_at"] = utc_now()
            graph_changed = True
        else:
            activated.append({"sid": sid, "after": "active", "dry_run": True})
    if graph_changed and not args.dry_run:
        write_json(graph_path, graph)
    return {"ok": True, "epic_id": epic_id, "activated": activated, "blocked": blocked, "graph_synced": graph_changed}


def validate_epic(args: argparse.Namespace) -> dict[str, Any]:
    epic_id = args.epic_id
    required = ["epic.md", "epic.json", "task_graph.json", "traceability.json"]
    missing = [name for name in required if not (SPRINTS_DIR / f"{epic_id}.{name}").exists()]
    meta = {}
    meta_path = SPRINTS_DIR / f"{epic_id}.epic.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    child_missing = []
    for sid in meta.get("child_sprints", []):
        for suffix in ("prd.md", "contract.md", "status.json"):
            if not (SPRINTS_DIR / f"{sid}.{suffix}").exists():
                child_missing.append(f"{sid}.{suffix}")
    return {"ok": not missing and not child_missing, "epic_id": epic_id, "missing": missing, "child_missing": child_missing}


def cmd_status(args: argparse.Namespace) -> dict[str, Any]:
    epics = []
    for path in sorted(SPRINTS_DIR.glob("epic-*.epic.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        meta = json.loads(path.read_text(encoding="utf-8"))
        children = []
        for sid in meta.get("child_sprints", []):
            st = {}
            sp = SPRINTS_DIR / f"{sid}.status.json"
            if sp.exists():
                st = json.loads(sp.read_text(encoding="utf-8"))
            children.append({"sid": sid, "status": st.get("status", "missing"), "phase": st.get("phase", "")})
        epics.append({"epic_id": meta.get("epic_id"), "title": meta.get("title"), "status": meta.get("status"), "children": children})
        if args.latest:
            break
    return {"ok": True, "epics": epics}


def print_payload(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(f"ok={str(payload.get('ok')).lower()}")
    for key, value in payload.items():
        if key == "ok":
            continue
        print(f"{key}: {value}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Solar Epic Decomposer")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_create = sub.add_parser("create", help="create epic + child PRDs/contracts/task graph")
    p_create.add_argument("--title", required=True)
    p_create.add_argument("--request", default="")
    p_create.add_argument("--request-file", default="")
    p_create.add_argument("--slug", default="")
    p_create.add_argument("--priority", default="P0")
    p_create.add_argument("--slices", type=int, default=len(DEFAULT_SLICES))
    p_create.add_argument("--activate-ready", action="store_true")
    p_create.add_argument("--dry-run", action="store_true")
    p_create.add_argument("--json", action="store_true")

    p_validate = sub.add_parser("validate", help="validate epic artifact completeness")
    p_validate.add_argument("epic_id")
    p_validate.add_argument("--json", action="store_true")

    p_activate = sub.add_parser("activate-ready", help="activate dependency-ready child sprints")
    p_activate.add_argument("epic_id")
    p_activate.add_argument("--max", type=int, default=2)
    p_activate.add_argument("--dry-run", action="store_true")
    p_activate.add_argument("--json", action="store_true")

    p_status = sub.add_parser("status", help="show epic status")
    p_status.add_argument("--latest", action="store_true")
    p_status.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    if args.cmd == "create":
        payload = create_epic(args)
    elif args.cmd == "validate":
        payload = validate_epic(args)
    elif args.cmd == "activate-ready":
        payload = activate_ready(args)
    elif args.cmd == "status":
        payload = cmd_status(args)
    else:  # pragma: no cover
        parser.error("unknown command")
    print_payload(payload, getattr(args, "json", False))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
