"""Guards for the full-suite collection quarantine manifest."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path


HARNESS_DIR = (Path(__file__).resolve().parents[3] / 'harness')
CONFTEST_PATH = HARNESS_DIR / "tests" / "conftest.py"


def _load_tests_conftest():
    spec = importlib.util.spec_from_file_location("_collection_hygiene_conftest", CONFTEST_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_quarantine_manifest_entries_exist_on_disk():
    conftest = _load_tests_conftest()
    missing = [
        rel_path
        for rel_path in conftest.COLLECTION_QUARANTINE_MANIFEST
        if not (HARNESS_DIR / rel_path).is_file()
    ]
    assert not missing, "remove deleted files from COLLECTION_QUARANTINE_MANIFEST: " + repr(missing)


def test_quarantine_manifest_count_is_explicit():
    conftest = _load_tests_conftest()
    manifest = conftest.COLLECTION_QUARANTINE_MANIFEST
    # Shrinking this exact count is the goal; any increase must be a reviewed quarantine decision.
    # Wave-2 dup-basename renames un-quarantined 11 entries (41 -> 30): every
    # remaining duplicate-basename entry either got a unique name or had its
    # collision partner renamed, and each un-quarantined file passes standalone.
    assert len(manifest) == conftest.QUARANTINE_EXPECTED_COUNT == 30
    assert list(manifest) == sorted(manifest)
    assert all(meta["class"] and meta["cause"] for meta in manifest.values())


def test_full_suite_collect_only_exits_cleanly():
    result = subprocess.run(
        ["python3", "-m", "pytest", "tests/", "--collect-only", "-q"],
        cwd=HARNESS_DIR,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        "full-suite collect-only failed\n"
        f"returncode={result.returncode}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
