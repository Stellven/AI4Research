from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any


HARNESS = (Path(__file__).resolve().parents[2] / 'harness')
REPO = HARNESS.parent
AUDIT = REPO / "docs" / "integrations" / "autosci" / "phase-c-premerge-readiness-audit.v1.json"
MANIFEST = REPO / "docs" / "integrations" / "autosci" / "phase-c-solar-unification-import-manifest.v1.json"
CI_WORKFLOW = REPO / ".github" / "workflows" / "solar-ci.yml"
GATE_SCRIPT = REPO / "tests" / "harness" / "test_autosci_premerge_gate.sh"
SOLAR_HARNESS = HARNESS / "solar-harness.sh"
SHIM = HARNESS / "plugins" / "autosci" / "bin" / "autosci_skill_shim.py"
SHIM_TEST = REPO / "tests" / "plugins" / "autosci" / "test_autosci_skill_shim.py"
ROUTE_CONFIG = HARNESS / "plugins" / "autosci" / "config" / "feature_parity_routes.v1.json"
SKILL_ROOT = REPO / ".agents" / "skills"

REQUIRED_P0_ITEMS = {
    "p0_1_product_autosci_dispatch",
    "p0_2_agent_skill_wrappers",
    "p0_3_product_level_smoke_tests",
    "p0_4_research_scheduler_demo",
    "p0_5_tracked_artifact_cleanup",
}
REQUIRED_CURRENT_BRANCH_SMOKES = {
    "tests/harness/integration/test_autosci_routes_list.py",
    "tests/harness/integration/test_autosci_cli_dispatch.py",
    "tests/harness/integration/test_autosci_ingest_demo.py",
    "tests/harness/integration/test_autosci_review_demo.py",
    "tests/harness/integration/test_autosci_research_scheduler_demo.py",
    "tests/harness/integration/test_autosci_artifact_root.py",
}


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _git_ls_files(pathspec: str) -> list[str]:
    proc = subprocess.run(
        ["git", "ls-files", pathspec],
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return [line for line in proc.stdout.splitlines() if line]


def test_premerge_readiness_audit_records_ready_but_no_merge_started() -> None:
    payload = _load_json(AUDIT)

    assert payload["schema"] == "autosci_phase_c_premerge_readiness_audit.v1"
    assert payload["status"] == "ready_for_integration_branch_premerge"
    assert payload["source_inputs"]["latest_attachment"].endswith("/3735d5e6-b4f4-4abf-a7d3-c368f88a54f0/pasted-text.txt")
    assert payload["source_inputs"]["prior_attachment"].endswith("/d1462411-4aa9-4a88-8f05-5410e3e21707/pasted-text.txt")
    assert payload["source_inputs"]["updated_plan"].endswith("/AutoSci_Solar_Prioritized_Integration_Plan_2026-06-30.md")

    decision = payload["decision"]
    assert decision["can_start_integration_merge_branch"] is True
    assert decision["direct_product_branch_merge_recommended"] is False
    assert decision["boss_demo_preconditions_present_in_source_branch"] is True
    assert decision["full_autosci_parity_complete"] is False
    assert "explicitly asks" in decision["next_step"]

    merge_activity = payload["merge_activity"]
    assert merge_activity == {
        "integration_branch_created": False,
        "stellven_product_branch_modified": False,
        "fetch_or_merge_performed": False,
        "git_maintenance_or_repack_performed": False,
    }


def test_premerge_readiness_audit_matches_current_product_glue() -> None:
    payload = _load_json(AUDIT)
    p0 = {item["id"]: item for item in payload["attachment_p0_reconciliation"]}
    assert REQUIRED_P0_ITEMS <= set(p0)
    assert all(item["status"] == "ok" for item in p0.values())

    solar_text = SOLAR_HARNESS.read_text(encoding="utf-8")
    assert "do_autosci_command()" in solar_text
    assert re.search(r"^\s+autosci\)", solar_text, re.MULTILINE)
    assert re.search(r"^\s+\\\$\*\)", solar_text, re.MULTILINE)
    assert "autosci_skill_shim.py" in solar_text
    assert '"$py" "$shim" text "$command_text"' in solar_text

    smoke_paths = set(p0["p0_3_product_level_smoke_tests"]["current_branch_evidence"])
    assert REQUIRED_CURRENT_BRANCH_SMOKES <= smoke_paths
    for relative in REQUIRED_CURRENT_BRANCH_SMOKES:
        assert (REPO / relative).exists(), relative

    shim_text = SHIM.read_text(encoding="utf-8")
    shim_test_text = SHIM_TEST.read_text(encoding="utf-8")
    assert "--scheduler-demo" in shim_text
    assert "SCHEDULER_DEMO_NODE_IDS" in shim_text
    assert "test_autosci_skill_shim_research_scheduler_demo_uses_multi_node_preset" in shim_test_text


def test_agent_skill_wrappers_use_explicit_autosci_subcommand() -> None:
    payload = _load_json(AUDIT)
    assert payload["wrapper_policy"]["status"] == "ok"
    assert payload["wrapper_policy"]["direct_dollar_dispatch_supported_but_not_preferred_for_docs"] is True

    routes = _load_json(ROUTE_CONFIG)["routes"]
    skill_names = {route["native_skill"] for route in routes}
    assert len(skill_names) == 28

    for skill_name in skill_names:
        skill_path = SKILL_ROOT / skill_name / "SKILL.md"
        text = skill_path.read_text(encoding="utf-8")
        assert f"solar-harness.sh\" autosci '${skill_name} <user args>'" in text, skill_name
        assert f"solar-harness autosci '${skill_name} <user args>'" in text, skill_name
        assert f"solar-harness.sh\" '${skill_name}' <user args>" not in text, skill_name
        assert f"solar-harness '${skill_name}' <user args>" not in text, skill_name


def test_generated_artifacts_remain_untracked_for_premerge() -> None:
    payload = _load_json(AUDIT)
    cleanup = payload["tracked_generated_artifacts"]
    assert cleanup["status"] == "ok"

    for pattern in cleanup["must_remain_untracked_patterns"]:
        assert _git_ls_files(pattern) == [], pattern


def test_local_ci_premerge_gate_is_wired_without_merge_activity() -> None:
    payload = _load_json(AUDIT)
    gate = payload["local_ci_gate"]
    assert gate == {
        "status": "wired",
        "script_path": "tests/harness/test_autosci_premerge_gate.sh",
        "ci_workflow_path": ".github/workflows/solar-ci.yml",
        "ci_job": "autosci-premerge-gate",
        "runs_current_branch_contracts": True,
        "runs_product_level_smokes": True,
        "runs_scheduler_demo_shim_tests": True,
        "checks_generated_artifact_tracking": True,
        "checks_git_connectivity": True,
        "starts_merge_branch": False,
        "fetches_or_merges_stellven": False,
        "claims_full_autosci_parity": False,
    }

    script_text = GATE_SCRIPT.read_text(encoding="utf-8")
    workflow_text = CI_WORKFLOW.read_text(encoding="utf-8")
    assert "test_autosci_phase_c_premerge_readiness.py" in script_text
    assert "test_autosci_routes_list.py" in script_text
    assert "test_autosci_research_scheduler_demo.py" in script_text
    assert "test_autosci_skill_shim_research_scheduler_demo_uses_multi_node_preset" in script_text
    assert "git fsck --connectivity-only --no-dangling" in script_text
    assert "autosci-premerge-gate:" in workflow_text
    assert "bash tests/harness/test_autosci_premerge_gate.sh" in workflow_text

    forbidden = (
        "git fetch",
        "git merge",
        "git maintenance",
        "git repack",
        "git checkout -b",
        "git switch -c",
        "gh pr merge",
    )
    for needle in forbidden:
        assert needle not in script_text


def test_phase_c_manifest_references_premerge_readiness_audit() -> None:
    manifest = _load_json(MANIFEST)
    audit_ref = manifest["premerge_readiness_audit"]
    assert audit_ref == {
        "path": "docs/integrations/autosci/phase-c-premerge-readiness-audit.v1.json",
        "test_path": "tests/harness/test_autosci_phase_c_premerge_readiness.py",
        "status": "ready_for_integration_branch_premerge",
        "does_not_claim_stellven_merge_executed": True,
        "does_not_start_merge_branch": True,
    }
    assert (REPO / audit_ref["path"]).exists()
    assert (REPO / audit_ref["test_path"]).exists()
