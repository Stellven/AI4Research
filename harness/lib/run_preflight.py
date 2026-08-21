#!/usr/bin/env python3
"""run_preflight.py — Lane 0.5: fail-closed run preflight (design §1.6; R5/R7/R8/R2d).

Before a run dispatches anything, prove the ground it stands on:

  1. harness_path_consistency — HARNESS_DIR / PYTHONPATH / a `solar-harness` on
     PATH / already-imported harness modules all resolve inside the ACTIVE tree,
     never a different checkout or the installed ~/.solar/harness (the cb2cc504
     / F-CLASS-21 installed-harness contamination class).
  2. codex_landlock_write_scope — for a Codex runtime, perform a real
     kernel-restricted write below the active Harness tree. This rejects WSL
     DrvFs deployments before a Sprint or Planner task is created.
  3. auth_presence — per-provider credential PRESENCE only, via stat/env-name
     checks (``~/.claude/.credentials.json`` non-empty or CLAUDE_CODE_OAUTH_TOKEN
     set; ``~/.codex/auth.json`` non-empty — same signals as auth-helpers.sh).
     Token contents are NEVER read and never appear in the report. A
     single-provider policy is a product contract: that provider must be authed;
     a multi-provider policy needs at least one authed provider.
  4. role_routes — per-role route resolution under the provider policy
     (SOLAR_MULTI_TASK_DEFAULT_PROVIDERS, default "anthropic,openai"; R5
     fail-closed per role). Candidates come from the real registry loaders and
     selectors (multi_task_runner.load_physical_operators / operator_dispatchable
     / _operator_backend_runnable) with lease/health state classified by THE
     single classifier, operator_runtime.get_operator_runtime_state. A role with
     zero policy-admissible, dispatchable, healthy operators fails the run.
     leased/running operators still route: busy is not broken (F-CLASS-08).
  5. live_capacity — the multi-task pool session is up, or is auto-startable
     (tmux present). Zero capacity fails closed (the "no live workers" wall).
  6. contract_compile — when the run is contracted, the workflow contract must
     compile via the Lane 1 ``workflow_contract`` module, against THIS run's
     provider policy (not the contract's embedded one), so the contract gate and
     the run resolve the same stage the same way; a contracted run on a tree
     without the compiler fails closed, never silently skips.

Output: ``$SPRINTS_DIR/<sid>.preflight.json`` (SPRINTS_DIR -> HARNESS_SPRINTS_DIR
-> $HARNESS_DIR/sprints), written atomically; ``ok`` is the AND of every check
and each failing check carries a remediation string.

CLI (exit 0 pass / 1 fail-closed / 2 usage):
    python3 run_preflight.py --sid <sid> [--roles planner,builder,evaluator]
        [--providers anthropic,openai] [--contract path.workflow.json]
        [--expect-harness-dir DIR] [--no-write]

Intended call sites (hooks land via the Lane 0 serialized-files stub PR; this
lane does not edit those files):
  * harness/solar-harness.sh — a thin ``preflight-run`` subcommand stub calling
    this CLI before intake/dispatch of a sprint (distinct from the existing
    ``preflight`` launch-dependency check).
  * scripts/live-codex-e2e-isolated.sh — run preflight inside the isolated
    sandbox before submitting the task, so a doomed run fails in seconds.
  * runtime-validation-ladder P2+ rungs — the preflight report is part of each
    run bundle's evidence.
"""
from __future__ import annotations

import argparse
import datetime
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

_SID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_UNSET = object()

DEFAULT_ROLES: Tuple[str, ...] = ("planner", "builder", "evaluator")
# states from operator_runtime.get_operator_runtime_state that make an operator
# un-routable; leased/running/draining mean busy-not-broken and still route
_BLOCKING_STATES = {"disabled", "quota_exhausted", "auth_expired"}


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _env(env: Optional[Mapping[str, str]]) -> Mapping[str, str]:
    return os.environ if env is None else env


def _provider_policy(env: Optional[Mapping[str, str]] = None) -> Tuple[str, ...]:
    """Same parsing as multi_task_runner.DEFAULT_OPERATOR_PROVIDER_ORDER, but read
    at call time (multi_task_runner captures the env at import, which is stale in
    long-lived processes)."""
    raw = _env(env).get("SOLAR_MULTI_TASK_DEFAULT_PROVIDERS", "anthropic,openai")
    return tuple(p.strip().lower() for p in raw.split(",") if p.strip())


def _check(name: str, ok: bool, detail: Dict[str, Any], remediation: str = "") -> Dict[str, Any]:
    return {
        "check": name,
        "ok": bool(ok),
        "detail": detail,
        "remediation": remediation if not ok else "",
    }


# --- 1. harness path self-consistency (cb2cc504 / F-CLASS-21) --------------------


def check_harness_path_consistency(
    expected_harness_dir: Optional[Path | str] = None,
    env: Optional[Mapping[str, str]] = None,
    solar_harness_path: Any = _UNSET,
    modules: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    env_map = _env(env)
    expected = Path(expected_harness_dir or Path(__file__).resolve().parents[1]).resolve()
    expected_lib = (expected / "lib").resolve()
    installed = (Path.home() / ".solar" / "harness").resolve()
    problems: List[str] = []

    raw_hd = env_map.get("HARNESS_DIR", "")
    if not raw_hd:
        problems.append("HARNESS_DIR is unset (children fall back to ~/.solar/harness)")
    else:
        resolved = Path(raw_hd).resolve()
        if resolved != expected:
            note = " (the installed harness — F-CLASS-21 contamination)" if resolved == installed else ""
            problems.append(f"HARNESS_DIR={raw_hd} resolves outside the active tree{note}")

    raw_shd = env_map.get("SOLAR_HARNESS_DIR", "")
    if raw_shd and Path(raw_shd).resolve() != expected:
        problems.append(f"SOLAR_HARNESS_DIR={raw_shd} resolves outside the active tree")

    pythonpath_entries = [p for p in env_map.get("PYTHONPATH", "").split(os.pathsep) if p]
    resolved_entries = []
    for entry in pythonpath_entries:
        try:
            resolved_entries.append(Path(entry).resolve())
        except OSError:
            continue
    if expected_lib not in resolved_entries:
        problems.append(
            f"PYTHONPATH does not pin the active tree's lib ({expected_lib}); "
            "child processes will import whatever tree they find first"
        )

    if solar_harness_path is _UNSET:
        solar_harness_path = shutil.which("solar-harness")
    if solar_harness_path:
        resolved_cli = Path(str(solar_harness_path)).resolve()
        allowed_roots = {expected, expected.parent}
        if not any(root == resolved_cli or root in resolved_cli.parents for root in allowed_roots):
            problems.append(
                f"solar-harness on PATH resolves to a different tree: {resolved_cli}"
            )

    module_map: Mapping[str, Any]
    if modules is None:
        module_map = {
            name: sys.modules[name]
            for name in ("multi_task_runner", "operator_runtime", "run_process_registry")
            if name in sys.modules
        }
    else:
        module_map = modules
    for name, module in module_map.items():
        file_value = getattr(module, "__file__", None)
        if not file_value:
            continue
        resolved_mod = Path(file_value).resolve()
        if expected not in resolved_mod.parents:
            problems.append(f"module {name} imported from outside the active tree: {resolved_mod}")

    remediation = (
        f"pin the run to the active tree: export HARNESS_DIR={expected} "
        f"PYTHONPATH={expected_lib} and put its solar-harness shim first on PATH"
        if problems
        else ""
    )
    return _check(
        "harness_path_consistency",
        not problems,
        {"expected": str(expected), "problems": problems},
        remediation,
    )


# --- 2. Codex Landlock write capability -----------------------------------------


def check_codex_landlock_write_scope(
    harness_dir: Optional[Path | str] = None,
    env: Optional[Mapping[str, str]] = None,
    platform_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Prove that Landlock can write an explicitly granted Harness file.

    WSL DrvFs accepts the Landlock rule but denies the later write. A normal
    directory-writable check therefore produces a false green run; only an
    actual restricted child write detects the deployment wall.
    """
    env_map = _env(env)
    runtime = str(
        env_map.get("SOLAR_PANE_RUNTIME")
        or env_map.get("SOLAR_RUNTIME")
        or ""
    ).strip().lower()
    mode = str(env_map.get("SOLAR_CODEX_OPERATOR_FS_ISOLATION") or "landlock").strip().lower()
    strict = str(env_map.get("SOLAR_OPERATOR_STRICT_FS_SCOPE") or "").strip().lower() in {
        "1", "true", "yes", "on"
    }
    if runtime != "codex":
        return _check(
            "codex_landlock_write_scope",
            True,
            {"skipped": "runtime_not_codex", "runtime": runtime or "unset"},
        )
    if mode in {"0", "off", "disabled", "none"}:
        return _check(
            "codex_landlock_write_scope",
            not strict,
            {"skipped": "landlock_disabled", "strict": strict},
            "strict Codex operator scope requires Landlock; enable SOLAR_CODEX_OPERATOR_FS_ISOLATION=landlock",
        )
    effective_platform = platform_name or sys.platform
    if effective_platform != "linux":
        return _check(
            "codex_landlock_write_scope",
            not strict,
            {"skipped": "landlock_requires_linux", "platform": effective_platform, "strict": strict},
            "strict Codex operator scope requires a Linux filesystem with Landlock support",
        )

    harness = Path(harness_dir or _harness_dir_from_env(env_map)).expanduser().resolve(strict=False)
    wrapper = harness / "tools" / "landlock_exec.py"
    if not wrapper.is_file():
        return _check(
            "codex_landlock_write_scope",
            False,
            {"harness_dir": str(harness), "error": "landlock_wrapper_missing"},
            f"Landlock wrapper missing from active Harness: {wrapper}",
        )

    probe_dir = harness / "run" / "preflight-probes"
    probe: Optional[Path] = None
    try:
        probe_dir.mkdir(parents=True, exist_ok=True)
        fd, raw_probe = tempfile.mkstemp(prefix="landlock-write-", dir=probe_dir)
        os.close(fd)
        probe = Path(raw_probe).resolve(strict=False)
        command = [sys.executable, str(wrapper)]
        system_root_strings = ["/usr", "/bin", "/lib", "/lib64", "/etc"]
        readable_roots = [
            (Path(root).resolve(strict=False), root) for root in system_root_strings
        ]
        # The probe execs this same interpreter, so its own prefix has to be
        # readable or Landlock denies the exec before the write is ever
        # attempted. A Python outside /usr -- conda, pyenv, a virtualenv in
        # $HOME -- is not covered by the roots above, and the check then fails
        # with EACCES on the interpreter and reports it as a filesystem that
        # cannot honour write grants, which sends the reader after the wrong
        # problem entirely.
        interpreter = Path(sys.executable).resolve(strict=False)
        prefix = Path(sys.prefix).resolve(strict=False)
        for extra in (interpreter.parent, prefix):
            if extra.exists() and not any(
                extra == root or root in extra.parents for root, _display in readable_roots
            ):
                readable_roots.append((extra, str(extra)))
        for readable, display in readable_roots:
            if display in system_root_strings or readable.exists():
                command.extend(["--read-only", display])
        command.extend(
            [
                "--read-write",
                str(probe),
                "--",
                sys.executable,
                "-c",
                (
                    "import os,sys; "
                    "fd=os.open(sys.argv[1],os.O_WRONLY|os.O_TRUNC); "
                    "os.write(fd,b'landlock-ok'); os.close(fd)"
                ),
                str(probe),
            ]
        )
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=15,
            env=dict(env_map),
        )
        wrote = completed.returncode == 0 and probe.read_bytes() == b"landlock-ok"
        detail = {
            "harness_dir": str(harness),
            "mode": mode,
            "returncode": completed.returncode,
            "error_tail": (completed.stderr or completed.stdout or "")[-500:] if not wrote else "",
        }
    except Exception as exc:
        wrote = False
        detail = {
            "harness_dir": str(harness),
            "mode": mode,
            "error": f"{type(exc).__name__}: {exc}",
        }
    finally:
        if probe is not None:
            try:
                probe.unlink(missing_ok=True)
            except OSError:
                pass

    return _check(
        "codex_landlock_write_scope",
        wrote,
        detail,
        (
            "Landlock could not complete the write probe. If error_tail shows "
            "PermissionError on an executable, the interpreter or a helper binary "
            "sits outside the read-only grants and the exec was denied before any "
            "write was attempted. Otherwise the Harness filesystem cannot honor "
            "write grants: on WSL install SOLAR_HOME/HARNESS_DIR inside the Linux "
            "ext4 filesystem (for example /home/<user>/.solar), not under /mnt/c, "
            "then rerun preflight"
        ),
    )


# --- 3. auth presence (existence/validity signal only — never token contents) ----


def _file_nonempty(path: Path) -> bool:
    try:
        return path.stat().st_size > 0
    except OSError:
        return False


def _auth_signal(
    provider: str, home: Path, env: Mapping[str, str]
) -> Tuple[bool, str]:
    if provider == "anthropic":
        if _file_nonempty(home / ".claude" / ".credentials.json"):
            return True, "file:.claude/.credentials.json"
        if env.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip():
            return True, "env:CLAUDE_CODE_OAUTH_TOKEN"
        return False, "file:.claude/.credentials.json"
    if provider == "openai":
        return _file_nonempty(home / ".codex" / "auth.json"), "file:.codex/auth.json"
    if provider in {"zhipu", "glm"}:
        secrets = Path(
            env.get("SOLAR_SECRETS_ENV", "")
            or home / ".solar" / "secrets" / "solar-user-secrets.env"
        )
        return _file_nonempty(secrets), "file:.solar/secrets/solar-user-secrets.env"
    return False, "no_presence_signal"


def check_auth_presence(
    providers: Sequence[str],
    home: Optional[Path | str] = None,
    env: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    env_map = _env(env)
    home_dir = Path(home) if home else Path.home()
    normalized = [str(p).strip().lower() for p in providers if str(p).strip()]
    report: Dict[str, Any] = {}
    present: List[str] = []
    for provider in normalized:
        found, signal_name = _auth_signal(provider, home_dir, env_map)
        report[provider] = {"present": found, "signal": signal_name}
        if found:
            present.append(provider)

    if not normalized:
        ok = False
        why = "no providers to check"
    elif len(normalized) == 1:
        ok = bool(present)  # single-provider policy: that provider must be authed
        why = ""
    else:
        ok = bool(present)  # mixed policy: at least one provider can run
        why = ""

    remediation = ""
    if not ok:
        remediation = (
            "no authenticated provider available"
            + (f" ({why})" if why else "")
            + ": run `claude setup-token` (anthropic) or `codex login --device-auth` "
            "(openai); see harness/auth-helpers.sh"
        )
    return _check("auth_presence", ok, {"providers": report}, remediation)


# --- 3. per-role route resolution under provider policy ---------------------------


def check_role_routes(
    roles: Sequence[str] = DEFAULT_ROLES,
    providers: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    policy = _provider_policy() if providers is None else tuple(
        str(p).strip().lower() for p in providers if str(p).strip()
    )
    try:
        multi_task_runner = importlib.import_module("multi_task_runner")
        operator_runtime = importlib.import_module("operator_runtime")
    except Exception as exc:  # fail closed: no selectors means no provable routes
        return _check(
            "role_routes",
            False,
            {"error": f"selector modules unavailable: {exc}"},
            "run preflight from inside the active harness tree (lib on PYTHONPATH)",
        )

    operators = multi_task_runner.load_physical_operators().get("operators") or {}
    role_report: Dict[str, Any] = {}
    failing: List[str] = []
    for role in [str(r).strip().lower() for r in roles if str(r).strip()]:
        candidates: List[Dict[str, Any]] = []
        excluded: List[Dict[str, Any]] = []
        for operator_id, spec in operators.items():
            if not isinstance(spec, dict):
                continue
            if str(spec.get("role") or "").strip().lower() != role:
                continue
            operator = multi_task_runner._operator_ref(operator_id, dict(spec))
            provider = str(operator.get("provider") or operator.get("vendor") or "").lower()

            def _exclude(why: str) -> None:
                excluded.append({"operator_id": operator_id, "why": why})

            if bool(operator.get("deprecated")):
                _exclude("deprecated")
                continue
            if not operator.get("enabled", True):
                _exclude("disabled")
                continue
            if policy and provider not in policy:
                _exclude(f"provider_policy_excludes:{provider or 'unknown'}")
                continue
            dispatchable, reason = multi_task_runner.operator_dispatchable(operator)
            # This preflight proves that a role has a valid route, not that the
            # selected worker is idle at this instant.  A leased/running worker
            # is temporarily busy but remains a configured, healthy route.
            busy = reason in {"dynamic_state_leased", "dynamic_state_running"}
            if not dispatchable and not busy:
                _exclude(f"not_dispatchable:{reason}")
                continue
            if not multi_task_runner._operator_backend_runnable(operator):
                _exclude("backend_cli_missing")
                continue
            state = operator_runtime.get_operator_runtime_state(operator_id)
            if state in _BLOCKING_STATES:
                _exclude(f"runtime_state_{state}")
                continue
            candidates.append(
                {
                    "operator_id": operator_id,
                    "provider": provider,
                    "backend": str(operator.get("backend") or ""),
                    "state": state,
                }
            )
        role_report[role] = {"candidates": candidates, "excluded": excluded}
        if not candidates:
            failing.append(role)

    remediation = ""
    if failing:
        remediation = (
            f"no routable operator for role(s) {', '.join(failing)} under provider policy "
            f"{list(policy) or 'ALL'}: enable a matching operator in physical-operators.json "
            "or adjust SOLAR_MULTI_TASK_DEFAULT_PROVIDERS"
        )
    return _check(
        "role_routes",
        not failing,
        {"policy": list(policy), "roles": role_report},
        remediation,
    )


# --- 4. live capacity --------------------------------------------------------------


def check_live_capacity(
    session_alive: Optional[bool] = None,
    tmux_available: Optional[bool] = None,
) -> Dict[str, Any]:
    if session_alive is None:
        try:
            multi_task_runner = importlib.import_module("multi_task_runner")
            session_alive = bool(multi_task_runner.tmux_session_exists())
        except Exception:
            session_alive = False
    if tmux_available is None:
        tmux_available = shutil.which("tmux") is not None

    mode = "pool_up" if session_alive else ("auto_startable" if tmux_available else "none")
    ok = mode != "none"
    remediation = ""
    if not ok:
        remediation = (
            "zero live worker capacity: the multi-task pool session is down and tmux is "
            "missing — install tmux, then start workers with `solar-harness multi-task start`"
        )
    return _check(
        "live_capacity",
        ok,
        {"pool_session_alive": bool(session_alive), "tmux_available": bool(tmux_available), "mode": mode},
        remediation,
    )


# --- 5. contract compile (fail-closed when contracted) ------------------------------


def _compiler_policy_arg(provider_policy: Optional[Sequence[str]]) -> Optional[Dict[str, Any]]:
    """Shape the RUN provider policy into the Lane 1 compiler's policy object
    (``{"allowed_providers": [...]}``). A non-empty run policy is authoritative and
    overrides the contract's embedded provider_policy (F13 — compile the contract
    against the policy the run will actually execute under). An absent/empty run
    policy imposes no wall, so we pass None and let compile_checks fall back to the
    contract's own embedded policy (pre-F13 behavior; matches check_role_routes'
    empty-policy semantics)."""
    providers = [str(p).strip().lower() for p in (provider_policy or ()) if str(p).strip()]
    return {"allowed_providers": providers} if providers else None


def check_contract_compiles(
    contract_path: Optional[Path | str],
    provider_policy: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    if not contract_path:
        return _check("contract_compile", True, {"skipped": "not_contracted"})
    path = Path(contract_path)
    if not path.is_file():
        return _check(
            "contract_compile",
            False,
            {"contract": str(path), "error": "contract_file_missing"},
            f"contract file not found: {path}",
        )
    try:
        workflow_contract = importlib.import_module("workflow_contract")
    except ImportError:
        return _check(
            "contract_compile",
            False,
            {"contract": str(path), "error": "workflow_contract_module_unavailable"},
            "this tree has no workflow_contract compiler (Lane 1); a contracted run "
            "must not proceed uncompiled",
        )

    # Lane 1 API (contract/lane1-compiler): load_contract raises on schema errors;
    # compile_checks(contract, capsule_registry, operator_registry, provider_policy)
    # -> [] iff it compiles. Passing the RUN policy (not the contract's embedded one)
    # is F13: the contract must compile against the policy the run executes under.
    load_contract = getattr(workflow_contract, "load_contract", None)
    compile_checks = getattr(workflow_contract, "compile_checks", None)
    if callable(load_contract) and callable(compile_checks):
        try:
            contract = load_contract(str(path))
            capsules = getattr(workflow_contract, "load_capsule_registry", dict)()
            operators = getattr(workflow_contract, "load_operator_registry", dict)()
            errors = compile_checks(
                contract, capsules, operators,
                provider_policy=_compiler_policy_arg(provider_policy),
            )
        except Exception as exc:
            return _check(
                "contract_compile",
                False,
                {"contract": str(path), "error": f"{type(exc).__name__}: {exc}"},
                f"contract does not load/compile: {exc}",
            )
        if errors:
            return _check(
                "contract_compile",
                False,
                {"contract": str(path), "errors": list(errors)[:10]},
                f"contract does not compile: {len(errors)} compile error(s)",
            )
        return _check(
            "contract_compile", True, {"contract": str(path), "api": "load_contract+compile_checks"}
        )

    # API-drift fallback: any single-arg compile entrypoint; still fail-closed
    compile_fn = None
    for name in ("compile_workflow_contract", "compile_contract", "load_and_compile", "compile"):
        candidate = getattr(workflow_contract, name, None)
        if callable(candidate):
            compile_fn = candidate
            break
    if compile_fn is None:
        return _check(
            "contract_compile",
            False,
            {"contract": str(path), "error": "no_known_compile_entrypoint"},
            "workflow_contract exposes no compile entrypoint this preflight knows; "
            "align run_preflight with the Lane 1 API",
        )
    try:
        compile_fn(str(path))
    except Exception as exc:
        return _check(
            "contract_compile",
            False,
            {"contract": str(path), "error": f"{type(exc).__name__}: {exc}"},
            f"contract does not compile: {exc}",
        )
    return _check("contract_compile", True, {"contract": str(path), "api": "fallback_probe"})


# --- report ---------------------------------------------------------------------------


def _harness_dir_from_env(env_map: Mapping[str, str]) -> Path:
    raw = env_map.get("HARNESS_DIR") or env_map.get("SOLAR_HARNESS_DIR")
    return Path(raw) if raw else Path.home() / ".solar" / "harness"


def sprints_dir(env: Optional[Mapping[str, str]] = None) -> Path:
    env_map = _env(env)
    raw = env_map.get("SPRINTS_DIR") or env_map.get("HARNESS_SPRINTS_DIR")
    if raw:
        return Path(raw)
    return _harness_dir_from_env(env_map) / "sprints"


def write_report(sid: str, report: Dict[str, Any], env: Optional[Mapping[str, str]] = None) -> Path:
    out_dir = sprints_dir(env)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{sid}.preflight.json"
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, out)
    return out


def run_preflight(
    sid: str,
    roles: Sequence[str] = DEFAULT_ROLES,
    providers: Optional[Sequence[str]] = None,
    contract_path: Optional[Path | str] = None,
    expected_harness_dir: Optional[Path | str] = None,
    home: Optional[Path | str] = None,
    env: Optional[Mapping[str, str]] = None,
    session_alive: Optional[bool] = None,
    tmux_available: Optional[bool] = None,
    solar_harness_path: Any = _UNSET,
    modules: Optional[Mapping[str, Any]] = None,
    write: bool = True,
) -> Dict[str, Any]:
    sid = str(sid or "").strip()
    if not _SID_RE.fullmatch(sid):
        raise ValueError(f"invalid sid (path-safe [A-Za-z0-9._-] required): {sid!r}")
    env_map = _env(env)
    policy = (
        _provider_policy(env_map)
        if providers is None
        else tuple(str(p).strip().lower() for p in providers if str(p).strip())
    )

    checks = [
        check_harness_path_consistency(
            expected_harness_dir=expected_harness_dir,
            env=env_map,
            solar_harness_path=solar_harness_path,
            modules=modules,
        ),
        check_codex_landlock_write_scope(
            harness_dir=expected_harness_dir or _harness_dir_from_env(env_map),
            env=env_map,
        ),
        check_auth_presence(policy, home=home, env=env_map),
        check_role_routes(roles=roles, providers=policy),
        check_live_capacity(session_alive=session_alive, tmux_available=tmux_available),
        check_contract_compiles(contract_path, provider_policy=policy),
    ]
    failed = [c["check"] for c in checks if not c["ok"]]
    report: Dict[str, Any] = {
        "kind": "preflight_run",
        "ok": not failed,
        "sid": sid,
        "written_at": _now(),
        "provider_policy": list(policy),
        "roles": [str(r).strip().lower() for r in roles if str(r).strip()],
        "checks": checks,
        "failed": failed,
        "remediation": [c["remediation"] for c in checks if c["remediation"]],
    }
    if write:
        report["report_path"] = str(sprints_dir(env_map) / f"{sid}.preflight.json")
        write_report(sid, report, env_map)
    return report


# --- CLI ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail-closed run preflight (Lane 0.5, design §1.6)"
    )
    parser.add_argument("--sid", required=True, help="sprint/run id; report lands at sprints/<sid>.preflight.json")
    parser.add_argument("--roles", default=",".join(DEFAULT_ROLES))
    parser.add_argument("--providers", default=None, help="override provider policy (csv)")
    parser.add_argument("--contract", default=None, help="workflow contract path (compile check)")
    parser.add_argument("--expect-harness-dir", default=None)
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args(argv)

    roles = tuple(r.strip() for r in args.roles.split(",") if r.strip())
    providers = (
        tuple(p.strip() for p in args.providers.split(",") if p.strip())
        if args.providers is not None
        else None
    )
    try:
        report = run_preflight(
            args.sid,
            roles=roles,
            providers=providers,
            contract_path=args.contract,
            expected_harness_dir=args.expect_harness_dir,
            write=not args.no_write,
        )
    except ValueError as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
