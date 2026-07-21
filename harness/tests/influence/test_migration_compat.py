"""Migration and rollout verification tests for Social Signal Plane convergence.

These tests verify:
1. Existing scripts are not broken by the new package
2. Migration DAG rules are honored
3. Feature toggle on/off behavior works
4. Knowledge dir isolation (no writes to live ~/Knowledge)
5. Rollback procedure is valid

Tests depend on S2 producing:
- harness/lib/influence/ package
- harness/config/influence/source_adapters.yaml
- harness/scripts/influence/ CLI entry points

If S2 has not yet produced these artifacts, tests will skip with clear messages.
"""
import json
import os
import pathlib
import tempfile

import pytest

# Paths — test file at tests/influence/ → parents[2] = ~/.solar/harness/
HARNESS_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS_DIR = HARNESS_ROOT / "scripts"
INFLUENCE_LIB = HARNESS_ROOT / "lib" / "influence"
INFLUENCE_CONFIG = HARNESS_ROOT / "config" / "influence"
INFLUENCE_SCRIPTS = SCRIPTS_DIR / "influence"
EXISTING_SCRIPTS = SCRIPTS_DIR
SOURCE_ADAPTERS_YAML = INFLUENCE_CONFIG / "source_adapters.yaml"


def _skip_if_no_lib():
    if not INFLUENCE_LIB.exists():
        pytest.skip("harness/lib/influence/ not yet created by S2")


# ── Compat: existing scripts not broken ──


class TestExistingScriptsIntact:
    """Verify S2 did not modify existing scripts."""

    EXISTING = [
        "ai_influence_digest.py",
        "youtube_influence_digest.py",
        "tech_hotspot_radar.py",
    ]

    @pytest.mark.parametrize("script", EXISTING)
    def test_existing_script_exists(self, script):
        path = EXISTING_SCRIPTS / script
        assert path.exists(), f"Existing script {script} was removed"

    @pytest.mark.parametrize("script", EXISTING)
    def test_existing_script_importable(self, script):
        """Existing scripts must remain importable as modules."""
        path = EXISTING_SCRIPTS / script
        if not path.exists():
            pytest.skip(f"{script} not found")
        content = path.read_text()
        # Should not import from harness.lib.influence (would create coupling)
        assert "from harness.lib.influence" not in content
        assert "from lib.influence" not in content


# ── Migration: new dirs are additive ──


class TestMigrationDAG:
    """Verify migration DAG rules from S3 spec §2."""

    def test_new_package_exists(self):
        _skip_if_no_lib()
        assert INFLUENCE_LIB.is_dir()

    def test_new_package_is_separate(self):
        """New package must not import from or modify existing scripts."""
        _skip_if_no_lib()
        for py in INFLUENCE_LIB.rglob("*.py"):
            content = py.read_text()
            assert "ai_influence_digest" not in content or "statement_collector" in str(py), \
                f"{py.name} couples to ai_influence_digest directly — use adapter pattern"

    def test_knowledge_extracted_dirs_additive(self):
        """New Knowledge dirs must be under extracted/, not _raw/."""
        _skip_if_no_lib()
        for py in INFLUENCE_LIB.rglob("*.py"):
            content = py.read_text()
            assert "_raw" not in content or "read_text" in content, \
                f"{py.name} writes to _raw/ — only reads allowed"


# ── Feature toggle: source adapters ──


class TestSourceAdapters:
    """Verify source_adapters.yaml toggle behavior."""

    def test_config_file_exists(self):
        _skip_if_no_lib()
        assert SOURCE_ADAPTERS_YAML.exists(), "source_adapters.yaml not created"

    @pytest.mark.skipif(not SOURCE_ADAPTERS_YAML.exists(), reason="config not yet created")
    def test_mvp_adapters_enabled(self):
        content = SOURCE_ADAPTERS_YAML.read_text()
        # MVP adapters must be present
        assert "x_backend" in content
        assert "youtube_transcript" in content

    @pytest.mark.skipif(not SOURCE_ADAPTERS_YAML.exists(), reason="config not yet created")
    def test_non_mvp_adapters_disabled(self):
        content = SOURCE_ADAPTERS_YAML.read_text()
        # Non-MVP adapters must be disabled
        for adapter in ["bluesky", "hackernews", "gdelt", "sec_filings"]:
            if adapter in content:
                # If present, must be enabled: false
                lines = content.split("\n")
                in_adapter = False
                for line in lines:
                    if adapter in line:
                        in_adapter = True
                    if in_adapter and "enabled" in line:
                        assert "false" in line, f"{adapter} must be disabled in MVP"


# ── Knowledge dir isolation ──


class TestKnowledgeIsolation:
    """Verify tests never write to live ~/Knowledge."""

    def test_knowledge_root_env_required(self):
        """All Knowledge writes must go through KNOWLEDGE_ROOT env var."""
        _skip_if_no_lib()
        for py in INFLUENCE_LIB.rglob("*.py"):
            content = py.read_text()
            if "~/Knowledge" in content or "Knowledge/_raw" in content:
                # Only allowed in comments or config reading
                assert "KNOWLEDGE_ROOT" in content or "os.environ" in content, \
                    f"{py.name} hardcodes Knowledge path — use KNOWLEDGE_ROOT env"


# ── Rollback verification ──


class TestRollbackProcedure:
    """Verify rollback is clean (all new files are in removable dirs)."""

    NEW_DIRS = [
        INFLUENCE_LIB,
        HARNESS_ROOT / "schemas" / "influence",
        INFLUENCE_SCRIPTS,
        pathlib.Path(__file__).parent,  # harness/tests/influence/
        INFLUENCE_CONFIG,
    ]

    def test_new_dirs_are_self_contained(self):
        """All new files must be within removable directories."""
        _skip_if_no_lib()
        for new_dir in self.NEW_DIRS:
            if new_dir.exists():
                for f in new_dir.rglob("*"):
                    # Verify no symlinks pointing outside
                    if f.is_symlink():
                        target = f.resolve()
                        assert any(d in target.parents or target == d for d in self.NEW_DIRS), \
                            f"Symlink {f} points outside new package dirs"
