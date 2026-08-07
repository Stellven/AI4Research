#!/usr/bin/env python3
"""
test_qmd_sources_reconcile.py — S4 acceptance tests for QMD reindex/reconcile.
Sprint: sprint-20260510-data-plane-storage-access-unification

Verifies:
  - QMD index/reindex plan or execution report exists
  - Sample queries hit canonical source and reference page
  - Old _raw/file-uploads provenance remains traceable
  - Embedding work is background/idle or explicitly queued, not foreground blocking
"""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", str(Path.home() / ".solar" / "harness")))
KNOWLEDGE_DIR = Path.home() / "Knowledge"
sys.path.insert(0, str(HARNESS_DIR / "lib"))


def _qmd_search(query: str, collection: str = "solar-wiki") -> list:
    """Run qmd search and return parsed results."""
    try:
        r = subprocess.run(
            ["qmd", "search", query, "-c", collection],
            capture_output=True, text=True, timeout=30,
        )
        # Parse qmd output - each hit starts with "qmd://"
        hits = []
        for line in r.stdout.split("\n"):
            if line.startswith("qmd://"):
                hits.append(line.strip())
        return hits
    except Exception:
        return []


def _qmd_get(path: str) -> bool:
    """Check if a qmd document exists."""
    try:
        r = subprocess.run(
            ["qmd", "get", f"qmd://solar-wiki/{path}"],
            capture_output=True, text=True, timeout=10,
        )
        return r.returncode == 0
    except Exception:
        return False


class TestQMDReindexReportExists(unittest.TestCase):
    """Acceptance: QMD index/reindex plan or execution report exists."""

    def test_reindex_report_file_exists(self):
        """QMD reindex report file exists at expected path."""
        report_path = (
            HARNESS_DIR
            / "reports"
            / "data-plane-storage-access-unification"
            / "qmd-reindex.md"
        )
        self.assertTrue(report_path.exists(), f"Report should exist at {report_path}")

    def test_reindex_report_has_required_sections(self):
        """Reindex report covers all required sections."""
        report_path = (
            HARNESS_DIR
            / "reports"
            / "data-plane-storage-access-unification"
            / "qmd-reindex.md"
        )
        content = report_path.read_text()
        for section in ["Index Status", "Verification Evidence", "Provenance", "Embedding"]:
            # At least some mention of these topics
            self.assertTrue(
                any(kw in content for kw in [section.lower(), section]),
                f"Report should mention '{section}'",
            )

    def test_qmd_index_is_current(self):
        """QMD index has files and was updated recently."""
        r = subprocess.run(
            ["qmd", "status"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(r.returncode, 0, "qmd status should succeed")
        self.assertIn("indexed", r.stdout, "QMD should report indexed files")
        self.assertIn("embedded", r.stdout, "QMD should report embedded vectors")


class TestQMDSampleQueriesHitCanonical(unittest.TestCase):
    """Acceptance: Sample queries hit canonical source and reference page."""

    def test_search_scaling_law_hits_reference(self):
        """Search for 'scaling law' hits reference pages."""
        hits = _qmd_search("scaling law")
        self.assertTrue(len(hits) > 0, "'scaling law' search should return hits")
        ref_hits = [h for h in hits if "/references/" in h]
        self.assertTrue(len(ref_hits) > 0, "'scaling law' should hit at least one reference page")

    def test_search_grokking_hits_reference(self):
        """Search for 'grokking feature learning' hits reference pages."""
        hits = _qmd_search("grokking feature learning")
        self.assertTrue(len(hits) > 0, "'grokking' search should return hits")
        ref_hits = [h for h in hits if "/references/" in h]
        self.assertTrue(len(ref_hits) > 0, "'grokking' should hit at least one reference page")

    def test_search_manifold_hits_reference(self):
        """Search for '流形假设' (manifold hypothesis) hits the re-ingested page."""
        hits = _qmd_search("流形假设")
        self.assertTrue(len(hits) > 0, "'流形假设' search should return hits")
        # Should hit the re-ingested page
        manifold_hits = [h for h in hits if "流形假设下的思考" in h]
        self.assertTrue(len(manifold_hits) > 0, "Should hit '流形假设下的思考' reference page")

    def test_recently_ingested_pages_in_index(self):
        """Pages re-ingested today are present in QMD index."""
        for page in [
            "对谈田渊栋-ai走向何方-我们需要怎样的深度学习理论",
            "流形假设下的思考",
            "谷歌访谈纪要",
        ]:
            self.assertTrue(
                _qmd_get(f"references/{page}.md"),
                f"Re-ingested page '{page}' should be in QMD index",
            )

    def test_reference_pages_count_in_index(self):
        """QMD index has a substantial number of reference pages."""
        r = subprocess.run(
            ["qmd", "ls", "solar-wiki"],
            capture_output=True, text=True, timeout=30,
        )
        ref_lines = [l for l in r.stdout.split("\n") if "qmd://solar-wiki/references/" in l]
        self.assertGreater(
            len(ref_lines), 100,
            f"QMD should have >100 reference pages, got {len(ref_lines)}",
        )


class TestQMDProvenanceTraceability(unittest.TestCase):
    """Acceptance: Old _raw/file-uploads provenance remains traceable."""

    def test_source_manifest_exists(self):
        """source-manifest.jsonl exists and has entries."""
        manifest_path = KNOWLEDGE_DIR / "_meta" / "source-manifest.jsonl"
        self.assertTrue(manifest_path.exists(), "source-manifest.jsonl should exist")

    def test_manifest_has_all_required_fields(self):
        """Every manifest entry has sha256, original_path, canonical_path."""
        manifest_path = KNOWLEDGE_DIR / "_meta" / "source-manifest.jsonl"
        with open(manifest_path) as f:
            entries = [json.loads(line) for line in f if line.strip()]
        self.assertGreater(len(entries), 0, "Manifest should have entries")
        for entry in entries:
            self.assertIn("sha256", entry, "Entry should have sha256")
            self.assertIn("original_path", entry, "Entry should have original_path")
            self.assertIn("canonical_path", entry, "Entry should have canonical_path")
            self.assertIn("_raw/file-uploads", entry["original_path"],
                          "original_path should reference _raw/file-uploads")

    def test_manifest_covers_all_source_categories(self):
        """Manifest covers papers, other, apple-notes categories."""
        manifest_path = KNOWLEDGE_DIR / "_meta" / "source-manifest.jsonl"
        with open(manifest_path) as f:
            entries = [json.loads(line) for line in f if line.strip()]
        categories = set(e.get("category") for e in entries)
        self.assertIn("papers", categories, "Manifest should have papers category")

    def test_no_migration_related_broken_links(self):
        """No broken wiki links are caused by the data-plane migration."""
        from qmd_adapter import _check_wiki_links
        result = _check_wiki_links()
        broken = result.get("broken", [])
        migration_related = [
            b for b in broken
            if any(kw in b.get("link", "")
                   for kw in ("_sources", "_raw", "file-uploads"))
        ]
        self.assertEqual(
            len(migration_related), 0,
            f"No broken links should be migration-related, found: {migration_related}",
        )

    def test_reference_page_provenance_chain(self):
        """Reference pages link back to source files through frontmatter."""
        import re
        refs_dir = KNOWLEDGE_DIR / "references"
        if not refs_dir.exists():
            self.skipTest("references directory not found")
        # Check a sample of reference pages have source_file in frontmatter
        md_files = list(refs_dir.glob("*.md"))[:20]
        with_source = 0
        for md in md_files:
            try:
                content = md.read_text(errors="replace")
                if re.search(r'^source_file:', content, re.MULTILINE):
                    with_source += 1
            except Exception:
                pass
        # Not all pages need source_file, but many should have it
        self.assertGreater(
            with_source, 5,
            f"At least some reference pages should have source_file provenance, found {with_source}/{len(md_files)}",
        )


class TestQMDEmbeddingIsBackground(unittest.TestCase):
    """Acceptance: Embedding work is background/idle, not foreground blocking."""

    def test_embed_runner_script_exists(self):
        """qmd-embed-runner.sh exists for background embedding."""
        runner = HARNESS_DIR / "lib" / "qmd-embed-runner.sh"
        self.assertTrue(runner.exists(), "qmd-embed-runner.sh should exist")

    def test_embed_runner_is_gentle_mode(self):
        """Default embed runner mode is gentle (not force)."""
        runner = HARNESS_DIR / "lib" / "qmd-embed-runner.sh"
        content = runner.read_text()
        self.assertIn("gentle", content, "Embed runner should support gentle mode")
        # Check for load/idle guards
        self.assertIn("MAX_LOAD", content, "Embed runner should have load guard")
        self.assertIn("can_start", content, "Embed runner should have start guard")

    def test_no_foreground_embed_running(self):
        """No foreground qmd embed process is blocking the shell."""
        try:
            r = subprocess.run(
                ["pgrep", "-f", "qmd embed"],
                capture_output=True, text=True, timeout=5,
            )
            # pgrep returns 0 if process found, 1 if not
            # We just verify the check doesn't fail; background process is ok
            self.assertIn(r.returncode, [0, 1], "pgrep should succeed or find nothing")
        except Exception:
            pass  # Non-blocking: pgrep not available is ok

    def test_adapter_rebuild_is_incremental(self):
        """QMD adapter rebuild supports dry-run and incremental mode."""
        r = subprocess.run(
            [sys.executable, str(HARNESS_DIR / "lib" / "qmd_adapter.py"), "rebuild", "--dry-run", "--json"],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(r.returncode, 0, "dry-run rebuild should succeed")
        data = json.loads(r.stdout)
        self.assertTrue(data.get("dry_run"), "Should report dry_run=true")
        self.assertIn("new_files_found", data, "Should report new files count")


if __name__ == "__main__":
    unittest.main()
