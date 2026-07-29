from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
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
    return path.read_text(encoding="utf-8", errors="replace")


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
        for category, feature in J02_PLANNED_L2:
            rec.add_l2(
                category,
                feature,
                "J02 live coding journey was blocked by local runtime/platform preflight before sprint creation or provider invocation.",
                rec.run_dir / "commands.json",
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

    natural_request = _read_text(request_file).strip()
    rec.add_assertion("intake_is_natural_language", bool(natural_request), request_file)
    augmented_request = f"{natural_request}\nRun context id: {run_id}"

    target_file = project / "calculator.py"
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
    handoff_path = sprint_dir / f"{sprint_id}.handoff.md"
    eval_path = sprint_dir / f"{sprint_id}.eval.md"

    rec.add_assertion("contract_created", contract_path.exists(), contract_path)
    rec.add_assertion("sprint_status_file_exists", status_path.exists(), status_path)

    contract_text = _read_text(contract_path)
    rec.add_assertion(
        "contract_has_requirement_section",
        "## Requirements" in contract_text or "Requirements" in contract_text,
        str(contract_path),
    )
    rec.add_assertion(
        "contract_refers_to_natural_request",
        "calculator" in contract_text.lower() and "defect" in contract_text.lower(),
        {"contract_path": str(contract_path), "run_id": run_id},
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
        timeout=240,
    )
    rec.add_assertion("builder_wake_command", wake.returncode == 0, wake.returncode)
    dispatch_text = _read_text(dispatch_path)
    rec.add_assertion("builder_dispatch_file_present", bool(dispatch_path.exists()), dispatch_path)
    rec.add_assertion(
        "builder_dispatch_referenced_after_approval",
        "Builder" in dispatch_text or "builder" in dispatch_text.lower(),
        dispatch_text[:320] if dispatch_text else "",
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
        str(sprint_status_after_wake.get("status") or "").lower() in {"built", "ready", "done", "completed", "passed", "eval_pass"},
        {
            "pre_plan_status": sprint_status_before.get("status"),
            "post_wake_status": sprint_status_after_wake.get("status"),
        },
    )
    rec.add_artifact(status_path, "j02-sprint-status")
    if plan_path.exists():
        rec.add_artifact(plan_path, "j02-sprint-plan")
    if handoff_path.exists():
        rec.add_artifact(handoff_path, "j02-sprint-handoff")

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

    eval_verdict = rec.run(
        "evaluator_verdict_pass_after_verification",
        bash_argv(repo_root, str(harness_script), "eval-verdict", sprint_id, "pass", "implementation reviewed after tests and diff checks"),
        cwd=project,
        env=env,
        timeout=120,
    )
    rec.add_assertion("evaluator_verdict_command_ok", eval_verdict.returncode == 0, eval_verdict.returncode)

    sprint_status_final = _read_json_payload(status_path)
    final_status = str(sprint_status_final.get("status") or "")
    rec.add_assertion(
        "evaluator_verdict_recorded",
        _usable_status(final_status),
        {"status": final_status, "status_file": str(status_path)},
    )
    evaluator_path_present = eval_path.exists() and eval_path.stat().st_size > 0
    rec.add_assertion("evaluator_path_present", evaluator_path_present, eval_path.stat().st_size if eval_path.exists() else "missing")
    if evaluator_path_present:
        rec.add_artifact(eval_path, "j02-eval-verdict")

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

    rec.add_artifact(request_file, "j02-intake-request")
    rec.add_artifact(contract_path, "j02-sprint-contract", required=True)

    for category, feature in J02_PLANNED_L2:
        rec.add_l2(
            category,
            feature,
            "Sprint created, plan approved before builder, real diff and tests verified, then explicit evaluator verdict and final status were recorded.",
            rec.run_dir / "commands.json",
            all(item["passed"] for item in rec.assertions),
        )

    if not all(item["passed"] for item in rec.assertions):
        rec.finalize("FAIL", blockers=["One or more required J02 assertions failed."])
        return

    rec.finalize("PASS")
