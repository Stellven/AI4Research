"""Tests for RecoverDetector — 3 regex patterns + 4 detect methods."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from recover_detector import (
    DET_PROCEED,
    DET_QUEUED,
    DET_PERMISSION,
    DetectResult,
    PromptType,
    RecoverDetector,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "tmux_capture_samples"


def _load_fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text()


# --- Regex unit tests ---

class TestRegexPatterns:
    def test_proceed_matches_do_you_want(self):
        assert DET_PROCEED.search("Do you want to proceed?")

    def test_proceed_matches_proceed_question(self):
        assert DET_PROCEED.search("please proceed?")

    def test_proceed_no_match_plain(self):
        assert not DET_PROCEED.search("normal output line")

    def test_queued_matches_press_up(self):
        assert DET_QUEUED.search("Press up to edit queued messages")

    def test_queued_matches_case_insensitive(self):
        assert DET_QUEUED.search("press UP to edit queued messages")

    def test_queued_no_match_plain(self):
        assert not DET_QUEUED.search("no queued content here")

    def test_permission_matches_allow(self):
        assert DET_PERMISSION.search("Do you want to allow this?")

    def test_permission_matches_deny(self):
        assert DET_PERMISSION.search("Allow or deny this command?")

    def test_permission_no_match_plain(self):
        assert not DET_PERMISSION.search("normal output without any special words")


# --- Fixture-based detection tests ---

class TestFixtureDetection:
    @pytest.fixture
    def proceed_output(self):
        return _load_fixture("proceed.txt")

    @pytest.fixture
    def queued_output(self):
        return _load_fixture("queued.txt")

    @pytest.fixture
    def permission_output(self):
        return _load_fixture("permission.txt")

    @pytest.fixture
    def clean_output(self):
        return _load_fixture("clean.txt")

    def test_detect_proceed_from_fixture(self, proceed_output):
        det = RecoverDetector(capture_fn=lambda _: proceed_output)
        result = det.detect_proceed_prompt("test:0.0")
        assert result.prompt_type == PromptType.PROCEED
        assert result.detected

    def test_detect_queued_from_fixture(self, queued_output):
        det = RecoverDetector(capture_fn=lambda _: queued_output)
        result = det.detect_queued_message("test:0.0")
        assert result.prompt_type == PromptType.QUEUED
        assert result.detected

    def test_detect_permission_from_fixture(self, permission_output):
        det = RecoverDetector(capture_fn=lambda _: permission_output)
        result = det.detect_permission_prompt("test:0.0")
        assert result.prompt_type == PromptType.PERMISSION
        assert result.detected

    def test_clean_no_detection(self, clean_output):
        det = RecoverDetector(capture_fn=lambda _: clean_output)
        result = det.classify_prompt("test:0.0")
        assert result.prompt_type == PromptType.NONE
        assert not result.detected


# --- classify_prompt priority tests ---

class TestClassifyPrompt:
    def test_classify_returns_proceed(self):
        text = "Do you want to proceed with this action?"
        det = RecoverDetector(capture_fn=lambda _: text)
        result = det.classify_prompt("test:0.0")
        assert result.prompt_type == PromptType.PROCEED

    def test_classify_returns_queued(self):
        text = "Press up to edit queued messages"
        det = RecoverDetector(capture_fn=lambda _: text)
        result = det.classify_prompt("test:0.0")
        assert result.prompt_type == PromptType.QUEUED

    def test_classify_returns_permission(self):
        text = "Allow this file read? Permission required."
        det = RecoverDetector(capture_fn=lambda _: text)
        result = det.classify_prompt("test:0.0")
        assert result.prompt_type == PromptType.PERMISSION

    def test_classify_returns_none_on_clean(self):
        text = "just normal output\nno detection patterns"
        det = RecoverDetector(capture_fn=lambda _: text)
        result = det.classify_prompt("test:0.0")
        assert result.prompt_type == PromptType.NONE


# --- DetectResult tests ---

class TestDetectResult:
    def test_detected_true_for_proceed(self):
        r = DetectResult(pane_id="p", prompt_type=PromptType.PROCEED)
        assert r.detected

    def test_detected_false_for_none(self):
        r = DetectResult(pane_id="p", prompt_type=PromptType.NONE)
        assert not r.detected

    def test_matched_line_populated(self):
        r = DetectResult(pane_id="p", prompt_type=PromptType.QUEUED,
                         matched_line="Press up to edit queued messages")
        assert r.matched_line is not None

    def test_default_matched_line_none(self):
        r = DetectResult(pane_id="p", prompt_type=PromptType.NONE)
        assert r.matched_line is None


# --- capture_fn injection test ---

class TestCaptureInjection:
    def test_custom_capture_fn_used(self):
        calls = []
        def custom_capture(pid):
            calls.append(pid)
            return ""
        det = RecoverDetector(capture_fn=custom_capture)
        det.classify_prompt("my-pane:0.5")
        assert calls == ["my-pane:0.5"]

    def test_default_lines_50(self):
        det = RecoverDetector()
        assert det._lines == 50

    def test_custom_lines(self):
        det = RecoverDetector(lines=100)
        assert det._lines == 100
