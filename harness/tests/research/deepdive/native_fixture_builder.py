"""Deterministic builder for a REAL DeepResearch native-export set.

Lane 4 test support. Rather than hand-guess the native jsonl shapes, this seeds a
throwaway SQLite via the engine's own ``research.storage`` layer and runs the
engine's own ``research.cli.export_run_to_dir`` — so the fixtures are byte-for-byte
what the live engine emits (``sources.jsonl``, ``evidence.jsonl``, ``claims.jsonl``,
``claim_evidence.jsonl``, ``sections.jsonl``, ``section_checks.jsonl``, plus
``report_ast.json``/``final.bibliography.json``/``<run>-research_eval.json``).

Everything is deterministic: explicit ids, explicit content, sha256 content hashes,
and the exported columns carry no timestamps (verified against the export SELECTs),
so regenerating produces identical jsonl. The committed fixture
(``fixtures/native_export_rsi/``) is exactly this generator's output;
``test_native_fixture_is_real_engine_export`` re-runs the generator and asserts
byte-equality, so the fixture can never silently drift from the real export path.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HARNESS_LIB = Path(__file__).resolve().parents[3] / "lib"
if str(_HARNESS_LIB) not in sys.path:
    sys.path.insert(0, str(_HARNESS_LIB))

from research import cli, storage  # noqa: E402
from research.hashing import content_hash  # noqa: E402

RUN_ID = "rsi-demo-run"
TOPIC = "Recursive Self-Improving Models"

# 6 RSI-themed sources. source_type spans the engine's validated set
# ({paper, code, official_doc, benchmark}) so the diversity gate is satisfied.
_SOURCES = [
    ("src_good1965", "https://example.org/good1965", "Speculations Concerning the First Ultraintelligent Machine", "paper"),
    ("src_star2022", "https://arxiv.org/abs/2203.14465", "STaR: Bootstrapping Reasoning With Reasoning", "paper"),
    ("src_reflexion2023", "https://arxiv.org/abs/2303.11366", "Reflexion: Language Agents with Verbal Reinforcement Learning", "paper"),
    ("src_selfrefine2023", "https://github.com/example/self-refine", "Self-Refine: Iterative Refinement with Self-Feedback", "code"),
    ("src_verify2023", "https://arxiv.org/abs/2305.20050", "Let's Verify Step by Step", "benchmark"),
    ("src_aiscientist2024", "https://platform.example.org/docs/ai-scientist", "The AI Scientist: Fully Automated Open-Ended Discovery", "official_doc"),
]

# 8 evidence atoms, each bound to a source. (evidence_type in the DB CHECK set.)
_EVIDENCE = [
    ("ev_1", "src_good1965", "An ultraintelligent machine could design ever-better machines, yielding an intelligence explosion.", "quoted"),
    ("ev_2", "src_star2022", "STaR bootstraps a model's own generated rationales to improve reasoning without new labels.", "factual"),
    ("ev_3", "src_reflexion2023", "Reflexion converts environment feedback into verbal self-reflection stored in an episodic memory.", "factual"),
    ("ev_4", "src_selfrefine2023", "Self-Refine improves outputs by iterating generate/self-critique/refine with the same model.", "factual"),
    ("ev_5", "src_verify2023", "Process supervision that verifies each reasoning step outperforms outcome-only reward on hard math.", "statistical"),
    ("ev_6", "src_aiscientist2024", "An automated pipeline generates ideas, runs experiments, and writes papers with a reviewer in the loop.", "factual"),
    ("ev_7", "src_verify2023", "Verifier-driven selection raises solution accuracy relative to unverified self-improvement.", "statistical"),
    ("ev_8", "src_reflexion2023", "Self-reflection gains are bounded by the fidelity of the feedback signal available to the agent.", "derived"),
]

# 12 claims (>= the validator's MIN_CLAIMS of 10). claim_type/stance in the DB CHECK sets.
_CLAIMS = [
    ("cl_01", "Recursive self-improvement is the mechanism behind Good's hypothesized intelligence explosion.", "causal", "neutral"),
    ("cl_02", "Models can bootstrap reasoning from their own generated rationales without new human labels.", "assertion", "supports"),
    ("cl_03", "Verbal self-reflection stored in memory improves an agent's subsequent attempts.", "causal", "supports"),
    ("cl_04", "Iterative self-critique and refinement improves output quality with a single model.", "assertion", "supports"),
    ("cl_05", "Step-level process supervision outperforms outcome-only reward on hard reasoning tasks.", "comparative", "supports"),
    ("cl_06", "A verifier in the loop is more reliable than unverified self-improvement.", "comparative", "supports"),
    ("cl_07", "Automated research pipelines can propose, run, and write up experiments end to end.", "assertion", "neutral"),
    ("cl_08", "The gains from self-reflection are bounded by the fidelity of the feedback signal.", "causal", "refutes"),
    ("cl_09", "Self-improving loops still depend on an external grounding or verification signal.", "assertion", "neutral"),
    ("cl_10", "Bootstrapped rationale training is a practical form of recursive self-improvement today.", "assertion", "supports"),
    ("cl_11", "Verifier-driven selection is a safer default than open-ended self-modification.", "comparative", "neutral"),
    ("cl_12", "Fully automated discovery raises evaluation and oversight challenges as capability grows.", "predictive", "neutral"),
]

# claim -> evidence link (round-robin across the 8 evidence atoms so >=5 sources
# are represented and every claim resolves to a valid source via evidence.source_id).
_CLAIM_EVIDENCE = [
    (f"ce_{i:02d}", claim_id, _EVIDENCE[i % len(_EVIDENCE)][0], "supports", 0.8)
    for i, (claim_id, *_rest) in enumerate(_CLAIMS)
]

# 4 report sections. Each body is >= 220 chars, cites >= 1 evidence id [cite:ev_N],
# and carries analysis vocabulary — so the engine's own eval-artifacts section-
# coverage + citation-grounding gates pass. Grounding is per-line token overlap
# (TOKEN_RE keeps hyphenated words whole), so each citing sentence reuses a
# distinctive plain token from the evidence it cites.
_SECTIONS = [
    ("sec_intro", "introduction", "Introduction",
     "# Introduction\n\nRecursive self-improvement (RSI) describes systems whose design lets them "
     "improve their own ability to improve. The classic framing predicts that ultraintelligent "
     "machines could design ever-better machines [cite:ev_1]. Modern runtime work instantiates "
     "weaker but real loops by training on self-generated rationales and reasoning traces "
     "[cite:ev_2]. This report evaluates the mechanisms, their limits, and the engineering "
     "implications for deploying such systems.\n", 0),
    ("sec_evidence", "evidence_synthesis", "Evidence Synthesis",
     "# Evidence Synthesis\n\nSeveral mechanisms recur across the evidence. Verbal self-reflection "
     "stored in memory improves later attempts [cite:ev_3]; iterative refinement lets a model "
     "refine its own outputs [cite:ev_4]; step-level process supervision beats outcome-only reward "
     "on hard reasoning [cite:ev_5]; and verifier-driven selection raises accuracy over unverified "
     "self-improvement [cite:ev_7]. The pattern is a generate-critique-refine loop bound to an "
     "external evaluation signal.\n", 1),
    ("sec_tensions", "contradictions", "Contradictions and Limits",
     "# Contradictions and Limits\n\nThe loops are not unbounded. Self-reflection gains are capped "
     "by the fidelity of the available feedback signal [cite:ev_8], so a weak signal limits how far "
     "improvement can go. Automated discovery still depends on a reviewer running experiments in the "
     "loop [cite:ev_6]. These tensions are the main risk and the boundary conditions for deploying "
     "recursive self-improvement safely.\n", 2),
    ("sec_conclusion", "conclusion", "Conclusion",
     "# Conclusion\n\nToday's recursive self-improvement is real but grounded. The practical, safer "
     "forms train on self-generated rationales [cite:ev_2] and put a verifier-driven selection step "
     "in the loop [cite:ev_7]. The engineering implication is a design that pairs self-improvement "
     "with an explicit evaluation gate and clear failure boundaries rather than open-ended "
     "self-modification.\n", 3),
]

_FINAL_MD = (
    "# Recursive Self-Improving Models\n\n"
    "## Introduction\n\n"
    "Recursive self-improvement (RSI) describes systems whose design lets them improve their own "
    "ability to improve; the classic framing predicts ultraintelligent machines that design "
    "ever-better machines [cite:ev_1], while modern work trains on self-generated rationales and "
    "reasoning traces [cite:ev_2].\n\n"
    "## Evidence Synthesis\n\n"
    "Verbal self-reflection improves later attempts [cite:ev_3]; iterative refinement lets a model "
    "refine its own outputs [cite:ev_4]; step-level process supervision beats outcome-only reward "
    "[cite:ev_5]; and verifier-driven selection raises accuracy over unverified self-improvement "
    "[cite:ev_7].\n\n"
    "## Contradictions and Limits\n\n"
    "Self-reflection gains are capped by the fidelity of the feedback signal [cite:ev_8], and "
    "automated discovery still depends on a reviewer running experiments in the loop [cite:ev_6].\n\n"
    "## Engineering Implications\n\n"
    "The engineering implication is a design that pairs self-generated rationales [cite:ev_2] with a "
    "verifier-driven selection gate [cite:ev_7], adding explicit evaluation and failure boundaries "
    "rather than open-ended self-modification.\n"
)


def _seed(db_path: str, *, defect: str | None = None) -> None:
    conn = storage.init_db(db_path)
    conn.execute(
        "INSERT INTO research_runs (id, topic, depth_tier, status, char_budget, char_used) "
        "VALUES (?, ?, 'deep', 'completed', 40000, 4000)",
        (RUN_ID, TOPIC),
    )
    for sid, url, title, stype in _SOURCES:
        conn.execute(
            "INSERT INTO research_sources (id, run_id, url, title, source_type, content_hash, content_span, relevance_score) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (sid, RUN_ID, url, title, stype, content_hash(title + url), "0:0", 0.9),
        )
    for eid, source_id, content, etype in _EVIDENCE:
        conn.execute(
            "INSERT INTO evidence_items (id, run_id, source_id, content, evidence_type, confidence, span_start, span_end, content_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)",
            (eid, RUN_ID, source_id, content, etype, 0.85, len(content), content_hash(content)),
        )
    for cid, text, ctype, stance in _CLAIMS:
        conn.execute(
            "INSERT INTO claims (id, run_id, claim_text, claim_type, stance, confidence, section_ref, content_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (cid, RUN_ID, text, ctype, stance, 0.8, None, content_hash(text)),
        )
    for link_id, claim_id, evidence_id, relation, strength in _CLAIM_EVIDENCE:
        conn.execute(
            "INSERT INTO claim_evidence (id, run_id, claim_id, evidence_id, relation, strength) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (link_id, RUN_ID, claim_id, evidence_id, relation, strength),
        )
    for sec_id, stype, title, content, order in _SECTIONS:
        if defect == "thin_section" and sec_id == "sec_conclusion":
            content = "# Conclusion\n\nGrounded RSI is real [cite:ev_7].\n"  # < 220 chars
        conn.execute(
            "INSERT INTO report_sections (id, run_id, section_type, title, content, char_count, section_order) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sec_id, RUN_ID, stype, title, content, len(content), order),
        )
        for check_type in ("factual_accuracy", "source_coverage"):
            conn.execute(
                "INSERT INTO section_checks (id, run_id, section_id, check_type, score, details, passed) "
                "VALUES (?, ?, ?, ?, ?, ?, 1)",
                (f"chk_{sec_id}_{check_type}", RUN_ID, sec_id, check_type, 0.95, "seeded pass"),
            )
    conn.commit()
    conn.close()


def build_native_export(dest_dir: str | Path, *, defect: str | None = None) -> Path:
    """Seed a throwaway DB and run the engine's real export into ``dest_dir``.

    Writes ``final.md`` plus the six native jsonl files and the engine's derived
    ``report_ast.json`` / ``final.bibliography.json`` / ``<run>-research_eval.json``.
    Returns the export directory path.

    ``defect`` seeds a genuine content flaw so the REAL ``research eval-artifacts``
    gate fails (used for the eval-artifacts *bad* fixture):

    - ``"thin_section"``  — the conclusion body is under the 220-char coverage floor.
    - ``"dangling_citation"`` — final.md cites ``ev_999``, an evidence id that does
      not exist, so the citation-grounding check reports missing cited evidence.
    """
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    db_path = str(dest / "_seed.sqlite")
    _seed(db_path, defect=defect)
    final_md = dest / "final.md"
    final_text = _FINAL_MD
    if defect == "dangling_citation":
        final_text = final_text.replace("[cite:ev_1]", "[cite:ev_1] [cite:ev_999]", 1)
    final_md.write_text(final_text, encoding="utf-8")
    cli.export_run_to_dir(db_path, RUN_ID, str(dest), final_md=str(final_md))
    # The seed DB is an implementation detail, not part of the export surface.
    for artifact in (dest / "_seed.sqlite", dest / "_seed.sqlite-wal", dest / "_seed.sqlite-shm"):
        if artifact.exists():
            artifact.unlink()
    return dest


# The six native jsonl files the adapter consumes, plus final.md — the committed
# fixture surface (research_eval.json/report_ast.json embed an absolute output_dir
# and are regenerated per-run, so they are not part of the committed fixture).
COMMITTED_EXPORT_FILES = (
    "sources.jsonl",
    "evidence.jsonl",
    "claims.jsonl",
    "claim_evidence.jsonl",
    "sections.jsonl",
    "section_checks.jsonl",
    "final.md",
)


if __name__ == "__main__":  # regenerate the committed fixture in place
    import shutil

    target = Path(__file__).resolve().parent / "fixtures" / "native_export_rsi"
    tmp = Path(__file__).resolve().parent / "fixtures" / "_native_tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    build_native_export(tmp)
    target.mkdir(parents=True, exist_ok=True)
    for name in COMMITTED_EXPORT_FILES:
        shutil.copyfile(tmp / name, target / name)
    shutil.rmtree(tmp)
    print(f"regenerated committed fixture at {target}")
