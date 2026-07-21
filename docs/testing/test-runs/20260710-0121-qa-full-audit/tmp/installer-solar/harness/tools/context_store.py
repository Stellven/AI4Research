"""context_store.py — Context packet store for actor task envelopes.

Loads/stores context packets referenced by task envelopes,
without pane-memory dependence.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

HOME = Path.home()
HARNESS_DIR = Path.home() / ".solar" / "harness"
CONTEXT_STORE_DIR = HARNESS_DIR / "run" / "context-store"


class ContextStore:
    """File-based context packet store."""

    def __init__(self, store_dir: Optional[Path] = None):
        self.store_dir = store_dir or CONTEXT_STORE_DIR

    def save(self, packet_id: str, data: Dict[str, Any]) -> str:
        self.store_dir.mkdir(parents=True, exist_ok=True)
        path = self.store_dir / f"{packet_id}.json"
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def load(self, packet_id: str) -> Optional[Dict[str, Any]]:
        path = self.store_dir / f"{packet_id}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def resolve_ref(self, ref: Optional[Dict[str, str]]) -> Optional[Dict[str, Any]]:
        """Resolve a context_packet_ref {path, packet_id} to actual data."""
        if not ref:
            return None
        pid = ref.get("packet_id")
        if pid:
            return self.load(pid)
        path = ref.get("path")
        if path:
            p = Path(path)
            if not p.is_absolute():
                p = HARNESS_DIR / path
            if p.exists():
                try:
                    return json.loads(p.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    return None
        return None
