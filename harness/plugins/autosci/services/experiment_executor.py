"""A real, sandboxed experiment executor for AutoSci's run_experiment.

`scientific_lifecycle.action.experiment.run_experiment` is the registered
implementation behind the ScientificExperimentRunner logical operator. It
verifies a hash-bound approval and then requires an `experiment_executor`
service; none existed anywhere in the tree, so that operator could only fail
closed. This module is that executor.

It executes exactly one allowlisted, digest-pinned runner script under
`unshare -Urn` (fresh user and network namespaces, networking disabled) with
a minimal environment, honours the plan's timeout and output bound, and
converts the runner's raw JSON into the genuine outcome vocabulary
(supports | refutes | inconclusive | failed). It never invents a result: the
outcome is computed from the raw evidence the sandboxed process wrote, and a
missing or unparseable raw result is `failed`, not `inconclusive`.
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from ..operators.research_synthesis.base import ResearchOperatorError
except ImportError:  # direct-module execution paths used by the adapter
    try:
        from operators.research_synthesis.base import ResearchOperatorError
    except ImportError:
        from harness.plugins.autosci.operators.research_synthesis.base import (
            ResearchOperatorError,
        )

EXECUTOR_SERVICE_ID = "autosci-sandboxed-benchmark-executor"
EXECUTOR_SERVICE_VERSION = "1.0.0"
_ALLOWED_SANDBOX_MODES = {"isolated", "container", "process_restricted"}


@dataclass
class SandboxedBenchmarkExecutor:
    """Execute the digest-pinned benchmark runner inside a no-network sandbox."""

    work_dir: Path
    runner: Path
    runner_sha256: str
    handoff_path: Path
    plan_path: Path
    raw_output_path: Path
    stdout_path: Path
    stderr_path: Path
    sandbox_home: Path
    environment_path: str = ""
    last_execution: dict[str, Any] = field(default_factory=dict, init=False, repr=False)

    service_id: str = EXECUTOR_SERVICE_ID
    service_version: str = EXECUTOR_SERVICE_VERSION

    def __call__(
        self,
        *,
        plan: dict[str, Any],
        sandbox: dict[str, Any],
        timeout_seconds: int,
        max_output_bytes: int,
    ) -> dict[str, Any]:
        import hashlib
        import os
        import time

        if str(sandbox.get("mode") or "") not in _ALLOWED_SANDBOX_MODES or bool(sandbox.get("network", False)):
            raise ResearchOperatorError(
                "experiment sandbox must be an isolated no-network mode",
                error_type="safety_violation",
            )
        runner = Path(self.runner).resolve(strict=True)
        actual_runner_sha = hashlib.sha256(runner.read_bytes()).hexdigest()
        if actual_runner_sha != str(self.runner_sha256 or "").lower():
            # The approval pinned specific runner bytes; different bytes mean
            # the approved experiment is not the one about to execute.
            raise ResearchOperatorError(
                "experiment runner bytes do not match the approved digest",
                error_type="approval_mismatch",
            )
        timeout = max(1, min(int(timeout_seconds or 0) or 60, 60))
        command = [
            "unshare", "-Urn", sys.executable, str(runner),
            "--work-dir", str(self.work_dir),
            "--handoff", str(self.handoff_path),
            "--plan", str(self.plan_path),
            "--output", str(self.raw_output_path),
        ]
        env = {
            "PATH": self.environment_path or os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "HOME": str(self.sandbox_home),
        }
        self.sandbox_home.mkdir(parents=True, exist_ok=True)
        started_ns = time.monotonic_ns()
        try:
            completed = subprocess.run(
                command,
                cwd=self.stdout_path.parent,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ResearchOperatorError(
                f"experiment timed out after {timeout}s",
                error_type="experiment_timeout",
            ) from exc
        ended_ns = time.monotonic_ns()
        bound = max(1, int(max_output_bytes or 1_000_000))
        stdout_text = (completed.stdout or "")[:bound]
        stderr_text = (completed.stderr or "")[:bound]
        self.stdout_path.write_text(stdout_text, encoding="utf-8")
        self.stderr_path.write_text(
            json.dumps(
                {
                    "schema": "solar.fixed_research.command_stream.v1",
                    "stream": "stderr",
                    "encoding": "utf-8",
                    "bytes": len(stderr_text.encode("utf-8")),
                    "content": stderr_text,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        execution = {
            "command": command,
            "exit_code": int(completed.returncode),
            "duration_ms": round((ended_ns - started_ns) / 1_000_000, 3),
            "runner_sha256": actual_runner_sha,
            "timeout_seconds": timeout,
            "max_output_bytes": bound,
        }
        self.last_execution = execution

        if not self.raw_output_path.is_file():
            return {
                "outcome": "failed",
                "metrics": [{"name": "exit_code", "value": int(completed.returncode)}],
                "evidence_ids": ["benchmark-stdout", "benchmark-stderr"],
                "criteria_results": {},
                "limitations": ["The sandboxed benchmark produced no raw evidence; nothing was measured."],
                "execution": execution,
            }
        try:
            raw = json.loads(self.raw_output_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {
                "outcome": "failed",
                "metrics": [{"name": "exit_code", "value": int(completed.returncode)}],
                "evidence_ids": ["benchmark-raw", "benchmark-stdout", "benchmark-stderr"],
                "criteria_results": {},
                "limitations": ["The sandboxed benchmark wrote unparseable raw evidence."],
                "execution": execution,
            }
        metrics = raw.get("metrics") if isinstance(raw.get("metrics"), dict) else {}
        checks = [item for item in raw.get("checks") or [] if isinstance(item, dict)]
        claim_checks = [item for item in raw.get("claim_checks") or [] if isinstance(item, dict)]
        lineage_intact = bool(checks) and all(bool(item.get("passed")) for item in checks)
        claims_total = int(metrics.get("claims_total") or 0)
        claims_refuted = int(metrics.get("claims_refuted") or 0)

        if completed.returncode == 0 and raw.get("passed") is True and lineage_intact and claims_total >= 1:
            outcome = "supports"
        elif lineage_intact and claims_total >= 1 and claims_refuted > 0:
            outcome = "refutes"
        elif checks and not lineage_intact:
            outcome = "refutes"
        elif claims_total == 0:
            # Everything measurable was measured and nothing failed, but the
            # hypothesis's claim set was empty: nothing to support or refute.
            outcome = "inconclusive"
        else:
            outcome = "failed"

        criteria_results: dict[str, bool] = {
            "lineage_digests_match": lineage_intact,
            "exit_code_zero": completed.returncode == 0,
            "no_claim_refuted": claims_total >= 1 and claims_refuted == 0,
        }
        for item in claim_checks:
            claim_id = str(item.get("claim_id") or "").strip()
            if claim_id:
                criteria_results[f"{claim_id}:grounding_replicated"] = item.get("outcome") == "supported"

        return {
            "outcome": outcome,
            "metrics": [
                {"name": str(key), "value": metrics.get(key)}
                for key in sorted(metrics)
            ] or [{"name": "exit_code", "value": int(completed.returncode)}],
            "evidence_ids": [
                "benchmark-raw",
                "benchmark-stdout",
                "benchmark-stderr",
                *[str(item.get("claim_id") or "") for item in claim_checks if str(item.get("claim_id") or "")],
            ],
            "criteria_results": criteria_results,
            "limitations": [
                f"Tested: {raw.get('tested') or 'retained-artifact digest lineage'}.",
                f"Not tested: {raw.get('not_tested') or 'external scientific validity of the sources'}.",
            ],
            "execution": execution,
        }
