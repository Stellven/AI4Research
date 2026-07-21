"""Internal Mirage VFS source connector for DeepResearch.

Uses existing `solar-harness mirage search` and file reads via pathlib.
No HTTP imports — all access is local filesystem + subprocess CLI.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from .base import BaseSourceConnector, FetchResult, SearchResult

_MIRAGE_CMD = "mirage"
_FALLBACK_CMD_PATH = Path.home() / ".solar" / "harness" / "solar-harness.sh"


def _run_mirage_search(query: str, max_hits: int, json_output: bool = True) -> str:
    """Run mirage search via subprocess. Returns stdout."""
    cmd = [_FALLBACK_CMD_PATH, "mirage", "search", query, "--max", str(max_hits)]
    if json_output:
        cmd.append("--json")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"mirage search failed (rc={result.returncode}): {result.stderr[:500]}")
    return result.stdout


def _parse_search_output(raw: str) -> list[dict[str, Any]]:
    """Parse mirage search JSON output into list of dicts."""
    if not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        results = data.get("results") or data.get("hits") or []
        return results if isinstance(results, list) else []
    return []


class InternalMirageConnector(BaseSourceConnector):
    """Searches and fetches from the local Mirage VFS knowledge base."""

    connector_id = "internal_mirage"
    connector_type = "internal_mirage"
    source_tier = "internal"
    display_name = "Mirage VFS (Local Knowledge)"

    def __init__(self, vault_path: Optional[Path] = None) -> None:
        self.vault_path = vault_path or Path.home() / "Knowledge"

    def search(self, query: str, max_hits: int = 10, **kwargs: Any) -> list[SearchResult]:
        """Search Mirage VFS for documents matching query."""
        try:
            raw = _run_mirage_search(query, max_hits)
        except (RuntimeError, subprocess.TimeoutExpired, FileNotFoundError):
            try:
                cmd = [sys.executable, "-m", "mirage_search", query, "--max", str(max_hits), "--json"]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                raw = result.stdout if result.returncode == 0 else "[]"
            except Exception:
                return []

        hits = _parse_search_output(raw)
        results: list[SearchResult] = []
        for i, hit in enumerate(hits[:max_hits]):
            path_str = hit.get("path") or hit.get("file") or hit.get("url") or ""
            results.append(SearchResult(
                source_id=f"mirage:{path_str}" if path_str else f"mirage:hit-{i}",
                connector_id=self.connector_id,
                title=hit.get("title") or Path(path_str).stem if path_str else f"Mirage hit {i}",
                url=path_str,
                snippet=hit.get("snippet") or hit.get("excerpt") or hit.get("text", "")[:200],
                metadata=hit,
                score=float(hit.get("score", 0.0)),
            ))
        return results

    def fetch(self, source_id: str) -> FetchResult:
        """Read a file from Mirage VFS by source_id (mirage:<path>)."""
        if not source_id.startswith("mirage:"):
            return FetchResult(
                source_id=source_id,
                connector_id=self.connector_id,
                title="",
                raw_text="",
                fetch_status="failed",
                fetch_error=f"Invalid source_id format: {source_id!r}",
            )

        rel_path = source_id[len("mirage:"):]
        file_path = self.vault_path / rel_path

        if not file_path.exists():
            return FetchResult(
                source_id=source_id,
                connector_id=self.connector_id,
                title=Path(rel_path).stem,
                raw_text="",
                fetch_status="failed",
                fetch_error=f"File not found: {file_path}",
            )

        try:
            raw_text = file_path.read_text(encoding="utf-8")
        except Exception as exc:
            return FetchResult(
                source_id=source_id,
                connector_id=self.connector_id,
                title=Path(rel_path).stem,
                raw_text="",
                fetch_status="failed",
                fetch_error=str(exc),
            )

        return FetchResult(
            source_id=source_id,
            connector_id=self.connector_id,
            title=Path(rel_path).stem,
            raw_text=raw_text,
            source_url=str(file_path),
            metadata={"file_extension": file_path.suffix, "file_size": file_path.stat().st_size},
        )
