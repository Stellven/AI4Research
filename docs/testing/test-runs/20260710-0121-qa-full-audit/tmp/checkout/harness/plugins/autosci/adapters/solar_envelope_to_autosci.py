"""Normalize Solar operator envelopes for the AutoSci backend bridge."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_envelope(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return normalize_envelope(data)


def normalize_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(envelope)
    normalized.setdefault("task_id", "task-autosci-fixture")
    normalized.setdefault("sprint_id", "sprint-autosci-fixture")
    normalized.setdefault("node_id", "node-autosci-fixture")
    normalized.setdefault("mode", "fixture")
    normalized.setdefault("inputs", {})
    return normalized
