"""RC9 installed intake must self-pin its active harness Python modules.

The real dashboard POST reached ``solar harness intake`` but product-mode
preflight rejected it because a normal installed ``solar-harness`` invocation
did not put ``$HARNESS_DIR/lib`` on ``PYTHONPATH``.  The live campaign scripts
had injected that variable themselves, which hid the fresh-install defect.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


_HARNESS = Path(__file__).resolve().parents[2]
_SCRIPT = _HARNESS / "solar-harness.sh"


def _resolved_pythonpath(initial: str) -> list[str]:
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(_HARNESS)
    env["PYTHONPATH"] = initial
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1" help >/dev/null; printf "%s" "$PYTHONPATH"',
            "bash",
            str(_SCRIPT),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.split(os.pathsep)


def test_installed_harness_pins_its_lib_before_foreign_pythonpath_entries(tmp_path: Path):
    foreign = tmp_path / "foreign-lib"
    entries = _resolved_pythonpath(str(foreign))

    assert entries[0] == str(_HARNESS / "lib"), entries
    assert str(foreign) in entries, "self-pinning must preserve caller Python paths"


def test_installed_harness_does_not_duplicate_an_already_leading_lib():
    active_lib = str(_HARNESS / "lib")
    entries = _resolved_pythonpath(active_lib)

    assert entries == [active_lib]
