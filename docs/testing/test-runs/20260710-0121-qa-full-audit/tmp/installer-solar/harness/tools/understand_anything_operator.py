#!/usr/bin/env python3
"""Command backend adapter for understand-anything TUI pane skill dispatch."""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "lib") not in sys.path:
    sys.path.insert(0, str(ROOT / "lib"))

from hands_runtime import PaneHand, ResultStatus  # noqa: E402
import operator_flow_control as ofc  # noqa: E402
import understand_anything_local_pipeline as local_pipeline  # noqa: E402


DEFAULT_OPERATOR_ID = "mini-understand-anything-pane-bridge"
DEFAULT_LANGUAGE = "zh"
DEFAULT_SEMANTIC_BACKEND = "ThunderOMLX"
DEFAULT_SEMANTIC_OPERATOR_ID = "mini-thunderomlx-qwen36-knowledge"
DEFAULT_PANE_TARGET = "0"
DEFAULT_SKILL_COMMAND_TEMPLATE = "/understand --language {language} {repo_path}"
DEFAULT_EXECUTION_SURFACE = "deterministic_scan_and_thunderomlx_semantic"
LEGACY_EXECUTION_SURFACE = "tui_pane_skill_command"
DEFAULT_PANE_SESSIONS = (
    "solar-harness-lab",
    "solar-harness-multi-task",
    "solar-harness",
    "solar",
)


def _load_envelope() -> dict[str, Any]:
    path = str(os.environ.get("SOLAR_OPERATOR_ENVELOPE_JSON") or "").strip()
    if not path:
        raise RuntimeError("SOLAR_OPERATOR_ENVELOPE_JSON missing")
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("operator envelope must be a JSON object")
    return payload


def _task_dir() -> Path:
    raw = str(os.environ.get("TASK_DIR") or "").strip()
    if raw:
        path = Path(raw).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path
    return Path.cwd()


def _operator_id(envelope: dict[str, Any]) -> str:
    value = str(envelope.get("operator_id") or "").strip()
    return value or DEFAULT_OPERATOR_ID


def _runtime_preferences(envelope: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    resolved = envelope.get("resolved_capability_capsule")
    if isinstance(resolved, dict) and isinstance(resolved.get("runtime_preferences"), dict):
        merged.update(deepcopy(resolved["runtime_preferences"]))
    if isinstance(envelope.get("runtime_preferences"), dict):
        merged.update(deepcopy(envelope["runtime_preferences"]))
    return merged


def _shell_quote(value: str) -> str:
    return shlex.quote(str(value))


def _discover_tmux_panes() -> list[dict[str, str]]:
    try:
        proc = subprocess.run(
            [
                "tmux",
                "list-panes",
                "-a",
                "-F",
                "#{session_name}\t#{window_index}\t#{pane_index}\t#{pane_title}\t#{pane_current_command}",
            ],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except Exception:
        return []
    if proc.returncode != 0:
        return []
    panes: list[dict[str, str]] = []
    for line in (proc.stdout or "").splitlines():
        if not line.strip():
            continue
        session, window, pane, title, command = (line.split("\t", 4) + ["", "", "", "", ""])[:5]
        panes.append(
            {
                "session": session.strip(),
                "window": window.strip(),
                "pane": pane.strip(),
                "target": f"{session.strip()}:{window.strip()}.{pane.strip()}",
                "title": title.strip(),
                "command": command.strip(),
            }
        )
    return panes


def _pane_score(row: dict[str, str]) -> tuple[int, int, int]:
    session = row.get("session", "")
    title = row.get("title", "").lower()
    command = row.get("command", "").lower()
    session_rank = DEFAULT_PANE_SESSIONS.index(session) if session in DEFAULT_PANE_SESSIONS else len(DEFAULT_PANE_SESSIONS)
    title_bonus = 0
    if any(token in title for token in ("builder", "lab-builder", "knowledge", "qwen", "sonnet", "opus")):
        title_bonus = -2
    elif any(token in title for token in ("planner", "evaluator", "pm")):
        title_bonus = 1
    command_bonus = 0 if command in {"claude", "codex", "zsh", "bash"} else 1
    return (session_rank, title_bonus, command_bonus)


def _resolve_pane_target(request: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    requested = str(request.get("pane_target") or "").strip()
    if requested and ":" in requested:
        return requested, {"strategy": "explicit_full_target", "requested": requested}
    if requested and requested not in {"auto", "builder_idle", "knowledge_idle", "best_effort"}:
        return requested, {"strategy": "explicit_legacy_target", "requested": requested}

    selector = str(request.get("pane_target_selector") or requested or "best_effort").strip() or "best_effort"
    panes = _discover_tmux_panes()
    if not panes:
        fallback = requested if requested and requested not in {"auto", "builder_idle", "knowledge_idle", "best_effort"} else DEFAULT_PANE_TARGET
        return fallback, {"strategy": "no_tmux_inventory_fallback", "requested": requested, "selector": selector}

    filtered = [row for row in panes if row.get("session") in DEFAULT_PANE_SESSIONS]
    if selector == "builder_idle":
        filtered = [
            row for row in filtered
            if any(token in row.get("title", "").lower() for token in ("builder", "lab-builder", "knowledge"))
        ] or filtered
    elif selector == "knowledge_idle":
        filtered = [
            row for row in filtered
            if any(token in row.get("title", "").lower() for token in ("knowledge", "qwen", "builder"))
        ] or filtered
    if not filtered:
        filtered = panes
    chosen = sorted(filtered, key=_pane_score)[0]
    return chosen["target"], {
        "strategy": "tmux_inventory_selector",
        "selector": selector,
        "requested": requested,
        "resolved": chosen["target"],
        "title": chosen.get("title", ""),
        "command": chosen.get("command", ""),
    }


def _render_skill_command(request: dict[str, Any]) -> str:
    template = str(request.get("skill_command_template") or "").strip() or DEFAULT_SKILL_COMMAND_TEMPLATE
    payload = {
        "repo_path": _shell_quote(str(request.get("repo_path") or "")),
        "language": _shell_quote(str(request.get("language") or DEFAULT_LANGUAGE)),
        "semantic_backend": _shell_quote(str(request.get("semantic_backend") or DEFAULT_SEMANTIC_BACKEND)),
        "semantic_operator_id": _shell_quote(str(request.get("semantic_operator_id") or DEFAULT_SEMANTIC_OPERATOR_ID)),
    }
    return template.format(**payload).strip()


def build_request(envelope: dict[str, Any], *, task_dir: Path | None = None) -> dict[str, Any]:
    runtime_preferences = _runtime_preferences(envelope)
    repo_path = str(
        envelope.get("repo_path")
        or envelope.get("workspace_path")
        or envelope.get("project_root")
        or envelope.get("cwd")
        or ""
    ).strip()
    language = str(
        envelope.get("language")
        or runtime_preferences.get("language")
        or DEFAULT_LANGUAGE
    ).strip() or DEFAULT_LANGUAGE
    request = {
        "repo_path": repo_path,
        "language": language,
        "pane_target": str(
            envelope.get("pane_target")
            or runtime_preferences.get("pane_target")
            or "best_effort"
        ),
        "pane_target_selector": str(
            envelope.get("pane_target_selector")
            or runtime_preferences.get("pane_target_selector")
            or "builder_idle"
        ),
        "semantic_backend": str(
            envelope.get("semantic_backend")
            or runtime_preferences.get("semantic_backend")
            or DEFAULT_SEMANTIC_BACKEND
        ),
        "semantic_operator_id": str(
            envelope.get("semantic_operator_id")
            or runtime_preferences.get("semantic_operator_id")
            or DEFAULT_SEMANTIC_OPERATOR_ID
        ),
        "execution_surface": str(runtime_preferences.get("execution_surface") or DEFAULT_EXECUTION_SURFACE),
        "skill_command_template": str(
            runtime_preferences.get("skill_command_template")
            or envelope.get("skill_command_template")
            or DEFAULT_SKILL_COMMAND_TEMPLATE
        ),
        "operator_id": _operator_id(envelope),
        "task_id": str(envelope.get("task_id") or ""),
        "node_id": str(envelope.get("node_id") or ""),
        "sprint_id": str(envelope.get("sprint_id") or ""),
        "objective": str(envelope.get("objective") or ""),
    }
    request["skill_command"] = _render_skill_command(request)
    resolved_pane_target, pane_meta = _resolve_pane_target(request)
    request["pane_target"] = resolved_pane_target
    request["pane_resolution"] = pane_meta
    if task_dir is not None:
        request["output_dir"] = str(task_dir.resolve())
    return request


def _rate_control_settings(envelope: dict[str, Any]) -> dict[str, Any]:
    operator_id = _operator_id(envelope)
    flow_control: dict[str, Any] = {}
    try:
        import operator_runtime  # type: ignore

        config = operator_runtime.get_operator_config(operator_id) or {}
        if isinstance(config.get("flow_control"), dict):
            flow_control = dict(config["flow_control"])
    except Exception:
        flow_control = {}
    return {
        "operator_id": operator_id,
        "success_cooldown_seconds": ofc.int_value(
            envelope.get("understand_anything_success_cooldown_seconds")
            or os.environ.get("SOLAR_UNDERSTAND_ANYTHING_SUCCESS_COOLDOWN_SECONDS")
            or flow_control.get("success_cooldown_seconds"),
            900,
        ),
        "rate_limit_cooldown_seconds": ofc.int_value(
            envelope.get("understand_anything_rate_limit_cooldown_seconds")
            or os.environ.get("SOLAR_UNDERSTAND_ANYTHING_RATE_LIMIT_COOLDOWN_SECONDS")
            or flow_control.get("rate_limit_cooldown_seconds"),
            3600,
        ),
        "auth_cooldown_seconds": ofc.int_value(
            envelope.get("understand_anything_auth_cooldown_seconds")
            or os.environ.get("SOLAR_UNDERSTAND_ANYTHING_AUTH_COOLDOWN_SECONDS")
            or flow_control.get("auth_cooldown_seconds"),
            21600,
        ),
        "defer_on_cooldown": ofc.bool_value(
            envelope.get("understand_anything_defer_on_cooldown")
            or os.environ.get("SOLAR_UNDERSTAND_ANYTHING_DEFER_ON_COOLDOWN")
            or flow_control.get("defer_on_cooldown"),
            True,
        ),
        "defer_on_auth": ofc.bool_value(
            envelope.get("understand_anything_defer_on_auth")
            or os.environ.get("SOLAR_UNDERSTAND_ANYTHING_DEFER_ON_AUTH")
            or flow_control.get("defer_on_auth"),
            True,
        ),
    }


def _validate_request(request: dict[str, Any]) -> None:
    repo_path = str(request.get("repo_path") or "").strip()
    if not repo_path:
        raise RuntimeError("understand-anything operator requires repo_path")
    if not Path(repo_path).expanduser().exists():
        raise RuntimeError(f"repo_path does not exist: {repo_path}")
    skill_command_template = str(request.get("skill_command_template") or "").strip() or DEFAULT_SKILL_COMMAND_TEMPLATE
    if "{repo_path}" not in skill_command_template:
        raise RuntimeError("skill_command_template must include {repo_path}")
    semantic_backend = str(request.get("semantic_backend") or "").strip()
    if semantic_backend.lower() != DEFAULT_SEMANTIC_BACKEND.lower():
        raise RuntimeError(
            f"semantic backend must be {DEFAULT_SEMANTIC_BACKEND}, got {semantic_backend or 'N/A'}"
        )
    execution_surface = str(request.get("execution_surface") or "").strip()
    if execution_surface not in {DEFAULT_EXECUTION_SURFACE, LEGACY_EXECUTION_SURFACE}:
        raise RuntimeError(
            f"execution_surface must be {DEFAULT_EXECUTION_SURFACE} or {LEGACY_EXECUTION_SURFACE}"
        )
    if execution_surface == LEGACY_EXECUTION_SURFACE and not str(request.get("pane_target") or "").strip():
        raise RuntimeError("pane_target must not be empty for legacy pane dispatch")


def _ensure_semantic_backend_ready(request: dict[str, Any], *, task_dir: Path) -> None:
    semantic_operator_id = str(request.get("semantic_operator_id") or "").strip()
    if not semantic_operator_id:
        return
    snapshot = ofc.current_block_state(semantic_operator_id, allow_unregistered=True)
    if not snapshot:
        return
    runtime_state = str(snapshot.get("runtime_state") or "")
    reason = f"semantic backend blocked: {semantic_operator_id} state={runtime_state}"
    delay_seconds = 0
    expires_at = str(snapshot.get("expires_at") or "").strip()
    if expires_at:
        try:
            import datetime as dt

            when = dt.datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            now = dt.datetime.now(dt.timezone.utc)
            delay_seconds = max(0, int((when - now).total_seconds()))
        except Exception:
            delay_seconds = 0
    if runtime_state in {"cooldown", "auth_expired"}:
        ofc.write_task_control(
            task_dir,
            operator_id=str(request.get("operator_id") or DEFAULT_OPERATOR_ID),
            action="defer",
            runtime_state=runtime_state,
            reason=reason,
            delay_seconds=delay_seconds,
        )
    raise RuntimeError(reason)


def _summary_markdown(response: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Understand Anything Operator Result",
            "",
            "## 已完成",
            f"- repo_path: {response.get('repo_path') or 'N/A'}",
            f"- pane_target: {response.get('pane_target') or 'N/A'}",
            f"- skill_command: {response.get('skill_command') or 'N/A'}",
            f"- execution_surface: {response.get('execution_surface') or 'N/A'}",
            f"- semantic_backend: {response.get('semantic_backend') or 'N/A'}",
            f"- proof_artifact: {response.get('proof_artifact') or 'N/A'}",
            f"- knowledge_graph_path: {response.get('knowledge_graph_path') or 'N/A'}",
        ]
    )


def _write_semantic_proof_artifact(
    request: dict[str, Any],
    *,
    task_dir: Path,
    semantic_phase_request_path: str = "",
    semantic_phase_prompt_path: str = "",
) -> Path:
    semantic_operator_id = str(request.get("semantic_operator_id") or "").strip()
    snapshot = ofc.current_block_state(semantic_operator_id, allow_unregistered=True) or {}
    payload = {
        "schema_version": "solar.understand_anything.semantic_proof.v1",
        "semantic_backend_declared": str(request.get("semantic_backend") or ""),
        "semantic_operator_id": semantic_operator_id,
        "semantic_operator_block_state": snapshot,
        "execution_surface": str(request.get("execution_surface") or ""),
        "skill_command_template": str(request.get("skill_command_template") or ""),
        "rendered_skill_command": str(request.get("skill_command") or ""),
        "pane_target": str(request.get("pane_target") or ""),
        "pane_resolution": dict(request.get("pane_resolution") or {}),
        "repo_path": str(request.get("repo_path") or ""),
        "language": str(request.get("language") or ""),
        "semantic_phase_request_path": semantic_phase_request_path,
        "semantic_phase_prompt_path": semantic_phase_prompt_path,
        "enforcement_mode": "contract_and_runtime_gate",
        "proof_note": (
            "This artifact proves Solar Harness enforced ThunderOMLX at the capsule/runtime/operator level "
            "before executing understand-anything through the governed execution surface."
        ),
    }
    path = Path(task_dir) / "understand-anything-semantic-proof.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _write_semantic_phase_request_artifacts(request: dict[str, Any], *, task_dir: Path) -> tuple[Path, Path]:
    prompt = "\n".join(
        [
            "你是 Solar Harness 的 ThunderOMLX 语义阶段执行器。",
            "请基于即将由 understand-anything 生成/消费的仓库理解上下文，补充语义层抽取与摘要。",
            "",
            f"- repo_path: {request.get('repo_path') or 'N/A'}",
            f"- language: {request.get('language') or 'N/A'}",
            f"- objective: {request.get('objective') or 'N/A'}",
            f"- source_skill_command: {request.get('skill_command') or 'N/A'}",
            "",
            "输出要求：",
            "- 用中文输出高密度语义摘要。",
            "- 标明模块边界、关键命令、关键文件、后续验证点。",
            "- 不要编造未观察到的实现细节。",
        ]
    )
    prompt_path = Path(task_dir) / "understand-anything-semantic-phase-prompt.md"
    prompt_path.write_text(prompt + "\n", encoding="utf-8")
    payload = {
        "schema_version": "solar.understand_anything.semantic_phase_request.v1",
        "backend": str(request.get("semantic_backend") or ""),
        "operator_id": str(request.get("semantic_operator_id") or ""),
        "task_type": "knowledge-extraction",
        "repo_path": str(request.get("repo_path") or ""),
        "language": str(request.get("language") or ""),
        "objective": str(request.get("objective") or ""),
        "source_skill_command": str(request.get("skill_command") or ""),
        "prompt_path": str(prompt_path),
        "dispatch_mode": "explicit_followup_request",
    }
    request_path = Path(task_dir) / "understand-anything-semantic-phase-request.json"
    request_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return request_path, prompt_path


def _run_local_semantic_pipeline(request: dict[str, Any], *, task_dir: Path) -> dict[str, Any]:
    knowledge_dir = Path(str(request.get("output_dir") or "")).expanduser()
    if not knowledge_dir.is_absolute():
        knowledge_dir = Path(str(request.get("repo_path") or "")).expanduser() / ".understand-anything"
    pipeline_result = local_pipeline.run_pipeline(
        str(request["repo_path"]),
        output_dir=str(knowledge_dir),
        language=str(request.get("language") or DEFAULT_LANGUAGE),
        objective=str(request.get("objective") or ""),
    )
    response = {
        "ok": True,
        "repo_path": request["repo_path"],
        "pane_target": "N/A",
        "skill_command": "N/A",
        "skill_command_template": request["skill_command_template"],
        "execution_surface": request["execution_surface"],
        "semantic_backend": request["semantic_backend"],
        "semantic_operator_id": request["semantic_operator_id"],
        "pane_resolution": request.get("pane_resolution") or {},
        "knowledge_graph_path": pipeline_result["knowledge_graph_path"],
        "knowledge_output_dir": pipeline_result["output_dir"],
        "chunk_manifest_path": pipeline_result["manifest_path"],
        "resume_state_path": pipeline_result["resume_state_path"],
        "dispatch_result": {
            "mode": "local_pipeline",
            "scan_path": pipeline_result["scan_path"],
            "summary_path": pipeline_result["summary_path"],
            "meta_path": pipeline_result["meta_path"],
            "manifest_path": pipeline_result["manifest_path"],
            "resume_state_path": pipeline_result["resume_state_path"],
            "chunks_total": pipeline_result.get("chunks_total"),
            "chunks_completed": pipeline_result.get("chunks_completed"),
            "resumed": pipeline_result.get("resumed"),
            "usage": pipeline_result.get("usage") or {},
        },
    }
    return response


def _run_legacy_pane_dispatch(request: dict[str, Any]) -> dict[str, Any]:
    pane_target = str(request["pane_target"])
    hand = PaneHand()
    hand_ref = hand.provision(
        capabilities=["skill.understand-anything", "tmux.send-keys"],
        location=pane_target,
    )
    result = hand.execute(
        hand_ref,
        "understand_anything",
        {"command": request["skill_command"]},
        idempotency_key=str(request.get("task_id") or request["repo_path"]),
        timeout_seconds=30,
    )
    if result.status != ResultStatus.OK:
        raise RuntimeError(result.error or "pane dispatch failed")
    return {
        "ok": True,
        "repo_path": request["repo_path"],
        "pane_target": pane_target,
        "skill_command": request["skill_command"],
        "skill_command_template": request["skill_command_template"],
        "execution_surface": request["execution_surface"],
        "semantic_backend": request["semantic_backend"],
        "semantic_operator_id": request["semantic_operator_id"],
        "pane_resolution": request.get("pane_resolution") or {},
        "dispatch_result": result.output,
    }


def run_request(request: dict[str, Any], *, task_dir: Path) -> dict[str, Any]:
    _validate_request(request)
    _ensure_semantic_backend_ready(request, task_dir=task_dir)
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "understand-anything-request.json").write_text(
        json.dumps(request, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    contract = {
        "execution_surface": request["execution_surface"],
        "skill_command": request["skill_command"],
        "skill_command_template": request["skill_command_template"],
        "pane_target": request.get("pane_target") or "",
        "pane_resolution": request.get("pane_resolution") or {},
        "repo_path": request["repo_path"],
        "semantic_backend": request["semantic_backend"],
        "semantic_operator_id": request["semantic_operator_id"],
        "execution_surface": request["execution_surface"],
        "status": "dispatching",
    }
    (task_dir / "understand-anything-bridge-contract.json").write_text(
        json.dumps(contract, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    semantic_request_path, semantic_prompt_path = _write_semantic_phase_request_artifacts(request, task_dir=task_dir)
    proof_path = _write_semantic_proof_artifact(
        request,
        task_dir=task_dir,
        semantic_phase_request_path=str(semantic_request_path),
        semantic_phase_prompt_path=str(semantic_prompt_path),
    )
    if str(request.get("execution_surface") or "") == DEFAULT_EXECUTION_SURFACE:
        response = _run_local_semantic_pipeline(request, task_dir=task_dir)
    else:
        response = _run_legacy_pane_dispatch(request)
    response.update(
        {
            "proof_artifact": str(proof_path),
            "semantic_phase_request_artifact": str(semantic_request_path),
            "semantic_phase_prompt_artifact": str(semantic_prompt_path),
        }
    )
    (task_dir / "understand-anything-result.json").write_text(
        json.dumps(response, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(_summary_markdown(response))
    return response


def main() -> int:
    envelope = _load_envelope()
    task_dir = _task_dir()
    ofc.clear_task_control(task_dir)
    request = build_request(envelope, task_dir=task_dir)
    rate_control = _rate_control_settings(envelope)
    operator_id = str(rate_control["operator_id"])
    try:
        ofc.ensure_operator_available(operator_id)
        run_request(request, task_dir=task_dir)
        ofc.apply_success_cooldown(
            operator_id,
            success_cooldown_seconds=int(rate_control.get("success_cooldown_seconds") or 0),
        )
        return 0
    except Exception as exc:
        decision = ofc.apply_failure_flow_control(
            task_dir,
            operator_id=operator_id,
            failure_text=str(exc),
            rate_limit_cooldown_seconds=int(rate_control.get("rate_limit_cooldown_seconds") or 0),
            auth_cooldown_seconds=int(rate_control.get("auth_cooldown_seconds") or 0),
            defer_on_cooldown=bool(rate_control.get("defer_on_cooldown")),
            defer_on_auth=bool(rate_control.get("defer_on_auth")),
        )
        runtime_state = str(decision.get("runtime_state") or "")
        suffix = f" [runtime_state={runtime_state}]" if runtime_state else ""
        print(f"understand_anything_operator failed: {exc}{suffix}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
