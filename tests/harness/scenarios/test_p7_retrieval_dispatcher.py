"""Retrieval-only nodes use pack integrity closeout, never report closeout."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HARNESS = (Path(__file__).resolve().parents[3] / 'harness')
_HARNESS_LIB = str(_HARNESS / "lib")
if _HARNESS_LIB not in sys.path:
    sys.path.insert(0, _HARNESS_LIB)

import graph_node_dispatcher as gnd  # noqa: E402
from research.source_pack import write_source_pack  # noqa: E402
from research.sources.base import FetchResult  # noqa: E402

SID = "sprint-p7-retrieval-dispatch"


def _retrieval_node() -> dict:
    return {
        "id": "R1",
        "goal": "retrieve sources for the research question",
        "write_scope": [
            "workspace/research/source-pack/sources.jsonl",
            "workspace/research/source-pack/evidence.jsonl",
            "workspace/research/source-pack/extracts",
        ],
        "artifacts": {
            "sources": "workspace/research/source-pack/sources.jsonl",
            "evidence": "workspace/research/source-pack/evidence.jsonl",
        },
    }


def _claim_node() -> dict:
    return {
        "id": "R2",
        "goal": "write the grounded report",
        "write_scope": ["workspace/research/final.md", "workspace/research/claims.jsonl"],
        "artifacts": {"final_md": "workspace/research/final.md"},
    }


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    sprints = tmp_path / "sprints"
    (sprints / SID / "workdir" / "workspace").mkdir(parents=True)
    monkeypatch.setattr(gnd, "SPRINTS_DIR", sprints)
    eval_json = sprints / f"{SID}.R1-eval.json"
    eval_json.write_text(json.dumps({"node_id": "R1", "verdict": "PASS"}), encoding="utf-8")
    return tmp_path, sprints, eval_json


def _stage_pack(path: Path) -> Path:
    write_source_pack(
        path,
        [
            FetchResult(
                source_id="web_a",
                connector_id="codex_live_search",
                title="Official source",
                raw_text="retrieval provenance lands on disk with hashes",
                source_url="https://docs.example.org/research",
                metadata={"source_type": "official_doc"},
            )
        ],
    )
    return path


def test_detection_is_declaration_keyed():
    assert gnd._node_declares_retrieval_only(_retrieval_node()) is True
    assert gnd._node_declares_retrieval_only(_claim_node()) is False
    sources_only = {"write_scope": ["workspace/research/source-pack/sources.jsonl"]}
    assert gnd._node_declares_retrieval_only(sources_only) is True
    assert gnd._node_requires_deepresearch_quality_gate(sources_only) is True
    mixed = _retrieval_node()
    mixed["artifacts"]["claims"] = "workspace/research/claims.jsonl"
    assert gnd._node_declares_retrieval_only(mixed) is False
    assert gnd._node_requires_deepresearch_quality_gate(_retrieval_node()) is True


def test_valid_pack_passes_retrieval_closeout(sandbox):
    _, sprints, eval_json = sandbox
    pack = _stage_pack(sprints / SID / "workdir" / "workspace" / "research" / "source-pack")
    before = {
        path.relative_to(pack): path.read_bytes()
        for path in sorted(pack.rglob("*"))
        if path.is_file()
    }
    result = gnd._deepresearch_quality_gate_auto_run(SID, _retrieval_node(), eval_json)
    assert result["present"] is True
    assert result["ok"] is True
    assert result["gate"]["retrieval_only"] is True
    assert result["gate"]["closeout_verdict"] == "pass"
    after = {
        path.relative_to(pack): path.read_bytes()
        for path in sorted(pack.rglob("*"))
        if path.is_file()
    }
    assert after == before


def test_auto_closeout_preserves_the_evaluators_frozen_snapshot(sandbox):
    _, sprints, eval_json = sandbox
    _stage_pack(sprints / SID / "workdir" / "workspace" / "research" / "source-pack")
    node = _retrieval_node()
    graph = {
        "sprint_id": SID,
        "workflow_contract_id": "pm.generic.v1",
        "nodes": [node],
    }
    snapshot = gnd._capture_eval_artifact_snapshot(SID, node, graph)
    assert snapshot["ok"] is True, snapshot
    eval_payload = {
        "artifact_snapshot_schema": snapshot["schema"],
        "artifact_snapshot_path": snapshot["path"],
        "artifact_snapshot_digest": snapshot["snapshot_digest"],
    }

    closeout = gnd._deepresearch_quality_gate_auto_run(SID, node, eval_json)
    revalidated = gnd._validate_eval_artifact_snapshot(SID, node, graph, eval_payload)

    assert closeout["ok"] is True, closeout
    assert revalidated["ok"] is True, revalidated


def test_missing_pack_is_repairable_and_claim_node_keeps_report_gate(sandbox):
    _, _, eval_json = sandbox
    missing = gnd._deepresearch_quality_gate_auto_run(SID, _retrieval_node(), eval_json)
    assert missing["gate"]["closeout_verdict"] == "repairable_fail"
    assert "sources_jsonl_missing" in missing["gate"]["errors"]

    claim = gnd._deepresearch_quality_gate_auto_run(SID, _claim_node(), eval_json)
    assert claim["present"] is False
    assert any(error.startswith("research_eval_artifact_missing") for error in claim["gate"]["errors"])


def test_foreign_absolute_traversing_and_sibling_sprint_packs_are_rejected(sandbox):
    outside_root, sprints, eval_json = sandbox
    foreign = _stage_pack(outside_root / "foreign")
    sibling = _stage_pack(sprints / "other-sprint" / "workdir" / "workspace" / "research")

    for declared in (
        str(foreign / "sources.jsonl"),
        "../../../foreign/sources.jsonl",
        str(sibling / "sources.jsonl"),
    ):
        node = _retrieval_node()
        node["write_scope"] = []
        node["artifacts"] = {"sources": declared}
        result = gnd._deepresearch_quality_gate_auto_run(SID, node, eval_json)
        assert result["ok"] is False
        assert result["gate"]["closeout_verdict"] == "repairable_fail"


def test_absolute_pack_inside_current_sprint_is_allowed(sandbox):
    _, sprints, eval_json = sandbox
    pack = _stage_pack(sprints / SID / "workdir" / "workspace" / "research" / "absolute-pack")
    node = _retrieval_node()
    node["artifacts"] = {"sources": str(pack / "sources.jsonl")}
    node["write_scope"] = [str(pack / "sources.jsonl"), str(pack / "evidence.jsonl"), str(pack / "extracts")]

    result = gnd._deepresearch_quality_gate_auto_run(SID, node, eval_json)
    assert result["ok"] is True


def test_eval_instruction_distinguishes_retrieval_from_report(sandbox):
    _, _, eval_json = sandbox
    retrieval = gnd._deepresearch_quality_gate_eval_instruction(_retrieval_node(), eval_json)
    report = gnd._deepresearch_quality_gate_eval_instruction(_claim_node(), eval_json)
    assert "retrieval-only" in retrieval
    assert "do not run" in retrieval.lower()
    assert "must first run" in report.lower()
