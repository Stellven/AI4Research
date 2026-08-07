from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from journey_runner import python_executable, repo_root_from


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "live_provider: requires live model/network/provider authorization")


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return repo_root_from(Path(__file__))


@pytest.fixture(scope="session")
def phase22_python(repo_root: Path) -> str:
    return python_executable(repo_root)
