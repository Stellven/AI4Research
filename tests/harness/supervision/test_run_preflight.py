"""Lane 0.5 — run preflight (design §1.6; R5 provider fail-closed, R7 capacity,
R2d contract compile, F-CLASS-21 path self-consistency).

P1.5 deterministic tests. Every external surface is either a tmp-dir fixture or
an injected parameter; no live pools, models, or network. The four mandated
fail-closed scenarios: auth absent, zero capacity, disabled-operator-only role,
HARNESS_DIR resolving to an installed ~/.solar tree instead of the worktree.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

import run_preflight as rp
import multi_task_runner
import operator_runtime
import operator_flow_control


SID = "sprint-20260706-preflight"
_HARNESS_DIR = Path(rp.__file__).resolve().parents[1]


def _write_operators(path: Path, operators: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "operators": operators}), encoding="utf-8")
    return path


def _op(role: str, provider: str, *, enabled: bool = True, backend: str | None = None) -> dict:
    return {
        "role": role,
        "provider": provider,
        "backend": backend or ("claude-cli" if provider == "anthropic" else "command"),
        "enabled": enabled,
        "available": True,
        "auth_mode": "subscription",
    }


FULL_SPINE = {
    "test-claude-planner": _op("planner", "anthropic"),
    "test-claude-builder": _op("builder", "anthropic"),
    "test-codex-builder": _op("builder", "openai"),
    "test-codex-evaluator": _op("evaluator", "openai"),
}


@pytest.fixture()
def ops_fixture(tmp_path, monkeypatch):
    """Point every registry reader at a tmp operators file; fake backend CLIs present."""

    def _install(operators: dict) -> Path:
        path = _write_operators(tmp_path / "config" / "physical-operators.json", operators)
        monkeypatch.setattr(multi_task_runner, "PHYSICAL_OPERATORS_PATH", path)
        monkeypatch.setattr(operator_runtime, "PHYSICAL_OPERATORS_PATH", path)
        monkeypatch.setattr(operator_flow_control, "PHYSICAL_OPERATORS_PATH", path)
        run_dir = tmp_path / "run"
        monkeypatch.setattr(operator_runtime, "OPERATOR_LEASE_DIR", run_dir / "operator-leases")
        monkeypatch.setattr(operator_runtime, "OPERATOR_STATUS_DIR", run_dir / "operator-status")
        monkeypatch.setattr(
            multi_task_runner,
            "_CLI_AVAILABLE_CACHE",
            {"claude": True, "codex": True, "gemini": True},
        )
        return path

    return _install


# --- Codex Landlock write capability -----------------------------------------


def _landlock_harness(tmp_path: Path) -> Path:
    harness = tmp_path / "harness"
    tools = harness / "tools"
    tools.mkdir(parents=True)
    (tools / "landlock_exec.py").write_text("# test wrapper\n", encoding="utf-8")
    return harness


def test_landlock_probe_skips_non_codex_runtime(tmp_path):
    result = rp.check_codex_landlock_write_scope(
        harness_dir=tmp_path,
        env={"SOLAR_PANE_RUNTIME": "claude"},
        platform_name="linux",
    )
    assert result["ok"] is True
    assert result["detail"]["skipped"] == "runtime_not_codex"


def test_landlock_probe_accepts_real_restricted_write(tmp_path, monkeypatch):
    harness = _landlock_harness(tmp_path)

    def _run(command, **_kwargs):
        Path(command[-1]).write_bytes(b"landlock-ok")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(rp.subprocess, "run", _run)
    result = rp.check_codex_landlock_write_scope(
        harness_dir=harness,
        env={"SOLAR_PANE_RUNTIME": "codex"},
        platform_name="linux",
    )
    assert result["ok"] is True
    assert result["detail"]["returncode"] == 0


def test_landlock_probe_rejects_filesystem_that_denies_granted_write(tmp_path, monkeypatch):
    harness = _landlock_harness(tmp_path)

    def _run(command, **_kwargs):
        return subprocess.CompletedProcess(command, 1, "", "Permission denied")

    monkeypatch.setattr(rp.subprocess, "run", _run)
    result = rp.check_codex_landlock_write_scope(
        harness_dir=harness,
        env={"SOLAR_PANE_RUNTIME": "codex"},
        platform_name="linux",
    )
    assert result["ok"] is False
    assert "Permission denied" in result["detail"]["error_tail"]
    assert "/mnt/c" in result["remediation"]


# --- auth presence (existence only — never token contents) --------------------


def test_auth_absent_fails_closed(tmp_path):
    result = rp.check_auth_presence(("anthropic", "openai"), home=tmp_path, env={})
    assert result["ok"] is False
    assert result["remediation"]
    providers = result["detail"]["providers"]
    assert providers["anthropic"]["present"] is False
    assert providers["openai"]["present"] is False


def test_auth_presence_is_stat_only(tmp_path):
    cred = tmp_path / ".claude" / ".credentials.json"
    cred.parent.mkdir(parents=True)
    cred.write_text('{"token": "must-never-be-read"}')
    cred.chmod(0)  # unreadable: presence must still be detectable via stat alone
    try:
        result = rp.check_auth_presence(("anthropic",), home=tmp_path, env={})
    finally:
        cred.chmod(stat.S_IRUSR | stat.S_IWUSR)
    assert result["ok"] is True
    assert result["detail"]["providers"]["anthropic"]["present"] is True
    assert "must-never-be-read" not in json.dumps(result)


def test_auth_env_token_counts_but_never_leaks(tmp_path):
    secret = "sekret-oauth-token-xyz"
    result = rp.check_auth_presence(
        ("anthropic",), home=tmp_path, env={"CLAUDE_CODE_OAUTH_TOKEN": secret}
    )
    assert result["ok"] is True
    assert secret not in json.dumps(result)


def test_auth_empty_file_is_absent(tmp_path):
    auth = tmp_path / ".codex" / "auth.json"
    auth.parent.mkdir(parents=True)
    auth.write_text("")  # zero bytes == unauthenticated (matches auth-helpers -s)
    result = rp.check_auth_presence(("openai",), home=tmp_path, env={})
    assert result["ok"] is False


def test_auth_single_provider_policy_fails_closed(tmp_path):
    # multi-provider policy: one authed provider is enough
    cred = tmp_path / ".claude" / ".credentials.json"
    cred.parent.mkdir(parents=True)
    cred.write_text("x")
    multi = rp.check_auth_presence(("anthropic", "openai"), home=tmp_path, env={})
    assert multi["ok"] is True
    # single-provider policy is a product contract: that provider must be authed
    single = rp.check_auth_presence(("openai",), home=tmp_path, env={})
    assert single["ok"] is False


# --- live capacity ------------------------------------------------------------


def test_zero_capacity_fails_closed():
    result = rp.check_live_capacity(session_alive=False, tmux_available=False)
    assert result["ok"] is False
    assert result["remediation"]


def test_capacity_pool_up():
    result = rp.check_live_capacity(session_alive=True, tmux_available=False)
    assert result["ok"] is True
    assert result["detail"]["mode"] == "pool_up"


def test_capacity_auto_startable():
    result = rp.check_live_capacity(session_alive=False, tmux_available=True)
    assert result["ok"] is True
    assert result["detail"]["mode"] == "auto_startable"


# --- per-role route resolution under provider policy ---------------------------


def test_role_routes_resolve_on_full_spine(ops_fixture):
    ops_fixture(FULL_SPINE)
    result = rp.check_role_routes(providers=("anthropic", "openai"))
    assert result["ok"] is True
    routes = result["detail"]["roles"]
    assert routes["planner"]["candidates"]
    assert routes["builder"]["candidates"]
    assert routes["evaluator"]["candidates"]


def test_disabled_operator_only_role_fails_closed(ops_fixture):
    ops = dict(FULL_SPINE)
    ops["test-claude-planner"] = _op("planner", "anthropic", enabled=False)
    ops_fixture(ops)
    result = rp.check_role_routes(providers=("anthropic", "openai"))
    assert result["ok"] is False
    assert result["detail"]["roles"]["planner"]["candidates"] == []
    assert "planner" in (result["remediation"] or "")


def test_provider_policy_excludes_off_policy_operator(ops_fixture):
    ops = dict(FULL_SPINE)
    ops.pop("test-claude-builder")
    ops.pop("test-codex-builder")
    ops["test-gemini-builder"] = _op("builder", "google", backend="gemini-cli")
    ops_fixture(ops)

    policy = rp.check_role_routes(providers=("anthropic", "openai"))
    assert policy["ok"] is False, "R5: provider policy must be fail-closed per role"

    no_policy = rp.check_role_routes(providers=())
    assert no_policy["ok"] is True, "empty policy disables the provider wall"


def test_role_route_uses_runtime_state_classifier(ops_fixture, monkeypatch):
    ops_fixture(FULL_SPINE)
    # the single classifier says the only evaluator is auth_expired -> role fails
    real = operator_runtime.get_operator_runtime_state

    def fake_state(operator_id: str) -> str:
        if operator_id == "test-codex-evaluator":
            return "auth_expired"
        return real(operator_id)

    monkeypatch.setattr(operator_runtime, "get_operator_runtime_state", fake_state)
    result = rp.check_role_routes(providers=("anthropic", "openai"))
    assert result["ok"] is False
    excluded = result["detail"]["roles"]["evaluator"]["excluded"]
    assert any("auth_expired" in e["why"] for e in excluded)


def test_busy_operator_still_routes(ops_fixture, monkeypatch):
    """leased/running means busy, not broken (F-CLASS-08 distinction)."""
    ops_fixture(FULL_SPINE)
    monkeypatch.setattr(operator_runtime, "get_operator_runtime_state", lambda oid: "leased")
    result = rp.check_role_routes(providers=("anthropic", "openai"))
    assert result["ok"] is True


# --- harness path self-consistency (cb2cc504 / F-CLASS-21) ---------------------


def _consistent_env(worktree: Path) -> dict:
    return {
        "HARNESS_DIR": str(worktree),
        "PYTHONPATH": str(worktree / "lib"),
    }


def test_path_consistency_green(tmp_path):
    worktree = tmp_path / "checkout" / "harness"
    (worktree / "lib").mkdir(parents=True)
    result = rp.check_harness_path_consistency(
        expected_harness_dir=worktree,
        env=_consistent_env(worktree),
        solar_harness_path=None,
        modules={},
    )
    assert result["ok"] is True


def test_path_resolving_to_installed_solar_fails_closed(tmp_path):
    worktree = tmp_path / "checkout" / "harness"
    (worktree / "lib").mkdir(parents=True)
    installed = tmp_path / "home" / ".solar" / "harness"
    (installed / "lib").mkdir(parents=True)
    env = {"HARNESS_DIR": str(installed), "PYTHONPATH": str(worktree / "lib")}
    result = rp.check_harness_path_consistency(
        expected_harness_dir=worktree, env=env, solar_harness_path=None, modules={}
    )
    assert result["ok"] is False
    assert "HARNESS_DIR" in (result["remediation"] or "")


def test_path_unset_harness_dir_fails_closed(tmp_path):
    worktree = tmp_path / "checkout" / "harness"
    (worktree / "lib").mkdir(parents=True)
    result = rp.check_harness_path_consistency(
        expected_harness_dir=worktree,
        env={"PYTHONPATH": str(worktree / "lib")},
        solar_harness_path=None,
        modules={},
    )
    assert result["ok"] is False


def test_path_foreign_pythonpath_fails_closed(tmp_path):
    worktree = tmp_path / "checkout" / "harness"
    (worktree / "lib").mkdir(parents=True)
    other = tmp_path / "other" / "harness"
    (other / "lib").mkdir(parents=True)
    env = {"HARNESS_DIR": str(worktree), "PYTHONPATH": str(other / "lib")}
    result = rp.check_harness_path_consistency(
        expected_harness_dir=worktree, env=env, solar_harness_path=None, modules={}
    )
    assert result["ok"] is False


def test_path_foreign_solar_harness_on_path_fails_closed(tmp_path):
    worktree = tmp_path / "checkout" / "harness"
    (worktree / "lib").mkdir(parents=True)
    foreign = tmp_path / "home" / ".solar" / "bin" / "solar-harness"
    foreign.parent.mkdir(parents=True)
    foreign.write_text("#!/bin/sh\n")
    result = rp.check_harness_path_consistency(
        expected_harness_dir=worktree,
        env=_consistent_env(worktree),
        solar_harness_path=str(foreign),
        modules={},
    )
    assert result["ok"] is False


# --- contract compile (fail-closed while the Lane 1 module is absent) ----------


def test_not_contracted_is_skipped_ok(tmp_path):
    result = rp.check_contract_compiles(None)
    assert result["ok"] is True
    assert result["detail"]["skipped"] == "not_contracted"


def test_contracted_without_compiler_fails_closed(tmp_path):
    contract = tmp_path / "demo.workflow.json"
    contract.write_text("{}")
    result = rp.check_contract_compiles(contract)
    # workflow_contract is Lane 1's module and is absent on this branch:
    # a contracted run must fail closed, never silently skip the compile.
    assert result["ok"] is False
    assert result["remediation"]


def test_contract_file_missing_fails_closed(tmp_path):
    result = rp.check_contract_compiles(tmp_path / "nope.workflow.json")
    assert result["ok"] is False


def _fake_lane1_module(monkeypatch, compile_result=None, load_raises=None):
    """Mimic the real Lane 1 API (contract/lane1-compiler):
    load_contract(path) raising on schema errors, plus
    compile_checks(contract, capsule_registry, operator_registry) -> error list."""
    import types

    fake = types.ModuleType("workflow_contract")
    calls: dict = {}

    def load_contract(path):
        if load_raises is not None:
            raise load_raises
        calls["loaded"] = str(path)
        return {"workflow_id": "demo", "_source_path": str(path)}

    def compile_checks(contract, capsule_registry, operator_registry, provider_policy=None):
        calls["compiled"] = contract
        calls["provider_policy"] = provider_policy
        return list(compile_result or [])

    fake.load_contract = load_contract
    fake.compile_checks = compile_checks
    fake.load_capsule_registry = lambda: {}
    fake.load_operator_registry = lambda: {}
    monkeypatch.setitem(sys.modules, "workflow_contract", fake)
    return calls


def test_contract_compiles_via_lane1_api(tmp_path, monkeypatch):
    contract = tmp_path / "demo.workflow.json"
    contract.write_text("{}")
    calls = _fake_lane1_module(monkeypatch)
    result = rp.check_contract_compiles(contract)
    assert result["ok"] is True
    assert "compiled" in calls, "must run the real load_contract+compile_checks path"


def test_contract_compile_errors_fail_closed(tmp_path, monkeypatch):
    contract = tmp_path / "demo.workflow.json"
    contract.write_text("{}")
    _fake_lane1_module(
        monkeypatch,
        compile_result=[
            {"code": "OBLIGATION_UNSATISFIABLE_FOR_NODE_KIND", "stage_id": "S3"}
        ],
    )
    result = rp.check_contract_compiles(contract)
    assert result["ok"] is False
    assert "OBLIGATION_UNSATISFIABLE_FOR_NODE_KIND" in json.dumps(result["detail"])


def test_contract_schema_error_fails_closed(tmp_path, monkeypatch):
    contract = tmp_path / "demo.workflow.json"
    contract.write_text("{}")
    _fake_lane1_module(monkeypatch, load_raises=ValueError("bad schema"))
    result = rp.check_contract_compiles(contract)
    assert result["ok"] is False
    assert "bad schema" in json.dumps(result["detail"])


# --- F13: preflight compiles against the RUN policy, not the embedded one ------


def test_check_contract_compiles_threads_run_policy_to_compiler(tmp_path, monkeypatch):
    """F13: the RUN provider policy — not the contract's embedded provider_policy —
    must reach the Lane 1 compiler, so preflight's contract gate judges the stage
    under the same policy the run will execute under. Shaped as the compiler's
    ``{"allowed_providers": [...]}`` policy object."""
    contract = tmp_path / "demo.workflow.json"
    contract.write_text("{}")
    calls = _fake_lane1_module(monkeypatch)
    result = rp.check_contract_compiles(contract, provider_policy=("Anthropic", "openai"))
    assert result["ok"] is True
    assert calls["provider_policy"] == {"allowed_providers": ["anthropic", "openai"]}, (
        "check_contract_compiles must pass the RUN policy (normalized) into compile_checks"
    )


def test_check_contract_compiles_empty_policy_falls_back_to_embedded(tmp_path, monkeypatch):
    """An absent/empty run policy imposes no wall: the compiler falls back to the
    contract's own embedded policy (backward-compatible pre-F13 behavior), never a
    fabricated empty allow-list."""
    contract = tmp_path / "demo.workflow.json"
    contract.write_text("{}")
    calls = _fake_lane1_module(monkeypatch)
    rp.check_contract_compiles(contract, provider_policy=())
    assert calls["provider_policy"] is None
    rp.check_contract_compiles(contract)  # default arg: also no override
    assert calls["provider_policy"] is None


def test_run_preflight_threads_run_policy_into_contract_compile(tmp_path, ops_fixture, monkeypatch):
    """End-to-end wiring: run_preflight feeds its resolved provider policy to the
    contract compile check, not the contract's embedded policy (F13 call site)."""
    ops_fixture(FULL_SPINE)
    contract = tmp_path / "demo.workflow.json"
    contract.write_text("{}")
    calls = _fake_lane1_module(monkeypatch)
    worktree = tmp_path / "checkout" / "harness"
    (worktree / "lib").mkdir(parents=True)
    home = tmp_path / "home"
    home.mkdir()
    env = dict(_consistent_env(worktree))

    rp.run_preflight(
        SID,
        providers=("anthropic",),
        contract_path=contract,
        expected_harness_dir=worktree,
        home=home,
        env=env,
        session_alive=True,
        solar_harness_path=None,
        modules={},
        write=False,
    )
    assert calls["provider_policy"] == {"allowed_providers": ["anthropic"]}


def test_preflight_and_compiler_agree_on_openai_stage_under_anthropic_policy():
    """F13 disagreement regression (preflight vs. the real Lane 1 compiler must
    agree on the same stage): an openai-only contract compiles clean under its
    embedded openai policy, but under an anthropic-only RUN policy every openai
    stage is unroutable — the compiler must reject it, and preflight, fed the same
    run policy, must fail closed on the same stage.

    xfail-until-Lane-1-F1-merges: while the empty stage∩policy intersection
    short-circuits the provider filter (workflow_contract.py:406-428, disposition
    F1), the compiler still resolves an openai stage under an anthropic-only
    policy, so this rejection is not yet in force. Detected at runtime so the test
    self-heals into a real green regression once F1 lands — nothing to unmark.

    Skips on the standalone Lane 0.5 branch, where neither the Lane 1
    ``workflow_contract`` module nor the shipped contracts are present; it becomes
    live on the integrated tree.
    """
    wc = pytest.importorskip("workflow_contract")
    rsi = _HARNESS_DIR / "config" / "workflows" / "research.deepdive.rsi_demo.workflow.json"
    if not rsi.is_file():
        pytest.skip("shipped RSI contract absent on this tree (pre-integration)")

    capsules = wc.load_capsule_registry()
    operators = wc.load_operator_registry()
    contract = wc.load_contract(str(rsi))

    # Baseline: the openai contract compiles clean under its embedded openai policy.
    if wc.compile_checks(contract, capsules, operators):
        pytest.skip("RSI baseline does not compile clean under embedded policy on this tree")

    run_policy = {"allowed_providers": ["anthropic"]}

    # xfail-until-F1: the empty-intersection short-circuit still resolves the route.
    if wc.resolve_role_operators("builder", ["openai"], operators, run_policy):
        pytest.xfail(
            "Lane 1 F1 not merged: empty stage∩policy intersection short-circuits "
            "the provider filter (workflow_contract.py:406-428), so an openai stage "
            "still resolves under an anthropic-only run policy"
        )

    # F1 has landed -> the compiler rejects the openai stages under the run policy...
    compiler_errors = wc.compile_checks(contract, capsules, operators, provider_policy=run_policy)
    compiler_route_stages = {
        e.get("stage_id")
        for e in compiler_errors
        if e.get("code") == wc.ERROR_ROUTE_UNRESOLVABLE
    }
    assert compiler_route_stages, "compiler must reject openai stages under anthropic-only run policy"

    # ...and preflight, fed the SAME run policy, must agree on the same stage(s).
    result = rp.check_contract_compiles(rsi, provider_policy=("anthropic",))
    assert result["ok"] is False
    preflight_route_stages = {
        e.get("stage_id")
        for e in result["detail"].get("errors", [])
        if e.get("code") == wc.ERROR_ROUTE_UNRESOLVABLE
    }
    assert compiler_route_stages & preflight_route_stages, (
        "preflight and the compiler must fail closed on the same openai stage under the run policy"
    )


# --- full run: fail-closed report written to sprints/<sid>.preflight.json ------


def test_run_preflight_writes_fail_closed_report(tmp_path, ops_fixture, monkeypatch):
    ops_fixture(FULL_SPINE)
    worktree = tmp_path / "checkout" / "harness"
    (worktree / "lib").mkdir(parents=True)
    sprints = tmp_path / "sprints"
    home = tmp_path / "home"  # no auth files -> auth check fails
    home.mkdir()
    env = dict(_consistent_env(worktree))
    env["SPRINTS_DIR"] = str(sprints)

    report = rp.run_preflight(
        SID,
        providers=("anthropic", "openai"),
        expected_harness_dir=worktree,
        home=home,
        env=env,
        session_alive=False,
        tmux_available=False,
        solar_harness_path=None,
        modules={},
    )

    assert report["ok"] is False
    assert "auth_presence" in report["failed"]
    assert "live_capacity" in report["failed"]
    assert report["remediation"], "fail-closed report must carry remediation strings"

    out = sprints / f"{SID}.preflight.json"
    assert out.is_file(), "report must land at sprints/<sid>.preflight.json"
    on_disk = json.loads(out.read_text())
    assert on_disk["ok"] is False
    assert on_disk["sid"] == SID


def test_run_preflight_green(tmp_path, ops_fixture):
    ops_fixture(FULL_SPINE)
    worktree = tmp_path / "checkout" / "harness"
    (worktree / "lib").mkdir(parents=True)
    sprints = tmp_path / "sprints"
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / ".credentials.json").write_text("x")
    (home / ".codex").mkdir(parents=True)
    (home / ".codex" / "auth.json").write_text("x")
    env = dict(_consistent_env(worktree))
    env["SPRINTS_DIR"] = str(sprints)

    report = rp.run_preflight(
        SID,
        providers=("anthropic", "openai"),
        expected_harness_dir=worktree,
        home=home,
        env=env,
        session_alive=True,
        solar_harness_path=None,
        modules={},
    )

    assert report["failed"] == []
    assert report["ok"] is True
    assert (sprints / f"{SID}.preflight.json").is_file()


def test_run_preflight_rejects_bad_sid(tmp_path):
    with pytest.raises(ValueError):
        rp.run_preflight("../evil", env={"SPRINTS_DIR": str(tmp_path)}, write=True)


# --- CLI ------------------------------------------------------------------------


def _fake_bin(tmp_path: Path) -> Path:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    for name in ("claude", "codex"):
        exe = fake_bin / name
        exe.write_text("#!/bin/sh\nexit 0\n")
        exe.chmod(0o755)
    # fake tmux: binary present (auto-startable), no session alive
    tmux = fake_bin / "tmux"
    tmux.write_text("#!/bin/sh\nexit 1\n")
    tmux.chmod(0o755)
    return fake_bin


def _cli_env(tmp_path: Path, worktree_harness: Path, ops_path: Path, home: Path) -> dict:
    env = {
        "HARNESS_DIR": str(worktree_harness),
        "SPRINTS_DIR": str(tmp_path / "sprints"),
        "PYTHONPATH": str(worktree_harness / "lib"),
        "SOLAR_MULTI_TASK_OPERATORS": str(ops_path),
        "HOME": str(home),
        "PATH": f"{_fake_bin(tmp_path)}:/usr/bin:/bin",
    }
    return env


def test_cli_exit_codes_and_report(tmp_path):
    worktree_harness = Path(rp.__file__).resolve().parents[1]
    ops_path = _write_operators(tmp_path / "ops.json", FULL_SPINE)
    home = tmp_path / "home"
    home.mkdir()
    env = _cli_env(tmp_path, worktree_harness, ops_path, home)

    module = Path(rp.__file__).resolve()
    red = subprocess.run(
        [sys.executable, str(module), "--sid", SID],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert red.returncode == 1, red.stdout + red.stderr
    report = json.loads((tmp_path / "sprints" / f"{SID}.preflight.json").read_text())
    assert report["ok"] is False
    assert "auth_presence" in report["failed"]

    # authenticate both providers -> preflight passes
    (home / ".claude").mkdir()
    (home / ".claude" / ".credentials.json").write_text("x")
    (home / ".codex").mkdir()
    (home / ".codex" / "auth.json").write_text("x")
    green = subprocess.run(
        [sys.executable, str(module), "--sid", SID],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert green.returncode == 0, green.stdout + green.stderr
    report = json.loads((tmp_path / "sprints" / f"{SID}.preflight.json").read_text())
    assert report["ok"] is True


def test_landlock_probe_grants_read_on_an_interpreter_outside_usr(tmp_path, monkeypatch):
    """The probe execs sys.executable, so its own prefix must be readable.

    The grants were a fixed list -- /usr, /bin, /lib, /lib64, /etc -- and the
    probe then executed the running interpreter. Under conda, pyenv or a
    virtualenv in $HOME that binary is outside every grant, so Landlock denied
    the exec with EACCES before any write was attempted, and preflight reported
    a filesystem that "cannot honor write grants". Measured on this machine:

        landlock_exec: active abi=3 ro=5 rw=1
        PermissionError: [Errno 13] Permission denied:
            '/home/ssubr/miniconda3/bin/python3'
    """
    harness = _landlock_harness(tmp_path)
    fake_prefix = tmp_path / "opt" / "conda"
    (fake_prefix / "bin").mkdir(parents=True)
    fake_python = fake_prefix / "bin" / "python3"
    fake_python.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(rp.sys, "executable", str(fake_python))
    monkeypatch.setattr(rp.sys, "prefix", str(fake_prefix))

    seen: dict = {}

    def _run(command, **_kwargs):
        seen["command"] = list(command)
        Path(command[-1]).write_bytes(b"landlock-ok")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(rp.subprocess, "run", _run)
    result = rp.check_codex_landlock_write_scope(
        harness_dir=harness,
        env={"SOLAR_PANE_RUNTIME": "codex"},
        platform_name="linux",
    )

    assert result["ok"] is True
    granted = [
        seen["command"][i + 1]
        for i, part in enumerate(seen["command"])
        if part == "--read-only"
    ]
    assert str(fake_python.parent) in granted, granted


def test_landlock_probe_does_not_duplicate_a_system_interpreter_grant(tmp_path, monkeypatch):
    """An interpreter already under /usr needs no extra grant."""
    harness = _landlock_harness(tmp_path)
    monkeypatch.setattr(rp.sys, "executable", "/usr/bin/python3")
    monkeypatch.setattr(rp.sys, "prefix", "/usr")
    seen: dict = {}

    def _run(command, **_kwargs):
        seen["command"] = list(command)
        Path(command[-1]).write_bytes(b"landlock-ok")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(rp.subprocess, "run", _run)
    rp.check_codex_landlock_write_scope(
        harness_dir=harness, env={"SOLAR_PANE_RUNTIME": "codex"}, platform_name="linux"
    )

    granted = [
        seen["command"][i + 1]
        for i, part in enumerate(seen["command"])
        if part == "--read-only"
    ]
    assert granted.count("/usr") == 1, granted
    assert "/usr/bin" not in granted


def test_landlock_remediation_distinguishes_denied_exec_from_bad_filesystem(tmp_path, monkeypatch):
    """The old text named one cause with total confidence, and was wrong.

    It sent the reader to check filesystems while the real fault was a binary
    outside the grant set, which cost three failed runs to notice.
    """
    harness = _landlock_harness(tmp_path)

    def _run(command, **_kwargs):
        return subprocess.CompletedProcess(command, 1, "", "PermissionError: Permission denied")

    monkeypatch.setattr(rp.subprocess, "run", _run)
    result = rp.check_codex_landlock_write_scope(
        harness_dir=harness, env={"SOLAR_PANE_RUNTIME": "codex"}, platform_name="linux"
    )

    assert result["ok"] is False
    # Both causes are offered, with the discriminator the reader can check.
    assert "error_tail" in result["remediation"]
    assert "outside the read-only grants" in result["remediation"]
    assert "/mnt/c" in result["remediation"]
