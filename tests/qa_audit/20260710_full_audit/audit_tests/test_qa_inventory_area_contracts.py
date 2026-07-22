from __future__ import annotations

import csv
import os
from pathlib import Path

import pytest


AUDIT_ROOT_VALUE = os.environ.get("QA_AUDIT_ROOT")
if not AUDIT_ROOT_VALUE:
    pytest.skip(
        "requires QA_AUDIT_ROOT pointing to the archived full-audit run",
        allow_module_level=True,
    )

AUDIT_ROOT = Path(AUDIT_ROOT_VALUE).resolve()


def read_csv(name: str) -> list[dict[str, str]]:
    with (AUDIT_ROOT / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


FEATURES = read_csv("feature-results.csv")
ENTRYPOINTS = {row["feature_id"]: row for row in read_csv("feature-entrypoint-map.csv")}
EXISTING = {row["feature_id"]: row for row in read_csv("feature-existing-test-map.csv")}
CRITERIA = {row["feature_id"]: row for row in read_csv("pass-fail-criteria.csv")}

AREA_FEATURES = [
    row for row in FEATURES
    if row["feature_path"].startswith("QA inventory top-level area:")
]


@pytest.mark.parametrize("feature", AREA_FEATURES, ids=lambda row: row["feature_id"])
def test_qa_inventory_area_contract(feature: dict[str, str]) -> None:
    feature_id = feature["feature_id"]
    atomic = feature["atomic_feature"].lower()
    assert feature_id in ENTRYPOINTS
    assert feature_id in EXISTING
    assert feature_id in CRITERIA
    entry = ENTRYPOINTS[feature_id]
    existing = EXISTING[feature_id]
    criteria = CRITERIA[feature_id]

    if "tracked files/features" in atomic:
        assert entry["seeded_entrypoint_candidates"] or entry["discovered_entrypoints"] or entry["implementation_files_functions"]
        assert entry["mapping_basis"]
    elif "map to real tests" in atomic:
        has_test = bool(existing["existing_test_files"] or existing.get("eligible_phase_selected_targets", ""))
        has_gap = bool(existing["gap_to_confirm"] or existing.get("eligibility_reason", ""))
        assert has_test or has_gap
    elif "explicit criteria" in atomic:
        assert criteria["happy_path_pass_criteria"]
        assert criteria["negative_failure_pass_criteria"]
        assert criteria["fail_criteria"]
        allowed = set(criteria["allowed_result_classifications"].replace(";", " ").split())
        assert {"PASS", "FAIL"}.issubset(allowed)
        assert allowed & {"INCONCLUSIVE_EXPECTED", "SKIPPED_NA", "SKIPPED_ENV", "NOT_RUN"}
        assert criteria["expected_evidence"]
        assert "BLOCKED_EXPECTED" in criteria["gated_handling"] or "approval" in criteria["gated_handling"].lower()
    elif "coverage status is justified" in atomic:
        assert existing["coverage_status"] in {
            "direct", "indirect", "partial", "missing", "manual-only", "gated", "not-applicable"
        }
        if feature["final_result_status"] == "PASS":
            assert feature["execution_evidence"]
        assert existing["mapping_evidence"] or existing["gap_to_confirm"] or existing.get("eligibility_reason", "")
    else:
        raise AssertionError(f"Unhandled QA inventory atomic contract: {feature['atomic_feature']}")
