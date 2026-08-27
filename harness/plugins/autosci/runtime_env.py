"""Load explicitly allowlisted local provider secrets without serializing them."""

from __future__ import annotations

import os
from collections.abc import MutableMapping
from pathlib import Path


PROVIDER_SECRET_KEYS = frozenset({"SEMANTIC_SCHOLAR_API_KEY"})


def load_local_provider_env(
    path: str | Path,
    *,
    env: MutableMapping[str, str] | None = None,
) -> set[str]:
    """Load missing allowlisted keys from a dotenv file and return key names only."""
    target = os.environ if env is None else env
    dotenv = Path(path)
    if not dotenv.is_file():
        return set()

    loaded: set[str] = set()
    for raw_line in dotenv.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in PROVIDER_SECRET_KEYS or target.get(key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if not value:
            continue
        target[key] = value
        loaded.add(key)
    return loaded
