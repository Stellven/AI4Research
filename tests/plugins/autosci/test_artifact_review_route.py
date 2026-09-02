from __future__ import annotations

import json
import hashlib
from pathlib import Path

from harness.plugins.autosci.backends import artifact_review


SCIENTIFIC_REPORT_ROUTE = "schema:schemas/evidence/scientific_report.v1.schema.json"


def _report_payload(report_id: str) -> dict:
    return {
        "schema": "scientific_report.v1",
        "task_id": "task-report",
        "sprint_id": "sprint-report",
        "node_id": "draft",
        "status": "completed",
        "inputs": {},
        "outputs": {
            "report": {
                "report_id": report_id,
                "title": "KV-cache efficiency landscape",
                "sections": [
                    {
                        "section_id": "findings",
                        "title": "Findings",
                        "body": "The report compares measured methods and cites its evidence.",
                        "evidence_ids": ["source-1"],
                    }
                ],
                "evidence_ids": ["source-1"],
                "unsupported_claims": [],
            }
        },
        "artifacts": [],
        "provenance": {
            "operator_id": "test-report-writer",
            "implementation_package": "tests",
            "timestamp": "2026-09-02T00:00:00Z",
        },
        "limitations": [],
    }


def test_artifact_review_resolves_exact_scientific_report_route(tmp_path: Path) -> None:
    report_path = tmp_path / "draft" / "scientific_report.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(json.dumps(_report_payload("report-1")), encoding="utf-8")
    legacy_target = tmp_path / "unrelated.md"
    legacy_target.write_text("# Wrong legacy target\n", encoding="utf-8")

    resolved = artifact_review._resolve_artifact(
        {
            "target": str(legacy_target),
            "artifact_routes": {SCIENTIFIC_REPORT_ROUTE: str(report_path.parent)},
        },
        tmp_path,
        tmp_path,
    )

    assert resolved["path"] == report_path.resolve()
    assert resolved["route_authority"] == "artifact_routes:scientific_report.v1"
    assert resolved["schema"] == "scientific_report.v1"
    assert resolved["sha256"] == hashlib.sha256(report_path.read_bytes()).hexdigest()
    assert '"report_id": "report-1"' in resolved["text"]
    assert str(legacy_target) not in resolved["checked_paths"]


def test_artifact_review_fails_closed_on_ambiguous_scientific_report_route(tmp_path: Path) -> None:
    route = tmp_path / "draft"
    route.mkdir()
    (route / "report-a.json").write_text(json.dumps(_report_payload("report-a")), encoding="utf-8")
    (route / "report-b.json").write_text(json.dumps(_report_payload("report-b")), encoding="utf-8")
    legacy_target = tmp_path / "legacy.md"
    legacy_target.write_text("# Legacy fallback must not be reviewed\n", encoding="utf-8")

    resolved = artifact_review._resolve_artifact(
        {
            "target": str(legacy_target),
            "artifact_routes": {SCIENTIFIC_REPORT_ROUTE: str(route)},
        },
        tmp_path,
        tmp_path,
    )

    assert resolved["path"] is None
    assert resolved["route_error"] == "scientific_report.v1 route contained multiple completed reports"
    assert str(legacy_target) not in resolved["checked_paths"]
