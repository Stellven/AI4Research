"""Tests for DeepResearch claim extraction quality."""

from __future__ import annotations

import sys
from pathlib import Path

_HARNESS_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_HARNESS_LIB) not in sys.path:
    sys.path.insert(0, str(_HARNESS_LIB))

from research.cli import split_claim_sentences  # noqa: E402


def test_split_claim_sentences_ignores_source_metadata():
    text = """Title: Example Paper
URL: https://example.com/paper
Publisher: arXiv
Published: 2025-01-01
Source Type: paper

Summary:
- Proposes a recurrent latent block for test-time reasoning.
- Contrasts latent compute with long visible chain-of-thought traces.

Key Claims:
- Latent compute can reduce tokenized reasoning overhead for search-heavy tasks.
- Projection-based soft thoughts are easier to deploy with existing models.
"""

    claims = split_claim_sentences(text, limit=10)

    assert claims
    assert all(not claim.lower().startswith(("title:", "url:", "publisher:", "published:", "source type:")) for claim in claims)
    assert any("recurrent latent block" in claim for claim in claims)
    assert any("tokenized reasoning overhead" in claim for claim in claims)
