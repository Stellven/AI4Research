from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


OUTPUT_ROOT = Path(__file__).resolve().parent
STAGE3_ROOT = OUTPUT_ROOT.parent
REPO_ROOT = OUTPUT_ROOT.parents[3]
HARNESS_LIB = REPO_ROOT / "harness" / "lib"
COMPILER_PATH = HARNESS_LIB / "intent_gateway.py"
INPUT_ROOT = (
    REPO_ROOT
    / "harness"
    / "metadata"
    / "2-intent compiler output"
    / "requirement-compiler-input-fixtures"
)
CATALOG_PATH = INPUT_ROOT / "fixture_catalog.json"
TEMPLATE_PATHS = {
    "requirement_ir.json": STAGE3_ROOT / "requirement_ir" / "requirement_ir.json",
    "requirement_validation.json": STAGE3_ROOT / "requirement_validation" / "requirement_validation.json",
    "requirement_coverage.json": STAGE3_ROOT / "requirement_coverage" / "requirement_coverage.json",
}
EXPECTED_ARTIFACTS = set(TEMPLATE_PATHS)


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"Expected object JSON: {path}")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> str:
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)
    return hashlib.sha256(encoded).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_current_compiler():
    sys.path.insert(0, str(HARNESS_LIB))
    spec = importlib.util.spec_from_file_location("current_requirement_compiler_evaluation", COMPILER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load current compiler: {COMPILER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate_input_bundle(case: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    case_dir = INPUT_ROOT / case["bundle_path"]
    intent = load_json(case_dir / "intent_ir.json")
    validation = load_json(case_dir / "intent_validation.json")
    fidelity = load_json(case_dir / "intent_fidelity.json")
    intent_hash = sha256_file(case_dir / "intent_ir.json")
    expected_ref = {"intent_ir_id": intent["intent_ir_id"], "sha256": intent_hash}
    assert validation["intent_ir_ref"] == expected_ref
    assert fidelity["intent_ir_ref"] == expected_ref
    assert validation["status"] == "pass" and not validation["errors"]
    assert fidelity["status"] == "pass" and not fidelity["errors"]
    assert not any(item["blocking"] for item in intent["ambiguities"])
    return intent, validation, fidelity


def compatibility_adapter(
    case: dict[str, Any],
    intent: dict[str, Any],
    fidelity: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    prompt = case["prompt"]
    category = case["category"]
    lane = "research" if category in {"research", "internet_data", "experiment"} else "delivery"
    raw_intent = {
        "raw": {"text": prompt, "attachments": []},
        "source": {"channel": "synthetic_intent_fixture", "actor_ref": "fixture-catalog"},
        "context": {"repo": str(REPO_ROOT)},
        "routing_hints": {},
        "clarifications": {"answers": {}},
    }
    execution_authorized = fidelity["decisions"][0]["answer"] == "yes"
    rewritten = {
        "title": intent["goals"][0]["statement"][:90],
        "problem": prompt,
        "objective": " ".join(item["statement"] for item in intent["goals"]),
        "outcome": " ".join(item["description"] for item in intent["outcomes"]),
        "constraints": [item["statement"] for item in intent["constraints"]],
        "non_goals": (
            []
            if execution_authorized
            else ["Do not claim that domain experiment execution occurred."]
        ),
        "acceptance": [
            f"Preserve and satisfy IntentIR item {item_id}."
            for item_id in (
                [item["goal_id"] for item in intent["goals"]]
                + [item["outcome_id"] for item in intent["outcomes"]]
                + [item["constraint_id"] for item in intent["constraints"]]
            )
        ],
        "suggested_lane": lane,
        "suggested_logical_operators": ["RequirementCompiler", "Planner", "Verifier"],
    }
    return raw_intent, rewritten


def compare_output(
    case: dict[str, Any],
    output: dict[str, Any],
    output_sha256: str,
) -> dict[str, Any]:
    template = load_json(TEMPLATE_PATHS["requirement_ir.json"])
    actual_keys = set(output)
    expected_keys = set(template)
    actual_artifacts = {"requirement_ir.json"}
    missing_artifacts = sorted(EXPECTED_ARTIFACTS - actual_artifacts)
    extra_artifacts = sorted(actual_artifacts - EXPECTED_ARTIFACTS)
    missing_fields = sorted(expected_keys - actual_keys)
    extra_fields = sorted(actual_keys - expected_keys)
    schema_matches = output.get("schema_version") == template.get("schema_version")
    shape_matches = not missing_fields and not extra_fields
    routes_directly_to_planner = output.get("compiler_next") == "pm_planner_task_graph"

    reason_codes = []
    if missing_artifacts:
        reason_codes.extend(
            "MISSING_" + artifact.removesuffix(".json").upper()
            for artifact in missing_artifacts
        )
    if not schema_matches:
        reason_codes.append("REQUIREMENT_IR_SCHEMA_VERSION_MISMATCH")
    if not shape_matches:
        reason_codes.append("REQUIREMENT_IR_TEMPLATE_SHAPE_MISMATCH")
    reason_codes.append("CURRENT_COMPILER_HAS_NO_NATIVE_INTENT_BUNDLE_INTERFACE")
    if routes_directly_to_planner:
        reason_codes.append("BYPASSES_REQUIREMENT_VALIDATION_AND_COVERAGE_GATES")

    return {
        "schema_version": "solar.requirement_compiler_template_comparison.v1",
        "case_id": case["case_id"],
        "result": "PASS" if not reason_codes else "FAIL",
        "production_entrypoint": "harness/lib/intent_gateway.py::build_requirement_ir",
        "compatibility_adapter_used": True,
        "native_intent_bundle_interface": False,
        "input_intent_ir_id": case["intent_ir_id"],
        "output_sha256": output_sha256,
        "artifact_inventory": {
            "expected": sorted(EXPECTED_ARTIFACTS),
            "actual": sorted(actual_artifacts),
            "missing": missing_artifacts,
            "extra": extra_artifacts,
            "matches": not missing_artifacts and not extra_artifacts,
        },
        "requirement_ir": {
            "expected_schema_version": template.get("schema_version"),
            "actual_schema_version": output.get("schema_version"),
            "schema_version_matches": schema_matches,
            "expected_top_level_fields": sorted(expected_keys),
            "actual_top_level_fields": sorted(actual_keys),
            "missing_fields": missing_fields,
            "extra_fields": extra_fields,
            "template_shape_matches": shape_matches,
        },
        "handoff": {
            "expected_next_gate": "requirement_validation_and_coverage",
            "actual_compiler_next": output.get("compiler_next"),
            "routes_directly_to_planner": routes_directly_to_planner,
        },
        "reason_codes": sorted(set(reason_codes)),
    }


def main() -> None:
    compiler = load_current_compiler()
    catalog = load_json(CATALOG_PATH)
    templates = {name: load_json(path) for name, path in TEMPLATE_PATHS.items()}
    results = []

    for case in catalog["cases"]:
        intent, _validation, fidelity = validate_input_bundle(case)
        raw_intent, rewritten = compatibility_adapter(case, intent, fidelity)
        output = compiler.build_requirement_ir(intent["intent_ir_id"], raw_intent, rewritten)
        case_dir = OUTPUT_ROOT / case["case_id"]
        output_hash = write_json(case_dir / "requirement_ir.json", output)
        comparison = compare_output(case, output, output_hash)
        write_json(case_dir / "comparison.json", comparison)
        results.append(comparison)

    passed = sum(result["result"] == "PASS" for result in results)
    reason_counts: dict[str, int] = {}
    for result in results:
        for reason in result["reason_codes"]:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
    repo_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    summary = {
        "schema_version": "solar.requirement_compiler_fixture_evaluation.v1",
        "run_id": "current-v1-compiler-evaluation-20260825",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_head": repo_head,
        "source_fixture_catalog": str(CATALOG_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
        "production_entrypoint": "harness/lib/intent_gateway.py::build_requirement_ir",
        "compatibility_adapter_used": True,
        "native_intent_bundle_interface": False,
        "source_of_truth_templates": {
            name: {
                "path": str(TEMPLATE_PATHS[name].relative_to(REPO_ROOT)).replace("\\", "/"),
                "schema_version": payload.get("schema_version"),
                "sha256": sha256_file(TEMPLATE_PATHS[name]),
            }
            for name, payload in templates.items()
        },
        "case_count": len(results),
        "pass_count": passed,
        "fail_count": len(results) - passed,
        "overall_result": "PASS" if passed == len(results) else "FAIL",
        "reason_counts": dict(sorted(reason_counts.items())),
        "case_results": [
            {
                "case_id": result["case_id"],
                "result": result["result"],
                "comparison_path": f"{result['case_id']}/comparison.json",
                "output_path": f"{result['case_id']}/requirement_ir.json",
            }
            for result in results
        ],
    }
    write_json(OUTPUT_ROOT / "evaluation_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
