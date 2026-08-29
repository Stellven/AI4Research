#!/usr/bin/env python3
"""Consume RawIntent artifacts into Planner handoff packages.

The gateway captures raw user intent. This consumer is the next hop: it turns
an intent directory into an immutable RequirementIR sprint package. Trusted
entry points can then get a best-effort Planner handoff through
pm_dispatch/runtime; raw natural language is never sent directly to operators.
The Planner emits PlanIR, and the deterministic static execution compiler—not
the Planner or scheduler—binds that PlanIR into frozen scheduler authority.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

HARNESS_DIR = Path(
    os.environ.get("HARNESS_DIR")
    or os.environ.get("SOLAR_HARNESS_DIR")
    or Path(__file__).resolve().parents[1]
)
SPRINTS_DIR = Path(os.environ.get("SOLAR_HARNESS_SPRINTS_DIR") or (HARNESS_DIR / "sprints"))
INTENTS_DIR = Path(os.environ.get("SOLAR_INTENT_GATEWAY_DIR") or (HARNESS_DIR / "intents"))
DEFAULT_TRUSTED_AUTODISPATCH_CHANNELS = (
    "dashboard",
    "pm_dispatch",
    "pm_compile_request",
    "codex_bridge",
    "github_webhook",
)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def is_formal_requirement_ir(requirement_ir: dict[str, Any]) -> bool:
    return requirement_ir.get("schema_version") == "solar.requirement_ir.v2"


def initialize_formal_sprint(
    sprint_id: str,
    raw: dict[str, Any],
    planning_view: dict[str, Any],
) -> Path:
    """Create only lifecycle state for the typed path; never synthesize a DAG."""
    status_path = SPRINTS_DIR / f"{sprint_id}.status.json"
    if status_path.exists():
        return status_path
    created = now_iso()
    write_json(
        status_path,
        {
            "schema_version": "solar.sprint_status.v1",
            "sprint_id": sprint_id,
            "title": str(planning_view.get("title") or sprint_id),
            "objective": str(planning_view.get("objective") or ""),
            "status": "drafting",
            "phase": "requirement_compiled",
            "handoff_to": "elastic_planner",
            "target_role": "planner",
            "round": 0,
            "created_at": created,
            "updated_at": created,
            "planning_authority": "solar.requirement_ir.v2",
            "plan_compile_required": True,
            "runtime_handoff_allowed": False,
            "source_intent_id": str(raw.get("intent_id") or ""),
            "history": [
                {
                    "ts": created,
                    "event": "formal_requirement_compiled",
                    "by": "intent_consumer",
                }
            ],
        },
    )
    return status_path


def is_direct_answer_requirement(requirement_ir: dict[str, Any]) -> bool:
    """Keep intake routing dependency-free; the heavy Planner loads in its worker."""
    hints = (
        requirement_ir.get("planner_hints")
        if isinstance(requirement_ir.get("planner_hints"), dict)
        else {}
    )
    return (
        requirement_ir.get("request_type") == "direct_answer"
        and hints.get("preferred_outcome") == "direct_answer"
        and hints.get("runtime_handoff_allowed") is False
    )


def safe_slug(value: str, limit: int = 48) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-").lower()
    return (value or "rawintent")[:limit]


def intent_dir(intent_id: str) -> Path:
    return INTENTS_DIR / intent_id


def _semantic_intent_compatibility_view(
    raw: dict[str, Any],
    intent_ir: dict[str, Any],
    requirement_ir: dict[str, Any],
) -> dict[str, Any]:
    """Project the accepted semantic bundle into the legacy PM request view.

    ``rewritten_intent.json`` belonged to the pre-IntentIR gateway.  The native
    pipeline intentionally no longer emits it, but the current PM request
    compiler still consumes its small title/objective/constraint view.  Build
    that view deterministically in memory; do not create a fake stage artifact.
    """
    goals = [
        str(item.get("statement") or "").strip()
        for item in intent_ir.get("goals") or []
        if isinstance(item, dict) and str(item.get("statement") or "").strip()
    ]
    constraints = [
        str(item.get("statement") or "").strip()
        for item in intent_ir.get("constraints") or []
        if isinstance(item, dict) and str(item.get("statement") or "").strip()
    ]
    acceptance = [
        str(item.get("statement") or "").strip()
        for item in requirement_ir.get("requirements") or []
        if isinstance(item, dict) and str(item.get("statement") or "").strip()
    ]
    raw_text = str(((raw.get("raw") or {}).get("text") or "")).strip()
    title = goals[0] if goals else raw_text
    return {
        "schema_version": "solar.intent_planner_compatibility_view.v1",
        "title": title[:90],
        "objective": "\n".join(goals) or raw_text,
        "problem": raw_text,
        "constraints": constraints,
        "acceptance": acceptance,
    }


def load_intent(intent_id: str) -> tuple[Path, dict[str, Any], dict[str, Any], dict[str, Any]]:
    base = intent_dir(intent_id)
    raw_path = base / "raw_intent.json"
    rewritten_path = base / "rewritten_intent.json"
    semantic_intent_path = base / "intent" / "intent_ir.json"
    ir_path = base / "requirement_ir.json"
    missing = [
        path.name
        for path in (raw_path, ir_path)
        if not path.exists()
    ]
    if missing:
        raise SystemExit(f"intent artifacts incomplete: {intent_id}; missing={','.join(missing)}")

    raw = read_json(raw_path)
    requirement_ir = read_json(ir_path)
    if rewritten_path.exists():
        planning_view = read_json(rewritten_path)
    elif semantic_intent_path.exists():
        intent_ir = read_json(semantic_intent_path)
        expected_intent_id = str((requirement_ir.get("intent_ir_ref") or {}).get("intent_ir_id") or "")
        actual_intent_id = str(intent_ir.get("intent_ir_id") or "")
        if expected_intent_id and expected_intent_id != actual_intent_id:
            raise SystemExit(
                "intent artifacts incompatible: "
                f"{intent_id}; requirement IntentIR ref={expected_intent_id!r} "
                f"but bundle contains {actual_intent_id!r}"
            )
        planning_view = _semantic_intent_compatibility_view(raw, intent_ir, requirement_ir)
    else:
        raise SystemExit(
            "intent artifacts incomplete: "
            f"{intent_id}; missing=rewritten_intent.json|intent/intent_ir.json"
        )
    return base, raw, planning_view, requirement_ir


def list_pending(limit: int = 20, oldest_first: bool = True) -> list[str]:
    if not INTENTS_DIR.exists():
        return []
    dirs = [p for p in INTENTS_DIR.iterdir() if p.is_dir() and (p / "raw_intent.json").exists()]
    dirs.sort(key=lambda p: p.stat().st_mtime, reverse=not oldest_first)
    result: list[str] = []
    for base in dirs:
        consumer = base / "consumer.json"
        if consumer.exists():
            try:
                data = read_json(consumer)
                if data.get("status") == "consumed":
                    continue
            except Exception:
                pass
        if (base / "binding.json").exists():
            continue
        result.append(base.name)
        if len(result) >= limit:
            break
    return result


def extract_research_artifact(raw: dict[str, Any], ir: dict[str, Any]) -> dict[str, Any] | None:
    research = raw.get("research") if isinstance(raw.get("research"), dict) else None
    if research:
        return research
    source_inputs = ir.get("source_inputs") if isinstance(ir.get("source_inputs"), dict) else {}
    research = source_inputs.get("research_artifact") if isinstance(source_inputs.get("research_artifact"), dict) else None
    return research


def require_research_artifact(raw: dict[str, Any], ir: dict[str, Any]) -> bool:
    routing = raw.get("routing_hints", {}) if isinstance(raw.get("routing_hints"), dict) else {}
    if routing.get("require_research_artifact"):
        return True
    return extract_research_artifact(raw, ir) is not None


def annotate_compiled_package_with_research_artifact(sprint_id: str, research: dict[str, Any]) -> None:
    ir_path = SPRINTS_DIR / f"{sprint_id}.requirement_ir.json"
    product_brief_path = SPRINTS_DIR / f"{sprint_id}.product-brief.md"
    prd_path = SPRINTS_DIR / f"{sprint_id}.prd.md"
    requirement_ir = read_json(ir_path)
    source_inputs = requirement_ir.get("source_inputs")
    if not isinstance(source_inputs, dict):
        source_inputs = {}
    source_inputs["research_artifact"] = {
        "path": str(research.get("path") or ""),
        "project_name": str(research.get("project_name") or ""),
        "conversation_id": str(research.get("conversation_id") or ""),
        "source_url": str(research.get("source_url") or ""),
    }
    requirement_ir["source_inputs"] = source_inputs
    write_json(ir_path, requirement_ir)

    lines = [
        "## Research Artifact Inputs",
        "",
        f"- path: {research.get('path') or 'N/A'}",
        f"- project_name: {research.get('project_name') or 'N/A'}",
        f"- conversation_id: {research.get('conversation_id') or 'N/A'}",
        f"- source_url: {research.get('source_url') or 'N/A'}",
    ]
    block = "\n".join(lines) + "\n"
    for path in (product_brief_path, prd_path):
        text = path.read_text(encoding="utf-8")
        if "## Research Artifact Inputs" in text:
            continue
        path.write_text(text.rstrip() + "\n\n" + block, encoding="utf-8")


def build_consumer_text(raw: dict[str, Any], rewritten: dict[str, Any], ir: dict[str, Any]) -> str:
    source = raw.get("source", {}) if isinstance(raw.get("source"), dict) else {}
    raw_text = (((raw.get("raw") or {}).get("text")) or "").strip()
    constraints = rewritten.get("constraints") or ir.get("constraints") or []
    acceptance = rewritten.get("acceptance") or ir.get("acceptance") or []
    title = str(rewritten.get("title") or ir.get("title") or "RawIntent")
    research = extract_research_artifact(raw, ir)
    lines = [
        f"# RawIntent Consumer Request - {title}",
        "",
        "## Source",
        "",
        f"- intent_id: {raw.get('intent_id') or ir.get('intent_id')}",
        f"- channel: {source.get('channel', 'N/A')}",
        f"- actor: {source.get('actor', 'N/A')}",
        f"- device: {source.get('device', 'N/A')}",
        f"- thread_ref: {source.get('thread_ref', 'N/A')}",
        "",
        "## Rewritten Objective",
        "",
        str(rewritten.get("objective") or ir.get("objective") or title),
        "",
        "## Problem",
        "",
        str(rewritten.get("problem") or ir.get("problem") or raw_text),
        "",
        "## Constraints",
        "",
        *(f"- {item}" for item in constraints),
        "",
        "## Acceptance",
        "",
        *(f"- {item}" for item in acceptance),
        "",
    ]
    if research:
        lines.extend([
            "## Research Artifact Inputs",
            "",
            f"- path: {research.get('path') or 'N/A'}",
            f"- project_name: {research.get('project_name') or 'N/A'}",
            f"- conversation_id: {research.get('conversation_id') or 'N/A'}",
            f"- source_url: {research.get('source_url') or 'N/A'}",
            "",
            "Research artifact must remain a first-class source input for product-brief, PRD, and requirement_ir generation.",
            "",
        ])
    lines.extend([
        "## Raw User Intent",
        "",
        raw_text,
    ])
    return "\n".join(lines).strip() + "\n"


def sprint_id_for(intent_id: str, rewritten: dict[str, Any]) -> str:
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    title = safe_slug(str(rewritten.get("title") or intent_id), 28)
    tail = intent_id.rsplit("-", 1)[-1][:8]
    return f"sprint-{ts}-intent-{title}-{tail}"


def trusted_autodispatch_channels() -> set[str]:
    raw = os.environ.get("SOLAR_INTENT_TRUSTED_AUTODISPATCH_CHANNELS", "")
    values = raw.split(",") if raw.strip() else DEFAULT_TRUSTED_AUTODISPATCH_CHANNELS
    return {item.strip() for item in values if item.strip()}


def codex_pane_runtime_suppresses_pm_operator_dispatch() -> bool:
    runtime = os.environ.get("SOLAR_PANE_RUNTIME", "").strip().lower()
    allow = os.environ.get("SOLAR_CODEX_ALLOW_PM_OPERATOR_DISPATCH", "").strip().lower()
    return runtime == "codex" and allow not in {"1", "true", "yes", "on"}


def suppress_pm_operator_dispatch_for_codex(handoff: dict[str, Any]) -> dict[str, Any]:
    if not handoff.get("requested"):
        return handoff
    if not codex_pane_runtime_suppresses_pm_operator_dispatch():
        return handoff
    return {
        **handoff,
        "requested": False,
        "suppressed_requested": True,
        "suppressed_reason": handoff.get("reason"),
        "reason": "codex_pane_runtime_uses_coordinator_planner_pane",
    }


def planner_handoff_policy(
    raw: dict[str, Any],
    *,
    explicit_dispatch_planner: bool = False,
    auto_dispatch_planner: bool = True,
) -> dict[str, Any]:
    source = raw.get("source", {}) if isinstance(raw.get("source"), dict) else {}
    routing = raw.get("routing_hints", {}) if isinstance(raw.get("routing_hints"), dict) else {}
    trust = raw.get("trust", {}) if isinstance(raw.get("trust"), dict) else {}
    source_channel = str(source.get("channel") or "")
    source_trust = str(trust.get("source_trust") or "")
    allow_autodispatch = bool(routing.get("allow_autodispatch", False))
    requires_human_confirm = bool(routing.get("requires_human_confirm", False))
    trusted = trusted_autodispatch_channels()

    base = {
        "source_channel": source_channel,
        "source_trust": source_trust,
        "allow_autodispatch": allow_autodispatch,
        "requires_human_confirm": requires_human_confirm,
        "trusted_channels": sorted(trusted),
        "auto_dispatch_planner": auto_dispatch_planner,
    }
    if explicit_dispatch_planner:
        return {**base, "requested": True, "reason": "explicit_cli"}
    if not auto_dispatch_planner:
        return {**base, "requested": False, "reason": "auto_dispatch_disabled"}
    if requires_human_confirm:
        return {**base, "requested": False, "reason": "requires_human_confirm"}
    if not allow_autodispatch:
        return {**base, "requested": False, "reason": "autodispatch_not_allowed"}
    if source_channel in trusted or source_trust in trusted:
        return {**base, "requested": True, "reason": "trusted_channel"}
    return {**base, "requested": False, "reason": "untrusted_channel"}


def planner_objective_for_compiled_sprint(sprint_id: str) -> str:
    base = str(SPRINTS_DIR / sprint_id)
    return textwrap.dedent(
        f"""\
        请接手 {sprint_id}：RawIntent 已通过 Intent Compiler 和 Requirement Compiler。
        Planner 只负责需求整理与向下游交接。

        权威输入：
        - {base}.requirement_ir.json
        - {base}.contract.md
        - {base}.prd.md

        只允许输出：
        - {base}.planner-requirements.md
        - {base}.planner-handoff.md

        规则：
        1. 整理目标、约束、验收标准、风险、输入和建议的下游执行模式。
        2. 不得创建或修改 design.md、plan.md、task_graph.json、PlanIR 或 DAG。
        3. 不得研究、调用浏览器、生成 HTML/最终答案/报告、执行任务或评估。
        4. 不得派发其他角色，也不得修改 status.json；Solar 根据 handoff 决定下一角色。
        5. 简单问题可在 handoff 中建议 direct_response，但答案必须由下游 direct-response worker 生成。
        """
    ).strip()


def submit_typed_planner(
    sprint_id: str,
    requirement_ir_path: Path,
    *,
    workspace_root: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    output_root = SPRINTS_DIR / sprint_id / "planning"
    log_dir = HARNESS_DIR / "logs" / "elastic-planner"
    log_path = log_dir / f"{sprint_id}.log"
    command = [
        sys.executable,
        str(HARNESS_DIR / "tools" / "elastic_planner_adapter.py"),
        "--requirement-ir",
        str(requirement_ir_path),
        "--output-root",
        str(output_root),
        "--sprint-id",
        sprint_id,
        "--workspace-root",
        workspace_root,
    ]
    if dry_run:
        return {
            "status": "dry_run",
            "mode": "elastic_planner",
            "cmd": command,
            "output_root": str(output_root),
        }
    log_dir.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    environment["HARNESS_DIR"] = str(HARNESS_DIR)
    environment["SOLAR_HARNESS_DIR"] = str(HARNESS_DIR)
    environment["SOLAR_HARNESS_SPRINTS_DIR"] = str(SPRINTS_DIR)
    with log_path.open("ab") as output:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            cwd=str(HARNESS_DIR),
            env=environment,
            start_new_session=(os.name != "nt"),
        )
    (output_root / "adapter.pid").parent.mkdir(parents=True, exist_ok=True)
    (output_root / "adapter.pid").write_text(f"{process.pid}\n", encoding="utf-8")
    return {
        "status": "submitted",
        "mode": "elastic_planner",
        "pid": process.pid,
        "cmd": command,
        "log": str(log_path),
        "output_root": str(output_root),
    }


def submit_planner_handoff(sprint_id: str, requirement_ir_path: Path, *, dry_run: bool = False) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(HARNESS_DIR / "tools" / "pm_dispatch.py"),
        "submit",
        "--role", "planner",
        "--objective", planner_objective_for_compiled_sprint(sprint_id),
        "--sprint", sprint_id,
        "--node", "N0",
        "--task-type", "requirements_handoff",
        "--context", f"compiled_requirement_ir={requirement_ir_path}",
    ]
    if dry_run:
        cmd.append("--dry-run")
    env = dict(os.environ)
    env["SOLAR_HARNESS_DIR"] = str(HARNESS_DIR)
    env["HARNESS_DIR"] = str(HARNESS_DIR)
    env["SOLAR_HARNESS_SPRINTS_DIR"] = str(SPRINTS_DIR)
    env["SOLAR_INTENT_GATEWAY_DIR"] = str(INTENTS_DIR)
    env["SOLAR_PM_DISPATCH_ALLOW_DIRECT"] = "1"
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, env=env, timeout=90)
    except Exception as exc:
        return {"status": "failed", "exit_code": -1, "error": str(exc), "cmd": cmd}
    return {
        "status": "submitted" if proc.returncode == 0 else "failed",
        "exit_code": proc.returncode,
        "cmd": cmd,
        "stdout_tail": (proc.stdout or "")[-4000:],
        "stderr_tail": (proc.stderr or "")[-4000:],
    }


def submit_direct_answer_runtime(sprint_id: str, requirement_ir_path: Path) -> dict[str, Any]:
    """Compatibility launcher for the downstream no-DAG response worker.

    New intake never calls this directly: Planner handoff must complete first,
    and the coordinator then launches the worker.
    """
    from activity_runtime import ActivityRuntime
    from runtime_status import transition_status

    status_path = SPRINTS_DIR / f"{sprint_id}.status.json"
    log_dir = HARNESS_DIR / "logs" / "direct-answer"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{sprint_id}.log"
    configured_python = os.environ.get("SOLAR_DIRECT_ANSWER_PYTHON", "").strip()
    runtime_python = HARNESS_DIR / ".venv-runtime" / "bin" / "python"
    python_executable = (
        configured_python
        or (str(runtime_python) if runtime_python.is_file() else "")
        or sys.executable
    )
    command = [
        python_executable,
        str(HARNESS_DIR / "tools" / "direct_answer_runtime.py"),
        "--sprint-id",
        sprint_id,
    ]
    environment = dict(os.environ)
    environment["HARNESS_DIR"] = str(HARNESS_DIR)
    environment["SOLAR_HARNESS_DIR"] = str(HARNESS_DIR)
    environment["SOLAR_HARNESS_SPRINTS_DIR"] = str(SPRINTS_DIR)
    transition_status(
        status_path,
        "active",
        "direct_answer_queued",
        "intent_consumer",
        extra={
            "status_fields": {
                "phase": "direct_answer",
                "stage": "direct_answer_queued",
                "handoff_to": "direct_response_worker",
                "target_role": "direct_response_worker",
                "runtime_handoff_allowed": False,
                "direct_answer_status": "queued",
                "plan_compile_required": False,
                "planner_dispatch_claim": None,
            },
            "note": "Queued the downstream direct-response worker; no TaskGraph dispatch is allowed.",
        },
    )
    runtime = ActivityRuntime(sprint_id, harness_dir=str(HARNESS_DIR))
    runtime.command_issued(
        "direct-answer",
        actor="intent_consumer",
        target="direct_response_worker",
        payload={"stage": "direct_answer", "runtime_handoff_allowed": False},
    )
    try:
        with log_path.open("ab") as output:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                env=environment,
                cwd=str(HARNESS_DIR),
                start_new_session=(os.name != "nt"),
            )
        (SPRINTS_DIR / f"{sprint_id}.direct-answer.pid").write_text(
            f"{process.pid}\n", encoding="utf-8"
        )
    except Exception as exc:
        transition_status(
            status_path,
            "failed",
            "direct_answer_launch_failed",
            "intent_consumer",
            extra={
                "status_fields": {
                    "stage": "direct_answer_failed",
                    "direct_answer_status": "failed",
                    "direct_answer_error": str(exc),
                },
                "note": str(exc),
            },
        )
        return {
            "status": "failed",
            "mode": "direct_answer",
            "error": str(exc),
            "cmd": command,
        }
    return {
        "status": "submitted",
        "mode": "direct_answer",
        "pid": process.pid,
        "cmd": command,
        "log": str(log_path),
    }


def consume_one(
    intent_id: str,
    *,
    sprint_id: str = "",
    dry_run: bool = False,
    dispatch_planner: bool = False,
    auto_dispatch_planner: bool = True,
) -> dict[str, Any]:
    base, raw, rewritten, ir = load_intent(intent_id)
    research = extract_research_artifact(raw, ir)
    research_required = require_research_artifact(raw, ir)
    existing = base / "consumer.json"
    if existing.exists() and not dry_run:
        data = read_json(existing)
        if data.get("status") == "consumed":
            return {"ok": True, "intent_id": intent_id, "status": "already_consumed", "sprint_id": data.get("sprint_id", "")}

    sid = sprint_id or sprint_id_for(intent_id, rewritten)
    handoff = planner_handoff_policy(
        raw,
        explicit_dispatch_planner=dispatch_planner,
        auto_dispatch_planner=auto_dispatch_planner,
    )
    formal_requirement = is_formal_requirement_ir(ir)
    if not formal_requirement:
        handoff = suppress_pm_operator_dispatch_for_codex(handoff)
    if research_required and not research:
        payload = {
            "ok": False,
            "status": "blocked_missing_research_artifact",
            "intent_id": intent_id,
            "sprint_id": sid,
            "updated_at": now_iso(),
            "planner_handoff": handoff,
        }
        write_json(base / "consumer.json", payload)
        return payload

    if formal_requirement:
        workspace_root = os.environ.get(
            "SOLAR_INTENT_CONSUMER_WORKSPACE_ROOT", str(HARNESS_DIR)
        )
        requirement_ir_path = SPRINTS_DIR / f"{sid}.requirement_ir.json"
        if dry_run:
            typed_handoff = (
                submit_typed_planner(
                    sid,
                    requirement_ir_path,
                    workspace_root=workspace_root,
                    dry_run=True,
                )
                if handoff.get("requested")
                else {"status": "skipped", "mode": "elastic_planner"}
            )
            return {
                "ok": True,
                "intent_id": intent_id,
                "status": "dry_run",
                "sprint_id": sid,
                "planner_handoff": {**handoff, **typed_handoff},
            }

        initialize_formal_sprint(sid, raw, rewritten)
        env = dict(os.environ)
        env["SOLAR_HARNESS_DIR"] = str(HARNESS_DIR)
        env["HARNESS_DIR"] = str(HARNESS_DIR)
        env["SOLAR_HARNESS_SPRINTS_DIR"] = str(SPRINTS_DIR)
        env["SOLAR_INTENT_GATEWAY_DIR"] = str(INTENTS_DIR)
        bind_cmd = [
            sys.executable,
            str(HARNESS_DIR / "lib" / "intent_gateway.py"),
            "bind",
            "--intent-id",
            intent_id,
            "--sprint-id",
            sid,
            "--json",
        ]
        bind = subprocess.run(
            bind_cmd, text=True, capture_output=True, env=env, timeout=30
        )
        if bind.returncode != 0:
            payload = {
                "ok": False,
                "status": "bind_failed",
                "intent_id": intent_id,
                "sprint_id": sid,
                "updated_at": now_iso(),
                "planner_handoff": handoff,
                "bind_stderr_tail": (bind.stderr or bind.stdout or "")[-4000:],
            }
            write_json(base / "consumer.json", payload)
            return payload

        if handoff.get("requested"):
            handoff = {
                **handoff,
                **submit_typed_planner(
                    sid,
                    requirement_ir_path,
                    workspace_root=workspace_root,
                ),
            }
        else:
            handoff = {**handoff, "status": "skipped", "mode": "elastic_planner"}
        payload = {
            "ok": True,
            "status": "consumed",
            "intent_id": intent_id,
            "sprint_id": sid,
            "updated_at": now_iso(),
            "consumer": "intent_consumer.py",
            "direct_pane_dispatch": False,
            "planner_runtime_submit": handoff.get("status") == "submitted",
            "planner_handoff": handoff,
            "artifacts": {
                "status": str(SPRINTS_DIR / f"{sid}.status.json"),
                "raw_intent": str(SPRINTS_DIR / f"{sid}.raw_intent.json"),
                "intent_ir": str(SPRINTS_DIR / f"{sid}.intent_ir.json"),
                "requirement_ir": str(requirement_ir_path),
                "planning_output_root": str(SPRINTS_DIR / sid / "planning"),
            },
        }
        write_json(base / "consumer.json", payload)
        return payload

    request_text = build_consumer_text(raw, rewritten, ir)
    cmd = [
        sys.executable,
        str(HARNESS_DIR / "tools" / "pm_dispatch.py"),
        "compile-request",
        "--text", request_text,
        "--sprint", sid,
        "--workspace-root", os.environ.get("SOLAR_INTENT_CONSUMER_WORKSPACE_ROOT", str(HARNESS_DIR)),
        "--target-system", "solar-harness",
    ]
    env = dict(os.environ)
    env["SOLAR_HARNESS_DIR"] = str(HARNESS_DIR)
    env["HARNESS_DIR"] = str(HARNESS_DIR)
    env["SOLAR_HARNESS_SPRINTS_DIR"] = str(SPRINTS_DIR)
    env["SOLAR_INTENT_GATEWAY_DIR"] = str(INTENTS_DIR)
    env["SOLAR_PM_DISPATCH_ALLOW_DIRECT"] = "1"

    if dry_run:
        return {"ok": True, "intent_id": intent_id, "status": "dry_run", "sprint_id": sid, "cmd": cmd, "planner_handoff": handoff}

    proc = subprocess.run(cmd, text=True, capture_output=True, env=env, timeout=120)
    if proc.returncode != 0:
        payload = {
            "ok": False,
            "status": "failed",
            "intent_id": intent_id,
            "sprint_id": sid,
            "updated_at": now_iso(),
            "exit_code": proc.returncode,
            "planner_handoff": handoff,
            "stdout_tail": (proc.stdout or "")[-4000:],
            "stderr_tail": (proc.stderr or "")[-4000:],
        }
        write_json(base / "consumer.json", payload)
        return payload

    bind_cmd = [
        sys.executable,
        str(HARNESS_DIR / "lib" / "intent_gateway.py"),
        "bind",
        "--intent-id", intent_id,
        "--sprint-id", sid,
        "--json",
    ]
    bind = subprocess.run(bind_cmd, text=True, capture_output=True, env=env, timeout=30)
    if bind.returncode != 0:
        payload = {
            "ok": False,
            "status": "bind_failed",
            "intent_id": intent_id,
            "sprint_id": sid,
            "updated_at": now_iso(),
            "planner_handoff": handoff,
            "stdout_tail": (proc.stdout or "")[-4000:],
            "bind_stderr_tail": (bind.stderr or bind.stdout or "")[-4000:],
        }
        write_json(base / "consumer.json", payload)
        return payload

    if research:
        annotate_compiled_package_with_research_artifact(sid, research)

    requirement_ir_path = SPRINTS_DIR / f"{sid}.requirement_ir.json"
    if handoff.get("requested"):
        handoff = {**handoff, **submit_planner_handoff(sid, requirement_ir_path)}
    else:
        handoff = {**handoff, "status": "skipped"}

    payload = {
        "ok": True,
        "status": "consumed",
        "intent_id": intent_id,
        "sprint_id": sid,
        "updated_at": now_iso(),
        "consumer": "intent_consumer.py",
        "direct_pane_dispatch": False,
        "planner_runtime_submit": handoff.get("status") == "submitted",
        "planner_handoff": handoff,
        "artifacts": {
            "status": str(SPRINTS_DIR / f"{sid}.status.json"),
            "product_brief": str(SPRINTS_DIR / f"{sid}.product-brief.md"),
            "prd": str(SPRINTS_DIR / f"{sid}.prd.md"),
            "contract": str(SPRINTS_DIR / f"{sid}.contract.md"),
            "task_graph": str(SPRINTS_DIR / f"{sid}.task_graph.json"),
            "raw_intent": str(SPRINTS_DIR / f"{sid}.raw_intent.json"),
            "requirement_ir": str(SPRINTS_DIR / f"{sid}.requirement_ir.json"),
        },
        "compiler_stdout_tail": (proc.stdout or "")[-4000:],
    }
    write_json(base / "consumer.json", payload)
    return payload


def consume(args: argparse.Namespace) -> dict[str, Any]:
    ids = [args.intent_id] if args.intent_id else list_pending(limit=args.limit, oldest_first=not args.newest_first)
    results = [
        consume_one(
            intent_id,
            sprint_id=args.sprint_id,
            dry_run=args.dry_run,
            dispatch_planner=args.dispatch_planner,
            auto_dispatch_planner=not args.no_auto_dispatch_planner,
        )
        for intent_id in ids
    ]
    return {"ok": all(item.get("ok") for item in results), "count": len(results), "results": results}


def status(args: argparse.Namespace) -> dict[str, Any]:
    pending = list_pending(limit=args.limit, oldest_first=not args.newest_first)
    consumed = 0
    failed = 0
    if INTENTS_DIR.exists():
        for base in INTENTS_DIR.iterdir():
            consumer = base / "consumer.json"
            if not consumer.exists():
                continue
            try:
                data = read_json(consumer)
            except Exception:
                continue
            if data.get("status") == "consumed":
                consumed += 1
            elif data.get("status"):
                failed += 1
    return {"ok": True, "pending": pending, "pending_count": len(pending), "consumed_count": consumed, "failed_count": failed}


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="intent_consumer.py")
    sub = parser.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("consume")
    c.add_argument("--intent-id", default="")
    c.add_argument("--sprint-id", default="")
    c.add_argument("--limit", type=int, default=10)
    c.add_argument("--newest-first", action="store_true")
    c.add_argument("--dry-run", action="store_true")
    c.add_argument("--dispatch-planner", action="store_true", help="force planner handoff even if source is not trusted")
    c.add_argument("--no-auto-dispatch-planner", action="store_true", help="compile only; disable trusted-source planner handoff")
    c.add_argument("--json", action="store_true")

    st = sub.add_parser("status")
    st.add_argument("--limit", type=int, default=20)
    st.add_argument("--newest-first", action="store_true")
    st.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    if args.cmd == "consume":
        payload = consume(args)
    else:
        payload = status(args)

    if getattr(args, "json", False):
        # Keep the machine-readable CLI surface safe even when a Windows
        # parent process decodes pipes with CP1252. JSON consumers recover the
        # original Unicode values from the escapes.
        print(json.dumps(payload, ensure_ascii=True, indent=2))
    else:
        if args.cmd == "consume":
            print(f"consumed={payload['count']} ok={payload['ok']}")
            for item in payload["results"]:
                handoff = item.get("planner_handoff") or {}
                print(f"- {item.get('intent_id')} {item.get('status')} sprint={item.get('sprint_id', 'N/A')} planner={handoff.get('status', 'N/A')}")
        else:
            print(f"pending={payload['pending_count']} consumed={payload['consumed_count']} failed={payload['failed_count']}")
            for item in payload["pending"]:
                print(f"- {item}")
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
