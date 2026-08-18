from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


BRIDGE_PATH = Path(__file__).resolve().parents[1] / "bin" / "autosci_bridge.py"
sys.path.insert(0, str(BRIDGE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("autosci_bridge_execution_contract_test", BRIDGE_PATH)
assert SPEC and SPEC.loader
BRIDGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BRIDGE)


def _contract(path: Path) -> dict:
    return {
        "allowlist_evidence": [
            {
                "path": str(path),
                "artifact_path": str(path),
                "exists": True,
            }
        ]
    }


def test_strict_execution_argv_accepts_only_normalized_exact_tokens(tmp_path: Path) -> None:
    runner = tmp_path / "runner.py"
    dataset = tmp_path / "dataset.csv"
    result = tmp_path / "result.json"
    runner.write_text("print('ok')\n", encoding="utf-8")
    dataset.write_text("value\n1\n", encoding="utf-8")
    approved = [sys.executable, str(runner), str(dataset), str(result)]
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text(
        json.dumps(
            {
                "command_argvs": [approved],
                "executables": [Path(sys.executable).name],
                "allowed_prefixes": [" ".join(approved[:2])],
                "commands": ["{executable} {runner} {dataset} {result}"],
            }
        ),
        encoding="utf-8",
    )
    plan = {"command_argv": approved}

    ok, reason, normalized = BRIDGE._strict_execution_argv(approved, plan, _contract(allowlist))
    assert ok, reason
    assert normalized == BRIDGE._normalize_command(approved)

    for tampered in (
        ["different-python", *approved[1:]],
        [approved[0], str(runner) + ".other", *approved[2:]],
        [*approved, "--unauthorized-suffix"],
    ):
        accepted, _, _ = BRIDGE._strict_execution_argv(tampered, plan, _contract(allowlist))
        assert not accepted


def test_strict_execution_argv_rejects_prefix_template_and_executable_only_rules(tmp_path: Path) -> None:
    approved = [sys.executable, "runner.py", "dataset.csv", "result.json"]
    broad_allowlist = tmp_path / "broad-allowlist.json"
    broad_allowlist.write_text(
        json.dumps(
            {
                "executables": [Path(sys.executable).name],
                "allowed_prefixes": [f"{sys.executable} runner.py"],
                "commands": ["{executable} {runner} {dataset} {result}"],
            }
        ),
        encoding="utf-8",
    )
    accepted, reason, _ = BRIDGE._strict_execution_argv(
        approved,
        {"command_argv": approved},
        _contract(broad_allowlist),
    )
    assert not accepted
    assert "command_argvs" in reason
