import importlib.util
import sys
from pathlib import Path


HARNESS_LIB = (Path(__file__).resolve().parents[3] / 'harness') / "lib"
sys.path.insert(0, str(HARNESS_LIB))

from capability_inference import enrich_graph  # noqa: E402


def test_explicit_required_capabilities_are_not_union_enriched() -> None:
    graph = {
        "nodes": [
            {
                "id": "C1",
                "goal": "Implement Python state gate",
                "required_capabilities": ["python", "testing"],
            }
        ]
    }

    enriched = enrich_graph(
        graph,
        source_text="Contract mentions browser automation, empirical research, and MarkItDown.",
    )

    assert enriched["nodes"][0]["required_capabilities"] == ["python", "testing"]
    assert enriched["capability_inference"]["changed_nodes"] == []


def test_missing_required_capabilities_are_still_inferred() -> None:
    graph = {
        "nodes": [
            {
                "id": "R1",
                "goal": "Use Ruflo Claude Flow swarm orchestration to verify MCP workflow templates",
            }
        ]
    }

    enriched = enrich_graph(graph)

    assert "ruflo.swarm" in enriched["nodes"][0]["required_capabilities"]
    assert enriched["capability_inference"]["changed_nodes"] == ["R1"]


def test_tools_entrypoint_forwards_to_lib_capability_authority() -> None:
    tools_module_path = HARNESS_LIB.parent / "tools" / "capability_inference.py"
    spec = importlib.util.spec_from_file_location("capability_inference_tools_probe", tools_module_path)
    assert spec is not None and spec.loader is not None
    tools_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tools_module)

    assert Path(tools_module.enrich_graph.__code__.co_filename).resolve() == (
        HARNESS_LIB / "capability_inference.py"
    ).resolve()
