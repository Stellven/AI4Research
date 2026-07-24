"""Structural validation for Phase 22 contract-derived L2 test-case designs.

This suite validates the design inventory only. It does not report product-feature
pass/fail results; behavioral adapters still need to implement each designed case.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path


TESTS_ROOT = Path(__file__).resolve().parents[2]
CATEGORY_DIRS = ("workflow", "foundation", "vertical")
EXPECTED_MANIFESTS = 60
EXPECTED_SEED_TESTS = 180
EXPECTED_ATOMIC_CASES = 490
REQUIRED_CONTRACT_FIELDS = {
    "purpose_user_function",
    "valid_inputs",
    "expected_outputs",
    "state_side_effects",
    "failure_rejection_behavior",
    "supported_boundaries_exclusions",
    "success_evidence",
    "granularity_atomic_contracts",
    "readme_product_docs",
    "cli_api_skill_interfaces",
    "config_schemas",
    "implementation_entrypoints",
    "platform_provider_limitations",
}
REQUIRED_CASE_FIELDS = {
    "case_id",
    "test_name",
    "case_type",
    "atomic_scenario",
    "source_seed_registry_id",
    "source_atomic_feature_id",
    "source_seed_test_name",
    "objective",
    "focused_input",
    "preconditions",
    "procedure",
    "expected_result",
    "state_and_side_effect_oracle",
    "required_evidence",
    "supported_boundary",
    "execution_status",
}


def load_manifests():
    paths = []
    for category in CATEGORY_DIRS:
        paths.extend((TESTS_ROOT / category).rglob("phase22_*_cases.json"))
    return [(path, json.loads(path.read_text(encoding="utf-8"))) for path in sorted(paths)]


class Phase22L2CaseSpecificationTests(unittest.TestCase):
    def setUp(self):
        self.manifests = load_manifests()

    def test_contract_gated_manifest_inventory_is_complete(self):
        self.assertEqual(EXPECTED_MANIFESTS, len(self.manifests))
        feature_keys = {
            (item["feature"]["sheet"], item["feature"]["level_1"], item["feature"]["level_2"])
            for _, item in self.manifests
        }
        self.assertEqual(EXPECTED_MANIFESTS, len(feature_keys))
        for path, item in self.manifests:
            self.assertIn("Contract-gated", item["generation_policy"], path)
            self.assertEqual(REQUIRED_CONTRACT_FIELDS, set(item["contract"]), path)
            self.assertTrue(all(str(value).strip() for value in item["contract"].values()), path)

    def test_all_seed_tests_are_concretized_by_atomic_scenarios(self):
        seed_ids = set()
        case_count = 0
        for path, item in self.manifests:
            seeds = item["source_seed_tests"]
            self.assertEqual(3, len(seeds), path)
            manifest_seed_ids = {seed["registry_id"] for seed in seeds}
            seed_ids.update(manifest_seed_ids)
            cases = item["cases"]
            self.assertEqual(item["case_count"], len(cases), path)
            self.assertGreaterEqual(len(cases), 3, path)
            case_count += len(cases)
            self.assertEqual(manifest_seed_ids, {case["source_seed_registry_id"] for case in cases}, path)
        self.assertEqual(EXPECTED_SEED_TESTS, len(seed_ids))
        self.assertEqual(EXPECTED_ATOMIC_CASES, case_count)

    def test_case_names_ids_and_oracles_are_actionable(self):
        case_ids = set()
        test_names = set()
        for path, item in self.manifests:
            for case in item["cases"]:
                self.assertEqual(REQUIRED_CASE_FIELDS, set(case), (path, case.get("case_id")))
                self.assertNotIn(case["case_id"], case_ids)
                self.assertNotIn(case["test_name"], test_names)
                case_ids.add(case["case_id"])
                test_names.add(case["test_name"])
                self.assertRegex(case["test_name"], r"^test_[a-z0-9_]+$")
                self.assertIn(case["case_type"], {"core_behavior", "input_guardrail", "evidence_auditability"})
                self.assertGreaterEqual(len(case["procedure"]), 4)
                for field in ("atomic_scenario", "objective", "focused_input", "expected_result", "required_evidence"):
                    self.assertTrue(str(case[field]).strip(), (path, case["case_id"], field))

    def test_current_implementation_surfaces_are_tracked_files(self):
        repo_root = TESTS_ROOT.parent
        for path, item in self.manifests:
            implementation = item["implementation"]
            if implementation["status"] == "NOT_FOUND_IN_CURRENT_CODEBASE":
                self.assertTrue(all(case["execution_status"] == "BLOCKED_NO_CURRENT_IMPLEMENTATION" for case in item["cases"]), path)
                continue
            self.assertTrue(implementation["tracked_surfaces"], path)
            for relative_surface in implementation["tracked_surfaces"]:
                surface = (repo_root / relative_surface).resolve()
                self.assertTrue(surface.is_relative_to(repo_root.resolve()), (path, relative_surface))
                self.assertTrue(surface.is_file(), (path, relative_surface))
            self.assertTrue(all(case["execution_status"] == "DESIGNED_NOT_YET_IMPLEMENTED" for case in item["cases"]), path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
