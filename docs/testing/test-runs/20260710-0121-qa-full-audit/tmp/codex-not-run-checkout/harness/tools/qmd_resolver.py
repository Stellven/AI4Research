#!/usr/bin/env python3
"""Shared qmd binary resolver for Solar harness Python entrypoints."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def resolve_qmd_bin() -> str:
    candidates: list[Path] = []
    env_qmd = os.environ.get("QMD_BIN", "").strip()
    if env_qmd:
        candidates.append(Path(env_qmd).expanduser())

    path_qmd = shutil.which("qmd")
    if path_qmd:
        candidates.append(Path(path_qmd))

    home = Path.home()
    candidates.extend(
        [
            home / ".npm-global/bin/qmd",
            home / "n/bin/qmd",
            Path("/opt/homebrew/bin/qmd"),
            Path("/usr/local/bin/qmd"),
        ]
    )

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists() and os.access(candidate, os.X_OK):
            return key
    return ""
