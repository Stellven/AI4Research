#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import skill_to_capsule_operator_productization_closeout as closeout  # noqa: E402


def test_write_artifacts_generates_expected_files(tmp_path):
    runtime_root = tmp_path / "runtime"
    (runtime_root / "sprints").mkdir(parents=True, exist_ok=True)
    verification = {
        "pytest_cmd": ["pytest", "-q"],
        "pytest_ok": True,
        "pytest_stdout": "19 passed",
        "pytest_stderr": "",
        "compile_cmd": ["python3", "solar_skills.py", "compile-to-capsule"],
        "compile_ok": True,
        "compile_stdout": "capsules=4",
        "compile_stderr": "",
    }
    paths = closeout._write_artifacts(runtime_root, verification)  # type: ignore[attr-defined]
    assert paths["s2_handoff"].exists()
    assert paths["s3_report"].exists()
    assert paths["s4_review"].exists()
    assert paths["s5_rollout"].exists()
    traceability = json.loads(paths["traceability"].read_text(encoding="utf-8"))
    assert traceability["requirements"]["REQ-000"] == ["S2", "S3", "S4", "S5"]
