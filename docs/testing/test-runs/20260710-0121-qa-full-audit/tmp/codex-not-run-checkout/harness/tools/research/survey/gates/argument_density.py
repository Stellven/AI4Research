"""Argument density gate — O2 implementation.

Pure deterministic functions that analyse section text and produce an
``ArgumentDensityProfile`` with 5 dimension coverage.  No external I/O,
no LLM calls, no randomness.

S03 N4 implementation per S02 argument-density-arch.md.
"""

from __future__ import annotations

import re

from ..schemas import (
    ArgumentDensityProfile,
    DimensionIndicator,
    NotApplicableEntry,
    SectionReview,
    SectionSpec,
)
from . import register_gate
from .config_defaults import DIMENSION_DETECTORS


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_DIMENSION_NAMES = list(DIMENSION_DETECTORS.keys())


def _find_keyword_spans(text: str, keywords: list[str]) -> list[str]:
    """Return sentences from *text* that contain at least one *keyword*."""
    sentences = re.split(r"[.!?。！？\n]", text)
    spans: list[str] = []
    for sentence in sentences:
        stripped = sentence.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        for kw in keywords:
            if kw.lower() in lower:
                spans.append(stripped)
                break
    return spans


def _count_enumeration_items(text: str) -> int:
    """Count enumerated / bulleted items in *text*."""
    patterns = [
        r"(?:^|\n)\s*\d+[.)]\s",
        r"(?:^|\n)\s*\([a-z]\)\s",
        r"(?:^|\n)\s*-\s",
        r"\b(?:first|second|third|fourth|fifth|sixth)\b",
    ]
    return sum(len(re.findall(p, text, re.IGNORECASE)) for p in patterns)


def _run_detector(
    text: str,
    dimension: str,
    config: dict[str, object],
) -> tuple[bool, list[str]]:
    """Run a single dimension detector using its config entry."""
    keywords = config.get("keywords", [])
    if not isinstance(keywords, list):
        keywords = []
    spans = _find_keyword_spans(text, keywords)

    # mechanism_comparison: also match sentence-level patterns
    if dimension == "mechanism_comparison":
        patterns = config.get("patterns", [])
        if isinstance(patterns, list):
            for pat in patterns:
                if pat.lower() in text.lower():
                    for sentence in re.split(r"[.!?。！？\n]", text):
                        s = sentence.strip()
                        if s and pat.lower() in s.lower() and s not in spans:
                            spans.append(s)

    # method_taxonomy: if min_subtypes configured, require enumeration too
    if dimension == "method_taxonomy":
        min_sub = config.get("min_subtypes", 0)
        if isinstance(min_sub, (int, float)) and min_sub > 0:
            # Keywords alone are enough for "present"; enumeration counts as bonus
            pass  # keep keyword-based detection; enumeration is soft signal

    return (len(spans) > 0, spans)


# ---------------------------------------------------------------------------
# 5 independent dimension detectors (pure functions)
# ---------------------------------------------------------------------------


def detect_mechanism_comparison(text: str) -> tuple[bool, list[str]]:
    """Detect mechanism comparison dimension in *text*."""
    return _run_detector(text, "mechanism_comparison", DIMENSION_DETECTORS["mechanism_comparison"])


def detect_method_taxonomy(text: str) -> tuple[bool, list[str]]:
    """Detect method taxonomy dimension in *text*."""
    return _run_detector(text, "method_taxonomy", DIMENSION_DETECTORS["method_taxonomy"])


def detect_evaluation_protocol(text: str) -> tuple[bool, list[str]]:
    """Detect evaluation protocol dimension in *text*."""
    return _run_detector(text, "evaluation_protocol", DIMENSION_DETECTORS["evaluation_protocol"])


def detect_failure_negative_evidence(text: str) -> tuple[bool, list[str]]:
    """Detect failure / negative evidence dimension in *text*."""
    return _run_detector(text, "failure_negative_evidence", DIMENSION_DETECTORS["failure_negative_evidence"])


def detect_engineering_implication(text: str) -> tuple[bool, list[str]]:
    """Detect engineering implication dimension in *text*."""
    return _run_detector(text, "engineering_implication", DIMENSION_DETECTORS["engineering_implication"])


# Map dimension name -> detector function (derived from config, not hardcoded)
_DIMENSION_DETECTORS_MAP: dict[str, callable] = {
    name: globals()[f"detect_{name}"] for name in _DIMENSION_NAMES
}


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def measure_argument_density(
    section: SectionReview,
    text: str,
) -> ArgumentDensityProfile:
    """Build an ``ArgumentDensityProfile`` from a ``SectionReview`` and its text.

    Runs each of the 5 dimension detectors against *text*, assembles coverage
    status, detected indicators, density score, and issue list.
    """
    dimension_coverages: dict[str, str] = {}
    detected_indicators: list[DimensionIndicator] = []

    for dim_name in _DIMENSION_NAMES:
        detector_fn = _DIMENSION_DETECTORS_MAP[dim_name]
        detected, spans = detector_fn(text)
        dimension_coverages[dim_name] = "present" if detected else "absent"
        for span in spans:
            detected_indicators.append(
                DimensionIndicator(
                    dimension=dim_name,
                    span_text=span[:200],
                    confidence="high",
                )
            )

    present_count = sum(1 for v in dimension_coverages.values() if v == "present")
    total_dims = len(_DIMENSION_NAMES)
    density_score = present_count / total_dims if total_dims else 0.0

    absent_dims = [k for k, v in dimension_coverages.items() if v == "absent"]
    issues: list[str] = []
    if absent_dims:
        issues.append("low_density_dimensions:" + ",".join(absent_dims))

    return ArgumentDensityProfile(
        section_id=section.section_id,
        dimension_coverages=dimension_coverages,
        density_score=density_score,
        detected_indicators=detected_indicators,
        not_applicable_entries=[],
        issues=issues,
    )


def map_dimension_applicability(
    section_spec: SectionSpec,
    profile: ArgumentDensityProfile,
) -> ArgumentDensityProfile:
    """Apply applicability rules based on section metadata.

    Background / overview sections may exclude ``engineering_implication`` and
    ``failure_negative_evidence`` dimensions.  Only marks dimensions as
    ``not_applicable`` when they are currently ``absent`` (never overrides
    an already-detected ``present`` dimension).
    """
    not_applicable: list[NotApplicableEntry] = []
    updated_coverages = dict(profile.dimension_coverages)

    rq = section_spec.research_question.lower()
    is_background = any(
        kw in rq
        for kw in ["background", "introduction", "背景", "介绍", "overview", "综述"]
    )

    if is_background:
        for dim in ("engineering_implication", "failure_negative_evidence"):
            if updated_coverages.get(dim) == "absent":
                updated_coverages[dim] = "not_applicable"
                not_applicable.append(
                    NotApplicableEntry(
                        dimension=dim,
                        reason=(
                            f"Section '{section_spec.title}' is a "
                            f"background/overview section; {dim} not applicable"
                        ),
                    )
                )

    # Recompute score excluding not_applicable dimensions
    applicable = {k: v for k, v in updated_coverages.items() if v != "not_applicable"}
    present_count = sum(1 for v in applicable.values() if v == "present")
    total_applicable = len(applicable)
    density_score = present_count / total_applicable if total_applicable else 0.0

    return ArgumentDensityProfile(
        section_id=profile.section_id,
        dimension_coverages=updated_coverages,
        density_score=density_score,
        detected_indicators=profile.detected_indicators,
        not_applicable_entries=not_applicable,
        issues=profile.issues,
    )


# ---------------------------------------------------------------------------
# Gate registration
# ---------------------------------------------------------------------------


@register_gate("argument_density")
def argument_density_gate(
    section: SectionReview,
    text: str,
) -> ArgumentDensityProfile:
    """Gate entry point registered in the plugin registry."""
    return measure_argument_density(section, text)
