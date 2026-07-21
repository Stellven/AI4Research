"""Consume survey rewrite queues and execute section rewrites."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .rewrite_queue import build_rewrite_queue
from .writing_loop import run_section_revision_loop


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _round_index_from_target(path_text: str, default: int = 1) -> int:
    match = re.search(r"round_(\d+)\.md$", path_text or "")
    if not match:
        return default
    return int(match.group(1))


def run_rewrite_queue(
    output_dir: str | Path,
    *,
    limit: int = 0,
    max_rounds: int = 2,
    min_chars: int = 1200,
    writer_backend: str = "deterministic",
    writer_command: str = "",
    writer_timeout: int = 120,
    pane_target: str = "",
    pane_send: bool = False,
    emit_prompt_packet: bool = True,
    build_if_missing: bool = True,
    replace_final: bool = True,
) -> dict[str, Any]:
    root = Path(output_dir).expanduser()
    queue_path = root / "survey_rewrite_queue.json"
    queue = _read_json(queue_path)
    if build_if_missing and not isinstance(queue.get("items"), list):
        queue = build_rewrite_queue(root)
    items = queue.get("items", []) if isinstance(queue.get("items"), list) else []
    results: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    unlimited = limit <= 0
    for item in items:
        if not isinstance(item, dict):
            continue
        section_id = str(item.get("section_id") or "")
        if not section_id:
            skipped.append({"reason": "section_id_missing"})
            continue
        section_dir = root / "sections" / section_id
        spec = section_dir / "section.spec.json"
        pack = section_dir / "evidence_pack.json"
        if not spec.exists():
            skipped.append({"section_id": section_id, "reason": "section_spec_missing"})
            continue
        if not pack.exists():
            skipped.append({"section_id": section_id, "reason": "evidence_pack_missing"})
            continue
        final = section_dir / "final.md"
        if replace_final and final.exists():
            backup = section_dir / "final.before_rewrite.md"
            backup.write_text(final.read_text(encoding="utf-8"), encoding="utf-8")
            final.unlink()
        round_index = _round_index_from_target(str(item.get("target_response") or ""), default=1)
        result = run_section_revision_loop(
            root,
            section_id,
            max_rounds=max_rounds,
            start_round_index=round_index,
            min_chars=min_chars,
            writer_backend=writer_backend,
            writer_command=writer_command,
            writer_timeout=writer_timeout,
            pane_target=pane_target,
            pane_send=pane_send,
            emit_prompt_packet=emit_prompt_packet,
        )
        result["queue_id"] = item.get("queue_id") or ""
        result["rewrite_round_index"] = round_index
        results.append(result)
        if not unlimited and len(results) >= limit:
            break
    waiting = sum(1 for item in results if str(item.get("reason") or "").startswith(("human_response_missing", "pane_response_missing")))
    payload = {
        "ok": bool(results) and all(item.get("ok") for item in results),
        "queue_path": str(queue_path),
        "processed": len(results),
        "passed": sum(1 for item in results if item.get("ok")),
        "failed": sum(1 for item in results if not item.get("ok")),
        "waiting": waiting,
        "skipped": skipped,
        "results": results,
        "run_path": str(root / "survey_rewrite_run.json"),
    }
    (root / "survey_rewrite_run.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload
