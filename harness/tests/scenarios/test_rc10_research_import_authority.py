"""The installed research implementation has one import authority.

Tool entrypoints run with ``harness/tools`` first on ``sys.path``.  A retired
copy of the ``research`` package there must forward to ``harness/lib/research``
instead of shadowing the product implementation.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


HARNESS = Path(__file__).resolve().parents[2]
LIB_RESEARCH = (HARNESS / "lib" / "research").resolve()
TOOLS = (HARNESS / "tools").resolve()


def test_tools_first_imports_resolve_research_modules_from_lib() -> None:
    code = """
import json
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
import research.cli
import research.evaluator
import research.survey.evaluator

print(json.dumps({
    "cli": str(Path(research.cli.__file__).resolve()),
    "evaluator": str(Path(research.evaluator.__file__).resolve()),
    "survey_evaluator": str(Path(research.survey.evaluator.__file__).resolve()),
}))
"""
    proc = subprocess.run(
        [sys.executable, "-I", "-c", code, str(TOOLS)],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    resolved = json.loads(proc.stdout)

    assert set(resolved) == {"cli", "evaluator", "survey_evaluator"}
    assert all(
        Path(path).resolve().is_relative_to(LIB_RESEARCH)
        for path in resolved.values()
    ), resolved


def test_retired_tools_cli_forwards_to_the_current_product_cli() -> None:
    proc = subprocess.run(
        [sys.executable, str(TOOLS / "research" / "cli.py"), "--help"],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )

    assert "compile-grounded" in proc.stdout
    assert "synthesize" in proc.stdout
