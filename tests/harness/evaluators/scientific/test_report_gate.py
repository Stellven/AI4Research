from pathlib import Path
import copy
import hashlib
import json

from evaluators.scientific import publication_gate, report_gate
from evaluators.scientific.common import load_json

FIXTURES = (Path(__file__).resolve().parents[4] / 'tests' / 'harness' / 'evaluators' / 'scientific') / "fixtures"


def test_report_gate_accepts_evidence_linked_report():
    result = report_gate.evaluate(load_json(FIXTURES / "pass/scientific_report.json"))

    assert result.ok is True
    assert result.status == "passed"
    assert result.reasons == []


def test_report_gate_rejects_unsupported_or_evidence_free_report():
    result = report_gate.evaluate(load_json(FIXTURES / "fail/scientific_report.json"))

    assert result.ok is False
    assert result.status == "failed"
    joined = " ".join(result.reasons)
    assert "evidence_ids" in joined
    assert "unsupported_claims" in joined


def test_publication_gate_accepts_file_linked_bundle():
    result = publication_gate.evaluate(load_json(FIXTURES / "pass/publication_bundle.json"))

    assert result.ok is True
    assert result.status == "passed"
    assert result.reasons == []


def test_publication_gate_rejects_missing_files_and_source_report_link():
    result = publication_gate.evaluate(load_json(FIXTURES / "fail/publication_bundle.json"))

    assert result.ok is False
    assert result.status == "failed"
    joined = " ".join(result.reasons)
    assert "files" in joined
    assert "source_report_id" in joined


def test_publication_gate_enforces_exact_manifest_and_machine_readable_fields(tmp_path):
    report_path = tmp_path / "report.md"
    matrix_path = tmp_path / "evidence_matrix.csv"
    report_path.write_text("# Report\n\nEvidence-grounded result.\n", encoding="utf-8")
    matrix_path.write_text("source_id,claim\npaper-1,Supported claim\n", encoding="utf-8")
    manifest = {
        "output_root": "Downloads/demo_outputs/landscape",
        "exact_file_set": True,
        "files": [
            {
                "file_id": "report",
                "relative_path": "report.md",
                "media_type": "text/markdown",
                "description": "Report",
                "content_requirements": ["Non-empty"],
                "required_fields": [],
                "source_refs": ["D1"],
                "required": True,
            },
            {
                "file_id": "matrix",
                "relative_path": "evidence_matrix.csv",
                "media_type": "text/csv",
                "description": "Matrix",
                "content_requirements": ["One row per source"],
                "required_fields": ["source_id", "claim"],
                "source_refs": ["D1"],
                "required": True,
            },
        ],
    }
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_digest = hashlib.sha256(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    payload = {
        "schema": "publication_bundle.v1",
        "task_id": "task",
        "sprint_id": "sprint",
        "node_id": "publication",
        "status": "completed",
        "inputs": {},
        "outputs": {"bundle": {
            "bundle_id": "bundle",
            "publication_type": "mixed",
            "files": [
                {"type": "text/markdown", "path": "report.md", "sha256": digest(report_path), "manifest_relative_path": "report.md"},
                {"type": "text/csv", "path": "evidence_matrix.csv", "sha256": digest(matrix_path), "manifest_relative_path": "evidence_matrix.csv"},
            ],
            "source_report_id": "report-1",
            "evidence_ids": ["report-1", "paper-1"],
            "delivery_manifest": manifest,
            "delivery_manifest_sha256": manifest_digest,
        }},
        "artifacts": [
            {"type": "publication_output", "path": "report.md", "sha256": digest(report_path)}
        ],
        "provenance": {
            "operator_id": "producer",
            "implementation_package": "test",
            "timestamp": "2026-09-02T00:00:00Z",
        },
        "limitations": ["Bounded fixture."],
    }
    evidence_path = tmp_path / "publication_bundle.v1.json"
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")
    assert publication_gate.evaluate(payload, path=evidence_path).ok is True

    missing = copy.deepcopy(payload)
    missing["outputs"]["bundle"]["files"].pop()
    result = publication_gate.evaluate(missing, path=evidence_path)
    assert result.ok is False
    assert "exactly match" in " ".join(result.reasons)

    run_manifest_path = tmp_path / "research_run_manifest.json"
    run_manifest_path.write_text(
        json.dumps({
            "closure_status": "open_degraded",
            "evidence_gate": {
                "status": "failed_for_full_requested_scope",
                "failed_gates": ["minimum source coverage was not achieved"],
            },
        }),
        encoding="utf-8",
    )
    declared_failure = copy.deepcopy(payload)
    declared_failure_manifest = declared_failure["outputs"]["bundle"]["delivery_manifest"]
    declared_failure_manifest["files"].append({
        "file_id": "research_run_manifest",
        "relative_path": "research_run_manifest.json",
        "media_type": "application/json",
        "description": "Research run manifest",
        "content_requirements": ["Record the evidence gate outcome"],
        "required_fields": ["evidence_gate", "closure_status"],
        "source_refs": ["D1"],
        "required": True,
    })
    declared_failure["outputs"]["bundle"]["files"].append({
        "type": "application/json",
        "path": "research_run_manifest.json",
        "sha256": digest(run_manifest_path),
        "manifest_relative_path": "research_run_manifest.json",
    })
    declared_failure["outputs"]["bundle"]["delivery_manifest_sha256"] = hashlib.sha256(
        json.dumps(
            declared_failure_manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    result = publication_gate.evaluate(declared_failure, path=evidence_path)
    assert result.ok is False
    assert "declares evidence gate failed" in " ".join(result.reasons)


def test_publication_gate_resolves_workspace_and_private_paths_from_nested_output(tmp_path):
    workdir = tmp_path / "run" / "workdir"
    output_root = workdir / "workspace" / "demo_outputs" / "landscape"
    private_root = workdir / "private" / "report"
    output_root.mkdir(parents=True)
    private_root.mkdir(parents=True)
    report_path = output_root / "report.md"
    source_path = private_root / "scientific_report.json"
    report_path.write_text("# Report\n\nEvidence-grounded result.\n", encoding="utf-8")
    source_path.write_text("{}\n", encoding="utf-8")
    digest = lambda target: hashlib.sha256(target.read_bytes()).hexdigest()
    payload = {
        "schema": "publication_bundle.v1",
        "task_id": "task",
        "sprint_id": "sprint",
        "node_id": "publication",
        "status": "completed",
        "inputs": {},
        "outputs": {"bundle": {
            "bundle_id": "bundle",
            "publication_type": "mixed",
            "files": [{
                "type": "text/markdown",
                "path": "workspace/demo_outputs/landscape/report.md",
                "sha256": digest(report_path),
            }],
            "source_report_id": "report-1",
            "evidence_ids": ["report-1"],
        }},
        "artifacts": [{
            "type": "input_evidence",
            "path": "private/report/scientific_report.json",
            "sha256": digest(source_path),
        }],
        "provenance": {
            "operator_id": "producer",
            "implementation_package": "test",
            "timestamp": "2026-09-02T00:00:00Z",
        },
        "limitations": ["Bounded fixture."],
    }
    evidence_path = output_root / "publication_bundle.v1.json"
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")

    assert publication_gate.evaluate(payload, path=evidence_path).ok is True
