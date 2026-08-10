"""Round-4 G7 — one shared sprints-dir resolution for Lane-3 evidence.

The route-record writer (operator_runtime), the dispatcher's ledger paths
(gnd.SPRINTS_DIR) and gate_ledger.default_sprints_dir() resolved the sprints
dir by three different rules; with HARNESS_DIR unset, route records could land
in the LIVE ~/.solar/harness/sprints while the gates read elsewhere (AC-R5.1
break + runtime pollution). All three must agree in every env combination that
names a harness location:

    HARNESS_SPRINTS_DIR > HARNESS_DIR > SOLAR_HARNESS_DIR > install default

(The dispatcher's nothing-set fallback stays the SOURCE TREE, not
~/.solar/harness — a dev checkout must never pollute the live runtime; that
combo is documented in lane3-spec-mismatches.md D11 and not exercised here.)

Resolution is read-only in a subprocess per combo — module constants are
computed at import time, so in-process reloads would lie.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_HARNESS = Path(__file__).resolve().parents[2]
_LIB = str(_HARNESS / "lib")

_SNIPPET = """
import json, sys
sys.path.insert(0, {lib!r})
import operator_runtime as opr
import graph_node_dispatcher as gnd
import gate_ledger as gl
print(json.dumps({{
    "route_writer": str(opr._route_sprints_dir()),
    "dispatcher": str(gnd.SPRINTS_DIR),
    "gate_ledger": str(gl.default_sprints_dir()),
}}))
"""


def _resolve(env_overrides: dict[str, str]) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items()
           if k not in {"HARNESS_DIR", "SOLAR_HARNESS_DIR", "HARNESS_SPRINTS_DIR"}}
    env.update(env_overrides)
    proc = subprocess.run(
        [sys.executable, "-c", _SNIPPET.format(lib=_LIB)],
        capture_output=True, text=True, env=env, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-800:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("combo,env,expected_tail", [
    ("harness_dir", {"HARNESS_DIR": "{box}"}, "sprints"),
    ("solar_harness_dir_only", {"SOLAR_HARNESS_DIR": "{box}"}, "sprints"),
    ("sprints_dir_wins_over_harness_dir",
     {"HARNESS_SPRINTS_DIR": "{box}/custom-sprints", "HARNESS_DIR": "{box}"},
     "custom-sprints"),
    ("sprints_dir_only", {"HARNESS_SPRINTS_DIR": "{box}/custom-sprints"},
     "custom-sprints"),
])
def test_all_three_resolvers_agree(tmp_path, combo, env, expected_tail):
    box = str(tmp_path)
    resolved = _resolve({k: v.format(box=box) for k, v in env.items()})
    values = set(resolved.values())
    assert len(values) == 1, f"{combo}: split-brain resolution {resolved}"
    only = values.pop()
    assert only.startswith(box), f"{combo}: resolved outside the sandbox: {only}"
    assert only.endswith(expected_tail)
    home_solar = str(Path.home() / ".solar")
    assert not only.startswith(home_solar), f"{combo}: resolved into the live runtime"
