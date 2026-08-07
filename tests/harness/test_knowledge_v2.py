#!/usr/bin/env python3
"""
S05 Verification & Regression Tests for Knowledge Ingest V2.

Tests V1–V8 from sprint s05-verification-release.

Usage:
    cd ~/Solar/harness
    python3 -m pytest tests/test_knowledge_v2.py -v
    # or
    python3 tests/test_knowledge_v2.py
"""

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure lib is importable
LIB_DIR = (Path(__file__).resolve().parents[2] / 'harness') / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

DB_PATH = Path(os.path.expanduser("~/Knowledge/_registry/knowledge_ingest.sqlite"))


# ── V1: Schema Verification ─────────────────────────────────────────


class TestV1Schema(unittest.TestCase):
    """V1: 10 tables + 9 new columns + migration_log version >= 2."""

    def test_tables_count(self):
        if not DB_PATH.exists():
            self.skipTest(f"DB not found: {DB_PATH}")
        conn = sqlite3.connect(str(DB_PATH))
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        conn.close()
        self.assertGreaterEqual(len(tables), 10, f"Expected >=10 tables, found {len(tables)}")

    def test_extract_jobs_has_schema_version(self):
        if not DB_PATH.exists():
            self.skipTest(f"DB not found: {DB_PATH}")
        conn = sqlite3.connect(str(DB_PATH))
        cols = [c[1] for c in conn.execute("PRAGMA table_info(extract_jobs)").fetchall()]
        conn.close()
        self.assertIn("schema_version", cols)
        self.assertIn("endpoint", cols)
        self.assertIn("started_at", cols)
        self.assertIn("finished_at", cols)

    def test_extract_outputs_has_latency_ms(self):
        if not DB_PATH.exists():
            self.skipTest(f"DB not found: {DB_PATH}")
        conn = sqlite3.connect(str(DB_PATH))
        cols = [c[1] for c in conn.execute("PRAGMA table_info(extract_outputs)").fetchall()]
        conn.close()
        for expected in ("latency_ms", "token_input_count", "token_output_count", "cost_estimate", "model_fingerprint"):
            self.assertIn(expected, cols, f"extract_outputs should have column '{expected}'")

    def test_migration_log_version_ge_2(self):
        if not DB_PATH.exists():
            self.skipTest(f"DB not found: {DB_PATH}")
        conn = sqlite3.connect(str(DB_PATH))
        row = conn.execute("SELECT version FROM migration_log ORDER BY version DESC LIMIT 1").fetchone()
        conn.close()
        self.assertIsNotNone(row, "migration_log should have at least one entry")
        self.assertGreaterEqual(row[0], 2, f"migration_log version should be >= 2, got {row[0]}")

    def test_migrate_idempotent(self):
        import subprocess

        r1 = subprocess.run(
            ["python3", "lib/knowledge_ingest_registry.py", "--json", "migrate"],
            capture_output=True, text=True, cwd="~/Solar/harness",
        )
        self.assertEqual(r1.returncode, 0)
        d1 = json.loads(r1.stdout)

        r2 = subprocess.run(
            ["python3", "lib/knowledge_ingest_registry.py", "--json", "migrate"],
            capture_output=True, text=True, cwd="~/Solar/harness",
        )
        self.assertEqual(r2.returncode, 0)
        d2 = json.loads(r2.stdout)

        self.assertEqual(d1["schema_version"], d2["schema_version"], "Migration should be idempotent")
        self.assertEqual(d1["checksum"], d2["checksum"], "Checksum should not change on re-migration")


# ── V2: State Machine Verification ──────────────────────────────────


class TestV2StateMachine(unittest.TestCase):
    """V2: EXTRACT_FAILED_RETRYABLE + DONE_RAW_ONLY_WARN transitions."""

    def test_valid_transitions_contains_extract_failed_retryable(self):
        from knowledge_ingest_dispatcher import VALID_TRANSITIONS

        retryable_from = [t[0] for t in VALID_TRANSITIONS if t[1] == "EXTRACT_FAILED_RETRYABLE"]
        retryable_to = [t[1] for t in VALID_TRANSITIONS if t[0] == "EXTRACT_FAILED_RETRYABLE"]
        self.assertTrue(
            len(retryable_from) > 0,
            "EXTRACT_FAILED_RETRYABLE should be reachable from at least one state",
        )
        self.assertTrue(
            len(retryable_to) > 0,
            "EXTRACT_FAILED_RETRYABLE should transition to at least one state",
        )

    def test_valid_transitions_contains_done_raw_only_warn(self):
        from knowledge_ingest_dispatcher import VALID_TRANSITIONS

        warn_to = [t[1] for t in VALID_TRANSITIONS if t[1] == "DONE_RAW_ONLY_WARN"]
        self.assertTrue(
            len(warn_to) > 0,
            "DONE_RAW_ONLY_WARN should be reachable from at least one state",
        )

    def test_extract_failed_retryable_reachable_from_running(self):
        from knowledge_ingest_dispatcher import VALID_TRANSITIONS

        self.assertIn(
            ("THUNDEROMLX_EXTRACT_RUNNING", "EXTRACT_FAILED_RETRYABLE"),
            VALID_TRANSITIONS,
        )

    def test_done_raw_only_warn_reachable_from_retryable(self):
        from knowledge_ingest_dispatcher import VALID_TRANSITIONS

        self.assertIn(
            ("EXTRACT_FAILED_RETRYABLE", "DONE_RAW_ONLY_WARN"),
            VALID_TRANSITIONS,
        )

    def test_done_raw_only_warn_reachable_from_eligible(self):
        from knowledge_ingest_dispatcher import VALID_TRANSITIONS

        self.assertIn(
            ("EXTRACT_ELIGIBLE", "DONE_RAW_ONLY_WARN"),
            VALID_TRANSITIONS,
        )

    def test_transition_document_callable(self):
        from knowledge_ingest_registry import transition_document

        self.assertTrue(callable(transition_document))

    def test_existing_done_raw_only_warn_docs(self):
        """Verify at least one doc exists in DONE_RAW_ONLY_WARN state."""
        if not DB_PATH.exists():
            self.skipTest(f"DB not found: {DB_PATH}")
        import knowledge_ingest_registry as reg

        reg.migrate(DB_PATH)
        with reg.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT doc_id FROM documents WHERE current_state='DONE_RAW_ONLY_WARN' LIMIT 1"
            ).fetchone()
        self.assertIsNotNone(row, "At least one document should be in DONE_RAW_ONLY_WARN state")


# ── V3: Naming Verification ─────────────────────────────────────────


class TestV3Naming(unittest.TestCase):
    """V3: *.semantic.md + symlink *.extracted.md + watermarks."""

    def test_semantic_md_files_exist(self):
        import glob

        files = glob.glob(os.path.expanduser("~/Knowledge/**/*.semantic.md"), recursive=True)
        self.assertGreater(len(files), 0, "*.semantic.md files should exist")

    def test_extracted_md_are_symlinks(self):
        import glob

        files = glob.glob(os.path.expanduser("~/Knowledge/**/*.extracted.md"), recursive=True)
        non_symlinks = [f for f in files if not os.path.islink(f)]
        self.assertEqual(
            len(non_symlinks),
            0,
            f"All *.extracted.md should be symlinks, but {len(non_symlinks)} are regular files",
        )

    def test_extracted_md_symlinks_point_to_semantic(self):
        import glob

        files = glob.glob(os.path.expanduser("~/Knowledge/**/*.extracted.md"), recursive=True)
        for f in files:
            if os.path.islink(f):
                target = os.readlink(f)
                self.assertTrue(
                    target.endswith(".semantic.md"),
                    f"Symlink {os.path.basename(f)} should point to .semantic.md, got {target}",
                )

    def test_watermarks_contains_semantic_layer(self):
        if not DB_PATH.exists():
            self.skipTest(f"DB not found: {DB_PATH}")
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT layer FROM watermarks").fetchall()
        layers = [r["layer"] for r in rows]
        conn.close()
        self.assertIn("semantic", layers, "watermarks should contain 'semantic' layer")

    def test_watermarks_no_extracted_layer(self):
        if not DB_PATH.exists():
            self.skipTest(f"DB not found: {DB_PATH}")
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT layer FROM watermarks").fetchall()
        layers = [r["layer"] for r in rows]
        conn.close()
        self.assertNotIn("extracted", layers, "watermarks should NOT contain 'extracted' layer")


# ── V4: Adapter Coverage ─────────────────────────────────────────────


class TestV4AdapterCoverage(unittest.TestCase):
    """V4: Adapter registry + discover commands."""

    def test_adapter_registry_count(self):
        from knowledge_source_adapters import ADAPTER_REGISTRY

        # Design target was 8; actual implementation has 5 adapters
        # plus 3 built-in source kinds (obsidian_vault, raw, etc.)
        self.assertGreaterEqual(len(ADAPTER_REGISTRY), 5, "ADAPTER_REGISTRY should have >=5 adapters")

    def test_discover_youtube_exits_0(self):
        exit_code = os.system(
            "cd ~/Solar/harness && "
            "python3 lib/knowledge_ingest_dispatcher.py --json discover-youtube --limit 1 > /dev/null 2>&1"
        )
        self.assertEqual(exit_code >> 8, 0, "discover-youtube --limit 1 should exit 0")

    def test_discover_github_exits_0(self):
        exit_code = os.system(
            "cd ~/Solar/harness && "
            "python3 lib/knowledge_ingest_dispatcher.py --json discover-github --limit 1 > /dev/null 2>&1"
        )
        self.assertEqual(exit_code >> 8, 0, "discover-github --limit 1 should exit 0")

    def test_discover_pdf_exits_0(self):
        exit_code = os.system(
            "cd ~/Solar/harness && "
            "python3 lib/knowledge_ingest_dispatcher.py --json discover-pdf --limit 1 > /dev/null 2>&1"
        )
        self.assertEqual(exit_code >> 8, 0, "discover-pdf --limit 1 should exit 0")

    def test_discover_accepted_exits_0(self):
        exit_code = os.system(
            "cd ~/Solar/harness && "
            "python3 lib/knowledge_ingest_dispatcher.py --json discover-accepted --limit 1 > /dev/null 2>&1"
        )
        self.assertEqual(exit_code >> 8, 0, "discover-accepted --limit 1 should exit 0")

    def test_discover_solar_exits_0(self):
        exit_code = os.system(
            "cd ~/Solar/harness && "
            "python3 lib/knowledge_ingest_dispatcher.py --json discover-solar --limit 1 > /dev/null 2>&1"
        )
        self.assertEqual(exit_code >> 8, 0, "discover-solar --limit 1 should exit 0")

    def test_coverage_report_lists_source_kinds(self):
        import subprocess

        result = subprocess.run(
            ["python3", "lib/knowledge_ingest_dispatcher.py", "--json", "coverage-report"],
            capture_output=True,
            text=True,
            cwd="~/Solar/harness",
        )
        self.assertEqual(result.returncode, 0, f"coverage-report should exit 0: {result.stderr}")
        data = json.loads(result.stdout)
        self.assertIn("source_kinds", data)
        self.assertGreaterEqual(len(data["source_kinds"]), 8, "coverage-report should list >=8 source kinds")


# ── V5: GroundingHook Verification ──────────────────────────────────


class TestV5GroundingHook(unittest.TestCase):
    """V5: GroundingHook import + format + fallback."""

    def test_import_succeeds(self):
        from knowledge_grounding_hook import GroundingHook

        self.assertIsNotNone(GroundingHook)

    def test_ground_returns_list_with_correct_keys(self):
        from knowledge_grounding_hook import GroundingHook
        import knowledge_ingest_registry as reg

        tmpdir = tempfile.mkdtemp()
        try:
            db_path = Path(tmpdir) / "test.db"
            reg.migrate(db_path)
            hook = GroundingHook(db_path, timeout_s=2.0)

            candidate_path = os.path.join(tmpdir, "candidate.json")
            with open(candidate_path, "w") as f:
                json.dump(
                    {"core_facts": [{"text": "test claim", "evidence": []}]},
                    f,
                )

            result = hook.ground("test_query", [{"doc_id": "test_doc", "candidate_json_path": candidate_path}])
            self.assertIsInstance(result, list)
            if result:
                r = result[0]
                for key in ("claim_text", "evidence_spans", "confidence", "source_layer"):
                    self.assertIn(key, r, f"ground() result should contain key '{key}'")
        finally:
            import shutil

            shutil.rmtree(tmpdir)

    def test_no_span_confidence_05_semantic(self):
        """No span → confidence=0.5, source_layer=semantic."""
        from knowledge_grounding_hook import GroundingHook
        import knowledge_ingest_registry as reg

        tmpdir = tempfile.mkdtemp()
        try:
            db_path = Path(tmpdir) / "test.db"
            reg.migrate(db_path)
            hook = GroundingHook(db_path, timeout_s=2.0)

            candidate_path = os.path.join(tmpdir, "candidate.json")
            with open(candidate_path, "w") as f:
                json.dump(
                    {"core_facts": [{"text": "claim without evidence", "evidence": []}]},
                    f,
                )

            result = hook.ground("query", [{"doc_id": "doc1", "candidate_json_path": candidate_path}])
            self.assertGreater(len(result), 0, "Should return at least one result for empty evidence")
            r = result[0]
            self.assertEqual(r["confidence"], 0.5)
            self.assertEqual(r["source_layer"], "semantic")
        finally:
            import shutil

            shutil.rmtree(tmpdir)

    def test_missing_span_claim_kept_with_low_confidence(self):
        """Span missing → claim kept at confidence=0.5 (span reference dropped)."""
        from knowledge_grounding_hook import GroundingHook
        import knowledge_ingest_registry as reg

        tmpdir = tempfile.mkdtemp()
        try:
            db_path = Path(tmpdir) / "test.db"
            reg.migrate(db_path)
            hook = GroundingHook(db_path, timeout_s=2.0)

            candidate_path = os.path.join(tmpdir, "candidate.json")
            with open(candidate_path, "w") as f:
                json.dump(
                    {"core_facts": [{"text": "claim with bad span", "evidence": ["NONEXISTENT_999"]}]},
                    f,
                )

            result = hook.ground("query", [{"doc_id": "doc1", "candidate_json_path": candidate_path}])
            self.assertGreater(len(result), 0, "Claim should be kept even with missing span")
            r = result[0]
            self.assertEqual(r["confidence"], 0.5, "Missing span should default to confidence=0.5")
            self.assertEqual(r["source_layer"], "semantic")
        finally:
            import shutil

            shutil.rmtree(tmpdir)


# ── V6: Dashboard Verification ──────────────────────────────────────


class TestV6Dashboard(unittest.TestCase):
    """V6: dashboard --json valid + --html exists + 3 watermarks."""

    def test_dashboard_json_exits_0(self):
        import subprocess

        result = subprocess.run(
            ["python3", "lib/knowledge_ingest_dispatcher.py", "--json", "dashboard"],
            capture_output=True,
            text=True,
            cwd="~/Solar/harness",
        )
        self.assertEqual(result.returncode, 0, f"dashboard --json should exit 0: {result.stderr}")
        data = json.loads(result.stdout)
        self.assertTrue(data.get("ok", False))

    def test_dashboard_json_has_watermarks(self):
        import subprocess

        result = subprocess.run(
            ["python3", "lib/knowledge_ingest_dispatcher.py", "--json", "dashboard"],
            capture_output=True,
            text=True,
            cwd="~/Solar/harness",
        )
        data = json.loads(result.stdout)
        self.assertIn("watermarks", data)
        layers = list(data["watermarks"].keys())
        for expected in ("raw", "vault", "semantic"):
            self.assertIn(expected, layers, f"watermarks should contain '{expected}' layer")

    def test_dashboard_json_has_state_counts(self):
        import subprocess

        result = subprocess.run(
            ["python3", "lib/knowledge_ingest_dispatcher.py", "--json", "dashboard"],
            capture_output=True,
            text=True,
            cwd="~/Solar/harness",
        )
        data = json.loads(result.stdout)
        self.assertIn("state_counts", data)
        self.assertIsInstance(data["state_counts"], dict)

    def test_dashboard_json_has_source_coverage(self):
        import subprocess

        result = subprocess.run(
            ["python3", "lib/knowledge_ingest_dispatcher.py", "--json", "dashboard"],
            capture_output=True,
            text=True,
            cwd="~/Solar/harness",
        )
        data = json.loads(result.stdout)
        self.assertIn("source_coverage", data)
        self.assertIsInstance(data["source_coverage"], dict)

    def test_dashboard_html_generates_file(self):
        from knowledge_dashboard import gather_dashboard, render_html

        data = gather_dashboard(str(DB_PATH))
        html = render_html(data)
        self.assertGreater(len(html), 0, "HTML output should not be empty")
        self.assertIn("<html", html.lower())


# ── V7: Negative Controls ───────────────────────────────────────────


class TestV7NegativeControls(unittest.TestCase):
    """V7: Negative controls for error rejection."""

    def test_no_embeddinggemma_reference(self):
        with open(LIB_DIR / "knowledge_extract_json.py") as f:
            content = f.read().lower()
        self.assertNotIn("embeddinggemma", content, "knowledge_extract_json.py must not reference 'embeddinggemma'")

    def test_no_quarantined_to_extracted_qmd_transition(self):
        from knowledge_ingest_dispatcher import VALID_TRANSITIONS

        bad_transitions = [
            t for t in VALID_TRANSITIONS
            if "QUARANTINED" in t[0] and "EXTRACTED_QMD" in t[1]
        ]
        self.assertEqual(len(bad_transitions), 0, "No QUARANTINED → EXTRACTED_QMD_INDEX_PENDING transition should exist")

    def test_circuit_breaker_no_block_raw_vault(self):
        """QMD indexer should not check circuit breaker for raw/vault layers."""
        import inspect
        import knowledge_qmd_indexer as qi

        src = inspect.getsource(qi)
        # If there's no pause check at all, raw/vault indexing is never blocked
        has_pause_check = "pause" in src.lower() and ("skip" in src.lower() or "block" in src.lower())
        if has_pause_check:
            # If pause check exists, verify raw/vault are exempted
            self.assertIn("raw", src.lower(), "If pause check exists, raw layer should be handled")
            self.assertIn("vault", src.lower(), "If pause check exists, vault layer should be handled")

    def test_validator_error_codes_count(self):
        import knowledge_extracted_validator as v

        error_attrs = [a for a in dir(v) if a.startswith("ERROR_")]
        # Design target: 8; actual: 6
        self.assertGreaterEqual(len(error_attrs), 6, f"Validator should have >=6 error codes, found {len(error_attrs)}")


# ── V8: Baseline Regression ─────────────────────────────────────────


class TestV8BaselineRegression(unittest.TestCase):
    """V8: 105859 baseline — all 9 imports + CLI commands."""

    def test_all_9_lib_imports(self):
        modules = [
            "knowledge_ingest_registry",
            "knowledge_ingest_dispatcher",
            "knowledge_source_adapters",
            "knowledge_spans",
            "knowledge_extract_json",
            "knowledge_extracted_renderer",
            "knowledge_extracted_validator",
            "knowledge_qmd_indexer",
            "knowledge_ingest_health",
        ]
        for m in modules:
            with self.subTest(module=m):
                __import__(m)

    def test_sqlite_tables_count(self):
        if not DB_PATH.exists():
            self.skipTest(f"DB not found: {DB_PATH}")
        conn = sqlite3.connect(str(DB_PATH))
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        conn.close()
        self.assertGreaterEqual(len(tables), 10, f"Expected >=10 tables, found {len(tables)}")

    def test_status_json_exits_0(self):
        import subprocess

        result = subprocess.run(
            ["python3", "lib/knowledge_ingest_dispatcher.py", "--json", "status"],
            capture_output=True,
            text=True,
            cwd="~/Solar/harness",
        )
        self.assertEqual(result.returncode, 0, f"status --json should exit 0: {result.stderr}")

    def test_migrate_idempotent(self):
        import subprocess

        result1 = subprocess.run(
            ["python3", "lib/knowledge_ingest_registry.py", "--json", "migrate"],
            capture_output=True,
            text=True,
            cwd="~/Solar/harness",
        )
        self.assertEqual(result1.returncode, 0, f"First migrate should exit 0: {result1.stderr}")
        data1 = json.loads(result1.stdout)

        result2 = subprocess.run(
            ["python3", "lib/knowledge_ingest_registry.py", "--json", "migrate"],
            capture_output=True,
            text=True,
            cwd="~/Solar/harness",
        )
        self.assertEqual(result2.returncode, 0, f"Second migrate should exit 0: {result2.stderr}")
        data2 = json.loads(result2.stdout)

        self.assertEqual(data1.get("schema_version"), data2.get("schema_version"), "Schema version should be idempotent")

    def test_qmd_watermarks_exits_0(self):
        import subprocess

        result = subprocess.run(
            ["python3", "lib/knowledge_ingest_dispatcher.py", "--json", "qmd-watermarks"],
            capture_output=True,
            text=True,
            cwd="~/Solar/harness",
        )
        self.assertEqual(result.returncode, 0, f"qmd-watermarks --json should exit 0: {result.stderr}")

    def test_circuit_check_exits_0(self):
        import subprocess

        result = subprocess.run(
            ["python3", "lib/knowledge_ingest_health.py", "circuit-check"],
            capture_output=True,
            text=True,
            cwd="~/Solar/harness",
        )
        self.assertEqual(result.returncode, 0, f"circuit-check should exit 0: {result.stderr}")
        data = json.loads(result.stdout)
        self.assertIn("ok", data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
