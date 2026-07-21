"""Deterministic validator for AI Influence YouTube report bundles."""

from __future__ import annotations

import re
from typing import Any

from .schema import ValidatorCheck, ValidatorReport


INTERNAL_TOKEN_RE = re.compile(r"\b(video_id|V\d{3}|raw_refs|pipeline_fields|transcript_status|processing_log)\b")
TRUNCATION_RE = re.compile(r"(明显没有写完|未完待续|\\bG$|\\.\\.\\.$)")


def validator_run(report_bundle: dict[str, Any]) -> ValidatorReport:
    report_md = str(report_bundle.get("report_md") or "")
    report_html = str(report_bundle.get("report_html") or "")
    evidence_map = report_bundle.get("evidence_map") or {}
    checks = [
        _check("1", "no_internal_tokens_md", not INTERNAL_TOKEN_RE.search(report_md), ["report_md"]),
        _check("2", "no_internal_tokens_html", not INTERNAL_TOKEN_RE.search(report_html), ["report_html"]),
        _check("3", "no_truncation_tail", not TRUNCATION_RE.search(report_md.strip()), ["report_md"]),
        _check("4", "inline_svg_present", "<svg" in report_html and "</svg>" in report_html, ["report_html"]),
        _check("5", "evidence_map_complete", bool(evidence_map.get("entries")), ["evidence_map"]),
        _check("6", "no_t3_core_evidence", not any(e.get("transcript_grade") == "T3" for e in evidence_map.get("entries", [])), ["evidence_map"]),
        _check("7", "source_mapping_reader_facing", all({"channel", "title", "published_at"} <= set(e) for e in evidence_map.get("entries", [])), ["evidence_map"]),
        _check("8", "hierarchy_or_citations_present", bool(report_bundle.get("plan_json") or report_bundle.get("inline_citations")), ["plan_json"]),
    ]
    overall = "PASS" if all(check.status == "PASS" for check in checks) else "FAIL"
    return ValidatorReport(run_id=str(report_bundle.get("run_id") or "unknown"), overall=overall, checks=checks)


def _check(check_id: str, name: str, ok: bool, evidence: list[str]) -> ValidatorCheck:
    return ValidatorCheck(id=check_id, name=name, status="PASS" if ok else "FAIL", evidence=evidence, diff="")
