#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import solar_skills  # noqa: E402


def test_extract_selected_skills_from_dispatch_section() -> None:
    text = """
# Dispatch

## Selected Skills

- `skill.nano-pdf`
- `skill.content-research-writer`

## Required Closeout
"""
    assert solar_skills._extract_selected_skills_from_dispatch(text) == [
        "skill.nano-pdf",
        "skill.content-research-writer",
    ]


def test_build_skills_block_lists_selected_skills() -> None:
    block = solar_skills._build_skills_block(
        ["solar-harness-runtime"],
        42,
        selected_skills=["skill.nano-pdf", "skill.content-research-writer"],
    )
    assert "Selected installed skills for this dispatch:" in block
    assert "skill.nano-pdf" in block
    assert "skill.content-research-writer" in block
