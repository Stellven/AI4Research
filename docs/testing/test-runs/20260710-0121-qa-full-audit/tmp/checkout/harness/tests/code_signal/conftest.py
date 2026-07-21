"""Shared fixtures for code_signal tests."""
import sys
import tempfile
from pathlib import Path

import pytest

# Add harness/lib to path
HARNESS_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HARNESS_ROOT / "lib"))
sys.path.insert(0, str(HARNESS_ROOT))


@pytest.fixture
def knowledge_root(tmp_path):
    return tmp_path


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_code_signal.sqlite")
