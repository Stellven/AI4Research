"""Deterministic trend/chapter/subsection hierarchy builder."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def build_hierarchy(group_plan: dict[str, Any]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in group_plan.get("items", []):
        if item.get("transcript_grade") == "T3":
            continue
        groups[str(item.get("group_type") or "other")].append(item)

    trends = []
    for group_type, items in sorted(groups.items()):
        evidence_refs = [str(item["evidence_ref"]) for item in items if item.get("evidence_ref")]
        if not evidence_refs:
            continue
        trends.append({
            "trend_id": f"trend-{group_type}",
            "title": f"{group_type.replace('_', ' ').title()} Signals",
            "chapters": [
                {
                    "chapter_id": f"chapter-{group_type}-1",
                    "title": f"{group_type.replace('_', ' ').title()} 观察",
                    "subsections": [
                        {
                            "subsection_id": f"subsection-{group_type}-1",
                            "title": "核心证据",
                            "evidence_refs": evidence_refs,
                        }
                    ],
                }
            ],
        })
    return {"schema_version": "report_hierarchy.v1", "trends": trends}
