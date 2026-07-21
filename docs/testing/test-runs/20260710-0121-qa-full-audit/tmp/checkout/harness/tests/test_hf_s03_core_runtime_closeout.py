import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = ROOT / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from hf_s03_core_runtime_closeout import NODE_IDS, auto_closeout_hf_s03_nodes


def test_auto_closeout_hf_s03_nodes(monkeypatch, tmp_path):
    runtime_root = tmp_path / "runtime"
    sprint_root = runtime_root / "sprints"
    lib_root = runtime_root / "lib" / "hf_paper_insight"
    tests_root = runtime_root / "tests"
    providers_root = lib_root / "providers"
    sprint_root.mkdir(parents=True, exist_ok=True)
    lib_root.mkdir(parents=True, exist_ok=True)
    tests_root.mkdir(parents=True, exist_ok=True)
    providers_root.mkdir(parents=True, exist_ok=True)

    sid = "sprint-20260527-p0-ai-influence-hf-paper-insight-flow-paper-to-project-研究-s03-core-runtime"
    (sprint_root / f"{sid}.task_graph.json").write_text(
        json.dumps(
            {
                "sprint_id": sid,
                "nodes": [
                    {"id": "C1_schema_storage_state", "status": "reviewing", "depends_on": []},
                    {"id": "C2_collection_canonical_enrichment", "status": "reviewing", "depends_on": ["C1_schema_storage_state"]},
                    {"id": "C3_taxonomy_scoring_packet", "status": "reviewing", "depends_on": ["C1_schema_storage_state"]},
                    {"id": "C4_reasoning_compiler_store_watch", "status": "reviewing", "depends_on": ["C2_collection_canonical_enrichment", "C3_taxonomy_scoring_packet"]},
                    {"id": "C5_core_runtime_release", "status": "reviewing", "depends_on": ["C4_reasoning_compiler_store_watch"]},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    for node_id in NODE_IDS:
        (sprint_root / f"{sid}.{node_id}-handoff.md").write_text("tests all pass\n", encoding="utf-8")
    for name in ("schema.py", "storage.py", "state_machine.py", "compat.py", "collector.py", "canonicalizer.py", "taxonomy.py", "scoring.py", "packet.py", "reasoning.py", "compiler.py", "knowledge_store.py", "watch.py"):
        (lib_root / name).write_text("# stub\n", encoding="utf-8")
    for name in ("__init__.py", "hf_metadata.py", "arxiv_metadata.py", "hf_assets.py"):
        (providers_root / name).write_text("# stub\n", encoding="utf-8")
    (tests_root / "test_hf_paper_insight_schema.py").write_text("def test_stub():\n    assert True\n", encoding="utf-8")
    (tests_root / "test_hf_paper_insight_scoring.py").write_text("def test_stub():\n    assert True\n", encoding="utf-8")
    (tests_root / "test_hf_paper_insight_collection.py").write_text("def test_stub():\n    assert True\n", encoding="utf-8")
    (tests_root / "test_hf_paper_insight_runtime.py").write_text("def test_stub():\n    assert True\n", encoding="utf-8")

    monkeypatch.setattr(
        "hf_s03_core_runtime_closeout.subprocess.run",
        lambda *args, **kwargs: type("P", (), {"returncode": 0, "stdout": "25 passed", "stderr": ""})(),
    )

    calls = []

    def _fake_closeout(**kwargs):
        calls.append(kwargs)
        return {"ok": True, "node_results": {node_id: {"ok": True} for node_id in kwargs["node_payloads"]}, "status_sync": {"ok": True}}

    monkeypatch.setattr("hf_s03_core_runtime_closeout.auto_closeout_graph_nodes", _fake_closeout)

    result = auto_closeout_hf_s03_nodes(runtime_root)

    assert result["ok"] is True
    assert calls
    for node_id in NODE_IDS:
        payload = next(call["node_payloads"][node_id] for call in calls if node_id in call["node_payloads"])
        assert payload["verdict"] == "PASS"
        assert "runtime_pytest_passed" in payload["passed_conditions"]
