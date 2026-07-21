"""Build executable rewrite queues from survey section scorecards."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SEVERITY_ORDER = {"P0": 0, "P1": 1, "P2": 2}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _allowed_severity(issue: dict[str, Any], max_severity: str) -> bool:
    issue_level = SEVERITY_ORDER.get(str(issue.get("severity") or "P2"), 2)
    max_level = SEVERITY_ORDER.get(str(max_severity or "P1"), 1)
    return issue_level <= max_level


def build_rewrite_queue(
    output_dir: str | Path,
    *,
    max_severity: str = "P1",
    limit: int = 0,
    min_risk_score: int = 25,
) -> dict[str, Any]:
    root = Path(output_dir).expanduser()
    scorecard_path = root / "survey_section_scorecard.json"
    scorecard = _read_json(scorecard_path)
    rows = scorecard.get("top_issues")
    if not isinstance(rows, list):
        rows = scorecard.get("sections")
    if not isinstance(rows, list):
        rows = []
    items: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("status") == "pending":
            continue
        risk_score = int(row.get("risk_score") or 0)
        if risk_score < min_risk_score:
            continue
        issues = [
            issue for issue in row.get("issues", [])
            if isinstance(issue, dict) and _allowed_severity(issue, max_severity)
        ]
        if not issues:
            continue
        section_id = str(row.get("section_id") or "")
        if not section_id:
            continue
        section_dir = root / "sections" / section_id
        items.append({
            "queue_id": f"rewrite_{section_id.replace('/', '_')}",
            "section_id": section_id,
            "priority": issues[0].get("severity") or "P2",
            "risk_score": risk_score,
            "issues": issues,
            "section_spec": str(section_dir / "section.spec.json"),
            "evidence_pack": str(section_dir / "evidence_pack.json"),
            "current_final": str(section_dir / "final.md"),
            "target_response": str(section_dir / "human_responses" / "round_01.md"),
            "writer_backend": "human-packet",
            "action": "rewrite_section_from_scorecard",
        })
        if limit > 0 and len(items) >= limit:
            break
    seen_queue_ids = {str(item.get("queue_id") or "") for item in items}
    seen_section_ids = {str(item.get("section_id") or "") for item in items if str(item.get("section_id") or "")}
    chapter_review = _read_json(root / "survey_chapter_review.json")
    chapter_rows = chapter_review.get("chapters") if isinstance(chapter_review.get("chapters"), list) else []
    for row in chapter_rows:
        if not isinstance(row, dict):
            continue
        chapter_id = str(row.get("chapter_id") or "")
        issues = [
            issue for issue in row.get("issues", [])
            if isinstance(issue, dict) and _allowed_severity(issue, max_severity)
        ]
        if not chapter_id or not issues:
            continue
        section_ids = [str(item) for item in row.get("section_ids", []) if str(item)] if isinstance(row.get("section_ids"), list) else []
        actionable_sections = [
            section_id for section_id in section_ids
            if (root / "sections" / section_id / "final.md").exists()
        ] or section_ids[:1]
        for section_id in actionable_sections[:1]:
            if section_id in seen_section_ids:
                continue
            queue_id = f"rewrite_chapter_{chapter_id}_{section_id.replace('/', '_')}"
            if queue_id in seen_queue_ids:
                continue
            section_dir = root / "sections" / section_id
            items.append({
                "queue_id": queue_id,
                "chapter_id": chapter_id,
                "chapter_title": str(row.get("title") or ""),
                "section_id": section_id,
                "priority": issues[0].get("severity") or "P2",
                "risk_score": 100 if issues[0].get("severity") == "P0" else 25,
                "issues": issues,
                "section_spec": str(section_dir / "section.spec.json"),
                "evidence_pack": str(section_dir / "evidence_pack.json"),
                "current_final": str(section_dir / "final.md"),
                "target_response": str(section_dir / "human_responses" / "round_01.md"),
                "writer_backend": "human-packet",
                "action": "rewrite_section_from_chapter_review",
            })
            seen_queue_ids.add(queue_id)
            seen_section_ids.add(section_id)
            if limit > 0 and len(items) >= limit:
                break
        if limit > 0 and len(items) >= limit:
            break
    payload = {
        "ok": True,
        "queue_count": len(items),
        "max_severity": max_severity,
        "min_risk_score": min_risk_score,
        "items": items,
        "scorecard_path": str(scorecard_path),
        "queue_path": str(root / "survey_rewrite_queue.json"),
    }
    (root / "survey_rewrite_queue.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload
