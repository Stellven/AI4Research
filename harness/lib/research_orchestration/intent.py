"""Pure deterministic intent classification for research orchestration.

This module only classifies user intent and suggests a workflow family. It does
not dispatch workflows, mutate route registries, call providers, or touch files.
"""

from __future__ import annotations

import re
from typing import Any


class ResearchIntentError(ValueError):
    """Raised when research intent inputs cannot be classified safely."""


SEED_KINDS = frozenset(
    {
        "url",
        "pdf",
        "markdown",
        "topic",
        "research_brief",
        "external_evidence",
    }
)

WORKFLOW_KINDS = frozenset(
    {
        "research_synthesis",
        "paper_ingestion",
        "literature_synthesis",
        "scientific_lifecycle",
        "workflow_evolution",
    }
)

RUN_MODES = frozenset({"execute", "resume", "import_evidence"})

_URL_RE = re.compile(r"https?://[^\s)>\]]+", re.IGNORECASE)
_PDF_RE = re.compile(r"(?<!\w)[^\s]+\.pdf\b", re.IGNORECASE)
_MARKDOWN_RE = re.compile(r"(?<!\w)[^\s]+\.(?:md|markdown)\b", re.IGNORECASE)

_REPORT_SIGNALS = (
    "report",
    "survey",
    "trend",
    "trends",
    "analysis",
    "analyze",
    "analyse",
    "compare",
    "comparison",
    "报告",
    "调研",
    "综述",
    "趋势",
    "分析",
)

_LITERATURE_SIGNALS = (
    "survey",
    "literature",
    "literature review",
    "related work",
    "state of the art",
    "report",
    "综述",
    "文献",
    "调研",
    "报告",
)

_LIFECYCLE_SIGNALS = (
    "hypothesis",
    "hypothesize",
    "experiment",
    "experimental",
    "validate hypothesis",
    "test hypothesis",
    "full lifecycle",
    "scientific lifecycle",
    "paper submission",
    "验证假设",
    "实验",
    "论文投稿",
    "完整科研流程",
)

_WORKFLOW_EVOLUTION_SIGNALS = (
    "failed workflow",
    "workflow failure",
    "repair workflow",
    "postmortem",
    "retro",
    "improve workflow",
    "optimize workflow",
    "workflow evolution",
    "失败流程",
    "流程失败",
    "改进流程",
    "优化研究流程",
    "复盘",
)


def classify_research_intent(
    prompt: str,
    *,
    seed_inputs: list[dict] | None = None,
    explicit_workflow: str | None = None,
    run_mode: str = "execute",
) -> dict:
    """Classify seed and workflow intent without side effects."""

    if not isinstance(prompt, str) or not prompt.strip():
        raise ResearchIntentError("prompt must be a non-empty string")

    normalized_run_mode = _validate_enum("run_mode", run_mode, RUN_MODES)
    normalized_explicit = (
        _validate_enum("explicit_workflow", explicit_workflow, WORKFLOW_KINDS)
        if explicit_workflow is not None
        else None
    )

    prompt_text = prompt.strip()
    prompt_lower = prompt_text.lower()
    reason_codes: list[str] = []

    seed_kind, seed_reasons = _classify_seed_kind(prompt_text, seed_inputs)
    reason_codes.extend(seed_reasons)

    if seed_kind == "external_evidence" and normalized_run_mode not in {"resume", "import_evidence"}:
        raise ResearchIntentError("external_evidence seed_kind requires run_mode resume or import_evidence")

    requires_user_confirmation = False
    confidence = 0.64

    if normalized_explicit:
        workflow_kind = normalized_explicit
        reason_codes.append("explicit_workflow_selected")
        confidence = 0.98
    elif _has_any(prompt_lower, _WORKFLOW_EVOLUTION_SIGNALS):
        workflow_kind = "workflow_evolution"
        reason_codes.append("workflow_evolution_signal")
        confidence = 0.9
    elif seed_kind == "external_evidence":
        workflow_kind = "scientific_lifecycle"
        reason_codes.append(f"{normalized_run_mode}_external_evidence")
        confidence = 0.78
    elif _has_any(prompt_lower, _LIFECYCLE_SIGNALS):
        workflow_kind = "scientific_lifecycle"
        reason_codes.append("scientific_lifecycle_signal")
        confidence = 0.88
    elif seed_kind in {"pdf", "markdown"}:
        workflow_kind = "paper_ingestion"
        reason_codes.append(f"{seed_kind}_paper_ingestion_signal")
        confidence = 0.86
    elif seed_kind == "url" and _has_any(prompt_lower, _REPORT_SIGNALS):
        workflow_kind = "research_synthesis"
        reason_codes.append("url_report_synthesis_signal")
        confidence = 0.86
    elif seed_kind == "research_brief":
        workflow_kind = "research_synthesis"
        reason_codes.append("research_brief_synthesis_signal")
        confidence = 0.78
    elif seed_kind == "topic" and _has_any(prompt_lower, _LITERATURE_SIGNALS):
        workflow_kind = "literature_synthesis"
        reason_codes.append("topic_literature_synthesis_signal")
        confidence = 0.82
    else:
        workflow_kind = "literature_synthesis"
        requires_user_confirmation = True
        reason_codes.append("ambiguous_conservative_literature_suggestion")
        confidence = 0.42

    if normalized_run_mode != "execute":
        reason_codes.append(f"run_mode_{normalized_run_mode}")

    return {
        "seed_kind": seed_kind,
        "workflow_kind": workflow_kind,
        "run_mode": normalized_run_mode,
        "reason_codes": _dedupe(reason_codes),
        "confidence": round(confidence, 2),
        "requires_user_confirmation": requires_user_confirmation,
    }


def _validate_enum(name: str, value: str, allowed: frozenset[str]) -> str:
    if not isinstance(value, str):
        raise ResearchIntentError(f"{name} must be a string")
    normalized = value.strip().lower()
    if normalized not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise ResearchIntentError(f"{name} must be one of: {allowed_values}")
    return normalized


def _classify_seed_kind(prompt: str, seed_inputs: list[dict] | None) -> tuple[str, list[str]]:
    reasons: list[str] = []
    detected: list[str] = []

    for item in seed_inputs or []:
        if not isinstance(item, dict):
            raise ResearchIntentError("seed_inputs must contain dictionaries")
        seed_kind = _seed_kind_from_mapping(item)
        if seed_kind:
            detected.append(seed_kind)
            reasons.append(f"seed_input_{seed_kind}")

    prompt_lower = prompt.lower()
    if _URL_RE.search(prompt):
        detected.append("url")
        reasons.append("prompt_url")
    if _PDF_RE.search(prompt) or "pdf" in prompt_lower and _has_paper_file_signal(prompt_lower):
        detected.append("pdf")
        reasons.append("prompt_pdf")
    if _MARKDOWN_RE.search(prompt) or "markdown" in prompt_lower and _has_paper_file_signal(prompt_lower):
        detected.append("markdown")
        reasons.append("prompt_markdown")
    if "research brief" in prompt_lower or "研究简报" in prompt_lower:
        detected.append("research_brief")
        reasons.append("prompt_research_brief")
    if "external evidence" in prompt_lower or "外部证据" in prompt_lower:
        detected.append("external_evidence")
        reasons.append("prompt_external_evidence")

    if detected:
        return _highest_priority_seed(detected), reasons

    return "topic", ["implicit_topic"]


def _seed_kind_from_mapping(item: dict[str, Any]) -> str | None:
    for key in ("seed_kind", "kind", "type", "source_type", "input_type"):
        value = item.get(key)
        if isinstance(value, str):
            normalized = value.strip().lower().replace("-", "_")
            aliases = {"web_url": "url", "paper_pdf": "pdf", "md": "markdown", "evidence": "external_evidence"}
            normalized = aliases.get(normalized, normalized)
            if normalized in SEED_KINDS:
                return normalized
            if key == "seed_kind":
                allowed_values = ", ".join(sorted(SEED_KINDS))
                raise ResearchIntentError(f"seed_kind must be one of: {allowed_values}")

    url_value = item.get("url") or item.get("source_url")
    if isinstance(url_value, str) and _URL_RE.search(url_value):
        return "url"

    for key in ("path", "file", "filename", "source_ref"):
        value = item.get(key)
        if isinstance(value, str):
            lower = value.lower()
            if lower.endswith(".pdf"):
                return "pdf"
            if lower.endswith((".md", ".markdown")):
                return "markdown"

    content_type = item.get("content_type")
    if isinstance(content_type, str) and "markdown" in content_type.lower():
        return "markdown"
    if "research_brief" in item or "brief" in item:
        return "research_brief"
    if "evidence_path" in item or "evidence" in item:
        return "external_evidence"
    return None


def _highest_priority_seed(seed_kinds: list[str]) -> str:
    priority = ("external_evidence", "pdf", "markdown", "url", "research_brief", "topic")
    seen = set(seed_kinds)
    for candidate in priority:
        if candidate in seen:
            return candidate
    return "topic"


def _has_any(text: str, signals: tuple[str, ...]) -> bool:
    return any(signal in text for signal in signals)


def _has_paper_file_signal(text: str) -> bool:
    return any(signal in text for signal in ("file", "path", "paper", "论文", "文件", "本地"))


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped
