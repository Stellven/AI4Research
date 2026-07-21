#!/usr/bin/env python3
"""Role-aware Autoresearch advisor blocks for Solar-Harness panes.

This helper does not execute autoresearch. It only decides whether a pane
dispatch should receive an explicit quality-optimizer hint and renders a small
markdown block that keeps execution gated behind dry-run / --execute rules.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROLE_MAP = {
    "pm": "pm",
    "product": "pm",
    "产品经理": "pm",
    "planner": "planner",
    "规划者": "planner",
    "architect": "planner",
    "架构师": "planner",
    "builder": "builder",
    "建设者": "builder",
    "lab-builder": "builder",
    "evaluator": "evaluator",
    "审判官": "evaluator",
    "reviewer": "evaluator",
}


@dataclass(frozen=True)
class RoleProfile:
    title: str
    trigger: str
    use: str
    stop: str


PROFILES: dict[str, RoleProfile] = {
    "pm": RoleProfile(
        "PM requirements optimizer",
        "需求复杂、验收标准含糊、用户意图需要拆成可执行 issue 时。",
        "把用户问题改写成候选 local issue、验收 probes、风险/反例清单；只作为 PRD 质量检查，不写代码。",
        "PM 不得运行 --execute，不得替 Builder 生成实现。",
    ),
    "planner": RoleProfile(
        "Planner DAG optimizer",
        "DAG 边界、write_scope、并发切片、score gate 或 stop rules 需要更硬时。",
        "用 autoresearch.issue_loop 的 issue/score-gate 思路反审 task_graph：每个节点是否可独立验证、是否有清晰失败退出条件。",
        "Planner 只把建议写进 plan/task_graph；不得让 autoresearch 直接接管 Builder。",
    ),
    "builder": RoleProfile(
        "Builder execution optimizer",
        "实现轮次复杂、上一轮 FAIL、修复项可转成明确 local issue，或需要多轮评分门禁时。",
        "先 dry-run 生成/检查 local issue 计划；把 issue、命令、score gate 当作实现 checklist 和验证增强。",
        "除非用户明确授权并给出 --execute，否则不得启动 autoresearch 执行循环。",
    ),
    "evaluator": RoleProfile(
        "Evaluator review optimizer",
        "评估需要更强 evidence、反例、score gate、失败复现或修复建议结构化时。",
        "用 score-gate 思路补强 eval：每个 FAIL 要有证据、复现、期望分数/测试门禁和可交给 Builder 的 issue 化修复提示。",
        "Evaluator 不改代码，不运行 --execute；只把检查结果写进 eval.md/eval.json。",
    ),
}


GENERAL_PATTERNS = [
    r"\b(autoresearch|auto research|issue[- ]loop|local issue|score[- ]gate|passing score)\b",
    r"\b(task_graph|write_scope|acceptance|stop rules?|round|fail|review|eval|handoff)\b",
    r"验收|评分门禁|分数门禁|多轮|失败|修复|评审|反例|风险|并发边界|写范围",
]


ROLE_DEFAULT_ENABLED = {"pm", "planner", "builder", "evaluator"}
FAIL_STATUSES = {
    "failed",
    "failed_review",
    "blocked",
    "repair",
    "repairing",
    "reviewing",
}
FAIL_PHASE_PATTERNS = [
    r"fail",
    r"repair",
    r"blocked",
    r"retry",
    r"round",
    r"eval",
]


def normalize_role(role: str) -> str:
    lowered = role.strip().lower()
    for key, value in ROLE_MAP.items():
        if key.lower() in lowered:
            return value
    return lowered or "unknown"


def should_recommend(role: str, task: str) -> tuple[bool, list[str]]:
    canonical = normalize_role(role)
    text = f"{role}\n{task}".lower()
    reasons: list[str] = []
    if canonical in ROLE_DEFAULT_ENABLED:
        reasons.append(f"role:{canonical}")
    for pattern in GENERAL_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            reasons.append(f"pattern:{pattern}")
    return bool(reasons and canonical in PROFILES), reasons


def read_json_file(path: str | None) -> tuple[dict[str, Any], str]:
    if not path:
        return {}, ""
    p = Path(path).expanduser()
    if not p.exists():
        return {}, "missing"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - exact parse text is not stable.
        return {}, f"parse_error:{exc}"
    return data if isinstance(data, dict) else {"value": data}, ""


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def compact_item(item: Any) -> str:
    if isinstance(item, dict):
        for key in ("condition", "cond", "id", "name", "title", "message", "fix_hint", "evidence"):
            value = item.get(key)
            if value:
                return str(value)
        return json.dumps(item, ensure_ascii=False, sort_keys=True)[:220]
    return str(item)


def first_text(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if value is not None and value != "":
            return str(value)
    return ""


def parse_round(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def telemetry_snapshot(status_file: str | None, eval_json: str | None, eval_md: str | None) -> dict[str, Any]:
    status_data, status_error = read_json_file(status_file)
    eval_data, eval_error = read_json_file(eval_json)
    status = first_text(status_data, "status", "state")
    phase = first_text(status_data, "phase", "handoff_to", "target_role")
    round_no = parse_round(status_data.get("round") or status_data.get("repair_round") or status_data.get("review_round"))
    verdict = first_text(eval_data, "verdict", "overall", "status").upper()
    failed_conditions = [compact_item(x) for x in as_list(eval_data.get("failed_conditions"))]
    failed_conditions.extend(compact_item(x) for x in as_list(eval_data.get("failures")))
    errors = [compact_item(x) for x in as_list(eval_data.get("errors"))]
    warnings = [compact_item(x) for x in as_list(eval_data.get("warnings"))]
    eval_md_present = bool(eval_md and Path(eval_md).expanduser().exists())
    return {
        "status_file": status_file or "",
        "status_file_error": status_error,
        "eval_json": eval_json or "",
        "eval_json_error": eval_error,
        "eval_md": eval_md or "",
        "eval_md_present": eval_md_present,
        "status": status,
        "phase": phase,
        "round": round_no,
        "eval_verdict": verdict,
        "failed_conditions": failed_conditions[:12],
        "errors": errors[:12],
        "warnings": warnings[:12],
        "error_count": len(errors),
        "warning_count": len(warnings),
    }


def telemetry_triggers(telemetry: dict[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    status = telemetry.get("status", "").lower()
    phase = telemetry.get("phase", "").lower()
    verdict = telemetry.get("eval_verdict", "").upper()
    if status in FAIL_STATUSES or status.startswith("failed") or status.startswith("blocked"):
        reasons.append(f"status:{status}")
    if any(re.search(pattern, phase, re.IGNORECASE) for pattern in FAIL_PHASE_PATTERNS):
        reasons.append(f"phase:{phase}")
    if telemetry.get("round", 0) > 0:
        reasons.append(f"round:{telemetry['round']}")
    if verdict in {"FAIL", "FAILED", "ERROR", "NOT_READY", "NOT READY"}:
        reasons.append(f"eval_verdict:{verdict}")
    if telemetry.get("failed_conditions"):
        reasons.append(f"failed_conditions:{len(telemetry['failed_conditions'])}")
    if telemetry.get("error_count", 0) > 0:
        reasons.append(f"errors:{telemetry['error_count']}")
    if telemetry.get("status_file_error"):
        reasons.append(f"status_file:{telemetry['status_file_error']}")
    if telemetry.get("eval_json_error"):
        reasons.append(f"eval_json:{telemetry['eval_json_error']}")
    if any(reason.startswith(("eval_verdict:", "failed_conditions:", "errors:")) for reason in reasons):
        return "strong", reasons
    if reasons:
        return "recommended", reasons
    return "advisory", reasons


def quality_metrics(role: str, trigger_level: str) -> dict[str, Any]:
    canonical = normalize_role(role)
    expected_effect = {
        "pm": ["reduce_requirement_ambiguity", "surface_acceptance_gaps"],
        "planner": ["reduce_dag_rework", "harden_write_scope_and_stop_rules"],
        "builder": ["reduce_repair_rounds", "turn_eval_failures_into_local_issues"],
        "evaluator": ["improve_fail_reproducibility", "produce_builder_actionable_feedback"],
    }.get(canonical, ["improve_evidence_linkage"])
    return {
        "trigger_level": trigger_level,
        "expected_effect": expected_effect,
        "must_measure": [
            "repair_round_delta",
            "eval_failure_recurrence",
            "evidence_gap_count",
        ],
    }


def now_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def artifact_summary(payload: dict[str, Any]) -> dict[str, Any]:
    telemetry = payload.get("telemetry") or {}
    return {
        "recorded_at": now_utc(),
        "sid": payload.get("sid", ""),
        "role": payload.get("role", ""),
        "canonical_role": payload.get("canonical_role", ""),
        "recommended": bool(payload.get("recommended")),
        "trigger_level": payload.get("trigger_level", "advisory"),
        "reasons": (payload.get("reasons") or [])[:12],
        "telemetry": {
            "status": telemetry.get("status", ""),
            "phase": telemetry.get("phase", ""),
            "round": telemetry.get("round", 0),
            "eval_verdict": telemetry.get("eval_verdict", ""),
            "failed_conditions": (telemetry.get("failed_conditions") or [])[:8],
            "error_count": telemetry.get("error_count", 0),
            "warning_count": telemetry.get("warning_count", 0),
        },
        "quality_metrics": payload.get("quality_metrics") or {},
        "execution_policy": payload.get("execution_policy") or {},
    }


def record_status_artifact(status_file: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not status_file:
        return {"ok": False, "reason": "status_file_missing"}
    p = Path(status_file).expanduser()
    if not p.exists():
        return {"ok": False, "reason": "status_file_not_found", "status_file": str(p)}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "reason": "status_file_parse_error", "error": str(exc), "status_file": str(p)}
    if not isinstance(data, dict):
        return {"ok": False, "reason": "status_file_not_object", "status_file": str(p)}
    summary = artifact_summary(payload)
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, dict):
        artifacts = {}
    artifacts["autoresearch_optimizer"] = summary
    data["artifacts"] = artifacts
    data.setdefault("history", []).append({
        "ts": summary["recorded_at"],
        "event": "autoresearch_optimizer_recorded",
        "by": "coordinator",
        "trigger_level": summary["trigger_level"],
        "recommended": summary["recommended"],
        "role": summary["canonical_role"],
    })
    data["updated_at"] = summary["recorded_at"]
    tmp = p.with_name(f".{p.name}.autoresearch.tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, p)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    return {"ok": True, "status_file": str(p), "artifact": "autoresearch_optimizer"}


def advisory_payload(
    sid: str,
    role: str,
    task: str,
    status_file: str | None = None,
    eval_json: str | None = None,
    eval_md: str | None = None,
) -> dict[str, Any]:
    canonical = normalize_role(role)
    recommended, reasons = should_recommend(role, task)
    telemetry = telemetry_snapshot(status_file, eval_json, eval_md)
    trigger_level, telemetry_reasons = telemetry_triggers(telemetry)
    if telemetry_reasons and canonical in PROFILES:
        recommended = True
        reasons.extend(f"telemetry:{reason}" for reason in telemetry_reasons)
    profile = PROFILES.get(canonical)
    return {
        "ok": True,
        "sid": sid,
        "role": role,
        "canonical_role": canonical,
        "recommended": recommended,
        "reasons": reasons,
        "trigger_level": trigger_level,
        "telemetry": telemetry,
        "telemetry_reasons": telemetry_reasons,
        "quality_metrics": quality_metrics(role, trigger_level),
        "capabilities": [
            "autoresearch.pane_optimizer",
            "autoresearch.issue_loop",
            "autoresearch.score_gate",
        ] if recommended else [],
        "execution_policy": {
            "mode": "advisor_only_by_default",
            "default_command": "dry_run",
            "execute_requires": "--execute",
            "replaces_builder": False,
        },
        "profile": profile.__dict__ if profile else {},
    }


def render_markdown(payload: dict[str, Any]) -> str:
    if not payload.get("recommended"):
        return ""
    profile = payload.get("profile") or {}
    caps = ", ".join(payload.get("capabilities") or [])
    telemetry = payload.get("telemetry") or {}
    telemetry_lines = ""
    if payload.get("telemetry_reasons"):
        failed = telemetry.get("failed_conditions") or []
        failed_text = "\n".join(f"  - {item}" for item in failed[:5]) or "  - N/A"
        telemetry_lines = f"""
### Telemetry trigger

- Trigger level: {payload.get("trigger_level", "advisory")}
- Status/phase/round: {telemetry.get("status") or "N/A"} / {telemetry.get("phase") or "N/A"} / {telemetry.get("round", 0)}
- Eval verdict: {telemetry.get("eval_verdict") or "N/A"}
- Failed conditions:
{failed_text}
- Measurement: 记录 repair_round_delta、eval_failure_recurrence、evidence_gap_count，证明 autoresearch 是否真的降低返工。
"""
    return f"""## Autoresearch Pane Optimizer

Status: advisor_only
Capability: {caps}
Role fit: {profile.get("title", payload.get("canonical_role", "unknown"))}
Trigger level: {payload.get("trigger_level", "advisory")}

- When to use: {profile.get("trigger", "N/A")}
- How it improves this pane: {profile.get("use", "N/A")}
- Stop rule: {profile.get("stop", "N/A")}
- Execution gate: 默认只 dry-run；只有用户明确授权且命令包含 `--execute` 时，才允许运行 autoresearch 执行循环。
- Boundary: Autoresearch 不替代 PM/Planner/Builder/Evaluator；它只提供 issue 化拆解、score-gate、反例/风险和验证增强建议。
{telemetry_lines}
"""


def main() -> int:
    ap = argparse.ArgumentParser(prog="autoresearch_pane_optimizer.py")
    ap.add_argument("--sid", default="")
    ap.add_argument("--role", required=True)
    ap.add_argument("--task", required=True)
    ap.add_argument("--status-file", default="")
    ap.add_argument("--eval-json", default="")
    ap.add_argument("--eval-md", default="")
    ap.add_argument("--record-status", action="store_true", help="Fail-open update status.json artifacts/history with optimizer telemetry")
    ap.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = ap.parse_args()

    payload = advisory_payload(args.sid, args.role, args.task, args.status_file, args.eval_json, args.eval_md)
    if args.record_status:
        payload["record_status"] = record_status_artifact(args.status_file, payload)
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        text = render_markdown(payload)
        if text:
            print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
