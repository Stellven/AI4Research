"""
Tests for operator_schedule_binder — S04 N1.

Cases:
  1. Normal binding from a valid registry (5 lines → 4 cron + 1 manual).
  2. Missing registry file raises RegistryLoadError.
  3. Cron format validation (minute hour * * * pattern).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

# Ensure lib/ is on sys.path
_LIB = str(Path(__file__).resolve().parents[1] / "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from operator_registry_loader import RegistryLoadError
from operator_schedule_binder import bind_schedules, write_schedules

# --- fixtures ---

_VALID_REGISTRY: dict = {
    "schema_version": "solar.operator_registry.v1",
    "lines": {
        "x_social": {
            "primary": "scripts/ai_influence_daily.py",
            "executors": ["tools/playwright_twitter_scraper.py"],
            "fallback": [],
            "schedule": "daily",
            "output_dir": "reports/x-social/",
        },
        "github_trends": {
            "primary": "scripts/github_trends_digest.py",
            "executors": [],
            "fallback": [],
            "schedule": "daily",
            "output_dir": "reports/github/",
            "dual_run": {"enabled": True, "comparison_view": True},
        },
        "hf_papers": {
            "primary": "scripts/tech_hotspot_radar.py",
            "executors": [],
            "fallback": [],
            "schedule": "daily",
            "output_dir": "reports/hf-papers/",
        },
        "gemini_research": {
            "primary": "tools/gemini_deep_research_operator.py",
            "executors": [],
            "fallback": [],
            "schedule": "on_demand",
            "output_dir": "reports/gemini/",
        },
        "youtube": {
            "primary": "scripts/youtube_influence_digest.py",
            "executors": [],
            "fallback": [],
            "schedule": "daily",
            "output_dir": "reports/youtube/",
        },
    },
}

_CRON_PATTERN = re.compile(r"^\d{1,2} \d{1,2} \* \* \*$")


# --- test cases ---


class TestBindSchedulesNormal:
    """Case 1: valid registry produces correct bindings."""

    def test_produces_five_bindings(self):
        result = bind_schedules(registry=_VALID_REGISTRY)
        assert "bindings" in result
        assert len(result["bindings"]) == 5

    def test_four_cron_one_manual(self):
        result = bind_schedules(registry=_VALID_REGISTRY)
        bindings = result["bindings"]
        cron_count = sum(1 for b in bindings.values() if b["type"] == "cron")
        manual_count = sum(1 for b in bindings.values() if b["type"] == "manual")
        assert cron_count == 4, f"Expected 4 cron bindings, got {cron_count}"
        assert manual_count == 1, f"Expected 1 manual binding, got {manual_count}"

    def test_gemini_is_manual(self):
        result = bind_schedules(registry=_VALID_REGISTRY)
        gemini = result["bindings"]["gemini_research"]
        assert gemini["type"] == "manual"
        assert gemini["cron"] is None
        assert gemini["source_schedule"] == "on_demand"

    def test_cron_format_valid(self):
        result = bind_schedules(registry=_VALID_REGISTRY)
        for name, b in result["bindings"].items():
            if b["type"] == "cron":
                assert b["cron"] is not None, f"{name}: cron should not be None"
                assert _CRON_PATTERN.match(b["cron"]), (
                    f"{name}: invalid cron format: {b['cron']!r}"
                )

    def test_daily_lines_staggered(self):
        result = bind_schedules(registry=_VALID_REGISTRY)
        cron_times = []
        for b in result["bindings"].values():
            if b["type"] == "cron":
                parts = b["cron"].split()
                total_minutes = int(parts[1]) * 60 + int(parts[0])
                cron_times.append(total_minutes)
        # All daily cron times should be distinct
        assert len(cron_times) == len(set(cron_times)), "Daily cron times must be unique"

    def test_dual_run_carried_over(self):
        result = bind_schedules(registry=_VALID_REGISTRY)
        gh = result["bindings"]["github_trends"]
        assert "dual_run" in gh
        assert gh["dual_run"]["enabled"] is True

    def test_schema_version_present(self):
        result = bind_schedules(registry=_VALID_REGISTRY)
        assert result["schema_version"] == "solar.operator_schedules.v1"

    def test_generated_at_present(self):
        result = bind_schedules(registry=_VALID_REGISTRY)
        assert "generated_at" in result
        assert len(result["generated_at"]) > 0


class TestBindSchedulesMissingRegistry:
    """Case 2: missing registry file raises RegistryLoadError."""

    def test_missing_registry_raises(self, tmp_path):
        nonexistent = tmp_path / "does_not_exist.json"
        with pytest.raises(RegistryLoadError, match="not found"):
            bind_schedules(registry_path=nonexistent)

    def test_invalid_json_raises(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(RegistryLoadError, match="Invalid JSON"):
            bind_schedules(registry_path=bad_file)


class TestWriteSchedules:
    """Case 3: write_schedules produces a valid JSON file."""

    def test_writes_valid_json(self, tmp_path):
        out = tmp_path / "operator_schedules.json"
        result_path = write_schedules(
            output_path=out,
            registry=_VALID_REGISTRY,
        )
        assert result_path.is_file()
        data = json.loads(result_path.read_text(encoding="utf-8"))
        assert len(data["bindings"]) == 5
        assert data["schema_version"] == "solar.operator_schedules.v1"
