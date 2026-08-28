"""Planner-owned, no-DAG runtime for accepted direct-answer requests."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import file_lock_compat as fcntl

from activity_runtime import ActivityRuntime
from elastic_planner import run_elastic_planning_request
from intent_compiler import CodexJsonModel
from runtime_status import transition_status


def load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def is_direct_answer_requirement(requirement_ir: dict[str, Any]) -> bool:
    hints = (
        requirement_ir.get("planner_hints")
        if isinstance(requirement_ir.get("planner_hints"), dict)
        else {}
    )
    return (
        requirement_ir.get("request_type") == "direct_answer"
        and hints.get("preferred_outcome") == "direct_answer"
        and hints.get("runtime_handoff_allowed") is False
    )


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _answer_markdown(response: dict[str, Any]) -> str:
    answer = str(response.get("answer") or "").strip()
    limitations = [
        str(item).strip()
        for item in response.get("limitations") or []
        if str(item).strip()
    ]
    if limitations:
        answer += "\n\n## Limitations\n\n" + "\n".join(
            f"- {item}" for item in limitations
        )
    return answer.rstrip() + "\n"


def _model(role: str) -> CodexJsonModel:
    role_key = role.upper()
    default_model = os.environ.get("SOLAR_DIRECT_ANSWER_MODEL", "gpt-5.5")
    model = os.environ.get(f"SOLAR_DIRECT_ANSWER_{role_key}_MODEL", default_model).strip()
    timeout = int(os.environ.get("SOLAR_DIRECT_ANSWER_TIMEOUT_SEC", "240") or "240")
    return CodexJsonModel(model=model, timeout_seconds=timeout)


def _run_direct_answer_locked(
    *,
    harness_dir: Path,
    sprint_id: str,
    planner_model: Any | None = None,
    reviewer_model: Any | None = None,
) -> dict[str, Any]:
    """Generate one Planner answer, independently review it, and terminate."""
    harness_dir = harness_dir.resolve()
    sprints_dir = harness_dir / "sprints"
    status_path = sprints_dir / f"{sprint_id}.status.json"
    requirement_path = sprints_dir / f"{sprint_id}.requirement_ir.json"
    answer_path = sprints_dir / f"{sprint_id}.answer.md"
    workdir_answer_path = (
        sprints_dir / sprint_id / "workdir" / "workspace" / "direct_response" / "answer.md"
    )
    output_root = sprints_dir / sprint_id / "workdir" / "planner"
    activity_id = "direct-answer"
    runtime = ActivityRuntime(sprint_id, harness_dir=str(harness_dir))

    requirement_ir = load_object(requirement_path)
    if not is_direct_answer_requirement(requirement_ir):
        raise ValueError("RequirementIR is not an authoritative direct-answer request")
    if answer_path.is_file():
        status = load_object(status_path)
        if str(status.get("status") or "") in {"completed", "passed"}:
            return {"status": "already_completed", "answer_path": str(answer_path)}

    runtime.activity_started(
        activity_id,
        actor="planner",
        payload={"stage": "direct_answer", "message": "Planner is writing the direct answer."},
    )
    transition_status(
        status_path,
        "active",
        "direct_answer_started",
        "elastic_planner",
        extra={
            "allow_reopen": True,
            "status_fields": {
                "phase": "direct_answer",
                "stage": "direct_answer_in_progress",
                "handoff_to": "planner",
                "target_role": "planner",
                "runtime_handoff_allowed": False,
                "direct_answer_status": "running",
                "plan_compile_required": False,
                "planner_dispatch_claim": None,
                "direct_answer_error": None,
            },
            "note": "Elastic Planner is generating the answer; no TaskGraph is running.",
        },
    )
    try:
        result = run_elastic_planning_request(
            requirement_ir,
            output_root,
            planner_model or _model("planner"),
            reviewer_model or _model("reviewer"),
            sprint_id=sprint_id,
            workspace_root="workspace",
        )
        if result.get("status") != "direct_response" or result.get("verification_errors"):
            raise RuntimeError(
                "direct response was not accepted: "
                + json.dumps(
                    {
                        "status": result.get("status"),
                        "verification_errors": result.get("verification_errors") or [],
                    },
                    ensure_ascii=False,
                )
            )
        semantic = result.get("semantic") or {}
        response = semantic.get("direct_response") or {}
        review = semantic.get("direct_response_review") or {}
        acceptance = semantic.get("plan_acceptance") or {}
        markdown = _answer_markdown(response)
        if not markdown.strip():
            raise RuntimeError("accepted direct response was empty")

        _write_text(answer_path, markdown)
        _write_text(workdir_answer_path, markdown)
        _write_json(sprints_dir / f"{sprint_id}.direct_response.json", response)
        _write_json(sprints_dir / f"{sprint_id}.direct_response_review.json", review)
        _write_json(sprints_dir / f"{sprint_id}.plan_acceptance.json", acceptance)

        runtime.activity_succeeded(
            activity_id,
            actor="planner",
            payload={
                "stage": "direct_answer",
                "result": "accepted",
                "answer_path": str(answer_path),
                "review_status": review.get("status"),
            },
        )
        transition_status(
            status_path,
            "completed",
            "direct_answer_completed",
            "elastic_planner",
            extra={
                "status_fields": {
                    "phase": "finalized",
                    "stage": "completed",
                    "handoff_to": "",
                    "target_role": "",
                    "active_node": None,
                    "open_nodes": [],
                    "failed_nodes": [],
                    "direct_answer_status": "accepted",
                    "result_path": str(answer_path),
                    "runtime_handoff_allowed": False,
                    "plan_compile_required": False,
                    "planner_dispatch_claim": None,
                },
                "note": "Planner direct answer passed one independent review; no TaskGraph was dispatched.",
            },
        )
        return {
            "status": "completed",
            "answer_path": str(answer_path),
            "review_status": review.get("status"),
        }
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        runtime.activity_failed(
            activity_id,
            actor="planner",
            error=message,
            payload={"stage": "direct_answer", "reason": "direct_answer_runtime_failed"},
        )
        transition_status(
            status_path,
            "failed",
            "direct_answer_failed",
            "elastic_planner",
            extra={
                "status_fields": {
                    "stage": "direct_answer_failed",
                    "direct_answer_status": "failed",
                    "direct_answer_error": message,
                    "runtime_handoff_allowed": False,
                },
                "note": message,
            },
        )
        raise


def run_direct_answer(
    *,
    harness_dir: Path,
    sprint_id: str,
    planner_model: Any | None = None,
    reviewer_model: Any | None = None,
) -> dict[str, Any]:
    """Serialize the whole direct-answer run so recovery cannot duplicate it."""
    harness_dir = harness_dir.resolve()
    lock_path = harness_dir / "run" / "direct-answer-locks" / f"{sprint_id}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b")
    try:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, PermissionError):
            return {"status": "already_running", "sprint_id": sprint_id}
        return _run_direct_answer_locked(
            harness_dir=harness_dir,
            sprint_id=sprint_id,
            planner_model=planner_model,
            reviewer_model=reviewer_model,
        )
    finally:
        try:
            fcntl.flock(handle, fcntl.LOCK_UN)
        except OSError:
            pass
        handle.close()
