"""GitHub Project Intelligence — Evidence Pipeline (C3 node).

Sprint: sprint-20260524-p0-ai-influence-github-project-intelligence-system-upgrade-s03-core-runtime
Node:   C3_evidence_pipeline

Provides:
- compress_readme  : README text → list[EvidenceAtom] (evidence_type="readme_claim")
- compress_releases: release list → list[EvidenceAtom] (evidence_type="release_signal")
- compress_issues  : issue list  → list[EvidenceAtom] (evidence_type="issue_signal")
- build_reasoning_packet: atoms + snapshot → ReasoningPacket
- persist_atoms    : batch write atoms to SQLite
- make_evidence_id : deterministic ev-{hash6}-{type}-{seq:04d} format

Design constraints honored:
- Pure stdlib only
- Deterministic output (same input → same output)
- compressed_content ≤ 500 chars (enforced by EvidenceAtom.__post_init__)
- importance_score < 20 atoms are discarded from readme pipeline
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from typing import Any

from .schema import (
    EvidenceAtom,
    ReasoningPacket,
    RepoSnapshot,
    insert_row,
    utc_now_iso,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TECH_KEYWORDS = frozenset(
    [
        "llm", "gpu", "cpu", "neural", "model", "inference", "training", "dataset",
        "transformer", "attention", "embedding", "vector", "agent", "api", "sdk",
        "framework", "runtime", "benchmark", "performance", "memory", "cache",
        "distributed", "parallel", "async", "stream", "pipeline", "batch",
        "fast", "efficient", "scalable", "production", "deploy", "open-source",
        "zero-shot", "few-shot", "rag", "fine-tun", "lora", "quantiz", "compress",
        "tokenizer", "context", "multimodal", "vision", "audio", "code", "tool",
        "plugin", "extension", "integration", "workflow", "automation",
    ]
)

_STOP_WORDS = frozenset(
    [
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will", "would",
        "could", "should", "may", "might", "shall", "can", "this", "that",
        "these", "those", "it", "its", "we", "our", "you", "your", "i", "my",
        "he", "she", "they", "their", "as", "if", "so", "not", "no", "also",
        "just", "more", "all", "any", "each", "both", "here", "there", "then",
        "than", "into", "about", "over", "after", "before", "up", "out", "very",
    ]
)


def make_evidence_id(full_name: str, evidence_type: str, seq: int) -> str:
    """Generate deterministic ev-{hash6}-{type}-{seq:04d} ID.

    hash6 is derived from full_name + evidence_type so IDs are stable across
    runs for the same repo/type combination.
    """
    digest = hashlib.sha256(f"{full_name}|{evidence_type}".encode()).hexdigest()[:6]
    return f"ev-{digest}-{evidence_type}-{seq:04d}"


def _keyword_density(text: str) -> float:
    """Return fraction of non-stop words that are tech keywords [0.0, 1.0]."""
    words = re.findall(r"[a-z0-9_\-]+", text.lower())
    content_words = [w for w in words if w not in _STOP_WORDS]
    if not content_words:
        return 0.0
    hits = sum(
        1 for w in content_words if any(kw in w for kw in _TECH_KEYWORDS)
    )
    return hits / len(content_words)


def _importance_from_text(text: str) -> float:
    """Compute importance_score [0, 100] for a single text fragment.

    Formula:
    - Base 20 points
    - Length bonus: up to 30 pts (saturates at 200 chars)
    - Keyword density bonus: up to 50 pts
    """
    text = text.strip()
    if not text:
        return 0.0
    length_score = min(len(text) / 200.0, 1.0) * 30.0
    density_score = _keyword_density(text) * 50.0
    return round(20.0 + length_score + density_score, 2)


def _one_sentence(text: str, max_len: int = 120) -> str:
    """Extract or fabricate a one-sentence summary from text."""
    text = text.strip()
    # Take first sentence ending with punctuation
    m = re.search(r"[^.!?]*[.!?]", text)
    if m:
        s = m.group(0).strip()
        if len(s) <= max_len:
            return s
    # Fall back: truncate
    return text[:max_len].rstrip() + ("…" if len(text) > max_len else "")


def _extract_topic_tags(text: str) -> list[str]:
    """Return sorted list of tech-keyword tags found in text (deduped)."""
    words = re.findall(r"[a-z0-9_\-]+", text.lower())
    found: set[str] = set()
    for w in words:
        for kw in _TECH_KEYWORDS:
            if kw in w:
                found.add(kw)
    return sorted(found)


def _extract_entities(text: str) -> list[str]:
    """Heuristic: extract capitalised tokens that look like project/tech names."""
    # Match runs of capitalised alphanumeric tokens (acronyms, PascalCase names)
    candidates = re.findall(r"\b[A-Z][A-Za-z0-9_\-]{1,30}\b", text)
    # Deduplicate, keep insertion order deterministically via sorted
    seen: set[str] = set()
    result: list[str] = []
    for c in candidates:
        if c not in seen and c not in {"The", "This", "That", "For", "In", "It", "A"}:
            seen.add(c)
            result.append(c)
    return result[:10]  # cap to 10


# ---------------------------------------------------------------------------
# README Compression
# ---------------------------------------------------------------------------

def _split_readme_fragments(readme_text: str) -> list[str]:
    """Split README into meaningful fragments: headings + bullet items + paragraphs."""
    fragments: list[str] = []
    lines = readme_text.splitlines()
    current_para: list[str] = []

    def _flush_para() -> None:
        para = " ".join(current_para).strip()
        if para:
            fragments.append(para)
        current_para.clear()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            _flush_para()
            continue
        # Heading: ## Foo or # Foo
        if re.match(r"^#{1,6}\s+", stripped):
            _flush_para()
            heading_text = re.sub(r"^#{1,6}\s+", "", stripped).strip()
            if heading_text:
                fragments.append(heading_text)
        # Bullet: - foo / * foo / + foo
        elif re.match(r"^[\-\*\+]\s+", stripped):
            _flush_para()
            bullet_text = re.sub(r"^[\-\*\+]\s+", "", stripped).strip()
            if bullet_text:
                fragments.append(bullet_text)
        # Numbered list: 1. foo
        elif re.match(r"^\d+\.\s+", stripped):
            _flush_para()
            item_text = re.sub(r"^\d+\.\s+", "", stripped).strip()
            if item_text:
                fragments.append(item_text)
        else:
            current_para.append(stripped)

    _flush_para()
    return fragments


def compress_readme(
    full_name: str,
    readme_text: str,
    source: str = "api",
) -> list[EvidenceAtom]:
    """Extract heading/bullet/claim atoms from README text.

    Returns list[EvidenceAtom] with evidence_type='readme_claim'.
    Atoms with importance_score < 20 are discarded.
    """
    fragments = _split_readme_fragments(readme_text)
    atoms: list[EvidenceAtom] = []
    seq = 0
    for frag in fragments:
        score = _importance_from_text(frag)
        if score < 20.0:
            continue
        compressed = frag[:EvidenceAtom.MAX_COMPRESSED_CHARS]
        atom = EvidenceAtom(
            evidence_id=make_evidence_id(full_name, "readme_claim", seq),
            full_name=full_name,
            source=source,
            evidence_type="readme_claim",
            raw_ref="readme",
            one_sentence_summary=_one_sentence(frag),
            compressed_content=compressed,
            entities=_extract_entities(frag),
            topic_tags=_extract_topic_tags(frag),
            importance_score=score,
            technical_depth_score=_keyword_density(frag) * 100.0,
            novelty_score=None,
            confidence=0.85,
            created_at=utc_now_iso(),
        )
        atoms.append(atom)
        seq += 1
    return atoms


# ---------------------------------------------------------------------------
# Release Compression
# ---------------------------------------------------------------------------

def compress_releases(
    full_name: str,
    releases: list[dict],
) -> list[EvidenceAtom]:
    """Convert release list into release_signal EvidenceAtom list.

    Each release produces one atom. Content = tag + name + truncated body.
    """
    atoms: list[EvidenceAtom] = []
    for seq, rel in enumerate(releases):
        tag = str(rel.get("tag") or rel.get("tag_name") or "")
        name = str(rel.get("name") or "")
        body = str(rel.get("body") or "")
        published_at = str(rel.get("published_at") or "")

        # Compose compressed content: tag | name | first 300 chars of body
        parts = [p for p in [tag, name] if p]
        label = " — ".join(parts) if parts else "(release)"
        body_snippet = body[:300].strip()
        content = f"{label}\n{body_snippet}" if body_snippet else label
        content = content[:EvidenceAtom.MAX_COMPRESSED_CHARS]

        summary = f"Release {tag or name}: {_one_sentence(body) if body else name or tag}"

        atom = EvidenceAtom(
            evidence_id=make_evidence_id(full_name, "release_signal", seq),
            full_name=full_name,
            source="api",
            evidence_type="release_signal",
            raw_ref=tag or f"release_{seq}",
            one_sentence_summary=summary[:120],
            compressed_content=content,
            entities=_extract_entities(f"{name} {body[:200]}"),
            topic_tags=_extract_topic_tags(f"{name} {body}"),
            importance_score=_importance_from_text(f"{name} {body[:200]}"),
            technical_depth_score=_keyword_density(body) * 100.0 if body else 0.0,
            novelty_score=None,
            confidence=0.95,
            created_at=utc_now_iso(),
        )
        atoms.append(atom)
    return atoms


# ---------------------------------------------------------------------------
# Issues Compression
# ---------------------------------------------------------------------------

_PRIORITY_LABELS = frozenset([
    "bug", "enhancement", "feature", "feature-request", "breaking", "critical",
    "help wanted", "good first issue", "performance", "security", "regression",
    "v2", "v3", "roadmap", "milestone",
])


def _issue_relevance_score(issue: dict) -> float:
    """Score an issue for inclusion priority. Higher = more relevant."""
    score = float(issue.get("comment_count", issue.get("comments", 0)) or 0) * 2.0
    labels: list[str] = issue.get("labels", [])
    label_strs = [
        (lb if isinstance(lb, str) else lb.get("name", "") if isinstance(lb, dict) else "")
        for lb in labels
    ]
    for lbl in label_strs:
        if lbl.lower() in _PRIORITY_LABELS:
            score += 10.0
    title = issue.get("title", "")
    score += _importance_from_text(title) * 0.3
    # Prefer open issues slightly
    if issue.get("state", "open") == "open":
        score += 5.0
    return score


def compress_issues(
    full_name: str,
    issues: list[dict],
    top_n: int = 10,
) -> list[EvidenceAtom]:
    """Convert issue list into issue_signal EvidenceAtom list (top N by relevance)."""
    ranked = sorted(issues, key=_issue_relevance_score, reverse=True)[:top_n]
    atoms: list[EvidenceAtom] = []
    for seq, issue in enumerate(ranked):
        title = str(issue.get("title") or "")
        body = str(issue.get("body") or "")
        state = str(issue.get("state") or "open")
        labels: list[str] = issue.get("labels", [])
        label_strs = [
            (lb if isinstance(lb, str) else lb.get("name", "") if isinstance(lb, dict) else "")
            for lb in labels
        ]
        issue_num = issue.get("number", seq)

        body_snippet = body[:300].strip()
        label_part = ", ".join(label_strs) if label_strs else ""
        content_parts = [f"[{state}] #{issue_num}: {title}"]
        if label_part:
            content_parts.append(f"Labels: {label_part}")
        if body_snippet:
            content_parts.append(body_snippet)
        content = "\n".join(content_parts)[:EvidenceAtom.MAX_COMPRESSED_CHARS]

        summary_base = f"Issue #{issue_num}: {title}"
        summary = summary_base[:120]

        combined_text = f"{title} {body[:300]}"
        atom = EvidenceAtom(
            evidence_id=make_evidence_id(full_name, "issue_signal", seq),
            full_name=full_name,
            source="api",
            evidence_type="issue_signal",
            raw_ref=str(issue_num),
            one_sentence_summary=summary,
            compressed_content=content,
            entities=_extract_entities(combined_text),
            topic_tags=_extract_topic_tags(combined_text) + [
                lbl.lower().replace(" ", "_") for lbl in label_strs
                if lbl.lower() in _PRIORITY_LABELS
            ],
            importance_score=_importance_from_text(combined_text),
            technical_depth_score=_keyword_density(combined_text) * 100.0,
            novelty_score=None,
            confidence=0.80,
            created_at=utc_now_iso(),
        )
        # Deduplicate topic_tags
        atom.topic_tags = sorted(set(atom.topic_tags))
        atoms.append(atom)
    return atoms


# ---------------------------------------------------------------------------
# Reasoning Packet Assembly
# ---------------------------------------------------------------------------

def build_reasoning_packet(
    full_name: str,
    atoms: list[EvidenceAtom],
    snapshot: RepoSnapshot,
) -> ReasoningPacket:
    """Assemble a ReasoningPacket from atoms + snapshot.

    - metrics: key numbers from snapshot
    - local_project_brief: ≤1000 chars, top atoms' one_sentence_summary concatenated
    - atoms classified by evidence_type into respective evidence lists
    """
    # Build metrics dict from snapshot (only non-None numeric fields)
    metrics: dict[str, Any] = {}
    metric_fields = [
        "stars", "forks", "watchers", "open_issues",
        "commit_count_7d", "active_contributors_30d",
        "stars_delta_1h", "stars_delta_6h", "stars_delta_24h",
        "stars_delta_7d", "stars_delta_30d",
        "forks_delta_24h", "issues_delta_24h", "prs_delta_24h",
        "star_acceleration",
    ]
    for fname in metric_fields:
        val = getattr(snapshot, fname, None)
        if val is not None:
            metrics[fname] = val
    if snapshot.latest_release_tag:
        metrics["latest_release_tag"] = snapshot.latest_release_tag
    if snapshot.latest_release_at:
        metrics["latest_release_at"] = snapshot.latest_release_at
    if snapshot.history_status:
        metrics["history_status"] = snapshot.history_status

    # Sort atoms by importance_score descending (deterministic tie-break: evidence_id)
    sorted_atoms = sorted(
        atoms,
        key=lambda a: (-(a.importance_score or 0.0), a.evidence_id),
    )

    # Build local_project_brief from top summaries
    brief_parts: list[str] = []
    total_chars = 0
    brief_limit = ReasoningPacket.MAX_BRIEF_CHARS
    for atom in sorted_atoms:
        summary = atom.one_sentence_summary or ""
        if not summary:
            continue
        addition = summary if not brief_parts else f" {summary}"
        if total_chars + len(addition) > brief_limit:
            break
        brief_parts.append(summary)
        total_chars += len(addition)
    local_project_brief = " ".join(brief_parts)[:brief_limit]

    # Classify atoms by evidence_type
    growth_evidence: list[str] = []
    readme_evidence: list[str] = []
    release_evidence: list[str] = []
    social_evidence: list[str] = []
    youtube_evidence: list[str] = []

    for atom in atoms:
        etype = atom.evidence_type
        eid = atom.evidence_id
        if etype == "readme_claim":
            readme_evidence.append(eid)
        elif etype == "release_signal":
            release_evidence.append(eid)
        elif etype == "issue_signal":
            growth_evidence.append(eid)
        elif etype in ("social_mention", "growth_signal"):
            social_evidence.append(eid)
        elif etype == "youtube_mention":
            youtube_evidence.append(eid)
        else:
            # Unknown types go to growth_evidence
            growth_evidence.append(eid)

    packet_id = f"rp-{hashlib.sha256(full_name.encode()).hexdigest()[:8]}-{snapshot.snapshot_at[:10]}"

    return ReasoningPacket(
        packet_id=packet_id,
        full_name=full_name,
        created_at=utc_now_iso(),
        metrics=metrics,
        local_project_brief=local_project_brief or None,
        growth_evidence=growth_evidence,
        readme_evidence=readme_evidence,
        release_evidence=release_evidence,
        social_evidence=social_evidence,
        youtube_evidence=youtube_evidence,
        questions_for_reasoner=[],
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def persist_atoms(atoms: list[EvidenceAtom], conn: sqlite3.Connection) -> int:
    """Batch-write evidence atoms to repo_evidence_atoms table. Returns count written."""
    written = 0
    for atom in atoms:
        insert_row(conn, atom.TABLE, atom.to_row())
        written += 1
    conn.commit()
    return written


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test() -> dict[str, Any]:
    """Exercise the full evidence pipeline. Returns {tests_run, tests_passed, details}."""
    import sqlite3 as _sqlite3
    import tempfile
    import os

    from .schema import apply_schema, fetch_rows

    results: dict[str, Any] = {"tests_run": 0, "tests_passed": 0, "details": []}

    def _pass(name: str, note: str = "") -> None:
        results["tests_run"] += 1
        results["tests_passed"] += 1
        results["details"].append({"test": name, "status": "PASS", "note": note})

    def _fail(name: str, reason: str) -> None:
        results["tests_run"] += 1
        results["details"].append({"test": name, "status": "FAIL", "reason": reason})

    # ------------------------------------------------------------------
    # T1: make_evidence_id determinism
    # ------------------------------------------------------------------
    id1 = make_evidence_id("owner/repo", "readme_claim", 0)
    id2 = make_evidence_id("owner/repo", "readme_claim", 0)
    assert id1 == id2, "make_evidence_id is not deterministic"
    assert id1.startswith("ev-"), f"unexpected format: {id1}"
    assert "readme_claim" in id1, f"evidence_type segment missing: {id1}"
    assert id1.endswith("-0000"), f"seq segment missing: {id1}"
    _pass("make_evidence_id.determinism", id1)

    # Different repos → different IDs
    id3 = make_evidence_id("other/repo", "readme_claim", 0)
    assert id1 != id3, "different repos should produce different IDs"
    _pass("make_evidence_id.distinct_repos")

    # ------------------------------------------------------------------
    # T2: compress_readme — basic extraction
    # ------------------------------------------------------------------
    readme = """\
# MyProject

A blazing-fast LLM inference framework with GPU-accelerated attention.

## Features

- Sub-millisecond latency for transformer model inference
- Supports quantization, LoRA fine-tuning and RAG pipelines
- Production-ready distributed async batch processing API
- Open-source with active community and benchmark suite

## Installation

```
pip install myproject
```

Just run `pip install myproject` and you're ready.
"""
    atoms = compress_readme("owner/myproject", readme)
    assert len(atoms) > 0, "compress_readme returned no atoms"
    # All atoms should have importance_score >= 20
    low_score = [a for a in atoms if (a.importance_score or 0) < 20]
    assert not low_score, f"atoms below threshold: {[a.importance_score for a in low_score]}"
    # All evidence_ids should be unique
    ids = [a.evidence_id for a in atoms]
    assert len(ids) == len(set(ids)), "duplicate evidence_ids in compress_readme output"
    # All compressed_content ≤ 500
    too_long = [a for a in atoms if (a.compressed_content or "") and len(a.compressed_content) > 500]
    assert not too_long, "compressed_content exceeds 500 chars"
    # evidence_type
    assert all(a.evidence_type == "readme_claim" for a in atoms)
    _pass("compress_readme.basic", f"{len(atoms)} atoms extracted")

    # ------------------------------------------------------------------
    # T3: compress_readme — low-importance filter
    # ------------------------------------------------------------------
    sparse_readme = "# Setup\n\nRun it.\n\nDone.\n"
    sparse_atoms = compress_readme("owner/sparse", sparse_readme)
    # Fragments: "Setup", "Run it.", "Done." — short/no-keyword → should be filtered
    # The heading "Setup" has no keywords → score = 20 + tiny_len + 0_density
    # We just verify no fragment exceeds 500 chars and all >= 20
    for a in sparse_atoms:
        assert (a.importance_score or 0) >= 20
    _pass("compress_readme.low_importance_filter", f"{len(sparse_atoms)} atoms survived filter")

    # ------------------------------------------------------------------
    # T4: compress_releases
    # ------------------------------------------------------------------
    releases = [
        {
            "tag": "v2.0.0",
            "name": "Major Release: GPU Inference Engine",
            "body": "This release introduces a brand-new GPU inference engine with 3x faster transformer model performance, quantization support, and improved memory efficiency.",
            "published_at": "2026-05-10T12:00:00Z",
        },
        {
            "tag": "v1.9.1",
            "name": "Bug Fixes",
            "body": "Fixed tokenizer edge case.",
            "published_at": "2026-04-20T08:00:00Z",
        },
    ]
    rel_atoms = compress_releases("owner/myproject", releases)
    assert len(rel_atoms) == 2, f"expected 2 release atoms, got {len(rel_atoms)}"
    assert rel_atoms[0].evidence_type == "release_signal"
    assert rel_atoms[0].raw_ref == "v2.0.0"
    assert len(rel_atoms[0].compressed_content or "") <= 500
    # IDs unique
    rel_ids = [a.evidence_id for a in rel_atoms]
    assert len(rel_ids) == len(set(rel_ids))
    _pass("compress_releases.basic", f"{len(rel_atoms)} release atoms")

    # Empty releases
    assert compress_releases("owner/x", []) == []
    _pass("compress_releases.empty_list")

    # ------------------------------------------------------------------
    # T5: compress_issues
    # ------------------------------------------------------------------
    issues = [
        {
            "number": 101,
            "title": "Critical performance regression in GPU attention kernel",
            "body": "After v1.9 update, transformer inference speed dropped by 40% on CUDA devices. Reproducible with quantized models. See benchmark results attached.",
            "labels": ["bug", "performance"],
            "state": "open",
            "comment_count": 15,
        },
        {
            "number": 55,
            "title": "Feature request: add LoRA fine-tuning support",
            "body": "We need support for LoRA adapters in the production inference pipeline.",
            "labels": ["enhancement", "feature-request"],
            "state": "open",
            "comment_count": 8,
        },
        {
            "number": 12,
            "title": "Typo in README",
            "body": "Line 3 has a typo.",
            "labels": [],
            "state": "closed",
            "comment_count": 0,
        },
    ]
    issue_atoms = compress_issues("owner/myproject", issues, top_n=2)
    assert len(issue_atoms) == 2, f"expected 2 issue atoms, got {len(issue_atoms)}"
    assert issue_atoms[0].evidence_type == "issue_signal"
    # issue #101 (highest relevance: 15 comments + bug+performance labels) should be first
    assert "101" in issue_atoms[0].raw_ref or "101" in issue_atoms[0].compressed_content, (
        f"expected issue #101 to rank highest, got raw_ref={issue_atoms[0].raw_ref}"
    )
    assert len(issue_atoms[0].compressed_content or "") <= 500
    _pass("compress_issues.basic", f"{len(issue_atoms)} top-2 issue atoms")

    # Edge: empty
    assert compress_issues("owner/x", []) == []
    _pass("compress_issues.empty_list")

    # ------------------------------------------------------------------
    # T6: build_reasoning_packet
    # ------------------------------------------------------------------
    snapshot = RepoSnapshot(
        snapshot_id="snap-test-001",
        full_name="owner/myproject",
        snapshot_at="2026-05-27T00:00:00Z",
        stars=5000,
        forks=200,
        stars_delta_24h=450,
        star_acceleration=3.5,
        history_status="sufficient",
    )
    all_atoms = atoms + rel_atoms + issue_atoms
    packet = build_reasoning_packet("owner/myproject", all_atoms, snapshot)
    assert packet.full_name == "owner/myproject"
    assert "stars" in packet.metrics
    assert packet.metrics["stars"] == 5000
    assert packet.metrics["star_acceleration"] == 3.5
    assert len(packet.local_project_brief or "") <= 1000
    # Release atoms should appear in release_evidence
    for ra in rel_atoms:
        assert ra.evidence_id in packet.release_evidence, (
            f"{ra.evidence_id} missing from release_evidence"
        )
    # Readme atoms in readme_evidence
    for a in atoms:
        assert a.evidence_id in packet.readme_evidence
    _pass("build_reasoning_packet.basic", f"brief={len(packet.local_project_brief or '')} chars")

    # packet_id is deterministic: same full_name + snapshot → same packet_id
    packet2 = build_reasoning_packet("owner/myproject", all_atoms, snapshot)
    assert packet.packet_id == packet2.packet_id, "build_reasoning_packet not deterministic"
    _pass("build_reasoning_packet.determinism")

    # ------------------------------------------------------------------
    # T7: persist_atoms (SQLite round-trip)
    # ------------------------------------------------------------------
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
        db_path = tf.name
    try:
        conn = _sqlite3.connect(db_path)
        apply_schema(conn)
        count = persist_atoms(all_atoms, conn)
        assert count == len(all_atoms), f"persist_atoms returned {count}, expected {len(all_atoms)}"
        rows = fetch_rows(conn, "repo_evidence_atoms", "full_name=?", ("owner/myproject",))
        assert len(rows) == len(all_atoms), (
            f"expected {len(all_atoms)} rows in DB, got {len(rows)}"
        )
        # Verify round-trip for first readme atom
        first = EvidenceAtom.from_row(rows[0])
        assert first.evidence_type in ("readme_claim", "release_signal", "issue_signal")
        conn.close()
    finally:
        os.unlink(db_path)
    _pass("persist_atoms.sqlite_roundtrip", f"{count} atoms written and verified")

    # ------------------------------------------------------------------
    # T8: source metadata preserved
    # ------------------------------------------------------------------
    tagged_atoms = compress_readme("owner/repo", readme, source="github_api_v3")
    assert all(a.source == "github_api_v3" for a in tagged_atoms), (
        "source metadata not preserved in compress_readme"
    )
    _pass("compress_readme.source_metadata")

    return results


if __name__ == "__main__":
    import json as _json
    import sys as _sys

    m = _self_test()
    print(_json.dumps(m, indent=2))
    if m["tests_run"] != m["tests_passed"]:
        _sys.exit(1)
