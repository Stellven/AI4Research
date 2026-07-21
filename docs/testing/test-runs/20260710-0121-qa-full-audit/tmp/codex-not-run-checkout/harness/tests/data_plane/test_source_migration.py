#!/usr/bin/env python3
"""test_source_migration.py — S2 tests: safe migration with dry-run, copy, link, alias, checksum.

All tests use temp directories; no real _raw/file-uploads or _sources needed.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Add harness lib to path
HARNESS_LIB = Path(__file__).resolve().parent.parent.parent / "lib"
sys.path.insert(0, str(HARNESS_LIB))

from source_migration import (
    apply_migration,
    load_manifest,
    plan_migration,
    verify_migration,
    _sha256,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def migration_env(tmp_path):
    """Create a complete test environment with fake _raw files and manifest."""
    raw_dir = tmp_path / "_raw" / "file-uploads"
    sources_dir = tmp_path / "_sources"
    meta_dir = tmp_path / "_meta"

    # Create category dirs
    for cat in ("papers", "webpages", "apple-notes", "chatgpt", "other"):
        (sources_dir / cat).mkdir(parents=True)

    # Create fake raw files
    raw_dir.mkdir(parents=True)
    meta_dir.mkdir(parents=True)

    files = {
        "20260507-paper1.pdf": b"PDF content paper 1 " * 100,
        "20260507-paper2.pdf": b"PDF content paper 2 " * 200,
        "20260508-notes.md": b"# Notes\nSome markdown notes.",
        "20260508-data.jsonl": b'{"key": "value1"}\n{"key": "value2"}\n',
        "20260508-article.html": b"<html><body>Article</body></html>",
    }

    entries = []
    for fname, content in files.items():
        fpath = raw_dir / fname
        fpath.write_bytes(content)
        sha = hashlib.sha256(content).hexdigest()
        size = len(content)

        # Determine category
        ext = Path(fname).suffix.lower()
        cat_map = {".pdf": "papers", ".html": "webpages", ".md": "other", ".jsonl": "other"}
        category = cat_map.get(ext, "other")
        prefix = sha[:2]

        canonical = sources_dir / category / prefix / sha / fname
        entries.append({
            "sha256": sha,
            "size": size,
            "original_path": str(fpath),
            "canonical_path": str(canonical),
            "media_type": "application/octet-stream",
            "category": category,
            "status": "indexed",
        })

    # Write manifest
    manifest_path = meta_dir / "source-manifest.jsonl"
    with open(manifest_path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")

    return {
        "tmp": tmp_path,
        "raw_dir": raw_dir,
        "sources_dir": sources_dir,
        "meta_dir": meta_dir,
        "manifest_path": manifest_path,
        "entries": entries,
    }


# ---------------------------------------------------------------------------
# Test: dry-run shows planned paths without writing
# ---------------------------------------------------------------------------

class TestDryRun:
    """dry-run shows planned canonical paths without writing."""

    def test_plan_no_files_written(self, migration_env):
        """plan_migration does not create any files."""
        env = migration_env
        entries = load_manifest(env["manifest_path"])
        result = plan_migration(entries, mode="copy", sources_dir=env["sources_dir"])

        assert result["ok"] is True
        assert result["planned_actions"] == 5
        assert result["skipped"] == 0

        # Verify no files created in _sources
        for entry in entries:
            assert not Path(entry["canonical_path"]).exists(), \
                f"dry-run should not create {entry['canonical_path']}"

    def test_plan_shows_canonical_paths(self, migration_env):
        """Plan output includes all canonical paths."""
        env = migration_env
        entries = load_manifest(env["manifest_path"])
        result = plan_migration(entries, mode="copy", sources_dir=env["sources_dir"])

        planned_paths = [a["canonical_path"] for a in result["actions"]]
        for entry in entries:
            assert entry["canonical_path"] in planned_paths

    def test_plan_shows_mode(self, migration_env):
        """Plan output reflects the selected mode."""
        env = migration_env
        entries = load_manifest(env["manifest_path"])

        result_copy = plan_migration(entries, mode="copy", sources_dir=env["sources_dir"])
        assert result_copy["mode"] == "copy"

        result_link = plan_migration(entries, mode="link", sources_dir=env["sources_dir"])
        assert result_link["mode"] == "link"

    def test_plan_skips_already_migrated(self, migration_env):
        """Plan skips files whose canonical_path already exists with matching checksum."""
        env = migration_env
        entries = load_manifest(env["manifest_path"])

        # Pre-create one canonical file
        first = entries[0]
        Path(first["canonical_path"]).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(first["original_path"], first["canonical_path"])

        result = plan_migration(entries, mode="copy", sources_dir=env["sources_dir"])
        assert result["skipped"] == 1
        assert result["planned_actions"] == 4


# ---------------------------------------------------------------------------
# Test: apply mode copies but never deletes originals
# ---------------------------------------------------------------------------

class TestApplyCopy:
    """apply mode copies files but never deletes original _raw files."""

    def test_copy_creates_canonical_files(self, migration_env):
        """Copy mode creates files at canonical paths."""
        env = migration_env
        entries = load_manifest(env["manifest_path"])
        result = apply_migration(entries, mode="copy",
                                 sources_dir=env["sources_dir"],
                                 manifest_path=env["manifest_path"])

        assert result["ok"] is True
        assert result["succeeded"] == 5
        assert result["failed"] == 0

        for entry in entries:
            assert Path(entry["canonical_path"]).exists(), \
                f"Expected canonical file at {entry['canonical_path']}"

    def test_originals_never_deleted(self, migration_env):
        """Original _raw files are never deleted after copy."""
        env = migration_env
        entries = load_manifest(env["manifest_path"])

        # Record original file sizes
        original_sizes = {}
        for entry in entries:
            orig = Path(entry["original_path"])
            original_sizes[str(orig)] = orig.stat().st_size

        apply_migration(entries, mode="copy",
                        sources_dir=env["sources_dir"],
                        manifest_path=env["manifest_path"])

        # Verify all originals still exist with same size
        for entry in entries:
            orig = Path(entry["original_path"])
            assert orig.exists(), f"Original was deleted: {orig}"
            assert orig.stat().st_size == original_sizes[str(orig)]

    def test_copy_preserves_content(self, migration_env):
        """Copied files have identical content to originals."""
        env = migration_env
        entries = load_manifest(env["manifest_path"])

        apply_migration(entries, mode="copy",
                        sources_dir=env["sources_dir"],
                        manifest_path=env["manifest_path"])

        for entry in entries:
            orig_content = Path(entry["original_path"]).read_bytes()
            canon_content = Path(entry["canonical_path"]).read_bytes()
            assert orig_content == canon_content, \
                f"Content mismatch for {entry['canonical_path']}"

    def test_copy_idempotent(self, migration_env):
        """Running apply twice succeeds and does not duplicate or corrupt."""
        env = migration_env
        entries = load_manifest(env["manifest_path"])

        # First apply
        r1 = apply_migration(entries, mode="copy",
                             sources_dir=env["sources_dir"],
                             manifest_path=env["manifest_path"])
        assert r1["succeeded"] == 5

        # Reload manifest (it was updated)
        entries2 = load_manifest(env["manifest_path"])
        r2 = apply_migration(entries2, mode="copy",
                             sources_dir=env["sources_dir"],
                             manifest_path=env["manifest_path"])
        assert r2["succeeded"] == 0  # all already done
        assert r2["skipped"] == 5


# ---------------------------------------------------------------------------
# Test: link mode
# ---------------------------------------------------------------------------

class TestApplyLink:
    """apply mode with link creates symlinks without moving originals."""

    def test_link_creates_symlinks(self, migration_env):
        """Link mode creates symlinks at canonical paths pointing to originals."""
        env = migration_env
        entries = load_manifest(env["manifest_path"])
        result = apply_migration(entries, mode="link",
                                 sources_dir=env["sources_dir"],
                                 manifest_path=env["manifest_path"])

        assert result["ok"] is True
        assert result["succeeded"] == 5

        for entry in entries:
            canon = Path(entry["canonical_path"])
            assert canon.exists()
            assert os.path.islink(str(canon)), f"Expected symlink at {canon}"

    def test_link_originals_still_exist(self, migration_env):
        """Link mode does not touch original files."""
        env = migration_env
        entries = load_manifest(env["manifest_path"])

        apply_migration(entries, mode="link",
                        sources_dir=env["sources_dir"],
                        manifest_path=env["manifest_path"])

        for entry in entries:
            assert Path(entry["original_path"]).exists()


# ---------------------------------------------------------------------------
# Test: alias preservation (original_path resolvable)
# ---------------------------------------------------------------------------

class TestAliasPreservation:
    """old original_path remains resolvable through alias or symlink."""

    def test_alias_link_created_on_copy(self, migration_env):
        """Copy mode creates .canonical symlink next to original for backward compat."""
        env = migration_env
        entries = load_manifest(env["manifest_path"])
        result = apply_migration(entries, mode="copy",
                                 sources_dir=env["sources_dir"],
                                 manifest_path=env["manifest_path"])

        alias_links = [r for r in result["results"] if r.get("alias_link")]
        assert len(alias_links) == 5, f"Expected 5 alias links, got {len(alias_links)}"

        # Each alias link should resolve to the canonical file
        for r in alias_links:
            alias = Path(r["alias_link"])
            assert alias.exists(), f"Alias link missing: {alias}"
            target = os.readlink(str(alias))
            assert r["canonical_path"] in target or Path(target).name == Path(r["canonical_path"]).name

    def test_manifest_updated_with_migration_status(self, migration_env):
        """After apply, manifest entries have status=migrated and migration_mode."""
        env = migration_env
        entries = load_manifest(env["manifest_path"])

        apply_migration(entries, mode="copy",
                        sources_dir=env["sources_dir"],
                        manifest_path=env["manifest_path"])

        updated = load_manifest(env["manifest_path"])
        for entry in updated:
            assert entry.get("status") == "migrated"
            assert entry.get("migration_mode") == "copy"
            assert "migrated_at" in entry


# ---------------------------------------------------------------------------
# Test: checksum verification after copy/link
# ---------------------------------------------------------------------------

class TestChecksumVerification:
    """checksum verified after copy/link."""

    def test_verify_after_copy(self, migration_env):
        """verify_migration confirms all checksums match after copy."""
        env = migration_env
        entries = load_manifest(env["manifest_path"])

        apply_migration(entries, mode="copy",
                        sources_dir=env["sources_dir"],
                        manifest_path=env["manifest_path"])

        # Reload after manifest update
        updated = load_manifest(env["manifest_path"])
        result = verify_migration(updated, sources_dir=env["sources_dir"])

        assert result["ok"] is True
        assert result["verified"] == 5
        assert result["failed"] == 0

    def test_verify_after_link(self, migration_env):
        """verify_migration confirms all checksums match after link."""
        env = migration_env
        entries = load_manifest(env["manifest_path"])

        apply_migration(entries, mode="link",
                        sources_dir=env["sources_dir"],
                        manifest_path=env["manifest_path"])

        updated = load_manifest(env["manifest_path"])
        result = verify_migration(updated, sources_dir=env["sources_dir"])

        assert result["ok"] is True
        assert result["verified"] == 5

    def test_verify_detects_corruption(self, migration_env):
        """verify_migration detects a corrupted file."""
        env = migration_env
        entries = load_manifest(env["manifest_path"])

        apply_migration(entries, mode="copy",
                        sources_dir=env["sources_dir"],
                        manifest_path=env["manifest_path"])

        # Corrupt one file
        first_canonical = Path(entries[0]["canonical_path"])
        first_canonical.write_bytes(b"CORRUPTED")

        updated = load_manifest(env["manifest_path"])
        result = verify_migration(updated, sources_dir=env["sources_dir"])

        assert result["ok"] is False
        assert result["failed"] == 1
        assert result["verified"] == 4

    def test_verify_before_migration(self, migration_env):
        """verify_migration reports not_migrated before any apply."""
        env = migration_env
        entries = load_manifest(env["manifest_path"])
        result = verify_migration(entries, sources_dir=env["sources_dir"])

        assert result["not_migrated"] == 5
        assert result["verified"] == 0

    def test_checksum_mismatch_on_copy_detected(self, migration_env, monkeypatch):
        """If copy produces wrong checksum, migration reports failure."""
        env = migration_env
        entries = load_manifest(env["manifest_path"])

        # Patch shutil.copy2 to write garbage
        original_copy2 = shutil.copy2
        def bad_copy(src, dst):
            # Do the real copy, then overwrite with garbage
            original_copy2(src, dst)
            Path(dst).write_bytes(b"BADCOPY")

        monkeypatch.setattr(shutil, "copy2", bad_copy)

        result = apply_migration(entries, mode="copy",
                                 sources_dir=env["sources_dir"],
                                 manifest_path=None)  # don't update manifest

        assert result["ok"] is False
        assert result["failed"] == 5


# ---------------------------------------------------------------------------
# Test: manifest loading
# ---------------------------------------------------------------------------

class TestManifestLoading:
    """load_manifest handles various manifest formats."""

    def test_load_valid_manifest(self, migration_env):
        """load_manifest reads all entries."""
        entries = load_manifest(migration_env["manifest_path"])
        assert len(entries) == 5

    def test_load_missing_manifest(self, tmp_path):
        """load_manifest returns empty list for missing file."""
        entries = load_manifest(tmp_path / "nonexistent.jsonl")
        assert entries == []

    def test_load_manifest_skips_bad_lines(self, tmp_path):
        """load_manifest skips unparseable lines."""
        mf = tmp_path / "manifest.jsonl"
        mf.write_text('{"sha256": "abc"}\nBAD LINE\n{"sha256": "def"}\n\n')
        entries = load_manifest(mf)
        assert len(entries) == 2


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
