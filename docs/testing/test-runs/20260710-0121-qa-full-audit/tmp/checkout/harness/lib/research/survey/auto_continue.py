"""Safe one-command continuation for survey DeepResearch runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .finalize_run import finalize_survey_run
from .import_results import import_survey_search_results
from .status_next import survey_status_next_action


PAUSE_STATUSES = {"need_search_results", "waiting_for_writer"}


def continue_survey_run(
    output_dir: str | Path,
    *,
    brief: str = "",
    returned_md: str | Path = "",
    max_steps: int = 4,
    target_chars: int = 50000,
    audience: str = "technical",
    domain: str = "ai",
    section_limit: int = 3,
    repair_limit: int = 0,
    min_finalized: int | None = None,
    min_chars: int = 1200,
    require_complete: bool = False,
) -> dict[str, Any]:
    root = Path(output_dir).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    steps: list[dict[str, Any]] = []
    max_steps = max(1, max_steps)

    for index in range(max_steps):
        status = survey_status_next_action(root, brief=brief, returned_md=returned_md, require_complete=require_complete)
        state = str(status.get("status") or "unknown")
        step: dict[str, Any] = {
            "index": index,
            "status": state,
            "reason": status.get("reason") or "",
            "next_action": status.get("next_action") or "",
        }
        steps.append(step)

        if state == "done":
            return {
                "ok": True,
                "completed": True,
                "status": state,
                "reason": "already_done" if index == 0 else "completed",
                "steps": steps,
                "final_status": status,
            }

        if state in PAUSE_STATUSES:
            return {
                "ok": True,
                "completed": False,
                "paused": True,
                "status": state,
                "reason": status.get("reason") or state,
                "steps": steps,
                "final_status": status,
            }

        if state in {"not_started", "ready_to_finalize", "needs_more_sections"}:
            effective_section_limit = 0 if require_complete and state == "needs_more_sections" else section_limit
            result = finalize_survey_run(
                root,
                brief=brief,
                target_chars=target_chars,
                audience=audience,
                domain=domain,
                section_limit=effective_section_limit,
                repair_limit=repair_limit,
                min_finalized=min_finalized,
                min_chars=min_chars,
                require_complete=require_complete,
                skip_plan=(root / "survey_report_ast.json").exists(),
            )
            step["executed"] = "survey-finalize-run"
            step["section_limit"] = effective_section_limit
            step["result_ok"] = bool(result.get("ok"))
            step["result_reason"] = result.get("reason") or ""
            continue

        if state == "need_import_results":
            input_md = Path(str(status.get("returned_md") or returned_md or root / "returned_sources.md")).expanduser()
            result = import_survey_search_results(
                root,
                input_md,
                continue_finalize=True,
                brief=brief,
                target_chars=target_chars,
                audience=audience,
                domain=domain,
                section_limit=section_limit,
                repair_limit=repair_limit,
                min_finalized=min_finalized,
                min_chars=min_chars,
                require_complete=require_complete,
            )
            step["executed"] = "survey-import-search-results"
            step["input_md"] = str(input_md)
            step["result_ok"] = bool(result.get("ok"))
            step["result_reason"] = result.get("reason") or ""
            if not result.get("ok"):
                final_status = survey_status_next_action(root, brief=brief, returned_md=returned_md, require_complete=require_complete)
                return {
                    "ok": False,
                    "completed": False,
                    "status": "import_failed",
                    "reason": result.get("reason") or "import_failed",
                    "steps": steps,
                    "final_status": final_status,
                }
            continue

        return {
            "ok": False,
            "completed": False,
            "status": state,
            "reason": "unknown_status",
            "steps": steps,
            "final_status": status,
        }

    final_status = survey_status_next_action(root, brief=brief, returned_md=returned_md, require_complete=require_complete)
    return {
        "ok": final_status.get("status") == "done",
        "completed": final_status.get("status") == "done",
        "status": final_status.get("status"),
        "reason": "max_steps_reached",
        "steps": steps,
        "final_status": final_status,
    }
