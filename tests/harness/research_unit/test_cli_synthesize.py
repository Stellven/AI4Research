"""Tests for DeepResearch expert synthesis command internals."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

_HARNESS_LIB = (Path(__file__).resolve().parents[3] / 'harness') / "lib"
if str(_HARNESS_LIB) not in sys.path:
    sys.path.insert(0, str(_HARNESS_LIB))

from research import storage  # noqa: E402
from research import hashing  # noqa: E402
from research.cli import (  # noqa: E402
    continue_research_pipeline,
    extract_all_sources,
    insert_source,
    mine_claims_for_run,
    synthesize_expert_report,
)


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
    assert "## Evidence-Backed Findings" in text
    assert "## Source Coverage" in text
    assert "## Limitations and Open Questions" in text
    assert "## Synthesis Boundary" in text
    assert "[cite:ev_" in text


def test_synthesize_expert_report_never_injects_unrelated_topic_boilerplate(tmp_path):
    db_path = tmp_path / "research.db"
    conn = storage.init_db(str(db_path))
    run_id = "run-cardiac-rehabilitation"
    conn.execute(
        "INSERT INTO research_runs (id, topic, depth_tier, status, char_budget) VALUES (?, ?, 'standard', 'pending', 6000)",
        (run_id, "cardiac rehabilitation exercise guidance"),
    )
    insert_source(
        conn,
        run_id,
        title="Cardiac rehabilitation guidance",
        url="https://example.org/cardiac-rehabilitation",
        source_type="official_doc",
        text=(
            "Cardiac rehabilitation guidance recommends supervised exercise that is tailored to the patient, "
            "combined with risk-factor management and clinical follow-up. The guidance emphasizes that exercise "
            "intensity and progression depend on individual assessment rather than one universal prescription."
        ),
    )
    extract_all_sources(conn, run_id)
    claims, _ = mine_claims_for_run(conn, run_id)
    assert claims > 0

    output_md = tmp_path / "expert.md"
    path, _ = synthesize_expert_report(conn, run_id, str(output_md))
    conn.close()

    text = Path(path).read_text(encoding="utf-8")
    assert "cardiac rehabilitation" in text.lower()
    assert "## Evidence-Backed Findings" in text
    assert "## Source Coverage" in text
    assert "## Limitations and Open Questions" in text
    assert "latent-space reasoning" not in text.lower()
    assert "soft thought" not in text.lower()
    assert "recurrent depth" not in text.lower()


def test_synthesize_expert_report_excludes_claims_without_evidence(tmp_path):
    db_path = tmp_path / "research.db"
    conn = storage.init_db(str(db_path))
    run_id = "run-unsupported-claim"
    unsupported = "The unsupported claim must never appear in the rendered findings."
    conn.execute(
        "INSERT INTO research_runs (id, topic, depth_tier, status, char_budget) "
        "VALUES (?, ?, 'standard', 'pending', 6000)",
        (run_id, "unsupported claim regression"),
    )
    conn.execute(
        "INSERT INTO claims (id, run_id, claim_text, claim_type, stance, confidence, content_hash) "
        "VALUES (?, ?, ?, 'assertion', 'neutral', 0.4, ?)",
        ("claim-unsupported", run_id, unsupported, hashing.content_hash(unsupported)),
    )
    conn.commit()

    output_md = tmp_path / "expert.md"
    path, _ = synthesize_expert_report(conn, run_id, str(output_md))
    conn.close()

    text = Path(path).read_text(encoding="utf-8")
    assert unsupported not in text
    assert "No supported claims available" in text


def test_full_legacy_pipeline_compiles_topic_general_final_report(tmp_path):
    db_path = tmp_path / "research.db"
    conn = storage.init_db(str(db_path))
    run_id = "run-wetland-restoration"
    conn.execute(
        "INSERT INTO research_runs (id, topic, depth_tier, status, char_budget) VALUES (?, ?, 'standard', 'pending', 6000)",
        (run_id, "wetland restoration monitoring"),
    )
    insert_source(
        conn,
        run_id,
        title="Wetland restoration monitoring guidance",
        url="https://example.org/wetland-restoration",
        source_type="official_doc",
        text=(
            "Wetland restoration monitoring guidance recommends tracking hydrology, native vegetation, and "
            "habitat indicators over time. The guidance explains that restoration outcomes should be compared "
            "with baseline conditions and documented through repeated field measurements."
        ),
    )
    conn.close()

    result = continue_research_pipeline(str(db_path), run_id, str(tmp_path / "output"))
    final_text = Path(result["final_md"]).read_text(encoding="utf-8")

    assert "wetland restoration" in final_text.lower()
    assert "[cite:ev_" in final_text
    assert "latent-space reasoning" not in final_text.lower()
    assert "soft thought" not in final_text.lower()
    assert "recurrent depth" not in final_text.lower()
