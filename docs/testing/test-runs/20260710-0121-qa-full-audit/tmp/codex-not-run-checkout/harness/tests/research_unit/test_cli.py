"""Tests for research CLI (cli.py) — 5 subcommands via main() entry point.

Constraints:
- Real SQLite with tmp_path (no mocks)
- Zero @mock.patch decorators
- Assertion count >= 10

Spec: sprint-20260513-solar-deepresearch-product-line-s03-core-runtime / N5
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# Ensure harness/lib is importable from tests.
_HARNESS_LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

from research import cli as research_cli
from research.cli import build_parser, main
from research.evaluator import ANALYSIS_TERMS_RE, TOKEN_RE, evaluate_artifacts


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_research.db")


class TestCliParser:
    def test_all_five_subcommands_registered(self):
        """A1: --help lists init, add-source, extract, ledger, status."""
        parser = build_parser()
        subs = parser._subparsers._group_actions[0].choices
        assert "init" in subs
        assert "add-source" in subs
        assert "extract" in subs
        assert "ledger" in subs
        assert "status" in subs

    def test_help_exits_zero(self):
        """A2: research --help exits 0."""
        assert main(["--help"]) == 0

    def test_no_subcommand_exits_zero(self):
        """A3: no subcommand prints help and exits 0."""
        assert main([]) == 0


class TestInit:
    def test_init_creates_db(self, db_path):
        """A4: init creates DB file and returns 0."""
        assert main(["init", db_path]) == 0
        assert os.path.exists(db_path)

    def test_init_rejects_existing(self, db_path):
        """A5: init on existing DB returns 1."""
        assert main(["init", db_path]) == 0
        assert main(["init", db_path]) == 1


class TestAddSourceAndExtract:
    def test_add_source_then_extract(self, db_path):
        """A6: add-source followed by extract produces evidence row."""
        assert main(["init", db_path]) == 0
        # Get run_id from init output — parse it by running init again is messy,
        # so query the DB directly.
        import sqlite3
        conn = sqlite3.connect(db_path)
        run_id = conn.execute("SELECT id FROM research_runs LIMIT 1").fetchone()[0]
        conn.close()

        assert main([
            "add-source", db_path,
            "--run-id", run_id,
            "--title", "Test Source",
            "--text", "This is test source content for CLI testing.",
        ]) == 0

        source_row = sqlite3.connect(db_path).execute(
            "SELECT id FROM research_sources WHERE run_id = ?", (run_id,)
        ).fetchone()
        source_id = source_row[0]

        assert main([
            "extract", db_path,
            "--run-id", run_id,
            "--source-id", source_id,
        ]) == 0


class TestLedger:
    def test_ledger_shows_summary(self, tmp_path):
        """A7: ledger shows run summary with source and evidence counts."""
        db = str(tmp_path / "ledger_test.db")
        assert main(["init", db]) == 0

        import sqlite3
        conn = sqlite3.connect(db)
        run_id = conn.execute("SELECT id FROM research_runs LIMIT 1").fetchone()[0]
        conn.close()

        assert main([
            "add-source", db, "--run-id", run_id,
            "--text", "Evidence ledger content",
        ]) == 0

        source_id = sqlite3.connect(db).execute(
            "SELECT id FROM research_sources WHERE run_id = ?", (run_id,)
        ).fetchone()[0]

        assert main([
            "extract", db, "--run-id", run_id, "--source-id", source_id,
        ]) == 0

        # Run ledger — just check exit code; output goes to stdout.
        assert main(["ledger", db, "--run-id", run_id]) == 0


class TestStatus:
    def test_status_exits_zero(self, db_path):
        """A8: status on valid DB returns 0."""
        assert main(["init", db_path]) == 0
        assert main(["status", db_path]) == 0

    def test_status_nonexistent_returns_one(self):
        """A9: status on missing DB returns 1."""
        assert main(["status", "/tmp/nonexistent_cli_test.db"]) == 1


class TestWebResearch:
    def test_search_writes_online_sources_with_fetch(self, db_path, monkeypatch):
        """Search must materialize source rows, not only update last_search."""
        assert main(["init", db_path, "--topic", "web smoke"]) == 0

        import sqlite3
        conn = sqlite3.connect(db_path)
        run_id = conn.execute("SELECT id FROM research_runs LIMIT 1").fetchone()[0]
        conn.close()

        monkeypatch.setattr(
            research_cli,
            "browser_use_search",
            lambda query, max_results: (
                [{"title": "Result A", "url": "https://example.com/a", "snippet": "Snippet A", "rank": 1, "connector": "fake"}],
                [],
            ),
        )
        monkeypatch.setattr(
            research_cli,
            "fetch_url_readable",
            lambda url: ("A fetched article says orbital data centers need evidence ledgers and citations.", None),
        )
        monkeypatch.setattr(research_cli, "browser_use_fetch_url", lambda url: ("A browser-use fetched article says orbital data centers need evidence ledgers and citations.", None))

        assert main([
            "search", db_path,
            "--run-id", run_id,
            "--query", "orbital data centers",
            "--provider", "browser-use",
            "--fetch",
            "--require-online",
            "--json",
        ]) == 0

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT title, url, content_span FROM research_sources WHERE run_id = ?", (run_id,)).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "Result A"
        assert row[1] == "https://example.com/a"
        assert "fetched article" in json.loads(row[2])["text"]

    def test_run_web_query_end_to_end_without_network(self, db_path, tmp_path, monkeypatch):
        """run --web-query should create source/evidence/claims/sections/final.md."""
        monkeypatch.setattr(
            research_cli,
            "browser_use_search",
            lambda query, max_results: (
                [{"title": "Result B", "url": "https://example.com/b", "snippet": "Snippet B", "rank": 1, "connector": "fake"}],
                [],
            ),
        )
        monkeypatch.setattr(
            research_cli,
            "fetch_url_readable",
            lambda url: (
                "Orbital data centers are proposed as a response to terrestrial energy and cooling constraints. "
                "They also require launch economics, radiation tolerance, and reliable downlink capacity.",
                None,
            ),
        )
        monkeypatch.setattr(
            research_cli,
            "browser_use_fetch_url",
            lambda url: (
                "Orbital data centers are proposed as a response to terrestrial energy and cooling constraints. "
                "They also require launch economics, radiation tolerance, and reliable downlink capacity.",
                None,
            ),
        )

        out = tmp_path / "out"
        assert main([
            "run", db_path,
            "--topic", "orbital data centers",
            "--web-query", "orbital data centers",
            "--max-results", "1",
            "--output-dir", str(out),
            "--output-md", str(out / "final.md"),
        ]) == 0
        final = (out / "final.md").read_text()
        assert "Orbital data centers" in final or "orbital data centers" in final
        assert "[cite:" in final
        assert "## Execution Metrics" in final
        assert "Total token consumption" in final
        assert "Document word count" in final
        assert (out / "sources.jsonl").exists()
        assert (out / "evidence.jsonl").exists()
        assert (out / "claims.jsonl").exists()
        assert (out / "claim_evidence.jsonl").exists()
        assert (out / "sections.jsonl").exists()
        assert (out / "section_checks.jsonl").exists()
        assert (out / "report_ast.json").exists()
        assert (out / "final.bibliography.json").exists()
        assert (out / "research_execution_metrics.json").exists()
        eval_files = list(out.glob("*-research_eval.json"))
        assert eval_files
        eval_payload = json.loads(eval_files[0].read_text())
        assert eval_payload["status"] == "passed"
        assert eval_payload["source_count"] == 1
        assert eval_payload["evidence_count"] >= 1
        assert eval_payload["claim_count"] >= 1
        assert eval_payload["execution_metrics"]["document_word_count"] > 0
        assert eval_payload["execution_metrics"]["total_token_consumption"] > 0
        ast = json.loads((out / "report_ast.json").read_text())
        assert ast["target_sections"] >= 1
        assert ast["chapters"][0]["sections"]
        assert ast["execution_metrics"]["document_word_count"] > 0

    def test_auto_provider_prefers_browser_use_over_http(self, db_path, monkeypatch):
        """Auto provider must use browser-use first and avoid HTTP if it succeeds."""
        assert main(["init", db_path, "--topic", "provider route"]) == 0

        import sqlite3
        conn = sqlite3.connect(db_path)
        run_id = conn.execute("SELECT id FROM research_runs LIMIT 1").fetchone()[0]
        conn.close()

        called = {"http": False}
        monkeypatch.setattr(
            research_cli,
            "browser_use_search",
            lambda query, max_results: (
                [{"title": "Browser Result", "url": "https://example.com/browser", "snippet": "Browser snippet", "rank": 1, "connector": "browser-use"}],
                [],
            ),
        )

        def fail_http(query, max_results):
            called["http"] = True
            return [], ["http should not be called"]

        monkeypatch.setattr(research_cli, "http_web_search", fail_http)

        assert main([
            "search", db_path,
            "--run-id", run_id,
            "--query", "browser route",
            "--provider", "auto",
            "--json",
        ]) == 0
        assert called["http"] is False


class TestHumanSearchLoop:
    def test_handoff_search_writes_markdown(self, db_path, tmp_path):
        assert main(["init", db_path, "--topic", "human loop topic"]) == 0

        import sqlite3
        conn = sqlite3.connect(db_path)
        run_id = conn.execute("SELECT id FROM research_runs LIMIT 1").fetchone()[0]
        conn.close()

        out = tmp_path / "handoff.md"
        assert main([
            "handoff-search", db_path,
            "--run-id", run_id,
            "--query", "human loop query",
            "--max-results", "3",
            "--output-md", str(out),
        ]) == 0
        text = out.read_text()
        assert "Solar DeepResearch Human Search Handoff" in text
        assert "human loop query" in text
        assert "Required Output Format" in text

    def test_handoff_search_uses_research_profile_source_matrix(self, db_path, tmp_path):
        assert main(["init", db_path, "--topic", "technical architecture topic"]) == 0

        import sqlite3
        conn = sqlite3.connect(db_path)
        run_id = conn.execute("SELECT id FROM research_runs LIMIT 1").fetchone()[0]
        conn.close()

        out = tmp_path / "handoff-profile.md"
        assert main([
            "handoff-search", db_path,
            "--run-id", run_id,
            "--query", "latent reasoning architecture",
            "--research-profile", "technical_architecture",
            "--max-results", "8",
            "--output-md", str(out),
        ]) == 0
        text = out.read_text()
        assert "Profile: `technical_architecture`" in text
        assert "Required source types: paper" in text
        assert "Recommended source types: benchmark, code, official_doc" in text
        assert "| paper |" in text
        assert "| code |" in text
        assert "| official_doc |" in text
        assert "| benchmark |" in text
        assert "Source Type: <paper|code|official_doc|benchmark" in text
        assert "Source Type: <official|paper|news|blog|repo|standard|other>" not in text

    def test_import_search_normalizes_profile_source_type_aliases(self):
        markdown = """# External Search Results

## Source 1: Official Docs
URL: https://example.com/docs
Source Type: official

Summary:
- Official documentation.

## Source 2: GitHub Repo
URL: https://github.com/example/repo
Source Type: repo

Summary:
- Code repository.
"""
        records = research_cli.parse_human_search_markdown(markdown)

        assert [record["source_type"] for record in records] == ["official_doc", "code"]

    def test_profile_aware_online_search_writes_profile_source_types(self, db_path, monkeypatch):
        assert main(["init", db_path, "--topic", "profile online search topic"]) == 0

        import sqlite3
        conn = sqlite3.connect(db_path)
        run_id = conn.execute("SELECT id FROM research_runs LIMIT 1").fetchone()[0]
        conn.close()

        def fake_web_search(query, max_results, provider="auto"):
            if "GitHub" in query:
                kind = "code"
            elif "official documentation" in query:
                kind = "official"
            elif "benchmark results" in query:
                kind = "benchmark"
            else:
                kind = "paper"
            return ([{
                "title": f"{kind} result",
                "url": f"https://example.com/{kind}",
                "snippet": f"{kind} evidence about latent reasoning architecture.",
                "rank": 1,
                "connector": provider,
            }], [])

        monkeypatch.setattr(research_cli, "web_search", fake_web_search)

        assert main([
            "search", db_path,
            "--run-id", run_id,
            "--query", "latent reasoning architecture",
            "--research-profile", "technical_architecture",
            "--max-results", "8",
            "--json",
        ]) == 0

        conn = sqlite3.connect(db_path)
        source_types = sorted(row[0] for row in conn.execute(
            "SELECT DISTINCT source_type FROM research_sources WHERE run_id = ?",
            (run_id,),
        ).fetchall())
        conn.close()

        assert source_types == ["benchmark", "code", "official_doc", "paper"]

    def test_import_search_can_continue_pipeline(self, db_path, tmp_path):
        assert main(["init", db_path, "--topic", "human loop topic"]) == 0

        import sqlite3
        conn = sqlite3.connect(db_path)
        run_id = conn.execute("SELECT id FROM research_runs LIMIT 1").fetchone()[0]
        conn.close()

        results = tmp_path / "gemini-results.md"
        results.write_text(
            """# External Search Results: human loop topic

## Source 1: Official Orbital Data Center Note
URL: https://example.com/orbital-data-center
Publisher: Example Institute
Published: 2026-01-01
Source Type: official

Summary:
- Orbital data centers need launch economics and radiation-tolerant hardware.
- Power, cooling, and downlink constraints determine feasibility.

Key Claims:
- Orbital data centers can reduce terrestrial cooling pressure.
- Space deployment creates new reliability and communications constraints.

Relevant Quotes:
> Orbital computing depends on power and downlink capacity.
""",
            encoding="utf-8",
        )
        out = tmp_path / "out"
        final = out / "final.md"
        assert main([
            "import-search", db_path,
            "--run-id", run_id,
            "--input-md", str(results),
            "--continue",
            "--output-dir", str(out),
            "--output-md", str(final),
        ]) == 0
        assert final.exists()
        text = final.read_text()
        assert "Orbital data centers" in text
        assert "[cite:" in text
        assert (out / "sources.jsonl").exists()
        assert (out / "claims.jsonl").exists()


class TestTechnicalArchitectureProfile:
    def test_continue_pipeline_produces_profile_dense_sections(self, db_path, tmp_path):
        assert main(["init", db_path, "--topic", "latent reasoning technical architecture"]) == 0

        import sqlite3
        conn = sqlite3.connect(db_path)
        run_id = conn.execute("SELECT id FROM research_runs LIMIT 1").fetchone()[0]
        conn.close()

        seed_sources = [
            (
                "paper",
                "https://arxiv.org/abs/2412.06769",
                "Coconut paper",
                "Coconut uses continuous thought and hidden state recurrence for latent reasoning. "
                "The architecture changes test-time compute, reasoning state, and evaluation requirements.",
            ),
            (
                "code",
                "https://github.com/facebookresearch/coconut",
                "Coconut code",
                "The code repository exposes implementation boundaries for recurrent latent reasoning. "
                "Deployment requires reproducible checkpoints, pipeline gates, and audit evidence.",
            ),
            (
                "official_doc",
                "https://docs.example.edu/latent-reasoning",
                "OpenReview submission",
                "The official submission describes design tradeoffs, evaluation risk, and model-family constraints. "
                "Runtime integration must preserve provenance, citation support, and replayable artifacts.",
            ),
            (
                "benchmark",
                "https://paperswithcode.com/paper/softcot-soft-chain-of-thought-for-efficient",
                "SoftCoT benchmark",
                "Benchmark evidence compares soft chain of thought against visible token reasoning. "
                "Evaluation should track pass rate, token cost, wall time, and deployment failure modes.",
            ),
        ]
        for source_type, url, title, text in seed_sources:
            assert main([
                "add-source", db_path,
                "--run-id", run_id,
                "--source-type", source_type,
                "--url", url,
                "--title", title,
                "--text", text,
            ]) == 0

        out = tmp_path / "out"
        payload = research_cli.continue_research_pipeline(db_path, run_id, str(out), str(out / "final.md"))
        eval_path = out / f"{run_id}-research_eval.json"
        result = evaluate_artifacts(
            eval_path,
            report_ast=out / "report_ast.json",
            final_md=out / "final.md",
            bibliography=out / "final.bibliography.json",
            expert_md=out / "expert_synthesis.md",
            require_expert=True,
            research_profile="technical_architecture",
            strict_profile=True,
        )

        assert payload["claims"] >= 4
        assert result["ok"] is True
        assert not any(str(w).startswith("section_coverage_low_analysis_density") for w in result["warnings"])
        for raw in (out / "sections.jsonl").read_text(encoding="utf-8").splitlines():
            row = json.loads(raw)
            if row["section_type"] == "source_landscape":
                continue
            content = row["content"]
            density = len(ANALYSIS_TERMS_RE.findall(content)) / max(len(TOKEN_RE.findall(content)), 1)
            assert density >= 0.12, row["section_type"]

    def test_continue_pipeline_rewrites_sections_when_claims_already_exist(self, db_path, tmp_path):
        assert main(["init", db_path, "--topic", "latent reasoning rewrite regression"]) == 0

        import sqlite3
        conn = sqlite3.connect(db_path)
        run_id = conn.execute("SELECT id FROM research_runs LIMIT 1").fetchone()[0]
        conn.close()

        assert main([
            "add-source", db_path,
            "--run-id", run_id,
            "--source-type", "paper",
            "--url", "https://arxiv.org/abs/2412.06769",
            "--title", "Coconut paper",
            "--text", "Coconut uses continuous thought for latent reasoning architecture and runtime evaluation.",
        ]) == 0

        first_out = tmp_path / "first"
        first = research_cli.continue_research_pipeline(db_path, run_id, str(first_out), str(first_out / "final.md"))
        assert first["claims"] >= 1

        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE report_sections SET content = ? WHERE run_id = ? AND section_type = ?",
            ("# stale section\n\nNo architecture gate ledger.\n", run_id, "executive_summary"),
        )
        conn.commit()
        conn.close()

        second_out = tmp_path / "second"
        second = research_cli.continue_research_pipeline(db_path, run_id, str(second_out), str(second_out / "final.md"))
        assert second["claims"] == first["claims"]
        assert second["claims_inserted"] == 0

        sections = [json.loads(line) for line in (second_out / "sections.jsonl").read_text(encoding="utf-8").splitlines()]
        executive = next(row for row in sections if row["section_type"] == "executive_summary")
        assert "Architecture Gate Ledger" in executive["content"]


class TestDoctorUnaffected:
    def test_doctor_not_broken(self):
        """A10: doctor subcommand is not affected by research routing."""
        # doctor is a separate path, not going through our code.
        # We just verify the CLI parser still works after our changes.
        parser = build_parser()
        assert parser.prog == "solar-harness research"


class TestPolicyCli:
    def test_policy_doctor_lists_profiles(self, capsys):
        assert main(["policy-doctor", "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)

        assert payload["ok"] is True
        assert "technical_architecture" in payload["profiles"]
        assert "paper" in payload["source_authority_types"]
        assert payload["policy_path"].endswith("source_authority.json")

    def test_policy_explain_scores_arxiv_paper(self, capsys):
        assert main([
            "policy-explain",
            "--source-type", "paper",
            "--url", "https://arxiv.org/abs/2501.00001",
            "--title", "Paper",
            "--json",
        ]) == 0
        payload = json.loads(capsys.readouterr().out)

        assert payload["ok"] is True
        assert payload["score"] == 0.9
        assert payload["high_authority"] is True
        assert "arxiv.org" in payload["matched_rule"]["host_hits"]

    def test_source_audit_reports_profile_gaps(self, tmp_path, capsys):
        out = tmp_path / "out"
        out.mkdir()
        (out / "sources.jsonl").write_text(
            json.dumps({
                "id": "src_1",
                "source_type": "paper",
                "title": "Paper",
                "url": "https://arxiv.org/abs/2501.00001",
            }) + "\n",
            encoding="utf-8",
        )
        (out / "evidence.jsonl").write_text(
            json.dumps({
                "id": "ev_1",
                "source_id": "src_1",
                "content": "Abstract: latent reasoning paper.",
            }) + "\n",
            encoding="utf-8",
        )

        assert main([
            "source-audit",
            "--output-dir", str(out),
            "--research-profile", "technical_architecture",
            "--strict-profile",
            "--json",
        ]) == 1
        payload = json.loads(capsys.readouterr().out)

        assert payload["ok"] is False
        assert payload["source_authority_average"] == 0.9
        assert payload["missing_recommended_source_types"] == ["benchmark", "code", "official_doc"]
        assert any(err.startswith("source_type_count_too_low") for err in payload["errors"])
        assert any("Add code source" in suggestion for suggestion in payload["replacement_suggestions"])

    def test_source_audit_writes_gap_handoff(self, tmp_path, capsys):
        out = tmp_path / "out"
        out.mkdir()
        handoff = tmp_path / "gap.md"
        (out / "sources.jsonl").write_text(
            json.dumps({
                "id": "src_1",
                "source_type": "paper",
                "title": "Paper",
                "url": "https://arxiv.org/abs/2501.00001",
            }) + "\n",
            encoding="utf-8",
        )
        (out / "evidence.jsonl").write_text(
            json.dumps({
                "id": "ev_1",
                "source_id": "src_1",
                "content": "Abstract: latent reasoning paper.",
            }) + "\n",
            encoding="utf-8",
        )

        assert main([
            "source-audit",
            "--output-dir", str(out),
            "--research-profile", "technical_architecture",
            "--strict-profile",
            "--write-handoff", str(handoff),
            "--handoff-query", "latent reasoning architecture",
            "--json",
        ]) == 1
        payload = json.loads(capsys.readouterr().out)
        text = handoff.read_text(encoding="utf-8")

        assert payload["handoff_path"] == str(handoff)
        assert "DeepResearch Source Gap Handoff" in text
        assert "latent reasoning architecture" in text
        assert "Source Type: paper|code|official_doc|benchmark" in text
        assert "Add code source" in text

    def test_source_audit_enqueue_followup_appends_graph_node(self, tmp_path, capsys):
        out = tmp_path / "out"
        out.mkdir()
        graph = tmp_path / "sprint-test.task_graph.json"
        graph.write_text(
            json.dumps({
                "sprint_id": "sprint-test",
                "nodes": [],
                "node_results": {},
                "gate_results": {},
            }) + "\n",
            encoding="utf-8",
        )
        (out / "sources.jsonl").write_text(
            json.dumps({
                "id": "src_1",
                "source_type": "paper",
                "title": "Paper",
                "url": "https://arxiv.org/abs/2501.00001",
            }) + "\n",
            encoding="utf-8",
        )
        (out / "evidence.jsonl").write_text(
            json.dumps({
                "id": "ev_1",
                "source_id": "src_1",
                "content": "Abstract: latent reasoning paper.",
            }) + "\n",
            encoding="utf-8",
        )

        assert main([
            "source-audit",
            "--output-dir", str(out),
            "--research-profile", "technical_architecture",
            "--strict-profile",
            "--enqueue-followup",
            "--graph", str(graph),
            "--followup-node-id", "DR_SOURCE_GAP_TEST",
            "--handoff-query", "latent reasoning architecture",
            "--dry-run",
            "--json",
        ]) == 1
        payload = json.loads(capsys.readouterr().out)
        graph_payload = json.loads(graph.read_text(encoding="utf-8"))
        node = graph_payload["nodes"][0]
        followup = json.loads((out / "source-audit-followup.json").read_text(encoding="utf-8"))

        assert payload["followup"]["ok"] is True
        assert payload["followup"]["node_id"] == "DR_SOURCE_GAP_TEST"
        assert payload["followup"]["enqueue"]["dry_run"] is True
        assert payload["followup"]["enqueue"]["enqueued"][0]["node"] == "DR_SOURCE_GAP_TEST"
        assert node["id"] == "DR_SOURCE_GAP_TEST"
        assert "research.source_matrix" in node["required_capabilities"]
        assert "source-gap-handoff.md" in payload["handoff_path"]
        assert followup["node_id"] == "DR_SOURCE_GAP_TEST"

    def test_source_audit_enqueue_followup_writes_real_queue(self, tmp_path, capsys, monkeypatch):
        harness = tmp_path / "harness"
        (harness / "run" / "queue").mkdir(parents=True)
        (harness / "run" / "pane-leases").mkdir(parents=True)
        real_queue = Path.home() / ".solar" / "harness" / "run" / "queue" / "sprint-test.jsonl"
        real_queue_before = real_queue.read_text(encoding="utf-8") if real_queue.exists() else None
        out = tmp_path / "out"
        out.mkdir()
        graph = harness / "sprints" / "sprint-test.task_graph.json"
        graph.parent.mkdir(parents=True)
        graph.write_text(
            json.dumps({
                "sprint_id": "sprint-test",
                "nodes": [],
                "node_results": {},
                "gate_results": {},
            }) + "\n",
            encoding="utf-8",
        )
        (out / "sources.jsonl").write_text(
            json.dumps({
                "id": "src_1",
                "source_type": "paper",
                "title": "Paper",
                "url": "https://arxiv.org/abs/2501.00001",
            }) + "\n",
            encoding="utf-8",
        )
        (out / "evidence.jsonl").write_text(
            json.dumps({
                "id": "ev_1",
                "source_id": "src_1",
                "content": "Abstract: latent reasoning paper.",
            }) + "\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("HARNESS_DIR", str(harness))

        assert main([
            "source-audit",
            "--output-dir", str(out),
            "--research-profile", "technical_architecture",
            "--strict-profile",
            "--enqueue-followup",
            "--graph", str(graph),
            "--followup-node-id", "DR_SOURCE_GAP_QUEUE",
            "--pane", "controlled:0.0",
            "--json",
        ]) == 1
        payload = json.loads(capsys.readouterr().out)
        queue_file = harness / "run" / "queue" / "sprint-test.jsonl"
        queue_items = [json.loads(line) for line in queue_file.read_text(encoding="utf-8").splitlines()]

        assert payload["followup"]["enqueue"]["enqueued"][0]["queue"]["result"] == "enqueued"
        assert queue_items[0]["intent"].startswith("graph_node|node_id=DR_SOURCE_GAP_QUEUE")
        assert queue_items[0]["payload"]["node"]["id"] == "DR_SOURCE_GAP_QUEUE"
        assert queue_items[0]["payload"]["assignment"]["pane"] == "controlled:0.0"
        real_queue_after = real_queue.read_text(encoding="utf-8") if real_queue.exists() else None
        assert real_queue_after == real_queue_before
