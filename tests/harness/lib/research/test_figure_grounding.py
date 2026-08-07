"""Unit tests for FigureSpec and figure grounding gate.

Tests invariants of FigureSpec dataclass, deterministic grounding validation,
and evaluate_artifacts / evaluate_final_closeout integration.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from research.schemas import FigureSpec
from research.evaluator import evaluate_figures_grounding, evaluate_artifacts, evaluate_final_closeout


def test_figurespec_dataclass_validation():
    # Valid FigureSpec constructs successfully
    fig = FigureSpec(
        figure_id="fig_arch_1",
        title="Runtime Pipeline",
        figure_type="architecture_diagram",
        grounding_ids=["cl_1", "ev_2"],
        spec_data={
            "nodes": [{"id": "node_1", "label": "Orchestrator", "grounding_id": "cl_1"}],
            "edges": [{"source": "node_1", "target": "node_2", "grounding_id": "ev_2"}]
        }
    )
    assert fig.figure_id == "fig_arch_1"
    assert fig.renderer == "mermaid"

    # Invalid figure type raises ValueError
    with pytest.raises(ValueError, match="figure_type"):
        FigureSpec(
            figure_id="fig_invalid",
            title="Bad Figure",
            figure_type="not_real",
            grounding_ids=[]
        )

    # Empty figure ID raises ValueError
    with pytest.raises(ValueError, match="figure_id"):
        FigureSpec(
            figure_id="",
            title="Title Only",
            figure_type="timeline",
            grounding_ids=[]
        )


def _setup_mock_run(tmp_path: Path, claims: list[dict], evidence: list[dict], figures: list[dict] | None = None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    
    # Write claims
    claims_path = tmp_path / "claims.jsonl"
    with open(claims_path, "w", encoding="utf-8") as f:
        for c in claims:
            f.write(json.dumps(c) + "\n")
            
    # Write evidence
    evidence_path = tmp_path / "evidence.jsonl"
    with open(evidence_path, "w", encoding="utf-8") as f:
        for ev in evidence:
            f.write(json.dumps(ev) + "\n")

    # Write figures if present
    if figures is not None:
        figures_path = tmp_path / "figures.json"
        with open(figures_path, "w", encoding="utf-8") as f:
            json.dump(figures, f)


def test_evaluate_figures_grounding_success(tmp_path):
    claims = [{"id": "cl_1"}, {"id": "cl_2"}]
    evidence = [{"id": "ev_1"}]
    figures = [
        {
            "figure_id": "fig_1",
            "title": "Architecture",
            "figure_type": "architecture_diagram",
            "grounding_ids": ["cl_1", "ev_1"],
            "spec_data": {
                "nodes": [{"id": "n1", "grounding_id": "cl_1"}, {"id": "n2"}],
                "edges": [{"source": "n1", "target": "n2", "grounding_id": "ev_1"}]
            }
        },
        {
            "figure_id": "fig_2",
            "title": "Timeline",
            "figure_type": "timeline",
            "grounding_ids": ["cl_2"],
            "spec_data": {
                "events": [{"id": "e1", "grounding_id": "cl_2"}]
            }
        }
    ]
    _setup_mock_run(tmp_path, claims, evidence, figures)
    ok, errors, warnings = evaluate_figures_grounding(tmp_path)
    assert ok
    assert not errors


def test_evaluate_figures_grounding_failures(tmp_path):
    claims = [{"id": "cl_1"}]
    evidence = [{"id": "ev_1"}]

    # Case 1: Empty grounding IDs
    figures_empty_grounding = [
        {
            "figure_id": "fig_empty",
            "title": "No Grounding",
            "figure_type": "architecture_diagram",
            "grounding_ids": [],
            "spec_data": {"nodes": [{"id": "n1"}], "edges": [{"source": "n1", "target": "n2"}]}
        }
    ]
    _setup_mock_run(tmp_path, claims, evidence, figures_empty_grounding)
    ok, errors, warnings = evaluate_figures_grounding(tmp_path)
    assert not ok
    assert any("figure_grounding_empty" in err for err in errors)

    # Case 2: Unresolved grounding ID
    figures_unresolved = [
        {
            "figure_id": "fig_unresolved",
            "title": "Mismatched",
            "figure_type": "timeline",
            "grounding_ids": ["cl_missing"],
            "spec_data": {"events": [{"id": "e1"}]}
        }
    ]
    _setup_mock_run(tmp_path, claims, evidence, figures_unresolved)
    ok, errors, warnings = evaluate_figures_grounding(tmp_path)
    assert not ok
    assert any("figure_grounding_unresolved" in err for err in errors)

    # Case 3: Component grounding ID not listed in top-level grounding_ids
    figures_unlisted_comp = [
        {
            "figure_id": "fig_unlisted",
            "title": "Unlisted Comp",
            "figure_type": "architecture_diagram",
            "grounding_ids": ["cl_1"],
            "spec_data": {
                "nodes": [{"id": "n1", "grounding_id": "ev_1"}],
                "edges": []
            }
        }
    ]
    _setup_mock_run(tmp_path, claims, evidence, figures_unlisted_comp)
    ok, errors, warnings = evaluate_figures_grounding(tmp_path)
    assert not ok
    assert any("figure_component_grounding_unlisted" in err for err in errors)


def test_evaluate_artifacts_integration(tmp_path):
    # Set up a complete good run structure
    (tmp_path / "final.md").write_text("# Final\n\nContinuous thought evidence supports latent reasoning systems [cite:ev_1]\n", encoding="utf-8")
    (tmp_path / "sources.jsonl").write_text(
        json.dumps({
            "id": "src_1",
            "source_type": "paper",
            "title": "Paper Abstract",
            "url": "https://arxiv.org/abs/2501.00001",
        }) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "sections.jsonl").write_text(
        json.dumps({
            "id": "sec_db_1",
            "section_type": "evidence_synthesis",
            "title": "Evidence Synthesis",
            "content": (
                "# Evidence Synthesis\n\n"
                "This section analyzes the runtime architecture, projection gate, deployment boundary, "
                "and evaluation policy for latent reasoning systems. The implementation should preserve "
                "audit evidence and failure recovery while separating model exploration from control-plane "
                "orchestration. Supported claim [cite:ev_1]\n"
            ),
        }) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "claims.jsonl").write_text(
        json.dumps({"id": "cl_1", "claim_text": "Good claim text goes here for validation."}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "evidence.jsonl").write_text(
        json.dumps({"id": "ev_1", "span_text": "Abstract: Continuous thought and hidden-state reasoning can reduce dependence."}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "report_ast.json").write_text(
        json.dumps({"chapters": [{"sections": [{"section_id": "ch1/sec1", "db_section_id": "sec_db_1", "section_type": "evidence_synthesis"}]}]}),
        encoding="utf-8",
    )
    (tmp_path / "final.bibliography.json").write_text("[]", encoding="utf-8")
    
    eval_payload = {
        "run_id": "run-test",
        "source_count": 1,
        "evidence_count": 1,
        "claim_count": 1,
        "section_count": 1,
        "unsupported_rate": 0.0,
        "citation_accuracy": 1.0,
        "status": "passed",
        "output_dir": str(tmp_path),
        "final_md": str(tmp_path / "final.md"),
    }
    eval_json_path = tmp_path / "eval.json"
    eval_json_path.write_text(json.dumps(eval_payload), encoding="utf-8")

    # Case A: No figures file -> Pass (fail-open)
    res = evaluate_artifacts(eval_json_path)
    assert res["ok"]
    assert not res["errors"]

    # Case B: Valid figures file -> Pass
    valid_figures = [
        {
            "figure_id": "fig_1",
            "title": "Architecture",
            "figure_type": "architecture_diagram",
            "grounding_ids": ["cl_1", "ev_1"],
            "spec_data": {
                "nodes": [{"id": "n1", "grounding_id": "cl_1"}],
                "edges": [{"source": "n1", "target": "n2", "grounding_id": "ev_1"}]
            }
        }
    ]
    claims_full = [{"id": "cl_1", "claim_text": "Good claim text goes here for validation."}]
    evidence_full = [{"id": "ev_1", "span_text": "Abstract: Continuous thought and hidden-state reasoning can reduce dependence."}]

    _setup_mock_run(tmp_path, claims_full, evidence_full, valid_figures)
    res = evaluate_artifacts(eval_json_path)
    assert res["ok"]
    assert not res["errors"]

    # Case C: Invalid figures file -> FAIL
    invalid_figures = [
        {
            "figure_id": "fig_1",
            "title": "Architecture",
            "figure_type": "architecture_diagram",
            "grounding_ids": ["cl_1", "ev_missing"],
            "spec_data": {
                "nodes": [{"id": "n1", "grounding_id": "cl_1"}],
                "edges": [{"source": "n1", "target": "n2"}]
            }
        }
    ]
    _setup_mock_run(tmp_path, claims_full, evidence_full, invalid_figures)
    res = evaluate_artifacts(eval_json_path)
    assert not res["ok"]
    assert any("figure_grounding_unresolved" in err for err in res["errors"])

    # Case D: Hard fail check on closeout gate
    closeout_res = evaluate_final_closeout(tmp_path, strict=True)
    assert closeout_res["verdict"] == "hard_fail"
    assert any(iss.startswith("figure_") for iss in closeout_res["issues"])
