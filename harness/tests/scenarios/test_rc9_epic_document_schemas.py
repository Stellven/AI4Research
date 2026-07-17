"""Generated epic child documents must pass the validators that gate them."""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


_HARNESS = Path(__file__).resolve().parents[2]
_DECOMPOSER = _HARNESS / "lib" / "epic_decomposer.py"
_VALIDATOR = _HARNESS / "schemas" / "validate.sh"


def _load_decomposer():
    spec = importlib.util.spec_from_file_location(
        "rc9_epic_document_schema_decomposer", _DECOMPOSER
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def generated_children(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    decomposer = _load_decomposer()
    sprints_dir = tmp_path / "sprints"
    monkeypatch.setattr(decomposer, "SPRINTS_DIR", sprints_dir)
    result = decomposer.create_epic(
        SimpleNamespace(
            title="Bounded runtime improvement",
            request="Improve one bounded runtime path with tests and evidence.",
            request_file=None,
            priority="P0",
            slug="rc9-document-schema",
            slices=5,
            activate_ready=True,
            dry_run=False,
        )
    )
    return [child["sid"] for child in result["children"]]


@pytest.mark.parametrize("document_type", ["prd", "contract"])
def test_every_generated_child_document_passes_its_shipped_validator(
    generated_children: list[str], document_type: str, tmp_path: Path
):
    suffix = ".prd.md" if document_type == "prd" else ".contract.md"
    failures = []
    for sid in generated_children:
        path = tmp_path / "sprints" / f"{sid}{suffix}"
        result = subprocess.run(
            ["bash", str(_VALIDATOR), document_type, str(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            failures.append({"path": str(path), "output": result.stdout.strip()})
    assert not failures, failures
