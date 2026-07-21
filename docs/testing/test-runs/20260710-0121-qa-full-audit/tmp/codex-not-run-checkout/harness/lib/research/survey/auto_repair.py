"""Auto-repair loop for professor-grade survey reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .evaluator import evaluate_survey
from .rewrite_queue import build_rewrite_queue
from .rewrite_runner import run_rewrite_queue


def _scorecard_issues(eval_payload: dict[str, Any]) -> list[str]:
    scorecard = eval_payload.get("scorecard") if isinstance(eval_payload, dict) else {}
    issues = scorecard.get("issues") if isinstance(scorecard, dict) else []
    return [str(item) for item in issues] if isinstance(issues, list) else []


def run_auto_repair(
    output_dir: str | Path,
    *,
    max_passes: int = 2,
    per_pass_limit: int = 0,
    max_rounds: int = 2,
    min_chars: int = 1200,
    min_finalized: int | None = None,
    require_complete: bool = False,
    max_severity: str = "P1",
    min_risk_score: int = 25,
    writer_backend: str = "deterministic",
    writer_command: str = "",
    writer_timeout: int = 120,
    pane_target: str = "",
    pane_send: bool = False,
    emit_prompt_packet: bool = True,
) -> dict[str, Any]:
    root = Path(output_dir).expanduser()
    iterations: list[dict[str, Any]] = []
    max_passes = max(int(max_passes or 1), 1)
    waiting_total = 0
    final_eval = evaluate_survey(root, strict=True, min_finalized=min_finalized, require_complete=require_complete)
    if final_eval.get("ok"):
        payload = {
            "ok": True,
            "reason": "already_passed",
            "iterations": [],
            "final_eval": final_eval,
            "blocked_issues": [],
            "waiting": 0,
            "run_path": str(root / "survey_auto_repair.json"),
        }
        (root / "survey_auto_repair.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return payload

    reason = "max_passes_reached"
    for pass_index in range(max_passes):
        before = final_eval
        queue = build_rewrite_queue(
            root,
            max_severity=max_severity,
            limit=per_pass_limit,
            min_risk_score=min_risk_score,
        )
        if not queue.get("queue_count"):
            reason = "no_actionable_rewrites"
            iterations.append({
                "pass_index": pass_index,
                "before_ok": before.get("ok"),
                "before_issues": _scorecard_issues(before),
                "queue_count": 0,
                "rewrite_run": None,
                "after_ok": False,
                "after_issues": _scorecard_issues(before),
            })
            break
        rewrite_run = run_rewrite_queue(
            root,
            limit=per_pass_limit,
            max_rounds=max_rounds,
            min_chars=min_chars,
            writer_backend=writer_backend,
            writer_command=writer_command,
            writer_timeout=writer_timeout,
            pane_target=pane_target,
            pane_send=pane_send,
            emit_prompt_packet=emit_prompt_packet,
            build_if_missing=False,
            replace_final=True,
        )
        waiting_total += int(rewrite_run.get("waiting") or 0)
        final_eval = evaluate_survey(root, strict=True, min_finalized=min_finalized, require_complete=require_complete)
        iterations.append({
            "pass_index": pass_index,
            "before_ok": before.get("ok"),
            "before_issues": _scorecard_issues(before),
            "queue_count": queue.get("queue_count"),
            "rewrite_run": rewrite_run,
            "after_ok": final_eval.get("ok"),
            "after_issues": _scorecard_issues(final_eval),
        })
        if final_eval.get("ok"):
            reason = "repaired"
            break
        if waiting_total:
            reason = "waiting_for_writer"
            break

    payload = {
        "ok": bool(final_eval.get("ok")),
        "reason": reason,
        "iterations": iterations,
        "final_eval": final_eval,
        "blocked_issues": _scorecard_issues(final_eval),
        "waiting": waiting_total,
        "run_path": str(root / "survey_auto_repair.json"),
    }
    (root / "survey_auto_repair.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload
