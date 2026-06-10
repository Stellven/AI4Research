#!/usr/bin/env python3
"""Remote Mac mini multi-task monitor for Solar Harness."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shlex
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

DEFAULT_HOST = "solar@example-host"
REMOTE_HARNESS = "~/.solar/harness"
SESSION = "solar-harness-multi-task"
ACTIVE_STATUSES = {"dispatched", "running"}
TERMINAL_STATUSES = {"completed", "failed", "failed_missing_handoff", "failed_launch", "cancelled", "dry_run"}
DONE_NODE_STATUSES = {"passed", "reviewing", "completed", "done"}
PENDING_NODE_STATUSES = {"", "pending", "ready", "queued"}


REMOTE_COLLECTOR = r'''
import json, os, pathlib, subprocess, sys, time, traceback

HOME = pathlib.Path.home()
HARNESS = pathlib.Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))
RUN_DIR = HARNESS / "run" / "multi-task"
SPRINTS_DIR = HARNESS / "sprints"
SESSION = os.environ.get("SOLAR_HARNESS_MULTI_TASK_SESSION", "solar-harness-multi-task")

def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        return {"_read_error": str(exc), "_path": str(path)}

def tail(path, limit=80):
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-limit:])
    except Exception as exc:
        return f"N/A: {exc}"

def run(cmd, timeout=8):
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
        return {"rc": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
    except Exception as exc:
        return {"rc": 124, "stdout": "", "stderr": str(exc)}

def list_windows():
    proc = run(["tmux", "list-windows", "-t", SESSION, "-F", "#{window_name}"], timeout=4)
    if proc["rc"] != 0:
        return []
    return [line.strip() for line in proc["stdout"].splitlines() if line.strip()]

def node_status(graph, node):
    nid = str(node.get("id") or "")
    inline = str(node.get("status") or "").strip()
    result = graph.get("node_results") or {}
    result_status = ""
    if isinstance(result, dict) and isinstance(result.get(nid), dict):
        result_status = str(result[nid].get("status") or "").strip()
    return result_status or inline or "pending"

def graph_summary(path):
    graph = read_json(path)
    nodes = graph.get("nodes") if isinstance(graph, dict) else []
    if not isinstance(nodes, list):
        nodes = []
    statuses = {}
    node_rows = []
    done = {"passed", "reviewing", "completed", "done"}
    ready = []
    node_map = {str(n.get("id") or ""): n for n in nodes if isinstance(n, dict)}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        nid = str(node.get("id") or "")
        status = node_status(graph, node)
        statuses[status] = statuses.get(status, 0) + 1
        deps = [str(x) for x in (node.get("depends_on") or node.get("depends") or [])]
        node_rows.append({"id": nid, "status": status, "depends_on": deps, "goal": str(node.get("goal") or node.get("title") or "")[:180]})
    status_by_id = {row["id"]: row["status"] for row in node_rows}
    for row in node_rows:
        if row["status"] in done or row["status"] in {"running", "dispatched", "failed", "cancelled"}:
            continue
        if all(status_by_id.get(dep, "pending") in done for dep in row["depends_on"]):
            ready.append(row["id"])
    return {
        "path": str(path),
        "sprint_id": str(graph.get("sprint_id") or path.stem.replace(".task_graph", "")) if isinstance(graph, dict) else path.stem,
        "title": str(graph.get("title") or "") if isinstance(graph, dict) else "",
        "node_count": len(node_rows),
        "statuses": statuses,
        "ready_nodes": ready,
        "nodes": node_rows,
        "doctor": run(["python3", str(HARNESS / "lib" / "graph_scheduler.py"), "doctor", "--graph", str(path)], timeout=10),
    }

def main():
    windows = list_windows()
    tasks = []
    for status_path in sorted(RUN_DIR.glob("*/status.json")):
        status = read_json(status_path)
        task_dir = status_path.parent
        log_path = task_dir / "output.log"
        try:
            stat = log_path.stat()
            log_size, log_mtime = stat.st_size, stat.st_mtime
        except FileNotFoundError:
            log_size, log_mtime = 0, 0
        window = str(status.get("window") or "")
        tasks.append({
            "task_dir": str(task_dir),
            "status_path": str(status_path),
            "status": status,
            "output_tail": tail(log_path),
            "output_size": log_size,
            "output_mtime_epoch": log_mtime,
            "tmux_window_exists": bool(window and window in windows),
        })
    graphs = [graph_summary(path) for path in sorted(SPRINTS_DIR.glob("*.task_graph.json"))]
    mt_json = run([str(HARNESS / "solar-harness.sh"), "multi-task", "status", "--json"], timeout=30)
    mt_snapshot = {}
    if mt_json["rc"] == 0:
        try:
            mt_snapshot = json.loads(mt_json["stdout"] or "{}")
        except Exception:
            mt_snapshot = {}
    mt = run([str(HARNESS / "solar-harness.sh"), "multi-task", "status", "--no-clear"], timeout=20)
    print(json.dumps({
        "ok": True,
        "host": os.uname().nodename,
        "harness_dir": str(HARNESS),
        "checked_at_epoch": time.time(),
        "session": SESSION,
        "tmux_windows": windows,
        "tasks": tasks,
        "graphs": graphs,
        "multi_task_snapshot": mt_snapshot,
        "multi_task_status_json": mt_json,
        "multi_task_status": mt,
    }, ensure_ascii=False))

try:
    main()
except Exception as exc:
    print(json.dumps({"ok": False, "error": str(exc), "traceback": traceback.format_exc()}, ensure_ascii=False))
    sys.exit(1)
'''


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def parse_time(value: Any) -> dt.datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        try:
            return dt.datetime.fromtimestamp(float(value), tz=dt.timezone.utc)
        except Exception:
            return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def tail_text(path: Path, limit: int = 80) -> str:
    if not path.exists():
        return "N/A"
    return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:])


def collect_fixture(root: Path) -> dict[str, Any]:
    run_dir = root / "run" / "multi-task"
    sprints_dir = root / "sprints"
    windows_path = root / "tmux_windows.json"
    windows = read_json(windows_path) if windows_path.exists() else []
    tasks = []
    for status_path in sorted(run_dir.glob("*/status.json")):
        status = read_json(status_path)
        task_dir = status_path.parent
        log_path = task_dir / "output.log"
        stat = log_path.stat() if log_path.exists() else None
        window = str(status.get("window") or "")
        tasks.append({
            "task_dir": str(task_dir),
            "status_path": str(status_path),
            "status": status,
            "output_tail": tail_text(log_path),
            "output_size": stat.st_size if stat else 0,
            "output_mtime_epoch": stat.st_mtime if stat else 0,
            "tmux_window_exists": bool(window and window in windows),
        })
    graphs = [summarize_graph(path) for path in sorted(sprints_dir.glob("*.task_graph.json"))]
    return {
        "ok": True,
        "host": "fixture",
        "harness_dir": str(root),
        "checked_at_epoch": time.time(),
        "session": SESSION,
        "tmux_windows": windows,
        "tasks": tasks,
        "graphs": graphs,
        "multi_task_status": {"rc": 0, "stdout": "fixture", "stderr": ""},
    }


def run_ssh_json(host: str, timeout: int) -> dict[str, Any]:
    proc = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={timeout}", host, "python3", "-"],
        input=REMOTE_COLLECTOR,
        text=True,
        capture_output=True,
        timeout=max(timeout + 30, 45),
    )
    if proc.returncode != 0:
        return {"ok": False, "error": "ssh_collect_failed", "rc": proc.returncode, "stdout": proc.stdout[-2000:], "stderr": proc.stderr[-4000:]}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"invalid_remote_json: {exc}", "stdout": proc.stdout[-4000:], "stderr": proc.stderr[-4000:]}


def node_status(graph: dict[str, Any], node: dict[str, Any]) -> str:
    node_id = str(node.get("id") or "")
    results = graph.get("node_results") or {}
    if isinstance(results, dict) and isinstance(results.get(node_id), dict):
        value = str(results[node_id].get("status") or "").strip()
        if value:
            return value
    return str(node.get("status") or "pending").strip() or "pending"


def summarize_graph(path: Path) -> dict[str, Any]:
    graph = read_json(path)
    nodes = graph.get("nodes") if isinstance(graph, dict) else []
    if not isinstance(nodes, list):
        nodes = []
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    drift_issues: list[dict[str, Any]] = []
    node_results = graph.get("node_results") if isinstance(graph, dict) else {}
    if not isinstance(node_results, dict):
        node_results = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        status = node_status(graph, node)
        inline_status = str(node.get("status") or "").strip()
        result = node_results.get(str(node.get("id") or ""))
        result_status = str(result.get("status") or "").strip() if isinstance(result, dict) else ""
        if inline_status and result_status and inline_status != result_status:
            drift_issues.append({"type": "fixture_state_drift", "node_id": str(node.get("id") or ""), "inline_status": inline_status, "node_result_status": result_status})
        counts[status] = counts.get(status, 0) + 1
        rows.append({
            "id": str(node.get("id") or ""),
            "status": status,
            "depends_on": [str(x) for x in (node.get("depends_on") or node.get("depends") or [])],
            "goal": str(node.get("goal") or node.get("title") or "")[:180],
        })
    by_id = {row["id"]: row["status"] for row in rows}
    ready = [
        row["id"]
        for row in rows
        if row["status"] not in DONE_NODE_STATUSES | {"running", "dispatched", "failed", "cancelled"}
        and all(by_id.get(dep, "pending") in DONE_NODE_STATUSES for dep in row["depends_on"])
    ]
    return {
        "path": str(path),
        "sprint_id": str(graph.get("sprint_id") or path.name.replace(".task_graph.json", "")) if isinstance(graph, dict) else path.stem,
        "title": str(graph.get("title") or "") if isinstance(graph, dict) else "",
        "node_count": len(rows),
        "statuses": counts,
        "ready_nodes": ready,
        "nodes": rows,
        "doctor": {"rc": 0, "stdout": json.dumps({"ok": True, "issues": drift_issues, "repaired": False}, ensure_ascii=False), "stderr": ""},
    }


def graph_doctor_issues(graph: dict[str, Any]) -> list[dict[str, Any]]:
    raw = ((graph.get("doctor") or {}).get("stdout") or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except Exception:
        return [{"type": "graph_doctor_unparseable", "detail": raw[:300]}]
    issues = parsed.get("issues") or []
    return issues if isinstance(issues, list) else []


def analyze(snapshot: dict[str, Any], args: argparse.Namespace, checked_at: dt.datetime) -> dict[str, Any]:
    stale_seconds = int(args.stale_minutes * 60)
    active_tasks = []
    terminal_tasks = []
    findings: list[dict[str, Any]] = []
    by_graph_node: dict[tuple[str, str], dict[str, Any]] = {}

    for task in snapshot.get("tasks") or []:
        status = task.get("status") or {}
        task_status = str(status.get("status") or "unknown")
        task_id = str(status.get("id") or Path(str(task.get("task_dir") or "")).name)
        graph = str(status.get("graph") or "")
        node_id = str(status.get("node_id") or "")
        if graph and node_id:
            by_graph_node[(graph, node_id)] = task
        if task_status in ACTIVE_STATUSES:
            active_tasks.append(task)
        if task_status in TERMINAL_STATUSES:
            terminal_tasks.append(task)
        updated = parse_time(status.get("updated_at") or status.get("started_at"))
        age = int((checked_at - updated).total_seconds()) if updated else None
        if task_status in ACTIVE_STATUSES and (age is None or age > stale_seconds):
            findings.append({"severity": "error", "type": "stale_task", "task_id": task_id, "sprint_id": status.get("sprint_id"), "node_id": node_id, "graph": graph, "age_seconds": age, "status": task_status})
        if task_status in ACTIVE_STATUSES and not bool(task.get("tmux_window_exists")):
            findings.append({"severity": "error", "type": "missing_tmux_window", "task_id": task_id, "sprint_id": status.get("sprint_id"), "node_id": node_id, "graph": graph, "window": status.get("window")})
        log_mtime = parse_time(task.get("output_mtime_epoch"))
        log_age = int((checked_at - log_mtime).total_seconds()) if log_mtime else None
        if task_status in ACTIVE_STATUSES and (log_age is None or log_age > stale_seconds):
            findings.append({"severity": "warn", "type": "stale_output_log", "task_id": task_id, "sprint_id": status.get("sprint_id"), "node_id": node_id, "graph": graph, "age_seconds": log_age, "output_size": task.get("output_size")})

    active_workers = len(active_tasks)
    integrated_monitor = ((snapshot.get("multi_task_snapshot") or {}).get("monitor") or {})
    for item in integrated_monitor.get("findings") or []:
        severity = str(item.get("severity") or "warn")
        ftype = str(item.get("type") or "multi_task_monitor")
        findings.append({
            **item,
            "severity": severity if severity in {"ok", "warn", "error"} else "warn",
            "type": f"multi_task_{ftype}" if not ftype.startswith("multi_task_") else ftype,
            "source": "multi-task status --json",
        })
    for graph in snapshot.get("graphs") or []:
        ready = graph.get("ready_nodes") or []
        if ready and active_workers == 0:
            findings.append({"severity": "warn", "type": "ready_idle_graph", "graph": graph.get("path"), "sprint_id": graph.get("sprint_id"), "ready_nodes": ready})
        issues = graph_doctor_issues(graph)
        if issues:
            findings.append({"severity": "warn", "type": "graph_state_drift", "graph": graph.get("path"), "sprint_id": graph.get("sprint_id"), "issues": issues[:5]})
        for node in graph.get("nodes") or []:
            node_id = str(node.get("id") or "")
            task = by_graph_node.get((str(graph.get("path") or ""), node_id))
            if not task:
                continue
            tstatus = str((task.get("status") or {}).get("status") or "")
            nstatus = str(node.get("status") or "")
            if tstatus == "completed" and nstatus not in DONE_NODE_STATUSES:
                findings.append({"severity": "warn", "type": "terminal_status_misaligned", "graph": graph.get("path"), "sprint_id": graph.get("sprint_id"), "node_id": node_id, "task_status": tstatus, "node_status": nstatus, "target_status": "reviewing"})
            if tstatus.startswith("failed") and nstatus != "failed":
                findings.append({"severity": "warn", "type": "terminal_status_misaligned", "graph": graph.get("path"), "sprint_id": graph.get("sprint_id"), "node_id": node_id, "task_status": tstatus, "node_status": nstatus, "target_status": "failed"})

    worst = "ok"
    if any(f["severity"] == "error" for f in findings):
        worst = "error"
    elif any(f["severity"] == "warn" for f in findings):
        worst = "warn"
    return {
        "status": worst,
        "active_workers": active_workers,
        "task_count": len(snapshot.get("tasks") or []),
        "graph_count": len(snapshot.get("graphs") or []),
        "terminal_tasks": len(terminal_tasks),
        "integrated_monitor": {
            "status": integrated_monitor.get("status", "N/A"),
            "data_source": integrated_monitor.get("data_source", "N/A"),
            "finding_count": len(integrated_monitor.get("findings") or []),
        },
        "findings": findings,
    }


def safe_actions(analysis: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    remote_cd = "cd ~/.solar/harness"
    for finding in analysis.get("findings") or []:
        ftype = finding.get("type")
        graph = str(finding.get("graph") or "")
        if ftype == "ready_idle_graph" and graph:
            cmd = f"{remote_cd} && python3 lib/multi_task_runner.py start --graph {shlex.quote(graph)} --once --no-clear"
            key = (ftype, graph, cmd)
            if key not in seen:
                actions.append({"type": "start_ready_graph", "allowed": True, "graph": graph, "command": cmd, "reason": "ready 节点存在且 active_workers=0"})
                seen.add(key)
        elif ftype == "graph_state_drift" and graph:
            cmd = f"{remote_cd} && python3 lib/graph_scheduler.py doctor --graph {shlex.quote(graph)} --repair --in-place"
            key = (ftype, graph, cmd)
            if key not in seen:
                actions.append({"type": "repair_graph_drift", "allowed": True, "graph": graph, "command": cmd, "reason": "graph inline/node_results 状态漂移"})
                seen.add(key)
        elif ftype == "terminal_status_misaligned" and graph:
            node = str(finding.get("node_id") or "")
            target = str(finding.get("target_status") or "")
            if node and target in {"reviewing", "failed"}:
                note = "monitor terminal task status alignment"
                cmd = f"{remote_cd} && python3 lib/graph_scheduler.py mark --graph {shlex.quote(graph)} --node {shlex.quote(node)} --status {shlex.quote(target)} --note {shlex.quote(note)} --in-place"
                key = (ftype, graph, cmd)
                if key not in seen:
                    actions.append({"type": "align_terminal_status", "allowed": True, "graph": graph, "node_id": node, "command": cmd, "reason": "terminal task 与 graph 节点状态不一致"})
                    seen.add(key)
    return actions


def run_remote_action(host: str, command: str, timeout: int) -> dict[str, Any]:
    proc = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={timeout}", host, "bash -lc " + shlex.quote(command)],
        text=True,
        capture_output=True,
        timeout=max(timeout + 60, 90),
    )
    return {"rc": proc.returncode, "stdout": proc.stdout[-3000:], "stderr": proc.stderr[-3000:]}


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def compact_status(status: dict[str, Any]) -> str:
    keys = ["id", "status", "sprint_id", "node_id", "graph", "window", "started_at", "updated_at", "exit_code"]
    return json.dumps({k: status.get(k) for k in keys if k in status}, ensure_ascii=False, indent=2)


def matching_graph(snapshot: dict[str, Any], graph_path: str) -> dict[str, Any] | None:
    for graph in snapshot.get("graphs") or []:
        if str(graph.get("path") or "") == graph_path:
            return graph
    return None


def create_artifacts(snapshot: dict[str, Any], analysis: dict[str, Any], args: argparse.Namespace, checked_at: dt.datetime) -> dict[str, Any]:
    dead = [f for f in analysis.get("findings") or [] if f.get("type") in {"stale_task", "missing_tmux_window", "stale_output_log"}]
    if not dead:
        return {}
    base = Path(args.local_harness_dir).expanduser()
    stamp = checked_at.strftime("%Y%m%dT%H%M%SZ")
    first = dead[0]
    sid = str(first.get("sprint_id") or "unknown-sprint")
    node = str(first.get("node_id") or "unknown-node")
    safe_sid = re.sub(r"[^A-Za-z0-9_.-]+", "-", sid)[:80] or "unknown-sprint"
    draft_id = f"{safe_sid}.monitor-deadlock-{stamp}"
    report_path = base / "monitor-reports" / f"{stamp}-mac-mini-deadlock.md"
    draft_base = base / "monitor-drafts"
    prd_path = draft_base / f"{draft_id}.prd.md"
    contract_path = draft_base / f"{draft_id}.contract.md"
    graph_path = draft_base / f"{draft_id}.task_graph.json"

    task = None
    for item in snapshot.get("tasks") or []:
        status = item.get("status") or {}
        if str(status.get("id") or "") == str(first.get("task_id") or ""):
            task = item
            break
    if task is None and snapshot.get("tasks"):
        task = snapshot["tasks"][0]
    status = (task or {}).get("status") or {}
    graph = matching_graph(snapshot, str(first.get("graph") or ""))
    graph_nodes = (graph or {}).get("nodes") or []
    root_cause = "active task 已超过阈值未更新，或 tmux window 缺失，multi-task 状态与实际执行面可能漂移。"
    minimal_fix = f"先复现 task={first.get('task_id')} node={node} 的状态同步路径，再修复 worker/window/status graph 对齐。"
    output_tail = str((task or {}).get("output_tail") or "N/A")[-6000:]

    report = f"""# Mac mini multi-task 僵死巡检报告

- checked_at: {iso(checked_at)}
- host: {args.host}
- status: {analysis.get("status")}
- task_id: {first.get("task_id")}
- sprint_id: {sid}
- node_id: {node}

## 当前问题
{root_cause}

## status.json 摘要
```json
{compact_status(status)}
```

## output.log tail
```text
{output_tail}
```

## graph 节点状态
```json
{json.dumps(graph_nodes, ensure_ascii=False, indent=2)[:10000]}
```

## 推测根因
{root_cause}

## 最小修复节点
{minimal_fix}

## 下一步
审阅本地草案；确认后再同步到 Mac mini sprints 并启动 multi-task。
"""
    prd = f"""# PRD: Mac mini multi-task 僵死修复

## 背景
monitor 在 {iso(checked_at)} 发现 Mac mini multi-task 僵死/漂移风险。

## 目标
- 修复 task/window/status graph 同步路径。
- 保证僵死任务可被安全识别并恢复调度。
- 不 kill 用户进程，不删除 task 目录。

## 关键证据
- task_id: {first.get("task_id")}
- sprint_id: {sid}
- node_id: {node}
- finding: {first.get("type")}

## 验收
- stale running task 可被检测。
- completed/failed task 状态能对齐 graph。
- ready 节点且 worker 空闲时可安全启动一次 scheduler。
"""
    contract = f"""# Contract: Mac mini multi-task deadlock fix

## Scope
- Read: status.json, output.log, task_graph.json, tmux window state.
- Write: only graph/status repair code and tests after review.
- Forbidden: kill tmux window, delete task dir, rewrite user task output.

## Evidence
- task_id: {first.get("task_id")}
- sprint_id: {sid}
- node_id: {node}

## Minimum Fix Node
{minimal_fix}
"""
    task_graph = {
        "sprint_id": draft_id,
        "title": "Mac mini multi-task deadlock fix draft",
        "version": 1,
        "nodes": [
            {
                "id": "B1",
                "goal": "Analyze stale task evidence and reproduce status/window/graph drift.",
                "depends_on": [],
                "read_scope": ["~/.solar/harness/run/multi-task/", "~/.solar/harness/sprints/"],
                "write_scope": [str(draft_base)],
                "acceptance": ["root cause is tied to a concrete state transition"],
                "preferred_model": "sonnet",
            },
            {
                "id": "B2",
                "goal": "Implement the minimum fix for multi-task state synchronization.",
                "depends_on": ["B1"],
                "read_scope": ["harness/lib/multi_task_runner.py", "harness/lib/graph_scheduler.py"],
                "write_scope": ["harness/lib/", "harness/tests/"],
                "acceptance": ["fixture regression prevents recurrence", "no destructive recovery action is introduced"],
                "preferred_model": "sonnet",
            },
            {
                "id": "B3",
                "goal": "Verify monitor detects and safely advances the repaired state.",
                "depends_on": ["B2"],
                "read_scope": ["~/.solar/harness/monitor-reports/", "~/.solar/harness/monitor-drafts/"],
                "write_scope": ["~/.solar/harness/reports/"],
                "acceptance": ["monitor --json is ok after repair", "monitor --apply --dry-run lists only allowed commands"],
                "preferred_model": "sonnet",
            },
        ],
        "node_results": {},
        "source": "solar-harness monitor draft; not dispatched",
    }
    write_text(report_path, report)
    write_text(prd_path, prd)
    write_text(contract_path, contract)
    write_json(graph_path, task_graph)
    return {
        "report": str(report_path),
        "prd": str(prd_path),
        "contract": str(contract_path),
        "task_graph": str(graph_path),
    }


def width(text: Any) -> int:
    total = 0
    for ch in str(text):
        total += 2 if unicodedata.east_asian_width(ch) in {"W", "F"} else 1
    return total


def pad(text: Any, size: int) -> str:
    value = str(text)
    return value + " " * max(0, size - width(value))


def table(headers: list[str], rows: list[list[Any]]) -> str:
    data = [[str(x) for x in row] for row in rows]
    widths = [width(h) for h in headers]
    for row in data:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], min(width(cell), 64))
    top = "┌" + "┬".join("─" * (w + 2) for w in widths) + "┐"
    mid = "├" + "┼".join("─" * (w + 2) for w in widths) + "┤"
    bottom = "└" + "┴".join("─" * (w + 2) for w in widths) + "┘"
    out = [top, "│ " + " │ ".join(pad(h, widths[i]) for i, h in enumerate(headers)) + " │", mid]
    for row in data:
        clipped = [(cell[:61] + "...") if width(cell) > 64 else cell for cell in row]
        out.append("│ " + " │ ".join(pad(clipped[i], widths[i]) for i in range(len(headers))) + " │")
    out.append(bottom)
    return "\n".join(out)


def render_human(snapshot: dict[str, Any], analysis: dict[str, Any], actions: list[dict[str, Any]], artifacts: dict[str, Any]) -> str:
    rows = [[
        snapshot.get("host", "N/A"),
        analysis.get("status", "unknown"),
        analysis.get("task_count", 0),
        analysis.get("active_workers", 0),
        analysis.get("graph_count", 0),
        len(analysis.get("findings") or []),
    ]]
    finding_rows = []
    for item in analysis.get("findings") or []:
        finding_rows.append([item.get("severity", "warn"), item.get("type", "N/A"), item.get("sprint_id") or "N/A", item.get("node_id") or "N/A", item.get("task_id") or item.get("graph") or "N/A"])
    if not finding_rows:
        finding_rows = [["ok", "无异常", "N/A", "N/A", "N/A"]]
    action_rows = [[a.get("type"), "dry-run" if a.get("dry_run") else ("executed" if a.get("executed") else "planned"), a.get("rc", "N/A"), a.get("command", "N/A")] for a in actions]
    if not action_rows:
        action_rows = [["N/A", "pending", "N/A", "未启用 --apply 或无安全推进动作"]]
    findings = analysis.get("findings") or []
    has_deadlock = any(item.get("type") in {"stale_task", "missing_tmux_window", "stale_output_log"} for item in findings)
    problem = "无僵死任务" if analysis.get("status") == "ok" else f"发现 {len(findings)} 个 warn/error"
    if analysis.get("status") == "ok":
        next_step = "保持默认巡检；需要推进时运行 --apply --dry-run 先验命令"
    elif has_deadlock:
        next_step = "查看本地 monitor 草案；确认后再派发 bugfix sprint"
    else:
        next_step = "先运行 --apply --dry-run 审阅安全推进命令，再决定是否执行 --apply"
    parts = [
        "Mac mini multi-task 远端巡检结果",
        "",
        table(["目标", "状态", "task", "active", "graph", "finding"], rows),
        "",
        table(["级别", "类型", "sprint", "node", "证据"], finding_rows),
        "",
        table(["动作", "状态", "rc", "命令"], action_rows),
    ]
    if artifacts:
        parts.extend(["", table(["artifact", "path"], [[k, v] for k, v in artifacts.items()])])
    parts.extend(["", f"当前问题：{problem}", f"下一步：{next_step}"])
    return "\n".join(parts)


def tvs_table(columns: list[tuple[str, str, int | str]], rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "table",
        "columns": [
            {"key": key, "label": label, "width": width}
            for key, label, width in columns
        ],
        "rows": rows,
        "border": "minimal",
        "compact": True,
    }


def build_tvs_payload(result: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    analysis = result.get("summary") or {}
    findings = result.get("findings") or []
    actions = result.get("actions") or []
    artifacts = result.get("artifacts") or {}
    status = str(analysis.get("status") or "unknown")
    problem = "无僵死任务" if status == "ok" else f"发现 {len(findings)} 个 warn/error"
    has_deadlock = any(item.get("type") in {"stale_task", "missing_tmux_window", "stale_output_log"} for item in findings)
    if status == "ok":
        next_step = "保持默认巡检；需要推进时运行 --apply --dry-run 先验命令"
    elif has_deadlock:
        next_step = "查看本地 monitor 草案；确认后再派发 bugfix sprint"
    else:
        next_step = "先运行 --apply --dry-run 审阅安全推进命令，再决定是否执行 --apply"

    finding_items = [
        {
            "text": " | ".join([
                str(item.get("severity") or "warn"),
                str(item.get("type") or "N/A"),
                f"sprint={str(item.get('sprint_id') or 'N/A')[:42]}",
                f"node={str(item.get('node_id') or 'N/A')}",
                f"evidence={str(item.get('task_id') or item.get('graph') or 'N/A')[:52]}",
            ])
        }
        for item in findings
    ] or [{"text": "ok | 无异常 | sprint=N/A | node=N/A | evidence=N/A", "status": "success"}]

    action_items = [
        {
            "text": " | ".join([
                str(item.get("type") or "N/A"),
                "dry-run" if item.get("dry_run") else ("executed" if item.get("executed") else "planned"),
                f"rc={str(item.get('rc', 'N/A'))}",
                str(item.get("command") or "N/A")[:76],
            ])
        }
        for item in actions
    ] or [{"text": "pending | 未启用 --apply 或无安全推进动作", "status": "pending"}]

    sections: list[dict[str, Any]] = [
        {
            "type": "kv",
            "layout": "table",
            "keyWidth": 14,
            "items": [
                {"key": "目标", "value": str(result.get("host") or "N/A")},
                {"key": "状态", "value": status, "status": "success" if status == "ok" else ("error" if status == "error" else "warning")},
                {"key": "task", "value": str(analysis.get("task_count", 0))},
                {"key": "active", "value": str(analysis.get("active_workers", 0))},
                {"key": "graph", "value": str(analysis.get("graph_count", 0))},
                {"key": "finding", "value": str(len(findings))},
            ],
        },
        {"type": "divider", "label": "findings"},
        {"type": "list", "variant": "dash", "compact": True, "items": finding_items},
        {"type": "divider", "label": "actions"},
        {"type": "list", "variant": "dash", "compact": True, "items": action_items},
        {"type": "divider", "label": "conclusion"},
        {"type": "text", "content": f"当前问题：{problem}"},
        {"type": "text", "content": f"下一步：{next_step}"},
    ]
    if artifacts:
        sections.insert(
            -2,
            {"type": "list", "variant": "dash", "compact": True, "items": [f"{key}: {value}" for key, value in artifacts.items()]},
        )
    return {
        "canvas": {"width": int(args.tvs_width)},
        "style": str(args.tvs_style),
        "root": {
            "type": "card",
            "header": "Mac mini multi-task 远端巡检",
            "sections": sections,
        },
    }


def render_tvs(result: dict[str, Any], args: argparse.Namespace) -> str:
    harness_dir = Path(args.local_harness_dir).expanduser()
    cli = harness_dir / "solar-harness.sh"
    payload = build_tvs_payload(result, args)
    proc = subprocess.run(
        [str(cli), "tvs", "render", "--width", str(args.tvs_width), "--style", str(args.tvs_style), "--colors", "off"],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        timeout=20,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "TVS render failed").strip())
    return proc.stdout.rstrip()


def monitor_once(args: argparse.Namespace) -> dict[str, Any]:
    checked_at = parse_time(args.now) if args.now else now_utc()
    assert checked_at is not None
    snapshot = collect_fixture(Path(args.fixture_dir).expanduser()) if args.fixture_dir else run_ssh_json(args.host, args.ssh_timeout)
    if not snapshot.get("ok"):
        analysis = {"status": "error", "findings": [{"severity": "error", "type": "remote_collect_failed", "detail": snapshot.get("error"), "stderr": snapshot.get("stderr", "")[:1000]}], "task_count": 0, "graph_count": 0, "active_workers": 0}
        actions: list[dict[str, Any]] = []
        artifacts: dict[str, Any] = {}
    else:
        analysis = analyze(snapshot, args, checked_at)
        actions = safe_actions(analysis, args) if args.apply or args.dry_run else []
        for action in actions:
            if args.dry_run or args.fixture_dir:
                action["dry_run"] = True
                action["executed"] = False
                action["rc"] = "N/A"
            else:
                result = run_remote_action(args.host, str(action["command"]), args.ssh_timeout)
                action.update(result)
                action["executed"] = True
        failed_actions = [a for a in actions if a.get("executed") and a.get("rc") not in (0, "0")]
        if failed_actions:
            analysis.setdefault("findings", []).append({
                "severity": "error",
                "type": "apply_action_failed",
                "failed_actions": [
                    {"type": item.get("type"), "rc": item.get("rc"), "stderr": str(item.get("stderr") or "")[:500]}
                    for item in failed_actions
                ],
            })
            analysis["status"] = "error"
        artifacts = create_artifacts(snapshot, analysis, args, checked_at)
    result = {
        "ok": analysis.get("status") != "error",
        "host": args.host if not args.fixture_dir else "fixture",
        "checked_at": iso(checked_at),
        "summary": analysis,
        "findings": analysis.get("findings", []),
        "actions": actions,
        "artifacts": artifacts,
    }
    if args.write_report:
        base = Path(args.local_harness_dir).expanduser() / "monitor-reports"
        write_json(base / f"{checked_at.strftime('%Y%m%dT%H%M%SZ')}-mac-mini-monitor.json", result)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="solar-harness monitor")
    parser.add_argument("--host", default=os.environ.get("SOLAR_MONITOR_HOST", DEFAULT_HOST))
    parser.add_argument("--stale-minutes", type=float, default=float(os.environ.get("SOLAR_MONITOR_STALE_MINUTES", "30")))
    parser.add_argument("--apply", action="store_true", help="run safe allowlisted recovery actions")
    parser.add_argument("--dry-run", action="store_true", help="show allowlisted actions without mutating remote state")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--renderer", choices=["tvs", "plain"], default=os.environ.get("SOLAR_MONITOR_RENDER", "tvs"), help="human renderer")
    parser.add_argument("--tvs", action="store_true", help="use TVS renderer for human output")
    parser.add_argument("--plain", action="store_true", help="use legacy built-in table renderer")
    parser.add_argument("--tvs-style", default=os.environ.get("SOLAR_MONITOR_TVS_STYLE", "solar_default"))
    parser.add_argument("--tvs-width", type=int, default=int(os.environ.get("SOLAR_MONITOR_TVS_WIDTH", "120")))
    parser.add_argument("--loop", action="store_true", help="repeat monitor loop")
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--ssh-timeout", type=int, default=12)
    parser.add_argument("--local-harness-dir", default=os.environ.get("HARNESS_DIR", str(Path.home() / ".solar" / "harness")))
    parser.add_argument("--write-report", action="store_true", help="write JSON report for every scan")
    parser.add_argument("--fixture-dir", help=argparse.SUPPRESS)
    parser.add_argument("--now", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.tvs:
        args.renderer = "tvs"
    if args.plain:
        args.renderer = "plain"
    while True:
        result = monitor_once(args)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.renderer == "tvs":
            try:
                print(render_tvs(result, args))
            except Exception as exc:
                print(f"[monitor] TVS render failed, fallback=plain: {exc}", file=sys.stderr)
                print(render_human({"host": result["host"]}, result["summary"], result["actions"], result["artifacts"]))
        else:
            print(render_human({"host": result["host"]}, result["summary"], result["actions"], result["artifacts"]))
        if not args.loop:
            return 0 if result.get("ok") else 1
        time.sleep(max(1, int(args.interval)))


if __name__ == "__main__":
    raise SystemExit(main())
