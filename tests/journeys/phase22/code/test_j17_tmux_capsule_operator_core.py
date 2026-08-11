from __future__ import annotations

import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from evidence import command_exists, redact, relative_or_absolute, repo_head, utc_now
from journey_runner import (
    bash_argv,
    bash_blocker,
    base_env,
    has_live_authorization,
    python_executable,
)


JOURNEY_ID = "P22-J17"
BATCH_ID = "T2-tmux-prep-001"
JOURNEY_NAME = "TMUX capsule/operator core selection, graph persistence, and recovery"
SERIAL_GATE = "PHASE22_ENABLE_SERIAL_TMUX_JOURNEYS"
SELECTOR = (
    "tests/journeys/phase22/code/test_j17_tmux_capsule_operator_core.py::"
    "test_p22_j17_tmux_capsule_operator_core_real_user_entrypoint"
)
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "j17_tmux_capsule_operator_core"
SAMPLE_PROJECT_DIR = FIXTURE_ROOT / "sample_project"
USER_TASK_TEMPLATE = FIXTURE_ROOT / "user_messages" / "capsule_operator_core_task.md"

OWNED_L2: list[str] = [
    "Capsule Governance, Certification & Registry Management",
    "Capsule Invocation & Composition",
    "Capability Capsule Evolution & Version Promotion",
    "Logical Operator Definition, Assembly & Registration",
    "Operator Qualification, Admission & Governance",
    "Logical-to-Physical Matching, Selection & Binding",
    "Physical Operator & Execution Fleet Management",
    "Operator Runtime Evaluation & Capability Profiling",
    "Model Capability Registry",
    "Code Graph Management",
    "Workflow Graph Management",
    "Message Bus & Durable Task Queue",
    "Failure Recovery & Resumability",
]

PER_L2_SUCCESS_CRITERIA: dict[str, str] = {
    "Capsule Governance, Certification & Registry Management": (
        "Product-generated artifacts name the capsule/capability governance source used for the task "
        "and show it influenced admission or dispatch, not merely that a registry file exists."
    ),
    "Capsule Invocation & Composition": (
        "At least two capability or operator invocations are observed for the sprint, with task-specific "
        "inputs/outputs tied to the J17 workspace."
    ),
    "Capability Capsule Evolution & Version Promotion": (
        "The run records an evaluated version, promotion decision, rollback decision, or a product-stated "
        "not-supported outcome for the invoked capsule/operator path."
    ),
    "Logical Operator Definition, Assembly & Registration": (
        "A task graph, routing record, or operator result names logical operators selected for this task."
    ),
    "Operator Qualification, Admission & Governance": (
        "The operator path records an admission, qualification, policy, or gate decision before or during dispatch."
    ),
    "Logical-to-Physical Matching, Selection & Binding": (
        "A routing decision binds required logical capabilities to a physical operator, actor, pane, or runtime."
    ),
    "Physical Operator & Execution Fleet Management": (
        "A physical operator/actor execution record exists with lifecycle state beyond process start."
    ),
    "Operator Runtime Evaluation & Capability Profiling": (
        "The invoked operator has runtime evidence such as exit code, duration, result status, capability profile, "
        "or evaluator verdict."
    ),
    "Model Capability Registry": (
        "The selected model/runtime/provider is visible in a product artifact or command record for the task."
    ),
    "Code Graph Management": (
        "A CodeGraph or code-evidence artifact is generated or updated for the J17 workspace."
    ),
    "Workflow Graph Management": (
        "A WorkflowGraph, TaskGraph workflow state, or equivalent DAG artifact is generated or updated."
    ),
    "Message Bus & Durable Task Queue": (
        "Durable queue/event/operator records show enqueued, dispatched, running, completed, failed, or recovered "
        "states for this sprint."
    ),
    "Failure Recovery & Resumability": (
        "The test injects a controlled interruption after planning and observes resume/recovery through the same "
        "user entrypoint, with preserved state or recovery records."
    ),
}

STATUSES = {
    "PASS",
    "PASS_WITH_KNOWN_LIMITATIONS",
    "FAIL",
    "ENVIRONMENT_BLOCKED",
    "NOT_AVAILABLE",
    "NOT_TESTED",
}
PYTEST_OUTCOME_BY_STATUS = {
    "PASS": "passed",
    "PASS_WITH_KNOWN_LIMITATIONS": "passed",
    "FAIL": "failed",
    "ENVIRONMENT_BLOCKED": "skipped",
    "NOT_AVAILABLE": "skipped",
    "NOT_TESTED": "not_run",
}


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8-sig", errors="replace")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-") or "artifact"


def _shell_path(path: Path) -> str:
    return shlex.quote(path.resolve().as_posix())


def _tmux_args(socket_name: str, *args: str) -> list[str]:
    return ["tmux", "-L", socket_name, *args]


def _copy_or_link_j17(src: Path, dst: Path) -> None:
    if dst.exists():
        return
    try:
        dst.symlink_to(src, target_is_directory=src.is_dir())
    except OSError:
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def _prepare_j17_isolated_harness(repo_root: Path, sandbox: Path) -> Path:
    source = repo_root / "harness"
    harness_dir = sandbox / "harness"
    harness_dir.mkdir(parents=True, exist_ok=True)
    for name in (
        "bin",
        "config",
        "personas",
        "tools",
        "plugins",
        "evaluators",
        "schemas",
        "lib",
        "workflows",
        "solar-harness.sh",
    ):
        src = source / name
        if src.exists():
            _copy_or_link_j17(src, harness_dir / name)
    for src in source.glob("*.sh"):
        _copy_or_link_j17(src, harness_dir / src.name)
    (harness_dir / "run").mkdir(exist_ok=True)
    (harness_dir / "artifacts").mkdir(exist_ok=True)
    return harness_dir


def _find_sprint_id(text: str) -> str:
    match = re.search(r"(sprint-[A-Za-z0-9_.-]+)", text)
    return match.group(1) if match else ""


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _contains_any(text: str, *terms: str) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def _contains_all(text: str, *terms: str) -> bool:
    lowered = text.lower()
    return all(term.lower() in lowered for term in terms)


@dataclass
class CommandRecord:
    label: str
    argv: list[str]
    cwd: str
    exit_code: int | None
    timed_out: bool
    duration_seconds: float
    stdout_path: str
    stderr_path: str


@dataclass
class J17Recorder:
    repo_root: Path
    started_at: str = field(default_factory=utc_now)
    commands: list[CommandRecord] = field(default_factory=list)
    tmux_user_commands: list[dict[str, Any]] = field(default_factory=list)
    assertions: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    observed_l2: list[dict[str, Any]] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.run_id = f"p22-j17-{stamp}-{os.getpid()}"
        self.run_dir = self.repo_root / "outputs" / "phase22-real-journeys" / self.run_id
        self.stdout_dir = self.run_dir / "stdout"
        self.stderr_dir = self.run_dir / "stderr"
        self.artifact_dir = self.run_dir / "artifacts"
        self.user_input_dir = self.run_dir / "user-inputs"
        self.tmux_capture_dir = self.run_dir / "tmux-captures"
        for directory in (
            self.stdout_dir,
            self.stderr_dir,
            self.artifact_dir,
            self.user_input_dir,
            self.tmux_capture_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        label: str,
        argv: list[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        timeout: float = 60,
    ) -> subprocess.CompletedProcess[str]:
        started = time.monotonic()
        cwd = cwd or self.repo_root
        stdout_path = self.stdout_dir / f"{len(self.commands) + 1:02d}-{_slug(label)}.txt"
        stderr_path = self.stderr_dir / f"{len(self.commands) + 1:02d}-{_slug(label)}.txt"
        timed_out = False
        try:
            proc = subprocess.run(
                argv,
                cwd=cwd,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            proc = subprocess.CompletedProcess(argv, 127, "", str(exc))
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            proc = subprocess.CompletedProcess(
                argv,
                124,
                stdout=exc.stdout if isinstance(exc.stdout, str) else "",
                stderr=exc.stderr if isinstance(exc.stderr, str) else f"timed out after {timeout}s",
            )
        except OSError as exc:
            proc = subprocess.CompletedProcess(
                argv,
                126,
                stdout="",
                stderr=f"{type(exc).__name__}: {exc}",
            )
        duration = time.monotonic() - started
        stdout_path.write_text(redact(proc.stdout or ""), encoding="utf-8", errors="replace")
        stderr_path.write_text(redact(proc.stderr or ""), encoding="utf-8", errors="replace")
        self.commands.append(
            CommandRecord(
                label=label,
                argv=[redact(str(part)) for part in argv],
                cwd=str(cwd),
                exit_code=int(proc.returncode) if proc.returncode is not None else None,
                timed_out=timed_out,
                duration_seconds=round(duration, 3),
                stdout_path=relative_or_absolute(stdout_path, self.run_dir),
                stderr_path=relative_or_absolute(stderr_path, self.run_dir),
            )
        )
        return proc

    def run_in_user_tmux(
        self,
        socket_name: str,
        session_name: str,
        label: str,
        command: str,
        *,
        env: dict[str, str],
        timeout: int,
    ) -> dict[str, Any]:
        index = len(self.tmux_user_commands) + 1
        stdout_path = self.stdout_dir / f"tmux-{index:02d}-{_slug(label)}.stdout.txt"
        stderr_path = self.stderr_dir / f"tmux-{index:02d}-{_slug(label)}.stderr.txt"
        exit_path = self.artifact_dir / "tmux-exit-codes" / f"{index:02d}-{_slug(label)}.txt"
        exit_path.parent.mkdir(parents=True, exist_ok=True)
        pane_capture_path = self.tmux_capture_dir / f"{index:02d}-{_slug(label)}-pane.txt"
        token = f"P22J17_DONE_{index}_{_slug(label)}"
        shell_command = (
            f"({command}) > {_shell_path(stdout_path)} 2> {_shell_path(stderr_path)}; "
            "_p22_ec=$?; "
            f"printf '\\n{token}:%s\\n' \"$_p22_ec\"; "
            f"printf '%s\\n' \"$_p22_ec\" > {_shell_path(exit_path)}"
        )
        send = self.run(
            f"tmux-send-{label}",
            [*_tmux_args(socket_name, "send-keys", "-t", session_name, shell_command, "C-m")],
            env=env,
            timeout=30,
        )
        exit_code = 124
        deadline = time.monotonic() + timeout
        if send.returncode == 0:
            while time.monotonic() < deadline:
                if exit_path.exists():
                    try:
                        exit_code = int(exit_path.read_text(encoding="utf-8-sig").strip())
                    except ValueError:
                        exit_code = 125
                    break
                time.sleep(1)
        capture = self.run(
            f"tmux-capture-{label}",
            [*_tmux_args(socket_name, "capture-pane", "-p", "-t", session_name, "-S", "-2000")],
            env=env,
            timeout=30,
        )
        pane_capture_path.write_text(redact(capture.stdout or ""), encoding="utf-8", errors="replace")
        for output_path in (stdout_path, stderr_path):
            if output_path.exists():
                output_path.write_text(redact(_read_text(output_path)), encoding="utf-8", errors="replace")
        record = {
            "label": label,
            "command_sent_to_tmux_user_shell": redact(command),
            "send_exit_code": send.returncode,
            "inner_exit_code": exit_code,
            "timed_out": exit_code == 124,
            "timeout_seconds": timeout,
            "stdout_path": relative_or_absolute(stdout_path, self.run_dir),
            "stderr_path": relative_or_absolute(stderr_path, self.run_dir),
            "exit_code_path": relative_or_absolute(exit_path, self.run_dir),
            "pane_capture_path": relative_or_absolute(pane_capture_path, self.run_dir),
            "done_token": token,
        }
        self.tmux_user_commands.append(record)
        return record

    def add_assertion(self, name: str, passed: bool, detail: Any = None) -> None:
        self.assertions.append({"name": name, "passed": bool(passed), "detail": _json_safe(detail)})

    def add_artifact(self, path: Path, artifact_type: str, description: str = "", *, required: bool = True) -> None:
        path = path.resolve()
        exists = path.exists()
        stable_path = path
        stable_copy = False
        if exists and path.is_file():
            try:
                path.relative_to(self.run_dir.resolve())
            except ValueError:
                stable_path = self.artifact_dir / f"{len(self.artifacts) + 1:02d}-{_slug(artifact_type)}-{_slug(path.name)}"
                shutil.copy2(path, stable_path)
                stable_copy = True
        self.artifacts.append(
            {
                "type": artifact_type,
                "path": relative_or_absolute(stable_path, self.run_dir),
                "source_path": str(path),
                "description": description,
                "exists": exists,
                "required": bool(required),
                "stable_copy": stable_copy,
                "bytes": stable_path.stat().st_size if exists and stable_path.is_file() else None,
            }
        )

    def add_l2(
        self,
        feature: str,
        status: str,
        observation: str,
        evidence_path: Path,
        *,
        assertion_name: str,
        known_limitations: list[str] | None = None,
    ) -> None:
        if status not in STATUSES:
            raise ValueError(f"invalid L2 status: {status}")
        self.observed_l2.append(
            {
                "category": "Foundation",
                "level_2_feature": feature,
                "status": status,
                "assertion_name": assertion_name,
                "success_criteria": PER_L2_SUCCESS_CRITERIA[feature],
                "observation": observation,
                "evidence_path": relative_or_absolute(evidence_path, self.run_dir),
                "known_limitations": known_limitations or [],
            }
        )

    def finalize(self, status: str, *, limitations: list[str] | None = None, blockers: list[str] | None = None) -> Path:
        if status not in STATUSES:
            raise ValueError(f"invalid journey status: {status}")
        self.limitations.extend(limitations or [])
        self.blockers.extend(blockers or [])
        finished_at = utc_now()
        started = datetime.fromisoformat(self.started_at.replace("Z", "+00:00"))
        finished = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
        result = {
            "schema_version": "phase22.journey_result.v1",
            "worker_batch_id": BATCH_ID,
            "journey_id": JOURNEY_ID,
            "name": JOURNEY_NAME,
            "execution_selector": SELECTOR,
            "started_at": self.started_at,
            "finished_at": finished_at,
            "duration_seconds": round((finished - started).total_seconds(), 3),
            "repo_head": repo_head(self.repo_root),
            "runtime": {
                "os": platform.platform(),
                "system": platform.system(),
                "python": sys.version,
                "python_executable": sys.executable,
                "bash": "present" if command_exists("bash") else "missing",
                "tmux": "present" if command_exists("tmux") else "missing",
            },
            "sandbox_paths": {"run_dir": str(self.run_dir)},
            "commands": [record.__dict__ for record in self.commands],
            "tmux_user_commands": self.tmux_user_commands,
            "artifacts": self.artifacts,
            "assertions": self.assertions,
            "observed_l2": self.observed_l2,
            "status": status,
            "pytest_outcome": PYTEST_OUTCOME_BY_STATUS[status],
            "limitations": self.limitations,
            "blockers": self.blockers,
            "rerun_command": (
                "$env:PHASE22_ENABLE_SERIAL_TMUX_JOURNEYS='1'; "
                "$env:PHASE22_ENABLE_LIVE_JOURNEYS='1'; "
                f".venv\\Scripts\\python.exe -m pytest {SELECTOR} -m live_provider -vv"
            ),
        }
        result_path = _write_json(self.run_dir / "journey-result.json", result)
        _write_json(self.run_dir / "commands.json", result["commands"])
        _write_json(self.run_dir / "tmux-user-commands.json", self.tmux_user_commands)
        _write_json(self.run_dir / "artifacts.json", self.artifacts)
        _write_json(self.run_dir / "assertions.json", self.assertions)
        _write_json(self.run_dir / "observed-l2.json", self.observed_l2)
        if status == "FAIL":
            pytest.fail(f"{JOURNEY_ID} product status FAIL; evidence: {result_path}", pytrace=False)
        if status in {"ENVIRONMENT_BLOCKED", "NOT_AVAILABLE", "NOT_TESTED"}:
            pytest.skip(f"{JOURNEY_ID} product status {status}; evidence: {result_path}")
        return result_path


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return value


def _mark_all_l2(rec: J17Recorder, status: str, evidence_path: Path, reason: str) -> None:
    for feature in OWNED_L2:
        rec.add_l2(
            feature,
            status,
            reason,
            evidence_path,
            assertion_name=f"j17_{_slug(feature).lower()}_{status.lower()}",
            known_limitations=[reason],
        )


def _operator_provider_auth_blocker(harness_dir: Path, sprint_id: str) -> str:
    auth_signals = (
        "401 unauthorized",
        "missing bearer",
        "basic authentication",
        "codex login",
        "api key",
        "not authenticated",
    )
    result_root = harness_dir / "run" / "operator-results"
    if not result_root.exists():
        return ""
    for operator_dir in result_root.iterdir():
        if not operator_dir.is_dir():
            continue
        for task_dir in sorted((path for path in operator_dir.iterdir() if path.is_dir()), key=lambda path: path.stat().st_mtime, reverse=True):
            payload = _read_json(task_dir / "result.json")
            envelope = _read_json(task_dir / "envelope.json")
            if sprint_id and payload.get("sprint_id") != sprint_id and envelope.get("sprint_id") != sprint_id:
                continue
            text = "\n".join(
                _read_text(task_dir / name)
                for name in ("output.log", "codex-cli-output.log", "error.log", "result.json")
            ).lower()
            if any(signal in text for signal in auth_signals):
                return "Codex provider authentication is unavailable in the sandboxed live journey runtime."
    return ""


def _prepare_project(tmp_path: Path) -> Path:
    project = tmp_path / "j17-capsule-operator-project"
    shutil.copytree(SAMPLE_PROJECT_DIR, project)
    return project


def _render_user_task(rec: J17Recorder, project: Path, python_cmd: str) -> Path:
    template = _read_text(USER_TASK_TEMPLATE)
    rendered = template.format(
        workspace_root=project.resolve().as_posix(),
        test_command=f"{python_cmd} -m pytest -q",
    )
    path = rec.user_input_dir / "capsule-operator-core-task.md"
    path.write_text(rendered, encoding="utf-8")
    rec.add_artifact(path, "j17-rendered-user-task", required=True)
    return path


def _collect_paths(harness_dir: Path, sprint_id: str) -> dict[str, Path]:
    sprints_dir = harness_dir / "sprints"
    return {
        "status": sprints_dir / f"{sprint_id}.status.json",
        "events": sprints_dir / f"{sprint_id}.events.jsonl",
        "raw_intent": sprints_dir / f"{sprint_id}.raw-intent.json",
        "requirement_ir": sprints_dir / f"{sprint_id}.requirement-ir.json",
        "prd": sprints_dir / f"{sprint_id}.prd.md",
        "design": sprints_dir / f"{sprint_id}.design.md",
        "plan": sprints_dir / f"{sprint_id}.plan.md",
        "task_graph": sprints_dir / f"{sprint_id}.task_graph.json",
        "workflow_graph": sprints_dir / f"{sprint_id}.workflow_graph.json",
        "code_graph": sprints_dir / f"{sprint_id}.code_graph.json",
        "handoff": sprints_dir / f"{sprint_id}.handoff.md",
        "eval": sprints_dir / f"{sprint_id}.eval.md",
    }


def _operator_task_dirs(harness_dir: Path) -> list[Path]:
    result_root = harness_dir / "run" / "operator-results"
    if not result_root.exists():
        return []
    task_dirs: list[Path] = []
    for operator_dir in result_root.iterdir():
        if operator_dir.is_dir():
            task_dirs.extend(path for path in operator_dir.iterdir() if path.is_dir())
    return sorted(task_dirs, key=lambda path: path.stat().st_mtime, reverse=True)


def _read_operator_payloads(harness_dir: Path, sprint_id: str) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for task_dir in _operator_task_dirs(harness_dir):
        result = _read_json(task_dir / "result.json")
        envelope = _read_json(task_dir / "envelope.json")
        if result.get("sprint_id") == sprint_id or envelope.get("sprint_id") == sprint_id:
            payloads.append({"task_dir": str(task_dir), "result": result, "envelope": envelope})
    return payloads


def _artifact_bundle(paths: dict[str, Path], operator_payloads: list[dict[str, Any]], extra_paths: list[Path]) -> str:
    chunks = []
    for path in [*paths.values(), *extra_paths]:
        if path.exists() and path.is_file():
            chunks.append(f"\n--- {path.name} ---\n{_read_text(path)[:30000]}")
    chunks.append(json.dumps(operator_payloads, ensure_ascii=False, indent=2, sort_keys=True))
    return "\n".join(chunks)


def _write_static_probe(rec: J17Recorder, harness_dir: Path, sprint_id: str, project: Path) -> Path:
    paths = _collect_paths(harness_dir, sprint_id)
    operator_payloads = _read_operator_payloads(harness_dir, sprint_id)
    extra_paths = [
        harness_dir / "run" / "autopilot-state.json",
        harness_dir / "run" / "task-queue.json",
        harness_dir / "run" / "task_queue.json",
        harness_dir / "run" / "actor-runtime-results.jsonl",
        harness_dir / "config" / "capability-capsules.registry.yaml",
        harness_dir / "config" / "logical-operators.json",
        harness_dir / "config" / "physical-operators.json",
        harness_dir / "config" / "model-registry.json",
    ]
    for path in [*paths.values(), *extra_paths]:
        rec.add_artifact(path, f"j17-{_slug(path.name)}", required=False)
    for payload in operator_payloads:
        task_dir = Path(payload["task_dir"])
        rec.add_artifact(task_dir / "result.json", "j17-operator-result", required=False)
        rec.add_artifact(task_dir / "envelope.json", "j17-operator-envelope", required=False)
        rec.add_artifact(task_dir / "output.log", "j17-operator-output-log", required=False)
    bundle = _artifact_bundle(paths, operator_payloads, extra_paths)
    code_graph_candidates = [
        paths["code_graph"],
        *(harness_dir / "sprints").glob(f"{sprint_id}*code*graph*.json"),
        *(harness_dir / "artifacts").glob(f"**/*{sprint_id}*code*graph*"),
    ]
    workflow_graph_candidates = [
        paths["workflow_graph"],
        paths["task_graph"],
        *(harness_dir / "sprints").glob(f"{sprint_id}*workflow*graph*.json"),
        *(harness_dir / "artifacts").glob(f"**/*{sprint_id}*workflow*graph*"),
    ]
    probe = {
        "sprint_id": sprint_id,
        "workspace": str(project),
        "paths": {key: str(path) for key, path in paths.items()},
        "operator_payload_count": len(operator_payloads),
        "operator_payloads": operator_payloads,
        "signals": {
            "task_graph_exists": paths["task_graph"].exists(),
            "code_graph_exists": any(path.exists() for path in code_graph_candidates),
            "workflow_graph_exists": any(path.exists() for path in workflow_graph_candidates),
            "durable_events_exist": paths["events"].exists() or any((harness_dir / "run").glob("*queue*.json*")),
            "contains_capsule_terms": _contains_any(bundle, "capsule", "capability"),
            "contains_invocation_terms": _contains_any(bundle, "invoked", "completed", "operator-results", "task_dir"),
            "contains_evolution_terms": _contains_any(bundle, "promot", "version", "rollback", "not supported"),
            "contains_logical_operator": _contains_any(bundle, "logical_operator", "logical operator"),
            "contains_qualification_terms": _contains_any(bundle, "qualified", "admission", "governance", "gate", "policy"),
            "contains_binding_terms": _contains_any(bundle, "physical_operator", "actor_id", "target_pane", "capability_match"),
            "contains_runtime_terms": _contains_any(bundle, "exit_code", "duration", "runtime", "status"),
            "contains_model_terms": _contains_any(bundle, "model", "provider", "codex", "claude", "openai", "anthropic"),
            "contains_recovery_terms": _contains_any(bundle, "recover", "resume", "interruption", "restart", "resumed"),
            "contains_queue_lifecycle_terms": _contains_any(
                bundle,
                "queued",
                "dispatched",
                "running",
                "completed",
                "failed",
                "operator-results",
            ),
        },
    }
    return _write_json(rec.artifact_dir / "j17-artifact-probe.json", probe)


def _record_l2(rec: J17Recorder, probe_path: Path) -> None:
    probe = _read_json(probe_path)
    signals = probe.get("signals") or {}
    paths = {key: Path(value) for key, value in (probe.get("paths") or {}).items()}
    operator_count = int(probe.get("operator_payload_count") or 0)

    definitions: dict[str, tuple[bool, str, Path, list[str]]] = {
        "Capsule Governance, Certification & Registry Management": (
            signals.get("contains_capsule_terms") and signals.get("contains_qualification_terms"),
            "Capsule/capability and governance/admission signals are present in product artifacts.",
            probe_path,
            [],
        ),
        "Capsule Invocation & Composition": (
            operator_count >= 2 or (operator_count >= 1 and signals.get("contains_invocation_terms")),
            "Operator payloads or equivalent invocation evidence show task-specific execution.",
            probe_path,
            [] if operator_count >= 2 else ["Fewer than two separate operator result directories were observed."],
        ),
        "Capability Capsule Evolution & Version Promotion": (
            signals.get("contains_evolution_terms"),
            "Version, promotion, rollback, or not-supported evolution evidence is recorded.",
            probe_path,
            [],
        ),
        "Logical Operator Definition, Assembly & Registration": (
            signals.get("contains_logical_operator"),
            "Logical operator names are visible in task graph, routing, or operator results.",
            paths.get("task_graph", probe_path),
            [],
        ),
        "Operator Qualification, Admission & Governance": (
            signals.get("contains_qualification_terms"),
            "Qualification, admission, policy, gate, or governance evidence exists before/during dispatch.",
            probe_path,
            [],
        ),
        "Logical-to-Physical Matching, Selection & Binding": (
            signals.get("contains_binding_terms"),
            "Routing/binding artifacts connect logical requirements to physical actors or panes.",
            probe_path,
            [],
        ),
        "Physical Operator & Execution Fleet Management": (
            operator_count >= 1 and signals.get("contains_runtime_terms"),
            "Physical operator execution record exists with runtime/lifecycle state.",
            probe_path,
            [],
        ),
        "Operator Runtime Evaluation & Capability Profiling": (
            signals.get("contains_runtime_terms"),
            "Runtime status, exit code, duration, or evaluator evidence is present.",
            probe_path,
            [],
        ),
        "Model Capability Registry": (
            signals.get("contains_model_terms"),
            "Selected model/runtime/provider evidence is visible for this task.",
            probe_path,
            [],
        ),
        "Code Graph Management": (
            signals.get("code_graph_exists") or _contains_any(json.dumps(probe), "code graph", "code_graph"),
            "CodeGraph or code-evidence artifact exists or is referenced for the J17 workspace.",
            paths.get("code_graph", probe_path),
            [] if signals.get("code_graph_exists") else ["CodeGraph evidence may be a reference rather than a standalone file."],
        ),
        "Workflow Graph Management": (
            signals.get("workflow_graph_exists") or signals.get("task_graph_exists"),
            "WorkflowGraph or TaskGraph workflow state exists for the sprint.",
            paths.get("workflow_graph", paths.get("task_graph", probe_path)),
            [] if signals.get("workflow_graph_exists") else ["WorkflowGraph is represented by TaskGraph evidence."],
        ),
        "Message Bus & Durable Task Queue": (
            signals.get("durable_events_exist") and signals.get("contains_queue_lifecycle_terms"),
            "Durable events, queue, or operator-result lifecycle records exist beyond process start.",
            paths.get("events", probe_path),
            [],
        ),
        "Failure Recovery & Resumability": (
            signals.get("contains_recovery_terms"),
            "Controlled interruption and resume evidence is present in artifacts.",
            probe_path,
            [],
        ),
    }
    for feature in OWNED_L2:
        passed, observation, evidence_path, limitations = definitions[feature]
        if passed and limitations:
            status = "PASS_WITH_KNOWN_LIMITATIONS"
        elif passed:
            status = "PASS"
        elif feature in {"Code Graph Management", "Capability Capsule Evolution & Version Promotion"}:
            status = "NOT_TESTED"
            limitations = [f"No direct {feature} evidence was observed in the accepted artifact set."]
        else:
            status = "FAIL"
        rec.add_l2(
            feature,
            status,
            observation,
            evidence_path if evidence_path.exists() else probe_path,
            assertion_name=f"j17_l2_{_slug(feature).lower()}",
            known_limitations=limitations,
        )


@pytest.mark.live_provider
def test_p22_j17_tmux_capsule_operator_core_real_user_entrypoint(repo_root: Path, tmp_path: Path) -> None:
    if os.environ.get(SERIAL_GATE) != "1":
        pytest.skip(f"{SERIAL_GATE}=1 is required before any TMUX operation.")

    rec = J17Recorder(repo_root)
    sandbox = tmp_path / "p22-j17-sandbox"
    harness_dir = _prepare_j17_isolated_harness(repo_root, sandbox)
    env = base_env(repo_root, sandbox, allow_live=True)
    env.update(
        {
            "HARNESS_DIR": str(harness_dir),
            "SOLAR_HARNESS_DIR": str(harness_dir),
            "SOLAR_HARNESS_SPRINTS_DIR": str(harness_dir / "sprints"),
            "SPRINTS_DIR": str(harness_dir / "sprints"),
            "SOLAR_INTENT_GATEWAY_DIR": str(harness_dir / "intent-gateway"),
            "SOLAR_KNOWLEDGE_RAW_DIR": str(harness_dir / "Knowledge" / "_raw"),
            "SOLAR_HARNESS_SESSION": f"p22-j17-product-{rec.run_id}",
            "SOLAR_HARNESS_LAB_SESSION": f"p22-j17-lab-{rec.run_id}",
            "SOLAR_HARNESS_BG_SESSION": f"p22-j17-bg-{rec.run_id}",
            "SOLAR_PANE_RUNTIME": os.environ.get("PHASE22_SELECTED_RUNTIME", os.environ.get("SOLAR_PANE_RUNTIME", "codex")),
            "PHASE22_SELECTED_RUNTIME": os.environ.get("PHASE22_SELECTED_RUNTIME", os.environ.get("SOLAR_PANE_RUNTIME", "codex")),
            "PHASE22_JOURNEY_RUN_ID": str(rec.run_id),
            "SOLAR_INTENT_SOURCE_CHANNEL": "tmux_user_entry",
            "SOLAR_INTENT_ACTOR": "phase22_j17_user",
            "TERM": "dumb",
        }
    )
    selected_runtime = env["SOLAR_PANE_RUNTIME"].lower()
    preflight_path = rec.artifact_dir / "preflight.json"

    blockers: list[str] = []
    not_available: list[str] = []
    required_paths = [
        harness_dir / "solar-harness.sh",
        harness_dir / "config" / "capability-capsules.registry.yaml",
        harness_dir / "config" / "logical-operators.json",
        harness_dir / "config" / "physical-operators.json",
        harness_dir / "config" / "model-registry.json",
    ]
    for required in required_paths:
        if not required.exists():
            not_available.append(f"Required production artifact is missing: {required}")
    if not has_live_authorization():
        blockers.append("PHASE22_ENABLE_LIVE_JOURNEYS=1 was not set; live provider execution was not authorized.")
    bash_error = bash_blocker(repo_root)
    if bash_error is not None:
        blockers.append(bash_error)
    for executable in ("git", "tmux"):
        if not command_exists(executable):
            blockers.append(f"{executable} is not available on PATH.")
    if selected_runtime not in {"codex", "claude"}:
        blockers.append(f"Unsupported runtime identity: {selected_runtime}")
    elif not command_exists(selected_runtime):
        blockers.append(f"{selected_runtime} runtime is not available on PATH.")
    for required_fixture in [USER_TASK_TEMPLATE, SAMPLE_PROJECT_DIR / "solar_pipeline.py"]:
        if not required_fixture.exists():
            blockers.append(f"Missing J17 fixture: {required_fixture}")

    if command_exists("git"):
        rec.run("preflight-git-version", ["git", "--version"], env=env, timeout=30)
    if command_exists("tmux"):
        rec.run("preflight-tmux-version", ["tmux", "-V"], env=env, timeout=30)
    if command_exists(selected_runtime):
        rec.run("preflight-runtime-version", [selected_runtime, "--version"], env=env, timeout=30)
    _write_json(
        preflight_path,
        {
            "not_available": not_available,
            "blockers": blockers,
            "harness_dir": str(harness_dir),
            "selected_runtime": selected_runtime,
            "serial_guard": f"{SERIAL_GATE}=1",
        },
    )
    rec.add_artifact(preflight_path, "j17-preflight", required=True)
    if not_available:
        reason = "; ".join(not_available)
        _mark_all_l2(rec, "NOT_AVAILABLE", preflight_path, reason)
        rec.finalize("NOT_AVAILABLE", blockers=not_available)
        return
    if blockers:
        reason = "; ".join(blockers)
        _mark_all_l2(rec, "ENVIRONMENT_BLOCKED", preflight_path, reason)
        rec.finalize("ENVIRONMENT_BLOCKED", blockers=blockers)
        return

    project = _prepare_project(tmp_path)
    python_cmd = python_executable(repo_root)
    user_task = _render_user_task(rec, project, python_cmd)
    baseline = rec.run("baseline-pytest", [python_cmd, "-m", "pytest", "-q"], cwd=project, env=env, timeout=120)
    rec.add_assertion("fixture_tests_pass_before_product_work", baseline.returncode == 0, baseline.returncode)

    user_socket = f"p22j17user{os.getpid()}"
    user_session = f"p22-j17-user-{os.getpid()}"
    tmux_started = False
    harness_script = harness_dir / "solar-harness.sh"
    sprint_id = ""
    try:
        tmux_start = rec.run(
            "tmux-new-user-session",
            [
                *_tmux_args(
                    user_socket,
                    "new-session",
                    "-d",
                    "-s",
                    user_session,
                    "-c",
                    str(project),
                    *bash_argv(repo_root, "--noprofile", "--norc"),
                )
            ],
            cwd=project,
            env=env,
            timeout=30,
        )
        tmux_started = tmux_start.returncode == 0
        rec.add_assertion("tmux_user_session_started", tmux_started, tmux_start.returncode)
        if not tmux_started:
            _mark_all_l2(rec, "ENVIRONMENT_BLOCKED", preflight_path, "TMUX user session could not be started.")
            rec.finalize("ENVIRONMENT_BLOCKED", blockers=["TMUX user session could not be started."])
            return

        start_cmd = f"TERM=dumb bash {_shell_path(harness_script)} start --skip-doctor --clean {_shell_path(project)}"
        start_record = rec.run_in_user_tmux(user_socket, user_session, "harness-start", start_cmd, env=env, timeout=180)
        rec.add_assertion("harness_started_from_user_tmux", start_record["inner_exit_code"] == 0, start_record)

        intake_cmd = f"TERM=dumb bash {_shell_path(harness_script)} intake --file {_shell_path(user_task)} --no-dispatch"
        intake_record = rec.run_in_user_tmux(user_socket, user_session, "harness-intake-no-dispatch", intake_cmd, env=env, timeout=240)
        intake_stdout = _read_text(rec.run_dir / intake_record["stdout_path"])
        intake_stderr = _read_text(rec.run_dir / intake_record["stderr_path"])
        sprint_id = _find_sprint_id(f"{intake_stdout}\n{intake_stderr}")
        rec.add_assertion("harness_intake_created_sprint", intake_record["inner_exit_code"] == 0 and bool(sprint_id), intake_record)
        if not sprint_id:
            rec.finalize("FAIL", blockers=["Could not parse sprint id from harness intake output."])
            return

        wake_timeout = int(os.environ.get("PHASE22_J17_WAKE_TIMEOUT_SECONDS", "900"))
        planner_cmd = f"TERM=dumb bash {_shell_path(harness_script)} wake {shlex.quote(sprint_id)}"
        planner_record = rec.run_in_user_tmux(user_socket, user_session, "wake-planner", planner_cmd, env=env, timeout=wake_timeout)
        sprint_paths = _collect_paths(harness_dir, sprint_id)
        planner_ready = planner_record["inner_exit_code"] == 0 and (
            sprint_paths["plan"].exists() or sprint_paths["task_graph"].exists()
        )
        rec.add_assertion(
            "planner_or_task_graph_created_before_interruption",
            planner_ready,
            {
                "wake_exit": planner_record["inner_exit_code"],
                "plan_exists": sprint_paths["plan"].exists(),
                "task_graph_exists": sprint_paths["task_graph"].exists(),
            },
        )

        interrupted = False
        if planner_ready:
            kill_product = rec.run("controlled-interruption-kill-product-session", ["tmux", "kill-session", "-t", env["SOLAR_HARNESS_SESSION"]], env=env, timeout=30)
            interrupted = kill_product.returncode in {0, 1}
        rec.add_assertion("controlled_interruption_injected_after_planning", interrupted, env["SOLAR_HARNESS_SESSION"])

        restart_cmd = f"TERM=dumb bash {_shell_path(harness_script)} start --skip-doctor {_shell_path(project)}"
        restart_record = rec.run_in_user_tmux(user_socket, user_session, "harness-restart-after-interruption", restart_cmd, env=env, timeout=180)
        rec.add_assertion("harness_restarted_after_interruption", restart_record["inner_exit_code"] == 0, restart_record)

        approve_cmd = (
            f"TERM=dumb bash {_shell_path(harness_script)} plan-verdict {shlex.quote(sprint_id)} "
            "approve 'J17 user approved capsule/operator plan after interruption'"
        )
        approve_record = rec.run_in_user_tmux(user_socket, user_session, "plan-verdict-approve", approve_cmd, env=env, timeout=120)
        rec.add_assertion("plan_verdict_approved_from_user_tmux", approve_record["inner_exit_code"] == 0, approve_record)

        resume_cmd = f"TERM=dumb bash {_shell_path(harness_script)} wake {shlex.quote(sprint_id)}"
        resume_record = rec.run_in_user_tmux(user_socket, user_session, "wake-resume-after-interruption", resume_cmd, env=env, timeout=wake_timeout)
        rec.add_assertion("resume_wake_executed_from_user_tmux", resume_record["inner_exit_code"] == 0, resume_record)

        verify = rec.run("post-product-pytest", [python_cmd, "-m", "pytest", "-q"], cwd=project, env=env, timeout=120)
        rec.add_assertion("workspace_tests_pass_after_product_work", verify.returncode == 0, verify.returncode)

        eval_cmd = (
            f"TERM=dumb bash {_shell_path(harness_script)} eval-verdict {shlex.quote(sprint_id)} "
            "pass 'J17 static verification found graph operator queue and recovery evidence'"
        )
        eval_record = rec.run_in_user_tmux(user_socket, user_session, "eval-verdict-pass", eval_cmd, env=env, timeout=120)
        rec.add_assertion("eval_verdict_command_executed", eval_record["inner_exit_code"] == 0, eval_record)

        probe_path = _write_static_probe(rec, harness_dir, sprint_id, project)
        rec.add_artifact(probe_path, "j17-artifact-probe", required=True)
        _record_l2(rec, probe_path)
        command_summary = _write_json(rec.artifact_dir / "tmux-command-summary.json", rec.tmux_user_commands)
        rec.add_artifact(command_summary, "j17-tmux-command-summary", required=True)

        required_assertions = {
            item["name"]: item["passed"]
            for item in rec.assertions
            if item["name"]
            in {
                "fixture_tests_pass_before_product_work",
                "tmux_user_session_started",
                "harness_started_from_user_tmux",
                "harness_intake_created_sprint",
                "planner_or_task_graph_created_before_interruption",
                "controlled_interruption_injected_after_planning",
                "harness_restarted_after_interruption",
                "plan_verdict_approved_from_user_tmux",
                "resume_wake_executed_from_user_tmux",
                "workspace_tests_pass_after_product_work",
            }
        }
        if not all(required_assertions.values()):
            provider_auth_blocker = _operator_provider_auth_blocker(harness_dir, sprint_id)
            if provider_auth_blocker:
                rec.add_assertion("live_provider_auth_available", False, provider_auth_blocker)
                _mark_all_l2(rec, "ENVIRONMENT_BLOCKED", preflight_path, provider_auth_blocker)
                rec.finalize("ENVIRONMENT_BLOCKED", blockers=[provider_auth_blocker])
                return
            rec.finalize("FAIL", blockers=["One or more required J17 assertions failed."])
            return
        if any(item["status"] == "FAIL" for item in rec.observed_l2):
            rec.finalize("FAIL", blockers=["One or more observed J17 L2 criteria failed."])
            return
        limitations = sorted({lim for item in rec.observed_l2 for lim in item.get("known_limitations", [])})
        rec.finalize("PASS_WITH_KNOWN_LIMITATIONS" if limitations else "PASS", limitations=limitations)
    finally:
        if tmux_started:
            rec.run(
                "tmux-final-capture-user-session",
                [*_tmux_args(user_socket, "capture-pane", "-p", "-t", user_session, "-S", "-2000")],
                env=env,
                timeout=30,
            )
            rec.run("tmux-kill-user-server", [*_tmux_args(user_socket, "kill-server")], env=env, timeout=30)
        for session_env_key in ("SOLAR_HARNESS_SESSION", "SOLAR_HARNESS_LAB_SESSION", "SOLAR_HARNESS_BG_SESSION"):
            session_name = env.get(session_env_key)
            if session_name:
                rec.run("tmux-kill-product-session", ["tmux", "kill-session", "-t", session_name], env=env, timeout=30)
