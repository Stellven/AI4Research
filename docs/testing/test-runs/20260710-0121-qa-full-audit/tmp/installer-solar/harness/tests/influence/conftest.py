"""Pytest fixtures + import path setup for the influence test suite.

Adds the harness root to sys.path so ``import lib.influence`` resolves, and forces
every test to run against an isolated KNOWLEDGE_ROOT temp dir so the live
~/Knowledge tree is never touched.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

HARNESS_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(HARNESS_ROOT) not in sys.path:
    sys.path.insert(0, str(HARNESS_ROOT))

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def isolated_knowledge_root(tmp_path, monkeypatch):
    root = tmp_path / "Knowledge"
    root.mkdir()
    monkeypatch.setenv("KNOWLEDGE_ROOT", str(root))
    return root


@pytest.fixture
def sample_statement_dict():
    return json.loads((FIXTURES / "sample_statement.json").read_text())


@pytest.fixture
def sample_thesis_dict():
    return json.loads((FIXTURES / "sample_thesis.json").read_text())


@pytest.fixture
def sample_packet_dict():
    return json.loads((FIXTURES / "sample_evidence_packet.json").read_text())
