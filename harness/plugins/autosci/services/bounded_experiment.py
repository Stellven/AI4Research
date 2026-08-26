"""Bounded local execution for hash-bound, human-approved experiments."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from ..operators.research_synthesis.base import ResearchOperatorError
except ImportError:  # direct autosci_bridge.py execution loads plugins/autosci as a package root
    from operators.research_synthesis.base import ResearchOperatorError


EXPERIMENT_EXECUTOR_SERVICE_ID = "autosci-production-bounded-local-experiment"
SERVICE_VERSION = "1.0.0"
EXECUTION_CONTRACT = "python_json_file.v1"
_OPERATORS = {
    ">": lambda actual, expected: actual > expected,
    ">=": lambda actual, expected: actual >= expected,
    "<": lambda actual, expected: actual < expected,
    "<=": lambda actual, expected: actual <= expected,
    "==": lambda actual, expected: actual == expected,
    "!=": lambda actual, expected: actual != expected,
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


@dataclass
class BoundedLocalExperimentExecutor:
    """Execute one exact, hash-bound Python runner and collect its JSON result."""

    workspace_root: Path
    service_id: str = EXPERIMENT_EXECUTOR_SERVICE_ID
    service_version: str = SERVICE_VERSION

    def __post_init__(self) -> None:
        self.workspace_root = Path(self.workspace_root).resolve()

    def _path(self, raw: Any, *, field: str) -> Path:
        text = str(raw or "").strip()
        if not text:
            raise ResearchOperatorError(f"{field} is required", error_type="invalid_input")
        candidate = Path(text)
        resolved = (candidate if candidate.is_absolute() else self.workspace_root / candidate).resolve()
        if not _is_under(resolved, self.workspace_root):
            raise ResearchOperatorError(f"{field} escapes the experiment workspace", error_type="safety_violation")
        return resolved

    def _criteria(self, plan: dict[str, Any], metrics: list[dict[str, Any]]) -> dict[str, bool]:
        values = {
            str(item.get("name") or ""): item.get("value")
            for item in metrics
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        }
        results: dict[str, bool] = {}
        for binding in plan.get("criteria_bindings") or []:
            if not isinstance(binding, dict):
                raise ResearchOperatorError("criteria_bindings entries must be objects", error_type="invalid_input")
            criterion = str(binding.get("criterion") or "").strip()
            metric = str(binding.get("metric") or "").strip()
            operator = str(binding.get("operator") or "").strip()
            expected = binding.get("value")
            actual = values.get(metric)
            if not criterion or metric not in values or operator not in _OPERATORS:
                raise ResearchOperatorError("A criterion is not bound to a measured metric", error_type="invalid_input")
            try:
                results[criterion] = bool(_OPERATORS[operator](actual, expected))
            except TypeError as exc:
                raise ResearchOperatorError(
                    f"Criterion {criterion!r} compares incompatible values",
                    error_type="invalid_input",
                ) from exc
        return results

    def __call__(
        self,
        *,
        plan: dict[str, Any],
        sandbox: dict[str, Any],
        timeout_seconds: int,
        max_output_bytes: int,
    ) -> dict[str, Any]:
        execution = plan.get("execution") if isinstance(plan.get("execution"), dict) else {}
        if execution.get("contract") != EXECUTION_CONTRACT:
            raise ResearchOperatorError(
                f"Experiment execution must declare contract={EXECUTION_CONTRACT}",
                error_type="invalid_input",
            )
        if str(sandbox.get("mode") or "") not in {"isolated", "process_restricted"}:
            raise ResearchOperatorError("Local experiment mode is not process restricted", error_type="safety_violation")
        if sandbox.get("network") is not False:
            raise ResearchOperatorError("Local experiment must deny network access", error_type="safety_violation")

        argv = execution.get("command_argv") if isinstance(execution.get("command_argv"), list) else []
        if len(argv) < 4 or str(argv[0]).lower() not in {"python", "python.exe"}:
            raise ResearchOperatorError(
                "Execution argv must be python, a runner, at least one input, and one result path",
                error_type="invalid_input",
            )
        runner = self._path(argv[1], field="execution runner")
        if runner.suffix.lower() != ".py" or not runner.is_file():
            raise ResearchOperatorError("Execution runner must be an existing Python file", error_type="invalid_input")
        result_path = self._path(execution.get("result_path"), field="execution result_path")
        argv_result = self._path(argv[-1], field="command result path")
        if result_path != argv_result:
            raise ResearchOperatorError("Command output is not the declared result path", error_type="safety_violation")

        write_roots = [self._path(item, field="sandbox write_scope") for item in sandbox.get("write_scope") or []]
        if not write_roots or not any(_is_under(result_path, root) for root in write_roots):
            raise ResearchOperatorError("Experiment result is outside the approved write scope", error_type="safety_violation")

        expected_runner_hash = str(execution.get("runner_sha256") or "").lower()
        if len(expected_runner_hash) != 64 or _sha256(runner) != expected_runner_hash:
            raise ResearchOperatorError("Execution runner does not match its approved hash", error_type="approval_mismatch")
        input_hashes = execution.get("input_sha256s") if isinstance(execution.get("input_sha256s"), dict) else {}
        resolved_args: list[str] = []
        for index, raw in enumerate(argv[2:-1], start=2):
            path = self._path(raw, field=f"command_argv[{index}]")
            if not path.is_file():
                raise ResearchOperatorError("An experiment input file is missing", error_type="missing_input")
            declared_hash = str(input_hashes.get(str(raw)) or "").lower()
            if len(declared_hash) != 64 or _sha256(path) != declared_hash:
                raise ResearchOperatorError("An experiment input does not match its approved hash", error_type="approval_mismatch")
            resolved_args.append(str(path))

        result_path.parent.mkdir(parents=True, exist_ok=True)
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "NO_PROXY": "*",
            "no_proxy": "*",
        }
        command = [sys.executable, str(runner), *resolved_args, str(result_path)]
        try:
            completed = subprocess.run(
                command,
                cwd=self.workspace_root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=max(1, int(timeout_seconds)),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ResearchOperatorError("Experiment process exceeded its timeout", error_type="timeout") from exc
        captured_bytes = len(completed.stdout.encode("utf-8")) + len(completed.stderr.encode("utf-8"))
        if captured_bytes > max(1, int(max_output_bytes)):
            raise ResearchOperatorError("Experiment process exceeded its output limit", error_type="resource_limit")
        if completed.returncode != 0:
            raise ResearchOperatorError(
                f"Experiment process failed with exit code {completed.returncode}",
                error_type="experiment_failed",
            )
        if not result_path.is_file():
            raise ResearchOperatorError("Experiment did not create its declared result", error_type="provider_contract")
        if result_path.stat().st_size > max(1, int(max_output_bytes)):
            raise ResearchOperatorError("Experiment result exceeded its output limit", error_type="resource_limit")
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ResearchOperatorError("Experiment result is not readable JSON", error_type="provider_contract") from exc
        raw = payload.get("outputs", {}).get("result") if isinstance(payload, dict) else None
        if not isinstance(raw, dict):
            raise ResearchOperatorError("Experiment JSON lacks outputs.result", error_type="provider_contract")
        if str(raw.get("experiment_id") or "") != str(plan.get("experiment_id") or ""):
            raise ResearchOperatorError("Experiment result identity does not match the approved plan", error_type="provider_contract")
        metrics = raw.get("metrics") if isinstance(raw.get("metrics"), list) else []
        if not metrics:
            raise ResearchOperatorError("Experiment result contains no measured metrics", error_type="provider_contract")
        criteria_results = self._criteria(plan, metrics)
        outcome = "supports" if criteria_results and all(criteria_results.values()) else "refutes" if criteria_results else str(raw.get("outcome") or "")
        if outcome not in {"supports", "partially_supports", "refutes", "inconclusive", "failed"}:
            raise ResearchOperatorError("Experiment result has an invalid outcome", error_type="provider_contract")
        result_hash = _sha256(result_path)
        evidence_ids = [str(item) for item in raw.get("evidence_ids") or [] if str(item).strip()]
        evidence_ids.append(f"sha256:{result_hash}")
        return {
            "outcome": outcome,
            "metrics": metrics,
            "evidence_ids": list(dict.fromkeys(evidence_ids)),
            "criteria_results": criteria_results,
            "limitations": [str(item) for item in payload.get("limitations") or [] if str(item).strip()],
            "runtime": {
                "exit_code": completed.returncode,
                "runner_sha256": expected_runner_hash,
                "result_sha256": result_hash,
            },
        }
