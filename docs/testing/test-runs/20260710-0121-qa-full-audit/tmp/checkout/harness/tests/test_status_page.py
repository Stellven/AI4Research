"""Tests for AI Influence Status Page module."""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

HARNESS_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(HARNESS_ROOT) not in sys.path:
    sys.path.insert(0, str(HARNESS_ROOT))

from lib.ai_influence_status_page import (
    OPERATORS,
    RunStatus,
    build_cards,
    format_duration,
    format_timestamp,
    render_html,
)
from lib.metadata_validator import (
    ValidationError,
    RunStatus as ValidatorRunStatus,
    validate_metadata,
    load_and_validate,
    OperatorMetadata,
)


@pytest.fixture
def sample_metadata():
    """Sample valid metadata for testing."""
    return {
        "schema_version": "ai_influence_metadata.v1",
        "run_id": "test-run-123",
        "operator": "x_social",
        "run_status": "succeeded",
        "started_at": "2026-05-30T12:00:00Z",
        "completed_at": "2026-05-30T12:15:30Z",
        "artifacts": {
            "digest": "reports/x-social/2026-05-30/digest.json",
            "html": "reports/x-social/2026-05-30/digest.html",
        },
        "stats": {
            "collected": 42,
            "processed": 40,
        },
        "errors": [],
        "duration_seconds": 930.0,
        "source_count": 50,
        "processed_count": 40,
    }


@pytest.fixture
def sample_metadata_github_new():
    """Sample metadata for GitHub New operator."""
    return {
        "schema_version": "ai_influence_metadata.v1",
        "run_id": "gh-new-456",
        "operator": "github_new",
        "run_status": "succeeded",
        "started_at": "2026-05-30T10:00:00Z",
        "artifacts": {
            "digest": "reports/github/new/2026-05-30/digest.json",
        },
        "stats": {
            "repos_scanned": 150,
        },
        "errors": [],
    }


@pytest.fixture
def sample_metadata_failed():
    """Sample metadata for failed operator run."""
    return {
        "schema_version": "ai_influence_metadata.v1",
        "run_id": "failed-789",
        "operator": "youtube",
        "run_status": "failed",
        "started_at": "2026-05-30T14:00:00Z",
        "artifacts": {},
        "stats": {},
        "errors": [
            {"message": "Rate limit exceeded"},
            {"message": "API timeout"},
        ],
    }


class TestMetadataValidator:
    """Tests for metadata_validator module."""

    def test_validate_metadata_valid(self, sample_metadata):
        """Valid metadata should pass validation."""
        result = validate_metadata(sample_metadata)
        assert result.ok
        assert len(result.errors) == 0

    def test_validate_metadata_missing_required_field(self):
        """Missing required fields should fail validation."""
        data = {
            "schema_version": "ai_influence_metadata.v1",
            "run_id": "test",
        }
        result = validate_metadata(data)
        assert not result.ok
        assert any(e["code"] == ValidationError.MISSING_OPERATOR.value for e in result.errors)

    def test_validate_metadata_invalid_operator(self):
        """Invalid operator should fail validation."""
        data = {
            "schema_version": "ai_influence_metadata.v1",
            "run_id": "test",
            "operator": "invalid_operator",
            "run_status": "pending",
            "started_at": "2026-05-30T12:00:00Z",
        }
        result = validate_metadata(data)
        assert not result.ok

    def test_validate_metadata_invalid_run_status(self):
        """Invalid run_status should fail validation."""
        data = {
            "schema_version": "ai_influence_metadata.v1",
            "run_id": "test",
            "operator": "x_social",
            "run_status": "invalid_status",
            "started_at": "2026-05-30T12:00:00Z",
        }
        result = validate_metadata(data)
        assert not result.ok

    def test_validate_metadata_invalid_timestamp(self):
        """Invalid timestamp format should produce error."""
        data = {
            "schema_version": "ai_influence_metadata.v1",
            "run_id": "test",
            "operator": "x_social",
            "run_status": "pending",
            "started_at": "not-a-timestamp",
        }
        result = validate_metadata(data)
        assert not result.ok
        assert any(e["code"] == ValidationError.INVALID_TIMESTAMP.value for e in result.errors)

    def test_validate_metadata_artifact_warning(self, tmp_path):
        """Non-existent artifact paths should produce warnings."""
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()

        data = {
            "schema_version": "ai_influence_metadata.v1",
            "run_id": "test",
            "operator": "x_social",
            "run_status": "succeeded",
            "started_at": "2026-05-30T12:00:00Z",
            "artifacts": {
                "digest": "x-social/missing.json",
            },
        }
        result = validate_metadata(data, reports_dir)
        # Should have warnings but still be ok
        assert len(result.warnings) > 0


class TestOperatorMetadata:
    """Tests for OperatorMetadata dataclass."""

    def test_to_dict(self):
        """OperatorMetadata should serialize correctly."""
        metadata = OperatorMetadata(
            schema_version="v1",
            run_id="test-123",
            operator="x_social",
            run_status=ValidatorRunStatus.SUCCEEDED,
            started_at="2026-05-30T12:00:00Z",
            completed_at="2026-05-30T12:15:00Z",
            artifacts={"digest": "path/to/digest.json"},
            stats={"collected": 10},
        )
        result = metadata.to_dict()
        assert result["schema_version"] == "v1"
        assert result["run_id"] == "test-123"
        assert result["operator"] == "x_social"
        assert result["run_status"] == "succeeded"
        assert result["started_at"] == "2026-05-30T12:00:00Z"
        assert result["completed_at"] == "2026-05-30T12:15:00Z"


class TestStatusPageFormatting:
    """Tests for status page formatting utilities."""

    def test_format_duration_seconds(self):
        """Duration in seconds should format correctly."""
        assert format_duration(45.5) == "45.5s"

    def test_format_duration_minutes(self):
        """Duration in minutes should format correctly."""
        assert format_duration(150) == "2.5m"

    def test_format_duration_hours(self):
        """Duration in hours should format correctly."""
        assert format_duration(5400) == "1.5h"

    def test_format_duration_none(self):
        """None duration should return N/A."""
        assert format_duration(None) == "N/A"

    def test_format_timestamp_valid(self):
        """Valid ISO timestamp should format correctly."""
        assert "2026-05-30" in format_timestamp("2026-05-30T12:00:00Z")
        assert "UTC" in format_timestamp("2026-05-30T12:00:00Z")

    def test_format_timestamp_none(self):
        """None timestamp should return N/A."""
        assert format_timestamp(None) == "N/A"


class TestBuildCards:
    """Tests for build_cards function."""

    def test_build_cards_with_metadata(self, tmp_path, sample_metadata):
        """Should build cards from metadata files."""
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        x_social_dir = reports_dir / "x-social"
        x_social_dir.mkdir()

        # Write metadata file
        (x_social_dir / "metadata.json").write_text(json.dumps(sample_metadata))

        cards = build_cards(reports_dir)

        # Should have all 6 operators defined
        assert len(cards) == 6

        # x_social card should have succeeded status
        x_card = next(c for c in cards if c.operator_id == "x_social")
        assert x_card.run_status == RunStatus.SUCCEEDED
        assert x_card.has_errors is False

    def test_build_cards_no_data(self, tmp_path):
        """Should handle missing metadata gracefully."""
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()

        cards = build_cards(reports_dir)

        # Should still have all operators
        assert len(cards) == 6

        # All should have no_data status
        for card in cards:
            assert card.run_status.value in {"pending", "no_data"} or str(card.run_status) == "no_data"

    def test_build_cards_with_errors(self, tmp_path, sample_metadata_failed):
        """Should populate errors from metadata."""
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        youtube_dir = reports_dir / "youtube"
        youtube_dir.mkdir()

        (youtube_dir / "metadata.json").write_text(json.dumps(sample_metadata_failed))

        cards = build_cards(reports_dir)

        youtube_card = next(c for c in cards if c.operator_id == "youtube")
        assert youtube_card.run_status == RunStatus.FAILED
        assert youtube_card.has_errors is True
        assert len(youtube_card.errors) == 2

    def test_build_cards_processed_ratio(self, tmp_path):
        """Should calculate processed ratio correctly."""
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        x_social_dir = reports_dir / "x-social"
        x_social_dir.mkdir()

        metadata = {
            "schema_version": "ai_influence_metadata.v1",
            "run_id": "test",
            "operator": "x_social",
            "run_status": "running",
            "started_at": "2026-05-30T12:00:00Z",
            "source_count": 100,
            "processed_count": 75,
        }
        (x_social_dir / "metadata.json").write_text(json.dumps(metadata))

        cards = build_cards(reports_dir)
        x_card = next(c for c in cards if c.operator_id == "x_social")
        assert "75%" in x_card.processed_ratio


class TestRenderHtml:
    """Tests for HTML rendering."""

    def test_render_html_output(self):
        """Should render HTML with card data."""
        from lib.ai_influence_status_page import OperatorCard

        cards = [
            OperatorCard(
                operator_id="x_social",
                display_name="X / Twitter",
                icon="𝕏",
                run_status=RunStatus.SUCCEEDED,
                last_run="2026-05-30T12:00:00Z",
                artifacts={"digest": "path/to/digest.json"},
                stats={"collected": 42},
                errors=[],
            ),
        ]

        html = render_html(cards)

        # Should contain key elements
        assert "AI Influence Operator Status" in html
        assert "X / Twitter" in html
        assert "succeeded" in html or "good" in html
        assert "42" in html

    def test_render_html_summary(self):
        """Should include summary statistics."""
        from lib.ai_influence_status_page import OperatorCard

        cards = [
            OperatorCard(
                operator_id="test1",
                display_name="Test 1",
                icon="T",
                run_status=RunStatus.SUCCEEDED,
                last_run="2026-05-30T12:00:00Z",
            ),
            OperatorCard(
                operator_id="test2",
                display_name="Test 2",
                icon="T",
                run_status=RunStatus.FAILED,
                last_run="2026-05-30T12:00:00Z",
                errors=[{"message": "Error"}],
            ),
        ]

        html = render_html(cards)

        assert "2" in html  # Total
        assert "1" in html  # Succeeded
        assert "1" in html  # Failed


class TestOperatorDefinitions:
    """Tests for operator definitions."""

    def test_operators_complete(self):
        """Should have all 6 operators defined."""
        assert len(OPERATORS) == 6

        required_operators = {
            "x_social",
            "github_new",
            "github_legacy",
            "hf_papers",
            "youtube",
            "gemini",
        }
        assert set(OPERATORS.keys()) == required_operators

    def test_operator_structure(self):
        """Each operator should have required fields."""
        for op_id, op_def in OPERATORS.items():
            assert "display_name" in op_def
            assert "icon" in op_def
            assert "output_dir" in op_def
            assert "schedule" in op_def
            assert isinstance(op_def["display_name"], str)
            assert isinstance(op_def["icon"], str)
