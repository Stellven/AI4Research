from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[3]
HARNESS_LIB = REPO / "harness" / "lib"
sys.path.insert(0, str(HARNESS_LIB))

from requirement_compiler import (  # noqa: E402
    RequirementCompilationError,
    compile_requirement_ir,
    evaluate_requirement_ir_format,
)


FIXTURE_ROOT = (
    REPO
    / "harness"
    / "metadata"
    / "2-intent compiler output"
    / "requirement-compiler-input-fixtures"
)
TEMPLATE_PATH = (
    REPO
    / "harness"
    / "metadata"
    / "3-requirements compiler output"
    / "requirement_ir"
    / "requirement_ir.json"
)
COMPILER_SCRIPT = REPO / "harness" / "lib" / "requirement_compiler" / "compiler.py"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_all_25_intent_ir_fixtures_compile_to_template_shape() -> None:
    catalog = _load(FIXTURE_ROOT / "fixture_catalog.json")
    template = _load(TEMPLATE_PATH)
    assert catalog["case_count"] == 25

    for case in catalog["cases"]:
        case_dir = FIXTURE_ROOT / case["bundle_path"]
        assert {path.name for path in case_dir.iterdir() if path.is_file()} == {"intent_ir.json"}
        intent_path = case_dir / "intent_ir.json"
        intent_bytes = intent_path.read_bytes()
        intent = json.loads(intent_bytes)
        digest = hashlib.sha256(intent_bytes).hexdigest()

        first = compile_requirement_ir(intent, intent_ir_sha256=digest)
        second = compile_requirement_ir(intent, intent_ir_sha256=digest)
        evaluation = evaluate_requirement_ir_format(
            first,
            intent_ir=intent,
            intent_ir_sha256=digest,
        )

        assert first == second, case["case_id"]
        assert set(first) == set(template), case["case_id"]
        assert first["intent_ir_ref"] == {
            "intent_ir_id": intent["intent_ir_id"],
            "sha256": digest,
        }
        assert first["intent_acceptance_ref"] == {
            "acceptance_id": f"intent-acceptance-{intent['raw_intent_ref']['raw_intent_id']}",
            "required_decision": "accepted",
        }
        assert first["requirements"]
        assert evaluation["status"] == "pass", (case["case_id"], evaluation["defects"])
        assert all(check["status"] == "pass" for check in evaluation["checks"])
        assert "compiler_next" not in first
        assert "planner_hints" not in first


def test_format_evaluator_rejects_legacy_requirement_shape() -> None:
    legacy = {
        "schema_version": "solar.requirement_ir.v1",
        "intent_id": "intent-legacy",
        "title": "Legacy",
        "objective": "Legacy objective",
    }

    result = evaluate_requirement_ir_format(legacy)

    assert result["status"] == "fail"
    assert any(defect["code"] == "MISSING_FIELDS" for defect in result["defects"])
    assert any(defect["code"] == "EXTRA_FIELDS" for defect in result["defects"])


def test_format_evaluator_treats_schema_version_as_nonempty_string() -> None:
    case = _load(FIXTURE_ROOT / "01-research-scientific-reproducibility" / "intent_ir.json")
    encoded = (FIXTURE_ROOT / "01-research-scientific-reproducibility" / "intent_ir.json").read_bytes()
    digest = hashlib.sha256(encoded).hexdigest()
    compiled = compile_requirement_ir(case, intent_ir_sha256=digest)
    compiled["schema_version"] = "temporary-version-label"

    result = evaluate_requirement_ir_format(compiled, intent_ir=case, intent_ir_sha256=digest)

    assert result["status"] == "pass"


def test_compiler_rejects_intent_without_goals() -> None:
    intent = _load(FIXTURE_ROOT / "01-research-scientific-reproducibility" / "intent_ir.json")
    invalid = copy.deepcopy(intent)
    invalid["goals"] = []

    with pytest.raises(RequirementCompilationError, match="at least one goal"):
        compile_requirement_ir(invalid, intent_ir_sha256="a" * 64)


def test_format_evaluator_rejects_wrong_acceptance_handoff() -> None:
    path = FIXTURE_ROOT / "01-research-scientific-reproducibility" / "intent_ir.json"
    intent = _load(path)
    compiled = compile_requirement_ir(intent, intent_ir_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    compiled["intent_acceptance_ref"]["acceptance_id"] = "intent-acceptance-wrong"

    result = evaluate_requirement_ir_format(compiled, intent_ir=intent)

    assert result["status"] == "fail"
    assert any(
        defect["code"] == "INTENT_ACCEPTANCE_REFERENCE_MISMATCH"
        for defect in result["defects"]
    )


def test_compiler_cli_reads_only_intent_ir_and_writes_requirement_ir(tmp_path: Path) -> None:
    input_path = FIXTURE_ROOT / "21-kid-sky-and-sunset-colors" / "intent_ir.json"
    output_path = tmp_path / "requirement_ir.json"

    proc = subprocess.run(
        [
            sys.executable,
            str(COMPILER_SCRIPT),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--json",
        ],
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )

    stdout_payload = json.loads(proc.stdout)
    file_payload = _load(output_path)
    assert stdout_payload == file_payload
    assert set(file_payload) == set(_load(TEMPLATE_PATH))
