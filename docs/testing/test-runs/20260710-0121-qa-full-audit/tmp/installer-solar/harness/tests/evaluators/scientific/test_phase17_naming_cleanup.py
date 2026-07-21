from __future__ import annotations

import json
from pathlib import Path


HARNESS = Path(__file__).parents[3]


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_scientific_runtime_capability_ids_are_research_named() -> None:
    search_roots = [
        HARNESS / "capability-capsules",
        HARNESS / "config",
        HARNESS / "schemas" / "evidence",
        HARNESS / "workflows",
    ]

    checked_files = []
    for root in search_roots:
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in {".json", ".yaml"}:
                checked_files.append(path)
                text = _text(path)
                assert "cap.scientific-" not in text, path
                assert "cap.autosci-" not in text, path
                assert "sprint.autosci" not in text, path
                assert "artifacts/autosci/fixtures" not in text, path

    assert checked_files
    for capsule in (HARNESS / "capability-capsules").glob("cap.research-*.yaml"):
        first_line = _text(capsule).splitlines()[0]
        assert first_line.startswith("capability_capsule_id: cap.research-"), capsule


def test_lifecycle_black_box_policy_is_backend_generic() -> None:
    targets = list((HARNESS / "workflows").glob("scientific*.json"))
    targets.append(HARNESS / "evaluators" / "scientific" / "lifecycle_gate.py")

    for path in targets:
        text = _text(path)
        assert "hidden-autosci-full-workflow" not in text, path
        assert "autosci-black-box-runner" not in text, path

    gate_text = _text(HARNESS / "evaluators" / "scientific" / "lifecycle_gate.py")
    assert "hidden-backend-full-workflow" in gate_text
    assert "backend-black-box-runner" in gate_text


def test_scientific_workflow_templates_keep_solar_native_names() -> None:
    for path in (HARNESS / "workflows").glob("scientific*.json"):
        payload = json.loads(_text(path))
        assert payload["workflow_id"].startswith("scientific_"), path
        assert "AutoSci" not in payload["workflow_id"], path
        assert "AutoSci" not in payload["title"], path
        assert payload["dag_variant"] == "research", path
        for node in payload["nodes"]:
            assert str(node["logical_operator"]).startswith(("Scientific", "Verifier")), (
                path,
                node["id"],
            )
            for capability in node.get("required_capabilities", []):
                if capability.startswith("cap."):
                    assert capability.startswith("cap.research-"), (path, node["id"], capability)
