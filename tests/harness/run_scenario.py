#!/usr/bin/env python3
"""run_scenario.py — Lane 2 fake-operator scenario runner (the testing engine).

Given a ``*.scenario.json`` it builds a hermetic ``HARNESS_DIR``, wires a deterministic
``fake_operator.py`` operator through the **real** operator-pool command backend
(``operator_runtime.submit`` → ``operatord daemon --once`` → ``result.json``), collects the
resulting runtime facts, and evaluates the scenario's ``expect`` assertions. Nothing here is
mocked: the actual lease lifecycle, timeout enforcement, flow-control, heartbeat, and result
writer execute. See ``docs/product/lane2-spec-mismatches.md`` for why this seam (not the
``SOLAR_GRAPH_DISPATCH_FAKE_WORKERS`` pane stub) is the one Lane 2 builds on.

Red-before-green (independence guard #1): every scenario declares a ``fault`` block. Running
with ``--red`` injects that fault (disables the guard / removes the fix / makes the fault
present) and re-evaluates the **same** ``expect`` assertions. A valid scenario passes green and
FAILS red — proving it discriminates the class rather than being a tautology. The paired
pytest (``test_lane2_scenarios.py``) asserts exactly this for every ``verified_here`` scenario.

Scenario schema (JSON)::

    {
      "id": "F-CLASS-28",
      "class": 28,
      "title": "…",
      "mode": "submit_once" | "pre_lease_then_submit" | "kill_mid_run",
      "release_proof_level": "P1.5",
      "operator_id": "fake-builder",
      "operators": { "<id>": { registry entry … } },   # optional; a default is provided
      "env": { "SOLAR_OPERATORD_TASK_TIMEOUT_SECONDS": "3" },  # green env
      "daemon_cap_sec": 10,                              # our subprocess wall cap
      "envelope": { "fake_behavior": { … }, "task_type": "implementation", … },
      "fault": {                                         # red-mode injection
        "env": { "SOLAR_OPERATORD_TASK_TIMEOUT_SECONDS": "0" },
        "behavior": { … },        # merged into envelope.fake_behavior
        "operators": { … },       # merged into the registry (e.g. flip enabled)
        "skip_pre_lease": true,   # pre_lease_then_submit only
        "operator_id": "…"        # optional: submit to a different operator in red
      },
      "expect": [ { "fact": "result_status", "op": "eq", "value": "failed_timeout" }, … ]
    }
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_HARNESS = (Path(__file__).resolve().parents[2] / 'harness')
LIB_DIR = REPO_HARNESS / "lib"
TOOLS_DIR = REPO_HARNESS / "tools"
FAKE_OPERATOR = TOOLS_DIR / "fake_operator.py"
OPERATOR_RUNTIME = LIB_DIR / "operator_runtime.py"
OPERATORD = TOOLS_DIR / "operatord.py"
REAL_PERSONAS_DIR = REPO_HARNESS / "personas"
SCENARIOS_DIR = (Path(__file__).resolve().parents[2] / 'tests' / 'harness') / "scenarios"

DEFAULT_OPERATOR_ID = "fake-builder"


def _default_registry(operator_id: str) -> Dict[str, Any]:
    return {
        "version": 1,
        "operators": {
            operator_id: {
                "display_name": f"Fake builder ({operator_id})",
                "role": "builder",
                "persona": "builder",
                "backend": "command",
                "provider": "anthropic",
                "vendor": "Anthropic",
                "model": "fake-local",
                "enabled": True,
                "available": True,
                "roles": ["builder"],
                "task_classes": ["implementation"],
            }
        },
    }


def _write_personas(harness_dir: Path) -> None:
    personas = harness_dir / "personas"
    personas.mkdir(parents=True, exist_ok=True)
    for name in ("builder", "evaluator", "planner"):
        real = REAL_PERSONAS_DIR / f"{name}.md"
        dest = personas / f"{name}.md"
        if real.exists():
            shutil.copy(real, dest)
        else:
            dest.write_text(f"# {name.title()}\nYou are a {name}.\n", encoding="utf-8")
    # Evaluator verification protocol file is optional; provide a stub so the
    # evaluator persona resolves cleanly if a scenario uses it.
    proto = personas / "evaluator-verification-protocol.md"
    if not proto.exists():
        proto.write_text("# Evaluator Verification Protocol\nDeterministic scenario stub.\n", encoding="utf-8")


def _base_env(harness_dir: Path, extra: Dict[str, str]) -> Dict[str, str]:
    env = dict(os.environ)
    env["HARNESS_DIR"] = str(harness_dir)
    env["SPRINTS_DIR"] = str(harness_dir / "sprints")
    env["PYTHONPATH"] = os.pathsep.join(
        [str(LIB_DIR), str(TOOLS_DIR), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    # Never let submit() auto-spawn a detached daemon; the runner drives it explicitly.
    env["SOLAR_OPERATORD_AUTO_KICK"] = "0"
    for key, value in (extra or {}).items():
        env[str(key)] = str(value)
    return env


def _run_submit(env: Dict[str, str], envelope_path: Path) -> Tuple[bool, str, str]:
    proc = subprocess.run(
        [sys.executable, str(OPERATOR_RUNTIME), "submit", "--envelope", str(envelope_path)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    ok = proc.returncode == 0
    err = (proc.stderr or "").strip() or (proc.stdout or "").strip()
    return ok, err, (proc.stdout or "").strip()


def _run_acquire(env: Dict[str, str], operator_id: str, task_id: str, sprint_id: str, node_id: str, ttl: int = 3600) -> bool:
    proc = subprocess.run(
        [
            sys.executable, str(OPERATOR_RUNTIME), "acquire",
            "--operator", operator_id, "--task-id", task_id,
            "--sprint-id", sprint_id, "--node-id", node_id, "--ttl", str(ttl),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return proc.returncode == 0


def _run_daemon_once(env: Dict[str, str], operator_id: str, cap_sec: float) -> Tuple[Optional[int], bool, str]:
    proc = subprocess.Popen(
        [
            sys.executable, str(OPERATORD), "daemon",
            "--operator", operator_id, "--once", "--poll-interval", "0.2",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        out, _ = proc.communicate(timeout=cap_sec)
        return proc.returncode, False, (out or "")
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except Exception:
            proc.kill()
        try:
            out, _ = proc.communicate(timeout=5)
        except Exception:
            out = ""
        return None, True, (out or "")


def _start_daemon(env: Dict[str, str], operator_id: str) -> subprocess.Popen:
    return subprocess.Popen(
        [
            sys.executable, str(OPERATORD), "daemon",
            "--operator", operator_id, "--poll-interval", "0.1",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _result_path(harness_dir: Path, operator_id: str, task_id: str) -> Path:
    return harness_dir / "run" / "operator-results" / operator_id / task_id / "result.json"


def _collect_facts(
    harness_dir: Path,
    operator_id: str,
    task_id: str,
    submit_ok: bool,
    submit_error: str,
    daemon_rc: Optional[int],
    daemon_timed_out: bool,
) -> Dict[str, Any]:
    result = _read_json(_result_path(harness_dir, operator_id, task_id))
    status_file = _read_json(harness_dir / "run" / "operator-status" / f"{operator_id}.json")
    lease_file = harness_dir / "run" / "operator-leases" / f"{operator_id}.json"
    envelope_recorded = (
        harness_dir / "run" / "operator-results" / operator_id / task_id / "envelope.json"
    ).exists()
    return {
        "submit_ok": submit_ok,
        "submit_error": submit_error,
        "daemon_returncode": daemon_rc,
        "daemon_timed_out": daemon_timed_out,
        "result_exists": result is not None,
        "result_status": (result or {}).get("status", ""),
        "result_exit_code": (result or {}).get("exit_code"),
        "result_has_model_route": bool((result or {}).get("model_route")),
        "operator_status_state": (status_file or {}).get("runtime_state", ""),
        "final_heartbeat_state": (status_file or {}).get("state", ""),
        "lease_exists": lease_file.exists(),
        "envelope_recorded": envelope_recorded,
    }


# ── expect evaluation ────────────────────────────────────────────────────────

def _apply_op(actual: Any, op: str, value: Any) -> bool:
    if op == "eq":
        return actual == value
    if op == "ne":
        return actual != value
    if op == "contains":
        return isinstance(actual, str) and str(value) in actual
    if op == "not_contains":
        return not (isinstance(actual, str) and str(value) in actual)
    if op == "in":
        return actual in (value or [])
    if op == "gte":
        try:
            return float(actual) >= float(value)
        except Exception:
            return False
    if op == "lte":
        try:
            return float(actual) <= float(value)
        except Exception:
            return False
    if op == "truthy":
        return bool(actual)
    if op == "falsy":
        return not bool(actual)
    raise ValueError(f"unknown expect op: {op}")


def _evaluate(expect: List[Dict[str, Any]], facts: Dict[str, Any]) -> List[Dict[str, Any]]:
    checks = []
    for clause in expect:
        fact = clause["fact"]
        op = clause.get("op", "eq")
        value = clause.get("value")
        actual = facts.get(fact)
        ok = _apply_op(actual, op, value)
        checks.append({"fact": fact, "op": op, "value": value, "actual": actual, "ok": ok})
    return checks


# ── scenario execution ───────────────────────────────────────────────────────

def _merge_fault(scenario: Dict[str, Any], red: bool) -> Dict[str, Any]:
    scen = copy.deepcopy(scenario)
    if not red:
        return scen
    fault = scen.get("fault") or {}
    # env
    env = dict(scen.get("env") or {})
    env.update(fault.get("env") or {})
    scen["env"] = env
    # behavior
    envelope = dict(scen.get("envelope") or {})
    behavior = dict(envelope.get("fake_behavior") or {})
    behavior.update(fault.get("behavior") or {})
    if behavior:
        envelope["fake_behavior"] = behavior
    scen["envelope"] = envelope
    # registry overrides
    if fault.get("operators"):
        operators = dict((scen.get("operators") or {}))
        for oid, patch in fault["operators"].items():
            base = dict(operators.get(oid) or {})
            base.update(patch)
            operators[oid] = base
        scen["operators"] = operators
    # mode-specific flags
    if fault.get("skip_pre_lease"):
        scen["_skip_pre_lease"] = True
    if fault.get("operator_id"):
        scen["operator_id"] = fault["operator_id"]
    if fault.get("kill_signal"):
        scen["kill_signal"] = fault["kill_signal"]
    return scen


def run_scenario(scenario: Dict[str, Any], *, red: bool = False, workdir: Optional[Path] = None, keep: bool = False) -> Dict[str, Any]:
    scen = _merge_fault(scenario, red)
    operator_id = scen.get("operator_id", DEFAULT_OPERATOR_ID)
    mode = scen.get("mode", "submit_once")
    cap_sec = float(scen.get("daemon_cap_sec", 30))

    own_workdir = workdir is None
    harness_dir = Path(workdir) if workdir else Path(
        os.environ.get("TMPDIR", "/tmp")
    ) / f"lane2-{scen.get('id','scenario')}-{'red' if red else 'green'}-{os.getpid()}-{int(time.monotonic()*1000)%100000}"
    harness_dir.mkdir(parents=True, exist_ok=True)
    try:
        (harness_dir / "config").mkdir(parents=True, exist_ok=True)
        (harness_dir / "sprints").mkdir(parents=True, exist_ok=True)
        _write_personas(harness_dir)
        registry = {"version": 1, "operators": {}}
        registry["operators"].update(_default_registry(operator_id)["operators"])
        for oid, entry in (scen.get("operators") or {}).items():
            registry["operators"][oid] = entry
        (harness_dir / "config" / "physical-operators.json").write_text(
            json.dumps(registry, indent=2), encoding="utf-8"
        )

        env = _base_env(harness_dir, scen.get("env") or {})

        task_id = scen.get("task_id", f"T-{scen.get('id','scn')}")
        sprint_id = scen.get("sprint_id", f"sprint-{scen.get('id','scn')}")
        node_id = scen.get("node_id", "N1")

        envelope: Dict[str, Any] = {
            "task_id": task_id,
            "sprint_id": sprint_id,
            "node_id": node_id,
            "operator_id": operator_id,
            "task_type": "implementation",
            "objective": scen.get("title", "fake scenario task"),
            "command": f"{shlex_quote(sys.executable)} {shlex_quote(str(FAKE_OPERATOR))}",
        }
        envelope.update(scen.get("envelope") or {})
        # Guard: the runner never lets a scenario request capability-capsule resolution
        # (that would pull in unrelated runtime); keep the envelope on the plain path.
        for k in ("capability_native", "capability_capsule_id", "execution_capsule_id"):
            envelope.pop(k, None)

        submit_ok = False
        submit_error = ""
        submit_stdout = ""
        daemon_rc: Optional[int] = None
        daemon_timed_out = False

        if mode == "pre_lease_then_submit":
            if not scen.get("_skip_pre_lease"):
                _run_acquire(env, operator_id, f"{task_id}-pre", sprint_id, node_id)
            envelope_path = harness_dir / "envelope.json"
            envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
            submit_ok, submit_error, submit_stdout = _run_submit(env, envelope_path)
            # Only drive the daemon if submit actually queued work.
            if submit_ok:
                daemon_rc, daemon_timed_out, _ = _run_daemon_once(env, operator_id, cap_sec)

        elif mode == "kill_mid_run":
            envelope_path = harness_dir / "envelope.json"
            envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
            submit_ok, submit_error, submit_stdout = _run_submit(env, envelope_path)
            daemon = _start_daemon(env, operator_id)
            status_path = harness_dir / "run" / "operator-status" / f"{operator_id}.json"
            deadline = time.monotonic() + min(cap_sec, 15)
            saw_running = False
            while time.monotonic() < deadline:
                snap = _read_json(status_path)
                if snap and str(snap.get("state") or "") == "running":
                    saw_running = True
                    break
                if daemon.poll() is not None:
                    break
                time.sleep(0.1)
            kill_sig = signal.SIGKILL if str(scen.get("kill_signal", "SIGTERM")).upper() in {"SIGKILL", "KILL", "9"} else signal.SIGTERM
            try:
                os.killpg(daemon.pid, kill_sig)
            except Exception:
                daemon.terminate()
            try:
                daemon.communicate(timeout=10)
            except Exception:
                try:
                    os.killpg(daemon.pid, signal.SIGKILL)
                except Exception:
                    daemon.kill()
            daemon_rc = daemon.returncode
            envelope = dict(envelope, _saw_running=saw_running)

        elif mode == "gate_replay":
            # Lane 3 gate/ledger-level classes: the scenario names a driver script
            # that exercises the real scheduler/dispatcher/ledger seams inside the
            # sandbox HARNESS_DIR and prints one JSON facts line on stdout. The
            # canonical fault is env SOLAR_GATE_LEDGER=0 — the pre-contract world —
            # so red proves the scenario discriminates the class, not the plumbing.
            driver = str(scen.get("driver") or "")
            driver_path = Path(driver)
            if not driver_path.is_absolute():
                driver_path = SCENARIOS_DIR / driver
            try:
                proc = subprocess.run(
                    [sys.executable, str(driver_path)],
                    env=env, capture_output=True, text=True, timeout=cap_sec,
                )
                driver_rc: Optional[int] = proc.returncode
                driver_stdout = proc.stdout or ""
                driver_stderr = proc.stderr or ""
            except subprocess.TimeoutExpired as exc:
                driver_rc = None
                driver_stdout = str(exc.stdout or "")
                driver_stderr = str(exc.stderr or "")
            driver_facts: Dict[str, Any] = {}
            for line in reversed(driver_stdout.strip().splitlines()):
                line = line.strip()
                if line.startswith("{"):
                    try:
                        parsed = json.loads(line)
                        if isinstance(parsed, dict):
                            driver_facts = parsed
                    except Exception:
                        pass
                    break
            facts = {
                "driver_rc": driver_rc,
                "driver_stderr_tail": driver_stderr[-800:],
                **driver_facts,
            }
            checks = _evaluate(scen.get("expect") or [], facts)
            passed = all(c["ok"] for c in checks) and bool(checks)
            return {
                "id": scen.get("id"),
                "class": scen.get("class"),
                "mode": mode,
                "red": red,
                "passed": passed,
                "facts": facts,
                "checks": checks,
                "harness_dir": str(harness_dir),
            }

        else:  # submit_once
            envelope_path = harness_dir / "envelope.json"
            envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
            submit_ok, submit_error, submit_stdout = _run_submit(env, envelope_path)
            if submit_ok:
                daemon_rc, daemon_timed_out, _ = _run_daemon_once(env, operator_id, cap_sec)

        facts = _collect_facts(
            harness_dir, operator_id, task_id, submit_ok, submit_error, daemon_rc, daemon_timed_out
        )
        if mode == "kill_mid_run":
            facts["saw_running"] = bool(envelope.get("_saw_running"))

        checks = _evaluate(scen.get("expect") or [], facts)
        passed = all(c["ok"] for c in checks) and bool(checks)
        return {
            "id": scen.get("id"),
            "class": scen.get("class"),
            "mode": mode,
            "red": red,
            "passed": passed,
            "facts": facts,
            "checks": checks,
            "harness_dir": str(harness_dir),
        }
    finally:
        if own_workdir and not keep:
            shutil.rmtree(harness_dir, ignore_errors=True)


def shlex_quote(s: str) -> str:
    import shlex
    return shlex.quote(s)


def load_scenario(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Lane 2 fake-operator scenario runner")
    parser.add_argument("scenario", help="Path to a *.scenario.json")
    parser.add_argument("--red", action="store_true", help="Inject the scenario's fault (red-before-green demonstration)")
    parser.add_argument("--json", action="store_true", help="Emit the full report as JSON")
    parser.add_argument("--keep", action="store_true", help="Keep the hermetic HARNESS_DIR for inspection")
    args = parser.parse_args(argv)

    scenario = load_scenario(Path(args.scenario))
    report = run_scenario(scenario, red=args.red, keep=args.keep)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        verdict = "PASS" if report["passed"] else "FAIL"
        mode = "RED" if args.red else "GREEN"
        print(f"[{mode}] {report['id']} (class {report['class']}) → {verdict}")
        for c in report["checks"]:
            mark = "ok" if c["ok"] else "XX"
            print(f"  [{mark}] {c['fact']} {c['op']} {c['value']!r} (actual={c['actual']!r})")
    # Exit 0 iff all expects satisfied. A discriminating scenario therefore exits
    # 0 in green mode and non-zero in red mode.
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
