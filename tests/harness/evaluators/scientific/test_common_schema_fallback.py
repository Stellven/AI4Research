from __future__ import annotations

import builtins
from pathlib import Path

import pytest

from evaluators.scientific import common


def _research_paper_payload() -> dict:
    return {
        "schema": "research_paper.v1",
        "task_id": "task-schema-fallback",
        "sprint_id": "sprint-schema-fallback",
        "node_id": "node-schema-fallback",
        "status": "completed",
        "inputs": {"source_ref": "paper.md"},
        "outputs": {
            "paper": {
                "paper_id": "paper-schema-fallback",
                "title": "Schema Fallback Paper",
                "source_type": "markdown",
                "source_ref": "paper.md",
                "parse_status": "parsed",
                "sections": [{"section_id": "intro", "title": "Introduction"}],
            }
        },
        "artifacts": [],
        "provenance": {
            "operator_id": "test",
            "implementation_package": "test",
            "timestamp": "2026-06-25T00:00:00Z",
        },
        "limitations": [],
    }


def _jsonschema_missing():
    raise ModuleNotFoundError("No module named 'jsonschema'", name="jsonschema")


def test_import_jsonschema_preserves_module_not_found_when_dependency_is_unavailable(monkeypatch) -> None:
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "jsonschema":
            raise ModuleNotFoundError("No module named 'jsonschema'", name="jsonschema")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(common, "_repo_venv_site_packages", lambda: Path("/missing/autosci/venv"))

    with pytest.raises(ModuleNotFoundError):
        common._import_jsonschema()


def test_validate_schema_uses_limited_fallback_when_jsonschema_is_missing(monkeypatch) -> None:
    monkeypatch.setattr(common, "_import_jsonschema", _jsonschema_missing)

    reasons, warnings = common.validate_schema(_research_paper_payload(), "research_paper.v1")

    assert reasons == []
    assert any("jsonschema unavailable" in warning for warning in warnings)


def test_validate_schema_fallback_still_rejects_missing_required_fields(monkeypatch) -> None:
    monkeypatch.setattr(common, "_import_jsonschema", _jsonschema_missing)
    payload = _research_paper_payload()
    payload.pop("outputs")

    reasons, warnings = common.validate_schema(payload, "research_paper.v1")

    assert "fallback schema check missing top-level keys: outputs" in reasons
    assert "fallback schema check found non-object outputs" in reasons
    assert any("jsonschema unavailable" in warning for warning in warnings)
