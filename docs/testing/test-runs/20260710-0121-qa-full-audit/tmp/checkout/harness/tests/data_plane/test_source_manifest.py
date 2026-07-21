"""Tests for source_manifest.py generate command (S1 acceptance criteria)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lib"))
import source_manifest as sm


@pytest.fixture()
def tmp_raw(tmp_path: Path) -> Path:
    uploads = tmp_path / "_raw" / "file-uploads"
    uploads.mkdir(parents=True)
    (uploads / "paper.pdf").write_bytes(b"%PDF-1.4 test")
    (uploads / "note.pages").write_bytes(b"fake pages content")
    (uploads / "site.html").write_bytes(b"<html><body>hi</body></html>")
    (uploads / "readme.md").write_bytes(b"# hello")
    (uploads / "data.jsonl").write_bytes(b'{"x":1}\n')
    return uploads


@pytest.fixture()
def tmp_meta(tmp_path: Path) -> Path:
    meta = tmp_path / "_meta"
    meta.mkdir(parents=True)
    return meta


@pytest.fixture()
def tmp_sources(tmp_path: Path) -> Path:
    sources = tmp_path / "_sources"
    sources.mkdir(parents=True)
    return sources


class TestScaffoldDirs:
    def test_sources_categories_exist(self) -> None:
        base = Path.home() / "Knowledge" / "_sources"
        for cat in sm.SOURCE_CATEGORIES:
            assert (base / cat).exists(), f"Missing _sources/{cat}"

    def test_meta_dir_exists(self) -> None:
        assert (Path.home() / "Knowledge" / "_meta").exists()

    def test_manifest_jsonl_exists(self) -> None:
        assert sm.MANIFEST_JSONL.exists()

    def test_stats_json_exists(self) -> None:
        assert sm.MANIFEST_STATS.exists()


class TestGenerateManifest:
    def test_generate_dry_run_no_files_created(self, tmp_raw: Path, tmp_meta: Path, tmp_sources: Path) -> None:
        rc = sm.cmd_generate(tmp_raw, tmp_meta, tmp_sources, apply=False, as_json=False)
        assert rc == 0
        assert not (tmp_meta / "source-manifest.jsonl").exists()
        assert not (tmp_meta / "source-manifest-stats.json").exists()

    def test_generate_apply_creates_jsonl(self, tmp_raw: Path, tmp_meta: Path, tmp_sources: Path) -> None:
        rc = sm.cmd_generate(tmp_raw, tmp_meta, tmp_sources, apply=True, as_json=False)
        assert rc == 0
        manifest = tmp_meta / "source-manifest.jsonl"
        assert manifest.exists()
        lines = manifest.read_text().strip().splitlines()
        assert len(lines) == 5  # 5 test files

    def test_generate_entry_has_required_fields(self, tmp_raw: Path, tmp_meta: Path, tmp_sources: Path) -> None:
        sm.cmd_generate(tmp_raw, tmp_meta, tmp_sources, apply=True, as_json=False)
        manifest = tmp_meta / "source-manifest.jsonl"
        for line in manifest.read_text().strip().splitlines():
            entry = json.loads(line)
            for field in ("sha256", "size", "original_path", "canonical_path", "media_type", "status"):
                assert field in entry, f"Missing field: {field}"

    def test_generate_entry_status_is_indexed(self, tmp_raw: Path, tmp_meta: Path, tmp_sources: Path) -> None:
        sm.cmd_generate(tmp_raw, tmp_meta, tmp_sources, apply=True, as_json=False)
        manifest = tmp_meta / "source-manifest.jsonl"
        for line in manifest.read_text().strip().splitlines():
            entry = json.loads(line)
            assert entry["status"] == "indexed"

    def test_generate_categorization(self, tmp_raw: Path, tmp_meta: Path, tmp_sources: Path) -> None:
        sm.cmd_generate(tmp_raw, tmp_meta, tmp_sources, apply=True, as_json=False)
        manifest = tmp_meta / "source-manifest.jsonl"
        by_cat: dict[str, list[str]] = {}
        for line in manifest.read_text().strip().splitlines():
            entry = json.loads(line)
            cat = entry["category"]
            by_cat.setdefault(cat, []).append(Path(entry["original_path"]).name)
        assert "paper.pdf" in by_cat.get("papers", [])
        assert "note.pages" in by_cat.get("apple-notes", [])
        assert "site.html" in by_cat.get("webpages", [])
        assert "readme.md" in by_cat.get("other", [])
        assert "data.jsonl" in by_cat.get("other", [])

    def test_generate_stats_json(self, tmp_raw: Path, tmp_meta: Path, tmp_sources: Path) -> None:
        sm.cmd_generate(tmp_raw, tmp_meta, tmp_sources, apply=True, as_json=False)
        stats = json.loads((tmp_meta / "source-manifest-stats.json").read_text())
        assert stats["total_files"] == 5
        assert stats["total_bytes"] > 0
        assert stats["error_count"] == 0
        assert "by_category" in stats

    def test_generate_sha256_not_empty(self, tmp_raw: Path, tmp_meta: Path, tmp_sources: Path) -> None:
        sm.cmd_generate(tmp_raw, tmp_meta, tmp_sources, apply=True, as_json=False)
        manifest = tmp_meta / "source-manifest.jsonl"
        for line in manifest.read_text().strip().splitlines():
            entry = json.loads(line)
            assert len(entry["sha256"]) == 64

    def test_generate_canonical_path_includes_sha(self, tmp_raw: Path, tmp_meta: Path, tmp_sources: Path) -> None:
        sm.cmd_generate(tmp_raw, tmp_meta, tmp_sources, apply=True, as_json=False)
        manifest = tmp_meta / "source-manifest.jsonl"
        for line in manifest.read_text().strip().splitlines():
            entry = json.loads(line)
            assert entry["sha256"][:2] in entry["canonical_path"]
            assert entry["sha256"] in entry["canonical_path"]

    def test_generate_missing_raw_dir_returns_error(self, tmp_meta: Path, tmp_sources: Path) -> None:
        rc = sm.cmd_generate(Path("/nonexistent/path"), tmp_meta, tmp_sources, apply=True, as_json=False)
        assert rc != 0


class TestLiveManifest:
    def test_live_manifest_covers_183_files(self) -> None:
        if not sm.MANIFEST_JSONL.exists():
            pytest.skip("Live manifest not generated yet")
        lines = sm.MANIFEST_JSONL.read_text().strip().splitlines()
        assert len(lines) == 183

    def test_live_stats_total_files(self) -> None:
        if not sm.MANIFEST_STATS.exists():
            pytest.skip("Live stats not generated yet")
        stats = json.loads(sm.MANIFEST_STATS.read_text())
        assert stats["total_files"] == 183
        assert stats["total_bytes"] > 0
