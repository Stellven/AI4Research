#!/usr/bin/env python3
"""Small event bridge for remote solar-harness sprint monitoring.

The bridge is intentionally file based: it runs on the remote executor host,
scans a task graph on a short interval, and appends compact JSON events when
state changes. A local Codex session can pull only the latest JSON/event tail
over SSH without keeping a long blocking monitor in the foreground.
"""
from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# Add sibling directory 'lib' to sys.path
try:
    script_dir = Path(__file__).resolve().parent
except NameError:
    script_dir = Path.cwd()
lib_dir = script_dir.parent / "lib"
if str(lib_dir) not in sys.path:
    sys.path.insert(0, str(lib_dir))

import operator_runtime
import multi_task_runner


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def graph_nodes(graph: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = graph.get("nodes") or []
    if isinstance(nodes, dict):
        return [node for node in nodes.values() if isinstance(node, dict)]
    if isinstance(nodes, list):
        return [node for node in nodes if isinstance(node, dict)]
    return []


def node_id(node: dict[str, Any]) -> str:
    return str(node.get("id") or node.get("node_id") or "N/A")


def node_status(node: dict[str, Any]) -> str:
    raw = node.get("status")
    if raw:
        return str(raw)
    meta = node.get("meta") if isinstance(node.get("meta"), dict) else {}
    return str(meta.get("status") or "pending")


def node_dependencies(node: dict[str, Any]) -> list[str]:
    for key in ("depends_on", "dependencies", "needs", "after"):
        raw = node.get(key)
        if isinstance(raw, list):
            return [str(item) for item in raw if str(item)]
        if isinstance(raw, str) and raw:
            return [raw]
    return []


def ready_nodes(nodes: list[dict[str, Any]]) -> list[str]:
    statuses = {node_id(node): node_status(node) for node in nodes}
    ready: list[str] = []
    for node in nodes:
        nid = node_id(node)
        if node_status(node) not in {"pending", "ready"}:
            continue
        deps = node_dependencies(node)
        if all(statuses.get(dep) == "passed" for dep in deps):
            ready.append(nid)
    return ready


def safe_tail(path: Path, limit: int = 1200) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        return text[-limit:]
    except Exception:
        return ""


def latest_task_for_node(run_dir: Path, sprint_id: str, node_id: str) -> dict[str, Any] | None:
    best: tuple[float, dict[str, Any]] | None = None
    for status_path in run_dir.glob("*/status.json"):
        data = load_json(status_path)
        if data.get("sprint_id") != sprint_id or data.get("node_id") != node_id:
            continue
        try:
            mtime = status_path.stat().st_mtime
        except Exception:
            mtime = 0
        data["_task_dir"] = str(status_path.parent)
        data["_output_tail"] = safe_tail(status_path.parent / "output.log", 1200)
        if best is None or mtime > best[0]:
            best = (mtime, data)
    return best[1] if best else None


def graph_node_status(graph_path: Path, node_id_value: str) -> str:
    graph = load_json(graph_path)
    for node in graph_nodes(graph):
        if node_id(node) == node_id_value:
            return node_status(node)
    return "N/A"


def tmux_windows(session: str) -> list[dict[str, str]]:
    try:
        out = subprocess.check_output(
            [
                "tmux",
                "list-windows",
                "-t",
                session,
                "-F",
                "#{window_name}\t#{window_id}\t#{window_active}\t#{pane_current_command}\t#{pane_dead}\t#{pane_pid}",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
    except Exception:
        return []
    rows: list[dict[str, str]] = []
    for line in out.splitlines():
        parts = line.split("\t")
        if not parts or not parts[0].strip():
            continue
        rows.append({
            "name": parts[0].strip(),
            "id": parts[1].strip() if len(parts) > 1 else "",
            "active": parts[2].strip() if len(parts) > 2 else "",
            "command": parts[3].strip() if len(parts) > 3 else "",
            "dead": parts[4].strip() if len(parts) > 4 else "",
            "pane_pid": parts[5].strip() if len(parts) > 5 else "",
        })
    return rows


def tmux_window_match(session: str, window: str) -> dict[str, str] | None:
    if not window:
        return None
    for row in tmux_windows(session):
        name = row.get("name") or ""
        wid = row.get("id") or ""
        # tmux may truncate long names for display/targets and allows duplicate
        # prefixes. Treat a long runner window as live if either side is a
        # prefix of the other, then use PID/dead state to classify it.
        if window in {name, wid} or name.startswith(window) or window.startswith(name):
            return row
    return None


def tmux_window_exists(session: str, window: str) -> bool:
    match = tmux_window_match(session, window)
    return bool(match and match.get("dead") != "1")


def summarize(graph_path: Path, run_dir: Path, stale_sec: int) -> dict[str, Any]:
    graph = load_json(graph_path)
    sprint_id = str(graph.get("sprint_id") or graph_path.name.replace(".task_graph.json", ""))
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    warnings: list[str] = []
    now_ts = time.time()

    nodes = graph_nodes(graph)
    for node in nodes:
        node_id_value = node_id(node)
        status = node_status(node)
        counts[status] = counts.get(status, 0) + 1
        task = latest_task_for_node(run_dir, sprint_id, node_id_value)
        active_task = str((task or {}).get("id") or "N/A")
        updated_at = str((task or {}).get("updated_at") or node.get("updated_at") or "N/A")
        blocker = "N/A"
        next_action = "wait"
        task_status = str((task or {}).get("status") or "N/A")
        output_tail = str((task or {}).get("_output_tail") or "")
        window = str((task or {}).get("window") or "")
        tmux_match = tmux_window_match(str((task or {}).get("session") or "solar-harness-multi-task"), window)
        tmux_live = bool(tmux_match and tmux_match.get("dead") != "1")
        age_s = None
        try:
            age_s = int(now_ts - dt.datetime.fromisoformat(updated_at.replace("Z", "+00:00")).timestamp())
        except Exception:
            pass

        if status in {"dispatched", "running"} and age_s is not None and age_s > stale_sec:
            blocker = f"stale>{stale_sec}s"
            next_action = "diagnose"
        elif status in {"dispatched", "running"} and task and not tmux_live:
            blocker = "tmux_window_missing"
            next_action = "safe-align-or-restart"
        elif status == "reviewing":
            handoff = Path(str((task or {}).get("handoff") or graph_path.with_name(f"{sprint_id}.{node_id}-handoff.md")))
            if handoff.exists() and handoff.stat().st_size > 200:
                next_action = "can-mark-passed"
            else:
                blocker = "handoff_missing_or_small"
                next_action = "inspect"
        elif status == "passed":
            next_action = "done"

        if blocker != "N/A":
            warnings.append(f"{node_id_value}:{blocker}")

        rows.append({
            "node": node_id_value,
            "status": status,
            "task_status": task_status,
            "active_task": active_task,
            "updated_at": updated_at,
            "blocker": blocker,
            "next_action": next_action,
            "tmux_live": tmux_live,
            "tmux_window": (tmux_match or {}).get("name") or "N/A",
            "tmux_pane_pid": (tmux_match or {}).get("pane_pid") or "N/A",
            "output_tail_hash": hashlib.sha256(output_tail.encode("utf-8")).hexdigest()[:12] if output_tail else "N/A",
            "task_type": node.get("task_type") or "N/A",
        })

    ready = ready_nodes(nodes)
    return {
        "schema": "solar.monitor_bridge.v1",
        "sprint_id": sprint_id,
        "graph": str(graph_path),
        "observed_at": now_iso(),
        "counts": counts,
        "ready": ready,
        "ready_count": len(ready),
        "warnings": warnings,
        "nodes": rows,
        "all_passed": bool(rows) and all(r["status"] == "passed" for r in rows),
    }


def active_task_rows(run_dir: Path, limit: int = 80, sprints_dir: Path | None = None) -> list[dict[str, Any]]:
    rows: list[tuple[float, dict[str, Any]]] = []
    for status_path in run_dir.glob("*/status.json"):
        data = load_json(status_path)
        if not data:
            continue
        try:
            mtime = status_path.stat().st_mtime
        except Exception:
            mtime = 0
        status = str(data.get("status") or "N/A").lower()
        graph_path = Path(str(data.get("graph") or ""))
        if not graph_path.exists() and sprints_dir:
            alt_path = sprints_dir / graph_path.name
            if alt_path.exists():
                graph_path = alt_path
        graph_status = graph_node_status(graph_path, str(data.get("node_id") or "")) if graph_path.exists() else str(data.get("graph_status") or "")
        effective_status = graph_status if graph_status not in {"", "N/A"} else status
        active = effective_status.lower() in {"dispatched", "running", "reviewing", "active"}
        if not active:
            continue
        session = str(data.get("session") or "solar-harness-multi-task")
        window = str(data.get("window") or "")
        match = tmux_window_match(session, window)
        rows.append((mtime, {
            "task": str(data.get("id") or status_path.parent.name),
            "status": str(data.get("status") or "N/A"),
            "graph_status": graph_status or "N/A",
            "effective_status": effective_status,
            "sprint_id": str(data.get("sprint_id") or "N/A"),
            "node_id": str(data.get("node_id") or "N/A"),
            "operator_id": str(data.get("operator_id") or "N/A"),
            "vendor": str(data.get("operator_vendor") or data.get("provider") or "N/A"),
            "model": str(data.get("operator_model") or data.get("model") or "N/A"),
            "role": str(data.get("role") or data.get("profile") or "N/A"),
            "window": window or "N/A",
            "tmux_live": bool(match and match.get("dead") != "1"),
            "tmux_window": (match or {}).get("name") or "N/A",
            "updated_at": str(data.get("updated_at") or "N/A"),
        }))
    return [row for _, row in sorted(rows, key=lambda item: item[0], reverse=True)[:limit]]


def summarize_all(sprints_dir: Path, run_dir: Path, stale_sec: int, include_passed_limit: int) -> dict[str, Any]:
    graph_paths = sorted(sprints_dir.glob("*.task_graph.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    sprint_rows: list[dict[str, Any]] = []
    aggregate_counts: Counter[str] = Counter()
    warning_rows: list[dict[str, str]] = []
    passed_included = 0

    ready_by_task_type: Counter[str] = Counter()
    blocked_by_reason: Counter[str] = Counter()

    for graph_path in graph_paths:
        snapshot = summarize(graph_path, run_dir, stale_sec)
        all_passed = bool(snapshot.get("all_passed"))
        if not all_passed:
            ready_ids = set(snapshot.get("ready") or [])
            for n in snapshot.get("nodes") or []:
                node_id_val = n.get("node")
                if node_id_val in ready_ids:
                    ttype = n.get("task_type") or "N/A"
                    ready_by_task_type[ttype] += 1
                
                blocker = n.get("blocker") or "N/A"
                if blocker != "N/A":
                    blocked_by_reason[blocker] += 1

        if all_passed:
            if passed_included >= include_passed_limit:
                continue
            passed_included += 1
        counts = dict(snapshot.get("counts") or {})
        aggregate_counts.update(counts)
        warnings = [str(item) for item in snapshot.get("warnings") or []]
        for warning in warnings:
            warning_rows.append({"sprint_id": str(snapshot.get("sprint_id") or "N/A"), "warning": warning})
        sprint_rows.append({
            "sprint_id": str(snapshot.get("sprint_id") or "N/A"),
            "graph": str(graph_path),
            "counts": counts,
            "ready": snapshot.get("ready") or [],
            "ready_count": int(snapshot.get("ready_count") or 0),
            "warnings": warnings,
            "all_passed": all_passed,
            "updated_at": dt.datetime.fromtimestamp(graph_path.stat().st_mtime, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })

    tasks = active_task_rows(run_dir, sprints_dir=sprints_dir)
    operator_counts = Counter(str(task.get("operator_id") or "N/A") for task in tasks)
    vendor_counts = Counter(str(task.get("vendor") or "N/A") for task in tasks)
    
    # Load physical operators registry config
    registry = operator_runtime.load_registry()
    operators = registry.get("operators", {})
    
    operator_fleet = {}
    for op_id, op_cfg in operators.items():
        state = operator_runtime.get_operator_runtime_state(op_id)
        # Count active tasks that match this operator_id
        active_count = sum(1 for task in tasks if task.get("operator_id") == op_id)
        operator_fleet[op_id] = {
            "display_name": op_cfg.get("display_name", "N/A"),
            "role": op_cfg.get("role", "N/A"),
            "profile": op_cfg.get("profile", "N/A"),
            "provider": op_cfg.get("provider", "N/A"),
            "vendor": op_cfg.get("vendor", "N/A"),
            "enabled": op_cfg.get("enabled", True),
            "runtime_state": state,
            "active_task_count": active_count,
        }
        
    operator_class_counts = Counter(str(task.get("role") or "N/A") for task in tasks)

    # Provider and model counts calculation
    provider_list = []
    model_list = []
    for task in tasks:
        op_id = task.get("operator_id")
        provider = None
        model = None
        if op_id and op_id in operators:
            op_cfg = operators[op_id]
            provider = op_cfg.get("provider")
            model = op_cfg.get("model")
            
        if provider:
            provider_list.append(str(provider).lower())
        else:
            provider_list.append(str(task.get("vendor") or "N/A"))
            
        if model:
            model_list.append(str(model))
        else:
            model_list.append(str(task.get("model") or "N/A"))
    provider_counts = Counter(provider_list)
    model_counts = Counter(model_list)

    # Fallback ladder health calculation
    fallback_ladder_health = {}
    for ttype, ladder in multi_task_runner.NORM_FALLBACK_LADDERS.items():
        results = []
        for op_id in ladder:
            op_cfg = operators.get(op_id)
            if not op_cfg:
                results.append((op_id, False, False))
                continue
            
            # Construct operator spec
            operator_spec = multi_task_runner._operator_ref(op_id, dict(op_cfg))
            
            # Check dynamic state
            dyn_state = operator_runtime.get_operator_runtime_state(op_id)
            is_busy = dyn_state in {"leased", "running", "draining", "cooldown"}
            
            # Check dispatchable
            dispatchable, _ = multi_task_runner.operator_dispatchable(operator_spec)
            is_healthy = dispatchable or is_busy
            
            results.append((op_id, is_healthy, is_busy))
            
        if not results:
            status = "unavailable"
        elif not any(h for op, h, b in results):
            status = "unavailable"
        elif all(b for op, h, b in results if h):
            status = "busy"
        elif results[0][1] and not results[0][2]:
            status = "ok"
        elif any(h_back and not b_back for op_back, h_back, b_back in results[1:]):
            status = "degraded"
        else:
            status = "unavailable"
            
        fallback_ladder_health[ttype] = status

    return {
        "schema": "solar.monitor_bridge.global.v1",
        "observed_at": now_iso(),
        "sprints_dir": str(sprints_dir),
        "run_dir": str(run_dir),
        "sprint_count": len(sprint_rows),
        "active_sprint_count": sum(1 for row in sprint_rows if not row.get("all_passed")),
        "active_task_count": len(tasks),
        "ready_total": sum(int(row.get("ready_count") or 0) for row in sprint_rows if not row.get("all_passed")),
        "counts": dict(sorted(aggregate_counts.items())),
        "operator_counts": dict(sorted(operator_counts.items())),
        "vendor_counts": dict(sorted(vendor_counts.items())),
        "operator_fleet": dict(sorted(operator_fleet.items())),
        "operator_class_counts": dict(sorted(operator_class_counts.items())),
        "provider_counts": dict(sorted(provider_counts.items())),
        "model_counts": dict(sorted(model_counts.items())),
        "fallback_ladder_health": dict(sorted(fallback_ladder_health.items())),
        "ready_by_task_type": dict(sorted(ready_by_task_type.items())),
        "blocked_by_reason": dict(sorted(blocked_by_reason.items())),
        "warnings": warning_rows,
        "sprints": sprint_rows,
        "active_tasks": tasks,
    }



def digest(snapshot: dict[str, Any]) -> str:
    if snapshot.get("schema") == "solar.monitor_bridge.global.v1":
        compact = {
            "counts": snapshot.get("counts"),
            "warnings": snapshot.get("warnings"),
            "operator_fleet": snapshot.get("operator_fleet"),
            "operator_class_counts": snapshot.get("operator_class_counts"),
            "provider_counts": snapshot.get("provider_counts"),
            "model_counts": snapshot.get("model_counts"),
            "fallback_ladder_health": snapshot.get("fallback_ladder_health"),
            "ready_by_task_type": snapshot.get("ready_by_task_type"),
            "blocked_by_reason": snapshot.get("blocked_by_reason"),
            "sprints": [

                {
                    "sprint_id": s.get("sprint_id"),
                    "counts": s.get("counts"),
                    "ready": s.get("ready"),
                    "warnings": s.get("warnings"),
                    "all_passed": s.get("all_passed"),
                }
                for s in snapshot.get("sprints", [])
            ],
            "active_tasks": [
                {
                    "task": t.get("task"),
                    "status": t.get("status"),
                    "sprint_id": t.get("sprint_id"),
                    "node_id": t.get("node_id"),
                    "operator_id": t.get("operator_id"),
                    "tmux_live": t.get("tmux_live"),
                }
                for t in snapshot.get("active_tasks", [])
            ],
        }
        return hashlib.sha256(json.dumps(compact, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    compact = {
        "counts": snapshot.get("counts"),
        "warnings": snapshot.get("warnings"),
        "nodes": [
            {
                "node": n.get("node"),
                "status": n.get("status"),
                "task_status": n.get("task_status"),
                "active_task": n.get("active_task"),
                "blocker": n.get("blocker"),
                "next_action": n.get("next_action"),
                "tail": n.get("output_tail_hash"),
            }
            for n in snapshot.get("nodes", [])
        ],
    }
    return hashlib.sha256(json.dumps(compact, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def append_event(events_path: Path, event: dict[str, Any]) -> None:
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with events_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def write_latest(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def run(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).expanduser()
    out_dir = Path(args.out_dir).expanduser()
    latest_path = out_dir / f"{args.name}.latest.json"
    events_path = out_dir / f"{args.name}.events.jsonl"
    state_path = out_dir / f"{args.name}.state.json"
    previous = load_json(state_path).get("digest")

    while True:
        if args.all:
            snapshot = summarize_all(Path(args.sprints_dir).expanduser(), run_dir, int(args.stale_sec), int(args.include_passed_limit))
        else:
            if not args.graph:
                raise SystemExit("--graph is required unless --all is set")
            snapshot = summarize(Path(args.graph).expanduser(), run_dir, int(args.stale_sec))
        current = digest(snapshot)
        snapshot["digest"] = current
        snapshot["events_path"] = str(events_path)
        write_latest(latest_path, snapshot)
        if current != previous:
            append_event(events_path, {"ts": now_iso(), "type": "snapshot_changed", "digest": current, "snapshot": snapshot})
            write_latest(state_path, {"digest": current, "updated_at": now_iso()})
            previous = current
        if args.once or (not args.all and snapshot.get("all_passed")):
            return 0
        time.sleep(float(args.interval))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph")
    parser.add_argument("--all", action="store_true", help="scan all task graphs and active multi-task records")
    parser.add_argument("--name", required=True)
    parser.add_argument("--run-dir", default=str(Path.home() / ".solar" / "harness" / "run" / "multi-task"))
    parser.add_argument("--sprints-dir", default=str(Path.home() / ".solar" / "harness" / "sprints"))
    parser.add_argument("--out-dir", default=str(Path.home() / ".solar" / "harness" / "run" / "monitor-bridge"))
    parser.add_argument("--interval", type=float, default=15)
    parser.add_argument("--stale-sec", type=int, default=300)
    parser.add_argument("--include-passed-limit", type=int, default=5)
    parser.add_argument("--once", action="store_true")
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
