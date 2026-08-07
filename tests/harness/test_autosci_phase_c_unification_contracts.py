from __future__ import annotations

import fnmatch
import json
from pathlib import Path
from typing import Any


HARNESS = (Path(__file__).resolve().parents[2] / 'harness')
REPO = HARNESS.parent
MANIFEST = REPO / "docs" / "integrations" / "autosci" / "phase-c-solar-unification-import-manifest.v1.json"

REQUIRED_IMPORT_GROUPS = {
    "autosci_plugin_runtime",
    "scientific_tools",
    "scientific_workflows",
    "scientific_evaluators_and_evidence_schemas",
    "research_capability_capsules",
    "autosci_agent_skill_wrappers",
    "curated_design_docs",
}
REQUIRED_EXCLUDE_PATTERNS = {
    ".git/**",
    ".DS_Store",
    "**/.DS_Store",
    "**/__pycache__/**",
    "**/*.pyc",
    "harness/artifacts/autosci/runs/**",
    "harness/artifacts/autosci/operator-smoke/**",
    "harness/.coordinator*",
    "harness/.watchdog*",
    "harness/.pane-*",
    "harness/PLANNER-INBOX.md",
}
REQUIRED_MANUAL_MERGE_FILES = {
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
    "bin/solar",
    "harness/solar-harness.sh",
    "core/daemon/skill-dispatcher.ts",
    "harness/config/logical-operators.json",
    "harness/config/physical-operators.json",
    "harness/config/capability-capsules.registry.yaml",
}
REQUIRED_UNIFIED_SMOKE_TESTS = {
    "tests/integration/test_autosci_routes_list.py",
    "tests/integration/test_autosci_cli_dispatch.py",
    "tests/integration/test_autosci_ingest_demo.py",
    "tests/integration/test_autosci_review_demo.py",
    "tests/integration/test_autosci_research_scheduler_demo.py",
    "tests/integration/test_autosci_artifact_root.py",
}
REQUIRED_CURRENT_BRANCH_SMOKE_TESTS = {
    "tests/harness/integration/test_autosci_routes_list.py",
    "tests/harness/integration/test_autosci_cli_dispatch.py",
    "tests/harness/integration/test_autosci_ingest_demo.py",
    "tests/harness/integration/test_autosci_review_demo.py",
    "tests/harness/integration/test_autosci_research_scheduler_demo.py",
    "tests/harness/integration/test_autosci_artifact_root.py",
}


def _payload() -> dict[str, Any]:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _matches_any(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def test_phase_c_manifest_identifies_base_source_and_non_wholesale_policy() -> None:
    payload = _payload()

    assert payload["schema"] == "autosci_solar_unification_import_manifest.v1"
    assert payload["status"] == "premerge_contract"
    assert payload["base"] == {
        "repository": "Stellven/AI4Research",
        "branch": "openJiuwen-Solar",
        "role": "product_install_desktop_distribution_runtime",
    }
    assert payload["source"] == {
        "repository": "Coconut-ch1ken/OpenSolar",
        "branch": "feature/autosci-solar-native",
        "role": "autosci_scientific_runtime",
    }
    merge_policy = payload["merge_policy"]
    assert merge_policy["strategy"] == "selective_import_then_manual_merge"
    assert merge_policy["wholesale_copy_allowed"] is False
    assert merge_policy["overwrite_product_runtime_files_allowed"] is False
    assert merge_policy["git_auto_maintenance_required_disabled_before_merge"] is True


def test_phase_c_manifest_import_groups_point_to_existing_autosci_assets() -> None:
    payload = _payload()
    groups = {group["id"]: group for group in payload["import_groups"]}
    assert REQUIRED_IMPORT_GROUPS <= set(groups)

    excludes = payload["exclude_patterns"]
    for group in groups.values():
        assert group["policy"]
        for relative in group["paths"]:
            assert not relative.startswith("/")
            assert not _matches_any(relative, excludes), f"{relative} is excluded from import"
            path = REPO / relative.rstrip("/")
            assert path.exists(), relative
        for pattern in group.get("required_globs", []):
            assert not pattern.startswith("/")
            matches = sorted(REPO.glob(pattern))
            assert matches, pattern
            for match in matches:
                relative = match.relative_to(REPO).as_posix()
                assert not _matches_any(relative, excludes), relative

    skill_group = groups["autosci_agent_skill_wrappers"]
    for skill_name in skill_group["required_skill_names"]:
        assert (REPO / ".agents" / "skills" / skill_name / "SKILL.md").exists(), skill_name


def test_phase_c_manifest_excludes_generated_and_local_runtime_state() -> None:
    payload = _payload()
    excludes = set(payload["exclude_patterns"])
    assert REQUIRED_EXCLUDE_PATTERNS <= excludes

    generated_examples = [
        ".git/objects/pack/.tmp-example",
        ".DS_Store",
        "harness/plugins/autosci/bin/__pycache__/autosci_skill_shim.cpython-314.pyc",
        "harness/artifacts/autosci/runs/example/autosci_skill_run.json",
        "harness/artifacts/autosci/operator-smoke/example.json",
        "harness/.coordinator-state",
        "harness/.pane-restart-state",
        "harness/PLANNER-INBOX.md",
    ]
    for relative in generated_examples:
        assert _matches_any(relative, list(excludes)), relative


def test_phase_c_manifest_marks_shared_product_files_manual_merge_only() -> None:
    payload = _payload()
    manual_entries = {entry["path"]: entry for entry in payload["manual_merge_files"]}
    assert REQUIRED_MANUAL_MERGE_FILES <= set(manual_entries)

    for relative, entry in manual_entries.items():
        assert entry["policy"].startswith("manual_merge_only")
        assert entry["reason"]
        assert (REPO / relative).exists() is entry["current_source_branch_path_exists"], relative

    boundary = payload["skill_dispatcher_boundary"]
    assert boundary["path"] == "core/daemon/skill-dispatcher.ts"
    assert boundary["must_not_be_final_autosci_execution_path_until_extended"] is True
    assert "executed=false" in boundary["required_extension"]
    assert "shim" in boundary["required_extension"]


def test_phase_c_manifest_lists_unified_repo_smoke_tests_without_claiming_execution() -> None:
    payload = _payload()
    planned_tests = {entry["path"]: entry for entry in payload["integration_smoke_tests_to_create_in_unified_repo"]}
    assert set(planned_tests) == REQUIRED_UNIFIED_SMOKE_TESTS
    assert "research_paper.v1" in planned_tests["tests/integration/test_autosci_ingest_demo.py"]["minimum_assertion"]
    assert "artifact_review.v1" in planned_tests["tests/integration/test_autosci_review_demo.py"]["minimum_assertion"]
    assert "scientific_lifecycle.v1" in planned_tests[
        "tests/integration/test_autosci_research_scheduler_demo.py"
    ]["minimum_assertion"]
    assert "unified HARNESS_DIR" in planned_tests["tests/integration/test_autosci_artifact_root.py"][
        "minimum_assertion"
    ]
    current_branch_tests = {entry["current_branch_test_path"] for entry in planned_tests.values()}
    assert current_branch_tests == REQUIRED_CURRENT_BRANCH_SMOKE_TESTS
    for relative in current_branch_tests:
        assert (REPO / relative).exists(), relative

    helper = payload["current_branch_product_smoke_helper"]
    assert helper["path"] == "tests/harness/integration/autosci_product_smoke_helpers.py"
    assert (REPO / helper["path"]).exists()

    existing_contracts = payload["existing_branch_contract_tests"]
    for entry in existing_contracts:
        assert (REPO / entry["path"]).exists(), entry["path"]

    readiness = payload["premerge_readiness_audit"]
    assert readiness == {
        "path": "docs/integrations/autosci/phase-c-premerge-readiness-audit.v1.json",
        "test_path": "tests/harness/test_autosci_phase_c_premerge_readiness.py",
        "status": "ready_for_integration_branch_premerge",
        "does_not_claim_stellven_merge_executed": True,
        "does_not_start_merge_branch": True,
    }
    assert (REPO / readiness["path"]).exists()
    assert (REPO / readiness["test_path"]).exists()

    verification_policy = payload["verification_policy"]
    assert verification_policy["premerge_manifest_only"] is True
    assert verification_policy["does_not_claim_stellven_merge_executed"] is True
    assert verification_policy["current_branch_product_smokes_present"] is True
    assert verification_policy["unified_repo_smoke_required_after_import"] is True
    assert verification_policy["publication_or_analysis_success_must_not_be_claimed_without_evidence"] is True

    cleanup = payload["tracked_generated_artifact_cleanup"]
    assert cleanup["status"] == "cleaned_in_source_branch_index"
    assert cleanup["cleanup_mode"] == "git rm --cached; local files preserved by .gitignore"
    assert cleanup["tracked_before_cleanup"]["harness/artifacts/autosci/runs/**"] > 0
    assert "harness/artifacts/autosci/runs/**" in cleanup["must_remain_untracked_patterns"]
