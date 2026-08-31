#!/usr/bin/env python3
"""Unified RawIntent gateway for Solar-Harness entrypoints.

Every user-facing entrypoint writes the same RawIntent packet before it creates
PRD/contract/task_graph work.  Interactive production channels require the
formal LLM IntentIR compiler; deterministic rewriting remains an offline/CLI
compatibility path and must never silently classify GUI requests.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


HARNESS_DIR = Path(
    os.environ.get("HARNESS_DIR")
    or os.environ.get("SOLAR_HARNESS_DIR")
    or Path(__file__).resolve().parents[1]
)
SPRINTS_DIR = Path(os.environ.get("SOLAR_HARNESS_SPRINTS_DIR") or (HARNESS_DIR / "sprints"))
INTENTS_DIR = Path(os.environ.get("SOLAR_INTENT_GATEWAY_DIR") or (HARNESS_DIR / "intents"))
_DEFAULT_LLM_INTENT_CHANNELS = {
    "cli_intake",
    "dashboard",
    "gui",
    "webapp",
    "web",
    "codex_pm_router",
}


def _llm_intent_compiler_required(source_channel: str) -> bool:
    """Return whether this ingress must produce model-authored IntentIR.

    The channel list is configurable for deployments with renamed frontends,
    but the shipped GUI/web channels are fail-closed by default.  CLI capture
    stays deterministic-capable so local schema tests and offline maintenance
    do not unexpectedly invoke a live model.
    """
    configured = str(
        os.environ.get("SOLAR_INTENT_COMPILER_REQUIRED_CHANNELS") or ""
    ).strip()
    channels = (
        {
            value.strip().lower()
            for value in configured.split(",")
            if value.strip()
        }
        if configured
        else _DEFAULT_LLM_INTENT_CHANNELS
    )
    return str(source_channel or "").strip().lower() in channels


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slug(value: str, limit: int = 64) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-")
    return (text or "intent")[:limit]


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    # ASCII-safe JSON remains valid UTF-8 and can also be read by Windows
    # callers that omit an explicit encoding and fall back to CP1252.
    tmp.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def read_text_arg(args: argparse.Namespace) -> str:
    parts: list[str] = []
    if args.text:
        parts.append(args.text)
    if args.file:
        parts.append(Path(args.file).expanduser().read_text(encoding="utf-8", errors="replace"))
    if args.stdin:
        parts.append(sys.stdin.read())
    text = "\n".join(part.strip() for part in parts if part.strip()).strip()
    if not text:
        raise SystemExit("intent-gateway capture requires --text, --file, or --stdin")
    return text


def extract_research_artifact(args: argparse.Namespace) -> dict[str, Any] | None:
    path = str(getattr(args, "research_artifact", "") or "").strip()
    project_name = str(getattr(args, "research_project_name", "") or "").strip()
    conversation_id = str(getattr(args, "research_conversation_id", "") or "").strip()
    source_url = str(getattr(args, "research_source_url", "") or "").strip()
    if not any((path, project_name, conversation_id, source_url)):
        return None
    return {
        "path": path,
        "project_name": project_name,
        "conversation_id": conversation_id,
        "source_url": source_url,
    }


def intake_attachments_from_env() -> list[dict[str, Any]]:
    raw = str(os.environ.get("SOLAR_INTAKE_ATTACHMENTS_JSON") or "").strip()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    attachments: list[dict[str, Any]] = []
    for item in payload[:8]:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        if not path or not Path(path).is_file():
            continue
        attachments.append({
            "name": str(item.get("name") or Path(path).name)[:140],
            "path": path,
            "mime_type": str(item.get("mime_type") or "application/octet-stream")[:160],
            "size": int(item.get("size") or Path(path).stat().st_size),
            "sha256": str(item.get("sha256") or "")[:64],
        })
    return attachments


def _contains_marker(value: str, marker: str) -> bool:
    marker = marker.strip().lower()
    if not marker:
        return False
    if any(ord(character) > 127 for character in marker):
        return marker in value
    return re.search(
        rf"(?<![a-z0-9_]){re.escape(marker)}(?![a-z0-9_])",
        value,
    ) is not None


_DELIVERY_ACTIONS = (
    "build",
    "building",
    "implement",
    "implementing",
    "develop",
    "developing",
    "write",
    "writing",
    "code",
    "coding",
    "create",
    "creating",
    "add",
    "adding",
    "make",
    "making",
)

_TECHNICAL_ARTIFACTS = (
    "cli",
    "command-line",
    "script",
    "function",
    "api",
    "web app",
    "application",
    "service",
    "library",
    "package",
    "plugin",
    "tool",
    "component",
    "endpoint",
    "test suite",
    "codebase",
)

_UNAMBIGUOUS_SOFTWARE_ACTIONS = (
    "implement",
    "implementing",
    "develop",
    "developing",
    "code",
    "coding",
    "add",
    "adding",
)

_ENGINEERING_MARKERS = (
    "operator",
    "runtime",
    "schema",
    "registry",
    "scheduler",
    "actorhost",
    "agentactor",
    "logical_operator",
    "physicaloperator",
    "实现",
    "开发",
    "接入",
    "算子",
    "物理执行",
    "状态机",
    "注册",
)

_AMBIGUOUS_STRATEGY_ACTIONS = (
    "build",
    "create",
    "add",
)

_UNAMBIGUOUS_STRATEGY_ACTIONS = (
    "implement",
    "develop",
    "design",
    "architect",
    "refactor",
    "migrate",
    "integrate",
    "wire",
    "extend",
    "optimize",
    "实现",
    "开发",
    "接入",
    "增加",
    "改造",
    "迁移",
    "设计",
    "优化",
)

_NEGATION_CUE = re.compile(
    r"\b(?:do\s+not|does\s+not|did\s+not|not|no|never|without|rather\s+than|instead\s+of)\b"
    r"|\b(?:don't|doesn't|didn't|isn't|aren't|wasn't|weren't)\b",
    re.IGNORECASE,
)
_HARD_CLAUSE_BREAK = re.compile(r"[.!?;:\n]|\b(?:but|however|yet)\b", re.IGNORECASE)


def _marker_pattern(marker: str) -> re.Pattern[str]:
    marker = marker.strip().lower()
    if any(ord(character) > 127 for character in marker):
        return re.compile(re.escape(marker), re.IGNORECASE)
    return re.compile(
        rf"(?<![a-z0-9_]){re.escape(marker)}(?![a-z0-9_])",
        re.IGNORECASE,
    )


def _negation_scope_prefix(value: str, marker_start: int, *, marker_is_action: bool) -> str:
    """Return the local phrase whose negation can govern this marker.

    Intent routing only needs a bounded grammar distinction: requested output
    versus an explicitly excluded output. Hard punctuation and contrast words
    end negation scope. A comma also ends a fronted negative modifier when the
    following phrase starts a new delivery action (``without X, build Y``), or
    when a parenthetical negative phrase is enclosed by two commas. Commas in
    coordinated lists stay inside the scope (``not a CLI, package, or plugin``).
    """
    before = value[:marker_start]
    breaks = list(_HARD_CLAUSE_BREAK.finditer(before))
    clause = before[breaks[-1].end():] if breaks else before

    comma_positions = [index for index, character in enumerate(clause) if character == ","]
    if comma_positions:
        last_comma = comma_positions[-1]
        after_comma = clause[last_comma + 1:]
        starts_new_action = marker_is_action or any(
            _contains_marker(after_comma, action) for action in _DELIVERY_ACTIONS
        )
        enclosed_negative = False
        if len(comma_positions) >= 2:
            between_commas = clause[comma_positions[-2] + 1:last_comma]
            enclosed_negative = _NEGATION_CUE.search(between_commas) is not None
        if starts_new_action or enclosed_negative:
            clause = after_comma

    # These common modifiers contain negation-shaped tokens but affirm that a
    # software artifact is requested (for example, "build a no-code tool").
    clause = re.sub(r"\bnot\s+only\b", "", clause, flags=re.IGNORECASE)
    clause = re.sub(r"\bno[-\s]+code\b", "", clause, flags=re.IGNORECASE)
    return clause


def _requested_marker_matches(
    value: str,
    marker: str,
    *,
    marker_is_action: bool = False,
) -> list[re.Match[str]]:
    """Return marker occurrences that are requested, not locally negated."""
    requested: list[re.Match[str]] = []
    for match in _marker_pattern(marker).finditer(value):
        prefix = _negation_scope_prefix(value, match.start(), marker_is_action=marker_is_action)
        if _NEGATION_CUE.search(prefix) is None:
            requested.append(match)
    return requested


def _has_requested_action_artifact_pair(
    value: str,
    actions: tuple[str, ...],
    artifacts: tuple[str, ...],
    *,
    max_intervening_words: int,
) -> bool:
    """Recognize an action applied to a nearby artifact in the same clause.

    Global keyword co-occurrence confused the topic of a report with its
    requested output (``write a report comparing API schemas``). Pairing the
    action with the artifact it actually governs keeps technical subjects from
    overriding a research outcome while retaining real build requests.
    """
    for action in actions:
        action_matches = _requested_marker_matches(value, action, marker_is_action=True)
        for artifact in artifacts:
            artifact_matches = _requested_marker_matches(value, artifact)
            for action_match in action_matches:
                for artifact_match in artifact_matches:
                    if artifact_match.start() < action_match.end():
                        continue
                    between = value[action_match.end():artifact_match.start()]
                    if _HARD_CLAUSE_BREAK.search(between):
                        continue
                    intervening_words = re.findall(r"[a-z0-9_]+", between, flags=re.IGNORECASE)
                    if len(intervening_words) <= max_intervening_words:
                        return True
    return False


def _looks_like_research_request(value: str) -> bool:
    """Recognize evidence-seeking user outcomes without product-name patches."""
    explicit_markers = (
        "research",
        "report",
        "literature review",
        "survey",
        "white paper",
        "论文",
        "调研",
        "报告",
    )
    if any(_contains_marker(value, marker) for marker in explicit_markers):
        return True

    source_markers = (
        "sources",
        "citations",
        "references",
        "documentation",
        "official documentation",
        "docs",
        "websites",
        "web pages",
        "videos",
        "articles",
        "papers",
        "publications",
        "news coverage",
        "benchmark",
        "benchmarks",
        "links",
        "evidence",
    )
    research_actions = (
        "summarize",
        "summarizes",
        "summarizing",
        "summary",
        "compare",
        "compares",
        "comparing",
        "comparison",
        "evaluate",
        "evaluates",
        "evaluating",
        "analyze",
        "analyzes",
        "analyzing",
        "investigate",
        "investigates",
        "find",
        "gather",
        "review",
        "cite",
    )
    if any(_contains_marker(value, marker) for marker in source_markers) and any(
        _contains_marker(value, action) for action in research_actions
    ):
        return True

    comparative_markers = ("compare", "comparison", "versus", "vs", "between")
    decision_markers = ("which", "best", "recommend", "trade-off", "tradeoff")
    freshness_or_evidence = (
        "right now",
        "current",
        "latest",
        "today",
        "evidence",
        "cite",
        "sources",
    )
    return (
        any(_contains_marker(value, marker) for marker in comparative_markers)
        and any(_contains_marker(value, marker) for marker in decision_markers)
        and any(_contains_marker(value, marker) for marker in freshness_or_evidence)
    )


def _looks_like_technical_delivery_request(value: str) -> bool:
    """Keep requests to build software out of the research lane.

    The action alone is insufficient because people naturally say "build me a
    report".  It must be paired with a concrete software artifact.
    """
    return _has_requested_action_artifact_pair(
        value,
        _DELIVERY_ACTIONS,
        _TECHNICAL_ARTIFACTS,
        max_intervening_words=3,
    ) or _has_requested_action_artifact_pair(
        value,
        _UNAMBIGUOUS_SOFTWARE_ACTIONS,
        _TECHNICAL_ARTIFACTS,
        max_intervening_words=8,
    )


def _looks_like_engineering_strategy_request(value: str) -> bool:
    return _has_requested_action_artifact_pair(
        value,
        _AMBIGUOUS_STRATEGY_ACTIONS,
        _ENGINEERING_MARKERS,
        max_intervening_words=2,
    ) or _has_requested_action_artifact_pair(
        value,
        _UNAMBIGUOUS_STRATEGY_ACTIONS,
        _ENGINEERING_MARKERS,
        max_intervening_words=8,
    )


def _looks_like_direct_answer_request(value: str) -> bool:
    """Recognize bounded conversational answers that need no runtime DAG.

    This intentionally excludes requests whose answer depends on fresh data,
    supplied artifacts, retrieval, or an external effect.  Those requests must
    continue through research or delivery planning even when they are phrased
    as a question.
    """
    if not value.strip():
        return False
    if re.search(r"https?://|www\.", value, flags=re.IGNORECASE):
        return False
    if any(
        _contains_marker(value, marker)
        for marker in (
            "current",
            "latest",
            "today",
            "right now",
            "source",
            "sources",
            "citation",
            "citations",
            "attached",
            "attachment",
            "uploaded",
            "file",
            "repository",
            "repo",
            "codebase",
        )
    ):
        return False
    return bool(
        re.match(
            r"\s*(?:what|why|how|who|when|where|explain|describe|define|"
            r"tell\s+me|translate|rewrite|summarize)\b",
            value,
            flags=re.IGNORECASE,
        )
        or value.rstrip().endswith("?")
    )


def infer_mode(text: str) -> str:
    value = text.lower()
    # Failure/debug intent is more specific than the subsystem being repaired:
    # "fix the scheduler bug" is debugging, not generic runtime strategy.
    if any(token in value for token in ("debug", "bug", "失败", "报错", "修复", "卡住")):
        return "debug"
    if any(token in value for token in ("monitor", "heartbeat", "巡检", "监控")):
        return "monitor"
    # Engineering requests can contain "research" as a product name. Require a
    # positive action→subsystem relationship instead of letting a subsystem noun
    # anywhere in a sourced report override the user's research outcome.
    if _looks_like_engineering_strategy_request(value):
        return "strategy"
    if _looks_like_technical_delivery_request(value):
        return "delivery"
    if _looks_like_research_request(value):
        return "research"
    if any(token in value for token in ("架构", "设计", "strategy", "architecture")):
        return "strategy"
    if any(_contains_marker(value, token) for token in _ENGINEERING_MARKERS):
        return "strategy"
    if _looks_like_direct_answer_request(value):
        return "direct_answer"
    return "delivery"


def deterministic_rewrite(raw_text: str) -> dict[str, Any]:
    first = next((line.strip() for line in raw_text.splitlines() if line.strip()), raw_text.strip())
    # Display shortening only — the semantic objective below must carry the
    # complete request, or late instructions vanish from compiled requirements.
    title = re.sub(r"\s+", " ", first)[:90] or "Untitled Intent"
    objective = re.sub(r"\s+", " ", raw_text).strip() or title
    mode = infer_mode(raw_text)
    constraints: list[str] = [
        "All work must enter Solar-Harness through RawIntent and requirement compilation.",
    ]
    if mode == "direct_answer":
        constraints.extend(
            [
                "Do not claim retrieval, execution, file mutation, or other external effects.",
                "An independently accepted direct response must stop before task-graph runtime.",
            ]
        )
    else:
        constraints.append(
            "Do not bypass task_graph, operator runtime, quota-aware fallback, or evidence logging."
        )
    if mode == "debug":
        constraints.append("Capture failure evidence before changing implementation.")
    if mode == "research":
        constraints.append("Claims require source/evidence artifacts before final closeout.")
    acceptance = [
        "RawIntent, rewritten_intent, requirement_ir, and requirement_trace artifacts are persisted.",
        "Compiled work is routable through PM/Planner/task_graph and multi-task operator runtime.",
        "Completion requires evidence artifacts and verifier-visible status.",
    ]
    if mode == "direct_answer":
        acceptance = [
            "RawIntent, rewritten_intent, requirement_ir, and requirement_trace artifacts are persisted.",
            "The response directly answers the accepted request in the requested audience and format.",
            "Independent direct-response review passes before terminal closeout.",
        ]
    logical_operators = [
        "RequirementCompiler",
        "Planner",
        "ImplementationWorker",
        "Verifier",
    ]
    if mode == "direct_answer":
        logical_operators = [
            "RequirementCompiler",
            "Planner",
            "Verifier",
        ]
    if mode == "research":
        logical_operators = [
            "RequirementCompiler",
            "Planner",
            "ResearchScout",
            "ResearchSynthesizer",
            "Verifier",
        ]
    return {
        "schema_version": "solar.rewritten_intent.v1",
        "rewrite_method": "deterministic_fallback",
        "title": title,
        "problem": raw_text.strip(),
        "objective": objective,
        "outcome": (
            "A reviewed direct answer with no task-graph runtime."
            if mode == "direct_answer"
            else "A compiled, dispatchable Solar-Harness work item with acceptance evidence."
        ),
        "constraints": constraints,
        "non_goals": (
            ["Do not create or dispatch a runtime DAG for a bounded direct answer."]
            if mode == "direct_answer"
            else ["Do not dispatch raw natural language directly to builder panes."]
        ),
        "acceptance": acceptance,
        "suggested_lane": mode,
        "suggested_logical_operators": logical_operators,
    }


_READINESS_ANSWER_FIELDS = {
    "delivery_format",
    "execution_network",
    "mutation_policy",
    "objective",
    "target_choice",
}


def parse_clarification_answers(values: list[str] | None) -> dict[str, str]:
    """Parse explicit ``FIELD=VALUE`` answers accepted by the capture CLI."""
    answers: dict[str, str] = {}
    for raw_value in values or []:
        field, separator, value = str(raw_value).partition("=")
        field = field.strip()
        value = value.strip()
        if not separator or field not in _READINESS_ANSWER_FIELDS or not value:
            allowed = ", ".join(sorted(_READINESS_ANSWER_FIELDS))
            raise SystemExit(
                "--clarification-answer requires FIELD=VALUE with FIELD in: " + allowed
            )
        answers[field] = value
    return answers


def compile_ambiguity_readiness(
    raw_text: str,
    rewritten: dict[str, Any],
    *,
    requires_human_confirm: bool = False,
    answers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Return the minimum blocking questions needed before planning.

    This is intentionally a bounded, deterministic preflight. It does not try
    to turn every uncertainty into a conversation: only ambiguities that make
    execution unsafe or select mutually exclusive routes block readiness.
    Explicit ``answers`` resolve a named field and make the transition
    machine-readable without relying on prose inference.
    """
    supplied_answers = {
        str(field): str(value).strip()
        for field, value in (answers or {}).items()
        if str(field) in _READINESS_ANSWER_FIELDS and str(value).strip()
    }
    value = raw_text.strip()
    lowered = value.lower()
    blockers: list[dict[str, Any]] = []

    def add_blocker(
        *,
        reason: str,
        field: str,
        question: str,
        evidence_kind: str,
        evidence_matches: list[str],
    ) -> None:
        if field in supplied_answers or any(row["field"] == field for row in blockers):
            return
        blockers.append(
            {
                "reason": reason,
                "field": field,
                "question_id": f"clarify-{field.replace('_', '-')}",
                "question": question,
                "evidence": {
                    "kind": evidence_kind,
                    "matches": evidence_matches,
                },
            }
        )

    objective = str(rewritten.get("objective") or "").strip()
    if not objective:
        add_blocker(
            reason="missing_required_field",
            field="objective",
            question="What concrete outcome should this work produce?",
            evidence_kind="normalized_field",
            evidence_matches=["objective=empty"],
        )

    # Route choices expressed as "either X or Y" require one decision. The
    # question asks for that single decision instead of separately asking
    # about both alternatives.
    choice_match = re.search(
        r"\b(?:either|one\s+of)\s+([^.;\n]{1,80}?)\s+or\s+([^.;\n]{1,80})",
        value,
        re.IGNORECASE,
    )
    if choice_match:
        choices = [re.sub(r"\s+", " ", item).strip(" ,") for item in choice_match.groups()]
        add_blocker(
            reason="ambiguous_route_choice",
            field="target_choice",
            question=f"Which target should planning use: {choices[0]} or {choices[1]}?",
            evidence_kind="raw_request_span",
            evidence_matches=choices,
        )

    contradiction_rules = (
        (
            "execution_network",
            "conflicting_execution_constraints",
            (
                r"\b(?:offline|no\s+network|without\s+(?:the\s+)?internet)\b",
                r"\b(?:live|online|browse\s+(?:the\s+)?internet|current\s+web)\b",
            ),
            "Should execution remain offline, or may it access the live network?",
        ),
        (
            "mutation_policy",
            "conflicting_mutation_constraints",
            (
                r"\b(?:read[- ]only|do\s+not\s+(?:modify|change)|no\s+changes)\b",
                r"\b(?:implement|fix|patch|modify|change)\b",
            ),
            "May the implementation modify files, or must it remain read-only?",
        ),
        (
            "delivery_format",
            "conflicting_output_constraints",
            (r"\bjson\s+only\b", r"\bmarkdown\s+only\b"),
            "Which exclusive output format is required: JSON or Markdown?",
        ),
    )
    for field, reason, patterns, question in contradiction_rules:
        matches = []
        for pattern in patterns:
            match = re.search(pattern, lowered, re.IGNORECASE)
            if match:
                matches.append(match.group(0))
        if len(matches) == len(patterns):
            add_blocker(
                reason=reason,
                field=field,
                question=question,
                evidence_kind="conflicting_raw_request_spans",
                evidence_matches=matches,
            )

    # A clarification string is not attributable approval evidence.  Keep the
    # human gate closed until the dedicated approval workflow records it.
    if requires_human_confirm:
        add_blocker(
            reason="required_approval_missing",
            field="approval",
            question="Do you approve dispatching this compiled intent to planning?",
            evidence_kind="routing_hint",
            evidence_matches=["requires_human_confirm=true"],
        )

    return {
        "schema_version": "solar.intent_readiness.v1",
        "status": "ready" if not blockers else "needs_clarification",
        "ready": not blockers,
        "blocking_count": len(blockers),
        "unresolved": blockers,
        "questions": [
            {
                "question_id": blocker["question_id"],
                "field": blocker["field"],
                "question": blocker["question"],
                "reason": blocker["reason"],
            }
            for blocker in blockers
        ],
        "applied_answers": supplied_answers,
        "planning_admitted": not blockers,
        "next_action": "plan" if not blockers else "clarify",
        "policy": "Only ambiguities that block safe route selection or execution are questions.",
    }


def model_rewrite(raw_intent: dict[str, Any], prompt_path: Path) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    cmd = os.environ.get("SOLAR_INTENT_REWRITE_CMD", "").strip()
    if not cmd:
        return None, {"attempted": False, "reason": "SOLAR_INTENT_REWRITE_CMD_not_set"}
    prompt = {
        "instruction": (
            "Rewrite the RawIntent into strict JSON with keys: title, problem, "
            "objective, outcome, constraints, non_goals, acceptance, suggested_lane, "
            "suggested_logical_operators. Do not invent external facts."
        ),
        "raw_intent": raw_intent,
    }
    write_json(prompt_path, prompt)
    env = dict(os.environ)
    env["SOLAR_INTENT_REWRITE_PROMPT"] = str(prompt_path)
    try:
        proc = subprocess.run(
            ["bash", "-lc", cmd],
            text=True,
            capture_output=True,
            timeout=int(os.environ.get("SOLAR_INTENT_REWRITE_TIMEOUT_SEC", "90") or "90"),
            env=env,
        )
    except subprocess.TimeoutExpired:
        return None, {"attempted": True, "status": "timeout"}
    output = (proc.stdout or "").strip()
    meta = {"attempted": True, "exit_code": proc.returncode, "stderr_tail": (proc.stderr or "")[-1000:]}
    if proc.returncode != 0 or not output:
        meta["status"] = "failed"
        return None, meta
    try:
        parsed = json.loads(output)
        if isinstance(parsed, dict):
            parsed.setdefault("schema_version", "solar.rewritten_intent.v1")
            parsed["rewrite_method"] = "model"
            meta["status"] = "ok"
            return parsed, meta
    except Exception:
        pass
    fallback = deterministic_rewrite(output)
    fallback["rewrite_method"] = "model_text_normalized"
    meta["status"] = "text_normalized"
    return fallback, meta


def _planner_workflow_candidates(request: str, lane: str) -> list[dict[str, Any]]:
    """Expose memoized TaskGraphs to the planner without selecting one."""
    if str(lane or "").strip().lower() != "research":
        return []
    try:
        from workflow_router import FIXED_RESEARCH_WORKFLOW_ID, classify_research_request

        hint = classify_research_request(request)
        profile_hint = str(hint.get("execution_profile") or "part_a_only")
        reason = str(hint.get("reason") or "Requirement IR classified the request as research")
    except Exception as exc:
        # Candidate discovery is advisory. Requirement compilation and planner
        # handoff remain available when the template catalog cannot be loaded.
        FIXED_RESEARCH_WORKFLOW_ID = "research.evidence_to_poc.v1"
        profile_hint = "part_a_only"
        reason = f"research lane candidate; classifier unavailable: {type(exc).__name__}"
    return [
        {
            "workflow_id": FIXED_RESEARCH_WORKFLOW_ID,
            "candidate_kind": "memoized_task_graph",
            "selection_authority": "planner",
            "auto_instantiate": False,
            "execution_profile_hint": profile_hint,
            "reason": reason,
        }
    ]


def build_requirement_ir(intent_id: str, raw_intent: dict[str, Any], rewritten: dict[str, Any]) -> dict[str, Any]:
    context = raw_intent.get("context", {}) if isinstance(raw_intent.get("context"), dict) else {}
    raw_block = raw_intent.get("raw", {}) if isinstance(raw_intent.get("raw"), dict) else {}
    research = raw_intent.get("research") if isinstance(raw_intent.get("research"), dict) else None
    source_inputs: dict[str, Any] = {
        "raw_request": str(raw_block.get("text") or "").strip(),
        "repo_context": [context.get("repo")] if context.get("repo") else [],
    }
    if research:
        source_inputs["research_artifact"] = {
            "path": research.get("path", ""),
            "project_name": research.get("project_name", ""),
            "conversation_id": research.get("conversation_id", ""),
            "source_url": research.get("source_url", ""),
        }
    attachments = raw_block.get("attachments") if isinstance(raw_block.get("attachments"), list) else []
    if attachments:
        source_inputs["attachments"] = attachments
    routing_hints = (
        raw_intent.get("routing_hints", {})
        if isinstance(raw_intent.get("routing_hints"), dict)
        else {}
    )
    clarifications = (
        raw_intent.get("clarifications", {})
        if isinstance(raw_intent.get("clarifications"), dict)
        else {}
    )
    answers = clarifications.get("answers", {}) if isinstance(clarifications.get("answers"), dict) else {}
    readiness = compile_ambiguity_readiness(
        str(raw_block.get("text") or ""),
        rewritten,
        requires_human_confirm=bool(routing_hints.get("requires_human_confirm")),
        answers=answers,
    )
    lane = str(rewritten.get("suggested_lane") or "delivery")
    workflow_candidates = _planner_workflow_candidates(
        str(raw_block.get("text") or ""),
        lane,
    )
    planner_hints: dict[str, Any] = {
        "workflow_candidates": workflow_candidates,
        "selection_authority": "planner",
        "response_authority": "planner",
        "allowed_outcomes": ["direct_answer", "memoized_task_graph", "new_task_graph"],
    }
    if lane == "direct_answer":
        planner_hints["preferred_outcome"] = "direct_answer"
        planner_hints["runtime_handoff_allowed"] = False
    return {
        "schema_version": "solar.requirement_ir.v1",
        "intent_id": intent_id,
        "source": raw_intent.get("source", {}),
        "source_inputs": source_inputs,
        "title": rewritten.get("title", ""),
        "problem": rewritten.get("problem", ""),
        "objective": rewritten.get("objective", ""),
        "outcome": rewritten.get("outcome", ""),
        "constraints": rewritten.get("constraints", []),
        "non_goals": rewritten.get("non_goals", []),
        "acceptance": rewritten.get("acceptance", []),
        "lane": lane,
        "logical_operators": rewritten.get("suggested_logical_operators", []),
        "planner_hints": planner_hints,
        "readiness": readiness,
        "compiler_next": (
            "pm_elastic_planner"
            if readiness["ready"] and lane == "direct_answer"
            else "pm_planner_task_graph"
            if readiness["ready"]
            else "clarification_required"
        ),
    }


def compile_and_evaluate_requirement_bundle(
    intent_ir: dict[str, Any], intent_acceptance: dict[str, Any],
    *, work_dir: Path, model: Any = None, reviewer: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compile an admitted IntentIR and run the independent deterministic gate."""
    from intent_compiler import requirement_handoff
    from requirement_compiler import evaluate_requirement_ir_format
    from requirement_compiler.semantic import compile_semantic_requirement_ir

    handoff = requirement_handoff(intent_ir, intent_acceptance)
    intent_digest = handoff["intent_ir_sha256"]
    requirement_ir = compile_semantic_requirement_ir(
        intent_ir,
        intent_ir_sha256=intent_digest,
        work_dir=work_dir, model=model, reviewer=reviewer,
    )
    evaluation = evaluate_requirement_ir_format(
        requirement_ir,
        intent_ir=intent_ir,
        intent_ir_sha256=intent_digest,
        intent_acceptance=intent_acceptance,
    )
    return requirement_ir, evaluation


def capture(args: argparse.Namespace) -> dict[str, Any]:
    raw_text = read_text_arg(args)
    formal_intent_required = _llm_intent_compiler_required(args.source_channel)
    created = now_iso()
    digest = hashlib.sha1(f"{created}\n{raw_text}".encode("utf-8")).hexdigest()[:10]
    intent_id = args.intent_id or f"intent-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d-%H%M%S')}-{digest}"
    research = extract_research_artifact(args)
    attachments = intake_attachments_from_env()
    clarification_answers = parse_clarification_answers(
        getattr(args, "clarification_answer", None)
    )
    raw_intent = {
        "schema_version": "solar.raw_intent.v1",
        "intent_id": intent_id,
        "source": {
            "channel": args.source_channel,
            "actor": args.actor,
            "device": args.device,
            "session_id": args.session_id,
            "thread_ref": args.thread_ref,
        },
        "raw": {
            "text": raw_text,
            "attachments": attachments,
            "quoted_context": [],
            "received_at": created,
        },
        "context": {
            "repo": args.repo or "",
            "cwd": str(Path.cwd()),
            "related_sprints": [],
            "knowledge_query": args.knowledge_query or "",
        },
        "routing_hints": {
            "urgency": args.urgency,
            # A production IntentIR is semantic authority.  Keep an explicit
            # caller override, and retain the heuristic only for the named
            # offline/CLI compatibility path.
            "mode": args.mode or ("" if formal_intent_required else infer_mode(raw_text)),
            "allow_autodispatch": not args.no_autodispatch,
            "requires_human_confirm": args.requires_human_confirm,
            "require_research_artifact": bool(args.require_research_artifact or research),
        },
        "trust": {
            "source_trust": args.source_trust,
            "prompt_injection_risk": "unknown",
            "contains_secrets": "unknown",
        },
    }
    if clarification_answers:
        raw_intent["clarifications"] = {"answers": clarification_answers}
    if research:
        raw_intent["research"] = research
    base = INTENTS_DIR / intent_id
    artifact_compiler_provider = os.environ.get("SOLAR_INTENT_COMPILER_PROVIDER", "").strip()
    if not artifact_compiler_provider and formal_intent_required:
        # The formal compiler currently supports Codex and model_from_environment
        # already defaults both compiler and independent reviewer to that
        # provider.  Setting the sentinel here makes the production contract
        # explicit and prevents the legacy deterministic implementation label.
        artifact_compiler_provider = "codex"
    if artifact_compiler_provider:
        from intent_compiler import (
            model_from_environment,
            run_pipeline,
        )

        compiler_result = run_pipeline(
            raw_intent,
            base / "intent",
            model_from_environment("compiler"),
            model_from_environment("reviewer"),
        )
        acceptance = compiler_result["intent_acceptance"]
        accepted_intent = compiler_result.get("intent_ir")
        write_json(base / "raw_intent.json", raw_intent)
        candidate_trace_artifacts = {
            "raw_intent": str(base / "raw_intent.json"),
            "input": str(base / "intent" / "input.json"),
            "intent_ir": str(base / "intent" / "intent_ir.json"),
            "intent_validation": str(base / "intent" / "intent_validation.json"),
            "intent_fidelity": str(base / "intent" / "intent_fidelity.json"),
            "intent_acceptance": str(base / "intent" / "intent_acceptance.json"),
        }
        trace_artifacts = {
            name: path
            for name, path in candidate_trace_artifacts.items()
            if Path(path).exists()
        }
        trace = {
            "schema_version": "solar.requirement_trace.v1",
            "intent_id": intent_id,
            "created_at": created,
            "artifacts": trace_artifacts,
            "stages": [
                {"stage": "raw_intent_capture", "status": "ok"},
                {
                    "stage": "intent_ir_compile",
                    "status": "ok" if accepted_intent else "failed",
                    "provider": artifact_compiler_provider,
                },
                {
                    "stage": "intent_validation",
                    "status": (
                        compiler_result.get("intent_validation") or {"status": "not_run"}
                    ).get("status"),
                },
                {
                    "stage": "intent_fidelity",
                    "status": (
                        compiler_result.get("intent_fidelity") or {"status": "not_run"}
                    ).get("status"),
                },
                {
                    "stage": "intent_acceptance",
                    "status": acceptance["decision"],
                    "repair_attempted": acceptance["repair"]["attempted"],
                },
            ],
        }
        if acceptance["decision"] != "accepted" or not accepted_intent:
            raw_intent["routing_hints"]["allow_autodispatch"] = False
            raw_intent["routing_hints"]["readiness_blocked"] = True
            write_json(base / "raw_intent.json", raw_intent)
            write_json(base / "requirement_trace.json", trace)
            return {
                "ok": True,
                "intent_id": intent_id,
                "title": None,
                "lane": None,
                "ready": False,
                "readiness_status": acceptance["decision"],
                "clarification_questions": acceptance["clarification_questions"],
                "rewrite_method": "intent_ir_v3",
                "raw_intent": str(base / "raw_intent.json"),
                "intent_ir": (
                    str(base / "intent" / "intent_ir.json")
                    if (base / "intent" / "intent_ir.json").exists()
                    else None
                ),
                "intent_validation": (
                    str(base / "intent" / "intent_validation.json")
                    if (base / "intent" / "intent_validation.json").exists()
                    else None
                ),
                "intent_fidelity": (
                    str(base / "intent" / "intent_fidelity.json")
                    if (base / "intent" / "intent_fidelity.json").exists()
                    else None
                ),
                "intent_acceptance": str(base / "intent" / "intent_acceptance.json"),
                "requirement_trace": str(base / "requirement_trace.json"),
            }
        requirement_ir, requirement_evaluation = compile_and_evaluate_requirement_bundle(
            accepted_intent,
            acceptance,
            work_dir=base / "requirement",
        )
        requirement_ir_path = base / "requirement_ir.json"
        requirement_evaluation_path = base / "requirement_format_evaluation.json"
        trace["artifacts"].update(
            {
                "requirement_ir": str(requirement_ir_path),
                "requirement_format_evaluation": str(requirement_evaluation_path),
            }
        )
        trace["stages"].extend(
            [
                {"stage": "requirement_ir_compile", "status": "ok"},
                {
                    "stage": "requirement_format_evaluation",
                    "status": requirement_evaluation["status"],
                    "defect_count": len(requirement_evaluation["defects"]),
                },
            ]
        )
        write_json(requirement_ir_path, requirement_ir)
        write_json(requirement_evaluation_path, requirement_evaluation)
        if requirement_evaluation["status"] != "pass":
            raw_intent["routing_hints"]["allow_autodispatch"] = False
            raw_intent["routing_hints"]["readiness_blocked"] = True
            write_json(base / "raw_intent.json", raw_intent)
            write_json(base / "requirement_trace.json", trace)
            return {
                "ok": True,
                "intent_id": intent_id,
                "title": None,
                "lane": None,
                "ready": False,
                "readiness_status": "requirement_evaluation_failed",
                "clarification_questions": [],
                "rewrite_method": "intent_ir_v3",
                "raw_intent": str(base / "raw_intent.json"),
                "intent_ir": str(base / "intent" / "intent_ir.json"),
                "intent_validation": str(base / "intent" / "intent_validation.json"),
                "intent_fidelity": str(base / "intent" / "intent_fidelity.json"),
                "intent_acceptance": str(base / "intent" / "intent_acceptance.json"),
                "requirement_ir": str(requirement_ir_path),
                "requirement_evaluation": str(requirement_evaluation_path),
                "requirement_trace": str(base / "requirement_trace.json"),
            }
        write_json(base / "requirement_trace.json", trace)
        if args.sprint_id:
            bind_intent_artifacts(intent_id, args.sprint_id)
        goals = accepted_intent.get("goals") or []
        title = (
            str(goals[0].get("statement") or "")[:90]
            if goals and isinstance(goals[0], dict)
            else None
        )
        return {
            "ok": True,
            "intent_id": intent_id,
            "title": title,
            # Intent compilation must not choose a workflow lane.  The typed
            # Elastic Planner owns direct_response/exact_reuse/generate.
            "lane": None,
            "ready": True,
            "readiness_status": acceptance["decision"],
            "clarification_questions": acceptance["clarification_questions"],
            "rewrite_method": "intent_ir_v3",
            "raw_intent": str(base / "raw_intent.json"),
            "intent_ir": str(base / "intent" / "intent_ir.json"),
            "intent_validation": str(base / "intent" / "intent_validation.json"),
            "intent_fidelity": str(base / "intent" / "intent_fidelity.json"),
            "intent_acceptance": str(base / "intent" / "intent_acceptance.json"),
            "requirement_ir": str(requirement_ir_path),
            "requirement_evaluation": str(requirement_evaluation_path),
            "requirement_trace": str(base / "requirement_trace.json"),
        }
    model_result, rewrite_meta = model_rewrite(raw_intent, base / "rewrite_prompt.json")
    rewritten = model_result or deterministic_rewrite(raw_text)
    rewritten["intent_id"] = intent_id
    rewritten["model_rewrite"] = rewrite_meta
    requirement_ir = build_requirement_ir(intent_id, raw_intent, rewritten)
    readiness = requirement_ir["readiness"]
    if not readiness["ready"]:
        # The consumer's normal planner handoff policy reads this routing hint.
        # Capturing evidence remains allowed, but automatic planning is closed
        # until every blocking field has an explicit answer.
        raw_intent["routing_hints"]["allow_autodispatch"] = False
        raw_intent["routing_hints"]["readiness_blocked"] = True
    trace = {
        "schema_version": "solar.requirement_trace.v1",
        "intent_id": intent_id,
        "created_at": created,
        "artifacts": {
            "raw_intent": str(base / "raw_intent.json"),
            "rewritten_intent": str(base / "rewritten_intent.json"),
            "requirement_ir": str(base / "requirement_ir.json"),
        },
        "stages": [
            {"stage": "raw_intent_capture", "status": "ok"},
            {"stage": "intent_rewrite", "status": "ok", "method": rewritten.get("rewrite_method")},
            {
                "stage": "ambiguity_readiness",
                "status": readiness["status"],
                "blocking_count": readiness["blocking_count"],
            },
            {
                "stage": "requirement_ir_compile",
                "status": "ok" if readiness["ready"] else "blocked",
            },
        ],
    }
    write_json(base / "raw_intent.json", raw_intent)
    write_json(base / "rewritten_intent.json", rewritten)
    write_json(base / "requirement_ir.json", requirement_ir)
    write_json(base / "requirement_trace.json", trace)
    if args.sprint_id:
        bind_intent_artifacts(intent_id, args.sprint_id)
    return {
        "ok": True,
        "intent_id": intent_id,
        "title": rewritten.get("title"),
        "lane": requirement_ir.get("lane"),
        "ready": requirement_ir["readiness"]["ready"],
        "readiness_status": requirement_ir["readiness"]["status"],
        "clarification_questions": requirement_ir["readiness"]["questions"],
        "rewrite_method": rewritten.get("rewrite_method"),
        "raw_intent": str(base / "raw_intent.json"),
        "rewritten_intent": str(base / "rewritten_intent.json"),
        "requirement_ir": str(base / "requirement_ir.json"),
        "requirement_trace": str(base / "requirement_trace.json"),
    }


def bind_intent_artifacts(intent_id: str, sprint_id: str) -> dict[str, Any]:
    base = INTENTS_DIR / intent_id
    if not (base / "raw_intent.json").exists():
        raise SystemExit(f"unknown intent_id: {intent_id}")
    mapping = {
        "raw_intent.json": SPRINTS_DIR / f"{sprint_id}.raw_intent.json",
        "requirement_ir.json": SPRINTS_DIR / f"{sprint_id}.requirement_ir.json",
        "requirement_trace.json": SPRINTS_DIR / f"{sprint_id}.requirement_trace.json",
    }
    optional_mapping = {
        "rewritten_intent.json": SPRINTS_DIR / f"{sprint_id}.rewritten_intent.json",
        "requirement_format_evaluation.json": SPRINTS_DIR
        / f"{sprint_id}.requirement_format_evaluation.json",
        "intent/input.json": SPRINTS_DIR / f"{sprint_id}.input.json",
        "intent/intent_ir.json": SPRINTS_DIR / f"{sprint_id}.intent_ir.json",
        "intent/intent_validation.json": SPRINTS_DIR / f"{sprint_id}.intent_validation.json",
        "intent/intent_fidelity.json": SPRINTS_DIR / f"{sprint_id}.intent_fidelity.json",
        "intent/intent_acceptance.json": SPRINTS_DIR / f"{sprint_id}.intent_acceptance.json",
    }
    immutable_compiler_artifacts = {
        name
        for name in optional_mapping
        if name.startswith("intent/") or name == "requirement_format_evaluation.json"
    }
    mapping.update(
        {name: destination for name, destination in optional_mapping.items() if (base / name).exists()}
    )
    for name, dst in mapping.items():
        source_path = base / name
        if name == "requirement_ir.json":
            source_requirement = json.loads(source_path.read_text(encoding="utf-8"))
            if source_requirement.get("schema_version") == "solar.requirement_ir.v2":
                dst.parent.mkdir(parents=True, exist_ok=True)
                temporary = dst.with_suffix(dst.suffix + ".tmp")
                temporary.write_bytes(source_path.read_bytes())
                os.replace(temporary, dst)
                continue
        if name in immutable_compiler_artifacts:
            dst.parent.mkdir(parents=True, exist_ok=True)
            temporary = dst.with_suffix(dst.suffix + ".tmp")
            temporary.write_bytes(source_path.read_bytes())
            os.replace(temporary, dst)
            continue
        gateway_payload = json.loads(source_path.read_text(encoding="utf-8"))
        payload = gateway_payload
        if (
            dst.exists()
            and not dst.is_symlink()
            and name in {"requirement_ir.json", "requirement_trace.json"}
        ):
            try:
                compiled = json.loads(dst.read_text(encoding="utf-8"))
            except Exception:
                compiled = None
            compiled_ir = (
                name == "requirement_ir.json"
                and isinstance(compiled, dict)
                and compiled.get("schema_version") == "solar.requirement_ir.v1"
                and bool(compiled.get("id"))
            )
            compiled_trace = (
                name == "requirement_trace.json"
                and isinstance(compiled, dict)
                and compiled.get("schema_version") == "solar.requirement_trace.v1"
                and bool(compiled.get("requirement_ir_id"))
                and isinstance(compiled.get("items"), list)
            )
            if compiled_ir or compiled_trace:
                # The requirement compiler runs before RawIntent binding and
                # writes the richer, acceptance-mapped package at this path.
                # Never replace it with the gateway's earlier capture-stage
                # placeholder.  Bind ingress identity into the compiled
                # artifact while preserving its requirements and trace.
                payload = compiled
                payload["intent_id"] = intent_id
                payload["sprint_id"] = sprint_id
                if compiled_ir:
                    gateway_source = gateway_payload.get("source")
                    if not payload.get("source") and isinstance(gateway_source, dict):
                        payload["source"] = gateway_source
                    gateway_planner_hints = gateway_payload.get("planner_hints")
                    if (
                        not payload.get("planner_hints")
                        and isinstance(gateway_planner_hints, dict)
                    ):
                        payload["planner_hints"] = gateway_planner_hints
                    compiled_inputs = payload.get("source_inputs")
                    if not isinstance(compiled_inputs, dict):
                        compiled_inputs = {}
                    gateway_inputs = gateway_payload.get("source_inputs")
                    if isinstance(gateway_inputs, dict):
                        for key in ("raw_request", "repo_context", "research_artifact", "attachments"):
                            if not compiled_inputs.get(key) and gateway_inputs.get(key):
                                compiled_inputs[key] = gateway_inputs[key]
                    payload["source_inputs"] = compiled_inputs
        if isinstance(payload, dict):
            payload["sprint_id"] = sprint_id
        write_json(dst, payload)
    manifest = {"ok": True, "intent_id": intent_id, "sprint_id": sprint_id, "artifacts": {k: str(v) for k, v in mapping.items()}}
    write_json(base / "binding.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="intent_gateway.py")
    sub = parser.add_subparsers(dest="cmd", required=True)
    cap = sub.add_parser("capture")
    cap.add_argument("--text", default="")
    cap.add_argument("--file", default="")
    cap.add_argument("--stdin", action="store_true")
    cap.add_argument("--intent-id", default="")
    cap.add_argument("--source-channel", default="cli")
    cap.add_argument("--actor", default="user")
    cap.add_argument("--device", default="")
    cap.add_argument("--session-id", default="")
    cap.add_argument("--thread-ref", default="")
    cap.add_argument("--repo", default="")
    cap.add_argument("--knowledge-query", default="")
    cap.add_argument("--urgency", default="normal")
    cap.add_argument("--mode", default="")
    cap.add_argument("--source-trust", default="user_direct")
    cap.add_argument("--no-autodispatch", action="store_true")
    cap.add_argument("--requires-human-confirm", action="store_true")
    cap.add_argument(
        "--clarification-answer",
        action="append",
        default=[],
        metavar="FIELD=VALUE",
        help="Resolve one readiness field; repeat for multiple answers.",
    )
    cap.add_argument("--require-research-artifact", action="store_true")
    cap.add_argument("--research-artifact", default="")
    cap.add_argument("--research-project-name", default="")
    cap.add_argument("--research-conversation-id", default="")
    cap.add_argument("--research-source-url", default="")
    cap.add_argument("--sprint-id", default="")
    cap.add_argument("--json", action="store_true")

    bind = sub.add_parser("bind")
    bind.add_argument("--intent-id", required=True)
    bind.add_argument("--sprint-id", required=True)
    bind.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    if args.cmd == "capture":
        payload = capture(args)
    elif args.cmd == "bind":
        payload = bind_intent_artifacts(args.intent_id, args.sprint_id)
    else:
        raise SystemExit(f"unknown command: {args.cmd}")
    if getattr(args, "json", False):
        # Keep machine-readable stdout ASCII-safe. Windows callers commonly
        # decode subprocess output using their active code page (for example,
        # CP1252); JSON escapes preserve Unicode across that boundary.
        print(json.dumps(payload, ensure_ascii=True, indent=2))
    else:
        print(f"intent_id={payload.get('intent_id')} rewrite={payload.get('rewrite_method', 'N/A')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
