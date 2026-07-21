from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from .backend_selector import BackendSelector, TIER_ORDER
from .cli import EXIT_OK
from .hard_blocker_guard import CallableResolver, HardBlockerGuard
from .pipeline import AccountConfig, Pipeline
from .schema import BACKEND_BROWSER_AGENT, BACKEND_RSS_PUBLIC


def _base_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE social_posts ("
        "post_id TEXT, author_handle TEXT, text TEXT, created_at TEXT, "
        "post_url TEXT, reply_count INTEGER, repost_count INTEGER, "
        "like_count INTEGER, view_count INTEGER, urls TEXT"
        ")"
    )
    return conn


def test_selector_order_is_contract_order() -> None:
    assert TIER_ORDER == (
        "browser_agent",
        "rss_public",
        "manual_curated",
        "x_api",
    )


def test_selector_falls_back_to_rss_when_real_blocker_unmet() -> None:
    guard = HardBlockerGuard(
        resolver=CallableResolver(lambda: False),
        mock_mode_probe=lambda: False,
    )
    result = BackendSelector(guard=guard).select("auto")

    assert result.selected == BACKEND_RSS_PUBLIC
    assert result.walked[0].backend == BACKEND_BROWSER_AGENT
    assert result.walked[0].available is False
    assert result.walked[0].reason == "hard_blocker_unmet"
    assert result.walked[1].backend == BACKEND_RSS_PUBLIC
    assert result.walked[1].available is True


def test_explicit_browser_request_falls_back_to_rss_without_lease() -> None:
    guard = HardBlockerGuard(
        resolver=CallableResolver(lambda: False),
        mock_mode_probe=lambda: False,
    )
    result = BackendSelector(guard=guard).select("browser")

    assert result.selected == BACKEND_RSS_PUBLIC
    assert result.fallback_from_explicit is True


def test_guard_real_mode_raises_and_mock_mode_returns_ready() -> None:
    real_guard = HardBlockerGuard(
        resolver=CallableResolver(lambda: False),
        mock_mode_probe=lambda: False,
    )
    with pytest.raises(Exception):
        real_guard.assert_ready()

    mock_guard = HardBlockerGuard(
        resolver=CallableResolver(lambda: False),
        mock_mode_probe=lambda: True,
    )
    status = mock_guard.assert_ready()
    assert status.mode == "mock"
    assert status.mock_ready is True


def test_pipeline_mock_mode_runs_browser_lease_and_persists_posts(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BROWSER_AGENT_MOCK_MODE", "1")
    socket_path = tmp_path / "thunderomlx.socket"
    socket_path.write_text("mock socket", encoding="utf-8")

    conn = _base_conn()
    guard = HardBlockerGuard(
        resolver=CallableResolver(lambda: False),
        mock_mode_probe=lambda: True,
    )
    pipeline = Pipeline(conn, guard=guard, thunderomlx_socket=socket_path)
    result = pipeline.run(
        accounts=[AccountConfig(handle="karpathy", tier=1, profile_url="https://x.com/karpathy")],
        requested_backend="auto",
    )

    assert result.exit_code == EXIT_OK
    assert result.selection.selected == BACKEND_BROWSER_AGENT
    assert result.posts_stored == 1
    assert result.posts_deduped == 0
    assert result.parse_failures == 0
    assert {entry.step for entry in result.ledger} == {"lease", "extract", "semantic"}
    row_count = conn.execute("SELECT COUNT(*) FROM social_posts").fetchone()[0]
    ledger_count = conn.execute("SELECT COUNT(*) FROM model_call_ledger").fetchone()[0]
    assert row_count == 1
    assert ledger_count == 3


def test_pipeline_real_mode_unmet_blocker_falls_back_without_lease(monkeypatch) -> None:
    monkeypatch.delenv("BROWSER_AGENT_MOCK_MODE", raising=False)
    conn = _base_conn()
    guard = HardBlockerGuard(
        resolver=CallableResolver(lambda: False),
        mock_mode_probe=lambda: False,
    )
    pipeline = Pipeline(conn, guard=guard)
    result = pipeline.run(
        accounts=[AccountConfig(handle="karpathy", tier=1, profile_url="https://x.com/karpathy")],
        requested_backend="auto",
    )

    assert result.selection.selected == BACKEND_RSS_PUBLIC
    assert result.posts_stored == 0
    assert result.posts_skipped == 0
    assert result.parse_failures == 1
    assert result.ledger == []
    assert conn.execute("SELECT COUNT(*) FROM social_posts").fetchone()[0] == 0
