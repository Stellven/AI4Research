from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


# Was Path("~/Solar/harness/..."), a machine-local path from one developer's
# checkout that Path never expands, so this module failed to load everywhere.
SCRIPT = Path(__file__).resolve().parents[2] / "harness" / "scripts" / "ai_influence_daily.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("solar_ai_influence_daily_recency_test", str(SCRIPT))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_filter_recent_candidates_excludes_posts_older_than_30_days():
    mod = _load_module()
    candidates = [
        mod.Candidate(
            handle="fresh",
            text="recent agent workflow update",
            tweet_url="https://x.com/fresh/status/1",
            published_at="2026-05-25T10:00:00Z",
            source_method="dom_direct",
        ),
        mod.Candidate(
            handle="old",
            text="old pinned vibe coding thread",
            tweet_url="https://x.com/old/status/2",
            published_at="2026-02-02T10:00:00Z",
            source_method="dom_direct",
        ),
    ]

    recent, stale, missing = mod.filter_recent_candidates(
        candidates,
        date_str="2026-05-30",
        max_age_days=30,
    )

    assert [c.handle for c in recent] == ["fresh"]
    assert [c.handle for c in stale] == ["old"]
    assert missing == []


def test_rank_candidates_prefers_newer_post_on_score_tie():
    mod = _load_module()
    older = mod.Candidate(
        handle="older",
        text="agent workflow prompt template",
        tweet_url="https://x.com/older/status/1",
        published_at="2026-05-10T10:00:00Z",
        source_method="dom_direct",
    )
    newer = mod.Candidate(
        handle="newer",
        text="agent workflow prompt template",
        tweet_url="https://x.com/newer/status/2",
        published_at="2026-05-29T10:00:00Z",
        source_method="dom_direct",
    )

    ranked = mod.rank_candidates([older, newer], top_n=2)

    assert [c.handle for c in ranked] == ["newer", "older"]


def test_filter_pinned_candidates_excludes_pinned_rows():
    mod = _load_module()
    candidates = [
        mod.Candidate(
            handle="pinned",
            text="Pinned AI course launch",
            tweet_url="https://x.com/pinned/status/1",
            published_at="2026-05-29T10:00:00Z",
            source_method="dom_direct",
            is_pinned=True,
        ),
        mod.Candidate(
            handle="fresh",
            text="new agent workflow drop",
            tweet_url="https://x.com/fresh/status/2",
            published_at="2026-05-29T11:00:00Z",
            source_method="dom_direct",
        ),
    ]

    kept, pinned = mod.filter_pinned_candidates(candidates)

    assert [c.handle for c in kept] == ["fresh"]
    assert [c.handle for c in pinned] == ["pinned"]


def test_prune_recent_per_handle_keeps_latest_four():
    mod = _load_module()
    candidates = [
        mod.Candidate(
            handle="same",
            text=f"workflow update {idx}",
            tweet_url=f"https://x.com/same/status/{idx}",
            published_at=f"2026-05-{idx:02d}T10:00:00Z",
            source_method="dom_direct",
        )
        for idx in range(20, 26)
    ]

    kept, overflow = mod.prune_recent_per_handle(candidates, max_per_handle=4)

    assert [c.published_at for c in kept] == [
        "2026-05-25T10:00:00Z",
        "2026-05-24T10:00:00Z",
        "2026-05-23T10:00:00Z",
        "2026-05-22T10:00:00Z",
    ]
    assert len(overflow) == 2
