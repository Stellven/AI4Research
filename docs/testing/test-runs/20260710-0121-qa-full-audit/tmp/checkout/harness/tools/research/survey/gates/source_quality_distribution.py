"""Source quality distribution gate — O1 implementation.

Pure deterministic functions that analyse an ``EvidencePack`` and produce a
``SourceQualityDistribution``.  No external I/O, no LLM calls, no randomness.
"""

from __future__ import annotations

from collections import Counter
from urllib.parse import urlparse

from ..schemas import EvidencePack, SourceQualityDistribution, StuffingAlert
from . import register_gate
from .config_defaults import HIGH_AUTHORITY_TYPES, SOURCE_TAXONOMY


def _extract_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        return parsed.hostname or ""
    except Exception:
        return ""


def detect_stuffing_alerts(
    source_ids: list[str],
    source_urls: list[str],
    *,
    min_group_size: int = 3,
) -> list[StuffingAlert]:
    """Detect groups of same-domain sources that may indicate web stuffing.

    Parameters
    ----------
    source_ids, source_urls:
        Parallel lists (same length).  *source_urls* may contain empty strings
        for sources without a URL.
    min_group_size:
        Minimum number of same-domain sources to flag as stuffing.
    """
    domain_map: dict[str, list[str]] = {}
    for sid, url in zip(source_ids, source_urls):
        domain = _extract_domain(url)
        if not domain:
            continue
        domain_map.setdefault(domain, []).append(sid)

    alerts: list[StuffingAlert] = []
    for domain, sids in sorted(domain_map.items()):
        if len(sids) >= min_group_size:
            alerts.append(
                StuffingAlert(
                    domain=domain,
                    count=len(sids),
                    source_ids=sids,
                )
            )
    return alerts


def build_source_quality_distribution(
    evidence_pack: EvidencePack,
    *,
    source_urls: list[str] | None = None,
    stuffing_min_group: int = 3,
) -> SourceQualityDistribution:
    """Build a ``SourceQualityDistribution`` from an ``EvidencePack``.

    Parameters
    ----------
    evidence_pack:
        The frozen evidence pack for a section.
    source_urls:
        Parallel to ``evidence_pack.source_ids`` — used for stuffing detection.
        If *None*, stuffing detection is skipped (empty alerts).
    stuffing_min_group:
        Minimum same-domain group size to flag as stuffing.
    """
    source_types = evidence_pack.source_types
    total = len(source_types)

    # -- source_type_counts --
    type_counts: dict[str, int] = Counter(source_types)

    # -- canonical_coverage (high-authority types only) --
    canonical_coverage: dict[str, bool] = {
        t: (type_counts.get(t, 0) > 0) for t in HIGH_AUTHORITY_TYPES
    }

    # -- primary_ratio --
    if total == 0:
        primary_ratio = 0.0
    else:
        primary_count = sum(
            1 for t in source_types if t in HIGH_AUTHORITY_TYPES
        )
        primary_ratio = primary_count / total

    # -- stuffing_alerts --
    if source_urls is not None:
        stuffing_alerts = detect_stuffing_alerts(
            evidence_pack.source_ids,
            source_urls,
            min_group_size=stuffing_min_group,
        )
    else:
        stuffing_alerts = []

    # -- verdict + verdict_reasons --
    verdict = "pass"
    reasons: list[str] = []

    if total == 0:
        verdict = "fail"
        reasons.append("no_sources_found")
    else:
        if primary_ratio == 0.0:
            verdict = "fail"
            reasons.append("no_primary_sources")

        missing_canonical = [
            t for t, covered in canonical_coverage.items() if not covered
        ]
        if missing_canonical:
            if verdict == "pass":
                verdict = "warning"
            reasons.append(
                "missing_canonical_types:" + ",".join(missing_canonical)
            )

        if stuffing_alerts:
            if verdict == "pass":
                verdict = "warning"
            reasons.append(
                "stuffing_detected:" + ",".join(a.domain for a in stuffing_alerts)
            )

        unknown = set(source_types) - set(SOURCE_TAXONOMY) - {"other"}
        if unknown:
            if verdict == "pass":
                verdict = "warning"
            for ut in sorted(unknown):
                reasons.append(f"unknown_source_type:{ut}")

    return SourceQualityDistribution(
        section_id=evidence_pack.section_id,
        source_type_counts=dict(type_counts),
        primary_ratio=primary_ratio,
        stuffing_alerts=stuffing_alerts,
        canonical_coverage=canonical_coverage,
        verdict=verdict,
        verdict_reasons=reasons,
        taxonomy_version=",".join(SOURCE_TAXONOMY),
    )


@register_gate("source_quality")
def source_quality_gate(
    evidence_pack: EvidencePack,
    *,
    source_urls: list[str] | None = None,
    stuffing_min_group: int = 3,
) -> SourceQualityDistribution:
    """Gate entry point registered in the plugin registry."""
    return build_source_quality_distribution(
        evidence_pack,
        source_urls=source_urls,
        stuffing_min_group=stuffing_min_group,
    )
