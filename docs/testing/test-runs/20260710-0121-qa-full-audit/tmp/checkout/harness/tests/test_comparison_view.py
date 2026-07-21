"""Tests for lib/github_comparison_view.py (N4 — GitHub dual-run comparison view)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Ensure lib/ is on sys.path regardless of invocation directory
_LIB = Path(__file__).parent.parent / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from github_comparison_view import (
    GitHubComparisonData,
    GitHubRunMetrics,
    _derive_metrics,
    build_comparison,
    inject_into_status_html,
    render_comparison_html,
)


# ── fixtures ──────────────────────────────────────────────────────────────────


def _write_metadata(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


FULL_META_NEW = {
    "schema_version": "solar.operator_metadata.v1",
    "operator": "github_new",
    "run_status": "succeeded",
    "started_at": "2026-05-31T10:00:00Z",
    "items_processed": 42,
    "source_count": 45,
    "duration_seconds": 87.3,
    "artifacts": {"report": "reports/github/new/report.md"},
    "errors": [],
}

FULL_META_LEGACY = {
    "schema_version": "solar.operator_metadata.v1",
    "operator": "github_legacy",
    "run_status": "failed",
    "started_at": "2026-05-30T10:00:00Z",
    "items_processed": 10,
    "source_count": 40,
    "duration_seconds": 15.0,
    "artifacts": {},
    "errors": [{"message": "Connection timeout"}, {"message": "Rate limited"}],
}


# ── _derive_metrics ───────────────────────────────────────────────────────────


class TestDeriveMetrics:
    def test_none_metadata_returns_no_data(self):
        m = _derive_metrics("new", None)
        assert m.run_status == "no_data"
        assert m.items_processed is None
        assert m.report_quality is None
        assert m.error_rate is None
        assert m.duration_s is None

    def test_succeeded_with_artifacts(self):
        m = _derive_metrics("new", FULL_META_NEW)
        assert m.run_status == "succeeded"
        assert m.items_processed == 42
        assert m.report_quality == 1.0
        assert m.error_rate == 0.0
        assert m.duration_s == pytest.approx(87.3)
        assert m.last_run == "2026-05-31T10:00:00Z"

    def test_failed_with_errors(self):
        m = _derive_metrics("legacy", FULL_META_LEGACY)
        assert m.run_status == "failed"
        assert m.report_quality == 0.0
        assert len(m.errors) == 2
        # error_rate = 2 errors / 40 attempted
        assert m.error_rate == pytest.approx(2 / 40)

    def test_succeeded_no_artifacts(self):
        meta = {**FULL_META_NEW, "artifacts": {}}
        m = _derive_metrics("new", meta)
        assert m.report_quality == 0.8

    def test_running_has_no_quality(self):
        m = _derive_metrics("new", {"run_status": "running"})
        assert m.report_quality is None
        assert m.error_rate is None

    def test_variant_field_preserved(self):
        m = _derive_metrics("legacy", FULL_META_LEGACY)
        assert m.variant == "legacy"


# ── build_comparison ──────────────────────────────────────────────────────────


class TestBuildComparison:
    def test_both_variants_present(self, tmp_path):
        _write_metadata(tmp_path / "github" / "new" / "metadata.json", FULL_META_NEW)
        _write_metadata(tmp_path / "github" / "legacy" / "metadata.json", FULL_META_LEGACY)

        data = build_comparison(tmp_path)

        assert isinstance(data.new_run, GitHubRunMetrics)
        assert data.new_run.run_status == "succeeded"
        assert isinstance(data.legacy_run, GitHubRunMetrics)
        assert data.legacy_run.run_status == "failed"

    def test_legacy_absent_degrades(self, tmp_path):
        _write_metadata(tmp_path / "github" / "new" / "metadata.json", FULL_META_NEW)

        data = build_comparison(tmp_path)

        assert data.new_run.run_status == "succeeded"
        assert data.legacy_run is None  # degraded

    def test_flat_fallback_for_new(self, tmp_path):
        # If reports/github/metadata.json exists but no new/ subdir
        _write_metadata(tmp_path / "github" / "metadata.json", FULL_META_NEW)

        data = build_comparison(tmp_path)

        assert data.new_run.items_processed == 42
        assert data.legacy_run is None

    def test_no_data_at_all(self, tmp_path):
        data = build_comparison(tmp_path)

        assert data.new_run.run_status == "no_data"
        assert data.legacy_run is None

    def test_default_dir_does_not_raise(self):
        # Should return gracefully even if default path has no github data
        data = build_comparison()
        assert isinstance(data, GitHubComparisonData)


# ── render_comparison_html ────────────────────────────────────────────────────


class TestRenderComparisonHtml:
    def _make_data(self, new_meta=None, legacy_meta=None):
        new_run = _derive_metrics("new", new_meta)
        legacy_run = _derive_metrics("legacy", legacy_meta) if legacy_meta is not None else None
        return GitHubComparisonData(new_run=new_run, legacy_run=legacy_run)

    def test_contains_new_label(self):
        data = self._make_data(new_meta=FULL_META_NEW)
        out = render_comparison_html(data)
        assert "GitHub New" in out

    def test_contains_legacy_label_when_present(self):
        data = self._make_data(new_meta=FULL_META_NEW, legacy_meta=FULL_META_LEGACY)
        out = render_comparison_html(data)
        assert "GitHub Legacy" in out
        # When legacy is present, the column div should NOT carry the absent modifier class
        assert 'class="cmp-col cmp-col--absent"' not in out

    def test_degraded_mode_when_legacy_absent(self):
        data = self._make_data(new_meta=FULL_META_NEW)
        out = render_comparison_html(data)
        assert "cmp-col--absent" in out
        assert "not available" in out

    def test_four_comparison_dimensions_present(self):
        data = self._make_data(new_meta=FULL_META_NEW, legacy_meta=FULL_META_LEGACY)
        out = render_comparison_html(data)
        for dim_label in ("Items Processed", "Report Quality", "Error Rate", "Run Duration"):
            assert dim_label in out, f"Missing dimension: {dim_label}"

    def test_no_xss_in_operator_values(self):
        malicious = {
            **FULL_META_NEW,
            "run_status": '<script>alert(1)</script>',
        }
        data = self._make_data(new_meta=malicious)
        out = render_comparison_html(data)
        assert "<script>" not in out
        assert "&lt;script&gt;" in out

    def test_error_messages_shown(self):
        data = self._make_data(new_meta=FULL_META_NEW, legacy_meta=FULL_META_LEGACY)
        out = render_comparison_html(data)
        assert "Connection timeout" in out

    def test_html_fragment_no_doctype(self):
        data = self._make_data(new_meta=FULL_META_NEW)
        out = render_comparison_html(data)
        assert "<!doctype" not in out.lower()

    def test_returns_string(self):
        data = self._make_data()
        out = render_comparison_html(data)
        assert isinstance(out, str)
        assert len(out) > 0


# ── inject_into_status_html ───────────────────────────────────────────────────


class TestInjectIntoStatusHtml:
    def test_placeholder_replaced(self, tmp_path):
        _write_metadata(tmp_path / "github" / "new" / "metadata.json", FULL_META_NEW)
        base_html = "<body>{{GITHUB_COMPARISON}}</body>"
        result = inject_into_status_html(base_html, reports_dir=tmp_path)
        assert "{{GITHUB_COMPARISON}}" not in result
        assert "GitHub New" in result

    def test_fallback_insert_before_body_close(self, tmp_path):
        base_html = "<body><p>Status</p></body>"
        result = inject_into_status_html(base_html, reports_dir=tmp_path)
        assert result.endswith("</body>")
        assert "github-comparison" in result

    def test_idempotent_placeholder(self, tmp_path):
        base_html = "<body>{{GITHUB_COMPARISON}}</body>"
        result = inject_into_status_html(base_html, reports_dir=tmp_path)
        # The outer wrapper div appears exactly once (CSS class name appears more, that's fine)
        assert result.count('<div class="github-comparison">') == 1
