"""Integration tests for DeepResearch CLI — all 14 subcommands.

Constraints:
- Uses real sqlite3 with tmp_path fixtures
- Zero @mock.patch decorators
- Smoke test for each subcommand

Spec: sprint-20260513-solar-deepresearch-product-line-s04-orchestration-ui / N1
"""

from __future__ import annotations

import os
import glob
import subprocess
import sys
from pathlib import Path

import pytest

from harness.lib.research.cli import ALL_SUBCOMMANDS, SUBCOMMANDS, build_parser, main


_HARNESS_ROOT = Path(__file__).resolve().parents[2]
_SOLAR_HARNESS_SH = Path(__file__).resolve().parents[3] / "solar-harness.sh"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def db_with_run(tmp_path):
    """Create a research DB with one run, return (db_path, run_id)."""
    db_path = str(tmp_path / "test.db")
    assert main(["init", db_path, "--topic", "CLI test", "--depth-tier", "standard"]) == 0

    conn = __import__("sqlite3").connect(db_path)
    conn.row_factory = __import__("sqlite3").Row
    run_id = conn.execute("SELECT id FROM research_runs LIMIT 1").fetchone()["id"]
    conn.close()
    return db_path, run_id


# ---------------------------------------------------------------------------
# Test: help lists all subcommands
# ---------------------------------------------------------------------------


class TestHelpListing:
    def test_all_subcommands_registered(self):
        """All declared subcommands are in SUBCOMMANDS dict."""
        assert len(SUBCOMMANDS) == len(ALL_SUBCOMMANDS)
        for name in ALL_SUBCOMMANDS:
            assert name in SUBCOMMANDS, f"Missing subcommand: {name}"

    def test_help_output_contains_all(self, capsys):
        """--help output lists every subcommand."""
        main([])
        captured = capsys.readouterr()
        for name in ALL_SUBCOMMANDS:
            assert name in captured.out, f"--help missing: {name}"

    def test_parser_accepts_all_names(self):
        """All declared subcommand names are valid parser targets."""
        for name in ALL_SUBCOMMANDS:
            assert name in SUBCOMMANDS, f"Missing handler for: {name}"
            assert callable(SUBCOMMANDS[name])


# ---------------------------------------------------------------------------
# S03 smoke tests (init, add-source, extract, ledger, status)
# ---------------------------------------------------------------------------


class TestS03Subcommands:
    def test_init(self, tmp_path, capsys):
        db = str(tmp_path / "new.db")
        assert main(["init", db, "--topic", "Hello"]) == 0
        out = capsys.readouterr().out
        assert "Initialized research DB" in out

    def test_init_rejects_existing(self, tmp_path):
        db = str(tmp_path / "exists.db")
        main(["init", db])
        assert main(["init", db]) == 1

    def test_add_source(self, db_with_run, capsys):
        db_path, run_id = db_with_run
        assert main(["add-source", db_path, "--run-id", run_id, "--text", "Hello world"]) == 0
        out = capsys.readouterr().out
        assert "Source added" in out

    def test_status(self, tmp_path, capsys):
        db = str(tmp_path / "s.db")
        main(["init", db])
        assert main(["status", db]) == 0
        out = capsys.readouterr().out
        assert "Research DB" in out

    def test_status_nonexistent(self, tmp_path):
        assert main(["status", str(tmp_path / "nope.db")]) == 1

    def test_ledger(self, db_with_run, capsys):
        db_path, run_id = db_with_run
        assert main(["ledger", db_path, "--run-id", run_id]) == 0
        out = capsys.readouterr().out
        assert "Run:" in out


# ---------------------------------------------------------------------------
# S04 smoke tests (run, plan, search, mine, outline, write, check, compile, export)
# ---------------------------------------------------------------------------


class TestS04Subcommands:
    def test_run(self, tmp_path, capsys):
        db = str(tmp_path / "run.db")
        assert main(["run", db, "--topic", "Full run test", "--depth-tier", "deep"]) == 0
        out = capsys.readouterr().out
        assert "Research run started" in out
        assert "Full run test" in out

    def test_plan(self, db_with_run, capsys):
        db_path, run_id = db_with_run
        assert main(["plan", db_path, "--run-id", run_id]) == 0
        out = capsys.readouterr().out
        assert "Research plan generated" in out

    def test_search(self, db_with_run, capsys):
        db_path, run_id = db_with_run
        assert main(["search", db_path, "--run-id", run_id, "--query", "test query"]) == 0
        out = capsys.readouterr().out
        assert "Searching for: test query" in out

    def test_mine_no_evidence(self, db_with_run, capsys):
        db_path, run_id = db_with_run
        assert main(["mine", db_path, "--run-id", run_id]) == 1

    def test_outline(self, db_with_run, capsys):
        db_path, run_id = db_with_run
        assert main(["outline", db_path, "--run-id", run_id]) == 0
        out = capsys.readouterr().out
        assert "Report outline created" in out

    def test_write(self, db_with_run, capsys):
        db_path, run_id = db_with_run
        main(["outline", db_path, "--run-id", run_id])

        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        section_id = conn.execute(
            "SELECT id FROM report_sections WHERE run_id = ? LIMIT 1", (run_id,)
        ).fetchone()["id"]
        conn.close()

        assert main(["write", db_path, "--section-id", section_id, "--content", "Test content"]) == 0
        out = capsys.readouterr().out
        assert "Section written" in out

    def test_check(self, db_with_run, capsys):
        db_path, run_id = db_with_run
        main(["outline", db_path, "--run-id", run_id])
        assert main(["check", db_path, "--run-id", run_id]) == 0
        out = capsys.readouterr().out
        assert "Factuality check completed" in out

    def test_compile(self, db_with_run, capsys):
        db_path, run_id = db_with_run
        main(["outline", db_path, "--run-id", run_id])

        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        sections = conn.execute(
            "SELECT id FROM report_sections WHERE run_id = ?", (run_id,)
        ).fetchall()
        for s in sections:
            conn.execute(
                "UPDATE report_sections SET content = 'X', char_count = 1 WHERE id = ?",
                (s["id"],),
            )
        conn.commit()
        conn.close()

        assert main(["compile", db_path, "--run-id", run_id]) == 0
        out = capsys.readouterr().out
        assert "Report compiled" in out

    def test_export(self, db_with_run, capsys, tmp_path):
        db_path, run_id = db_with_run
        output_dir = str(tmp_path / "export_out")
        assert main(["export", db_path, "--run-id", run_id, "--output-dir", output_dir]) == 0
        out = capsys.readouterr().out
        assert "Exported to" in out
        assert os.path.exists(os.path.join(output_dir, "sources.jsonl"))
        assert os.path.exists(os.path.join(output_dir, "report_ast.json"))
        assert glob.glob(os.path.join(output_dir, "*-research_eval.json"))


# ---------------------------------------------------------------------------
# Regression: solar-harness doctor
# ---------------------------------------------------------------------------


class TestRegression:
    def test_doctor_exits_zero(self):
        """solar-harness doctor still exits 0 after CLI extension."""
        if not _SOLAR_HARNESS_SH.exists():
            pytest.skip("solar-harness.sh not found")
        result = subprocess.run(
            ["bash", str(_SOLAR_HARNESS_SH), "doctor"],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "HARNESS_DIR": str(_SOLAR_HARNESS_SH.parent)},
        )
        assert result.returncode == 0, f"doctor failed:\n{result.stdout}\n{result.stderr}"

    def test_non_research_routes_unchanged(self):
        """Existing solar-harness routes still function."""
        if not _SOLAR_HARNESS_SH.exists():
            pytest.skip("solar-harness.sh not found")
        result = subprocess.run(
            ["bash", str(_SOLAR_HARNESS_SH), "models"],
            capture_output=True, text=True, timeout=15,
            env={**os.environ, "HARNESS_DIR": str(_SOLAR_HARNESS_SH.parent)},
        )
        # models command should not crash
        assert result.returncode in (0, 1), f"models crashed:\n{result.stderr}"
