#!/usr/bin/env python3
"""B2 wave-1 import-resolution guard for operator_runtime.

The live tools entrypoints execute from harness/tools while PYTHONPATH may
already contain harness/lib. These checks pin the intended winner: imports from
pm_dispatch/operatord-style path setup must resolve operator_runtime from lib,
and the retired tools copy must stay a forwarding-compatible public surface.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path


HARNESS_DIR = Path(__file__).resolve().parents[2]
LIB_DIR = HARNESS_DIR / "lib"
TOOLS_DIR = HARNESS_DIR / "tools"


def _run_resolution_probe(entrypoint: str) -> dict[str, str]:
    code = textwrap.dedent(
        """
        import json
        import sys
        from pathlib import Path

        harness_dir = Path(sys.argv[1]).resolve()
        entrypoint = sys.argv[2]
        tools_dir = harness_dir / "tools"
        lib_dir = harness_dir / "lib"

        # Simulate direct script execution from harness/tools with inherited
        # PYTHONPATH=harness/lib already present but not winning precedence.
        rest = [p for p in sys.path if p not in {str(tools_dir), str(lib_dir)}]
        sys.path[:] = [str(tools_dir), str(lib_dir), *rest]

        if entrypoint == "pm_dispatch":
            pm_lib_dir = str(tools_dir.parent / "lib")
            if sys.path and sys.path[0] != pm_lib_dir:
                while pm_lib_dir in sys.path:
                    sys.path.remove(pm_lib_dir)
                sys.path.insert(0, pm_lib_dir)
        elif entrypoint == "operatord":
            op_lib_dir = str((tools_dir / "operatord.py").resolve().parent.parent / "lib")
            if sys.path and sys.path[0] != op_lib_dir:
                while op_lib_dir in sys.path:
                    sys.path.remove(op_lib_dir)
                sys.path.insert(0, op_lib_dir)
        else:
            raise SystemExit(f"unknown entrypoint: {entrypoint}")

        import operator_runtime  # noqa: E402

        print(json.dumps({
            "entrypoint": entrypoint,
            "file": str(Path(operator_runtime.__file__).resolve()),
            "sys_path_0": str(Path(sys.path[0]).resolve()),
        }))
        """
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(LIB_DIR)
    proc = subprocess.run(
        [sys.executable, "-c", code, str(HARNESS_DIR), entrypoint],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return json.loads(proc.stdout)


def test_pm_dispatch_context_resolves_operator_runtime_from_lib() -> None:
    result = _run_resolution_probe("pm_dispatch")

    assert result["sys_path_0"] == str(LIB_DIR.resolve())
    assert Path(result["file"]).parent == LIB_DIR.resolve(), result


def test_operatord_context_resolves_operator_runtime_from_lib() -> None:
    result = _run_resolution_probe("operatord")

    assert result["sys_path_0"] == str(LIB_DIR.resolve())
    assert Path(result["file"]).parent == LIB_DIR.resolve(), result


def _load_module_from_path(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(name, None)


def _public_names(module) -> set[str]:
    explicit_all = getattr(module, "__all__", None)
    if explicit_all is not None:
        return {str(name) for name in explicit_all}
    return {name for name in vars(module) if not name.startswith("_")}


def test_tools_operator_runtime_public_surface_matches_lib() -> None:
    tools_module = _load_module_from_path(
        "b2_tools_operator_runtime", TOOLS_DIR / "operator_runtime.py"
    )
    lib_module = _load_module_from_path(
        "b2_lib_operator_runtime", LIB_DIR / "operator_runtime.py"
    )

    assert _public_names(tools_module) == _public_names(lib_module)
