from __future__ import annotations

import json
import unittest
from pathlib import Path

from migration_test.adapter import AI4ResearchPhase0ArtifactAdapter
from migration_test.comparator import compare_contract_to_observed
from migration_test.schemas import (
    BenchmarkContract,
    ClaimComparison,
    ObservedMetric,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "skillgen_phase0_fixture.json"


class MigrationPipelineTest(unittest.TestCase):
    def test_golden_fixture_replay_preserves_phase0_conclusion(self) -> None:
        bundle = AI4ResearchPhase0ArtifactAdapter().load_fixture(FIXTURE)

        self.assertEqual(bundle.summary.paper_level_status, "not_reproduced")
        self.assertEqual(bundle.summary.full_paper_claim_status, "blocked")
        self.assertEqual(
            bundle.summary.claim_status_counts,
            {
                "partially_reproduced": 3,
                "blocked": 7,
                "not_reproduced": 2,
            },
        )
        self.assertEqual(len(bundle.claims), 12)
        self.assertEqual(len(bundle.contracts), 12)
        self.assertEqual(len(bundle.comparisons), 12)
        self.assertEqual(bundle.benchmark_run_result["verdict"], "not_reproduced")

    def test_readiness_cannot_upgrade_claim_verdict(self) -> None:
        with self.assertRaisesRegex(ValueError, "require observed metrics"):
            ClaimComparison(
                claim_id="claim_ready_only",
                contract_id="contract_ready_only",
                observed_metric_ids=(),
                claim_verdict_status="partially_reproduced",
                execution_readiness_status="ready",
                evidence_ids=("artifact:plan",),
                mismatch_summary="Ready is not evidence.",
                limitations=(),
                comparison_basis="readiness_only",
            )

    def test_observed_metric_requires_source_artifacts(self) -> None:
        with self.assertRaisesRegex(ValueError, "source_artifact_ids"):
            ObservedMetric(
                observed_metric_id="metric_missing_source",
                run_id="run",
                metric_name="accuracy_delta",
                observed_value=0.1,
                dataset="mcp_bench_single",
                split="test",
                config="model",
                source_artifact_ids=(),
                parser_confidence=1.0,
            )

    def test_reconstructed_contract_caps_positive_result_at_partial(self) -> None:
        contract = BenchmarkContract(
            contract_id="contract_reconstructed",
            claim_id="claim_reconstructed",
            runnable_target="reconstructed_path",
            metric_definition="Delta accuracy",
            aggregation_rule="single smoke",
            tolerance=0.0,
            comparison_logic="delta_positive",
            required_artifacts=("eval_results.json",),
            human_approval_state="approved",
            reconstructed_path=True,
            deviation_notes=("Reconstructed smoke only.",),
        )
        metric = ObservedMetric(
            observed_metric_id="metric_positive",
            run_id="run",
            metric_name="accuracy_delta",
            observed_value=0.2,
            dataset="mcp_bench_single",
            split="test",
            config="model",
            source_artifact_ids=("artifact:eval_results",),
            parser_confidence=1.0,
        )

        comparison = compare_contract_to_observed(
            contract,
            (metric,),
            readiness_status="ready",
            evidence_ids=("artifact:eval_results", "metric_positive"),
        )

        self.assertEqual(comparison.claim_verdict_status, "partially_reproduced")
        self.assertEqual(comparison.comparison_basis, "executed_reconstructed_smoke")

    def test_config_fragments_exist_and_name_missing_solar_components(self) -> None:
        capsule = ROOT / "config" / "capability-capsules" / "cap.phase0-claim-verification.yaml"
        registry = ROOT / "config" / "capability-capsules.registry.fragment.yaml"
        logical = ROOT / "config" / "logical-operators.fragment.json"
        schema = ROOT / "schemas" / "phase0_claim_verification.schema.json"

        self.assertIn("cap.phase0-claim-verification", capsule.read_text(encoding="utf-8"))
        self.assertIn("cap.phase0-claim-verification", registry.read_text(encoding="utf-8"))
        self.assertIn("ResearchClaimVerifier", logical.read_text(encoding="utf-8"))

        payload = json.loads(schema.read_text(encoding="utf-8"))
        self.assertEqual(payload["title"], "Solar Phase 0 Claim Verification Fixture")


if __name__ == "__main__":
    unittest.main()
