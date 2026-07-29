from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from evidence import JourneyRecorder, command_exists
from journey_runner import bash_argv, bash_blocker, base_env, has_live_authorization


def _read_json_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8-sig", errors="replace")


def _find_sprint_id(text: str) -> str:
    match = re.search(r"Sprint created:\s*(sprint-[^\s\r\n]+)", text)
    return match.group(1) if match else ""


def _git_changed_files(path: Path, env: dict[str, str] | None = None) -> list[str]:
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
    return [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]


def _git_diff_text(path: Path, env: dict[str, str] | None = None, *, base: str = "HEAD") -> str:
    proc = subprocess.run(
        ["git", "diff", base],
        cwd=path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return proc.stdout if proc.returncode == 0 else ""


def _is_real_defect(file_path: Path) -> bool:
    return "return a - b" in file_path.read_text(encoding="utf-8", errors="replace")


def _usable_status(value: str | None) -> bool:
    state = str(value or "").lower()
    return state in {
        "completed",
        "passed",
        "eval_pass",
        "done",
        "pass",
    }


def _lookup_command_argv(name: str) -> list[str]:
    if os.name == "nt":
        return ["where.exe", name]
    shell = shutil.which("sh") or "/bin/sh"
    return [shell, "-lc", f"command -v {shlex.quote(name)}"]


def _progress_status(value: str | None) -> bool:
    state = str(value or "").lower()
    return state in {
        "approved",
        "queued",
        "building",
        "built",
        "completed",
        "passed",
        "eval_pass",
        "done",
        "ready",
        "pass",
    }


def _operator_task_dirs(harness_dir: Path) -> list[Path]:
    result_root = harness_dir / "run" / "operator-results"
    if not result_root.exists():
        return []
    task_dirs: list[Path] = []
    for operator_dir in result_root.iterdir():
        if not operator_dir.is_dir():
            continue
        for task_dir in operator_dir.iterdir():
            if task_dir.is_dir():
                task_dirs.append(task_dir)
    return sorted(task_dirs, key=lambda path: path.stat().st_mtime, reverse=True)


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
        payload = _read_json_payload(task_dir / "result.json")
        if payload.get("sprint_id") == sprint_id:
            return task_dir, payload
        envelope = _read_json_payload(task_dir / "envelope.json")
        if envelope.get("sprint_id") == sprint_id:
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
    terminal_statuses = {"completed", "failed", "timeout", "cancelled"}
    while time.monotonic() < deadline:
        latest_dir, latest_payload = _latest_operator_result_for_sprint(
            harness_dir,
            sprint_id,
            seen_task_dirs=seen_task_dirs,
        )
        status = str(latest_payload.get("status") or "").lower()
        if status in terminal_statuses:
            return latest_dir, latest_payload
        time.sleep(2)
    return latest_dir, latest_payload


def _artifact_if_present(rec: JourneyRecorder, path: Path, artifact_type: str, *, required: bool = True) -> None:
    if path.exists():
        rec.add_artifact(path, artifact_type, required=required)


J02_PLANNED_L2 = [
    ("Workflow", "Request Capture"),
    ("Workflow", "Intake Context Binding"),
    ("Workflow", "Intake Provenance Registration"),
    ("Workflow", "Intent Interpretation"),
    ("Workflow", "Constraint Resolution"),
    ("Workflow", "Acceptance Definition"),
    ("Workflow", "Requirement Contract Confirmation"),
    ("Workflow", "POC Construction"),
    ("Workflow", "POC Functional Readiness Validation"),
    ("Workflow", "Evaluation Scope & Evidence Assembly"),
    ("Workflow", "Claim & Acceptance-Criteria Comparison"),
    ("Workflow", "Verdict, Blocker & Residual-Risk Classification"),
    ("Foundation", "Task Contract & Acceptance Compilation"),
    ("Foundation", "Task Contract Decomposition"),
    ("Foundation", "TaskGraph Construction"),
    ("Foundation", "TaskGraph Validation & Feasibility Analysis"),
    ("Foundation", "DAG Scheduler, TaskGraph Readiness & Operator Binding"),
    ("Foundation", "Main Loop Dispatch & Runtime Supervision"),
    ("Foundation", "Code Construction"),
    ("Foundation", "Verification Asset Construction"),
    ("Foundation", "Engineering Correctness & Code Quality Evaluator"),
    ("Foundation", "TaskGraph Persistence & Lifecycle Management"),
]


def _record_j02_l2(rec: JourneyRecorder, observation: str, supported: bool | str) -> None:
    for category, feature in J02_PLANNED_L2:
        rec.add_l2(
            category,
            feature,
            observation,
            rec.run_dir / "commands.json",
            supported,
        )


@pytest.mark.live_provider
def test_p22_j02_live_coding_task(repo_root: Path, tmp_path: Path) -> None:
    rec = JourneyRecorder(repo_root, "P22-J02")

    git_probe = rec.run("preflight_git_version", ["git", "--version"], timeout=30)
    bash_probe = rec.run("preflight_bash_lookup", _lookup_command_argv("bash"), timeout=30)
    tmux_probe = rec.run("preflight_tmux_lookup", _lookup_command_argv("tmux"), timeout=30)
    rec.add_assertion(
        "preflight_commands_recorded",
        True,
        {
            "git_exit": git_probe.returncode,
            "bash_lookup_exit": bash_probe.returncode,
            "tmux_lookup_exit": tmux_probe.returncode,
        },
    )

    blockers: list[str] = []
    if not has_live_authorization():
        blockers.append(
            "PHASE22_ENABLE_LIVE_JOURNEYS=1 was not set; live provider execution was not authorized."
        )

    bash_error = bash_blocker(repo_root)
    if bash_error is not None:
        blockers.append(bash_error)

    fixture_root = Path(__file__).resolve().parents[1] / "fixtures" / "j02_j05"
    request_file = fixture_root / "j02_intake_request.txt"
    fixture_repo = fixture_root / "j02_repo"
    expectations_file = fixture_root / "j02_expectations.json"
    expectations = _read_json_payload(expectations_file)

    expected_modified_files = [str(item) for item in expectations.get("expected_modified_files", ["calculator.py"])]
    max_modified_files = int(expectations.get("max_modified_files", 2))
    baseline_cmd = expectations.get("baseline_command", ["-q"])
    run_id = str(expectations.get("run_id", "p22-j02-live-coding"))
    selected_runtime = str(
        os.environ.get("PHASE22_SELECTED_RUNTIME", os.environ.get("SOLAR_PANE_RUNTIME", expectations.get("runtime", "codex")))
    ).lower()

    for needed in [request_file, fixture_repo, expectations_file]:
        if not needed.exists():
            blockers.append(f"Missing required J02 fixture: {needed}")

    required_files = [fixture_repo / "calculator.py", fixture_repo / "test_calculator.py"]
    if not all(item.exists() for item in required_files):
        blockers.append("Fixture repo missing calculator and test files needed for repair reproduction.")

    if not command_exists("git"):
        blockers.append("git is not available on PATH.")
    if not command_exists("tmux"):
        blockers.append("tmux is not available on PATH.")
    if not command_exists("bash"):
        blockers.append("bash is not available on PATH.")

    if selected_runtime not in {"codex", "claude"}:
        blockers.append(f"Unsupported runtime identity in request/environment: {selected_runtime}")

    if blockers:
        for blocker in blockers:
            rec.add_assertion("environment_gate", False, blocker)
        _record_j02_l2(
            rec,
            "J02 live coding journey was blocked by local runtime/platform preflight before sprint creation or provider invocation.",
            False,
        )
        rec.finalize("ENVIRONMENT_BLOCKED", blockers=blockers)
        return

    sandbox = tmp_path / "p22-j02"
    project = sandbox / "repo"
    if project.exists():
        shutil.rmtree(project)
    shutil.copytree(fixture_repo, project)

    rec.add_assertion(
        "j02_isolated_repo_created",
        project.exists() and project.is_dir(),
        str(project),
    )
    rec.add_assertion(
        "fixture_repo_is_reproducible",
        all(item.exists() for item in required_files),
        [str(item) for item in required_files],
    )

    env = base_env(repo_root, sandbox, allow_live=True)
    env["SOLAR_PANE_RUNTIME"] = selected_runtime
    env["PHASE22_SELECTED_RUNTIME"] = selected_runtime
    env["PHASE22_JOURNEY_RUN_ID"] = run_id

    git_init = rec.run("git_init", ["git", "init"], cwd=project, env=env, timeout=30)
    git_config_name = rec.run("git_config_name", ["git", "config", "user.name", "Solar J02 Repair"], cwd=project, env=env, timeout=30)
    git_config_email = rec.run(
        "git_config_email",
        ["git", "config", "user.email", "j02-repair@example.local"],
        cwd=project,
        env=env,
        timeout=30,
    )
    baseline_add = rec.run("baseline_stage", ["git", "add", "-A"], cwd=project, env=env, timeout=30)
    baseline_commit = rec.run("baseline_commit", ["git", "commit", "-m", f"{run_id}-baseline"], cwd=project, env=env, timeout=30)

    rec.add_assertion(
        "j02_repo_is_git_isolated",
        git_init.returncode == 0
        and git_config_name.returncode == 0
        and git_config_email.returncode == 0
        and baseline_add.returncode == 0
        and baseline_commit.returncode == 0,
        {
            "git_init": git_init.returncode,
            "git_add": baseline_add.returncode,
            "git_commit": baseline_commit.returncode,
            "stderr": baseline_commit.stderr[-400:],
        },
    )

    rec.add_assertion("runtime_identity_selected", selected_runtime in {"codex", "claude"}, selected_runtime)
    rec.add_assertion(
        "selected_runtime_visible_in_env",
        env.get("SOLAR_PANE_RUNTIME") == selected_runtime and env.get("PHASE22_SELECTED_RUNTIME") == selected_runtime,
        {
            "SOLAR_PANE_RUNTIME": env.get("SOLAR_PANE_RUNTIME"),
            "PHASE22_SELECTED_RUNTIME": env.get("PHASE22_SELECTED_RUNTIME"),
        },
    )

    target_file = project / "calculator.py"
    natural_request = _read_text(request_file).strip()
    rec.add_assertion("intake_is_natural_language", bool(natural_request), request_file)
    augmented_request = (
        f"{natural_request}\n"
        f"Target repository path: {project}\n"
        f"Target implementation file: {target_file}\n"
        f"Only modify files under {project}; do not edit source fixtures or files outside this target repository.\n"
        f"Run context id: {run_id}"
    )

    rec.add_assertion("defect_is_real_and_reproducible", _is_real_defect(target_file), _read_text(target_file)[:120])

    # Verify baseline behavior is a failure before any repair step.
    baseline = rec.run(
        "baseline_test_fails_before_repair",
        [sys.executable, "-m", "pytest", *baseline_cmd],
        cwd=project,
        env=env,
        timeout=90,
    )
    rec.add_assertion(
        "baseline_test_fails_for_known_defect",
        baseline.returncode != 0,
        {
            "returncode": baseline.returncode,
            "stdout_tail": baseline.stdout[-400:],
            "stderr_tail": baseline.stderr[-400:],
        },
    )

    install = rec.run(
        "install_solar_for_live_repair",
        [
            *bash_argv(
                repo_root,
                str(repo_root / "install.sh"),
            ),
            "--yes",
            "--components",
            "kernel,harness",
            "--solar-home",
            env["SOLAR_HOME"],
            "--claude-dir",
            env["CLAUDE_DIR"],
        ],
        cwd=project,
        env=env,
        timeout=240,
    )
    rec.add_assertion("solar_install_ok", install.returncode == 0, install.returncode)
    installed_harness = Path(env["SOLAR_HOME"]) / "harness"
    env["HARNESS_DIR"] = str(installed_harness)
    env["SOLAR_HARNESS_DIR"] = str(installed_harness)
    env["AUTOSCI_ARTIFACT_ROOT"] = str(installed_harness / "artifacts" / "autosci")
    env["SCIENTIFIC_ARTIFACT_ROOT"] = str(installed_harness / "artifacts" / "scientific")
    env["SOLAR_AUTOSCI_OUTPUT_HARNESS"] = str(installed_harness)

    harness_script = repo_root / "harness" / "solar-harness.sh"
    intake = rec.run(
        "harness_sprint_create",
        bash_argv(repo_root, str(harness_script), "sprint", augmented_request),
        cwd=project,
        env=env,
        timeout=180,
    )
    rec.add_assertion("harness_sprint_created", intake.returncode == 0, intake.returncode)

    combined_output = f"{intake.stdout or ''}\n{intake.stderr or ''}"
    sprint_id = _find_sprint_id(combined_output)
    rec.add_assertion("sprint_id_parsed", bool(sprint_id), {"run_id": run_id, "output_tail": combined_output[-240:]})
    if not sprint_id:
        rec.finalize("FAIL", blockers=["Could not parse sprint id from harness sprint output."])
        return

    sprint_dir = Path(env["HARNESS_DIR"]) / "sprints"
    contract_path = sprint_dir / f"{sprint_id}.contract.md"
    status_path = sprint_dir / f"{sprint_id}.status.json"
    dispatch_path = sprint_dir / f"{sprint_id}.dispatch.md"
    plan_path = sprint_dir / f"{sprint_id}.plan.md"
    design_path = sprint_dir / f"{sprint_id}.design.md"
    task_graph_path = sprint_dir / f"{sprint_id}.task_graph.json"
    handoff_path = sprint_dir / f"{sprint_id}.handoff.md"
    eval_path = sprint_dir / f"{sprint_id}.eval.md"
    requirement_ir_path = sprint_dir / f"{sprint_id}.requirement_ir.json"
    wake_timeout_seconds = int(os.environ.get("PHASE22_J02_WAKE_TIMEOUT_SECONDS", "900"))
    operator_wait_seconds = int(os.environ.get("PHASE22_J02_OPERATOR_WAIT_SECONDS", str(wake_timeout_seconds)))
    limitations: list[str] = []

    # Run-level artifact that ties sprint id and run id together for explicit handoff review.
    run_link = sandbox / f"{run_id}-correlation.json"
    run_link_payload = {
        "run_id": run_id,
        "sprint_id": sprint_id,
        "request_artifact": str(request_file),
        "status_artifact": str(status_path),
        "contract_artifact": str(contract_path),
        "dispatch_artifact": str(dispatch_path),
    }
    run_link.write_text(json.dumps(run_link_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rec.add_artifact(run_link, "j02-run-linkage")
    run_link_payload_read = _read_json_payload(run_link)
    rec.add_assertion(
        "run_id_links_to_sprint_id",
        run_link_payload_read.get("run_id") == run_id and run_link_payload_read.get("sprint_id") == sprint_id,
        run_link_payload,
    )

    rec.add_assertion("contract_created", contract_path.exists(), contract_path)
    rec.add_assertion("sprint_status_file_exists", status_path.exists(), status_path)

    contract_text = _read_text(contract_path)
    compiled_context_text = "\n".join(
        [
            contract_text,
            _read_text(requirement_ir_path),
            _read_text(status_path),
            augmented_request,
        ]
    ).lower()
    rec.add_assertion(
        "contract_has_requirement_section",
        "## Product Contract" in contract_text
        and "## Agent Execution Contract" in contract_text
        and "requirement_ir.json" in contract_text,
        str(contract_path),
    )
    rec.add_assertion(
        "contract_refers_to_natural_request",
        "calculator" in compiled_context_text
        and ("defect" in compiled_context_text or "bug" in compiled_context_text)
        and ("a + b" in compiled_context_text or "result equals" in compiled_context_text),
        {
            "contract_path": str(contract_path),
            "requirement_ir_path": str(requirement_ir_path),
            "run_id": run_id,
        },
    )

    sprint_status_before = _read_json_payload(status_path)
    rec.add_assertion(
        "sprint_status_bootstrapped",
        sprint_status_before.get("status") == "drafting",
        sprint_status_before,
    )
    rec.add_assertion(
        "sprint_id_roundtripped",
        str(sprint_status_before.get("id", "")) == sprint_id and str(sprint_status_before.get("id", "")).startswith("sprint-"),
        {"sprint_id": sprint_id, "status_id": sprint_status_before.get("id")},
    )
    rec.add_assertion(
        "intake_context_carries_run_id",
        run_id in augmented_request,
        {"run_id": run_id, "request_excerpt": augmented_request[-120:]},
    )

    seen_operator_dirs = {_task_dir_key(task_dir) for task_dir in _operator_task_dirs(installed_harness)}
    planner_wake = rec.run(
        "wake_planner_after_intake",
        bash_argv(repo_root, str(harness_script), "wake", sprint_id),
        cwd=project,
        env=env,
        timeout=wake_timeout_seconds,
    )
    rec.add_assertion("planner_wake_command", planner_wake.returncode == 0, planner_wake.returncode)

    planner_task_dir, planner_result = _wait_for_operator_result(
        installed_harness,
        sprint_id,
        operator_wait_seconds,
        seen_task_dirs=seen_operator_dirs,
    )
    if planner_task_dir is not None:
        seen_operator_dirs.add(_task_dir_key(planner_task_dir))
    planner_completed = (
        str(planner_result.get("status") or "").lower() == "completed"
        and int(planner_result.get("exit_code", -1)) == 0
    )
    rec.add_assertion(
        "live_planner_result_completed",
        planner_completed,
        {
            "operator_task_dir": str(planner_task_dir) if planner_task_dir else "",
            "status": planner_result.get("status"),
            "exit_code": planner_result.get("exit_code"),
            "wait_seconds": operator_wait_seconds,
        },
    )
    if planner_task_dir is not None:
        _artifact_if_present(rec, planner_task_dir / "result.json", "j02-live-planner-result")
        _artifact_if_present(rec, planner_task_dir / "codex-last-message.md", "j02-live-planner-last-message", required=False)
        _artifact_if_present(rec, planner_task_dir / "output.log", "j02-live-planner-output-log", required=False)
        _artifact_if_present(rec, planner_task_dir / "codex-cli-output.log", "j02-live-planner-cli-log", required=False)

    planner_dispatch_text = _read_text(dispatch_path)
    rec.add_artifact(dispatch_path, "j02-planner-dispatch")
    rec.add_assertion(
        "planner_dispatch_referenced_after_intake",
        "planner" in f"{planner_dispatch_text}\n{planner_wake.stdout or ''}\n{planner_wake.stderr or ''}".lower(),
        (planner_dispatch_text or planner_wake.stdout or planner_wake.stderr)[:320],
    )
    planner_artifacts_ok = plan_path.exists() and design_path.exists() and task_graph_path.exists()
    rec.add_assertion(
        "planner_artifacts_created",
        planner_artifacts_ok,
        {
            "plan": plan_path.stat().st_size if plan_path.exists() else "missing",
            "design": design_path.stat().st_size if design_path.exists() else "missing",
            "task_graph": task_graph_path.stat().st_size if task_graph_path.exists() else "missing",
        },
    )
    if design_path.exists():
        rec.add_artifact(design_path, "j02-sprint-design")
    if task_graph_path.exists():
        rec.add_artifact(task_graph_path, "j02-sprint-task-graph")

    if not planner_completed or not planner_artifacts_ok:
        rec.add_artifact(status_path, "j02-sprint-status")
        rec.add_artifact(request_file, "j02-intake-request")
        rec.add_artifact(contract_path, "j02-sprint-contract", required=True)
        _record_j02_l2(
            rec,
            "Live provider execution reached Planner, but required plan/design/task-graph artifacts were not completed before Builder dispatch.",
            False,
        )
        rec.finalize(
            "FAIL",
            blockers=["Planner did not complete required plan/design/task-graph artifacts before builder dispatch."],
        )
        return

    plan = rec.run(
        "plan_verdict_approve",
        bash_argv(
            repo_root,
            str(harness_script),
            "plan-verdict",
            sprint_id,
            "approve",
            "coding task is accepted",
        ),
        cwd=project,
        env=env,
        timeout=120,
    )
    rec.add_assertion("plan_verdict_command_ok", plan.returncode == 0, plan.returncode)

    sprint_status_after_plan = _read_json_payload(status_path)
    rec.add_assertion("plan_verdict_updates_status", _progress_status(sprint_status_after_plan.get("status")), sprint_status_after_plan.get("status"))

    wake = rec.run(
        "wake_builder_after_plan_approval",
        bash_argv(repo_root, str(harness_script), "wake", sprint_id),
        cwd=project,
        env=env,
        timeout=wake_timeout_seconds,
    )
    rec.add_assertion("builder_wake_command", wake.returncode == 0, wake.returncode)
    operator_task_dir, operator_result = _wait_for_operator_result(
        installed_harness,
        sprint_id,
        operator_wait_seconds,
        seen_task_dirs=seen_operator_dirs,
    )
    if operator_task_dir is not None:
        seen_operator_dirs.add(_task_dir_key(operator_task_dir))
    operator_completed = (
        str(operator_result.get("status") or "").lower() == "completed"
        and int(operator_result.get("exit_code", -1)) == 0
    )
    rec.add_assertion(
        "live_operator_result_completed",
        operator_completed,
        {
            "operator_task_dir": str(operator_task_dir) if operator_task_dir else "",
            "status": operator_result.get("status"),
            "exit_code": operator_result.get("exit_code"),
            "wait_seconds": operator_wait_seconds,
        },
    )
    if operator_task_dir is not None:
        _artifact_if_present(rec, operator_task_dir / "result.json", "j02-live-operator-result")
        _artifact_if_present(rec, operator_task_dir / "codex-last-message.md", "j02-live-operator-last-message", required=False)
        _artifact_if_present(rec, operator_task_dir / "output.log", "j02-live-operator-output-log", required=False)
        _artifact_if_present(rec, operator_task_dir / "codex-cli-output.log", "j02-live-operator-cli-log", required=False)

    dispatch_text = _read_text(dispatch_path)
    wake_text = f"{wake.stdout or ''}\n{wake.stderr or ''}"
    rec.add_assertion("builder_dispatch_file_present", bool(dispatch_path.exists()), dispatch_path)
    rec.add_assertion(
        "builder_dispatch_referenced_after_approval",
        "builder" in f"{dispatch_text}\n{wake_text}".lower(),
        (dispatch_text or wake_text)[:320],
    )
    rec.add_assertion(
        "plan_or_target_artifact_exists",
        plan_path.exists() or handoff_path.exists(),
        {"plan": str(plan_path), "handoff": str(handoff_path)},
    )

    sprint_status_after_wake = _read_json_payload(status_path)
    rec.add_artifact(dispatch_path, "j02-sprint-dispatch")
    rec.add_assertion(
        "builder_status_advanced_after_wake",
        operator_completed
        or str(sprint_status_after_wake.get("status") or "").lower()
        in {"built", "ready", "done", "completed", "passed", "eval_pass", "reviewing"},
        {
            "pre_plan_status": sprint_status_before.get("status"),
            "post_wake_status": sprint_status_after_wake.get("status"),
            "operator_status": operator_result.get("status"),
            "operator_exit_code": operator_result.get("exit_code"),
        },
    )
    rec.add_artifact(status_path, "j02-sprint-status")
    if plan_path.exists():
        rec.add_artifact(plan_path, "j02-sprint-plan")
    if handoff_path.exists():
        rec.add_artifact(handoff_path, "j02-sprint-handoff")
    node_id = str(operator_result.get("node_id") or "wake-builder")
    node_handoff_path = sprint_dir / f"{sprint_id}.{node_id}-handoff.md"
    pm_result_path = sprint_dir / f"{sprint_id}.{node_id}.pm-result.md"
    _artifact_if_present(rec, node_handoff_path, "j02-node-handoff", required=False)
    _artifact_if_present(rec, pm_result_path, "j02-node-pm-result", required=False)

    # Verify original target test now passes after the repair artifacts run through the workflow.
    post_repair_test = rec.run(
        "post_repair_target_tests_pass",
        [sys.executable, "-m", "pytest", *baseline_cmd],
        cwd=project,
        env=env,
        timeout=90,
    )
    rec.add_assertion("post_repair_target_tests_pass", post_repair_test.returncode == 0, post_repair_test.returncode)

    changed_files = _git_changed_files(project, env=env)
    rec.add_assertion("real_git_diff_has_changes", bool(changed_files), changed_files)
    diff_text = _git_diff_text(project, env=env)
    diff_path = sandbox / f"{run_id}-repair.diff"
    diff_path.write_text(diff_text, encoding="utf-8")
    rec.add_artifact(diff_path, "j02-real-git-diff")
    rec.add_assertion(
        "git_diff_not_placeholder",
        any(line.startswith(("+", "-", "@@")) for line in (diff_text or "").splitlines()),
        {"line_count": len((diff_text or "").splitlines()), "sample": (diff_text or "")[:240]},
    )

    # Ensure the fix stays tightly scoped, and verify the intended target changed.
    rec.add_assertion(
        "repair_scope_respected",
        bool(changed_files)
        and all(item in expected_modified_files for item in changed_files)
        and len(changed_files) <= max_modified_files,
        {
            "changed_files": changed_files,
            "expected_modified_files": expected_modified_files,
            "max_modified_files": max_modified_files,
        },
    )
    repaired_text = _read_text(target_file)
    rec.add_assertion("target_code_changed_to_addition", "return a + b" in repaired_text and "return a - b" not in repaired_text, repaired_text)

    repair_checks_passed = (
        post_repair_test.returncode == 0
        and bool(changed_files)
        and all(item in expected_modified_files for item in changed_files)
        and len(changed_files) <= max_modified_files
        and "return a + b" in repaired_text
        and "return a - b" not in repaired_text
    )
    if repair_checks_passed:
        eval_verdict = rec.run(
            "evaluator_verdict_pass_after_verification",
            bash_argv(repo_root, str(harness_script), "eval-verdict", sprint_id, "pass", "implementation reviewed after tests and diff checks"),
            cwd=project,
            env=env,
            timeout=120,
        )

        sprint_status_final = _read_json_payload(status_path)
        final_status = str(sprint_status_final.get("status") or "")
        if eval_verdict.returncode == 0:
            rec.add_assertion("evaluator_verdict_command_ok", True, eval_verdict.returncode)
            rec.add_assertion(
                "evaluator_verdict_recorded",
                _usable_status(final_status),
                {"status": final_status, "status_file": str(status_path)},
            )
            evaluator_path_present = eval_path.exists() and eval_path.stat().st_size > 0
            if evaluator_path_present:
                rec.add_assertion("evaluator_path_present", True, eval_path.stat().st_size)
                rec.add_artifact(eval_path, "j02-eval-verdict")
            else:
                limitations.append(
                    "The formal eval-verdict command accepted the sprint and updated status to a usable final state, "
                    "but the legacy eval.md sidecar was not emitted; command stdout/stderr and status.json remain the durable verdict evidence."
                )
                rec.add_assertion(
                    "evaluator_path_limitation_recorded",
                    True,
                    {"eval_path": str(eval_path), "status": final_status},
                )
        else:
            limitation = (
                "Formal eval-verdict remained blocked after live code repair/test verification. "
                f"Status={final_status or 'unknown'}; stdout_tail={(eval_verdict.stdout or '')[-240:]}; "
                f"stderr_tail={(eval_verdict.stderr or '')[-240:]}"
            )
            limitations.append(limitation)
            rec.add_assertion(
                "evaluator_verdict_limitation_recorded",
                True,
                {
                    "returncode": eval_verdict.returncode,
                    "status": final_status,
                    "stdout_tail": (eval_verdict.stdout or "")[-400:],
                    "stderr_tail": (eval_verdict.stderr or "")[-400:],
                },
            )
    else:
        rec.add_assertion(
            "evaluator_verdict_not_submitted_after_failed_repair_checks",
            True,
            {
                "reason": "Independent post-repair checks failed; refusing to record a formal PASS verdict.",
                "post_repair_returncode": post_repair_test.returncode,
                "changed_files": changed_files,
                "target_contains_addition": "return a + b" in repaired_text,
            },
        )

    rec.add_artifact(request_file, "j02-intake-request")
    rec.add_artifact(contract_path, "j02-sprint-contract", required=True)

    _record_j02_l2(
        rec,
        (
            "Sprint created, plan approved, live Codex operator completed, real diff and target tests verified. "
            "Formal evaluator verdict is recorded when the legacy graph/handoff gate accepts the sprint; otherwise retained as a known limitation."
        ),
        all(item["passed"] for item in rec.assertions),
    )

    if not all(item["passed"] for item in rec.assertions):
        rec.finalize("FAIL", blockers=["One or more required J02 assertions failed."])
        return

    rec.finalize("PASS_WITH_KNOWN_LIMITATIONS" if limitations else "PASS", limitations=limitations)
