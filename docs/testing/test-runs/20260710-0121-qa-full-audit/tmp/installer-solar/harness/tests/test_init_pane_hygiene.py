"""Tests for init_pane_hygiene.py initialization script."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.init_pane_hygiene import init_registry
from pane_hygiene_registry import PaneHygieneRegistry, PaneState


class TestInitFromPaneIds:
    def test_init_five_panes(self, tmp_path):
        pane_ids = [
            "solar-harness:0.3",
            "solar-harness-lab:0.0",
            "solar-harness-lab:0.1",
            "solar-harness-lab:0.2",
            "solar-harness-lab:0.3",
        ]
        result = init_registry(str(tmp_path / "test.json"), pane_ids=pane_ids)
        assert result["count"] == 5
        assert len(result["registered"]) == 5

    def test_all_panes_clean_after_init(self, tmp_path):
        pane_ids = ["solar-harness:0.3", "solar-harness-lab:0.0"]
        path = str(tmp_path / "test.json")
        init_registry(path, pane_ids=pane_ids)
        reg = PaneHygieneRegistry(path)
        for pid in pane_ids:
            assert reg.get_pane_state(pid).state == PaneState.clean

    def test_roles_assigned(self, tmp_path):
        pane_ids = ["solar-harness:0.3", "solar-harness-lab:0.0"]
        path = str(tmp_path / "test.json")
        init_registry(path, pane_ids=pane_ids)
        reg = PaneHygieneRegistry(path)
        assert reg.get_pane_state("solar-harness:0.3").pane_role == "evaluator"
        assert reg.get_pane_state("solar-harness-lab:0.0").pane_role == "builder"

    def test_models_assigned(self, tmp_path):
        pane_ids = ["solar-harness:0.3", "solar-harness-lab:0.3"]
        path = str(tmp_path / "test.json")
        init_registry(path, pane_ids=pane_ids)
        reg = PaneHygieneRegistry(path)
        assert reg.get_pane_state("solar-harness:0.3").model == "anthropic-opus"
        assert reg.get_pane_state("solar-harness-lab:0.3").model == "anthropic-sonnet"


class TestInitWithMockTmux:
    def test_discover_from_mock_tmux(self, tmp_path):
        mock_output = ["solar-harness:0.3", "solar-harness-lab:0.0", "solar-harness-lab:0.1"]
        with patch("scripts.init_pane_hygiene.discover_panes", return_value=mock_output):
            path = str(tmp_path / "test.json")
            result = init_registry(path)
        assert result["count"] == 3

    def test_empty_tmux_returns_zero(self, tmp_path):
        with patch("scripts.init_pane_hygiene.discover_panes", return_value=[]):
            path = str(tmp_path / "test.json")
            result = init_registry(path)
        assert result["count"] == 0


class TestIdempotent:
    def test_reinit_skips_existing(self, tmp_path):
        pane_ids = ["solar-harness:0.3"]
        path = str(tmp_path / "test.json")
        result1 = init_registry(path, pane_ids=pane_ids)
        assert result1["count"] == 1
        result2 = init_registry(path, pane_ids=pane_ids)
        assert result2["count"] == 0
