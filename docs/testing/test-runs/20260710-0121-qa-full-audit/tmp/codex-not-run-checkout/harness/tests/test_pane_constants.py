"""Tests for pane_constants — 5 error code constants (per architecture.md §9.1)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pane_constants import (
    ALL_ERROR_CODES,
    CLEAR_FAILED_EXHAUSTED,
    PERMISSION_LOOP,
    PROCEED_PROMPT_STUCK,
    QUEUED_PROMPT_STUCK,
    RESPAWN_FAILED,
)


class TestErrorCodes:
    def test_proceed_prompt_stuck(self):
        assert PROCEED_PROMPT_STUCK == "PROCEED_PROMPT_STUCK"

    def test_queued_prompt_stuck(self):
        assert QUEUED_PROMPT_STUCK == "QUEUED_PROMPT_STUCK"

    def test_permission_loop(self):
        assert PERMISSION_LOOP == "PERMISSION_LOOP"

    def test_clear_failed_exhausted(self):
        assert CLEAR_FAILED_EXHAUSTED == "CLEAR_FAILED_EXHAUSTED"

    def test_respawn_failed(self):
        assert RESPAWN_FAILED == "RESPAWN_FAILED"

    def test_all_five_distinct(self):
        codes = [
            PROCEED_PROMPT_STUCK,
            QUEUED_PROMPT_STUCK,
            PERMISSION_LOOP,
            CLEAR_FAILED_EXHAUSTED,
            RESPAWN_FAILED,
        ]
        assert len(set(codes)) == 5

    def test_all_error_codes_set(self):
        assert ALL_ERROR_CODES == frozenset({
            PROCEED_PROMPT_STUCK,
            QUEUED_PROMPT_STUCK,
            PERMISSION_LOOP,
            CLEAR_FAILED_EXHAUSTED,
            RESPAWN_FAILED,
        })

    def test_all_error_codes_count(self):
        assert len(ALL_ERROR_CODES) == 5

    def test_frozenset_type(self):
        assert isinstance(ALL_ERROR_CODES, frozenset)
