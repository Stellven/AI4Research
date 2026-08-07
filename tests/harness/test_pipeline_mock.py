from __future__ import annotations

import sqlite3
from pathlib import Path

from social_browser_backend_x.post_extractor import ExtractionResult, PostExtractor
from social_browser_backend_x.hard_blocker_guard import CallableResolver, HardBlockerGuard
from social_browser_backend_x.pipeline import AccountConfig, Pipeline
from social_browser_backend_x.schema import PostRecord
from social_browser_backend_x.schema import BACKEND_BROWSER_AGENT


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE social_posts ("
        "post_id TEXT, author_handle TEXT, text TEXT, created_at TEXT, "
        "post_url TEXT, reply_count INTEGER, repost_count INTEGER, "
        "like_count INTEGER, view_count INTEGER, urls TEXT)"
    )
    return conn


def test_pipeline_mock_mode_runs_10_step_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BROWSER_AGENT_MOCK_MODE", "1")
    socket_path = tmp_path / "thunderomlx.sock"
    socket_path.write_text("ready", encoding="utf-8")
    guard = HardBlockerGuard(
        resolver=CallableResolver(lambda: False),
        mock_mode_probe=lambda: True,
    )
    conn = _conn()
    artifact_root = tmp_path / "artifacts"
    result = Pipeline(
        conn,
        guard=guard,
        thunderomlx_socket=socket_path,
        artifact_root=artifact_root,
    ).run(
        accounts=[AccountConfig(handle="karpathy", tier=1, profile_url="https://x.com/karpathy")],
        requested_backend="auto",
    )

    assert result.exit_code == 0
    assert result.selection.selected == BACKEND_BROWSER_AGENT
    assert result.posts_stored == 1
    assert result.posts_deduped == 0
    assert result.posts_skipped == 0
    assert result.parse_failures == 0
    assert len(result.scans) == 1

    scan = result.scans[0]
    assert scan.lease_token is not None
    assert scan.dom_html
    assert scan.extraction is not None and scan.extraction.parse_ok is True
    assert scan.dedup_verdict is not None and scan.dedup_verdict.is_duplicate is False
    assert scan.post_pk is not None
    assert scan.metrics["like_count"] == 9873
    assert scan.semantic_result is not None and scan.semantic_result["reused_instance"] is True
    assert isinstance(scan.links, list)
    assert isinstance(scan.viewpoints, list)
    assert scan.propagation_score >= 0.0
    assert scan.knowledge_raw_path is not None
    assert scan.extract_queue_path is not None
    assert Path(scan.knowledge_raw_path).is_file()
    assert Path(scan.extract_queue_path).is_file()

    assert {entry.step for entry in result.ledger} == {"lease", "extract", "semantic"}
    assert conn.execute("SELECT COUNT(*) FROM social_posts").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM model_call_ledger").fetchone()[0] == 3


def test_pipeline_real_browser_unwired_reports_lease_fallback(monkeypatch) -> None:
    monkeypatch.delenv("BROWSER_AGENT_MOCK_MODE", raising=False)
    guard = HardBlockerGuard(
        resolver=CallableResolver(lambda: True),
        mock_mode_probe=lambda: False,
    )
    conn = _conn()
    result = Pipeline(conn, guard=guard).run(
        accounts=[AccountConfig(handle="karpathy", tier=1, profile_url="https://x.com/karpathy")],
        requested_backend="browser",
    )

    assert result.exit_code == 1
    assert result.posts_stored == 0
    assert result.posts_skipped == 1
    assert result.scans[0].error is not None
    assert "operator_not_ready" in result.scans[0].error


def test_pipeline_second_scan_dedups_without_rewriting_posts(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BROWSER_AGENT_MOCK_MODE", "1")
    socket_path = tmp_path / "thunderomlx.sock"
    socket_path.write_text("ready", encoding="utf-8")
    guard = HardBlockerGuard(
        resolver=CallableResolver(lambda: False),
        mock_mode_probe=lambda: True,
    )
    conn = _conn()
    pipeline = Pipeline(
        conn,
        guard=guard,
        thunderomlx_socket=socket_path,
        artifact_root=tmp_path / "artifacts",
    )
    accounts = [AccountConfig(handle="karpathy", tier=1, profile_url="https://x.com/karpathy")]

    first = pipeline.run(accounts=accounts, requested_backend="auto")
    second = pipeline.run(accounts=accounts, requested_backend="auto")

    assert first.posts_stored == 1
    assert second.posts_stored == 0
    assert second.posts_deduped == 1
    assert conn.execute("SELECT COUNT(*) FROM social_posts").fetchone()[0] == 1
    assert second.scans[0].dedup_verdict is not None
    assert second.scans[0].dedup_verdict.is_duplicate is True


class _MixedExtractor(PostExtractor):
    def extract(self, html: str, *, author_handle_hint: str | None = None) -> ExtractionResult:
        if author_handle_hint == "jxmnop":
            record = PostRecord(
                post_id="N/A",
                author_handle="jxmnop",
                text="N/A",
                created_at=None,
                post_url="N/A",
                reply_count=0,
                repost_count=0,
                like_count=0,
                view_count=None,
                urls="",
                dom_hash="deadbeef",
                screenshot_path=None,
                collection_backend="browser_agent",
            )
            return ExtractionResult(record=record, missing_fields=("post_id",), parse_ok=False)
        return super().extract(html, author_handle_hint=author_handle_hint)


def test_pipeline_failure_isolation_keeps_other_accounts_progressing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BROWSER_AGENT_MOCK_MODE", "1")
    socket_path = tmp_path / "thunderomlx.sock"
    socket_path.write_text("ready", encoding="utf-8")
    guard = HardBlockerGuard(
        resolver=CallableResolver(lambda: False),
        mock_mode_probe=lambda: True,
    )
    conn = _conn()
    pipeline = Pipeline(
        conn,
        guard=guard,
        thunderomlx_socket=socket_path,
        extractor=_MixedExtractor(),
        artifact_root=tmp_path / "artifacts",
    )
    result = pipeline.run(
        accounts=[
            AccountConfig(handle="karpathy", tier=1, profile_url="https://x.com/karpathy"),
            AccountConfig(handle="jxmnop", tier=1, profile_url="https://x.com/jxmnop"),
        ],
        requested_backend="auto",
    )

    assert result.posts_stored == 1
    assert result.parse_failures == 1
    assert conn.execute("SELECT COUNT(*) FROM social_posts").fetchone()[0] == 1
    scans = {scan.handle: scan for scan in result.scans}
    assert scans["karpathy"].post_pk is not None
    assert scans["karpathy"].knowledge_raw_path is not None
    assert scans["jxmnop"].error is not None
    assert "parse_failed" in scans["jxmnop"].error
