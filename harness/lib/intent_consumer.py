#!/usr/bin/env python3
"""Consume RawIntent artifacts into compiled Solar-Harness work packages.

The gateway captures raw user intent. This consumer is the next hop: it turns
an intent directory into a requirement-compiler sprint package. Trusted entry
points can then get a best-effort Planner handoff through pm_dispatch/runtime;
raw natural language is never sent directly to tmux panes.
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

HARNESS_DIR = Path(os.environ.get("SOLAR_HARNESS_DIR", Path(__file__).resolve().parents[1]))
SPRINTS_DIR = Path(os.environ.get("SOLAR_HARNESS_SPRINTS_DIR", Path.home() / ".solar" / "harness" / "sprints"))
INTENTS_DIR = Path(os.environ.get("SOLAR_INTENT_GATEWAY_DIR", Path.home() / ".solar" / "harness" / "intents"))
DEFAULT_TRUSTED_AUTODISPATCH_CHANNELS = (
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


def safe_slug(value: str, limit: int = 48) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-").lower()
    return (value or "rawintent")[:limit]


def intent_dir(intent_id: str) -> Path:
    return INTENTS_DIR / intent_id


def load_intent(intent_id: str) -> tuple[Path, dict[str, Any], dict[str, Any], dict[str, Any]]:
    base = intent_dir(intent_id)
    raw_path = base / "raw_intent.json"
    rewritten_path = base / "rewritten_intent.json"
    ir_path = base / "requirement_ir.json"
    if not raw_path.exists() or not rewritten_path.exists() or not ir_path.exists():
        raise SystemExit(f"intent artifacts incomplete: {intent_id}")
    return base, read_json(raw_path), read_json(rewritten_path), read_json(ir_path)


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
    objective = textwrap.dedent(
        f"""\
        请接手 {sprint_id}：RawIntent 已经通过 Intent Gateway 和 Requirement Compiler 生成需求编译包。

        先读取：
        - {base}.product-brief.md
        - {base}.prd.md
        - {base}.contract.md
        - {base}.task_graph.json
        - {base}.requirement_ir.json
        - {base}.handoff.md

        你的任务：
        1. 基于 compiled requirement package 产出 design.md 和 plan.md。
        2. 如有必要，细化或修正 task_graph.json，但不得绕过 compiled contracts。
        3. 不要直接跳 Builder；保持 RawIntent -> Requirement Compiler -> Planner -> task_graph -> Builder 主链。
        4. 如果 compiled package 缺失关键字段，先写明 blocker 和修正建议。
        5. 检查 requirement_ir.planner_hints.workflow_candidates，并在 direct_answer、memoized_task_graph、new_task_graph 中明确选择一种；候选模板不能自行生效。
        6. 只有选择 memoized_task_graph 时，才可把选中的 workflow_id 交给 TaskGraph compiler；必须保留节点合同、capability capsule、physical operator 候选和 fallback。
        """
    ).strip()
    # P5 G2: teach the planner the compile rules it will be checked against
    # (env-gated inside the helper; "" when SOLAR_PLAN_VALIDATOR is off, so
    # legacy prompts stay byte-identical). Prompt enrichment must never break
    # dispatch — enforcement lives at the compile/dispatch seams.
    try:
        import plan_validator  # noqa: WPS433

        policy_block = plan_validator.planner_compile_policy_block(SPRINTS_DIR, sprint_id)
    except Exception:
        policy_block = ""
    if policy_block:
        objective = f"{objective}\n\n{policy_block}"
    return objective


def submit_planner_handoff(sprint_id: str, requirement_ir_path: Path, *, dry_run: bool = False) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(HARNESS_DIR / "tools" / "pm_dispatch.py"),
        "submit",
        "--role", "planner",
        "--objective", planner_objective_for_compiled_sprint(sprint_id),
        "--sprint", sprint_id,
        "--node", "N0",
        "--task-type", "planning",
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

    if handoff.get("requested"):
        handoff = {**handoff, **submit_planner_handoff(sid, SPRINTS_DIR / f"{sid}.requirement_ir.json")}
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
        print(json.dumps(payload, ensure_ascii=False, indent=2))
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
