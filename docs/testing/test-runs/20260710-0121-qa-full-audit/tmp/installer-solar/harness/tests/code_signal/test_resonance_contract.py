"""Test resonance contract — G0–G5 levels computable."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))

from github_intelligence.code_signal.resonance import (
    RESONANCE_LEVELS,
    compute_resonance_level,
    stamp_packet_resonance,
)


def test_all_levels_defined():
    assert RESONANCE_LEVELS == ("G0", "G1", "G2", "G3", "G4", "G5")


def test_g0_code_only():
    level = compute_resonance_level(has_code_signal=True)
    assert level == "G0"


def test_g0_no_signal():
    level = compute_resonance_level(has_code_signal=False)
    assert level == "G0"


def test_g1_code_social():
    level = compute_resonance_level(has_code_signal=True, has_social_mention=True)
    assert level == "G1"


def test_g2_code_paper():
    level = compute_resonance_level(has_code_signal=True, has_paper_ref=True)
    assert level == "G2"


def test_g3_tri_source():
    level = compute_resonance_level(
        has_code_signal=True, has_social_mention=True, has_paper_ref=True
    )
    assert level == "G3"


def test_g4_sustained():
    level = compute_resonance_level(
        has_code_signal=True, has_social_mention=True, has_paper_ref=True,
        sustained_days=10,
    )
    assert level == "G4"


def test_g5_intervention():
    level = compute_resonance_level(
        has_code_signal=True, has_social_mention=True, has_paper_ref=True,
        has_intervention=True,
    )
    assert level == "G5"


def test_stamp_packet_resonance_default():
    level = stamp_packet_resonance()
    assert level == "G0"


def test_stamp_packet_resonance_with_refs():
    cross = {"social_mentions": ["thesis-1"], "paper_ids": ["paper-1"]}
    level = stamp_packet_resonance(cross_source_refs=cross)
    assert level == "G3"
