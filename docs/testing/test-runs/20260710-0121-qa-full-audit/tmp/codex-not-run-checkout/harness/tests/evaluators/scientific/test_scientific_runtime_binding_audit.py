from __future__ import annotations

import json
from pathlib import Path

import yaml

from tools.audit_scientific_runtime_bindings import AuditPaths, run_audit


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")


def _minimal_tree(tmp_path: Path) -> tuple[Path, AuditPaths]:
    workflow = tmp_path / "workflows/scientific_paper_ingestion_v1.json"
    _write_json(
        workflow,
        {
            "workflow_id": "scientific_paper_ingestion_v1",
            "nodes": [
                {
                    "id": "paper_ingest",
                    "logical_operator": "ScientificPaperIngestor",
                    "required_capabilities": ["cap.research-paper-ingest"],
                    "evidence_policy": {"expected_schema": "research_paper.v1"},
                    "gate": "G_PAPER_INGEST",
                }
            ],
        },
    )
    logical = tmp_path / "config/logical-operators.json"
    _write_json(
        logical,
        {
            "logical_operators": {"ScientificPaperIngestor": {"operator_type": "ScientificPaperIngestor"}},
            "bindings": {
                "ScientificPaperIngestor": {
                    "candidates": [{"actor_id": "autosci-paper-ingest-worker", "condition": "plugin_autosci_available"}]
                }
            },
        },
    )
    physical = tmp_path / "config/physical-operators.json"
    _write_json(
        physical,
        {
            "operators": {
                "autosci-paper-ingest-worker": {
                    "owner_host": "local-autosci",
                    "command": "python3 \"$HARNESS_DIR/plugins/autosci/bin/autosci_bridge.py\" run --action ingest_paper --envelope \"$SOLAR_OPERATOR_ENVELOPE_JSON\"",
                    "compat_maps_to": {"host_type": "local_command_worker"},
                }
            }
        },
    )
    hosts = tmp_path / "config/actor-hosts.json"
    _write_json(hosts, {"hosts": {"local-autosci": {"host_type": "local_command_worker"}}})
    manifest = tmp_path / "plugins/autosci/manifest.yaml"
    _write_yaml(manifest, {"capabilities": ["cap.research-paper-ingest"]})
    bridge = tmp_path / "plugins/autosci/bin/autosci_bridge.py"
    bridge.parent.mkdir(parents=True, exist_ok=True)
    bridge.write_text('ACTIONS: dict[str, object] = {\n    "ingest_paper": object(),\n}\n', encoding="utf-8")
    schemas = tmp_path / "schemas/evidence"
    schemas.mkdir(parents=True)
    (schemas / "research_paper.v1.schema.json").write_text("{}\n", encoding="utf-8")
    gates = tmp_path / "evaluators/scientific"
    gates.mkdir(parents=True)
    (gates / "paper_gate.py").write_text("# gate\n", encoding="utf-8")
    return workflow, AuditPaths(
        logical_operators=logical,
        physical_operators=physical,
        actor_hosts=hosts,
        plugin_manifest=manifest,
        bridge=bridge,
        schemas_dir=schemas,
        gates_dir=gates,
    )


def test_scientific_runtime_binding_audit_accepts_complete_chain(tmp_path: Path) -> None:
    workflow, paths = _minimal_tree(tmp_path)

    report = run_audit([workflow], paths)

    assert report["ok"] is True
    assert report["issue_count"] == 0
    assert report["checked_node_count"] == 1


def test_scientific_runtime_binding_audit_reports_missing_chain_parts(tmp_path: Path) -> None:
    workflow, paths = _minimal_tree(tmp_path)
    physical = json.loads(paths.physical_operators.read_text(encoding="utf-8"))
    physical["operators"]["autosci-paper-ingest-worker"]["owner_host"] = "solar@example-host"
    physical["operators"]["autosci-paper-ingest-worker"]["command"] = "python3 bridge.py run --action missing_action --envelope x"
    _write_json(paths.physical_operators, physical)
    logical = json.loads(paths.logical_operators.read_text(encoding="utf-8"))
    logical["bindings"]["ScientificPaperIngestor"]["candidates"][0]["condition"] = "backend_action_pending"
    _write_json(paths.logical_operators, logical)

    report = run_audit([workflow], paths)
    codes = {issue["code"] for issue in report["issues"]}

    assert report["ok"] is False
    assert "missing_host" in codes
    assert "stale_binding_condition" in codes
    assert "unknown_bridge_action" in codes


def test_scientific_runtime_binding_audit_rejects_wrong_node_action(tmp_path: Path) -> None:
    workflow, paths = _minimal_tree(tmp_path)
    physical = json.loads(paths.physical_operators.read_text(encoding="utf-8"))
    physical["operators"]["autosci-paper-ingest-worker"]["command"] = (
        "python3 \"$HARNESS_DIR/plugins/autosci/bin/autosci_bridge.py\" "
        "run --action extract_claims --envelope \"$SOLAR_OPERATOR_ENVELOPE_JSON\""
    )
    _write_json(paths.physical_operators, physical)
    paths.bridge.write_text(
        'ACTIONS: dict[str, object] = {\n'
        '    "ingest_paper": object(),\n'
        '    "extract_claims": object(),\n'
        '}\n',
        encoding="utf-8",
    )

    report = run_audit([workflow], paths)
    codes = {issue["code"] for issue in report["issues"]}

    assert report["ok"] is False
    assert "unexpected_bridge_action" in codes
