"""Live deep-research regression: directory manifests must satisfy capsule outputs.

The first isolated rc.10 research run wrote a complete retrieval pack beneath a
single declared directory.  The manifest correctly hashed that directory tree,
but the proof gate could only see the root row.  Capsule postconditions use
semantic field names (``sources_jsonl``, ``evidence_jsonl``, ``extracts_dir``),
so real files were reported missing and a content-valid node failed.
"""
from __future__ import annotations

import sys
from pathlib import Path


HARNESS = (Path(__file__).resolve().parents[3] / 'harness')
sys.path.insert(0, str(HARNESS / "lib"))

import artifact_manifest  # noqa: E402
import graph_node_dispatcher as gnd  # noqa: E402


def test_directory_manifest_exposes_semantic_retrieval_outputs(tmp_path, monkeypatch) -> None:
    sid = "sprint-live-retrieval-proof"
    sprints = tmp_path / "sprints"
    workdir = sprints / sid / "workdir"
    pack = workdir / "workspace" / "research" / "source-pack"
    extracts = pack / "extracts"
    extracts.mkdir(parents=True)
    (pack / "sources.jsonl").write_text('{"id":"source-1"}\n', encoding="utf-8")
    (pack / "evidence.jsonl").write_text('{"id":"evidence-1"}\n', encoding="utf-8")
    (extracts / "source-1.txt").write_text("Real fetched source text.\n", encoding="utf-8")

    node = {
        "id": "R1",
        "write_scope": ["workspace/research/source-pack/"],
        "proof_obligations": [
            {"kind": "postcondition", "requirement": "output_present", "field": "sources_jsonl"},
            {"kind": "postcondition", "requirement": "output_present", "field": "evidence_jsonl"},
            {"kind": "postcondition", "requirement": "output_present", "field": "extracts_dir"},
        ],
    }
    manifest = artifact_manifest.write_manifest(
        sprints,
        sid,
        node,
        generation=0,
        base_dir=workdir,
        roots={"canonical": "workspace/"},
    )
    assert manifest is not None

    monkeypatch.setattr(gnd, "SPRINTS_DIR", sprints)
    monkeypatch.setattr(gnd, "HARNESS_DIR", tmp_path / "harness")
    monkeypatch.setattr(gnd, "_ledger_enabled", lambda: True)

    presence = gnd._proof_artifact_presence(sid, node)
    assert presence["output:workspace/research/source-pack/sources.jsonl"] is True
    assert presence["output:workspace/research/source-pack/evidence.jsonl"] is True
    assert presence["output:workspace/research/source-pack/extracts"] is True

    proof = gnd._evaluate_proof_obligations(sid, node)
    assert proof["ok"] is True, proof
    assert proof["missing"] == []


def test_capsule_output_names_use_one_filename_convention() -> None:
    presence = {
        "output:workspace/research/report/claims.jsonl": True,
        "output:workspace/research/report/report_ast.json": True,
        "output:workspace/research/report/final.md": True,
        "output:workspace/research/report/extracts": True,
    }

    assert gnd._proof_field_presence(presence, "claims_jsonl") is True
    assert gnd._proof_field_presence(presence, "report_ast_json") is True
    assert gnd._proof_field_presence(presence, "final_md") is True
    assert gnd._proof_field_presence(presence, "extracts_dir") is True
    assert gnd._proof_field_presence(presence, "unrelated_json") is None
