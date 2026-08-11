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


JOURNEY_ID = "P22-J16"
BATCH_ID = "T1-tmux-prep-001"
JOURNEY_NAME = "TMUX user requirements builder with scoped defect repair"
SELECTOR = (
    "tests/journeys/phase22/code/test_j16_tmux_requirements_builder.py::"
    "test_p22_j16_tmux_requirements_builder_real_user_defect_repair"
)

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "j16_tmux_requirements_builder"
USER_MESSAGE_DIR = FIXTURE_ROOT / "user_messages"
SAMPLE_PROJECT_DIR = FIXTURE_ROOT / "sample_project"

OWNED_L2: list[dict[str, str]] = [
    {"category": "Workflow", "level_2_feature": "Context Scoping"},
    {"category": "Workflow", "level_2_feature": "Ambiguity Resolution"},
    {"category": "Workflow", "level_2_feature": "Requirement Prioritization"},
    {
        "category": "Foundation",
        "level_2_feature": "Intent Classification & Compilation Variant Selection",
    },
    {"category": "Foundation", "level_2_feature": "Goal, Scope and Context normalization"},
    {"category": "Foundation", "level_2_feature": "Ambiguity Resolution & Readiness"},
    {"category": "Foundation", "level_2_feature": "Constraint Compilation"},
    {"category": "Foundation", "level_2_feature": "Build Contract Interpretation"},
    {"category": "Foundation", "level_2_feature": "Build Preparation"},
    {"category": "Foundation", "level_2_feature": "Product Integration"},
    {"category": "Foundation", "level_2_feature": "Defect Repair"},
]

PER_L2_SUCCESS_CRITERIA: dict[str, str] = {
    "Context Scoping": (
        "User inputs, RawIntent or requirement IR, and compiled contract identify the target repo, "
        "affected checkout-discount domain, and bounded file/test context."
    ),
    "Ambiguity Resolution": (
        "The initial request is materially incomplete, later user messages supply the missing repo, "
        "scope, priority, constraints, and acceptance details, and compiled artifacts preserve that clarification."
    ),
    "Requirement Prioritization": (
        "Priority and must-have acceptance criteria are visible in user input and in a compiled artifact."
    ),
    "Intent Classification & Compilation Variant Selection": (
        "The harness intake path creates RawIntent/requirement IR evidence showing a build or defect-repair "
        "variant rather than bypassing PM requirements analysis or routing to a research workflow."
    ),
    "Goal, Scope and Context normalization": (
        "Requirement IR or contract normalizes the goal, repo/workspace, in-scope files, out-of-scope work, "
        "and test command."
    ),
    "Ambiguity Resolution & Readiness": (
        "Readiness is supported by resolved clarifications plus plan approval or an equivalent status transition "
        "before builder dispatch; absent direct product-generated clarification remains a limitation."
    ),
    "Constraint Compilation": (
        "The compiled contract or plan includes the stdlib-only constraint, no new dependencies, allowed files, "
        "and required pytest command."
    ),
    "Build Contract Interpretation": (
        "Planner or task graph artifacts map the accepted requirements into concrete build and verification work."
    ),
    "Build Preparation": (
        "The serial journey observes planner artifacts or task graph preparation before the builder wake command."
    ),
    "Product Integration": (
        "A product-managed builder/operator path applies a bounded change to the sandbox project or its harness "
        "worktree and independent verification observes passing tests."
    ),
    "Defect Repair": (
        "The fixture test fails before the product task, a real diff changes the defect area, and the same "
        "pytest command passes after the repair."
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


def _copy_or_link_j16(src: Path, dst: Path) -> None:
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


def _prepare_j16_isolated_harness(repo_root: Path, sandbox: Path) -> Path:
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
            _copy_or_link_j16(src, harness_dir / name)
    for src in source.glob("*.sh"):
        _copy_or_link_j16(src, harness_dir / src.name)
    (harness_dir / "run").mkdir(exist_ok=True)
    (harness_dir / "artifacts").mkdir(exist_ok=True)
    return harness_dir


def _find_sprint_id(text: str) -> str:
    match = re.search(r"Sprint created:\s*(sprint-[^\s\r\n]+)", text)
    return match.group(1) if match else ""


def _is_truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


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
class J16Recorder:
    repo_root: Path
    run_id: str | None = None
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
        self.run_id = self.run_id or f"p22-j16-{stamp}-{os.getpid()}"
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

    def add_assertion(self, name: str, passed: bool, detail: Any = None) -> None:
        self.assertions.append({"name": name, "passed": bool(passed), "detail": _json_safe(detail)})

    def add_l2(
        self,
        category: str,
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
                "category": category,
                "level_2_feature": feature,
                "status": status,
                "assertion_name": assertion_name,
                "success_criteria": PER_L2_SUCCESS_CRITERIA[feature],
                "observation": observation,
                "evidence_path": relative_or_absolute(evidence_path, self.run_dir),
                "known_limitations": known_limitations or [],
            }
        )

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
        entry: dict[str, Any] = {
            "type": artifact_type,
            "path": relative_or_absolute(stable_path, self.run_dir),
            "source_path": str(path),
            "description": description,
            "exists": exists,
            "required": bool(required),
            "stable_copy": stable_copy,
        }
        if exists and stable_path.is_file():
            entry["bytes"] = stable_path.stat().st_size
        self.artifacts.append(entry)

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
        stdout_path.write_text(redact(proc.stdout), encoding="utf-8", errors="replace")
        stderr_path.write_text(redact(proc.stderr), encoding="utf-8", errors="replace")
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
        token = f"P22J16_DONE_{index}_{_slug(label)}"
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
        pane_capture_path.write_text(redact(capture.stdout), encoding="utf-8", errors="replace")
        if stdout_path.exists():
            stdout_path.write_text(redact(_read_text(stdout_path)), encoding="utf-8", errors="replace")
        if stderr_path.exists():
            stderr_path.write_text(redact(_read_text(stderr_path)), encoding="utf-8", errors="replace")
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

    def finalize(self, status: str, *, limitations: list[str] | None = None, blockers: list[str] | None = None) -> Path:
        if status not in STATUSES:
            raise ValueError(f"invalid journey status: {status}")
        if limitations:
            self.limitations.extend(limitations)
        if blockers:
            self.blockers.extend(blockers)
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
        _write_json(self.run_dir / "journey-result.json", result)
        _write_json(self.run_dir / "commands.json", result["commands"])
        _write_json(self.run_dir / "tmux-user-commands.json", self.tmux_user_commands)
        _write_json(self.run_dir / "artifacts.json", self.artifacts)
        _write_json(self.run_dir / "assertions.json", self.assertions)
        _write_json(self.run_dir / "observed-l2.json", self.observed_l2)
        (self.run_dir / "limitations.md").write_text(
            "\n".join(f"- {item}" for item in [*self.limitations, *self.blockers]) + "\n",
            encoding="utf-8",
        )
        result_path = self.run_dir / "journey-result.json"
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
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _mark_l2_unavailable(rec: J16Recorder, status: str, evidence_path: Path, reason: str) -> None:
    for item in OWNED_L2:
        rec.add_l2(
            item["category"],
            item["level_2_feature"],
            status,
            reason,
            evidence_path,
            assertion_name=f"{_slug(item['level_2_feature']).lower()}_{status.lower()}",
            known_limitations=[reason] if status != "PASS" else [],
        )


def _operator_task_dirs(harness_dir: Path) -> list[Path]:
    result_root = harness_dir / "run" / "operator-results"
    if not result_root.exists():
        return []
    task_dirs: list[Path] = []
    for operator_dir in result_root.iterdir():
        if operator_dir.is_dir():
            task_dirs.extend(path for path in operator_dir.iterdir() if path.is_dir())
    return sorted(task_dirs, key=lambda path: path.stat().st_mtime, reverse=True)


def _operator_provider_auth_blocker(harness_dir: Path, sprint_id: str) -> str:
    auth_signals = (
        "401 unauthorized",
        "missing bearer",
        "basic authentication",
        "codex login",
        "api key",
        "not authenticated",
    )
    for task_dir in _operator_task_dirs(harness_dir):
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


def _task_dir_key(path: Path) -> str:
    return str(path.resolve())


def _latest_operator_result_for_sprint(
    harness_dir: Path,
    sprint_id: str,
    *,
    seen_task_dirs: set[str] | None = None,
) -> tuple[Path | None, dict[str, Any]]:
    seen_task_dirs = seen_task_dirs or set()
    for task_dir in _operator_task_dirs(harness_dir):
        if _task_dir_key(task_dir) in seen_task_dirs:
            continue
        payload = _read_json(task_dir / "result.json")
        envelope = _read_json(task_dir / "envelope.json")
        if payload.get("sprint_id") == sprint_id or envelope.get("sprint_id") == sprint_id:
            return task_dir, payload
    return None, {}


def _wait_for_operator_result(
    harness_dir: Path,
    sprint_id: str,
    timeout_seconds: int,
    *,
    seen_task_dirs: set[str] | None = None,
) -> tuple[Path | None, dict[str, Any]]:
    deadline = time.monotonic() + max(1, timeout_seconds)
    latest_dir: Path | None = None
    latest_payload: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest_dir, latest_payload = _latest_operator_result_for_sprint(
            harness_dir,
            sprint_id,
            seen_task_dirs=seen_task_dirs,
        )
        if str(latest_payload.get("status") or "").lower() in {"completed", "failed", "timeout", "cancelled"}:
            return latest_dir, latest_payload
        time.sleep(2)
    return latest_dir, latest_payload


def _wait_for_workflow_route(
    harness_dir: Path,
    sprint_id: str,
    env: dict[str, str],
    timeout_seconds: int,
) -> tuple[str, list[dict[str, Any]]]:
    """Wait for the asynchronous coordinator projection before the next wake."""

    deadline = time.monotonic() + max(1, timeout_seconds)
    observations: list[dict[str, Any]] = []
    route = ""
    while time.monotonic() < deadline:
        proc = subprocess.run(
            [
                sys.executable,
                str(harness_dir / "lib" / "workflow_guard.py"),
                "route",
                sprint_id,
                "--field",
                "route_role",
            ],
            cwd=harness_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        route = proc.stdout.strip().lower()
        observations.append(
            {
                "route": route,
                "returncode": proc.returncode,
                "stderr_tail": redact(proc.stderr[-400:]),
            }
        )
        if proc.returncode == 0 and route in {"builder", "builder_main"}:
            return route, observations
        time.sleep(2)
    return route, observations


def _prepare_user_inputs(rec: J16Recorder, project: Path, run_id: str) -> dict[str, Path]:
    replacements = {
        "{project_path}": str(project.resolve()),
        "{test_command}": f"{python_executable(rec.repo_root)} -m pytest -q",
        "{run_id}": run_id,
    }
    message_paths: list[Path] = []
    for source in sorted(USER_MESSAGE_DIR.glob("*.md")):
        text = source.read_text(encoding="utf-8")
        for needle, replacement in replacements.items():
            text = text.replace(needle, replacement)
        target = rec.user_input_dir / source.name
        target.write_text(text, encoding="utf-8")
        message_paths.append(target)
        rec.add_artifact(target, "j16-user-message", f"User message fixture {source.name}")
    conversation = rec.user_input_dir / "conversation.md"
    conversation.write_text(
        "\n\n---\n\n".join(path.read_text(encoding="utf-8") for path in message_paths) + "\n",
        encoding="utf-8",
    )
    rec.add_artifact(conversation, "j16-combined-user-conversation", required=True)
    return {"conversation": conversation, "messages_manifest": _write_json(rec.user_input_dir / "manifest.json", [str(p) for p in message_paths])}


def _prepare_project(rec: J16Recorder, tmp_path: Path, env: dict[str, str]) -> Path:
    project = tmp_path / "p22-j16" / "discount_project"
    if project.exists():
        shutil.rmtree(project)
    shutil.copytree(SAMPLE_PROJECT_DIR, project)
    git_init = rec.run("j16-git-init", ["git", "init"], cwd=project, env=env, timeout=30)
    rec.run("j16-git-config-name", ["git", "config", "user.name", "Solar J16"], cwd=project, env=env, timeout=30)
    rec.run("j16-git-config-email", ["git", "config", "user.email", "j16@example.local"], cwd=project, env=env, timeout=30)
    rec.run("j16-git-add-baseline", ["git", "add", "-A"], cwd=project, env=env, timeout=30)
    commit = rec.run("j16-git-commit-baseline", ["git", "commit", "-m", "p22-j16-baseline"], cwd=project, env=env, timeout=30)
    rec.add_assertion(
        "j16_isolated_git_fixture_created",
        git_init.returncode == 0 and commit.returncode == 0,
        {"git_init": git_init.returncode, "git_commit": commit.returncode, "project": project},
    )
    rec.add_artifact(project / "discounts.py", "j16-fixture-source", required=True)
    rec.add_artifact(project / "tests" / "test_discounts.py", "j16-fixture-tests", required=True)
    return project


def _git_changed_files(path: Path, env: dict[str, str]) -> list[str]:
    proc = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _git_diff_text(path: Path, env: dict[str, str]) -> str:
    proc = subprocess.run(
        ["git", "diff", "HEAD"],
        cwd=path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return redact(proc.stdout if proc.returncode == 0 else proc.stderr)


def _candidate_project_roots(project: Path, harness_dir: Path) -> list[Path]:
    candidates: list[Path] = [project]
    search_roots = [
        project.parent / ".worktrees",
        project.parent.parent / ".worktrees",
        harness_dir / ".worktrees",
        harness_dir.parent / ".worktrees",
        harness_dir / "run",
    ]
    for root in search_roots:
        if not root.exists():
            continue
        for path in root.rglob("discounts.py"):
            candidate = path.parent
            if (candidate / "tests" / "test_discounts.py").exists() and candidate not in candidates:
                candidates.append(candidate)
    return candidates


def _verify_repair_candidates(
    rec: J16Recorder,
    project: Path,
    harness_dir: Path,
    env: dict[str, str],
    python_cmd: str,
) -> tuple[bool, Path]:
    records: list[dict[str, Any]] = []
    verified = False
    for candidate in _candidate_project_roots(project, harness_dir):
        label = f"post-repair-pytest-{len(records) + 1}"
        proc = rec.run(label, [python_cmd, "-m", "pytest", "-q"], cwd=candidate, env=env, timeout=120)
        changed_files = _git_changed_files(candidate, env) if (candidate / ".git").exists() else []
        diff_text = _git_diff_text(candidate, env) if (candidate / ".git").exists() else ""
        diff_path = rec.artifact_dir / f"{_slug(candidate.name)}-{len(records) + 1}-repair.diff"
        diff_path.write_text(diff_text, encoding="utf-8", errors="replace")
        rec.add_artifact(diff_path, "j16-repair-diff", required=False)
        source_text = _read_text(candidate / "discounts.py")
        candidate_verified = (
            proc.returncode == 0
            and "discounts.py" in changed_files
            and "is_trial" in source_text
            and any(line.startswith(("+", "-", "@@")) for line in diff_text.splitlines())
        )
        verified = verified or candidate_verified
        records.append(
            {
                "candidate": str(candidate),
                "pytest_returncode": proc.returncode,
                "changed_files": changed_files,
                "diff_path": str(diff_path),
                "diff_line_count": len(diff_text.splitlines()),
                "verified_defect_repair": candidate_verified,
            }
        )
    summary_path = _write_json(rec.artifact_dir / "repair-candidate-summary.json", records)
    rec.add_artifact(summary_path, "j16-repair-candidate-summary", required=True)
    return verified, summary_path


def _collect_sprint_artifacts(rec: J16Recorder, harness_dir: Path, sprint_id: str) -> dict[str, Path]:
    sprint_dir = harness_dir / "sprints"
    paths = {
        "status": sprint_dir / f"{sprint_id}.status.json",
        "contract": sprint_dir / f"{sprint_id}.contract.md",
        "raw_intent": sprint_dir / f"{sprint_id}.raw_intent.json",
        "requirement_ir": sprint_dir / f"{sprint_id}.requirement_ir.json",
        "requirement_trace": sprint_dir / f"{sprint_id}.requirement_trace.json",
        "product_brief": sprint_dir / f"{sprint_id}.product-brief.md",
        "prd": sprint_dir / f"{sprint_id}.prd.md",
        "design": sprint_dir / f"{sprint_id}.design.md",
        "plan": sprint_dir / f"{sprint_id}.plan.md",
        "task_graph": sprint_dir / f"{sprint_id}.task_graph.json",
        "dispatch": sprint_dir / f"{sprint_id}.dispatch.md",
        "handoff": sprint_dir / f"{sprint_id}.handoff.md",
        "eval": sprint_dir / f"{sprint_id}.eval.md",
    }
    for name, path in paths.items():
        rec.add_artifact(path, f"j16-sprint-{name}", required=name in {"status", "contract"})
    return paths


def _text_bundle(paths: dict[str, Path], extra: dict[str, str] | None = None) -> dict[str, str]:
    bundle = {name: _read_text(path) for name, path in paths.items()}
    if extra:
        bundle.update(extra)
    return bundle


def _bundle_contains(bundle: dict[str, str], *terms: str) -> bool:
    text = "\n".join(bundle.values()).lower()
    return all(term.lower() in text for term in terms)


def _record_l2_outcomes(
    rec: J16Recorder,
    *,
    user_inputs: dict[str, Path],
    sprint_paths: dict[str, Path],
    command_summary_path: Path,
    repair_summary_path: Path,
    baseline_failed: bool,
    planner_ready: bool,
    builder_completed: bool,
    repair_verified: bool,
    eval_recorded: bool,
) -> None:
    bundle = _text_bundle(
        sprint_paths,
        {
            "conversation": _read_text(user_inputs["conversation"]),
            "repair_summary": _read_text(repair_summary_path),
            "commands": _read_text(command_summary_path),
        },
    )
    raw_or_ir_exists = sprint_paths["raw_intent"].exists() or sprint_paths["requirement_ir"].exists()
    direct_clarification_prompt = _bundle_contains(bundle, "clarifying question") or _bundle_contains(bundle, "need more information")
    plan_or_graph_exists = sprint_paths["plan"].exists() or sprint_paths["task_graph"].exists()
    constraint_terms = ("stdlib", "no new dependencies", "discounts.py", "pytest -q")

    definitions = [
        (
            "Context Scoping",
            sprint_paths["requirement_ir"] if sprint_paths["requirement_ir"].exists() else user_inputs["conversation"],
            _bundle_contains(bundle, "target repository path", "discount", "pytest"),
            "User and compiled artifacts identify repo, domain, and test context.",
            [],
        ),
        (
            "Ambiguity Resolution",
            user_inputs["conversation"],
            _bundle_contains(bundle, "missing", "priority", "constraints", "acceptance"),
            "The follow-up user messages resolve the missing scope, priority, constraints, and acceptance data.",
            ["No direct product-generated clarifying question was observed."] if not direct_clarification_prompt else [],
        ),
        (
            "Requirement Prioritization",
            user_inputs["conversation"],
            _bundle_contains(bundle, "priority", "p0", "acceptance"),
            "Priority and must-have criteria are present in the user input and compiled text.",
            [],
        ),
        (
            "Intent Classification & Compilation Variant Selection",
            sprint_paths["raw_intent"] if sprint_paths["raw_intent"].exists() else sprint_paths["requirement_ir"],
            raw_or_ir_exists and _bundle_contains(bundle, "defect", "repair"),
            "RawIntent or requirement IR shows a defect repair/build-class task.",
            [],
        ),
        (
            "Goal, Scope and Context normalization",
            sprint_paths["requirement_ir"] if sprint_paths["requirement_ir"].exists() else sprint_paths["contract"],
            _bundle_contains(bundle, "goal", "scope", "target repository path") or _bundle_contains(bundle, "discounts.py", "pytest -q"),
            "Requirement IR or contract normalizes the target goal, scope, repo, and test command.",
            [],
        ),
        (
            "Ambiguity Resolution & Readiness",
            sprint_paths["status"],
            planner_ready and _bundle_contains(bundle, "constraints", "acceptance"),
            "Resolved user clarifications plus plan readiness allowed builder dispatch.",
            ["Readiness was inferred from artifacts/status, not from an interactive clarification loop."] if not direct_clarification_prompt else [],
        ),
        (
            "Constraint Compilation",
            sprint_paths["contract"],
            _bundle_contains(bundle, *constraint_terms),
            "Compiled contract or plan preserves allowed files, stdlib-only constraint, and pytest command.",
            [],
        ),
        (
            "Build Contract Interpretation",
            sprint_paths["task_graph"] if sprint_paths["task_graph"].exists() else sprint_paths["plan"],
            plan_or_graph_exists and _bundle_contains(bundle, "trial", "pytest"),
            "Planner/task graph artifacts map the accepted requirements into build and verify work.",
            [],
        ),
        (
            "Build Preparation",
            sprint_paths["plan"] if sprint_paths["plan"].exists() else sprint_paths["task_graph"],
            planner_ready,
            "Planner artifacts or task graph exist before the builder wake command.",
            [],
        ),
        (
            "Product Integration",
            repair_summary_path,
            builder_completed and repair_verified,
            "Builder/operator path produced a bounded repair that passed independent tests.",
            [] if eval_recorded else ["Formal eval-verdict sidecar was not observed; repair evidence relies on diff and tests."],
        ),
        (
            "Defect Repair",
            repair_summary_path,
            baseline_failed and repair_verified,
            "The fixture failed before repair and passed after a real diff changed the defect area.",
            [],
        ),
    ]

    for item in OWNED_L2:
        feature = item["level_2_feature"]
        match = next(row for row in definitions if row[0] == feature)
        evidence_path = match[1] if match[1].exists() else command_summary_path
        passed = bool(match[2])
        limitations = list(match[4])
        if passed and limitations:
            status = "PASS_WITH_KNOWN_LIMITATIONS"
        elif passed:
            status = "PASS"
        elif feature in {"Intent Classification & Compilation Variant Selection"} and not raw_or_ir_exists:
            status = "NOT_TESTED"
            limitations = ["No RawIntent or requirement IR artifact was available to inspect classification."]
        else:
            status = "FAIL"
        rec.add_l2(
            item["category"],
            feature,
            status,
            match[3],
            evidence_path,
            assertion_name=f"j16_l2_{_slug(feature).lower()}",
            known_limitations=limitations,
        )


@pytest.mark.live_provider
def test_p22_j16_tmux_requirements_builder_real_user_defect_repair(repo_root: Path, tmp_path: Path) -> None:
    if os.environ.get("PHASE22_ENABLE_SERIAL_TMUX_JOURNEYS") != "1":
        pytest.skip("PHASE22_ENABLE_SERIAL_TMUX_JOURNEYS=1 is required before any TMUX operation.")

    rec = J16Recorder(repo_root)
    sandbox = tmp_path / "p22-j16-sandbox"
    harness_dir = _prepare_j16_isolated_harness(repo_root, sandbox)
    env = base_env(repo_root, sandbox, allow_live=True)
    env.update(
        {
            "HARNESS_DIR": str(harness_dir),
            "SOLAR_HARNESS_DIR": str(harness_dir),
            "SOLAR_HARNESS_SPRINTS_DIR": str(harness_dir / "sprints"),
            "SPRINTS_DIR": str(harness_dir / "sprints"),
            "SOLAR_INTENT_GATEWAY_DIR": str(harness_dir / "intent-gateway"),
            "SOLAR_KNOWLEDGE_RAW_DIR": str(harness_dir / "Knowledge" / "_raw"),
            "SOLAR_HARNESS_SESSION": f"p22-j16-product-{rec.run_id}",
            "SOLAR_HARNESS_LAB_SESSION": f"p22-j16-lab-{rec.run_id}",
            "SOLAR_HARNESS_BG_SESSION": f"p22-j16-bg-{rec.run_id}",
            "SOLAR_PANE_RUNTIME": os.environ.get("PHASE22_SELECTED_RUNTIME", os.environ.get("SOLAR_PANE_RUNTIME", "codex")),
            "PHASE22_SELECTED_RUNTIME": os.environ.get("PHASE22_SELECTED_RUNTIME", os.environ.get("SOLAR_PANE_RUNTIME", "codex")),
            "PHASE22_JOURNEY_RUN_ID": str(rec.run_id),
            "SOLAR_EPIC_AUTO_DECOMPOSE": "0",
            "SOLAR_INTENT_SOURCE_CHANNEL": "tmux_user_entry",
            "SOLAR_INTENT_ACTOR": "phase22_j16_user",
            "TERM": "dumb",
        }
    )
    selected_runtime = env["SOLAR_PANE_RUNTIME"].lower()
    preflight_path = rec.artifact_dir / "preflight.json"

    blockers: list[str] = []
    not_available: list[str] = []
    for required in [harness_dir / "solar-harness.sh", harness_dir / "lib" / "intent_gateway.py", harness_dir / "lib" / "intent_consumer.py"]:
        if not required.exists():
            not_available.append(f"Required production entrypoint is missing: {required}")
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
    for required_fixture in [SAMPLE_PROJECT_DIR / "discounts.py", SAMPLE_PROJECT_DIR / "tests" / "test_discounts.py"]:
        if not required_fixture.exists():
            blockers.append(f"Missing J16 fixture: {required_fixture}")

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
            "serial_guard": "PHASE22_ENABLE_SERIAL_TMUX_JOURNEYS=1",
        },
    )
    rec.add_artifact(preflight_path, "j16-preflight", required=True)
    if not_available:
        reason = "; ".join(not_available)
        rec.add_assertion("product_tmux_entrypoint_available", False, reason)
        _mark_l2_unavailable(rec, "NOT_AVAILABLE", preflight_path, reason)
        rec.finalize("NOT_AVAILABLE", blockers=not_available)
        return
    if blockers:
        reason = "; ".join(blockers)
        rec.add_assertion("serial_tmux_environment_ready", False, reason)
        _mark_l2_unavailable(rec, "ENVIRONMENT_BLOCKED", preflight_path, reason)
        rec.finalize("ENVIRONMENT_BLOCKED", blockers=blockers)
        return

    project = _prepare_project(rec, tmp_path, env)
    user_inputs = _prepare_user_inputs(rec, project, str(rec.run_id))
    python_cmd = python_executable(repo_root)
    baseline = rec.run("baseline-pytest-fails-before-product-repair", [python_cmd, "-m", "pytest", "-q"], cwd=project, env=env, timeout=120)
    baseline_failed = baseline.returncode != 0
    rec.add_assertion(
        "baseline_defect_reproduced_before_tmux_builder",
        baseline_failed,
        {"returncode": baseline.returncode, "stdout_tail": baseline.stdout[-400:], "stderr_tail": baseline.stderr[-400:]},
    )

    user_socket = f"p22j16user{os.getpid()}"
    user_session = f"p22-j16-user-{os.getpid()}"
    tmux_started = False
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
            _mark_l2_unavailable(rec, "ENVIRONMENT_BLOCKED", preflight_path, "TMUX user session could not be started.")
            rec.finalize("ENVIRONMENT_BLOCKED", blockers=["TMUX user session could not be started."])
            return

        harness_script = harness_dir / "solar-harness.sh"
        start_cmd = f"TERM=dumb bash {_shell_path(harness_script)} start --skip-doctor --clean {_shell_path(project)}"
        start_record = rec.run_in_user_tmux(user_socket, user_session, "harness-start", start_cmd, env=env, timeout=180)
        rec.add_assertion("harness_started_from_user_tmux", start_record["inner_exit_code"] == 0, start_record)

        intake_cmd = f"TERM=dumb bash {_shell_path(harness_script)} intake --file {_shell_path(user_inputs['conversation'])} --no-dispatch"
        intake_record = rec.run_in_user_tmux(user_socket, user_session, "harness-intake-no-dispatch", intake_cmd, env=env, timeout=240)
        intake_stdout = _read_text(rec.run_dir / intake_record["stdout_path"])
        intake_stderr = _read_text(rec.run_dir / intake_record["stderr_path"])
        sprint_id = _find_sprint_id(f"{intake_stdout}\n{intake_stderr}")
        rec.add_assertion("harness_intake_created_sprint", intake_record["inner_exit_code"] == 0 and bool(sprint_id), intake_record)
        if not sprint_id:
            _write_json(rec.artifact_dir / "tmux-command-summary.json", rec.tmux_user_commands)
            rec.finalize("FAIL", blockers=["Could not parse sprint id from harness intake output."])
            return

        sprint_paths = _collect_sprint_artifacts(rec, harness_dir, sprint_id)
        seen_operator_dirs = {_task_dir_key(task_dir) for task_dir in _operator_task_dirs(harness_dir)}
        wake_timeout = int(os.environ.get("PHASE22_J16_WAKE_TIMEOUT_SECONDS", "900"))
        operator_wait = int(os.environ.get("PHASE22_J16_OPERATOR_WAIT_SECONDS", str(wake_timeout)))

        planner_cmd = f"TERM=dumb bash {_shell_path(harness_script)} wake {shlex.quote(sprint_id)}"
        planner_record = rec.run_in_user_tmux(user_socket, user_session, "wake-planner", planner_cmd, env=env, timeout=wake_timeout)
        planner_dir, planner_result = _wait_for_operator_result(harness_dir, sprint_id, operator_wait, seen_task_dirs=seen_operator_dirs)
        if planner_dir is not None:
            seen_operator_dirs.add(_task_dir_key(planner_dir))
            rec.add_artifact(planner_dir / "result.json", "j16-planner-result", required=False)
            rec.add_artifact(planner_dir / "codex-last-message.md", "j16-planner-last-message", required=False)
            rec.add_artifact(planner_dir / "output.log", "j16-planner-output-log", required=False)
        planner_ready = (
            planner_record["inner_exit_code"] == 0
            and (sprint_paths["plan"].exists() or sprint_paths["task_graph"].exists())
            and str(planner_result.get("status") or "").lower() in {"completed", ""}
        )
        rec.add_assertion(
            "planner_artifacts_created_before_builder",
            planner_ready,
            {
                "wake_exit": planner_record["inner_exit_code"],
                "planner_result": planner_result,
                "plan_exists": sprint_paths["plan"].exists(),
                "task_graph_exists": sprint_paths["task_graph"].exists(),
            },
        )

        route_timeout = int(os.environ.get("PHASE22_J16_ROUTE_WAIT_SECONDS", "240"))
        compiled_route, compile_route_observations = _wait_for_workflow_route(
            harness_dir,
            sprint_id,
            env,
            route_timeout,
        )
        compile_route_evidence_path = _write_json(
            rec.artifact_dir / "workflow-route-after-planner-closeout.json",
            {
                "final_route": compiled_route,
                "observations": compile_route_observations,
                "timeout_seconds": route_timeout,
            },
        )
        rec.add_artifact(compile_route_evidence_path, "j16-workflow-route-after-planner-closeout", required=True)
        rec.add_assertion(
            "planner_compile_reached_builder_route",
            compiled_route in {"builder", "builder_main"},
            compile_route_evidence_path,
        )
        if compiled_route not in {"builder", "builder_main"}:
            rec.finalize("FAIL", blockers=["Planner closeout did not reach a certified builder route."])
            return

        approve_cmd = (
            f"TERM=dumb bash {_shell_path(harness_script)} plan-verdict {shlex.quote(sprint_id)} "
            "approve 'user confirmed scope constraints priority and acceptance'"
        )
        approve_record = rec.run_in_user_tmux(user_socket, user_session, "plan-verdict-approve", approve_cmd, env=env, timeout=120)
        rec.add_assertion("plan_verdict_approved_from_user_tmux", approve_record["inner_exit_code"] == 0, approve_record)

        approved_route, approved_route_observations = _wait_for_workflow_route(
            harness_dir,
            sprint_id,
            env,
            min(route_timeout, 60),
        )
        approved_route_evidence_path = _write_json(
            rec.artifact_dir / "workflow-route-after-plan-approval.json",
            {
                "final_route": approved_route,
                "observations": approved_route_observations,
                "timeout_seconds": min(route_timeout, 60),
            },
        )
        rec.add_artifact(approved_route_evidence_path, "j16-workflow-route-after-plan-approval", required=True)
        rec.add_assertion(
            "plan_approval_preserved_builder_route",
            approved_route in {"builder", "builder_main"},
            approved_route_evidence_path,
        )
        if approved_route not in {"builder", "builder_main"}:
            rec.finalize("FAIL", blockers=["Plan approval did not preserve the certified builder route."])
            return

        builder_cmd = f"TERM=dumb bash {_shell_path(harness_script)} wake {shlex.quote(sprint_id)}"
        builder_record = rec.run_in_user_tmux(user_socket, user_session, "wake-builder", builder_cmd, env=env, timeout=wake_timeout)
        builder_dir, builder_result = _wait_for_operator_result(harness_dir, sprint_id, operator_wait, seen_task_dirs=seen_operator_dirs)
        if builder_dir is not None:
            seen_operator_dirs.add(_task_dir_key(builder_dir))
            rec.add_artifact(builder_dir / "result.json", "j16-builder-result", required=False)
            rec.add_artifact(builder_dir / "codex-last-message.md", "j16-builder-last-message", required=False)
            rec.add_artifact(builder_dir / "output.log", "j16-builder-output-log", required=False)
        builder_completed = (
            builder_record["inner_exit_code"] == 0
            and str(builder_result.get("status") or "").lower() in {"completed", ""}
        )
        rec.add_assertion("builder_wake_executed_from_user_tmux", builder_record["inner_exit_code"] == 0, builder_record)

        repair_verified, repair_summary_path = _verify_repair_candidates(rec, project, harness_dir, env, python_cmd)
        rec.add_assertion("scoped_defect_repair_verified_by_diff_and_tests", repair_verified, repair_summary_path)

        eval_recorded = False
        if repair_verified:
            eval_cmd = (
                f"TERM=dumb bash {_shell_path(harness_script)} eval-verdict {shlex.quote(sprint_id)} "
                "pass 'independent diff and pytest verification passed'"
            )
            eval_record = rec.run_in_user_tmux(user_socket, user_session, "eval-verdict-pass", eval_cmd, env=env, timeout=120)
            eval_recorded = eval_record["inner_exit_code"] == 0 and sprint_paths["eval"].exists()
            rec.add_assertion("eval_verdict_recorded_after_verified_repair", eval_record["inner_exit_code"] == 0, eval_record)
        else:
            rec.add_assertion(
                "eval_verdict_not_submitted_after_failed_repair_checks",
                True,
                "Independent repair checks did not pass, so the test refused to submit eval pass.",
            )

        command_summary_path = _write_json(rec.artifact_dir / "tmux-command-summary.json", rec.tmux_user_commands)
        rec.add_artifact(command_summary_path, "j16-tmux-command-summary", required=True)
        sprint_paths = _collect_sprint_artifacts(rec, harness_dir, sprint_id)
        _record_l2_outcomes(
            rec,
            user_inputs=user_inputs,
            sprint_paths=sprint_paths,
            command_summary_path=command_summary_path,
            repair_summary_path=repair_summary_path,
            baseline_failed=baseline_failed,
            planner_ready=planner_ready,
            builder_completed=builder_completed,
            repair_verified=repair_verified,
            eval_recorded=eval_recorded,
        )

        limitations = []
        if any(item["status"] == "PASS_WITH_KNOWN_LIMITATIONS" for item in rec.observed_l2):
            limitations.append("Some L2 evidence is indirect or lacks direct product-generated clarification prompts.")
        if repair_verified and not eval_recorded:
            limitations.append("Formal eval sidecar was not observed; diff and pytest remain the durable repair evidence.")

        required_assertions = {
            item["name"]: item["passed"]
            for item in rec.assertions
            if item["name"]
            in {
                "baseline_defect_reproduced_before_tmux_builder",
                "tmux_user_session_started",
                "harness_started_from_user_tmux",
                "harness_intake_created_sprint",
                "planner_artifacts_created_before_builder",
                "planner_compile_reached_builder_route",
                "plan_verdict_approved_from_user_tmux",
                "plan_approval_preserved_builder_route",
                "builder_wake_executed_from_user_tmux",
                "scoped_defect_repair_verified_by_diff_and_tests",
            }
        }
        if not all(required_assertions.values()):
            provider_auth_blocker = _operator_provider_auth_blocker(harness_dir, sprint_id)
            if provider_auth_blocker:
                rec.add_assertion("live_provider_auth_available", False, provider_auth_blocker)
                _mark_l2_unavailable(rec, "ENVIRONMENT_BLOCKED", preflight_path, provider_auth_blocker)
                rec.finalize("ENVIRONMENT_BLOCKED", blockers=[provider_auth_blocker])
                return
            rec.finalize("FAIL", blockers=["One or more required J16 assertions failed."])
            return

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
