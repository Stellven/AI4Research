"""`harness/lib` must outrank `harness/tools` for every shadowed module.

172 module names exist in both directories. For the refactored ones,
`tools/<name>.py` is a thin CLI wrapper whose own docstring says the
implementation lives in `harness/lib`; `graph_node_dispatcher` is 559,565 bytes
in lib and 1,306 in tools. When the wrapper wins the import, tests monkeypatch
module-level constants the wrapper does not define, and whole directories stop
collecting.

That happened, and nothing detected it as such. Reversing the order in
tests/conftest.py produces 250+ collection errors, which is loud but says
nothing about the cause, and a partial shadowing would not break collection at
all. These tests assert the property directly so a regression names itself.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HARNESS_LIB = REPO_ROOT / "harness" / "lib"
HARNESS_TOOLS = REPO_ROOT / "harness" / "tools"

# Shadowed names where the two files are drastically different sizes, so the
# wrong one winning is never merely cosmetic.
SHADOWED = ("graph_node_dispatcher", "graph_scheduler", "solar_skills", "operator_runtime")


def resolve_under_pytest(module: str, pythonpath: str | None) -> str:
    """Where pytest's import setup resolves `module`, as a real subprocess.

    A subprocess is the only honest way to ask: sys.path inside this process has
    already been arranged by the conftest under test.
    """
    probe = REPO_ROOT / "tests" / "harness" / "gate_ledger" / "_precedence_probe_test.py"
    probe.write_text(
        f"import {module} as m\n"
        f"def test_probe():\n"
        f"    print('RESOLVED=' + m.__file__)\n",
        encoding="utf-8",
    )
    env = dict(os.environ)
    if pythonpath is not None:
        env["PYTHONPATH"] = pythonpath
    else:
        env.pop("PYTHONPATH", None)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-s", "-p", "no:cacheprovider", str(probe)],
            cwd=REPO_ROOT, capture_output=True, text=True, env=env, check=False,
        )
    finally:
        probe.unlink(missing_ok=True)
    for line in result.stdout.splitlines():
        if line.startswith("RESOLVED="):
            return line.split("=", 1)[1]
    pytest.fail(f"probe did not report a resolution:\n{result.stdout}\n{result.stderr}")


@pytest.mark.parametrize("module", SHADOWED)
def test_lib_wins_over_tools(module):
    assert (HARNESS_LIB / f"{module}.py").is_file()
    assert (HARNESS_TOOLS / f"{module}.py").is_file(), "not a shadowed name any more"

    resolved = resolve_under_pytest(module, pythonpath=None)
    assert resolved == str(HARNESS_LIB / f"{module}.py"), resolved


def test_lib_still_wins_when_the_environment_puts_tools_first():
    """The guard that survives a hostile PYTHONPATH.

    Downstream conftests re-insert harness/lib behind `if value not in
    sys.path`, which is a no-op once it is present at any position. So when the
    environment has already supplied both directories in the wrong order, only
    removing and reinserting fixes it. `PYTHONPATH=harness/...` is set by this
    repository's own workflow, so this is a real configuration, not a
    hypothetical one.
    """
    hostile = f"{HARNESS_TOOLS}{os.pathsep}{HARNESS_LIB}"

    resolved = resolve_under_pytest("graph_node_dispatcher", pythonpath=hostile)
    assert resolved == str(HARNESS_LIB / "graph_node_dispatcher.py"), resolved


def test_the_wrapper_really_is_a_wrapper():
    """Anchors why the order matters, so the tests above cannot be "fixed" backwards.

    If tools/ ever becomes the implementation, this fails and someone has to
    revisit the precedence deliberately instead of flipping it to make a test
    pass.
    """
    wrapper = (HARNESS_TOOLS / "graph_node_dispatcher.py").read_text(encoding="utf-8")
    impl = HARNESS_LIB / "graph_node_dispatcher.py"

    assert "Compatibility wrapper" in wrapper
    assert impl.stat().st_size > 100 * len(wrapper)
