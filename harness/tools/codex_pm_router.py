#!/usr/bin/env python3
"""Codex PM Router for three request classes.

Compiles a user request into a structured PM intake package that can feed
Codex-side skill workflows and downstream solar-harness PRD/contract/DAG
generation.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

HARNESS_ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = HARNESS_ROOT / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from requirement_coverage import (
    build_acceptance_verdict,
    build_coverage_report,
    build_requirement_trace,
    enrich_task_graph_defaults,
)
from apo_plan_compiler import build_capsule_plan_ir
from capability_capsules import default_capability_plan_for_logical_operator
from autosci_intake_contract import (
    WORKFLOW_CONTRACT_ID as AUTOSCI_WORKFLOW_CONTRACT_ID,
    build_autosci_task_graph,
    is_autosci_research_intake_text,
)
from intent_gateway import infer_mode as infer_intent_mode
from research.source_pack import CANONICAL_SOURCE_TYPES

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


SHORT_IMPL = "short_impl"
FULL_SPEC = "full_spec"
RESEARCH = "research"
MAX_REQUEST_CHARS = 12_000
# A RawIntent consumer envelope carries the same bounded request in up to
# three semantic sections (objective, problem, and raw user intent), plus
# metadata and policy sections. Bound that transport representation
# separately so legitimate 12,000-character requests remain admissible while
# malformed or padded envelopes cannot bypass the direct-request limit.
MAX_RAWINTENT_ENVELOPE_CHARS = MAX_REQUEST_CHARS * 4
CLASS_TO_CANONICAL = {
    SHORT_IMPL: "implementation",
    FULL_SPEC: "full_prd",
    RESEARCH: "research",
}
CODE_UNDERSTANDING_TOKENS = (
    "knowledge graph",
    "knowledge-graph",
    "codebase index",
    "codebase-index",
    "codebase indexing",
    "codebase-indexing",
    "code understanding",
    "code-understanding",
    "architecture map",
    "architecture-map",
    "onboarding",
    "repo map",
    "repository understanding",
    "代码库理解",
    "知识图",
    "架构图",
    "onboard",
)
PARALLEL_SPEC_TOKENS = (
    "convergence",
    "productization",
    "blueprint",
    "traceability",
    "收口",
    "产品化",
    "蓝图",
    "追踪矩阵",
)

RAWINTENT_SECTION_HEADERS = (
    "Source",
    "Rewritten Objective",
    "Problem",
    "Constraints",
    "Acceptance",
    "Raw User Intent",
)
RAWINTENT_METADATA_PREFIXES = (
    "intent_id:",
    "channel:",
    "actor:",
    "device:",
    "thread_ref:",
    "session_id:",
    "source-channel:",
    "source_trust:",
    "source-trust:",
    "sprint_id:",
    "node_id:",
    "role:",
)


class RequestTooLargeError(ValueError):
    """Raised when the direct compiler receives more text than it admits."""

    def __init__(self, actual_chars: int, max_chars: int = MAX_REQUEST_CHARS) -> None:
        self.actual_chars = actual_chars
        self.max_chars = max_chars
        super().__init__(
            f"request_too_long: request contains {actual_chars} characters; "
            f"maximum is {max_chars}"
        )


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _yaml_text(data: Any) -> str:
    if yaml is not None:
        return yaml.safe_dump(
            data,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )
    return json.dumps(data, ensure_ascii=False, indent=2)


def _fs_path(path: Path) -> str:
    resolved = str(Path(path).resolve(strict=False))
    if os.name != "nt" or resolved.startswith("\\\\?\\"):
        return resolved
    if resolved.startswith("\\\\"):
        return "\\\\?\\UNC\\" + resolved.lstrip("\\")
    return "\\\\?\\" + resolved


def _write_text(path: Path, content: str) -> None:
    os.makedirs(_fs_path(path.parent), exist_ok=True)
    with open(_fs_path(path), "w", encoding="utf-8") as handle:
        handle.write(content)


def _write_json(path: Path, payload: Any) -> None:
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _write_yaml(path: Path, payload: Any) -> None:
    _write_text(path, _yaml_text(payload))


def _safe_title(text: str) -> str:
    line = next((line.strip() for line in text.splitlines() if line.strip()), "").strip(" -:#")
    return line[:80] or "Untitled Request"


def _strip_yaml_frontmatter(text: str) -> str:
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        return text
    lines = stripped.splitlines()
    if len(lines) < 3 or lines[0].strip() != "---":
        return text
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "\n".join(lines[index + 1 :]).strip()
    return text


def _extract_markdown_section(text: str, heading: str) -> str:
    pattern = rf"(?ims)^\s*##\s+{re.escape(heading)}\s*$\n(.*?)(?=^\s*##\s+|\Z)"
    match = re.search(pattern, text)
    return match.group(1).strip() if match else ""


def _is_rawintent_consumer_envelope(text: str) -> bool:
    return bool(
        re.search(
            r"(?im)^\s*#\s+RawIntent Consumer Request(?:\s+-.*)?\s*$",
            text,
        )
    )


def _collapse_goal_text(text: str) -> str:
    lines: list[str] = []
    for raw_line in _strip_yaml_frontmatter(text).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower = line.lower()
        if line in {"[entrypoint_metadata]", "[raw_request]"}:
            continue
        if line.startswith("```") or line.startswith("---"):
            continue
        if lower.startswith(RAWINTENT_METADATA_PREFIXES):
            continue
        if re.fullmatch(r"#+\s*(?:RawIntent Consumer Request|Source|Rewritten Objective|Problem|Constraints|Acceptance|Raw User Intent)\s*", line, re.I):
            continue
        line = re.sub(r"^#+\s*", "", line).strip()
        if not line:
            continue
        lines.append(line)
    collapsed = re.sub(r"\s+", " ", " ".join(lines)).strip()
    return collapsed


def _extract_effective_request_text(text: str) -> dict[str, str]:
    whole = _collapse_goal_text(text)
    if not _is_rawintent_consumer_envelope(text):
        return {
            "effective_text": whole,
            "goal_text": whole,
            "problem_text": whole,
            "raw_user_text": whole,
        }

    objective = _collapse_goal_text(_extract_markdown_section(text, "Rewritten Objective"))
    problem = _collapse_goal_text(_extract_markdown_section(text, "Problem"))
    raw_user_intent = _collapse_goal_text(_extract_markdown_section(text, "Raw User Intent"))
    effective = raw_user_intent or problem or objective or whole
    goal = objective or problem or raw_user_intent or effective
    return {
        "effective_text": effective,
        "goal_text": goal,
        "problem_text": problem or effective,
        "raw_user_text": raw_user_intent or effective,
    }


def _extract_labeled_value(text: str, label: str) -> str:
    """Return the first explicit ``Label: value`` line from user text.

    RawIntent envelopes can repeat the user's request in multiple sections.  A
    line-oriented parser keeps paths and commands intact instead of trying to
    recover them from the normalized, whitespace-collapsed goal summary.
    """

    match = re.search(rf"(?im)^\s*{re.escape(label)}\s*:\s*(.+?)\s*$", text)
    if not match:
        return ""
    return match.group(1).strip().strip("`\"'")


def _extract_execution_contract(text: str) -> dict[str, Any]:
    project_dir = _extract_labeled_value(text, "Target repository path")
    if not project_dir:
        project_dir = _extract_labeled_value(text, "Project")

    scope = _extract_labeled_value(text, "Scope")
    constraints = _extract_labeled_value(text, "Constraints")
    acceptance = _extract_labeled_value(text, "Acceptance")

    allowed_paths: list[str] = []
    scope_tokens = re.findall(
        r"(?<![\w.-])([\w.-]+(?:/[\w.*-]+)*\.(?:py|js|ts|tsx|jsx|rs|go|java|kt|rb|php|cs|cpp|cc|c|h|md|json|ya?ml|toml))\b",
        scope,
        flags=re.I,
    )
    for token in scope_tokens:
        if token not in allowed_paths:
            allowed_paths.append(token)
    if re.search(r"\b(?:update|modify|change|edit)\s+(?:the\s+)?tests?\b", scope, re.I):
        allowed_paths.append("tests/**")

    test_commands = [
        command.strip()
        for command in re.findall(r"`([^`]*(?:pytest|unittest|npm\s+test|pnpm\s+test|cargo\s+test|go\s+test)[^`]*)`", acceptance, re.I)
        if command.strip()
    ]
    return {
        "project_dir": project_dir,
        "allowed_paths": allowed_paths,
        "constraints": [item.strip() for item in constraints.split(",") if item.strip()],
        "acceptance": acceptance,
        "test_commands": test_commands,
        "scope": scope,
    }


def _enforce_request_size(text: str) -> None:
    if len(text) > MAX_REQUEST_CHARS:
        raise RequestTooLargeError(len(text))


def _looks_like_raw_metadata_pollution(text: str) -> bool:
    lowered = text.lower()
    suspicious_tokens = (
        "# rawintent consumer request",
        "## source",
        "[entrypoint_metadata]",
        "[raw_request]",
        "intent_id:",
        "thread_ref:",
    )
    return any(token in lowered for token in suspicious_tokens)


def _derive_confidence(request_type: str, text: str, papers: list[str]) -> float:
    normalized = _normalized_text(text)
    if request_type == SHORT_IMPL:
        return 0.86 if len(normalized) < 200 else 0.79
    if request_type == RESEARCH:
        return 0.9 if papers else 0.72
    if re.search(r"(metric|指标|success|acceptance|scope|non-goal)", normalized, re.I):
        return 0.84
    return 0.73


def _derive_assumptions(request_type: str, lane_hint: str) -> list[str]:
    assumptions = [
        "PM 产物需要兼容 solar-harness 现有 PM -> Planner -> Builder 主链。",
        "Markdown PRD / contract 是编译视图，不是唯一事实源。",
    ]
    if request_type == SHORT_IMPL:
        assumptions.append("短实现类请求默认优先最小改动和 verifier gate。")
    if request_type == FULL_SPEC:
        assumptions.append("完整需求默认先保证正确性、可验证性和风险前置。")
    if request_type == RESEARCH:
        assumptions.append("研究类请求默认要求 evidence ledger 和 verifier gate。")
    if lane_hint == "strategy":
        assumptions.append("涉及架构/迁移/兼容时默认进入 strategy lane。")
    return assumptions


def _derive_open_questions(request_type: str, text: str, papers: list[str]) -> list[str]:
    questions: list[str] = []
    if ("优化 DAG" in text or "optimize dag" in text.lower()) and "wall-clock" not in text.lower():
        questions.append("DAG 优化优先级是否应默认按 正确性 > 可验证性 > 风险前置 > 并行度 > wall-clock 时间 排序？")
    if request_type == FULL_SPEC and not re.search(r"(metric|指标|success|acceptance)", text, re.I):
        questions.append("当前请求缺少显式 success metric，需在 PRD 中补齐。")
    if request_type == RESEARCH and not papers:
        questions.append("研究类请求尚未附具体 paper inventory，后续需要补充来源证据。")
    if "人工审批" in text and "全自动" in text:
        questions.append("全自动执行与 destructive 操作人工审批存在冲突，需要明确优先级。")
    return questions


def _derive_risk_register(request_type: str) -> list[dict[str, str]]:
    risks = [
        {
            "id": "R1",
            "level": "medium",
            "title": "PRD / contract / DAG 多份产物漂移",
            "mitigation": "用 Requirement IR 做唯一事实源，所有视图从 IR 编译。",
        },
        {
            "id": "R2",
            "level": "medium",
            "title": "原始需求直接派给 Builder 导致执行发散",
            "mitigation": "强制走 product-brief / planner handoff，不允许 raw request 直派 builder。",
        },
    ]
    if request_type == RESEARCH:
        risks.append(
            {
                "id": "R3",
                "level": "high",
                "title": "研究结论缺证据链就进入实现",
                "mitigation": "Research mode 强制 evidence ledger 和 review gate。",
            }
        )
    else:
        risks.append(
            {
                "id": "R3",
                "level": "medium",
                "title": "验收标准没有映射到验证步骤",
                "mitigation": "编译期做 acceptance coverage 检查，缺失时阻断派单。",
            }
        )
    return risks


def _default_acceptance(request_type: str) -> list[str]:
    if request_type == SHORT_IMPL:
        return [
            "目标变更在声明范围内完成。",
            "至少一条测试/执行证据被记录。",
            "存在独立 verifier 决策。",
        ]
    if request_type == RESEARCH:
        return [
            "paper/source inventory 完整可追溯。",
            "claim -> evidence -> implication 映射完整。",
            "研究结论具备 adoption/rejection criteria。",
        ]
    return [
        "PRD、contract、TaskDAG 互相对齐。",
        "实施、验证、兼容/发布路径均已显式表达。",
        "每条验收标准都能追溯到验证或 gate。",
    ]


def _default_non_goals(request_type: str) -> list[str]:
    if request_type == SHORT_IMPL:
        return [
            "不做无关架构重写。",
            "不默认引入新的生产依赖。",
        ]
    if request_type == RESEARCH:
        return [
            "不把论文总结直接当作实现结论。",
            "不在缺证据时进入生产实现。",
        ]
    return [
        "不在首批交付中做完整四区 PM pane 重构。",
        "不绕过 planner 直接进入 builder。",
    ]


def _default_stop_rules(request_type: str) -> list[str]:
    rules = [
        "缺少可验证 acceptance 不得标记为完成。",
        "缺少 verifier 决策不得进入 DONE。",
    ]
    if request_type == RESEARCH:
        rules.append("缺少 evidence ledger 或 critique gate 时不得推进到 adoption。")
    return rules


def _is_code_understanding_request(text: str, repo_context: list[str] | None = None) -> bool:
    haystack = " ".join([str(text or ""), *[str(x) for x in (repo_context or [])]]).lower()
    return any(token in haystack for token in CODE_UNDERSTANDING_TOKENS)


def _is_parallel_spec_request(request_type: str, text: str) -> bool:
    if request_type != FULL_SPEC:
        return False
    normalized = _normalized_text(text)
    lowered = normalized.lower()
    return any(token in lowered or token in normalized for token in PARALLEL_SPEC_TOKENS)


def _is_parallel_delivery_request(request_type: str, text: str) -> bool:
    if request_type != FULL_SPEC:
        return False
    normalized = _normalized_text(text)
    lowered = normalized.lower()
    return bool(
        re.search(r"\bp0\b|\bp1\b", lowered)
        or any(token in normalized for token in ("修复单", "架构整改单", "整改单"))
        or any(token in lowered for token in ("bug", "fix", "repair", "hotfix", "reliability"))
    )


def _adapt_graph_for_code_understanding(graph: dict[str, Any], request_type: str) -> dict[str, Any]:
    adapted = json.loads(json.dumps(graph, ensure_ascii=False))
    by_id = {str(node.get("id") or ""): node for node in adapted.get("nodes") or [] if isinstance(node, dict)}
    if request_type == RESEARCH:
        if "R1" in by_id:
            by_id["R1"]["goal"] = "Ingest repo context and build a codebase knowledge graph, onboarding map, and source manifest for the target repository."
            by_id["R1"]["acceptance"] = ["Knowledge graph inputs and source manifest are recorded."]
        if "R2" in by_id:
            by_id["R2"]["goal"] = "Extract architecture map, module boundaries, key entrypoints, and technical levers from the codebase."
            by_id["R2"]["acceptance"] = ["Architecture map and module-level findings are produced."]
        if "R4" in by_id:
            by_id["R4"]["goal"] = "Synthesize codebase understanding into onboarding guidance and actionable architecture insights."
            by_id["R4"]["acceptance"] = ["Onboarding and architecture synthesis is drafted."]
        if "R6" in by_id:
            by_id["R6"]["goal"] = "Translate codebase understanding into implementation, PRD, and task-graph implications."
    else:
        if "S1" in by_id:
            by_id["S1"]["goal"] = "Lock code-understanding scope, repo boundaries, and knowledge-graph/onboarding deliverables."
            by_id["S1"]["acceptance"] = ["Codebase-understanding path and deliverables are explicit."]
        if "S2" in by_id:
            by_id["S2"]["logical_operator"] = "ResearchScout"
            by_id["S2"]["goal"] = "Generate the codebase knowledge graph, architecture map, and onboarding artifacts for the approved repository scope."
            by_id["S2"]["acceptance"] = ["Knowledge graph and onboarding artifacts are produced within declared scope."]
        if "S3" in by_id:
            by_id["S3"]["goal"] = "Verify knowledge-graph, meta, chunk-manifest, and resume-state artifacts."
            by_id["S3"]["acceptance"] = ["Artifact verification evidence is attached."]
        if "S4" in by_id:
            by_id["S4"]["goal"] = "Perform independent review of the code-understanding artifacts and closeout decision."
    return adapted


def _node_enrichment(request_type: str, lane_hint: str, node: dict[str, Any]) -> dict[str, Any]:
    owner = "subagent" if request_type == RESEARCH and node["logical_operator"] in {"ResearchScout", "ResearchSynthesizer", "ArtifactCurator"} else ("solar-harness" if node["logical_operator"] in {"Verifier", "Critic"} else "codex")
    node_type_map = {
        "DeepArchitect": "design",
        "ImplementationWorker": "implementation",
        "TestRunner": "test",
        "Verifier": "review",
        "Critic": "review",
        "ResearchScout": "research",
        "ResearchSynthesizer": "research",
        "ArtifactCurator": "release",
    }
    validation_target = {
        "S1": "patch.diff",
        "S2": "test_report.md",
        "S3": "review_decision.yaml",
        "S4": "review_decision.yaml",
        "S5": "rollout_notes.md",
        "R1": "source_manifest.json",
        "R2": "claims.jsonl",
        "R3": "contradictions.jsonl",
        "R4": "synthesis.md",
        "R5": "critique.md",
        "R6": "final_prd_implications.md",
    }.get(node["id"], "artifact.md")
    enriched = dict(node)
    enriched.setdefault("type", node_type_map.get(node["logical_operator"], "spec"))
    enriched.setdefault("owner", owner)
    enriched.setdefault("inputs", ["requirement_ir.json"] if not node.get("depends_on") else ["upstream_artifact"])
    enriched.setdefault("outputs", [validation_target])
    enriched.setdefault(
        "validation",
        [
            {"kind": "artifact", "target": output, "required": True}
            for output in enriched.get("outputs") or [validation_target]
        ],
    )
    enriched.setdefault("risk", "high" if node["logical_operator"] in {"Verifier", "Critic"} else ("medium" if request_type != SHORT_IMPL else "low"))
    enriched.setdefault("uncertainty", 0.2 if request_type == SHORT_IMPL else (0.45 if request_type == FULL_SPEC else 0.55))
    enriched.setdefault("parallelizable", request_type != SHORT_IMPL and node["logical_operator"] not in {"Verifier", "Critic"})
    enriched.setdefault("approval_gate", node["logical_operator"] in {"Verifier", "Critic"})
    capability_plan = default_capability_plan_for_logical_operator(
        str(node.get("logical_operator") or ""),
        request_type=CLASS_TO_CANONICAL.get(request_type, request_type),
        lane_hint=lane_hint,
        node=node,
        registry_path=HARNESS_ROOT / "config" / "capability-capsules.registry.yaml",
    )
    if capability_plan:
        enriched.setdefault("capability_native", True)
        enriched.setdefault("capability_capsule_id", capability_plan["capability_capsule_id"])
        dispatch_task_type = capability_plan.get("dispatch_task_type") or enriched.get("type", "spec")
        enriched.setdefault("dispatch_task_type", dispatch_task_type)
        if capability_plan.get("capability_capsule_id") == "cap.understand-anything-indexer":
            enriched["type"] = "code-understanding"
            enriched["signals"] = sorted(
                {
                    *[str(x) for x in (enriched.get("signals") or [])],
                    "code-understanding",
                    "knowledge-graph",
                    "onboarding",
                    "architecture-map",
                }
            )
            enriched["outputs"] = ["knowledge-graph.json", "meta.json", "chunk-manifest.json", "resume-state.json"]
            enriched["validation"] = [
                {"kind": "artifact", "target": "knowledge-graph.json", "required": True},
                {"kind": "artifact", "target": "meta.json", "required": True},
                {"kind": "artifact", "target": "chunk-manifest.json", "required": True},
                {"kind": "artifact", "target": "resume-state.json", "required": True},
            ]
        elif enriched.get("type") == "research" and dispatch_task_type in {"code-understanding", "codebase-indexing"}:
            enriched["type"] = str(dispatch_task_type)
        enriched.setdefault("capsule_plan", capability_plan)
    return enriched


def _build_requirement_items(
    normalized_goal: str,
    acceptance: list[str],
    priority: str,
) -> list[dict[str, Any]]:
    items = [
        {
            "id": "REQ-000",
            "source_text": normalized_goal,
            "success_criteria": [normalized_goal],
            "verification_method": "task_graph_closeout",
            "priority": priority,
        }
    ]
    for index, item in enumerate(acceptance, start=1):
        items.append(
            {
                "id": f"REQ-{index:03d}",
                "source_text": item,
                "success_criteria": [item],
                "verification_method": "acceptance_evidence",
                "priority": priority,
            }
        )
    return items


def _apply_requirement_mapping(
    graph: dict[str, Any],
    requirements: list[dict[str, Any]],
    request_type: str,
) -> dict[str, Any]:
    mapped = dict(graph)
    nodes = [dict(node) for node in mapped.get("nodes") or []]
    goal_req = requirements[:1]
    acceptance_reqs = requirements[1:] or requirements[:1]
    all_req_ids = [item["id"] for item in requirements]
    goal_req_ids = [item["id"] for item in goal_req]
    acceptance_req_ids = [item["id"] for item in acceptance_reqs]

    root_ops = {"DeepArchitect", "ResearchScout"}
    terminal_ops = {"Verifier", "Critic", "ArtifactCurator"}
    execution_ops = {"ImplementationWorker", "TestRunner", "ResearchSynthesizer"}

    for node in nodes:
        op = str(node.get("logical_operator") or "")
        if op in root_ops:
            node["requirement_ids"] = all_req_ids
        elif op in execution_ops:
            node["requirement_ids"] = acceptance_req_ids
        elif op in terminal_ops:
            node["requirement_ids"] = all_req_ids
        else:
            node["requirement_ids"] = goal_req_ids
        if request_type == RESEARCH and op == "ResearchScout" and not node.get("depends_on"):
            node["requirement_ids"] = goal_req_ids
    mapped["nodes"] = nodes
    return mapped


def _make_prd_view(
    request_type: str,
    normalized_goal: str,
    source_inputs: dict[str, Any],
    acceptance: list[str],
    non_goals: list[str],
    open_questions: list[str],
    risks: list[dict[str, str]],
) -> dict[str, Any]:
    acceptance_body = "\n".join(f"- {item}" for item in acceptance) or "- N/A"
    non_goals_body = "\n".join(f"- {item}" for item in non_goals) or "- N/A"
    open_questions_body = "\n".join(f"- {item}" for item in open_questions) or "- N/A"
    risks_body = "\n".join(
        f"- [{risk['level']}] {risk['title']} -> {risk['mitigation']}" for risk in risks
    ) or "- N/A"
    source_context = (
        "相关上下文: " + ", ".join(source_inputs["repo_context"] + source_inputs["logs"])
        if source_inputs["repo_context"] or source_inputs["logs"]
        else "基于当前请求直接定位到交付范围。"
    )
    if request_type == "implementation":
        sections = [
            {"title": "背景 / Context", "body": source_context},
            {"title": "用户问题 / Problem", "body": normalized_goal},
            {"title": "用户目标 / Goals", "body": f"- {normalized_goal}"},
            {"title": "用户故事 / User Stories", "body": f"- As the requester, I need {normalized_goal} so the result is directly usable and verifiable."},
            {"title": "功能需求 / Requirements", "body": acceptance_body},
            {"title": "验收标准 / Acceptance Criteria", "body": acceptance_body},
            {"title": "非目标 / Non-Goals", "body": non_goals_body},
            {"title": "约束 / Constraints", "body": "- Keep changes inside the declared sprint workspace and write scope.\n- Builder execution must go through task_graph dispatch.\n- Record evaluator-visible execution evidence before closeout."},
            {"title": "风险 / Risks", "body": risks_body},
            {"title": "开放问题 / Open Questions", "body": open_questions_body},
            {"title": "架构交接 / Planner Handoff", "body": "Planner must preserve the declared write scope, map every acceptance criterion to a graph node, and require executable verification before builder closeout."},
            {"title": "Scope", "body": f"- {normalized_goal}"},
            {"title": "Validation", "body": "- 运行测试或 smoke check\n- 记录 diff / 风险 / 验证证据"},
            {"title": "Rollback", "body": "如验证失败，回退到变更前状态并保留失败证据。"},
        ]
        return {"variant": "short", "sections": sections}
    if request_type == "research":
        sections = [
            {"title": "背景 / Context", "body": "The request requires source-backed research rather than unsupported model recall."},
            {"title": "用户问题 / Problem", "body": normalized_goal},
            {"title": "用户目标 / Goals", "body": f"- Produce a traceable, evidence-backed answer to: {normalized_goal}"},
            {"title": "用户故事 / User Stories", "body": "- As the requester, I need claims tied to inspectable sources so I can distinguish evidence from synthesis."},
            {"title": "功能需求 / Requirements", "body": "- Inventory relevant sources.\n- Extract claims and supporting evidence.\n- Preserve provenance and confidence.\n- Synthesize only from verified evidence."},
            {"title": "验收标准 / Acceptance Criteria", "body": acceptance_body},
            {"title": "非目标 / Non-Goals", "body": non_goals_body},
            {"title": "约束 / Constraints", "body": "- Requirement IR remains the source of truth.\n- Every material claim must resolve to source evidence.\n- Unsupported claims must be omitted or labeled as unresolved."},
            {"title": "风险 / Risks", "body": risks_body},
            {"title": "开放问题 / Open Questions", "body": open_questions_body},
            {"title": "架构交接 / Planner Handoff", "body": "Planner must convert the source, evidence, synthesis, and verification stages into an acyclic research DAG with explicit artifacts and closeout gates."},
            {"title": "Research Question", "body": normalized_goal},
            {"title": "Paper Inventory", "body": "\n".join(f"- {paper}" for paper in source_inputs["papers"]) or "- 待补充来源"},
            {"title": "Claim Extraction", "body": "对每篇论文提取核心 claim、方法、benchmark、限制条件。"},
            {"title": "Evidence Map", "body": "每个 engineering implication 都必须绑定 source + evidence + confidence。"},
            {"title": "Relevance to Our System", "body": "输出对 Codex / solar-harness / PM pane 的工程含义。"},
            {"title": "Design Candidates", "body": "基于证据链生成候选设计方案，并明确 pros / cons。"},
            {"title": "Experiment Plan", "body": "定义 baseline、metric、threshold 和失败退出条件。"},
            {"title": "Build Plan", "body": "只有通过 eval gate 的研究结论才能进入实现 DAG。"},
            {"title": "Adoption Criteria", "body": acceptance_body},
            {"title": "Rejection Criteria", "body": risks_body},
        ]
        return {"variant": "research", "sections": sections}
    sections = [
        {"title": "背景 / Context", "body": "Compiled from RawIntent into Requirement IR, contract artifacts, and a dispatchable task graph."},
        {"title": "用户问题 / Problem", "body": normalized_goal},
        {"title": "用户目标 / Goals", "body": "- " + normalized_goal},
        {"title": "用户故事 / User Stories", "body": "- As the Solar operator, I need the request structured into PM, Planner, Builder, and Evaluator handoffs so execution stays inside the product workflow."},
        {"title": "功能需求 / Requirements", "body": "\n".join(f"- {item}" for item in acceptance)},
        {"title": "验收标准 / Acceptance Criteria", "body": "\n".join(f"- {item}" for item in acceptance)},
        {"title": "非目标 / Non-Goals", "body": "\n".join(f"- {item}" for item in non_goals)},
        {"title": "约束 / Constraints", "body": "- Requirement IR remains the source of truth.\n- Builder execution must go through task_graph dispatch.\n- Evaluator-visible evidence is required before closeout."},
        {"title": "风险 / Risks", "body": "\n".join(f"- [{risk['level']}] {risk['title']} -> {risk['mitigation']}" for risk in risks)},
        {"title": "开放问题 / Open Questions", "body": "\n".join(f"- {item}" for item in open_questions) if open_questions else "- N/A"},
        {"title": "架构交接 / Planner Handoff", "body": "Planner must use `requirement_ir.json`, `contract.md`, and `task_graph.json` to verify DAG boundaries, write scopes, gates, and evaluator evidence requirements before builder execution."},
    ]
    return {"variant": "standard", "sections": sections}


def _build_contracts(
    classification: str,
    normalized_goal: str,
    acceptance: list[str],
    non_goals: list[str],
    stop_rules: list[str],
    request_text: str,
    papers: list[str],
) -> dict[str, Any]:
    declared_execution = _extract_execution_contract(request_text)
    product = {
        "enabled": True,
        "goal": normalized_goal,
        "success_metrics": acceptance,
        "non_goals": non_goals,
        "acceptance": acceptance,
        "stop_rules": stop_rules,
    }
    interface = {
        "enabled": True,
        "name": "RequirementCompilerAdapters",
        "version": "1.0",
        "inputs": ["RequirementIR"],
        "outputs": ["ProductBrief", "ContractsBundle", "TaskDAG", "HandoffPackage"],
        "invariants": [
            "Requirement IR is the only source of truth.",
            "DAG nodes[*].id must be unique.",
            "Every acceptance criterion maps to at least one validation step.",
        ],
        "errors": [
            {"code": "CYCLE_DETECTED", "action": "split dependencies or ask for clarification"},
            {"code": "ACCEPTANCE_COVERAGE_MISSING", "action": "add validation before dispatch"},
        ],
    }
    allowed_paths = declared_execution["allowed_paths"] or [
        "apps/pm-pane/**",
        "packages/requirement-ir/**",
        "harness/**",
    ]
    agent_execution = {
        "enabled": True,
        "task_scope": CLASS_TO_CANONICAL[classification],
        "project_dir": declared_execution["project_dir"],
        "allowed_paths": allowed_paths,
        "forbidden_paths": ["infra/prod/**", ".env*", "secrets/**"],
        "commands": {
            "test": declared_execution["test_commands"] or ["pnpm test", "pnpm lint"],
            "inspect": ["rg", "python3", "pytest"],
        },
        "declared_constraints": declared_execution["constraints"],
        "declared_scope": declared_execution["scope"],
        "approval_required_when": [
            "new production dependency",
            "database migration",
            "network access",
            "touching auth or billing",
        ],
        "stop_conditions": stop_rules,
    }
    research = {
        "enabled": classification == RESEARCH,
        "question": normalized_goal if classification == RESEARCH else "",
        "hypothesis": normalized_goal,
        "source_papers": papers,
        "evidence_contract": {
            "source_pack": ["sources.jsonl", "evidence.jsonl", "extracts/"],
            "report_artifacts": [
                "sources.jsonl",
                "evidence.jsonl",
                "extracts/",
                "synthesis_plan.json",
                "evidence_gaps.json",
                "claims.jsonl",
                "claim_evidence.jsonl",
                "sections.jsonl",
                "section_checks.jsonl",
                "report_ast.json",
                "final.bibliography.json",
                "final.md",
                "research_eval.json",
            ],
            "citation_syntax": "[cite:ev_<id>]",
            "source_type_vocabulary": list(CANONICAL_SOURCE_TYPES),
        } if classification == RESEARCH else {},
        "quality_gates": [
            "Each retrieval source pack passes deterministic retrieval closeout.",
            "Every material factual claim resolves to verified evidence spans.",
            "The consolidated report passes deterministic final closeout.",
        ] if classification == RESEARCH else [],
        "failure_policy": {
            "fabricate_missing_evidence": False,
            "insufficient_evidence": "state_bounded_gap_or_fail",
            "retrieval_failure": "repair_or_fail",
        } if classification == RESEARCH else {},
        "rejection_criteria": [
            "No provenance-complete source pack is available.",
            "A material claim lacks resolvable evidence.",
            "The deterministic retrieval or final closeout gate fails.",
        ] if classification == RESEARCH else [],
    }
    return {
        "product": product,
        "interface": interface,
        "agent_execution": agent_execution,
        "research": research,
        "bundle": {
            "schema_version": "solar.contract_bundle.v1",
            "request_type": CLASS_TO_CANONICAL[classification],
            "source_of_truth": "requirement_ir.json",
            "contracts": {
                "product": product,
                "interface": interface,
                "agent_execution": agent_execution,
                "research": research,
            },
            "request_excerpt": request_text[:240],
        },
    }


def _render_prd_markdown(title: str, prd_view: dict[str, Any]) -> str:
    lines = [f"# {title}", ""]
    for section in prd_view["sections"]:
        lines.append(f"## {section['title']}")
        lines.append(section["body"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_contract_markdown(title: str, contracts: dict[str, Any]) -> str:
    product = contracts["product"]
    interface = contracts["interface"]
    agent = contracts["agent_execution"]
    research = contracts["research"]
    lines = [
        f"# Compiled Contract — {title}",
        "",
        *([f"Project: {agent['project_dir']}", ""] if agent.get("project_dir") else []),
        "## Canonical Sources",
        "",
        "- `requirement_ir.json` is the source of truth.",
        "- `contracts/*.yaml` are canonical structured contracts.",
        "- `.contract.md` is a compiled human-readable view.",
        "",
        "## Product Contract",
        "",
        f"- goal: {product['goal']}",
        "- success_metrics:",
        *[f"  - {item}" for item in product["success_metrics"]],
        "- non_goals:",
        *[f"  - {item}" for item in product["non_goals"]],
        "",
        "## Interface Contract",
        "",
        f"- name: {interface['name']}",
        f"- version: {interface['version']}",
        "- invariants:",
        *[f"  - {item}" for item in interface["invariants"]],
        "",
        "## Agent Execution Contract",
        "",
        "- allowed_paths:",
        *[f"  - {item}" for item in agent["allowed_paths"]],
        "- test_commands:",
        *[f"  - {item}" for item in agent.get("commands", {}).get("test", [])],
        "- declared_constraints:",
        *[f"  - {item}" for item in agent.get("declared_constraints", [])],
        "- forbidden_paths:",
        *[f"  - {item}" for item in agent["forbidden_paths"]],
        "- approval_required_when:",
        *[f"  - {item}" for item in agent["approval_required_when"]],
        "- stop_conditions:",
        *[f"  - {item}" for item in agent["stop_conditions"]],
    ]
    if research.get("enabled"):
        lines.extend(
            [
                "",
                "## Research Contract",
                "",
                f"- hypothesis: {research['hypothesis']}",
                "- source_papers:",
                *[f"  - {item}" for item in research["source_papers"]],
                "- rejection_criteria:",
                *[f"  - {item}" for item in research["rejection_criteria"]],
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _render_handoff_markdown(
    title: str,
    target: str,
    goal: str,
    artifacts: list[str],
    acceptance: list[str],
    constraints: list[str],
) -> str:
    lines = [
        f"# {target} Handoff — {title}",
        "",
        "## Goal",
        "",
        goal,
        "",
        "## Read First",
        "",
        *[f"- {item}" for item in artifacts],
        "",
        "## Constraints",
        "",
        *[f"- {item}" for item in constraints],
        "",
        "## Acceptance",
        "",
        *[f"- {item}" for item in acceptance],
        "",
    ]
    return "\n".join(lines)


def _sprint_handoff_artifacts(sprint_id: str, target: str) -> list[str]:
    if sprint_id and sprint_id != "N/A":
        artifacts = [
            f"{sprint_id}.requirement_ir.json",
            f"{sprint_id}.prd.md",
            f"{sprint_id}.Contracts.yaml",
            f"{sprint_id}.task_graph.json",
        ]
        if target == "solar_harness":
            artifacts.append(f"{sprint_id}.handoff.md")
        return artifacts
    artifacts = [
        ".pm/requirement_ir.json",
        ".pm/prd.md",
        ".pm/Contracts.yaml",
        ".pm/task_dag.json",
    ]
    if target == "solar_harness":
        artifacts.append(".pm/handoff/solar_harness_handoff.md")
    return artifacts


def _render_product_brief_markdown(brief: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"# Product Brief — {brief['title']}",
            "",
            f"**Source**: {brief['source']}",
            f"**Priority**: {brief['priority']}",
            f"**Lane**: {brief['lane_hint']}",
            f"**Handoff To**: {brief['handoff_to']}",
            "",
            "## Intent",
            "",
            brief["intent"],
            "",
            "## Problem",
            "",
            brief["problem"],
            "",
            "## Acceptance Criteria",
            "",
            *[f"- {item}" for item in brief["acceptance"]],
            "",
            "## Non-Goals",
            "",
            *[f"- {item}" for item in brief["non_goals"]],
            "",
            "## Stop Rules",
            "",
            *[f"- {item}" for item in brief["stop_rules"]],
            "",
            "## Context / Notes",
            "",
            brief.get("notes", "N/A"),
            "",
        ]
    )


def _emit_compiled_pm_tree(pm_dir: Path, payload: dict[str, Any]) -> None:
    """Write only compiler-owned PM inputs beneath ``pm_dir``."""

    contracts_dir = pm_dir / "contracts"
    handoff_dir = pm_dir / "handoff"
    evals_dir = pm_dir / "evals"
    artifacts = payload["compiled_artifacts"]
    requirement_ir = payload["requirement_ir"]
    _write_json(pm_dir / "intake.json", payload["pm_intake"])
    _write_json(pm_dir / "requirement_ir.json", requirement_ir)
    _write_json(pm_dir / "requirement_trace.json", artifacts["requirement_trace"])
    _write_json(pm_dir / "coverage_report.json", artifacts["coverage_report"])
    _write_json(pm_dir / "acceptance_verdict.json", artifacts["acceptance_verdict"])
    _write_text(pm_dir / "prd.md", artifacts["prd_markdown"])
    _write_yaml(pm_dir / "Contracts.yaml", artifacts["contracts_bundle"])
    _write_yaml(contracts_dir / "product.yaml", artifacts["contract_files"]["product"])
    _write_yaml(contracts_dir / "interface.yaml", artifacts["contract_files"]["interface"])
    _write_yaml(contracts_dir / "agent_execution.yaml", artifacts["contract_files"]["agent_execution"])
    _write_yaml(contracts_dir / "research.yaml", artifacts["contract_files"]["research"])
    _write_json(pm_dir / "task_dag.json", artifacts["task_dag"])
    _write_json(pm_dir / "capsule_plan.json", artifacts["capsule_plan"])
    if artifacts.get("plan_markdown"):
        _write_text(pm_dir / "plan.md", artifacts["plan_markdown"])
    if artifacts.get("design_markdown"):
        _write_text(pm_dir / "design.md", artifacts["design_markdown"])
    _write_text(handoff_dir / "codex_handoff.md", artifacts["handoff_markdown"]["codex"])
    _write_text(handoff_dir / "solar_harness_handoff.md", artifacts["handoff_markdown"]["solar_harness"])
    _write_text(evals_dir / "golden_cases.jsonl", "\n".join(json.dumps(case, ensure_ascii=False) for case in artifacts["eval_seed_cases"]) + "\n")


def emit_requirement_package(
    payload: dict[str, Any],
    *,
    workspace_root: Path,
    sprint_root: Path | None = None,
    sprint_id: str = "",
) -> dict[str, str]:
    workspace_root = Path(workspace_root)
    pm_dir = workspace_root / ".pm"
    contracts_dir = pm_dir / "contracts"
    handoff_dir = pm_dir / "handoff"
    artifacts = payload["compiled_artifacts"]
    requirement_ir = payload["requirement_ir"]
    _emit_compiled_pm_tree(pm_dir, payload)

    emitted = {
        "pm_dir": str(pm_dir),
        "requirement_ir": str(pm_dir / "requirement_ir.json"),
        "requirement_trace": str(pm_dir / "requirement_trace.json"),
        "coverage_report": str(pm_dir / "coverage_report.json"),
        "acceptance_verdict": str(pm_dir / "acceptance_verdict.json"),
        "prd": str(pm_dir / "prd.md"),
        "contracts_bundle": str(pm_dir / "Contracts.yaml"),
        "task_dag": str(pm_dir / "task_dag.json"),
        "capsule_plan": str(pm_dir / "capsule_plan.json"),
        "codex_handoff": str(handoff_dir / "codex_handoff.md"),
        "solar_harness_handoff": str(handoff_dir / "solar_harness_handoff.md"),
    }
    if sprint_root and sprint_id:
        sprint_root = Path(sprint_root)
        staging_pm_dir = sprint_root / sprint_id / "workdir" / "workspace" / ".pm"
        _emit_compiled_pm_tree(staging_pm_dir, payload)
        _write_text(sprint_root / f"{sprint_id}.prd.md", artifacts["prd_markdown"])
        _write_text(sprint_root / f"{sprint_id}.contract.md", artifacts["contract_markdown"])
        _write_json(sprint_root / f"{sprint_id}.task_graph.json", artifacts["task_dag"])
        _write_json(sprint_root / f"{sprint_id}.capsule_plan.json", artifacts["capsule_plan"])
        if artifacts.get("plan_markdown"):
            _write_text(sprint_root / f"{sprint_id}.plan.md", artifacts["plan_markdown"])
        if artifacts.get("design_markdown"):
            _write_text(sprint_root / f"{sprint_id}.design.md", artifacts["design_markdown"])
        _write_text(sprint_root / f"{sprint_id}.product-brief.md", artifacts["product_brief_markdown"])
        _write_text(sprint_root / f"{sprint_id}.handoff.md", artifacts["handoff_markdown"]["solar_harness"])
        _write_json(sprint_root / f"{sprint_id}.requirement_ir.json", requirement_ir)
        _write_json(sprint_root / f"{sprint_id}.requirement_trace.json", artifacts["requirement_trace"])
        _write_json(sprint_root / f"{sprint_id}.coverage_report.json", artifacts["coverage_report"])
        _write_json(sprint_root / f"{sprint_id}.acceptance_verdict.json", artifacts["acceptance_verdict"])
        _write_yaml(sprint_root / f"{sprint_id}.Contracts.yaml", artifacts["contracts_bundle"])
        emitted.update(
            {
                "sprint_prd": str(sprint_root / f"{sprint_id}.prd.md"),
                "sprint_contract": str(sprint_root / f"{sprint_id}.contract.md"),
                "sprint_task_graph": str(sprint_root / f"{sprint_id}.task_graph.json"),
                "sprint_capsule_plan": str(sprint_root / f"{sprint_id}.capsule_plan.json"),
                "sprint_plan": str(sprint_root / f"{sprint_id}.plan.md") if artifacts.get("plan_markdown") else "",
                "sprint_design": str(sprint_root / f"{sprint_id}.design.md") if artifacts.get("design_markdown") else "",
                "sprint_requirement_trace": str(sprint_root / f"{sprint_id}.requirement_trace.json"),
                "sprint_coverage_report": str(sprint_root / f"{sprint_id}.coverage_report.json"),
                "sprint_acceptance_verdict": str(sprint_root / f"{sprint_id}.acceptance_verdict.json"),
                "sprint_product_brief": str(sprint_root / f"{sprint_id}.product-brief.md"),
                "sprint_handoff": str(sprint_root / f"{sprint_id}.handoff.md"),
                "sprint_workspace_pm_dir": str(staging_pm_dir),
            }
        )
    return emitted


def _normalized_text(text: str) -> str:
    return " ".join(text.strip().split())


def classify_request_type(text: str, papers: list[str] | None = None) -> str:
    papers = papers or []
    normalized = _normalized_text(text)
    lowered = normalized.lower()
    if papers:
        return RESEARCH
    # RawIntent and the PM compiler are one product front door. Reuse the
    # gateway's evidence-seeking classifier so a prompt cannot enter as
    # research and silently become a short implementation task downstream.
    # Engineering requests containing the product name "Deep Research" remain
    # strategy/delivery because infer_mode resolves those before research.
    if infer_intent_mode(normalized) == "research":
        return RESEARCH

    full_spec_markers = [
        "architecture", "runtime", "system", "platform", "compatibility",
        "rollout", "migration", "refactor", "dag scheduler", "multi-step",
        "phased", "requirement compiler", "requirement ir", "task dag",
        "contract", "handoff", "operator", "physical operator",
        "logical_operator", "actorhost", "agentactor", "registry", "schema",
        "scheduler", "async", "state machine", "browser agent",
        "设计", "架构", "系统", "改造", "迁移", "兼容", "规划",
        "实现", "开发", "接入", "算子", "物理执行", "状态机", "注册",
        "需求编译器", "需求中间表示", "任务图",
    ]
    if any(marker in lowered for marker in full_spec_markers) or any(marker in normalized for marker in full_spec_markers):
        return FULL_SPEC
    if (
        re.search(r"\bp0\b|\bp1\b", lowered)
        or any(marker in normalized for marker in ("修复单", "架构整改单", "整改单"))
    ):
        return FULL_SPEC

    short_markers = [
        "fix", "bug", "add", "change", "rename", "check", "trace",
        "修", "改", "查", "看", "补", "加一个", "改一下", "检查",
    ]
    line_count = len([line for line in text.splitlines() if line.strip()])
    if (
        len(normalized) <= 280
        or line_count <= 3
        or any(marker in lowered for marker in short_markers)
        or any(marker in normalized for marker in short_markers)
    ):
        return SHORT_IMPL
    return FULL_SPEC

def choose_lane_hint(request_type: str, text: str) -> str:
    lowered = text.lower()
    if request_type == RESEARCH:
        return "strategy"
    if request_type == FULL_SPEC and re.search(r"(architecture|refactor|runtime|system|platform|schema|dag)", lowered):
        return "strategy"
    return "delivery"


def choose_priority(text: str, request_type: str) -> str:
    lowered = text.lower()
    if re.search(r"(p0|urgent|blocker|broken|crash|failure|security|sev0)", lowered):
        return "P0"
    if request_type == RESEARCH:
        return "P1"
    if request_type == SHORT_IMPL:
        return "P1" if re.search(r"(bug|fix|repair|修|排查|debug)", lowered) else "P2"
    return "P1"


def choose_output_mode(request_type: str) -> dict[str, str]:
    if request_type == SHORT_IMPL:
        return {"prd": "short", "contract": "short", "dag": "short"}
    if request_type == RESEARCH:
        return {"prd": "research", "contract": "research", "dag": "research"}
    return {"prd": "standard", "contract": "standard", "dag": "standard"}


def choose_acceptance_profile(request_type: str) -> str:
    if request_type == SHORT_IMPL:
        return "execution_evidence"
    if request_type == RESEARCH:
        return "evidence_synthesis"
    return "phased_delivery"


def _short_task_graph() -> dict[str, Any]:
    return {
        "dag_variant": "short",
        "required_gates": ["G_IMPL", "G_TEST", "G_REVIEW"],
        "nodes": [
            {
                "id": "S1",
                "goal": "Implement the requested targeted change.",
                "logical_operator": "ImplementationWorker",
                "depends_on": [],
                "acceptance": ["Patch or config change produced within declared scope."],
                "verifier_required": True,
                "estimated_cost": 1,
            },
            {
                "id": "S2",
                "goal": "Run tests or collect execution evidence for the change.",
                "logical_operator": "TestRunner",
                "depends_on": ["S1"],
                "acceptance": ["Test report or execution evidence captured."],
                "estimated_cost": 1,
            },
            {
                "id": "S3",
                "goal": "Review implementation and evidence before closeout.",
                "logical_operator": "Verifier",
                "depends_on": ["S2"],
                "acceptance": ["Independent verifier decision recorded."],
                "estimated_cost": 1,
            },
        ],
    }


def _standard_task_graph(strategy_lane: bool) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = [
        {
            "id": "S1",
            "goal": "Lock implementation approach, constraints, and file boundaries.",
            "logical_operator": "DeepArchitect",
            "depends_on": [],
            "acceptance": ["Implementation path and constraints are explicit."],
            "estimated_cost": 2,
        },
        {
            "id": "S2",
            "goal": "Implement the approved scope.",
            "logical_operator": "ImplementationWorker",
            "depends_on": ["S1"],
            "acceptance": ["Patch is produced within declared write scope."],
            "estimated_cost": 3,
        },
        {
            "id": "S3",
            "goal": "Run verification commands and collect execution evidence.",
            "logical_operator": "TestRunner",
            "depends_on": ["S2"],
            "acceptance": ["Verification evidence is attached."],
            "estimated_cost": 2,
        },
        {
            "id": "S4",
            "goal": "Perform independent review and closeout decision.",
            "logical_operator": "Verifier",
            "depends_on": ["S3"],
            "acceptance": ["Verifier decision is machine-readable."],
            "estimated_cost": 2,
        },
    ]
    if strategy_lane:
        nodes.append(
            {
                "id": "S5",
                "goal": "Check migration, compatibility, or rollout implications.",
                "logical_operator": "Critic",
                "depends_on": ["S4"],
                "acceptance": ["Compatibility or rollout notes are explicit."],
                "estimated_cost": 2,
            }
        )
    return {
        "dag_variant": "standard",
        "required_gates": ["G_PLAN", "G_IMPL", "G_VERIFY", "G_REVIEW"],
        "nodes": nodes,
    }


def _parallel_spec_task_graph() -> dict[str, Any]:
    return {
        "dag_variant": "parallel_spec",
        "required_gates": ["G_PLAN", "G_IMPL", "G_VERIFY", "G_REVIEW"],
        "nodes": [
            {
                "id": "S1",
                "goal": "Lock convergence scope, constraints, and the branch split for parallel spec workstreams.",
                "logical_operator": "DeepArchitect",
                "depends_on": [],
                "acceptance": ["Parallel workstreams, constraints, and merge conditions are explicit."],
                "estimated_cost": 2,
            },
            {
                "id": "S2",
                "goal": "Draft the architecture, contract, and interface convergence slice.",
                "logical_operator": "DeepArchitect",
                "depends_on": ["S1"],
                "acceptance": ["Architecture and contract convergence decisions are explicit."],
                "estimated_cost": 2,
            },
            {
                "id": "S3",
                "goal": "Draft the migration, compatibility, and rollout convergence slice.",
                "logical_operator": "DeepArchitect",
                "depends_on": ["S1"],
                "acceptance": ["Migration and rollout implications are explicit."],
                "estimated_cost": 2,
            },
            {
                "id": "S4",
                "goal": "Compile the task-graph, traceability, and verification slice for the converged plan.",
                "logical_operator": "ArtifactCurator",
                "depends_on": ["S1"],
                "acceptance": ["Task-graph and traceability implications are explicit."],
                "estimated_cost": 2,
            },
            {
                "id": "S5",
                "goal": "Perform integrated review across all slices and record the closeout decision.",
                "logical_operator": "Verifier",
                "depends_on": ["S2", "S3", "S4"],
                "acceptance": ["Integrated review decision is machine-readable and grounded in all branches."],
                "estimated_cost": 2,
            },
        ],
    }


def _parallel_delivery_task_graph() -> dict[str, Any]:
    return {
        "dag_variant": "parallel_delivery",
        "required_gates": ["G_PLAN", "G_IMPL", "G_VERIFY", "G_REVIEW"],
        "quality_gates": {
            "parallelism": {
                "min_ready_width": 3,
            }
        },
        "nodes": [
            {
                "id": "S1",
                "goal": "Lock interface, compatibility, and write-scope constraints for the requested fix.",
                "logical_operator": "DeepArchitect",
                "depends_on": [],
                "acceptance": ["Interface and write-scope constraints are explicit."],
                "estimated_cost": 2,
            },
            {
                "id": "S2",
                "goal": "Inspect runtime path, failure evidence, and affected integration points.",
                "logical_operator": "Critic",
                "depends_on": [],
                "acceptance": ["Failure evidence and affected paths are mapped."],
                "estimated_cost": 2,
            },
            {
                "id": "S3",
                "goal": "Prepare verification plan, regression commands, and acceptance probes.",
                "logical_operator": "TestRunner",
                "depends_on": [],
                "acceptance": ["Verification commands and acceptance probes are ready."],
                "estimated_cost": 2,
            },
            {
                "id": "S4",
                "goal": "Implement the fix using the combined constraints and evidence.",
                "logical_operator": "ImplementationWorker",
                "depends_on": ["S1", "S2", "S3"],
                "acceptance": ["Patch is produced within declared scope and linked to evidence."],
                "verifier_required": True,
                "estimated_cost": 3,
            },
            {
                "id": "S5",
                "goal": "Run regression verification and record the release decision.",
                "logical_operator": "Verifier",
                "depends_on": ["S4"],
                "acceptance": ["Verifier decision and regression evidence are machine-readable."],
                "estimated_cost": 2,
            },
        ],
    }


def _research_task_graph() -> dict[str, Any]:
    return {
        "dag_variant": "research",
        "research_mode": True,
        "quality_gates": {
            "parallelism": {
                "min_ready_width": 1,
            }
        },
        "evidence_policy": {
            "ledger_required": True,
            "unsupported_claim_guard": True,
            "citation_required": True,
        },
        "required_gates": ["G_SOURCE", "G_EVIDENCE", "G_SYNTHESIS", "G_REVIEW"],
        "nodes": [
            {
                "id": "R1",
                "goal": "Retrieve authoritative primary sources and persist provenance-complete source pack A.",
                "logical_operator": "ResearchScout",
                "depends_on": [],
                "outputs": [
                    "workspace/research/source-pack-a/sources.jsonl",
                    "workspace/research/source-pack-a/evidence.jsonl",
                    "workspace/research/source-pack-a/extracts",
                ],
                "acceptance": ["Source pack A passes deterministic retrieval closeout."],
                "estimated_cost": 2,
            },
            {
                "id": "R2",
                "goal": "Independently retrieve complementary and contradictory sources into source pack B.",
                "logical_operator": "ResearchScout",
                "depends_on": [],
                "outputs": [
                    "workspace/research/source-pack-b/sources.jsonl",
                    "workspace/research/source-pack-b/evidence.jsonl",
                    "workspace/research/source-pack-b/extracts",
                ],
                "acceptance": ["Source pack B passes deterministic retrieval closeout and is independent of pack A."],
                "estimated_cost": 2,
            },
            {
                "id": "R3",
                "goal": "Compare both verified source packs and enumerate contradictions, gaps, and unsupported assumptions.",
                "logical_operator": "Critic",
                "depends_on": ["R1", "R2"],
                "outputs": [
                    "workspace/research/evidence-review/contradictions.jsonl",
                    "workspace/research/evidence-review/gaps.md",
                ],
                "acceptance": ["Contradictions or gaps are enumerated."],
                "estimated_cost": 2,
            },
            {
                "id": "R4",
                "goal": "Synthesize only verified evidence into claims, a structured report AST, and a cited final report.",
                "logical_operator": "ResearchSynthesizer",
                "depends_on": ["R1", "R2", "R3"],
                "outputs": [
                    "workspace/research/report/sources.jsonl",
                    "workspace/research/report/evidence.jsonl",
                    "workspace/research/report/extracts",
                    "workspace/research/report/synthesis_plan.json",
                    "workspace/research/report/evidence_gaps.json",
                    "workspace/research/report/claims.jsonl",
                    "workspace/research/report/claim_evidence.jsonl",
                    "workspace/research/report/sections.jsonl",
                    "workspace/research/report/section_checks.jsonl",
                    "workspace/research/report/report_ast.json",
                    "workspace/research/report/final.bibliography.json",
                    "workspace/research/report/final.md",
                    "workspace/research/report/research_eval.json",
                ],
                "acceptance": ["Every material claim in final.md cites evidence that resolves to a verified source span."],
                "estimated_cost": 3,
            },
            {
                "id": "R5",
                "goal": "Independently verify claim support, citation resolution, source quality, and report completeness.",
                "logical_operator": "Verifier",
                "depends_on": ["R4"],
                "outputs": ["workspace/research/report/critique.md"],
                "acceptance": ["Critique and deterministic final-report closeout decision are recorded."],
                "estimated_cost": 2,
            },
            {
                "id": "R6",
                "goal": "Curate the verified report, limitations, and user-facing delivery summary without changing supported claims.",
                "logical_operator": "ArtifactCurator",
                "depends_on": ["R5"],
                "outputs": ["workspace/research/report/delivery.md"],
                "acceptance": ["The final deliverable links the verified report and states material evidence limitations."],
                "estimated_cost": 1,
            },
        ],
    }


def _apply_default_gate_assignments(graph: dict[str, Any]) -> dict[str, Any]:
    dag_variant = str(graph.get("dag_variant") or "").strip().lower()
    nodes = [node for node in (graph.get("nodes") or []) if isinstance(node, dict)]
    if not nodes:
        return graph

    gate_by_node_id: dict[str, str] = {}
    if dag_variant == "short":
        gate_by_node_id = {
            "S1": "G_IMPL",
            "S2": "G_TEST",
            "S3": "G_REVIEW",
        }
    elif dag_variant == "standard":
        gate_by_node_id = {
            "S1": "G_PLAN",
            "S2": "G_IMPL",
            "S3": "G_VERIFY",
            "S4": "G_REVIEW",
            "S5": "G_REVIEW",
        }
    elif dag_variant == "parallel_spec":
        gate_by_node_id = {
            "S1": "G_PLAN",
            "S2": "G_IMPL",
            "S3": "G_IMPL",
            "S4": "G_VERIFY",
            "S5": "G_REVIEW",
        }
    elif dag_variant == "parallel_delivery":
        gate_by_node_id = {
            "S1": "G_PLAN",
            "S2": "G_PLAN",
            "S3": "G_VERIFY",
            "S4": "G_IMPL",
            "S5": "G_REVIEW",
        }
    elif dag_variant == "research":
        gate_by_node_id = {
            "R1": "G_SOURCE",
            "R2": "G_EVIDENCE",
            "R3": "G_EVIDENCE",
            "R4": "G_SYNTHESIS",
            "R5": "G_REVIEW",
            "R6": "G_REVIEW",
        }

    required = [str(g) for g in (graph.get("required_gates") or []) if g]
    allowed = set(required)
    for node in nodes:
        node_id = str(node.get("id") or "")
        if node.get("gate"):
            continue
        gate = gate_by_node_id.get(node_id)
        if gate and (not allowed or gate in allowed):
            node["gate"] = gate

    owners: dict[str, list[str]] = {gate: [] for gate in required}
    for node in nodes:
        gate = str(node.get("gate") or "")
        if gate in owners:
            owners[gate].append(str(node.get("id") or ""))
    missing = [gate for gate in required if not owners.get(gate)]
    if not missing:
        return graph

    unassigned = [node for node in nodes if not node.get("gate")]
    for gate, node in zip(missing, unassigned):
        node["gate"] = gate
    return graph


def build_task_graph_skeleton(request_type: str, lane_hint: str, request_text: str = "") -> dict[str, Any]:
    if request_type == SHORT_IMPL:
        graph = _apply_default_gate_assignments(_short_task_graph())
    elif request_type == RESEARCH:
        graph = _apply_default_gate_assignments(_research_task_graph())
    elif _is_parallel_spec_request(request_type, request_text):
        graph = _apply_default_gate_assignments(_parallel_spec_task_graph())
    elif _is_parallel_delivery_request(request_type, request_text):
        graph = _apply_default_gate_assignments(_parallel_delivery_task_graph())
    else:
        graph = _apply_default_gate_assignments(_standard_task_graph(strategy_lane=lane_hint == "strategy"))
    # Intake birth marker (G4 blocker 2): sprints born through the requirement
    # compiler are the GOVERNED population — plan_validator classifies an
    # uncontracted graph as generic (certificate demanded) only when this
    # marker is present, so hand-authored/legacy graphs stay grandfathered
    # under default-on. The planner edits this file in place, so the marker
    # persists through planning; it sits outside the certificate's governed
    # subset, so stamping is unaffected.
    graph["plan_compile_required"] = True
    return graph


def build_pm_intake(
    text: str,
    *,
    papers: list[str] | None = None,
    logs: list[str] | None = None,
    repo_context: list[str] | None = None,
    sprint_id: str = "",
    target_system: str = "solar-harness",
) -> dict[str, Any]:
    papers = papers or []
    logs = logs or []
    repo_context = repo_context or []
    if _is_rawintent_consumer_envelope(text):
        if len(text) > MAX_RAWINTENT_ENVELOPE_CHARS:
            raise RequestTooLargeError(len(text), MAX_RAWINTENT_ENVELOPE_CHARS)
    else:
        _enforce_request_size(text)
    effective_text = _extract_effective_request_text(text)
    compile_text = effective_text["effective_text"] or _normalized_text(text)
    goal_text = effective_text["goal_text"] or compile_text
    problem_text = effective_text["problem_text"] or compile_text
    raw_user_text = effective_text["raw_user_text"] or compile_text
    # Keep semantic text lossless within the same explicit boundary used by
    # status-server intake. Reject larger direct-router requests instead of
    # silently slicing fields that later become requirements and contracts.
    for semantic_text in (compile_text, goal_text, problem_text, raw_user_text):
        _enforce_request_size(semantic_text)
    autosci_contract = is_autosci_research_intake_text(compile_text)
    request_type = RESEARCH if autosci_contract else classify_request_type(compile_text, papers)
    canonical_request_type = CLASS_TO_CANONICAL[request_type]
    lane_hint = choose_lane_hint(request_type, compile_text)
    output_mode = choose_output_mode(request_type)
    priority = choose_priority(compile_text, request_type)
    title = _safe_title(goal_text or compile_text)
    if autosci_contract:
        task_graph = build_autosci_task_graph(
            sprint_id=sprint_id or "N/A",
            title=title,
            request_text=compile_text,
            harness_dir=HARNESS_ROOT,
        )
    else:
        task_graph = build_task_graph_skeleton(request_type, lane_hint, compile_text)
    if _is_code_understanding_request(compile_text, repo_context):
        task_graph = _adapt_graph_for_code_understanding(task_graph, request_type)
    task_graph["nodes"] = [_node_enrichment(request_type, lane_hint, node) for node in task_graph["nodes"]]
    # Semantic fields must not be length-capped: REQ-000, the PRD view, and the
    # product contract are compiled from them, so a silent slice here drops
    # instructions from the end of long requests (title stays the bounded label).
    normalized_goal = _normalized_text(goal_text)
    normalized_problem = _normalized_text(problem_text)
    normalized_user_intent = _normalized_text(raw_user_text)
    acceptance = _default_acceptance(request_type)
    declared_execution = _extract_execution_contract(text)
    if declared_execution["acceptance"]:
        acceptance = [declared_execution["acceptance"]]
    if autosci_contract:
        acceptance = [
            "Normal Solar intake emits a research.autosci.v1 task graph.",
            "Scientific* nodes resolve to AutoSci research capsules and autosci-* physical operators.",
            "Autopilot can dispatch ready graph nodes without a manual AutoSci shim call.",
        ]
    non_goals = _default_non_goals(request_type)
    stop_rules = _default_stop_rules(request_type)
    open_questions = _derive_open_questions(request_type, compile_text, papers)
    risk_register = _derive_risk_register(request_type)
    requirements = _build_requirement_items(normalized_goal, acceptance, priority)
    source_inputs = {
        "raw_request": raw_user_text or text,
        "raw_request_original": text,
        "papers": papers,
        "logs": logs,
        "repo_context": repo_context,
    }
    prd_view = _make_prd_view(
        canonical_request_type,
        normalized_goal,
        source_inputs,
        acceptance,
        non_goals,
        open_questions,
        risk_register,
    )
    contracts = _build_contracts(
        request_type,
        normalized_goal,
        acceptance,
        non_goals,
        stop_rules,
        text,
        papers,
    )
    requirement_ir = {
        "schema_version": "solar.requirement_ir.v1",
        "id": f"req-{uuid.uuid4().hex[:12]}",
        "request_type": canonical_request_type,
        "priority": priority,
        "lane_hint": lane_hint,
        "source_inputs": source_inputs,
        "user_intent": normalized_user_intent or normalized_goal,
        "normalized_goal": normalized_goal,
        "problem_statement": normalized_problem,
        "assumptions": _derive_assumptions(request_type, lane_hint),
        "open_questions": open_questions,
        "risk_register": risk_register,
        "requirements": requirements,
        "scheduling": {
            "queue_class": "requirements_compile",
            "global_priority_boost": 1000,
            "lane_hint": lane_hint,
        },
        "confidence": _derive_confidence(request_type, text, papers),
        "prd_view": prd_view,
        "contracts": {
            "product": contracts["product"],
            "interface": contracts["interface"],
            "agent_execution": contracts["agent_execution"],
            "research": contracts["research"],
        },
        "dag_view": task_graph,
        "handoff_view": {
            "codex": {
                "target": "Codex",
                "artifacts": _sprint_handoff_artifacts(sprint_id or "", "codex"),
            },
            "solar_harness": {
                "target": "solar-harness",
                "artifacts": _sprint_handoff_artifacts(sprint_id or "", "solar_harness"),
            },
        },
        "evidence_policy": task_graph.get("evidence_policy", {}),
    }
    if autosci_contract:
        requirement_ir["workflow_contract"] = AUTOSCI_WORKFLOW_CONTRACT_ID
        requirement_ir["autosci_contract_bound"] = True
    task_graph = _apply_requirement_mapping(task_graph, requirements, request_type)
    task_graph = enrich_task_graph_defaults(task_graph, requirement_ir, sprint_id=sprint_id or "N/A")
    requirement_ir["dag_view"] = task_graph
    product_brief = {
        "title": title,
        "source": "codex-pm-router",
        "intent": normalized_goal,
        "problem": normalized_problem or normalized_goal,
        "priority": priority,
        "lane_hint": lane_hint,
        "acceptance": acceptance,
        "non_goals": non_goals,
        "stop_rules": stop_rules,
        "handoff_to": "planner",
        "request_type": request_type,
        "template_variant": output_mode["prd"],
        "pm_intake": {
            "request_type": request_type,
            "intent_summary": _normalized_text(normalized_problem or normalized_goal)[:240],
            "source_inputs": {
                "papers": papers,
                "logs": logs,
                "repo_context": repo_context,
            },
            "output_mode": output_mode,
        },
        "requirement_ir_ref": (
            f"{sprint_id}.requirement_ir.json" if sprint_id and sprint_id != "N/A" else ".pm/requirement_ir.json"
        ),
        "notes": "Requirement Compiler produced canonical IR, compiled contracts, and a task DAG proposal.",
    }
    if autosci_contract:
        product_brief.update(
            {
                "source": "autosci-intake-contract",
                "handoff_to": "planner",
                "template_variant": "autosci",
                "notes": "Normal intake selected an AutoSci graph proposal that requires independent Planner certification.",
            }
        )
    prd_markdown = _render_prd_markdown(title, prd_view)
    contract_markdown = _render_contract_markdown(title, contracts)
    codex_handoff_md = _render_handoff_markdown(
        title,
        "Codex",
        normalized_problem or normalized_goal,
        _sprint_handoff_artifacts(sprint_id or "", "codex"),
        acceptance,
        [
            "Treat requirement_ir.json and contracts/*.yaml as canonical sources.",
            "Use requirement_trace/coverage_report as completion evidence, not intuition.",
            "Do not bypass planner before builder dispatch.",
        ],
    )
    solar_handoff_md = _render_handoff_markdown(
        title,
        "solar-harness",
        (
            "Route the AutoSci graph proposal to a distinct Planner; Builder dispatch is forbidden until plan certification succeeds."
            if autosci_contract
            else "Read compiled PRD / contract / task graph proposal, then produce planner artifacts without skipping governance."
        ),
        _sprint_handoff_artifacts(sprint_id or "", "solar_harness"),
        [
            (
                "Planner reviews the Scientific* proposal and produces design.md, plan.md, and a valid plan certificate."
                if autosci_contract
                else "Planner produces design.md and plan.md."
            ),
            (
                "Do not dispatch any Scientific* Builder node before the Planner certificate is valid."
                if autosci_contract
                else "Planner may refine task_graph.json but must preserve compiled governance constraints and explicit requirement_ids mapping."
            ),
            "No direct builder dispatch from raw request.",
        ],
        [
            "IR is source of truth.",
            "Markdown PRD / contract are compiled views.",
        ],
    )
    product_brief_markdown = _render_product_brief_markdown(product_brief)
    # These are Planner-owned artifacts for every governed path, including
    # AutoSci. PM only emits the proposal graph and may not impersonate the
    # independent Planner stage by pre-generating design/plan files.
    plan_markdown = ""
    design_markdown = ""
    requirement_trace = build_requirement_trace(requirement_ir, task_graph)
    coverage_report = build_coverage_report(requirement_trace, task_graph)
    acceptance_verdict = build_acceptance_verdict(
        requirement_ir,
        task_graph,
        coverage_report,
        requested_verdict="pass",
    )
    capsule_plan_ir = build_capsule_plan_ir(
        task_graph,
        request_type=canonical_request_type,
        lane_hint=lane_hint,
        registry_path=HARNESS_ROOT / "config" / "capability-capsules.registry.yaml",
    )
    return {
        "pm_intake": {
            "request_type": request_type,
            "intent_summary": _normalized_text(normalized_problem or normalized_goal)[:240],
            "source_inputs": {
                "papers": papers,
                "logs": logs,
                "repo_context": repo_context,
            },
            "output_mode": output_mode,
        },
        "classification": request_type,
        "canonical_request_type": canonical_request_type,
        "prd_variant": output_mode["prd"],
        "contract_variant": output_mode["contract"],
        "dag_variant": str(task_graph.get("dag_variant") or output_mode["dag"]),
        "lane_hint": lane_hint,
        "priority": priority,
        "acceptance_profile": choose_acceptance_profile(request_type),
        "target_system": target_system,
        "workflow_contract": AUTOSCI_WORKFLOW_CONTRACT_ID if autosci_contract else "",
        "autosci_contract_bound": autosci_contract,
        "handoff_package": {
            "sprint_id": sprint_id or "N/A",
            "artifacts": [
                "product-brief.md",
                "contract.md",
                "plan.md",
                "task_graph.json",
            ],
            "research_artifacts": [
                "workspace/research/source-pack-a/sources.jsonl",
                "workspace/research/source-pack-a/evidence.jsonl",
                "workspace/research/source-pack-a/extracts",
                "workspace/research/source-pack-b/sources.jsonl",
                "workspace/research/source-pack-b/evidence.jsonl",
                "workspace/research/source-pack-b/extracts",
                "workspace/research/report/synthesis_plan.json",
                "workspace/research/report/evidence_gaps.json",
                "workspace/research/report/claims.jsonl",
                "workspace/research/report/claim_evidence.jsonl",
                "workspace/research/report/sections.jsonl",
                "workspace/research/report/section_checks.jsonl",
                "workspace/research/report/report_ast.json",
                "workspace/research/report/final.bibliography.json",
                "workspace/research/report/final.md",
                "workspace/research/report/research_eval.json",
            ] if request_type == RESEARCH else [],
        },
        "task_graph_skeleton": task_graph,
        "requirement_ir": requirement_ir,
        "compiled_artifacts": {
            "prd_markdown": prd_markdown,
            "contracts_bundle": contracts["bundle"],
            "contract_markdown": contract_markdown,
            "task_dag": task_graph,
            "capsule_plan": capsule_plan_ir,
            "requirement_trace": requirement_trace,
            "coverage_report": coverage_report,
            "acceptance_verdict": acceptance_verdict,
            "product_brief": product_brief,
            "product_brief_markdown": product_brief_markdown,
            "plan_markdown": plan_markdown,
            "design_markdown": design_markdown,
            "handoff_markdown": {
                "codex": codex_handoff_md,
                "solar_harness": solar_handoff_md,
            },
            "contract_files": {
                "product": contracts["product"],
                "interface": contracts["interface"],
                "agent_execution": contracts["agent_execution"],
                "research": contracts["research"],
            },
            "eval_seed_cases": [
                {
                    "case_id": f"golden-{requirement_ir['id']}",
                    "request_type": request_type,
                    "goal": normalized_goal,
                    "expected_dag_variant": task_graph["dag_variant"],
                    "expected_template_variant": output_mode["prd"],
                }
            ],
        },
    }


def validate_compiled_package(payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    requirement_ir = dict(payload.get("requirement_ir") or {})
    compiled = dict(payload.get("compiled_artifacts") or {})
    product_brief = dict(compiled.get("product_brief") or {})
    graph = dict(compiled.get("task_dag") or {})
    nodes = [node for node in (graph.get("nodes") or []) if isinstance(node, dict)]
    trace_items = list((compiled.get("requirement_trace") or {}).get("items") or [])
    acceptance = list(product_brief.get("acceptance") or requirement_ir.get("contracts", {}).get("product", {}).get("acceptance", []) or [])
    normalized_goal = str(requirement_ir.get("normalized_goal") or "")
    problem_statement = str(requirement_ir.get("problem_statement") or product_brief.get("problem") or "")

    if requirement_ir.get("schema_version") != "solar.requirement_ir.v1":
        errors.append("invalid_requirement_ir_schema")
    if not normalized_goal.strip():
        errors.append("normalized_goal_missing")
    if not problem_statement.strip():
        errors.append("problem_statement_missing")
    if _looks_like_raw_metadata_pollution(normalized_goal) or _looks_like_raw_metadata_pollution(problem_statement):
        errors.append("raw_metadata_pollution_detected")
    if not acceptance:
        errors.append("acceptance_missing")
    if not nodes:
        errors.append("task_graph_nodes_missing")

    node_ids: list[str] = []
    duplicates: set[str] = set()
    for node in nodes:
        node_id = str(node.get("id") or "").strip()
        if not node_id:
            errors.append("task_graph_node_id_missing")
            continue
        if node_id in node_ids:
            duplicates.add(node_id)
        node_ids.append(node_id)
        if not (node.get("acceptance") or []):
            errors.append(f"node_acceptance_missing:{node_id}")
        if not (node.get("requirement_ids") or []):
            errors.append(f"node_requirement_ids_missing:{node_id}")
    if duplicates:
        errors.append("duplicate_node_ids:" + ",".join(sorted(duplicates)))

    node_id_set = set(node_ids)
    graph_map = {str(node.get("id") or ""): node for node in nodes}
    for node in nodes:
        node_id = str(node.get("id") or "")
        for dep in node.get("depends_on") or []:
            dep_id = str(dep)
            if dep_id not in node_id_set:
                errors.append(f"unknown_dependency:{node_id}->{dep_id}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def _walk(node_id: str) -> bool:
        if node_id in visiting:
            return True
        if node_id in visited:
            return False
        visiting.add(node_id)
        for dep in graph_map.get(node_id, {}).get("depends_on") or []:
            if _walk(str(dep)):
                return True
        visiting.remove(node_id)
        visited.add(node_id)
        return False

    if any(_walk(node_id) for node_id in node_ids):
        errors.append("task_graph_cycle_detected")

    graph_variant = str(graph.get("dag_variant") or payload.get("dag_variant") or "").strip().lower()
    nonlinear = graph_variant not in {
        "",
        "linear",
        "serial",
        "sequential",
        "single",
        "single_node",
        "standard",
    }
    quality = graph.get("quality_gates") if isinstance(graph.get("quality_gates"), dict) else {}
    parallelism = quality.get("parallelism") if isinstance(quality.get("parallelism"), dict) else {}
    explicit_min = parallelism.get("min_ready_width") or quality.get("min_ready_width") or graph.get("min_ready_width")
    try:
        min_ready_width = int(explicit_min or 0)
    except Exception:
        min_ready_width = 0
    if nonlinear and len(nodes) >= 4:
        min_ready_width = min_ready_width or 2
        source_nodes = [
            str(node.get("id") or "")
            for node in nodes
            if not [dep for dep in (node.get("depends_on") or []) if str(dep) in node_id_set]
        ]
        if len(source_nodes) < min_ready_width:
            errors.append(
                "task_graph_ready_width_below_min:"
                f"source_width={len(source_nodes)}"
                f"<min_ready_width={min_ready_width}"
                f":variant={graph_variant or 'nonlinear'}"
            )

    if trace_items:
        unmapped = [item.get("requirement_id", "N/A") for item in trace_items if not (item.get("mapped_nodes") or [])]
        if unmapped:
            errors.append("requirement_mapping_missing:" + ",".join(str(x) for x in unmapped))
        missing_artifacts = [item.get("requirement_id", "N/A") for item in trace_items if not (item.get("expected_artifacts") or [])]
        if missing_artifacts:
            warnings.append("requirement_expected_artifacts_missing:" + ",".join(str(x) for x in missing_artifacts))
    else:
        errors.append("requirement_trace_missing")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "node_count": len(nodes),
            "requirement_count": len(requirement_ir.get("requirements") or []),
            "trace_count": len(trace_items),
        },
    }


def _markdown_summary(payload: dict[str, Any]) -> str:
    intake = payload["pm_intake"]
    graph = payload["task_graph_skeleton"]
    lines = [
        "# Codex PM Router Output",
        "",
        f"- request_type: `{intake['request_type']}`",
        f"- canonical_request_type: `{payload['canonical_request_type']}`",
        f"- prd_variant: `{payload['prd_variant']}`",
        f"- contract_variant: `{payload['contract_variant']}`",
        f"- dag_variant: `{payload['dag_variant']}`",
        f"- lane_hint: `{payload['lane_hint']}`",
        f"- priority: `{payload['priority']}`",
        f"- acceptance_profile: `{payload['acceptance_profile']}`",
        "",
        "## Task Graph Skeleton",
        "",
    ]
    for node in graph["nodes"]:
        lines.append(
            f"- `{node['id']}` `{node['logical_operator']}` -> {node['goal']}"
        )
    return "\n".join(lines) + "\n"


def _read_text(args: argparse.Namespace) -> str:
    if args.text:
        return args.text
    if args.input_file:
        return Path(args.input_file).read_text(encoding="utf-8")
    raw = sys.stdin.read()
    if raw.strip():
        return raw
    raise SystemExit("Provide --text, --input-file, or stdin.")


def _capture_and_consume_rawintent(args: argparse.Namespace, text: str) -> int:
    env = dict(os.environ)
    env.setdefault("SOLAR_HARNESS_DIR", str(HARNESS_ROOT))
    env.setdefault("HARNESS_DIR", str(HARNESS_ROOT))
    gateway_cmd = [
        sys.executable,
        str(HARNESS_ROOT / "lib" / "intent_gateway.py"),
        "capture",
        "--source-channel", "codex_pm_router",
        "--source-trust", "codex_pm_router",
        "--actor", "user",
        "--device", "codex_pm_router_cli",
        "--repo", str(Path(args.emit_dir or HARNESS_ROOT)),
        "--text", text,
        "--json",
    ]
    if args.sprint_id:
        gateway_cmd.extend(["--sprint-id", args.sprint_id])
    captured = subprocess.run(gateway_cmd, text=True, capture_output=True, env=env, timeout=60)
    if captured.returncode != 0:
        print(captured.stderr or captured.stdout or "intent capture failed", file=sys.stderr)
        return 1
    gateway_payload = json.loads(captured.stdout)
    consumer_cmd = [
        sys.executable,
        str(HARNESS_ROOT / "lib" / "intent_consumer.py"),
        "consume",
        "--intent-id", str(gateway_payload.get("intent_id") or ""),
        "--json",
    ]
    if args.sprint_id:
        consumer_cmd.extend(["--sprint-id", args.sprint_id])
    if not args.auto_dispatch_planner:
        consumer_cmd.append("--no-auto-dispatch-planner")
    consumed = subprocess.run(consumer_cmd, text=True, capture_output=True, env=env, timeout=180)
    if consumed.returncode != 0:
        print(consumed.stderr or consumed.stdout or "intent consume failed", file=sys.stderr)
        return 1
    consumer_payload = json.loads(consumed.stdout)
    result = {
        "ok": True,
        "mode": "rawintent",
        "gateway": gateway_payload,
        "consumer": consumer_payload,
    }
    if args.format == "markdown":
        sys.stdout.write(
            "\n".join(
                [
                    "# Codex PM Router RawIntent Handoff",
                    "",
                    f"- intent_id: `{gateway_payload.get('intent_id', '')}`",
                    f"- lane: `{gateway_payload.get('lane', '')}`",
                    f"- requirement_ir: `{gateway_payload.get('requirement_ir', '')}`",
                    f"- consumer_status: `{(consumer_payload.get('results') or [{}])[0].get('status', 'N/A')}`",
                ]
            )
            + "\n"
        )
    else:
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile a request into Requirement IR and PM intake artifacts.")
    parser.add_argument("--text", help="Inline request text.")
    parser.add_argument("--input-file", help="Read request text from file.")
    parser.add_argument("--paper", action="append", default=[], help="Paper title, link, or identifier.")
    parser.add_argument("--log", action="append", default=[], help="Relevant log or error artifact path.")
    parser.add_argument("--repo-context", action="append", default=[], help="Repo path or context hint.")
    parser.add_argument("--sprint-id", default="", help="Existing sprint id if continuing work.")
    parser.add_argument("--target-system", default="solar-harness", choices=["solar-harness", "codex"], help="Downstream target system.")
    parser.add_argument("--format", default="json", choices=["json", "markdown"], help="Output format.")
    parser.add_argument("--emit-dir", default="", help="Workspace root where .pm/ artifacts should be emitted.")
    parser.add_argument("--emit-sprint-root", default="", help="Optional sprint directory for compiled sprint artifacts.")
    parser.add_argument("--direct-compile", action="store_true", help="Bypass RawIntent capture/consume and compile directly.")
    parser.add_argument("--no-auto-dispatch-planner", dest="auto_dispatch_planner", action="store_false", help="When routing via RawIntent, do not request trusted planner auto handoff.")
    parser.set_defaults(auto_dispatch_planner=True)
    args = parser.parse_args()

    text = _read_text(args)
    if not args.direct_compile and os.environ.get("SOLAR_PM_ROUTER_ALLOW_DIRECT") != "1":
        return _capture_and_consume_rawintent(args, text)
    try:
        payload = build_pm_intake(
            text,
            papers=args.paper,
            logs=args.log,
            repo_context=args.repo_context,
            sprint_id=args.sprint_id,
            target_system=args.target_system,
        )
    except RequestTooLargeError as exc:
        error = {
            "ok": False,
            "error": "request_too_long",
            "actual_chars": exc.actual_chars,
            "max_chars": exc.max_chars,
        }
        if args.format == "markdown":
            sys.stdout.write(
                "# Codex PM Router Request Rejected\n\n"
                f"- error: `{error['error']}`\n"
                f"- actual_chars: `{error['actual_chars']}`\n"
                f"- max_chars: `{error['max_chars']}`\n"
            )
        else:
            json.dump(error, sys.stdout, ensure_ascii=False, indent=2)
            sys.stdout.write("\n")
        return 2
    validation = validate_compiled_package(payload)
    if not validation["ok"]:
        if args.format == "markdown":
            sys.stdout.write(
                "# Codex PM Router Validation Failed\n\n"
                + "\n".join(f"- {item}" for item in validation["errors"])
                + "\n"
            )
        else:
            json.dump({"ok": False, "validation": validation, "payload": payload}, sys.stdout, ensure_ascii=False, indent=2)
            sys.stdout.write("\n")
        return 2
    if args.emit_dir:
        emit_requirement_package(
            payload,
            workspace_root=Path(args.emit_dir),
            sprint_root=Path(args.emit_sprint_root) if args.emit_sprint_root else None,
            sprint_id=args.sprint_id,
        )

    if args.format == "markdown":
        sys.stdout.write(_markdown_summary(payload))
    else:
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
