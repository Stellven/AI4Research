"""End-to-end integration test for the DeepResearch core runtime.

Pipeline under test:
    fixture markdown source
        -> research.cli init   (real SQLite migration via lib/research/migrations/001_init.sql)
        -> research.cli add-source / extract  (real evidence write via evidence.ledger.write_evidence)
        -> research.cli export                 (real evidence.jsonl emitted from DB)
        -> test harness                        (real Claim / ClaimEvidenceLink / ReportAST built via schemas dataclasses, real final.md emitted by AST walk)

The test integrates against the same code path the CLI exposes for operators —
no @mock.patch, no fake DB, no fake span text. The S03 core runtime is the
unit under integration; claims + AST + final.md emission happen in the test
harness itself because S04 orchestration has not yet been built (per epic DAG).

Acceptance criteria (S05 N2 dispatch):
- pytest harness/tests/research/integration -v exits 0
- Fixture files present in tests/research/fixtures/integration/
- Generated _out/ contains: evidence.jsonl, claims.jsonl, report_ast.json, final.md
- final.md non-empty and contains at least 1 [evidence_id] citation pattern
- Zero @mock.patch / @patch in integration test files
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

# N5/N1 sys.path idiom — harness/ is intentionally not a Python package
_LIB_DIR = Path(__file__).resolve().parents[3] / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from research import cli as research_cli  # noqa: E402
from research import hashing as research_hashing  # noqa: E402
from research import ids as research_ids  # noqa: E402
from research import schemas as research_schemas  # noqa: E402
from research import storage as research_storage  # noqa: E402

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "integration"
FIXTURE_SOURCE = FIXTURE_DIR / "source_alpha.md"

CITATION_PATTERN = re.compile(r"\[cite:ev_[0-9a-f]+\]")


# ---------------------------------------------------------------------------
# Pipeline driver
# ---------------------------------------------------------------------------


def _run_cli(*argv: str) -> int:
    """Invoke research.cli.main directly with the given argv."""
    return research_cli.main(list(argv))


def _build_claims_jsonl(
    out_path: Path,
    db_path: Path,
    run_id: str,
    section_path: str,
) -> list[tuple[research_schemas.Claim, research_schemas.ClaimEvidenceLink]]:
    """Read evidence from DB, synthesise one Claim per evidence + a link, write claims.jsonl."""
    conn = research_storage.get_connection(str(db_path))
    rows = conn.execute(
        "SELECT id, source_id, content, span_start, span_end, content_hash "
        "FROM evidence_items WHERE run_id = ? ORDER BY span_start",
        (run_id,),
    ).fetchall()
    conn.close()

    pairs: list[tuple[research_schemas.Claim, research_schemas.ClaimEvidenceLink]] = []
    if out_path.exists():
        out_path.unlink()

    for i, row in enumerate(rows, start=1):
        evidence_id = row["id"]
        claim_text = (
            f"Evidence #{i} from source {row['source_id'][:8]} states: "
            f"{row['content'].split(chr(0))[0][:200]}"
        )
        cid = research_ids.claim_id(i, claim_text)
        claim = research_schemas.Claim(
            claim_id=cid,
            claim_text=claim_text,
            section_path=section_path,
            source_method="extracted_from_evidence",
            is_key=True,
            claim_type="factual",
            support_rating="moderate",
            evidence_ids=[evidence_id],
            confidence=0.75,
        )
        lid = research_ids.link_id(cid, evidence_id)
        link = research_schemas.ClaimEvidenceLink(
            link_id=lid,
            claim_id=cid,
            evidence_id=evidence_id,
            link_type="supports",
            relevance_score=row.get("confidence", 0.7) if hasattr(row, "get") else 0.7,
            is_primary=True,
        )
        research_storage.append_jsonl(str(out_path), asdict(claim))
        research_storage.append_jsonl(str(out_path), asdict(link))
        pairs.append((claim, link))

    return pairs


def _build_report_ast(
    sprint_id: str,
    pairs: list[tuple[research_schemas.Claim, research_schemas.ClaimEvidenceLink]],
) -> tuple[research_schemas.ReportAST, str]:
    """Build a 1-chapter, 1-section ReportAST and return (ast, ast_id)."""
    ast_id = research_ids.ast_id(sprint_id)
    section = research_schemas.Section(
        section_id=research_ids.section_id(1, 1),
        title="Smoke Section",
        order=1,
        target_chars=1800,
        min_chars=1500,
        max_chars=4000,
        evidence_budget=10,
        claim_budget=10,
        status="planned",
    )
    chapter = research_schemas.Chapter(
        chapter_id=research_ids.chapter_id(1),
        title="Smoke Chapter",
        order=1,
        sections=[section],
        status="planned",
    )
    ast = research_schemas.ReportAST(
        ast_id=ast_id,
        sprint_id=sprint_id,
        title="DeepResearch Integration Smoke",
        target_chars=1800,
        target_sections=1,
        target_chapters=1,
        depth_tier=2,
        status="drafting",
        chapters=[chapter],
    )
    return ast, ast_id


def _emit_final_md(
    out_path: Path,
    ast: research_schemas.ReportAST,
    pairs: list[tuple[research_schemas.Claim, research_schemas.ClaimEvidenceLink]],
) -> None:
    """Walk the AST and emit a markdown report with [cite:ev_xxx] citation markers."""
    lines: list[str] = []
    lines.append(f"# {ast.title}")
    lines.append("")
    lines.append(f"_ReportAST id_: `{ast.ast_id}` · _sprint_: `{ast.sprint_id}`")
    lines.append("")

    for chapter in sorted(ast.chapters, key=lambda c: c.order):
        lines.append(f"## {chapter.order}. {chapter.title}")
        lines.append("")
        for section in sorted(chapter.sections, key=lambda s: s.order):
            lines.append(f"### {chapter.order}.{section.order} {section.title}")
            lines.append("")
            for claim, link in pairs:
                lines.append(
                    f"{claim.claim_text} [cite:{link.evidence_id}]"
                )
                lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def _run_pipeline(work_dir: Path) -> dict:
    """Execute the full pipeline; return paths to produced artifacts."""
    db_path = work_dir / "research.sqlite"
    out_dir = work_dir / "_out"
    out_dir.mkdir(parents=True, exist_ok=True)

    source_text = FIXTURE_SOURCE.read_text(encoding="utf-8")

    # 1. init DB
    rc = _run_cli("init", str(db_path), "--topic", "Smoke integration", "--depth-tier", "quick")
    assert rc == 0, "research.cli init must succeed"

    conn = research_storage.get_connection(str(db_path))
    run_id = conn.execute("SELECT id FROM research_runs LIMIT 1").fetchone()["id"]
    conn.close()

    # 2. add source
    rc = _run_cli(
        "add-source", str(db_path),
        "--run-id", run_id,
        "--title", "Alpha Source — Solar DeepResearch Smoke",
        "--text", source_text,
    )
    assert rc == 0, "research.cli add-source must succeed"

    conn = research_storage.get_connection(str(db_path))
    source_id = conn.execute(
        "SELECT id FROM research_sources WHERE run_id = ?", (run_id,)
    ).fetchone()["id"]
    conn.close()

    # 3. extract evidence
    rc = _run_cli(
        "extract", str(db_path),
        "--run-id", run_id,
        "--source-id", source_id,
    )
    assert rc == 0, "research.cli extract must succeed"

    # 4. export evidence.jsonl + sources.jsonl
    rc = _run_cli(
        "export", str(db_path),
        "--run-id", run_id,
        "--output-dir", str(out_dir),
    )
    assert rc == 0, "research.cli export must succeed"

    evidence_jsonl = out_dir / "evidence.jsonl"
    sources_jsonl = out_dir / "sources.jsonl"
    assert evidence_jsonl.exists(), "evidence.jsonl must be written by export"
    assert sources_jsonl.exists(), "sources.jsonl must be written by export"

    # 5. build claims.jsonl from DB evidence
    claims_jsonl = out_dir / "claims.jsonl"
    pairs = _build_claims_jsonl(
        claims_jsonl, db_path, run_id, section_path="ch1/sec1"
    )
    assert pairs, "at least one Claim must be synthesised"
    assert claims_jsonl.exists()

    # 6. build ReportAST + write report_ast.json
    ast, ast_id = _build_report_ast(
        sprint_id="sprint-20260513-solar-deepresearch-product-line-s05-verification-release",
        pairs=pairs,
    )
    report_ast_json = out_dir / "report_ast.json"
    report_ast_json.write_text(
        json.dumps(asdict(ast), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # 7. emit final.md by walking the AST
    final_md = out_dir / "final.md"
    _emit_final_md(final_md, ast, pairs)

    return {
        "db_path": db_path,
        "out_dir": out_dir,
        "run_id": run_id,
        "source_id": source_id,
        "evidence_jsonl": evidence_jsonl,
        "sources_jsonl": sources_jsonl,
        "claims_jsonl": claims_jsonl,
        "report_ast_json": report_ast_json,
        "final_md": final_md,
        "ast_id": ast_id,
        "claim_count": len(pairs),
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory: pytest.TempPathFactory) -> dict:
    work_dir = tmp_path_factory.mktemp("integration_pipeline")
    return _run_pipeline(work_dir)


class TestFixturePresent:
    def test_fixture_dir_exists(self) -> None:
        assert FIXTURE_DIR.is_dir(), f"fixture dir missing: {FIXTURE_DIR}"

    def test_fixture_source_present(self) -> None:
        assert FIXTURE_SOURCE.is_file()
        text = FIXTURE_SOURCE.read_text(encoding="utf-8")
        assert len(text) > 200, "fixture markdown must be substantive"
        assert "Solar DeepResearch" in text


class TestPipelineArtifacts:
    def test_evidence_jsonl_written(self, pipeline: dict) -> None:
        path: Path = pipeline["evidence_jsonl"]
        assert path.is_file()
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        assert len(rows) >= 1, "at least one evidence row must be exported"
        for row in rows:
            assert "id" in row
            assert "source_id" in row
            assert "content_hash" in row
            assert isinstance(row.get("span_start"), int)
            assert isinstance(row.get("span_end"), int)

    def test_claims_jsonl_written(self, pipeline: dict) -> None:
        path: Path = pipeline["claims_jsonl"]
        assert path.is_file()
        lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        assert len(lines) >= 2, "expected interleaved Claim + ClaimEvidenceLink rows"

        claims = [r for r in lines if "claim_text" in r]
        links = [r for r in lines if "link_id" in r]
        assert claims, "no Claim records"
        assert links, "no ClaimEvidenceLink records"

        for claim in claims:
            assert claim["claim_text"], "claim_text must be non-empty"
            assert claim["claim_id"].startswith("clm_")
            assert claim["source_method"] in research_schemas.CLAIM_SOURCE_METHODS
            assert claim["claim_type"] in research_schemas.CLAIM_TYPES
            assert claim["support_rating"] in research_schemas.SUPPORT_RATINGS

        for link in links:
            assert link["link_id"].startswith("cel_")
            assert link["link_type"] in research_schemas.LINK_TYPES
            assert 0.0 <= link["relevance_score"] <= 1.0

    def test_report_ast_json_written(self, pipeline: dict) -> None:
        path: Path = pipeline["report_ast_json"]
        assert path.is_file()
        data = json.loads(path.read_text(encoding="utf-8"))

        assert data["ast_id"].startswith("ast_")
        assert data["sprint_id"].endswith("-s05-verification-release")
        assert data["target_chapters"] == len(data["chapters"])
        total_sections = sum(len(ch["sections"]) for ch in data["chapters"])
        assert data["target_sections"] == total_sections
        assert 1 <= data["depth_tier"] <= 4
        assert data["status"] in research_schemas.REPORT_STATUSES

    def test_final_md_written(self, pipeline: dict) -> None:
        path: Path = pipeline["final_md"]
        assert path.is_file()
        text = path.read_text(encoding="utf-8")
        assert len(text) > 0, "final.md must be non-empty"
        assert "DeepResearch Integration Smoke" in text

    def test_final_md_has_evidence_id_citation_pattern(self, pipeline: dict) -> None:
        text: str = pipeline["final_md"].read_text(encoding="utf-8")
        matches = CITATION_PATTERN.findall(text)
        assert matches, (
            f"final.md must contain at least one [cite:ev_xxx] citation pattern; "
            f"none matched {CITATION_PATTERN.pattern}"
        )
        # Each match must reference a real evidence_id present in evidence.jsonl
        ev_rows = [
            json.loads(line)
            for line in pipeline["evidence_jsonl"].read_text(encoding="utf-8").splitlines()
            if line
        ]
        ev_ids = {r["id"] for r in ev_rows}
        cited_ids = {m[len("[cite:"):-1] for m in matches}
        assert cited_ids.issubset(ev_ids), (
            f"every citation must reference a real evidence_id; "
            f"orphans={sorted(cited_ids - ev_ids)}"
        )


class TestEvidenceLedgerConsistency:
    def test_db_evidence_matches_export(self, pipeline: dict) -> None:
        db_path: Path = pipeline["db_path"]
        run_id: str = pipeline["run_id"]
        conn = research_storage.get_connection(str(db_path))
        db_count = conn.execute(
            "SELECT COUNT(*) FROM evidence_items WHERE run_id = ?", (run_id,)
        ).fetchone()[0]
        conn.close()

        exported = [
            line for line in
            pipeline["evidence_jsonl"].read_text(encoding="utf-8").splitlines()
            if line
        ]
        assert db_count == len(exported), (
            f"DB has {db_count} evidence rows, export has {len(exported)}"
        )

    def test_content_hash_canonical(self, pipeline: dict) -> None:
        """Every exported evidence row's content_hash must match sha256(span_text)."""
        for line in pipeline["evidence_jsonl"].read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            row = json.loads(line)
            content = row["content"]
            span_text = content.split("\x00", 1)[0]
            expected = research_hashing.content_hash(span_text)
            assert row["content_hash"] == expected, (
                f"content_hash mismatch for {row['id']}: "
                f"expected {expected[:16]}…, got {row['content_hash'][:16]}…"
            )


class TestIDDeterminism:
    def test_pipeline_run_twice_produces_same_ast_id(self, tmp_path_factory: pytest.TempPathFactory) -> None:
        """Independent run with identical inputs must derive an identical ast_id."""
        wd1 = tmp_path_factory.mktemp("rerun1")
        wd2 = tmp_path_factory.mktemp("rerun2")
        a = _run_pipeline(wd1)
        b = _run_pipeline(wd2)
        assert a["ast_id"] == b["ast_id"], (
            f"ast_id derivation must be deterministic; got {a['ast_id']} vs {b['ast_id']}"
        )


class TestTestIntegrity:
    def test_no_mock_patch_in_integration_files(self) -> None:
        """Stop Rule: integration suite must use no mock framework — AST scan, not text scan."""
        import ast as _ast

        root = Path(__file__).resolve().parent
        offenders: list[tuple[str, str]] = []
        for py_file in root.rglob("*.py"):
            tree = _ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for node in _ast.walk(tree):
                if isinstance(node, _ast.Import):
                    for alias in node.names:
                        if alias.name == "mock" or alias.name.startswith("unittest.mock"):
                            offenders.append((str(py_file), f"import {alias.name}"))
                elif isinstance(node, _ast.ImportFrom):
                    mod = node.module or ""
                    if mod == "mock" or mod.startswith("unittest.mock"):
                        offenders.append((str(py_file), f"from {mod} import …"))
                elif isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)):
                    for dec in node.decorator_list:
                        dec_src = _ast.unparse(dec) if hasattr(_ast, "unparse") else ""
                        if "mock" in dec_src or dec_src.startswith("patch"):
                            offenders.append((str(py_file), f"@{dec_src}"))
        assert not offenders, f"mock usage detected via AST scan: {offenders}"
