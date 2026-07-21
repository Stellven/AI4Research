"""Tests for DeepResearch expert synthesis command internals."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

_HARNESS_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_HARNESS_LIB) not in sys.path:
    sys.path.insert(0, str(_HARNESS_LIB))

from research import storage  # noqa: E402
from research.cli import insert_source, extract_all_sources, mine_claims_for_run, synthesize_expert_report  # noqa: E402


def test_synthesize_expert_report_outputs_required_sections(tmp_path):
    db_path = tmp_path / "research.db"
    conn = storage.init_db(str(db_path))
    run_id = "run-synth"
    conn.execute(
        "INSERT INTO research_runs (id, topic, depth_tier, status, char_budget) VALUES (?, ?, 'deep', 'pending', 8000)",
        (run_id, "latent reasoning"),
    )
    insert_source(
        conn,
        run_id,
        title="Latent reasoning source",
        url="https://example.com/latent",
        source_type="paper",
        text="""Summary:
- Introduces Coconut, where the last hidden state is fed back as continuous thought.
- Proposes recurrent depth for test-time compute by iterating blocks.

Key Claims:
- Soft thought projection is easier to deploy with existing models.
- Latent reasoning needs diversity and superposition for multiple paths.
- Evaluation must disentangle surface chain-of-thought from latent mediation.
""",
    )
    extract_all_sources(conn, run_id)
    claims, _ = mine_claims_for_run(conn, run_id)
    assert claims > 0

    output_md = tmp_path / "expert.md"
    path, chars = synthesize_expert_report(conn, run_id, str(output_md))
    conn.close()

    text = Path(path).read_text(encoding="utf-8")
    assert chars == len(text)
    assert "## Architecture Taxonomy" in text
    assert "## Insight Scorecard" in text
    assert "## Source Strength" in text
    assert "## Design Tradeoffs" in text
    assert "## Contradictions and Uncertainty" in text
    assert "**P0:**" in text and "**P1:**" in text and "**P2:**" in text
    assert "[cite:ev_" in text
