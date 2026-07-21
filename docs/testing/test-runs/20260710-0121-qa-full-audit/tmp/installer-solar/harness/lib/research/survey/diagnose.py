"""Actionable survey quality diagnosis."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .evaluator import evaluate_survey
from .status_next import survey_status_next_action


ISSUE_GROUPS = {
    "completion": ("finalized_sections_low", "incomplete_sections", "pending_placeholder_count", "blocked_sections"),
    "length": ("final_char_count_low", "avg_section_chars_low", "final_heading_count_low"),
    "evidence": ("evidence_count_low", "claim_count_low", "claim_support_coverage_low", "evidence_source_coverage_low", "claim_tag_density_low", "evidence_tag_density_low", "depth_claim_tag_density_low", "depth_evidence_tag_density_low", "depth_literature_map_not_ok", "depth_controversy_matrix_not_ok"),
    "sources": ("source_type_count_low", "survey_missing_required_source_types", "low_value_source_ratio_high", "source_count_low"),
    "structure": ("chapter_count_low", "section_count_low", "taxonomy_depth_score_low", "ready_pack_ratio_low", "depth_chapter_structure_", "depth_academic_marker_", "depth_section_marker_", "depth_terminology_"),
    "review": ("section_p0_issue_count", "section_factual_accuracy_low", "section_grounding_accuracy_low", "chapter_", "chief_editor_"),
    "repetition": ("section_repetition_rate_high", "final_repetition_rate_high", "final_duplicate_sentence_", "chief_editor_section_duplicate_rate_high"),
}


def _group_issue(issue: str) -> str:
    for group, prefixes in ISSUE_GROUPS.items():
        if issue.startswith(prefixes):
            return group
    return "other"


def _next_action_for_group(group: str, root: Path, require_complete: bool) -> str:
    base = f"solar-harness research survey-continue --output-dir {root} --require-complete --json"
    if group in {"completion", "length", "structure"}:
        return base
    if group in {"evidence", "sources"}:
        return f"open {root / 'survey_source_gap_handoff.md'}; fill returned_sources.md; {base}"
    if group in {"review", "repetition"}:
        return f"solar-harness research survey-auto-repair --output-dir {root} --json"
    return base if require_complete else f"solar-harness research survey-eval --output-dir {root} --strict --json"


def _primary_next_action(root: Path, status_payload: dict[str, Any], issue_groups: list[dict[str, Any]], require_complete: bool) -> str:
    if require_complete and issue_groups:
        groups = {str(item.get("group") or "") for item in issue_groups}
        if groups & {"evidence", "sources"} and (root / "survey_source_gap_handoff.md").exists():
            return _next_action_for_group("evidence", root, require_complete)
        return _next_action_for_group("completion", root, require_complete)
    return str(status_payload.get("next_action") or _next_action_for_group("other", root, require_complete))


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Solar DeepResearch Survey Diagnosis",
        "",
        f"- Status: `{payload['status']}`",
        f"- Verdict: `{payload['verdict']}`",
        f"- Output dir: `{payload['output_dir']}`",
        f"- Next action: `{payload['next_action']}`",
        "",
        "## Summary",
        "",
    ]
    for key, value in payload["summary"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Issue Groups", ""])
    for group in payload["issue_groups"]:
        lines.append(f"### {group['group']}")
        lines.append("")
        lines.append(f"- count: `{group['count']}`")
        lines.append(f"- next_action: `{group['next_action']}`")
        for issue in group["issues"][:10]:
            lines.append(f"- issue: `{issue}`")
        lines.append("")
    if payload["top_section_issues"]:
        lines.extend(["## Top Section Issues", ""])
        for item in payload["top_section_issues"][:10]:
            lines.append(f"- `{item.get('section_id')}` risk={item.get('risk_score')} p0={item.get('p0_count')} p1={item.get('p1_count')}")
    return "\n".join(lines).rstrip() + "\n"


def diagnose_survey(
    output_dir: str | Path,
    *,
    strict: bool = True,
    min_finalized: int | None = None,
    require_complete: bool = True,
    write_md: bool = False,
) -> dict[str, Any]:
    root = Path(output_dir).expanduser()
    eval_payload = evaluate_survey(root, strict=strict, min_finalized=min_finalized, require_complete=require_complete)
    status_payload = survey_status_next_action(root, require_complete=require_complete)
    scorecard = eval_payload.get("scorecard") if isinstance(eval_payload.get("scorecard"), dict) else {}
    coverage = eval_payload.get("coverage") if isinstance(eval_payload.get("coverage"), dict) else {}
    final_quality = eval_payload.get("final_quality") if isinstance(eval_payload.get("final_quality"), dict) else {}
    issues = [str(item) for item in scorecard.get("issues", [])]
    grouped: dict[str, list[str]] = {}
    for issue in issues:
        grouped.setdefault(_group_issue(issue), []).append(issue)
    issue_groups = [
        {
            "group": group,
            "count": len(items),
            "issues": items,
            "next_action": _next_action_for_group(group, root, require_complete),
        }
        for group, items in sorted(grouped.items())
    ]
    section_scorecard = eval_payload.get("section_scorecard") if isinstance(eval_payload.get("section_scorecard"), dict) else {}
    top_section_issues = section_scorecard.get("top_issues") if isinstance(section_scorecard.get("top_issues"), list) else []
    payload: dict[str, Any] = {
        "ok": bool(eval_payload.get("ok")),
        "status": "pass" if eval_payload.get("ok") else "fail",
        "output_dir": str(root),
        "verdict": scorecard.get("verdict", "UNKNOWN"),
        "strict": strict,
        "require_complete": require_complete,
        "summary": {
            "chapters": scorecard.get("chapter_count", 0),
            "sections": scorecard.get("section_count", 0),
            "finalized_sections": scorecard.get("finalized_sections", 0),
            "sources": coverage.get("source_count", 0),
            "evidence": coverage.get("evidence_count", 0),
            "claims": coverage.get("claim_count", 0),
            "final_chars": final_quality.get("final_char_count", 0),
            "min_final_chars": final_quality.get("min_final_chars", 0),
            "issue_count": len(issues),
        },
        "issues": issues,
        "issue_groups": issue_groups,
        "top_section_issues": top_section_issues[:20],
        "next_action": _primary_next_action(root, status_payload, issue_groups, require_complete),
        "status_next": status_payload,
        "eval": eval_payload,
    }
    (root / "survey_diagnosis.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if write_md:
        md_path = root / "survey_diagnosis.md"
        md_path.write_text(_markdown(payload), encoding="utf-8")
        payload["markdown_path"] = str(md_path)
    return payload


def render_survey_diagnosis_markdown(payload: dict[str, Any]) -> str:
    return _markdown(payload)
