"""Terminal-Bench 2.0 adapter implementing the BenchmarkAdapter Protocol.

S03 N3: TerminalBench20Adapter with doctor/list_tasks/plan/run/parse_result.
Uses harbor_adapter for detection and command construction.
Registered via @registry.register decorator at module bottom.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import harbor_adapter
from . import registry
from .schemas import (
    AGENT_ALLOWLIST,
    DEFAULT_DATASET,
    SAFE_TASKS,
    SCHEMA_VERSION,
    VALID_ENVS,
    BenchmarkDoctor,
    BenchmarkRunPlan,
    BenchmarkRunRequest,
    BenchmarkRunResult,
    BenchmarkTask,
    new_run_id,
)

_BENCHMARK_NAME = "terminal-bench"
_BENCHMARK_VERSION = "2.0"
_ADAPTER_NAME = "harbor"


class TerminalBench20Adapter:
    """Adapter for terminal-bench@2.0 benchmark via Harbor CLI."""

    id: str = f"{_BENCHMARK_NAME}@{_BENCHMARK_VERSION}"
    version: str = _BENCHMARK_VERSION

    def _doctor_for_agent(self, agent: str | None = None) -> BenchmarkDoctor:
        """Check prerequisites: Harbor, Docker, dataset, agent API keys.

        Never raises — returns BenchmarkDoctor with missing_prereqs populated
        when prerequisites are absent. Never returns a false positive (empty
        missing_prereqs when things are actually missing).
        """
        missing: list[str] = []

        harbor_available, harbor_kind = harbor_adapter.detect()
        if not harbor_available:
            missing.append("harbor_cli")

        docker_ok = harbor_adapter.docker_available()
        if not docker_ok:
            missing.append("docker")

        dataset_ok = harbor_adapter.probe_dataset(self.id)
        if not dataset_ok:
            missing.append("dataset_registry")

        agents_known: list[str] = []
        agents_to_check = (agent,) if agent else AGENT_ALLOWLIST
        auth_notes: list[str] = []
        for candidate in agents_to_check:
            status, evidence = harbor_adapter.agent_auth_status(candidate)
            auth_notes.append(f"{candidate}:{status}:{evidence}")
            if status != "missing":
                agents_known.append(candidate)
            else:
                missing.append(f"agent_auth:{candidate}")

        notes_parts: list[str] = []
        if harbor_available:
            notes_parts.append(f"harbor={harbor_kind}")
        else:
            notes_parts.append("harbor=missing")
        notes_parts.append(f"docker={'ok' if docker_ok else 'missing'}")
        notes_parts.append(f"dataset={'ok' if dataset_ok else 'unknown'}")
        notes_parts.append(f"auth={','.join(auth_notes) or 'N/A'}")
        notes = "; ".join(notes_parts)

        return BenchmarkDoctor(
            adapter_id=self.id,
            harbor_available=harbor_available,
            harbor_kind=harbor_kind,
            docker_available=docker_ok,
            dataset_known=dataset_ok,
            agents_known=tuple(agents_known),
            missing_prereqs=tuple(sorted(set(missing))),
            notes=notes,
        )

    def doctor(self) -> BenchmarkDoctor:
        """Check global prerequisites without requiring API-key-only auth."""
        return self._doctor_for_agent()

    def list_tasks(self) -> list[BenchmarkTask]:
        """Return known benchmark tasks from Harbor registry, with safe smoke tasks first."""
        registry_tasks = harbor_adapter.list_dataset_tasks(self.id)
        if registry_tasks:
            ordered = [
                task for task in SAFE_TASKS if task in registry_tasks
            ] + [
                task for task in registry_tasks if task not in SAFE_TASKS
            ]
        else:
            ordered = list(SAFE_TASKS)
        return [
            BenchmarkTask(
                id=t,
                title=t.replace("-", " ").title(),
                tags=["safe", "smoke"] if t in SAFE_TASKS else ["registry"],
            )
            for t in ordered
        ]

    def plan(self, req: BenchmarkRunRequest) -> BenchmarkRunPlan:
        """Build the Harbor command argv without executing it.

        Populates env_overrides with key presence markers (never values).
        """
        argv = harbor_adapter.build_argv(req)
        env_overrides: dict[str, str] = {}
        key_name = harbor_adapter.api_key_env_for(req.agent)
        if key_name and harbor_adapter.probe_api_key(req.agent):
            env_overrides[key_name] = "present"
        auth_status, auth_evidence = harbor_adapter.agent_auth_status(req.agent)
        if auth_status != "missing":
            env_overrides[f"auth:{req.agent}"] = auth_status
            env_overrides[f"auth_evidence:{req.agent}"] = auth_evidence
        return BenchmarkRunPlan(
            command=tuple(argv),
            env_overrides=env_overrides,
            notes=f"Harbor command for {req.agent}/{req.model} on {self.id}",
        )

    def run(self, req: BenchmarkRunRequest) -> BenchmarkRunResult:
        """Execute benchmark run with validation gate state machine.

        State machine per design §4.5:
          INIT → validate request fields
          DOCTOR → check prereqs; missing → PENDING
          PLAN → build argv; dry_run → OK (no exec)
          EXEC → not yet implemented (returns pending for non-dry-run)

        Validation gates that downgrade to error (never silent ok):
          - agent not in allowlist → error
          - full=True without confirm_budget → error
          - cloud env with missing key → pending
        """
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        run_id = new_run_id()
        base_result = self._base_result(req, run_id, now)

        # INIT: validate agent
        if req.agent not in AGENT_ALLOWLIST:
            return self._error_result(
                base_result, ("agent_not_in_allowlist",),
                f"Agent {req.agent!r} not in allowlist {list(AGENT_ALLOWLIST)}",
            )

        # INIT: validate full + confirm_budget
        if req.full and not req.confirm_budget:
            return self._error_result(
                base_result, ("full_run_without_confirm_budget",),
                "Full run requested without --confirm-budget flag",
            )

        # INIT: validate env
        if req.env and req.env not in VALID_ENVS:
            return self._error_result(
                base_result, ("invalid_env",),
                f"Env {req.env!r} not in {list(VALID_ENVS)}",
            )

        # INIT: validate requested tasks against local Harbor registry when available.
        registry_tasks = set(harbor_adapter.list_dataset_tasks(self.id))
        if registry_tasks and req.tasks:
            unknown_tasks = tuple(task for task in req.tasks if task not in registry_tasks)
            if unknown_tasks:
                return self._error_result(
                    base_result,
                    ("unknown_task",),
                    f"Unknown task(s) for {self.id}: {', '.join(unknown_tasks)}",
                )

        # DOCTOR: check prerequisites
        doc = self._doctor_for_agent(req.agent)
        if doc.missing_prereqs:
            return self._pending_result(
                base_result,
                doc.missing_prereqs,
                f"Missing prerequisites: {', '.join(doc.missing_prereqs)}",
            )

        # CLOUD ENV KEY CHECK
        if req.env in ("daytona", "modal", "e2b", "runloop"):
            key_name = harbor_adapter.api_key_env_for(req.agent)
            if key_name and not harbor_adapter.probe_api_key(req.agent):
                return self._pending_result(
                    base_result,
                    (f"cloud_env_key:{req.agent}",),
                    f"Cloud env {req.env!r} selected but API key for {req.agent} missing",
                )

        if req.agent in {"host-claude-code", "solar-harness-agent"} and not req.dry_run:
            installer = (
                harbor_adapter.ensure_solar_harness_agent_installed
                if req.agent == "solar-harness-agent"
                else harbor_adapter.ensure_host_claude_agent_installed
            )
            installed, evidence = installer()
            if not installed:
                return self._error_result(
                    base_result,
                    (f"{req.agent.replace('-', '_')}_install_failed",),
                    evidence,
                )

        run_dir = None
        plan_req = req
        if not req.dry_run:
            from .reports import _reports_base

            run_dir = _reports_base() / run_id
            harbor_jobs_dir = run_dir / "harbor-jobs"
            plan_req = replace(req, run_dir=str(harbor_jobs_dir))

        # PLAN
        plan = self.plan(plan_req)

        # DRY RUN → return ok with command visible, no execution
        if req.dry_run:
            return BenchmarkRunResult(
                schema_version=SCHEMA_VERSION,
                run_id=run_id,
                benchmark=_BENCHMARK_NAME,
                benchmark_version=_BENCHMARK_VERSION,
                dataset=self.id,
                adapter=_ADAPTER_NAME,
                agent=req.agent,
                model=req.model,
                env=req.env,
                tasks_requested=req.tasks,
                tasks_completed=(),
                score=None,
                pass_count=0,
                fail_count=0,
                pending_count=len(req.tasks),
                started_at=now,
                completed_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                duration_sec=0.0,
                command=plan.command,
                exit_code=None,
                stdout_path=None,
                stderr_path=None,
                artifacts=(),
                verdict="ok",
                failure_modes=(),
                limitations=("dry_run: no actual execution",),
            )

        # EXEC: delegate to Harbor and capture raw artifacts. Harbor owns scoring.
        assert run_dir is not None
        run_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = run_dir / "stdout.log"
        stderr_path = run_dir / "stderr.log"
        started = time.monotonic()
        try:
            proc = subprocess.run(
                list(plan.command),
                cwd=str(run_dir),
                text=True,
                capture_output=True,
                timeout=int(os.environ.get("SOLAR_BENCH_TIMEOUT_SEC", "7200")),
            )
            stdout = proc.stdout
            stderr = proc.stderr
            return_code = proc.returncode
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or f"Timed out after {exc.timeout}s"
            return_code = 124
        duration = time.monotonic() - started
        stdout_path.write_text(stdout, encoding="utf-8")
        stderr_path.write_text(stderr, encoding="utf-8")

        verdict = "ok" if return_code == 0 else "error"
        harbor_score, completed_count, error_count, harbor_result_path = (
            self._parse_harbor_job_summary(run_dir / "harbor-jobs")
        )
        completed_tasks = req.tasks if verdict == "ok" else ()
        if harbor_score is not None and completed_count is not None:
            pass_count = round(harbor_score * completed_count)
            fail_count = max(completed_count - pass_count, 0)
            if error_count:
                fail_count += error_count
        else:
            pass_count = completed_count if completed_count is not None else len(completed_tasks)
            fail_count = error_count if error_count is not None else (0 if verdict == "ok" else len(req.tasks))
        failure_modes = () if verdict == "ok" else (f"harbor_exit:{return_code}",)
        limitations = (
            "Harbor raw execution captured; score parsing is delegated to Harbor artifacts",
        )
        return BenchmarkRunResult(
            schema_version=SCHEMA_VERSION,
            run_id=run_id,
            benchmark=_BENCHMARK_NAME,
            benchmark_version=_BENCHMARK_VERSION,
            dataset=self.id,
            adapter=_ADAPTER_NAME,
            agent=req.agent,
            model=req.model,
            env=req.env,
            tasks_requested=req.tasks,
            tasks_completed=completed_tasks,
            score=harbor_score,
            pass_count=pass_count,
            fail_count=fail_count,
            pending_count=0,
            started_at=now,
            completed_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            duration_sec=duration,
            command=plan.command,
            exit_code=return_code,
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            artifacts=tuple(
                p for p in (
                    str(stdout_path),
                    str(stderr_path),
                    str(run_dir / "harbor-jobs"),
                    str(harbor_result_path) if harbor_result_path else "",
                )
                if p
            ),
            verdict=verdict,
            failure_modes=failure_modes,
            limitations=limitations,
        )

    def _parse_harbor_job_summary(
        self, jobs_dir: Path
    ) -> tuple[float | None, int | None, int | None, Path | None]:
        """Parse Harbor's top-level job result.json without assuming schema stability."""
        for result_path in sorted(jobs_dir.glob("*/result.json"), reverse=True):
            try:
                data = json.loads(result_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            stats = data.get("stats") if isinstance(data, dict) else None
            if not isinstance(stats, dict):
                continue
            score = None
            evals = stats.get("evals")
            if isinstance(evals, dict):
                for eval_payload in evals.values():
                    metrics = eval_payload.get("metrics") if isinstance(eval_payload, dict) else None
                    if isinstance(metrics, list) and metrics:
                        first = metrics[0]
                        if isinstance(first, dict) and isinstance(first.get("mean"), (int, float)):
                            score = float(first["mean"])
                            break
            completed = stats.get("n_completed_trials")
            errors = stats.get("n_errored_trials")
            return (
                score,
                completed if isinstance(completed, int) else None,
                errors if isinstance(errors, int) else None,
                result_path,
            )
        return None, None, None, None

    def parse_result(self, run_dir: Path) -> BenchmarkRunResult:
        """Parse run.json from a previous benchmark run directory.

        Falls back to minimal reconstruction from exit_code.txt if run.json
        is absent. Returns verdict='error' if no artifacts found.
        """
        run_json_path = run_dir / "run.json"
        if run_json_path.exists():
            try:
                with run_json_path.open(encoding="utf-8") as fh:
                    data = json.load(fh)
                return BenchmarkRunResult(
                    schema_version=data.get("schema_version", SCHEMA_VERSION),
                    run_id=data.get("run_id", ""),
                    benchmark=data.get("benchmark", _BENCHMARK_NAME),
                    benchmark_version=data.get("benchmark_version", _BENCHMARK_VERSION),
                    dataset=data.get("dataset", self.id),
                    adapter=data.get("adapter", _ADAPTER_NAME),
                    agent=data.get("agent", ""),
                    model=data.get("model", ""),
                    env=data.get("env", ""),
                    tasks_requested=tuple(data.get("tasks_requested", ())),
                    tasks_completed=tuple(data.get("tasks_completed", ())),
                    score=data.get("score"),
                    pass_count=data.get("pass_count", 0),
                    fail_count=data.get("fail_count", 0),
                    pending_count=data.get("pending_count", 0),
                    started_at=data.get("started_at", ""),
                    completed_at=data.get("completed_at"),
                    duration_sec=data.get("duration_sec"),
                    command=tuple(data.get("command", ())),
                    exit_code=data.get("exit_code"),
                    stdout_path=data.get("stdout_path"),
                    stderr_path=data.get("stderr_path"),
                    artifacts=tuple(data.get("artifacts", ())),
                    verdict=data.get("verdict", "error"),
                    failure_modes=tuple(data.get("failure_modes", ())),
                    limitations=tuple(data.get("limitations", ())),
                )
            except (json.JSONDecodeError, OSError):
                pass

        # Fallback: reconstruct minimal result from exit_code.txt
        exit_code: int | None = None
        exit_code_path = run_dir / "exit_code.txt"
        if exit_code_path.exists():
            try:
                exit_code = int(exit_code_path.read_text().strip())
            except (ValueError, OSError):
                pass

        return BenchmarkRunResult(
            schema_version=SCHEMA_VERSION,
            run_id="",
            benchmark=_BENCHMARK_NAME,
            benchmark_version=_BENCHMARK_VERSION,
            dataset=self.id,
            adapter=_ADAPTER_NAME,
            agent="",
            model="",
            env="",
            tasks_requested=(),
            tasks_completed=(),
            score=None,
            pass_count=0,
            fail_count=0,
            pending_count=0,
            started_at="",
            completed_at=None,
            duration_sec=None,
            command=(),
            exit_code=exit_code,
            stdout_path=None,
            stderr_path=None,
            artifacts=(),
            verdict="error",
            failure_modes=("no_run_json",),
            limitations=("Reconstructed from exit_code.txt only",),
        )

    def _base_result(
        self, req: BenchmarkRunRequest, run_id: str, started_at: str
    ) -> dict[str, Any]:
        """Shared base fields for run results."""
        return dict(
            schema_version=SCHEMA_VERSION,
            run_id=run_id,
            benchmark=_BENCHMARK_NAME,
            benchmark_version=_BENCHMARK_VERSION,
            dataset=self.id,
            adapter=_ADAPTER_NAME,
            agent=req.agent,
            model=req.model,
            env=req.env,
            tasks_requested=req.tasks,
            tasks_completed=(),
            score=None,
            pass_count=0,
            fail_count=0,
            pending_count=0,
            started_at=started_at,
            completed_at=None,
            duration_sec=0.0,
            command=(),
            exit_code=None,
            stdout_path=None,
            stderr_path=None,
            artifacts=(),
        )

    def _error_result(
        self, base: dict[str, Any], failure_modes: tuple[str, ...], notes: str
    ) -> BenchmarkRunResult:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        base.update(
            verdict="error",
            failure_modes=failure_modes,
            completed_at=now,
            limitations=(notes,),
        )
        return BenchmarkRunResult(**base)

    def _pending_result(
        self, base: dict[str, Any], missing: tuple[str, ...], notes: str
    ) -> BenchmarkRunResult:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        base.update(
            verdict="pending",
            failure_modes=missing,
            completed_at=now,
            pending_count=len(base.get("tasks_requested", ())),
            limitations=(notes,),
        )
        return BenchmarkRunResult(**base)


# Seed registration
@registry.register
class _TerminalBench20(TerminalBench20Adapter):
    """Registered subclass — triggers decorator on module import."""
    pass
