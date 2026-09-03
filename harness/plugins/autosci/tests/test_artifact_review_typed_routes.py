from __future__ import annotations

import json
import sys
from pathlib import Path

AUTOSCI_ROOT = Path(__file__).resolve().parents[1]
HARNESS_LIB = Path(__file__).resolve().parents[3] / "lib"
for root in (AUTOSCI_ROOT, HARNESS_LIB):
    if str(root) in sys.path:
        sys.path.remove(str(root))
    sys.path.insert(0, str(root))
for module_name in [name for name in sys.modules if name == "research" or name.startswith("research.")]:
    sys.modules.pop(module_name)

from harness.plugins.autosci.backends.artifact_review import _resolve_routed_review_target


def test_report_plan_route_is_a_valid_pre_draft_review_target(tmp_path):
    target = tmp_path / "scientific_report_plan.v1.json"
    target.write_text(
        json.dumps(
            {
                "schema": "scientific_report_plan.v1",
                "status": "completed",
                "outputs": {"report_plan": {"report_id": "report-1"}},
            }
        ),
        encoding="utf-8",
    )

    resolved = _resolve_routed_review_target(
        {
            "artifact_routes": {
                "schema:schemas/evidence/scientific_report_plan.v1.schema.json": str(target)
            }
        },
        tmp_path,
    )

    assert resolved is not None
    assert resolved["path"] == target.resolve()
    assert resolved["schema"] == "scientific_report_plan.v1"
    assert resolved["route_authority"] == "artifact_routes:scientific_report_plan.v1"


def test_multiple_typed_review_targets_fail_closed(tmp_path):
    report = tmp_path / "scientific_report.v1.json"
    report.write_text(
        json.dumps(
            {
                "schema": "scientific_report.v1",
                "status": "completed",
                "outputs": {"report": {"report_id": "report-1"}},
            }
        ),
        encoding="utf-8",
    )
    plan = tmp_path / "scientific_report_plan.v1.json"
    plan.write_text(
        json.dumps(
            {
                "schema": "scientific_report_plan.v1",
                "status": "completed",
                "outputs": {"report_plan": {"report_id": "report-1"}},
            }
        ),
        encoding="utf-8",
    )

    resolved = _resolve_routed_review_target(
        {
            "artifact_routes": {
                "schema:schemas/evidence/scientific_report.v1.schema.json": str(report),
                "schema:schemas/evidence/scientific_report_plan.v1.schema.json": str(plan),
            }
        },
        tmp_path,
    )

    assert resolved is not None
    assert resolved["path"] is None
    assert "multiple completed artifacts" in resolved["route_error"]
