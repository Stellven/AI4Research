"""Tests for priority_queue module."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.youtube.priority_queue import compute_priority_score


def test_p0_threshold():
    result = compute_priority_score("vid", 1.0, 1.0, 1.0, 1.0, 1.0, 1.0)
    assert result.score == 1.0
    assert result.priority == "P0"


def test_p1_threshold():
    result = compute_priority_score("vid", 0.6, 0.6, 0.6, 0.6, 0.6, 0.6)
    assert result.priority == "P1"
    assert result.score >= 0.60


def test_p2_threshold():
    result = compute_priority_score("vid", 0.4, 0.4, 0.4, 0.4, 0.4, 0.4)
    assert result.priority == "P2"


def test_p3_low_score():
    result = compute_priority_score("vid", 0.1, 0.1, 0.1, 0.1, 0.1, 0.1)
    assert result.priority == "P3"


def test_six_factor_formula():
    result = compute_priority_score(
        "vid",
        channel_weight=0.8,
        recency=0.6,
        report_candidate=0.7,
        cross_source=0.5,
        view_velocity=0.4,
        duration_value=0.3,
    )
    expected = (0.25*0.8 + 0.20*0.6 + 0.20*0.7 + 0.15*0.5 + 0.10*0.4 + 0.10*0.3)
    assert abs(result.score - round(expected, 4)) < 0.0001


def test_weights_sum_to_one():
    from lib.youtube.priority_queue import _WEIGHTS
    assert abs(sum(_WEIGHTS.values()) - 1.0) < 0.0001


def test_components_stored():
    result = compute_priority_score("vid", 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
    assert result.components["channel_weight"] == 0.5
    assert result.components["duration_value"] == 1.0


def test_exact_p0_boundary():
    result = compute_priority_score("vid", 0.8, 0.8, 0.8, 0.8, 0.8, 0.8)
    assert result.score >= 0.80
    assert result.priority == "P0"


def test_just_below_p0():
    result = compute_priority_score("vid", 0.79, 0.79, 0.79, 0.79, 0.79, 0.79)
    assert result.priority == "P1"
