"""Convert AutoSci publication-like data to `publication_bundle.v1` evidence."""

from __future__ import annotations

from typing import Any

from .common import evidence_base


def convert(raw: dict[str, Any], envelope: dict[str, Any] | None = None) -> dict[str, Any]:
    source_report_id = str(raw.get("source_report_id") or "report-001")
    files = list(raw.get("files") or [])
    limitations = list(raw.get("limitations") or ["Fixture publication bundle; human approval required before external submission."])
    bundle = {
        "bundle_id": str(raw.get("bundle_id") or "bundle-001"),
        "publication_type": str(raw.get("publication_type") or "mixed"),
        "files": files,
        "source_report_id": source_report_id,
        "evidence_ids": list(raw.get("evidence_ids") or [source_report_id]),
    }
    return evidence_base(
        "publication_bundle.v1",
        envelope,
        {"bundle": bundle},
        artifacts=list(raw.get("artifacts") or files),
        status=str(raw.get("status") or "completed"),
        limitations=limitations,
    )
