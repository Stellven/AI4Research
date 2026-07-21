"""Append-only model call ledger helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def append_model_call_ledger(path: str | Path, row: dict[str, Any]) -> dict[str, Any]:
    required = {"schema_version", "call_id", "stage", "cost_estimate_usd", "sprint_id", "browser_session_id", "chatgpt_url", "latency_ms"}
    missing = sorted(required - set(row))
    if missing:
        raise ValueError(f"model_call_ledger row missing required fields: {missing}")
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row
