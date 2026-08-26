from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
EXPECTED_REASONS = {
    "BYPASSES_REQUIREMENT_VALIDATION_AND_COVERAGE_GATES",
    "CURRENT_COMPILER_HAS_NO_NATIVE_INTENT_BUNDLE_INTERFACE",
    "MISSING_REQUIREMENT_COVERAGE",
    "MISSING_REQUIREMENT_VALIDATION",
    "REQUIREMENT_IR_SCHEMA_VERSION_MISMATCH",
    "REQUIREMENT_IR_TEMPLATE_SHAPE_MISMATCH",
}


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"Expected object JSON: {path}")
    return payload


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    summary = load_json(ROOT / "evaluation_summary.json")
    assert summary["case_count"] == 25
    assert summary["pass_count"] == 0
    assert summary["fail_count"] == 25
    assert summary["overall_result"] == "FAIL"
    assert summary["compatibility_adapter_used"] is True
    assert summary["native_intent_bundle_interface"] is False
    assert set(summary["reason_counts"]) == EXPECTED_REASONS
    assert set(summary["reason_counts"].values()) == {25}

    case_ids = {row["case_id"] for row in summary["case_results"]}
    actual_dirs = {path.name for path in ROOT.iterdir() if path.is_dir()}
    assert len(case_ids) == 25
    assert actual_dirs == case_ids

    for row in summary["case_results"]:
        case_id = row["case_id"]
        case_dir = ROOT / case_id
        assert {path.name for path in case_dir.iterdir() if path.is_file()} == {
            "requirement_ir.json",
            "comparison.json",
        }
        output_path = case_dir / "requirement_ir.json"
        output = load_json(output_path)
        comparison = load_json(case_dir / "comparison.json")
        assert row["result"] == comparison["result"] == "FAIL", case_id
        assert output["schema_version"] == "solar.requirement_ir.v1", case_id
        assert output["compiler_next"] == "pm_planner_task_graph", case_id
        assert comparison["output_sha256"] == sha256_file(output_path), case_id
        assert comparison["reason_codes"] and set(comparison["reason_codes"]) == EXPECTED_REASONS, case_id
        assert comparison["artifact_inventory"]["actual"] == ["requirement_ir.json"], case_id
        assert set(comparison["artifact_inventory"]["missing"]) == {
            "requirement_coverage.json",
            "requirement_validation.json",
        }, case_id
        assert comparison["requirement_ir"]["expected_schema_version"] == "solar.requirement_ir.v2", case_id
        assert comparison["requirement_ir"]["schema_version_matches"] is False, case_id
        assert comparison["requirement_ir"]["template_shape_matches"] is False, case_id
        assert comparison["handoff"]["routes_directly_to_planner"] is True, case_id

    print(
        json.dumps(
            {
                "ok": True,
                "case_count": 25,
                "retained_output_artifacts": 25,
                "comparison_files": 25,
                "pass_count": 0,
                "fail_count": 25,
                "overall_result": "FAIL",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
