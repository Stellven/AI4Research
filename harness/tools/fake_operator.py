#!/usr/bin/env python3
"""fake_operator.py — deterministic operator worker for the Lane 2 scenario harness.

This is a REAL operator backend, not a mock. It is executed by ``operatord`` exactly
like a live LLM operator would be: operatord resolves an operator whose ``backend`` is
``command`` (or whose task envelope carries a ``command``), materializes the envelope
context into the environment (``SOLAR_OPERATOR_ENVELOPE_JSON``, ``TASK_DIR``, ``NODE_ID``,
``SID``, ``RESULT_PATH``, ``HANDOFF``, ``HARNESS_DIR``, ``SPRINTS_DIR`` …), and runs this
script as a subprocess. Everything downstream — the lease lifecycle, ``result.json``, the
heartbeat, the pm-dispatch completion hook, failure flow-control — is the real runtime.

The script produces *scripted* behavior instead of calling a model. The behavior for a
task is read (in priority order) from:

1. the task envelope's ``fake_behavior`` key (``SOLAR_OPERATOR_ENVELOPE_JSON`` → JSON), or
2. a scenario file at ``$SOLAR_FAKE_OPERATOR_SCENARIO``, keyed by ``NODE_ID`` then ``role``
   then ``operator_id`` then ``"*"``.

A behavior object may contain:

    delay_sec        float   sleep before doing anything (exercise timeouts / bounded waits)
    hang             bool    sleep for an effectively-unbounded time (until killed)
    stdout_lines     [str]   lines to print to stdout (drives operatord flow-control, e.g.
                             an auth-absent or quota line) — printed before exiting
    artifacts        [ {path, content} ]  files to write; ``path`` may be absolute or
                             relative to ``$SOLAR_FAKE_ARTIFACT_ROOT`` (default: TASK_DIR)
    write_pm_result  bool    write a minimal PM-result markdown at ``$RESULT_PATH`` (so the
                             operatord pm-dispatch completion hook can pass)
    write_handoff    bool    write a minimal handoff markdown at ``$HANDOFF``
    eval_verdict     {status, verdict, ...}  write an eval sidecar JSON next to result.json
                             and (if ``$SOLAR_FAKE_EVAL_SIDECAR`` is set) at that path too
    exit_code        int     process exit code (operatord maps 0→completed, nonzero→failed)

The worker is fully deterministic: given the same envelope + scenario it does the same thing
and never touches the network or a model. It is safe to run in CI with no credentials.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional


def _log(msg: str) -> None:
    # Goes to operatord's captured output.log; prefix keeps it greppable.
    print(f"[fake-operator] {msg}", flush=True)


def _read_envelope() -> Dict[str, Any]:
    env_path = os.environ.get("SOLAR_OPERATOR_ENVELOPE_JSON", "").strip()
    if env_path and Path(env_path).exists():
        try:
            return json.loads(Path(env_path).read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - defensive
            _log(f"could not read envelope {env_path}: {exc}")
    return {}


def _behavior_from_scenario(envelope: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    scen_path = os.environ.get("SOLAR_FAKE_OPERATOR_SCENARIO", "").strip()
    if not scen_path or not Path(scen_path).exists():
        return None
    try:
        scenario = json.loads(Path(scen_path).read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        _log(f"could not read scenario {scen_path}: {exc}")
        return None
    behaviors = scenario.get("behaviors") or {}
    if not isinstance(behaviors, dict):
        return None
    keys = [
        os.environ.get("NODE_ID", "").strip(),
        str(envelope.get("node_id") or "").strip(),
        str(envelope.get("role") or "").strip(),
        str(envelope.get("dispatch_role") or "").strip(),
        str(envelope.get("operator_id") or "").strip(),
        "*",
    ]
    for key in keys:
        if key and key in behaviors:
            return dict(behaviors[key])
    return None


def _resolve_behavior() -> Dict[str, Any]:
    envelope = _read_envelope()
    behavior = envelope.get("fake_behavior")
    if isinstance(behavior, dict):
        return dict(behavior)
    scen_behavior = _behavior_from_scenario(envelope)
    if isinstance(scen_behavior, dict):
        return scen_behavior
    # Default: an honest no-op success so the daemon lifecycle can be exercised.
    return {"exit_code": 0, "stdout_lines": ["fake-operator default completion"]}


def _artifact_root() -> Path:
    root = os.environ.get("SOLAR_FAKE_ARTIFACT_ROOT", "").strip()
    if root:
        return Path(root)
    task_dir = os.environ.get("TASK_DIR", "").strip()
    if task_dir:
        return Path(task_dir)
    return Path.cwd()


def _write_artifacts(behavior: Dict[str, Any]) -> None:
    artifacts = behavior.get("artifacts") or []
    if not isinstance(artifacts, list):
        return
    root = _artifact_root()
    for entry in artifacts:
        if not isinstance(entry, dict):
            continue
        rel = str(entry.get("path") or "").strip()
        if not rel:
            continue
        target = Path(rel)
        if not target.is_absolute():
            target = root / target
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(entry.get("content", "")), encoding="utf-8")
        _log(f"wrote artifact {target}")


def _write_pm_result(behavior: Dict[str, Any]) -> None:
    if not behavior.get("write_pm_result"):
        return
    result_path = os.environ.get("RESULT_PATH") or os.environ.get("PM_RESULT_PATH") or ""
    if not result_path:
        _log("write_pm_result requested but no RESULT_PATH in env")
        return
    path = Path(result_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = str(
        behavior.get("pm_result_body")
        or "# PM Task Result\n\n## 已完成\n- fake operator produced a deterministic result\n"
    )
    path.write_text(body, encoding="utf-8")
    _log(f"wrote pm result {path}")


def _write_handoff(behavior: Dict[str, Any]) -> None:
    if not behavior.get("write_handoff"):
        return
    handoff = os.environ.get("HANDOFF", "").strip()
    if not handoff:
        _log("write_handoff requested but no HANDOFF in env")
        return
    path = Path(handoff)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(behavior.get("handoff_body") or "# Handoff\n\nfake operator handoff\n"), encoding="utf-8")
    _log(f"wrote handoff {path}")


def _write_eval_sidecar(behavior: Dict[str, Any]) -> None:
    verdict = behavior.get("eval_verdict")
    if not isinstance(verdict, dict):
        return
    payload = dict(verdict)
    payload.setdefault("author", os.environ.get("TASK_ID", "fake-operator"))
    payload.setdefault("evaluated_at", "scenario")
    task_dir = os.environ.get("TASK_DIR", "").strip()
    if task_dir:
        sidecar = Path(task_dir) / "eval.json"
        sidecar.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        _log(f"wrote eval sidecar {sidecar}")
    explicit = os.environ.get("SOLAR_FAKE_EVAL_SIDECAR", "").strip()
    if explicit:
        p = Path(explicit)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        _log(f"wrote eval sidecar {p}")


def main() -> int:
    behavior = _resolve_behavior()
    _log(
        "start task_id=%s node_id=%s"
        % (os.environ.get("TASK_ID", "?"), os.environ.get("NODE_ID", "?"))
    )

    delay = float(behavior.get("delay_sec", 0) or 0)
    if behavior.get("hang"):
        # Effectively unbounded: rely on operatord's task timeout / SIGTERM to stop us.
        # A finite very-large sleep keeps the process from becoming a true zombie if the
        # daemon dies without signalling.
        _log("hang requested — sleeping until killed")
        try:
            time.sleep(float(behavior.get("hang_seconds", 3600)))
        except KeyboardInterrupt:  # pragma: no cover
            return 143
        return int(behavior.get("exit_code", 0) or 0)

    if delay > 0:
        _log(f"sleeping {delay}s")
        time.sleep(delay)

    _write_artifacts(behavior)
    _write_pm_result(behavior)
    _write_handoff(behavior)
    _write_eval_sidecar(behavior)

    for line in behavior.get("stdout_lines") or []:
        print(str(line), flush=True)

    exit_code = int(behavior.get("exit_code", 0) or 0)
    _log(f"exit {exit_code}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
