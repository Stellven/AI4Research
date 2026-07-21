"""Write-scope policy.

check(write_set, node_write_scope) -> (verdict, reason)

verdict ∈ {"PASS", "DENY"}.

A path is in scope iff it is exactly listed in node_write_scope OR it
sits under a scope entry treated as a directory prefix. An empty
node_write_scope denies any non-empty write_set; an empty write_set
passes trivially (nothing to authorize).
"""

from __future__ import annotations

from typing import Iterable


def _normalize(path: str) -> str:
    return path.rstrip("/")


def _in_scope(path: str, scope: Iterable[str]) -> bool:
    p = _normalize(path)
    for raw in scope:
        if not raw:
            continue
        entry = _normalize(raw)
        if p == entry:
            return True
        if p.startswith(entry + "/"):
            return True
    return False


def check(write_set, node_write_scope) -> tuple[str, str]:
    write_set = list(write_set or [])
    node_write_scope = list(node_write_scope or [])

    if not write_set:
        return ("PASS", "write_set empty; nothing to authorize")
    if not node_write_scope:
        return ("DENY", "node_write_scope is empty; no writes permitted")

    for path in write_set:
        if not _in_scope(path, node_write_scope):
            return ("DENY", f"path '{path}' not in node write_scope")
    return ("PASS", "all paths within write_scope")
