#!/usr/bin/env python3
"""test_mineru_canonical_sources.py — S5 acceptance tests for MinerU canonical papers integration.

Tests:
  1. scan_canonical_papers discovers papers from manifest
  2. Output path is under Knowledge/references
  3. Worker mode is idle/background/rate-limited
  4. No foreground long-running extraction is launched by default
  5. mineru doctor reports canonical papers status
"""
from __future__ import annotations
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Ensure lib is importable
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", str(Path.home() / ".solar" / "harness")))
sys.path.insert(0, str(HARNESS_DIR / "lib"))

from mineru_extract import (
    scan_canonical_papers,
    queue_canonical_papers,
    extract_pdf,
    _slug,
    MANIFEST_JSONL,
    REFERENCES_DIR,
    OBSIDIAN_VAULT,
    K_SOURCES_DIR,
    K_META_DIR,
    QUEUE_FILE,
)


class TestCanonicalPapersScan(unittest.TestCase):
    """Test scan_canonical_papers reads manifest and resolves paper paths."""

    def test_manifest_exists(self):
        """source-manifest.jsonl should exist (S1 prerequisite)."""
        self.assertTrue(MANIFEST_JSONL.exists(), f"manifest missing: {MANIFEST_JSONL}")

    def test_scan_discovers_papers(self):
        """scan_canonical_papers should find papers in manifest."""
        result = scan_canonical_papers(as_json=False)
        self.assertTrue(result.get("ok"), f"scan failed: {result}")
        self.assertGreater(result["total"], 0, "no papers found in manifest")
        # Should have at least some resolvable papers (original fallback)
        self.assertGreater(result["resolvable"], 0,
                           "no resolvable papers — originals should exist in _raw")

    def test_scan_reports_already_extracted(self):
        """scan should report already_extracted count for existing references."""
        result = scan_canonical_papers(as_json=False)
        self.assertIn("already_extracted", result)
        self.assertIsInstance(result["already_extracted"], int)

    def test_papers_have_required_fields(self):
        """Each discovered paper should have sha256, resolved_path, slug."""
        result = scan_canonical_papers(as_json=False)
        if result["papers"]:
            paper = result["papers"][0]
            for field in ("sha256", "resolved_path", "slug", "name",
                          "canonical_path", "original_path", "source_type"):
                self.assertIn(field, paper, f"paper missing field: {field}")
            self.assertIsNotNone(paper["resolved_path"])
            self.assertTrue(Path(paper["resolved_path"]).exists(),
                            f"resolved path does not exist: {paper['resolved_path']}")

    def test_original_fallback_resolution(self):
        """When canonical path doesn't exist, original_path should be used."""
        result = scan_canonical_papers(as_json=False)
        # Given that migration hasn't been applied, most should be original_fallback
        fallback_count = sum(1 for p in result["papers"]
                             if p["source_type"] == "original_fallback")
        self.assertGreater(fallback_count, 0,
                           "expected some papers to resolve via original_fallback")


class TestOutputPathUnderReferences(unittest.TestCase):
    """Test that extraction output goes under Knowledge/references."""

    def test_references_dir_exists(self):
        """Knowledge/references should exist as the extraction target."""
        self.assertTrue(REFERENCES_DIR.exists(), f"references dir missing: {REFERENCES_DIR}")

    def test_slug_resolves_to_references(self):
        """_slug-based ref_dir should be under Knowledge/references."""
        test_pdf = Path("/tmp/test-paper.pdf")
        slug = _slug(test_pdf)
        ref_dir = REFERENCES_DIR / slug
        self.assertTrue(str(ref_dir).startswith(str(OBSIDIAN_VAULT / "references")),
                        f"ref_dir {ref_dir} not under references/")

    def test_extract_pdf_output_path(self):
        """extract_pdf should place output under Knowledge/references/<slug>."""
        # Use the smallest PDF we can find in the manifest for a quick test
        result = scan_canonical_papers(as_json=False)
        if not result["papers"]:
            self.skipTest("no papers available for extraction test")

        # Find smallest paper for fast test
        smallest = min(result["papers"], key=lambda p: p.get("size", float("inf")))
        pdf_path = Path(smallest["resolved_path"])

        # Extract (foreground is ok for this single small test)
        extract_result = extract_pdf(pdf_path, OBSIDIAN_VAULT, as_json=False)
        self.assertTrue(extract_result.get("ok"), f"extraction failed: {extract_result}")

        # Verify output is under references
        ref_dir = extract_result["ref_dir"]
        self.assertTrue(ref_dir.startswith(str(OBSIDIAN_VAULT / "references")),
                        f"output {ref_dir} not under Knowledge/references")

        # Verify index.md exists
        index_md = Path(ref_dir) / "index.md"
        self.assertTrue(index_md.exists(), f"index.md missing in {ref_dir}")

        # Verify provenance frontmatter
        content = index_md.read_text(encoding="utf-8")
        self.assertIn("source_pdf:", content)
        self.assertIn("source_pdf_sha256:", content)
        self.assertIn("extracted_at:", content)


class TestWorkerIdleBackground(unittest.TestCase):
    """Test that extraction worker is idle/background/rate-limited."""

    def test_queue_papers_is_background_only(self):
        """queue_canonical_papers should only queue, not extract."""
        result = queue_canonical_papers(limit=1, as_json=False)
        self.assertTrue(result.get("ok"), f"queue failed: {result}")
        # Should report background mode
        self.assertEqual(result.get("mode"), "idle_background")
        # Should not have any extraction results
        self.assertNotIn("generated_pages", result)
        self.assertNotIn("page_count", result)

    def test_queue_file_location(self):
        """Queue file should be under ~/.solar/queues/."""
        self.assertTrue(str(QUEUE_FILE).endswith("mineru.jsonl"))
        self.assertIn(".solar", str(QUEUE_FILE))

    def test_worker_script_exists_and_idle_guarded(self):
        """mineru_worker.sh should exist and contain idle guard."""
        worker_script = HARNESS_DIR / "lib" / "mineru_worker.sh"
        self.assertTrue(worker_script.exists(), f"worker script missing: {worker_script}")
        content = worker_script.read_text()
        # Should have idle guard
        self.assertIn("is_idle", content)
        self.assertIn("HIDIdleTime", content)
        # Should not run when user is active
        self.assertIn("sleep", content)
        # Should call mineru_extract.py, not do inline extraction
        self.assertIn("mineru_extract.py", content)

    def test_manifest_yaml_declares_idle_mode(self):
        """MinerU plugin manifest should declare idle/background mode."""
        manifest_path = HARNESS_DIR / "plugins" / "mineru" / "manifest.yaml"
        self.assertTrue(manifest_path.exists(), f"manifest missing: {manifest_path}")
        content = manifest_path.read_text()
        self.assertIn("idle", content.lower())
        self.assertIn("background", content.lower() or "idle_only" in content)


class TestNoForegroundBlocking(unittest.TestCase):
    """Test that no foreground long-running extraction is launched by default."""

    def test_queue_papers_returns_immediately(self):
        """queue_papers should return immediately without blocking."""
        import time
        start = time.time()
        result = queue_canonical_papers(limit=5, as_json=False)
        elapsed = time.time() - start
        # Should return in well under 5 seconds (just writes to queue file)
        self.assertLess(elapsed, 5.0, f"queue_papers took {elapsed:.1f}s — seems to be blocking")

    def test_scan_papers_returns_immediately(self):
        """scan_papers should return quickly without blocking."""
        import time
        start = time.time()
        result = scan_canonical_papers(as_json=False)
        elapsed = time.time() - start
        # Scanning manifest should be fast
        self.assertLess(elapsed, 10.0, f"scan_papers took {elapsed:.1f}s — seems to be blocking")

    def test_extract_single_pdf_without_background_flag(self):
        """Single PDF extract should work but is the only allowed foreground path.
        Batch/queue operations must never be foreground."""
        # queue_papers is the batch operation — must be background
        result = queue_canonical_papers(limit=10, as_json=False)
        self.assertEqual(result.get("mode"), "idle_background")


class TestMineruDoctor(unittest.TestCase):
    """Test mineru_doctor reports canonical papers status."""

    def test_doctor_reports_canonical_papers(self):
        """mineru doctor should include canonical_papers section."""
        import subprocess
        r = subprocess.run(
            [sys.executable, str(HARNESS_DIR / "lib" / "mineru_doctor.py"), "--json"],
            capture_output=True, text=True, timeout=30
        )
        # Doctor may exit 1 if venv has issues, but output should still be valid JSON
        try:
            data = json.loads(r.stdout)
        except json.JSONDecodeError:
            self.fail(f"doctor output not valid JSON: {r.stdout[:500]}")

        self.assertIn("canonical_papers", data,
                       "doctor missing canonical_papers section")
        cp = data["canonical_papers"]
        self.assertIn("status", cp)
        self.assertIn("total_in_manifest", cp)

    def test_doctor_canonical_papers_has_counts(self):
        """canonical_papers should report resolvable and extraction counts."""
        import subprocess
        r = subprocess.run(
            [sys.executable, str(HARNESS_DIR / "lib" / "mineru_doctor.py"), "--json"],
            capture_output=True, text=True, timeout=30
        )
        data = json.loads(r.stdout)
        cp = data["canonical_papers"]
        for field in ("total_in_manifest", "resolvable_canonical",
                      "resolvable_original_fallback", "already_extracted"):
            self.assertIn(field, cp, f"canonical_papers missing field: {field}")


if __name__ == "__main__":
    unittest.main()
