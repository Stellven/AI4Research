"""workflow_router.py CLI contract — the exact seam the Lane 0 intake stub in
solar-harness.sh calls (`match --request` exit 0/1, any failure non-zero =>
legacy path). Subprocess tests with pinned env, real shipped contracts."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parents[2]
ROUTER = HARNESS_DIR / "lib" / "workflow_router.py"

RSI_PROMPT = "Give me a deep research report on Recursive Self-Improving Models in HTML format"


def _run(*args: str, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(HARNESS_DIR)
    env["PYTHONPATH"] = str(HARNESS_DIR / "lib")
    env.pop("SOLAR_DEMO_REPORT_MODE", None)
    env.update(extra_env or {})
    return subprocess.run(
        [sys.executable, str(ROUTER), *args],
        capture_output=True, text=True, env=env, timeout=60,
    )


def test_match_rsi_prompt_exit_0_prints_workflow_id():
    result = _run("match", "--request", RSI_PROMPT)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "research.deepdive.rsi_demo"


def test_match_generic_prompt_exit_1():
    result = _run("match", "--request", "please research the market for me")
    assert result.returncode == 1, (result.stdout, result.stderr)


def test_match_demo_mode_env_gate_does_not_route_unrelated_text_exit_1():
    """F6 (round-2): the demo env gate can no longer route arbitrary text — a
    marker-free prompt in demo mode is a no-match (exit 1), never a hijack."""
    result = _run("match", "--request", "hello", extra_env={"SOLAR_DEMO_REPORT_MODE": "1"})
    assert result.returncode == 1, (result.returncode, result.stdout)
    assert result.stdout.strip() == ""


def test_match_demo_mode_marker_prompt_still_routes_exit_0():
    """F6 must not break the demo driver: a marker-bearing prompt still routes
    (with demo mode on)."""
    result = _run("match", "--request", RSI_PROMPT, extra_env={"SOLAR_DEMO_REPORT_MODE": "1"})
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "research.deepdive.rsi_demo"


def test_match_all_contracts_broken_is_fail_safe_nomatch(tmp_path):
    """A registry whose ONLY contract is malformed resolves to no match (exit 1,
    stub falls back to the generic/legacy path) — never a spurious match. F12
    made the malformed file skipped-and-logged rather than fatal, so an
    all-broken dir is a clean no-match (1) instead of a load error (2)."""
    bad_dir = tmp_path / "workflows"
    bad_dir.mkdir()
    (bad_dir / "broken.workflow.json").write_text("{not json", encoding="utf-8")
    result = _run("match", "--request", RSI_PROMPT, "--workflows-dir", str(bad_dir))
    assert result.returncode == 1, (result.returncode, result.stdout)
    assert result.stdout.strip() == ""


def test_one_malformed_contract_does_not_break_routing_for_others(tmp_path):
    """F12 (round-2): a single poisoned contract file must NOT take down routing
    for every request. The router skips it (logged to stderr) and keeps matching
    the healthy contracts. Reviewer probe: RSI_PROMPT still routes with a broken
    sibling in the registry."""
    poisoned = tmp_path / "workflows"
    poisoned.mkdir()
    rsi_src = HARNESS_DIR / "config" / "workflows" / "research.deepdive.rsi_demo.workflow.json"
    (poisoned / "research.deepdive.rsi_demo.workflow.json").write_text(
        rsi_src.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (poisoned / "aaa-broken.workflow.json").write_text("{not json", encoding="utf-8")
    result = _run("match", "--request", RSI_PROMPT, "--workflows-dir", str(poisoned))
    assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
    assert result.stdout.strip() == "research.deepdive.rsi_demo"
    assert "aaa-broken.workflow.json" in result.stderr


def test_list_skips_malformed_contract(tmp_path):
    """`list` likewise skips the malformed file and shows the healthy one."""
    poisoned = tmp_path / "workflows"
    poisoned.mkdir()
    rsi_src = HARNESS_DIR / "config" / "workflows" / "research.deepdive.rsi_demo.workflow.json"
    (poisoned / "research.deepdive.rsi_demo.workflow.json").write_text(
        rsi_src.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (poisoned / "zzz-broken.workflow.json").write_text("{not json", encoding="utf-8")
    result = _run("list", "--workflows-dir", str(poisoned))
    assert result.returncode == 0
    ids = [line.split("\t")[0] for line in result.stdout.strip().splitlines()]
    assert ids == ["research.deepdive.rsi_demo"]


def test_list_shows_all_shipped_contracts():
    result = _run("list")
    assert result.returncode == 0
    ids = [line.split("\t")[0] for line in result.stdout.strip().splitlines()]
    assert ids == ["code.cli_smoke", "code.cli_smoke_anthropic", "pm.generic.v1", "research.deepdive.rsi_demo"]


def test_compile_subcommand_clean_on_all_shipped_contracts():
    for workflow_id in ("research.deepdive.rsi_demo", "code.cli_smoke", "code.cli_smoke_anthropic", "pm.generic.v1"):
        result = _run("compile", "--workflow-id", workflow_id)
        assert result.returncode == 0, (workflow_id, result.stdout, result.stderr)
        assert "compile clean" in result.stdout


def test_compile_subcommand_reports_errors_nonzero(tmp_path):
    contract = json.loads(
        (HARNESS_DIR / "config" / "workflows" / "research.deepdive.rsi_demo.workflow.json")
        .read_text(encoding="utf-8")
    )
    contract["stages"][1]["task_type"] = "audit_inventory"  # scout does not admit it
    bad_file = tmp_path / "bad.workflow.json"
    bad_file.write_text(json.dumps(contract), encoding="utf-8")
    result = _run("compile", "--contract-file", str(bad_file))
    assert result.returncode == 3
    payload = json.loads(result.stdout)
    assert any(e["code"] == "TASK_TYPE_NOT_ADMITTED" for e in payload["errors"])


def test_instantiate_subcommand_emits_deterministic_graph():
    args = (
        "instantiate", "--workflow-id", "research.deepdive.rsi_demo",
        "--input", "sid=golden-sid", "--input", "sprint_id=sprint-golden",
    )
    first, second = _run(*args), _run(*args)
    assert first.returncode == 0, first.stderr
    assert first.stdout == second.stdout
    graph = json.loads(first.stdout)
    assert graph["workflow_contract_id"] == "research.deepdive.rsi_demo"


def test_instantiate_planner_generated_contract_fails():
    result = _run("instantiate", "--workflow-id", "pm.generic.v1")
    assert result.returncode == 2
    assert "planner-generated" in result.stderr
