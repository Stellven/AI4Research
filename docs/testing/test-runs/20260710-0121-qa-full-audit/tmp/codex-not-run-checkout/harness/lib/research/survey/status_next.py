"""Compute the next actionable step for a survey DeepResearch run."""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any


ARTIFACT_NAMES = [
    "final.md",
    "survey_finalize_run.json",
    "survey_source_gap.json",
    "survey_source_gap_handoff.md",
    "survey_import_search_results.json",
    "survey_rewrite_run.json",
    "survey_auto_repair.json",
    "pane_response_watch.json",
    "sources.jsonl",
    "evidence.jsonl",
    "claims.jsonl",
    "claim_evidence.jsonl",
    "survey_report_ast.json",
    "survey_evidence_packs.json",
    "survey_section_scorecard.json",
    "survey_final_quality.json",
    "survey_depth_profile.json",
]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            if isinstance(json.loads(line), dict):
                count += 1
        except json.JSONDecodeError:
            continue
    return count


def _q(value: str | Path) -> str:
    return shlex.quote(str(value))


def _cmd(name: str, root: Path, *, brief: str = "", returned_md: Path | None = None) -> str:
    base = f"solar-harness research {name} --output-dir {_q(root)}"
    if name == "survey-import-search-results":
        input_path = returned_md or root / "returned_sources.md"
        base += f" --input-md {_q(input_path)} --continue-finalize"
    if brief:
        base += f" --brief {_q(brief)}"
    return base + " --json"


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _has_waiting_writer(root: Path) -> tuple[bool, str]:
    rewrite = _read_json(root / "survey_rewrite_run.json")
    if int(rewrite.get("waiting") or 0) > 0:
        return True, "survey_rewrite_run_waiting"
    for item in rewrite.get("results", []) if isinstance(rewrite.get("results"), list) else []:
        reason = str(item.get("reason") or "")
        if reason.startswith(("human_response_missing", "pane_response_missing")):
            return True, reason

    repair = _read_json(root / "survey_auto_repair.json")
    if int(repair.get("waiting") or 0) > 0:
        return True, "survey_auto_repair_waiting"

    watch = _read_json(root / "pane_response_watch.json")
    for key in ("pending", "pending_responses", "waiting"):
        if int(watch.get(key) or 0) > 0:
            return True, f"pane_response_watch_{key}"
    return False, ""


def _returned_markdown(root: Path, returned_md: str | Path = "") -> Path:
    if returned_md:
        return Path(returned_md).expanduser()
    for name in ("returned_sources.md", "external_search_results.md", "search_results.md"):
        path = root / name
        if path.exists():
            return path
    return root / "returned_sources.md"


def survey_status_next_action(
    output_dir: str | Path,
    *,
    brief: str = "",
    returned_md: str | Path = "",
    require_complete: bool = False,
) -> dict[str, Any]:
    root = Path(output_dir).expanduser()
    returned_path = _returned_markdown(root, returned_md)
    artifacts = {name: (root / name).exists() for name in ARTIFACT_NAMES}
    counts = {
        "sources": _count_jsonl(root / "sources.jsonl"),
        "evidence": _count_jsonl(root / "evidence.jsonl"),
        "claims": _count_jsonl(root / "claims.jsonl"),
        "claim_evidence": _count_jsonl(root / "claim_evidence.jsonl"),
    }

    finalize = _read_json(root / "survey_finalize_run.json")
    source_gap = _read_json(root / "survey_source_gap.json")
    imported = _read_json(root / "survey_import_search_results.json")
    survey_eval = _read_json(root / "survey_eval.json")
    final_quality = _read_json(root / "survey_final_quality.json")
    final_path = root / "final.md"
    handoff_path = Path(str(source_gap.get("handoff_path") or root / "survey_source_gap_handoff.md")).expanduser()

    waiting, waiting_reason = _has_waiting_writer(root)
    import_ok = bool(imported.get("ok"))
    returned_ready = returned_path.exists()
    import_stale = returned_ready and _mtime(root / "survey_import_search_results.json") < _mtime(returned_path)
    source_gap_required = (
        finalize.get("reason") == "source_gap_handoff_required"
        or (bool(source_gap) and not source_gap.get("ok"))
    )

    payload: dict[str, Any] = {
        "ok": True,
        "output_dir": str(root),
        "brief": brief,
        "status": "unknown",
        "reason": "",
        "next_action": "",
        "artifacts": artifacts,
        "counts": counts,
        "handoff_path": str(handoff_path),
        "returned_md": str(returned_path),
        "final_md": str(final_path),
    }

    if final_path.exists() and finalize.get("ok") is True:
        payload.update({
            "status": "done",
            "reason": "finalize_run_passed",
            "next_action": f"open {_q(final_path)}",
        })
        return payload

    if returned_ready and (not import_ok or import_stale):
        payload.update({
            "status": "need_import_results",
            "reason": "returned_search_markdown_ready",
            "next_action": _cmd("survey-import-search-results", root, brief=brief, returned_md=returned_path),
        })
        return payload

    if source_gap_required:
        payload.update({
            "status": "need_search_results",
            "reason": "source_gap_handoff_required",
            "next_action": (
                f"open {_q(handoff_path)}; save returned Markdown to {_q(returned_path)}; "
                f"then run: {_cmd('survey-import-search-results', root, brief=brief, returned_md=returned_path)}"
            ),
        })
        return payload

    if finalize.get("reason") == "final_eval_failed":
        issues = list(((finalize.get("final_eval") or {}).get("scorecard") or {}).get("issues") or [])
        if not issues:
            issues = list((survey_eval.get("scorecard") or {}).get("issues") or [])
        incomplete = any(
            str(issue).startswith(("incomplete_sections:", "finalized_sections_low:", "pending_placeholder_count:"))
            for issue in issues
        ) or int(final_quality.get("pending_placeholder_count") or 0) > 0
        if incomplete:
            payload.update({
                "status": "needs_more_sections",
                "reason": "complete_survey_sections_required",
                "quality_issues": issues,
                "next_action": _cmd("survey-finalize-run", root, brief=brief) + (" --require-complete" if require_complete else ""),
            })
            return payload
        payload.update({
            "status": "quality_gate_failed",
            "reason": "final_eval_failed",
            "quality_issues": issues,
            "next_action": f"solar-harness research survey-auto-repair --output-dir {_q(root)} --json",
        })
        return payload

    if waiting:
        payload.update({
            "status": "waiting_for_writer",
            "reason": waiting_reason,
            "next_action": "write the expected human/pane response markdown, then rerun survey-rewrite-run or survey-watch-responses",
        })
        return payload

    if import_ok or artifacts["survey_report_ast.json"] or any(counts.values()):
        payload.update({
            "status": "ready_to_finalize",
            "reason": "artifacts_present_without_passed_final",
            "next_action": _cmd("survey-finalize-run", root, brief=brief),
        })
        return payload

    payload.update({
        "status": "not_started",
        "reason": "no_survey_artifacts_found",
        "next_action": _cmd("survey-finalize-run", root, brief=brief),
    })
    return payload
