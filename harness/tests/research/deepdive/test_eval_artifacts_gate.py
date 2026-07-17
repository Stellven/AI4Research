"""Lane 4 — the contract's deterministic quality gate (`research eval-artifacts`)
discriminates a good native export from defective ones.

The RSI contract's D2/D3 stages gate on the engine's own `research eval-artifacts`
command. These fixtures are REAL engine exports (native_fixture_builder seeds the
DB and runs the engine's export path); the good one genuinely passes the gate, and
each defect is a genuine content flaw the gate catches. Exercised two ways: the
in-process `evaluate_artifacts()` (what the gate runs) and the literal
`research eval-artifacts` CLI (what the contract command invokes), so the exit-code
contract the dispatcher relies on is proven end to end.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_HARNESS = _HERE.parents[2]
_LIB = _HARNESS / "lib"
for p in (str(_HERE), str(_LIB)):
    if p not in sys.path:
        sys.path.insert(0, p)

from native_fixture_builder import RUN_ID, build_native_export  # noqa: E402
from research.evaluator import evaluate_artifacts  # noqa: E402

EVAL_JSON = f"{RUN_ID}-research_eval.json"


def _eval_json_path(export_dir: Path) -> Path:
    return export_dir / EVAL_JSON


def _run_cli(eval_json: Path) -> subprocess.CompletedProcess:
    env = {**__import__("os").environ, "HARNESS_DIR": str(_HARNESS), "PYTHONPATH": str(_LIB)}
    return subprocess.run(
        [sys.executable, "-m", "research.cli", "eval-artifacts", "--eval-json", str(eval_json)],
        text=True, capture_output=True, env=env,
    )


# ---------------------------------------------------------------------------
# GOOD: a real passing export.
# ---------------------------------------------------------------------------

def test_good_export_passes_evaluate_artifacts(tmp_path):
    export = build_native_export(tmp_path / "good")
    result = evaluate_artifacts(str(_eval_json_path(export)))
    assert result["ok"] is True, result["errors"]
    assert result["verdict"] == "PASS"
    m = result["metrics"]
    assert m["source_count"] >= 5 and m["claim_count"] >= 10 and m["section_count"] >= 1
    assert m["unsupported_rate"] == 0.0 and m["citation_accuracy"] == 1.0


def test_good_export_passes_the_research_cli_gate(tmp_path):
    export = build_native_export(tmp_path / "good")
    proc = _run_cli(_eval_json_path(export))
    assert proc.returncode == 0, proc.stderr + proc.stdout


# ---------------------------------------------------------------------------
# BAD: genuine content defects the real gate rejects.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "defect,expected_error_substr",
    [
        ("thin_section", "section_coverage_too_thin"),
        ("dangling_citation", "final_md_missing_cited_evidence"),
    ],
)
def test_defective_export_fails_evaluate_artifacts(tmp_path, defect, expected_error_substr):
    export = build_native_export(tmp_path / defect, defect=defect)
    result = evaluate_artifacts(str(_eval_json_path(export)))
    assert result["ok"] is False
    assert result["verdict"] == "FAIL"
    assert any(expected_error_substr in err for err in result["errors"]), result["errors"]


@pytest.mark.parametrize("defect", ["thin_section", "dangling_citation"])
def test_defective_export_fails_the_research_cli_gate(tmp_path, defect):
    export = build_native_export(tmp_path / defect, defect=defect)
    proc = _run_cli(_eval_json_path(export))
    assert proc.returncode != 0
