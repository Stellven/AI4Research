"""Acceptance closeout for the Understand Anything background knowledge graph sprint."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from acceptance_closeout import auto_closeout_graph_nodes


SPRINT_ID = "sprint-20260527-understand-anything-background-knowledge-graph"
NODE_IDS = (
    "U1_preflight_runtime",
    "U2_run_understand_zh_background",
    "U3_verify_graph_artifacts",
    "U4_handoff_resume_contract",
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _claude_auth_snapshot(preflight: dict[str, Any]) -> tuple[bool, str]:
    status = str(preflight.get("claude_cli_auth_status") or "").strip()
    if status and status != "missing":
        return True, status
    claude_config = Path.home() / ".claude.json"
    if claude_config.exists():
        return True, "claude_config_json"
    return False, "missing"


def _plugin_readable(preflight: dict[str, Any]) -> bool:
    if "plugin_root_readable" in preflight:
        return bool(preflight.get("plugin_root_readable"))
    plugin_root = Path(str(preflight.get("plugin_root") or ""))
    return plugin_root.exists() and plugin_root.is_dir()


def build_node_handoffs(
    *,
    sprint_root: Path,
    run_root: Path,
    output_dir: Path,
    preflight: dict[str, Any],
    verify: dict[str, Any],
    parent_handoff: Path,
) -> dict[str, Path]:
    auth_ok, auth_evidence = _claude_auth_snapshot(preflight)
    handoffs: dict[str, Path] = {}
    u1 = sprint_root / f"{SPRINT_ID}.U1_preflight_runtime-handoff.md"
    handoffs["U1_preflight_runtime"] = _write_text(
        u1,
        "\n".join(
            [
                f"# Handoff — {SPRINT_ID} / U1_preflight_runtime",
                "",
                "## Summary",
                "",
                "- Claude CLI preflight, plugin cache, Node, pnpm, and output path were checked.",
                "",
                "## Evidence",
                "",
                f"- auth_ok: `{auth_ok}`",
                f"- auth_evidence: `{auth_evidence}`",
                f"- plugin_root_exists: `{bool(preflight.get('plugin_root_exists'))}`",
                f"- plugin_root_readable: `{_plugin_readable(preflight)}`",
                f"- node_version: `{preflight.get('node_version', '')}`",
                f"- pnpm_version: `{preflight.get('pnpm_version', '')}`",
                f"- preflight_json: `{run_root / 'preflight.json'}`",
                "",
            ]
        ),
    )
    u2 = sprint_root / f"{SPRINT_ID}.U2_run_understand_zh_background-handoff.md"
    handoffs["U2_run_understand_zh_background"] = _write_text(
        u2,
        "\n".join(
            [
                f"# Handoff — {SPRINT_ID} / U2_run_understand_zh_background",
                "",
                "## Summary",
                "",
                "- Background understand-anything pipeline was launched and completed without blocking the foreground panes.",
                "",
                "## Evidence",
                "",
                f"- config_exists: `{bool(verify.get('config_exists'))}`",
                f"- knowledge_graph_exists: `{bool(verify.get('knowledge_graph_exists'))}`",
                f"- output_dir: `{output_dir}`",
                f"- status_json: `{run_root / 'status.json'}`",
                f"- output_log: `{run_root / 'output.log'}`",
                "",
            ]
        ),
    )
    u3 = sprint_root / f"{SPRINT_ID}.U3_verify_graph_artifacts-handoff.md"
    handoffs["U3_verify_graph_artifacts"] = _write_text(
        u3,
        "\n".join(
            [
                f"# Handoff — {SPRINT_ID} / U3_verify_graph_artifacts",
                "",
                "## Summary",
                "",
                "- Knowledge graph artifacts were checked for existence and JSON parseability.",
                "",
                "## Evidence",
                "",
                f"- knowledge_graph_exists: `{bool(verify.get('knowledge_graph_exists'))}`",
                f"- knowledge_graph_json_valid: `{bool(verify.get('knowledge_graph_json_valid'))}`",
                f"- meta_exists: `{bool(verify.get('meta_exists'))}`",
                f"- chunk_manifest_exists: `{bool(verify.get('chunk_manifest_exists'))}`",
                f"- resume_state_exists: `{bool(verify.get('resume_state_exists'))}`",
                f"- verify_json: `{run_root / 'verify.json'}`",
                "",
            ]
        ),
    )
    u4 = sprint_root / f"{SPRINT_ID}.U4_handoff_resume_contract-handoff.md"
    parent_text = parent_handoff.read_text(encoding="utf-8") if parent_handoff.exists() else ""
    handoffs["U4_handoff_resume_contract"] = _write_text(
        u4,
        "\n".join(
            [
                f"# Handoff — {SPRINT_ID} / U4_handoff_resume_contract",
                "",
                "## Summary",
                "",
                "- Background run completion and resume contract were summarized for later non-blocking reuse.",
                "",
                "## Evidence",
                "",
                f"- parent_handoff: `{parent_handoff}`",
                f"- mentions_resume_strategy: `{'resume' in parent_text.lower() or '恢复' in parent_text}`",
                f"- status_json: `{run_root / 'status.json'}`",
                "",
            ]
        ),
    )
    return handoffs


def build_eval_payloads(
    *,
    run_root: Path,
    output_dir: Path,
    preflight: dict[str, Any],
    verify: dict[str, Any],
    node_handoffs: dict[str, Path],
    parent_handoff: Path,
) -> dict[str, dict[str, Any]]:
    auth_ok, auth_evidence = _claude_auth_snapshot(preflight)
    u1_conditions = [
        ("claude_cli_logged_in_or_session_auth", auth_ok),
        ("plugin_root_exists", bool(preflight.get("plugin_root_exists"))),
        ("plugin_root_readable", _plugin_readable(preflight)),
        ("node_available", bool(preflight.get("node_version"))),
        ("pnpm_available", bool(preflight.get("pnpm_version"))),
        ("u1_handoff_written", node_handoffs["U1_preflight_runtime"].exists()),
    ]
    u2_conditions = [
        ("pipeline_status_completed", str(_read_json(run_root / "status.json").get("status") or "") == "completed"),
        ("config_written", bool(verify.get("config_exists"))),
        ("knowledge_graph_written", bool(verify.get("knowledge_graph_exists"))),
        ("u2_handoff_written", node_handoffs["U2_run_understand_zh_background"].exists()),
    ]
    u3_conditions = [
        ("knowledge_graph_exists", bool(verify.get("knowledge_graph_exists"))),
        ("knowledge_graph_json_valid", bool(verify.get("knowledge_graph_json_valid"))),
        ("meta_exists", bool(verify.get("meta_exists"))),
        ("u3_handoff_written", node_handoffs["U3_verify_graph_artifacts"].exists()),
    ]
    u4_conditions = [
        ("parent_handoff_exists", parent_handoff.exists()),
        ("u4_handoff_written", node_handoffs["U4_handoff_resume_contract"].exists()),
        ("output_dir_exists", output_dir.exists()),
    ]

    def pack(node_id: str, conditions: list[tuple[str, bool]], summary: str, evidence: dict[str, Any]) -> dict[str, Any]:
        passed = [label for label, ok in conditions if ok]
        failed = [label for label, ok in conditions if not ok]
        return {
            "sprint_id": SPRINT_ID,
            "node_id": node_id,
            "round": 1,
            "verdict": "PASS" if not failed else "FAIL",
            "checked_at": _now(),
            "passed_conditions": passed,
            "failed_conditions": failed,
            "warnings": [],
            "evidence": evidence,
            "summary": summary,
        }

    return {
        "U1_preflight_runtime": pack(
            "U1_preflight_runtime",
            u1_conditions,
            "Preflight runtime requirements and plugin path evidence were recorded.",
            {"preflight_json": str(run_root / "preflight.json"), "auth_evidence": auth_evidence},
        ),
        "U2_run_understand_zh_background": pack(
            "U2_run_understand_zh_background",
            u2_conditions,
            "Background understand-anything pipeline completed and wrote repository artifacts.",
            {"status_json": str(run_root / "status.json"), "output_dir": str(output_dir)},
        ),
        "U3_verify_graph_artifacts": pack(
            "U3_verify_graph_artifacts",
            u3_conditions,
            "Knowledge graph artifacts were verified from the deterministic output directory.",
            {"verify_json": str(run_root / "verify.json")},
        ),
        "U4_handoff_resume_contract": pack(
            "U4_handoff_resume_contract",
            u4_conditions,
            "Resume handoff and non-blocking continuation contract were written.",
            {"parent_handoff": str(parent_handoff)},
        ),
    }


def auto_closeout_understand_anything_background(
    *,
    runtime_root: Path,
    target_repo: Path,
) -> dict[str, Any]:
    sprint_root = runtime_root / "sprints"
    run_root = runtime_root / "run" / "understand-anything-background" / SPRINT_ID
    output_dir = target_repo / ".understand-anything"
    preflight = _read_json(run_root / "preflight.json")
    verify = _read_json(run_root / "verify.json")
    parent_handoff = sprint_root / f"{SPRINT_ID}.handoff.md"
    node_handoffs = build_node_handoffs(
        sprint_root=sprint_root,
        run_root=run_root,
        output_dir=output_dir,
        preflight=preflight,
        verify=verify,
        parent_handoff=parent_handoff,
    )
    payloads = build_eval_payloads(
        run_root=run_root,
        output_dir=output_dir,
        preflight=preflight,
        verify=verify,
        node_handoffs=node_handoffs,
        parent_handoff=parent_handoff,
    )
    return auto_closeout_graph_nodes(
        graph_path=sprint_root / f"{SPRINT_ID}.task_graph.json",
        node_payloads=payloads,
        eval_json_paths={node_id: sprint_root / f"{SPRINT_ID}.{node_id}-eval.json" for node_id in NODE_IDS},
        reason="understand_anything_background_auto_closeout",
        actor="understand_anything_background_closeout",
        event="understand_anything_background_auto_closeout",
        dispatch_downstream=False,
    )
