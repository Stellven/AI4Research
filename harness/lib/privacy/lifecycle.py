"""Sandbox-scoped privacy operations.  No operation infers a user home."""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

EMAIL = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")
PHONE = re.compile(r"\b(?:\+?\d[\d -]{7,}\d)\b")
SECRET = re.compile(r"\b(?:Bearer\s+)?[A-Za-z0-9_-]{20,}\b")


def redact_text(value: str) -> str:
    value = EMAIL.sub("[EMAIL]", value)
    value = PHONE.sub("[PHONE]", value)
    return SECRET.sub("[REDACTED]", value)


def under_root(path: Path, root: Path) -> Path:
    candidate = path.resolve(strict=False)
    try:
        candidate.relative_to(root.resolve(strict=False))
    except ValueError as exc:
        raise ValueError("path must stay inside the explicit sandbox home") from exc
    return candidate


def write_redacted_export(root: Path, destination: Path, payload: dict[str, Any]) -> Path:
    import json

    target = under_root(destination, root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(redact_text(json.dumps(payload, sort_keys=True)), encoding="utf-8")
    return target


def remove_personal_data_surfaces(root: Path) -> list[str]:
    """Remove every product-owned data surface, including derived residue."""
    removed: list[str] = []
    for name in ("primary", "cache", "index", "logs", "derived", "backups"):
        target = root / name
        if target.exists():
            shutil.rmtree(target)
            removed.append(name)
    return removed
