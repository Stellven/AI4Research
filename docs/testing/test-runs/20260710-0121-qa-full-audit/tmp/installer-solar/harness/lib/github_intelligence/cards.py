"""GitHub Project Intelligence — analysis cards and planning briefs.

Node: C4_cards_briefs_reports_pipeline
Write-scope: harness/lib/github_intelligence/cards.py

Constraints (S02 §A4):
- A card cannot be created without ≥3 evidence_ids (validated by schema).
- A card is only marked verified=1 after explicit verifier PASS.
- A planning brief cannot be created without a verified analysis card.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

from github_intelligence.schema import (
    AnalysisCard,
    PlanningBrief,
    apply_schema,
    insert_row,
    fetch_rows,
    utc_now_iso,
)


# ---------------------------------------------------------------------------
# Card helpers
# ---------------------------------------------------------------------------


def make_analysis_id(full_name: str, date: str) -> str:
    h = hashlib.md5(full_name.encode()).hexdigest()[:6]
    return f"ac-{h}-{date}"


def create_analysis_card(
    full_name: str,
    analysis_date: str,
    evidence_ids: list[str],
    *,
    project_positioning: str | None = None,
    what_it_does: str | None = None,
    target_users: list[str] | None = None,
    core_technical_idea: str | None = None,
    why_it_is_hot: str | None = None,
    potential_score: float | None = None,
    heat_score: float | None = None,
    technical_depth_score: float | None = None,
    community_health_score: float | None = None,
    strategic_relevance_score: float | None = None,
    trend_implication: str | None = None,
    product_planning_ideas: list[str] | None = None,
    research_questions: list[str] | None = None,
    risks: list[dict[str, Any]] | None = None,
    watch_next: list[str] | None = None,
    model_used: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> AnalysisCard:
    """Create and optionally persist an AnalysisCard.

    Raises ValueError if evidence_ids < MIN_EVIDENCE_REFS (3).
    """
    card = AnalysisCard(
        analysis_id=make_analysis_id(full_name, analysis_date),
        full_name=full_name,
        analysis_date=analysis_date,
        project_positioning=project_positioning,
        what_it_does=what_it_does,
        target_users=target_users or [],
        core_technical_idea=core_technical_idea,
        why_it_is_hot=why_it_is_hot,
        potential_score=potential_score,
        heat_score=heat_score,
        technical_depth_score=technical_depth_score,
        community_health_score=community_health_score,
        strategic_relevance_score=strategic_relevance_score,
        trend_implication=trend_implication,
        product_planning_ideas=product_planning_ideas or [],
        research_questions=research_questions or [],
        risks=risks or [],
        watch_next=watch_next or [],
        evidence_ids=evidence_ids,
        model_used=model_used,
        verified=0,
    )
    card.validate_evidence_floor()  # raises if < 3 evidence_ids
    if conn is not None:
        insert_row(conn, card.TABLE, card.to_row())
        conn.commit()
    return card


def verify_card(analysis_id: str, conn: sqlite3.Connection) -> bool:
    """Mark a card verified=1. Returns True if the row existed and was updated."""
    cur = conn.execute(
        "UPDATE repo_analysis_cards SET verified=1 WHERE analysis_id=?",
        (analysis_id,),
    )
    conn.commit()
    return cur.rowcount > 0


def get_verified_cards(conn: sqlite3.Connection, date: str | None = None) -> list[AnalysisCard]:
    """Return all verified cards, optionally filtered by analysis_date."""
    where = "verified=1"
    params: list[Any] = []
    if date:
        where += " AND analysis_date=?"
        params.append(date)
    rows = fetch_rows(conn, AnalysisCard.TABLE, where, params)
    return [AnalysisCard.from_row(r) for r in rows]


# ---------------------------------------------------------------------------
# Brief helpers
# ---------------------------------------------------------------------------


def make_brief_id(full_name: str, date: str) -> str:
    h = hashlib.md5(full_name.encode()).hexdigest()[:6]
    return f"pb-{h}-{date}"


def create_planning_brief(
    card: AnalysisCard,
    *,
    opportunity_summary: str | None = None,
    user_pain_points: list[str] | None = None,
    target_personas: list[str] | None = None,
    proposed_product: str | None = None,
    mvp_scope: str | None = None,
    technical_architecture: str | None = None,
    go_to_market: str | None = None,
    risks: list[dict[str, Any]] | None = None,
    validation_metrics: list[str] | None = None,
    next_steps: list[str] | None = None,
    conn: sqlite3.Connection | None = None,
) -> PlanningBrief:
    """Create a PlanningBrief that requires a verified AnalysisCard.

    Raises ValueError if the card is not verified.
    """
    if not card.verified:
        raise ValueError(
            f"PlanningBrief requires a verified AnalysisCard; "
            f"card {card.analysis_id} has verified={card.verified}"
        )
    brief = PlanningBrief(
        brief_id=make_brief_id(card.full_name, card.analysis_date),
        full_name=card.full_name,
        analysis_id=card.analysis_id,
        opportunity_summary=opportunity_summary,
        user_pain_points=user_pain_points or [],
        target_personas=target_personas or [],
        proposed_product=proposed_product,
        mvp_scope=mvp_scope,
        technical_architecture=technical_architecture,
        go_to_market=go_to_market,
        risks=risks or [],
        validation_metrics=validation_metrics or [],
        next_steps=next_steps or [],
    )
    if conn is not None:
        insert_row(conn, brief.TABLE, brief.to_row())
        conn.commit()
    return brief


def get_briefs_for_card(analysis_id: str, conn: sqlite3.Connection) -> list[PlanningBrief]:
    rows = fetch_rows(conn, PlanningBrief.TABLE, "analysis_id=?", (analysis_id,))
    return [PlanningBrief.from_row(r) for r in rows]


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def _self_test() -> dict[str, Any]:
    import tempfile

    metrics: dict[str, Any] = {"tests_run": 0, "tests_passed": 0, "tests": []}

    def _ok(name: str) -> None:
        metrics["tests_run"] += 1
        metrics["tests_passed"] += 1
        metrics["tests"].append(name)

    def _fail(name: str, reason: str) -> None:
        metrics["tests_run"] += 1
        metrics["tests"].append(f"FAIL:{name}:{reason}")

    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
        db_path = tf.name
    try:
        conn = sqlite3.connect(db_path)
        apply_schema(conn)

        # 1. create card with ≥3 evidence_ids succeeds
        card = create_analysis_card(
            full_name="owner/repo",
            analysis_date="2026-05-27",
            evidence_ids=["ev1", "ev2", "ev3"],
            heat_score=75.0,
            potential_score=80.0,
            technical_depth_score=60.0,
            community_health_score=70.0,
            model_used="qwen3.6-local",
            conn=conn,
        )
        assert card.verified == 0
        _ok("create_card.unverified_by_default")

        # 2. evidence floor: < 3 evidence_ids raises
        try:
            create_analysis_card(
                full_name="owner/repo",
                analysis_date="2026-05-27",
                evidence_ids=["ev1", "ev2"],
            )
            _fail("create_card.evidence_floor", "should have raised ValueError")
        except ValueError:
            _ok("create_card.evidence_floor_raises")

        # 3. verify_card
        updated = verify_card(card.analysis_id, conn)
        assert updated is True
        _ok("verify_card.updates_row")

        # 4. verify_card on non-existent id returns False
        assert verify_card("ac-fake-id", conn) is False
        _ok("verify_card.missing_returns_false")

        # 5. get_verified_cards returns only verified
        card2 = create_analysis_card(
            full_name="owner/repo2",
            analysis_date="2026-05-27",
            evidence_ids=["ev4", "ev5", "ev6"],
            conn=conn,
        )
        verified_list = get_verified_cards(conn, "2026-05-27")
        assert len(verified_list) == 1
        assert verified_list[0].analysis_id == card.analysis_id
        _ok("get_verified_cards.filters_unverified")

        # 6. create_planning_brief on unverified card raises
        try:
            create_planning_brief(card2, opportunity_summary="test")
            _fail("create_brief.unverified_card", "should have raised ValueError")
        except ValueError:
            _ok("create_brief.requires_verified_card")

        # 7. create_planning_brief on verified card succeeds
        card.verified = 1  # in-memory flag (row is already updated in DB)
        brief = create_planning_brief(
            card,
            opportunity_summary="Great opportunity",
            user_pain_points=["pain1", "pain2"],
            validation_metrics=["10k stars in 30d"],
            conn=conn,
        )
        assert brief.analysis_id == card.analysis_id
        assert brief.brief_id.startswith("pb-")
        _ok("create_brief.created_for_verified_card")

        # 8. get_briefs_for_card
        briefs = get_briefs_for_card(card.analysis_id, conn)
        assert len(briefs) == 1
        assert briefs[0].brief_id == brief.brief_id
        _ok("get_briefs_for_card.returns_correct")

        # 9. brief row-trip round-trip through DB
        rows = fetch_rows(conn, PlanningBrief.TABLE, "brief_id=?", (brief.brief_id,))
        assert len(rows) == 1
        restored = PlanningBrief.from_row(rows[0])
        assert restored.user_pain_points == ["pain1", "pain2"]
        _ok("brief.db_roundtrip")

        # 10. make_analysis_id deterministic
        id1 = make_analysis_id("org/proj", "2026-05-27")
        id2 = make_analysis_id("org/proj", "2026-05-27")
        assert id1 == id2
        _ok("make_analysis_id.deterministic")

        conn.close()
    finally:
        _os.unlink(db_path)

    return metrics


if __name__ == "__main__":
    m = _self_test()
    print(json.dumps(m, indent=2))
    if m["tests_run"] != m["tests_passed"]:
        _sys.exit(1)
