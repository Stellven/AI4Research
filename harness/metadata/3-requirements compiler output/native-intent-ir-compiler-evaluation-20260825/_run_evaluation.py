from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
STAGE3_ROOT = ROOT.parent
REPO_ROOT = ROOT.parents[3]
HARNESS_LIB = REPO_ROOT / "harness" / "lib"
sys.path.insert(0, str(HARNESS_LIB))

from requirement_compiler import compile_requirement_file, evaluate_requirement_ir_format  # noqa: E402


INPUT_ROOT = (
    REPO_ROOT
    / "harness"
    / "metadata"
    / "2-intent compiler output"
    / "requirement-compiler-input-fixtures"
)
CATALOG_PATH = INPUT_ROOT / "fixture_catalog.json"
TEMPLATE_PATH = STAGE3_ROOT / "requirement_ir" / "requirement_ir.json"


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


def main() -> None:
    catalog = load_json(CATALOG_PATH)
    case_results = []
    for case in catalog["cases"]:
        input_dir = INPUT_ROOT / case["bundle_path"]
        input_files = {path.name for path in input_dir.iterdir() if path.is_file()}
        if input_files != {"intent_ir.json"}:
            raise AssertionError((case["case_id"], input_files))
        input_path = input_dir / "intent_ir.json"
        output_dir = ROOT / case["case_id"]
        output_path = output_dir / "requirement_ir.json"
        intent_ir = load_json(input_path)
        intent_sha256 = sha256_file(input_path)
        requirement_ir = compile_requirement_file(input_path, output_path)
        evaluation = evaluate_requirement_ir_format(
            requirement_ir,
            intent_ir=intent_ir,
            intent_ir_sha256=intent_sha256,
            template_path=TEMPLATE_PATH,
        )
        write_json(output_dir / "format_evaluation.json", evaluation)
        case_results.append(
            {
                "case_id": case["case_id"],
                "result": "PASS" if evaluation["status"] == "pass" else "FAIL",
                "input_path": str(input_path.relative_to(REPO_ROOT)).replace("\\", "/"),
                "output_path": str(output_path.relative_to(REPO_ROOT)).replace("\\", "/"),
                "evaluation_path": str((output_dir / "format_evaluation.json").relative_to(REPO_ROOT)).replace("\\", "/"),
                "input_sha256": intent_sha256,
                "output_sha256": sha256_file(output_path),
                "requirement_count": len(requirement_ir["requirements"]),
                "defect_count": len(evaluation["defects"]),
            }
        )

    pass_count = sum(row["result"] == "PASS" for row in case_results)
    repo_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    summary = {
        "schema_version": "solar.native_requirement_compiler_evaluation.v1",
        "run_id": "native-intent-ir-compiler-evaluation-20260825",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_head": repo_head,
        "compiler": "harness/lib/requirement_compiler/compiler.py::compile_requirement_file",
        "evaluator": "harness/lib/requirement_compiler/evaluator.py::evaluate_requirement_ir_format",
        "source_fixture_catalog": str(CATALOG_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
        "template_path": str(TEMPLATE_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
        "template_sha256": sha256_file(TEMPLATE_PATH),
        "compiler_input_artifacts_per_case": ["intent_ir.json"],
        "compiler_output_artifacts_per_case": ["requirement_ir.json"],
        "case_count": len(case_results),
        "pass_count": pass_count,
        "fail_count": len(case_results) - pass_count,
        "overall_result": "PASS" if pass_count == len(case_results) else "FAIL",
        "case_results": case_results,
    }
    write_json(ROOT / "evaluation_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
