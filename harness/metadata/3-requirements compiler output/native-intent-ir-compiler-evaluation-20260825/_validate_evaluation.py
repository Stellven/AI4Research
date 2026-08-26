from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SUMMARY_PATH = ROOT / "evaluation_summary.json"
EXPECTED_CASE_FILES = {"requirement_ir.json", "format_evaluation.json"}
EXPECTED_TOP_LEVEL_KEYS = {
    "schema_version",
    "requirement_ir_id",
    "intent_ir_ref",
    "intent_acceptance_ref",
    "requirements",
    "scope",
    "assumptions",
    "conflict_scan",
    "approvals",
    "rollback",
}
LEGACY_KEYS = {"title", "problem", "objective", "pm_planner_task_graph"}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    summary = _load(SUMMARY_PATH)
    assert summary["overall_result"] == "PASS"
    assert summary["case_count"] == 25
    assert summary["pass_count"] == 25
    assert summary["fail_count"] == 0
    assert summary["compiler_input_artifacts_per_case"] == ["intent_ir.json"]
    assert summary["compiler_output_artifacts_per_case"] == ["requirement_ir.json"]

    cases = summary["case_results"]
    assert len(cases) == 25
    assert len({case["case_id"] for case in cases}) == 25

    for case in cases:
        case_dir = ROOT / case["case_id"]
        assert case_dir.is_dir()
        assert {path.name for path in case_dir.iterdir()} == EXPECTED_CASE_FILES

        requirement_path = case_dir / "requirement_ir.json"
        evaluation_path = case_dir / "format_evaluation.json"
        requirement = _load(requirement_path)
        evaluation = _load(evaluation_path)

        assert case["result"] == "PASS"
        assert case["defect_count"] == 0
        assert case["output_sha256"] == _sha256(requirement_path)
        assert set(requirement) == EXPECTED_TOP_LEVEL_KEYS
        assert not LEGACY_KEYS.intersection(requirement)
        assert isinstance(requirement["schema_version"], str)
        assert requirement["schema_version"]
        assert requirement["requirements"]

        assert evaluation["status"] == "pass"
        assert evaluation["defects"] == []
        assert evaluation["checks"]
        assert all(check["status"] == "pass" for check in evaluation["checks"])

    print(
        json.dumps(
            {
                "ok": True,
                "case_count": len(cases),
                "compiler_inputs_per_case": ["intent_ir.json"],
                "compiler_outputs_per_case": ["requirement_ir.json"],
                "format_evaluations_passed": len(cases),
                "legacy_shape_outputs": 0,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
