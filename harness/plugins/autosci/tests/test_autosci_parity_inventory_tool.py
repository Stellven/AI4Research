from __future__ import annotations

import json
from pathlib import Path

from tools import autosci_parity_inventory


REQUIRED_FIELDS = {
    "route_count",
    "full_count",
    "partial_count",
    "gated_count",
    "missing_route_count",
    "manifest_registry_drift",
    "route_capabilities_missing_from_registry",
    "route_logical_operators_missing",
    "route_physical_operator_binding_missing",
    "route_evidence_schemas_missing",
    "route_backend_actions_missing",
    "route_gate_missing",
    "native_command_parity_by_command",
    "provider_live_proof_status",
    "remote_experiment_proof_status",
    "paper_compile_proof_status",
    "review_llm_proof_status",
}


def _native_repo(tmp_path: Path) -> Path:
    root = tmp_path / "AutoSci"
    for skill in ("ingest", "native-only"):
        skill_file = root / "i18n" / "en" / "skills" / skill / "SKILL.md"
        skill_file.parent.mkdir(parents=True, exist_ok=True)
        skill_file.write_text(f"# {skill}\n", encoding="utf-8")
    return root


def test_autosci_parity_inventory_reports_prompt_b_fields(tmp_path: Path) -> None:
    payload = autosci_parity_inventory.build_inventory(_native_repo(tmp_path))

    assert REQUIRED_FIELDS <= set(payload)
    assert payload["route_count"] >= 28
    assert payload["missing_route_count"] == 1
    assert payload["native_command_parity_by_command"]["/ingest"]["route_present"] is True
    assert payload["native_command_parity_by_command"]["/ingest"]["backend_action_registered"] is True
    assert payload["native_command_parity_by_command"]["/ingest"]["capability_registered"] is True
    assert payload["native_command_parity_by_command"]["/native-only"]["route_present"] is False
    assert payload["review_llm_proof_status"]["status"] in {"missing", "pending", "verified"}


def test_autosci_parity_inventory_cli_writes_json(tmp_path: Path, capsys) -> None:
    out = tmp_path / "inventory.json"

    code = autosci_parity_inventory.main(["--native-repo", str(_native_repo(tmp_path)), "--out", str(out)])

    assert code == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema"] == "autosci_parity_inventory.v1"
    assert payload["native_command_parity_by_command"]["/native-only"]["coverage_status"] == "missing"
    stdout = json.loads(capsys.readouterr().out)
    assert stdout["ok"] is True
