"""TrackedAdapter — discover repos from a manually tracked list in config.

Sprint: sprint-20260524-p0-ai-influence-github-project-intelligence-system-upgrade-s03-core-runtime
Node:   C2_adapters_snapshots / adapter:tracked

Config schema (dict or JSON file path):
    {
        "tracked_repos": [
            {"full_name": "owner/repo", "tags": ["llm"], "priority": 1},
            ...
        ]
    }

The TrackedAdapter does NOT call the network; it just emits DiscoveryCandidate
objects for each configured repo so they are queued for snapshot collection.

fetch_fn is accepted for interface parity (ignored internally).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

if __package__ is None or __package__ == "":
    import os as _os
    sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    from schema import DiscoveryCandidate, utc_now_iso
else:
    from ..schema import DiscoveryCandidate, utc_now_iso


_VALID_FULL_NAME_RE_STR = r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.\-]+$"
import re as _re
_VALID_FULL_NAME_RE = _re.compile(_VALID_FULL_NAME_RE_STR)


def _normalize_entry(entry: Any) -> dict[str, Any] | None:
    """Accept str or dict entry, return normalized dict or None if invalid."""
    if isinstance(entry, str):
        full_name = entry.strip()
        entry_dict: dict[str, Any] = {"full_name": full_name}
    elif isinstance(entry, dict):
        full_name = (entry.get("full_name") or "").strip()
        entry_dict = dict(entry)
        entry_dict["full_name"] = full_name
    else:
        return None
    if not _VALID_FULL_NAME_RE.match(full_name):
        return None
    return entry_dict


class TrackedAdapter:
    """Emit DiscoveryCandidate records for each configured tracked repo."""

    source_type = "tracked"

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        config_path: str | Path | None = None,
        fetch_fn: Callable[..., Any] | None = None,  # accepted, unused
    ) -> None:
        """Initialize with a config dict OR a path to a JSON config file.

        Args:
            config: Dict with 'tracked_repos' key.
            config_path: Path to a JSON file with 'tracked_repos' key.
              If both are given, config_path is ignored.
        """
        self._config_path = config_path
        self._static_config = config
        # fetch_fn is ignored; accepted only for interface parity

    def _load_config(self) -> dict[str, Any]:
        if self._static_config is not None:
            return self._static_config
        if self._config_path is not None:
            path = Path(self._config_path)
            if path.exists():
                with path.open("r", encoding="utf-8") as f:
                    return json.load(f)
        return {}

    def run(
        self,
        since: datetime | None = None,
        fetch_fn: Callable[..., Any] | None = None,
    ) -> list[DiscoveryCandidate]:
        """Return DiscoveryCandidate for each tracked repo.

        Args:
            since: Unused; kept for interface parity.
            fetch_fn: Unused; kept for interface parity.
        """
        cfg = self._load_config()
        raw_entries = cfg.get("tracked_repos") or []
        now = utc_now_iso()
        seen: set[str] = set()
        results: list[DiscoveryCandidate] = []

        for raw in raw_entries:
            entry = _normalize_entry(raw)
            if entry is None:
                continue
            full_name = entry["full_name"]
            if full_name in seen:
                continue
            seen.add(full_name)
            results.append(
                DiscoveryCandidate(
                    full_name=full_name,
                    source_type=self.source_type,
                    discovered_at=now,
                    metadata={
                        "tags": entry.get("tags") or [],
                        "priority": entry.get("priority"),
                        "note": entry.get("note"),
                    },
                )
            )

        return results


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

_SAMPLE_CONFIG: dict[str, Any] = {
    "tracked_repos": [
        {"full_name": "openai/openai-python", "tags": ["llm", "sdk"], "priority": 1},
        {"full_name": "ggerganov/llama.cpp", "tags": ["inference"], "priority": 1},
        {"full_name": "mlc-ai/mlc-llm", "tags": ["mlx", "llm"], "priority": 2},
        # plain string form
        "anthropic/anthropic-sdk-python",
        # duplicate — should be deduped
        {"full_name": "openai/openai-python", "tags": ["dup"]},
    ]
}


def _self_test() -> dict[str, Any]:
    metrics: dict[str, Any] = {"tests_run": 0, "tests_passed": 0, "details": []}

    def _ok(name: str) -> None:
        metrics["tests_run"] += 1
        metrics["tests_passed"] += 1
        metrics["details"].append({"test": name, "status": "pass"})

    def _fail(name: str, reason: str) -> None:
        metrics["tests_run"] += 1
        metrics["details"].append({"test": name, "status": "fail", "reason": reason})

    # Test 1: basic run count (4 unique repos after dedup)
    adapter = TrackedAdapter(config=_SAMPLE_CONFIG)
    candidates = adapter.run()
    if len(candidates) == 4:
        _ok("tracked_adapter.basic_run_count")
    else:
        _fail("tracked_adapter.basic_run_count", f"expected 4, got {len(candidates)}")

    # Test 2: source_type == 'tracked'
    if all(c.source_type == "tracked" for c in candidates):
        _ok("tracked_adapter.source_type_correct")
    else:
        _fail("tracked_adapter.source_type_correct", "wrong source_type")

    # Test 3: dedup works
    names = [c.full_name for c in candidates]
    if names.count("openai/openai-python") == 1:
        _ok("tracked_adapter.dedup_works")
    else:
        _fail("tracked_adapter.dedup_works", f"names={names}")

    # Test 4: string entry parsed
    if "anthropic/anthropic-sdk-python" in names:
        _ok("tracked_adapter.string_entry_accepted")
    else:
        _fail("tracked_adapter.string_entry_accepted", f"names={names}")

    # Test 5: metadata tags preserved
    llama = next(c for c in candidates if c.full_name == "ggerganov/llama.cpp")
    if llama.metadata.get("tags") == ["inference"] and llama.metadata.get("priority") == 1:
        _ok("tracked_adapter.metadata_tags_preserved")
    else:
        _fail("tracked_adapter.metadata_tags_preserved", f"metadata={llama.metadata}")

    # Test 6: invalid full_name filtered out
    bad_config: dict[str, Any] = {
        "tracked_repos": [
            "not-a-valid-full-name",
            {"full_name": ""},
            {"full_name": "valid/repo"},
        ]
    }
    bad_adapter = TrackedAdapter(config=bad_config)
    bad_candidates = bad_adapter.run()
    if len(bad_candidates) == 1 and bad_candidates[0].full_name == "valid/repo":
        _ok("tracked_adapter.invalid_entries_filtered")
    else:
        _fail("tracked_adapter.invalid_entries_filtered",
              f"got {[c.full_name for c in bad_candidates]}")

    # Test 7: empty config returns []
    empty_adapter = TrackedAdapter(config={})
    if empty_adapter.run() == []:
        _ok("tracked_adapter.empty_config_returns_empty")
    else:
        _fail("tracked_adapter.empty_config_returns_empty", "expected []")

    # Test 8: no config at all returns []
    none_adapter = TrackedAdapter()
    if none_adapter.run() == []:
        _ok("tracked_adapter.no_config_returns_empty")
    else:
        _fail("tracked_adapter.no_config_returns_empty", "expected []")

    # Test 9: config_path from a tempfile
    import tempfile
    import os

    cfg_data = {"tracked_repos": [{"full_name": "torch/pytorch", "tags": ["ml"]}]}
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as tf:
        json.dump(cfg_data, tf)
        tf_path = tf.name
    try:
        path_adapter = TrackedAdapter(config_path=tf_path)
        path_cands = path_adapter.run()
        if len(path_cands) == 1 and path_cands[0].full_name == "torch/pytorch":
            _ok("tracked_adapter.config_path_loaded")
        else:
            _fail("tracked_adapter.config_path_loaded", f"got {[c.full_name for c in path_cands]}")
    finally:
        os.unlink(tf_path)

    # Test 10: fetch_fn at run() is silently accepted (parity check)
    def _dummy_fn(url: str, headers: dict) -> Any:
        return {}

    parity_adapter = TrackedAdapter(config={"tracked_repos": ["owner/repo"]})
    parity_cands = parity_adapter.run(fetch_fn=_dummy_fn)
    if len(parity_cands) == 1:
        _ok("tracked_adapter.fetch_fn_parity_accepted")
    else:
        _fail("tracked_adapter.fetch_fn_parity_accepted", f"got {len(parity_cands)}")

    return metrics


if __name__ == "__main__":
    m = _self_test()
    print(json.dumps(m, indent=2))
    sys.exit(0 if m["tests_run"] == m["tests_passed"] else 1)
