#!/usr/bin/env python3
"""Run an AutoSci skill and hand its runtime evidence to the AutoSci bridge.

The bridge (``autosci_bridge.py``) verifies runtime evidence and converts it to
typed Solar evidence; it does not execute anything. AutoSci's real executor is
an agent running its skills (``$ideate``, ``$exp-design``, ``$exp-run``,
``$exp-status``, ``$exp-eval``, ``$paper-draft``). Nothing occupied that seam,
which is why Part B was reimplemented as Solar command operators instead of
using the bridge that already existed.

This executor is that seam. For one stage it:

1. runs the stage's AutoSci skill through the Codex CLI inside the configured
   AutoSci checkout,
2. writes a runtime record with the real exit code, command, streams, and any
   result path the skill produced,
3. rewrites the operator envelope so ``inputs.runtime_evidence`` points at that
   record,
4. invokes the matching bridge action and returns its typed evidence.

It never synthesises a runtime record. A failed or unavailable skill run is
recorded with its real non-zero exit code so the bridge fails closed, which is
the behaviour the governance depends on now that no approval node precedes
execution.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BRIDGE = Path(__file__).resolve().parent / "autosci_bridge.py"

# stage -> (AutoSci skill invocation, bridge action)
STAGES: dict[str, tuple[str, str]] = {
    "idea_generation": ("$ideate", "generate_ideas"),
    "idea_evaluation": ("$ideate", "evaluate_ideas"),
    "experiment_design": ("$exp-design", "design_experiment"),
    "experiment_run": ("$exp-run", "run_experiment"),
    "experiment_monitor": ("$exp-status", "monitor_experiment"),
    "claim_verification": ("$exp-eval", "verify_claim"),
    "report_delivery": ("$paper-draft", "write_report"),
}

# Never forward an inherited provider credential into the skill subprocess; the
# Codex CLI authenticates from its own CODEX_HOME.
SECRET_ENV_KEYS = {
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
}


class ExecutorError(RuntimeError):
    """The executor failed closed before producing runtime evidence."""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _autosci_home() -> Path:
    raw = str(os.environ.get("SOLAR_AUTOSCI_HOME") or "").strip()
    if not raw:
        raise ExecutorError(
            "SOLAR_AUTOSCI_HOME is not set; the AutoSci checkout location is "
            "machine-specific and has no safe default"
        )
    home = Path(raw).expanduser()
    if not home.is_dir():
        raise ExecutorError(f"SOLAR_AUTOSCI_HOME is not a directory: {home}")
    return home.resolve()


def _skill_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key not in SECRET_ENV_KEYS}
    codex_home = str(os.environ.get("SOLAR_CODEX_SOURCE_HOME") or "").strip()
    if codex_home:
        env["CODEX_HOME"] = codex_home
    return env


def run_skill(
    *,
    stage: str,
    request: str,
    record_path: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Run the stage's AutoSci skill and write a truthful runtime record."""
    skill, _action = STAGES[stage]
    home = _autosci_home()
    binary = shutil.which(str(os.environ.get("SOLAR_CODEX_BINARY") or "codex"))
    if not binary:
        raise ExecutorError("Codex CLI is unavailable on PATH")
    model = str(os.environ.get("SOLAR_AUTOSCI_SKILL_MODEL") or "").strip()

    prompt = f"{skill} {request}".strip()
    argv = [binary, "exec", "--skip-git-repo-check"]
    if model:
        argv += ["--model", model]
    argv.append(prompt)

    started_at = _now()
    try:
        proc = subprocess.run(
            argv,
            cwd=home,
            env=_skill_env(),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        exit_code, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        exit_code = 124
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr if isinstance(exc.stderr, str) else "") + f"\ntimed out after {timeout_seconds}s"
        timed_out = True

    record_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path = record_path.with_suffix(".stdout.log")
    stderr_path = record_path.with_suffix(".stderr.log")
    stdout_path.write_text(stdout or "", encoding="utf-8")
    stderr_path.write_text(stderr or "", encoding="utf-8")

    record = {
        "schema": "solar.autosci_skill_runtime.v1",
        "stage": stage,
        "skill": skill,
        "autosci_home": str(home),
        "command_run": " ".join(argv[:-1] + ["<prompt>"]),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "started_at": started_at,
        "finished_at": _now(),
        "model": model or "codex-default",
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "logs": [line for line in (stdout or "").splitlines()[-40:] if line.strip()],
        "credential_contents_recorded": False,
    }
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record


def invoke_bridge(*, action: str, envelope_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BRIDGE), "run", "--action", action, "--envelope", str(envelope_path)],
        capture_output=True,
        text=True,
        check=False,
    )


def execute(args: argparse.Namespace) -> dict[str, Any]:
    stage = args.stage
    if stage not in STAGES:
        raise ExecutorError(f"unknown stage: {stage}")
    _skill, action = STAGES[stage]

    envelope_path = Path(args.envelope).expanduser().resolve(strict=True)
    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    if not isinstance(envelope, dict):
        raise ExecutorError("operator envelope must be a JSON object")

    work_dir = Path(args.work_dir).expanduser() if args.work_dir else envelope_path.parent
    run_id = uuid.uuid4().hex[:12]
    record_path = work_dir / "autosci-runtime" / f"{stage}-{run_id}.runtime.json"

    request = str(args.request or (envelope.get("inputs") or {}).get("request") or "").strip()
    record = run_skill(
        stage=stage,
        request=request,
        record_path=record_path,
        timeout_seconds=args.timeout_seconds,
    )

    # Point the bridge at the record we just produced. The bridge decides
    # whether the run counts; the executor never asserts success on its behalf.
    inputs = dict(envelope.get("inputs") or {})
    existing = inputs.get("runtime_evidence")
    entries = list(existing) if isinstance(existing, list) else []
    entries.append({"path": str(record_path), "exists": record_path.is_file()})
    inputs["runtime_evidence"] = entries
    envelope["inputs"] = inputs

    augmented = work_dir / "autosci-runtime" / f"{stage}-{run_id}.envelope.json"
    augmented.parent.mkdir(parents=True, exist_ok=True)
    augmented.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    bridged = invoke_bridge(action=action, envelope_path=augmented)
    try:
        bridge_payload = json.loads(bridged.stdout or "{}")
    except json.JSONDecodeError:
        bridge_payload = {"ok": False, "reason": "bridge_output_not_json", "stdout": bridged.stdout[-2000:]}

    return {
        "ok": bridged.returncode == 0,
        "stage": stage,
        "bridge_action": action,
        "skill_exit_code": record["exit_code"],
        "runtime_record": str(record_path),
        "envelope": str(augmented),
        "bridge_returncode": bridged.returncode,
        "bridge": bridge_payload,
        "bridge_stderr": (bridged.stderr or "")[-2000:],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run an AutoSci skill and convert its runtime evidence through the AutoSci bridge",
        epilog="stages: " + ", ".join(sorted(STAGES)),
    )
    parser.add_argument("--stage", required=True, choices=sorted(STAGES))
    parser.add_argument("--envelope", required=True)
    parser.add_argument("--request", default="")
    parser.add_argument("--work-dir", default="")
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        payload = execute(args)
    except (ExecutorError, OSError, ValueError) as exc:
        print(
            json.dumps({"ok": False, "error_type": type(exc).__name__, "error": str(exc)}, indent=2),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
