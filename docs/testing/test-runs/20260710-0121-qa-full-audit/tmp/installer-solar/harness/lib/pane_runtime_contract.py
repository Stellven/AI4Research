#!/usr/bin/env python3
"""pane_runtime_contract.py — pane send/observe/judge/evidence helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any


@dataclass
class SendResult:
    ok: bool
    dispatch_mode: str
    output: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class JudgeResult:
    status: str
    reasons: list[str]
    output: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def send_command(pane_id: str, command: str, timeout_s: int = 10) -> SendResult:
    if shutil.which("tmux"):
        result = subprocess.run(
            ["tmux", "send-keys", "-t", str(pane_id), command, "C-m"],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        return SendResult(
            ok=result.returncode == 0,
            dispatch_mode="tmux",
            output=result.stdout.strip(),
            error=result.stderr.strip(),
        )
    result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout_s)
    return SendResult(
        ok=result.returncode == 0,
        dispatch_mode="stdout_fallback",
        output=(result.stdout or "").strip(),
        error=(result.stderr or "").strip(),
    )


def observe_output(pane_id: str, lines: int = 50, timeout_s: int = 10) -> str:
    if not shutil.which("tmux"):
        return ""
    result = subprocess.run(
        ["tmux", "capture-pane", "-p", "-t", str(pane_id), f"-S-{int(lines)}"],
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )
    return (result.stdout or "").strip()


def _pass_conditions(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    conditions = manifest.get("verification", {}).get("pass_conditions", []) or []
    normalized: list[dict[str, Any]] = []
    success_artifact = manifest.get("runtime_preferences", {}).get("success_artifact")
    for condition in conditions:
        if isinstance(condition, dict):
            normalized.append(condition)
        elif condition == "artifact_present" and success_artifact:
            normalized.append({"kind": "artifact_present", "path": success_artifact})
        elif condition == "exit_code_zero":
            normalized.append({"kind": "exit_code_zero"})
        elif condition == "pattern_match":
            normalized.append({"kind": "pattern_match", "pattern": "."})
        elif condition == "no_error_pattern":
            normalized.append({"kind": "no_error_pattern", "pattern": r"(?i)(error|failed|traceback)"})
    return normalized


def judge_result(output: str, manifest: dict[str, Any], artifacts_dir: str | Path = ".") -> JudgeResult:
    root = Path(artifacts_dir)
    reasons: list[str] = []
    blocked_patterns = [
        r"(?i)\bblocked\b",
        r"(?i)\bwaiting_human\b",
        r"(?i)\bno module\b",
    ]
    for pattern in blocked_patterns:
        if re.search(pattern, output or ""):
            return JudgeResult(status="BLOCKED", reasons=[f"blocked pattern matched: {pattern}"], output=output)

    success = True
    for condition in _pass_conditions(manifest):
        kind = condition.get("kind")
        if kind == "artifact_present":
            target = Path(str(condition.get("path") or ""))
            if not target.is_absolute():
                target = root / target
            if not target.exists() or target.stat().st_size == 0:
                success = False
                reasons.append(f"artifact missing: {target}")
        elif kind == "exit_code_zero":
            if "exit_code=0" not in (output or ""):
                success = False
                reasons.append("exit_code_zero not observed")
        elif kind == "pattern_match":
            pattern = str(condition.get("pattern") or "")
            if pattern and not re.search(pattern, output or ""):
                success = False
                reasons.append(f"pattern mismatch: {pattern}")
        elif kind == "no_error_pattern":
            pattern = str(condition.get("pattern") or r"(?i)(error|failed|traceback)")
            if re.search(pattern, output or ""):
                success = False
                reasons.append(f"error pattern present: {pattern}")
    if success and _pass_conditions(manifest):
        return JudgeResult(status="SUCCESS", reasons=["all pass conditions satisfied"], output=output)
    if re.search(r"(?i)(error|failed|traceback)", output or ""):
        return JudgeResult(status="FAILURE", reasons=reasons or ["error pattern detected"], output=output)
    return JudgeResult(status="PENDING", reasons=reasons or ["waiting for more evidence"], output=output)


def build_capsule_evidence(judge_result: JudgeResult) -> dict[str, Any]:
    return {
        "status": judge_result.status,
        "reasons": list(judge_result.reasons),
        "output": judge_result.output,
        "observed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def write_evidence(capsule_id: str, judge_result: JudgeResult, artifacts_dir: str | Path) -> Path:
    target_dir = Path(artifacts_dir) / ".capsule-evidence" / str(capsule_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    target.write_text(json.dumps(build_capsule_evidence(judge_result), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target
