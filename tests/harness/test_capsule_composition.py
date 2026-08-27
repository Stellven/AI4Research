import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "harness" / "lib"
CAPSULE_DIR = ROOT / "harness" / "capability-capsules"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import capsule_composition as composition
import elastic_planner


REQUEST_ENVELOPE = "schema:request-envelope.schema.json"
PAPER = "schema:schemas/evidence/research_paper.v1.schema.json"
CLAIMS = "schema:schemas/evidence/research_claims.v1.schema.json"
METHODS = "schema:schemas/evidence/research_method.v1.schema.json"
IDEAS = "schema:schemas/evidence/idea_candidate.v1.schema.json"
IDEA_EVALUATION = "schema:schemas/evidence/idea_evaluation.v1.schema.json"
LITERATURE = "schema:schemas/evidence/literature_discovery.v1.schema.json"
EXPERIMENT_PLAN = "schema:schemas/evidence/experiment_plan.v1.schema.json"
EXPERIMENT_APPROVAL = "schema:schemas/evidence/experiment_approval.v1.schema.json"
EXPERIMENT_RESULT = "schema:schemas/evidence/experiment_result.v1.schema.json"
PUBLICATION_BUNDLE = "schema:schemas/evidence/publication_bundle.v1.schema.json"
CLAIM_VERDICT = "schema:schemas/evidence/claim_verdict.v1.schema.json"
REPORT = "schema:schemas/evidence/scientific_report.v1.schema.json"


def _catalog() -> dict:
    return elastic_planner.build_planning_catalog_snapshot()


def test_canonical_type_and_conversion_registries_are_explicit() -> None:
    artifact_registry = composition.load_artifact_type_registry()
    conversion_registry = composition.load_conversion_registry()
    identities = [row["artifact_type"] for row in artifact_registry["artifact_types"]]

    assert len(identities) == len(set(identities))
    assert {REQUEST_ENVELOPE, PAPER, CLAIMS, EXPERIMENT_RESULT}.issubset(identities)
    assert conversion_registry["conversions"] == []


def test_real_registry_audit_exposes_current_gaps_without_aliasing() -> None:
    audit = composition.build_registry_graph_audit(_catalog())
    codes = {row["code"] for row in audit["issues"]}

    assert audit["catalog_ref"]["sha256"]
    assert audit["artifact_registry_ref"]["sha256"]
    assert audit["conversion_registry_ref"]["sha256"]
    assert "ARTIFACT_TYPE_UNREGISTERED" not in codes
    assert "MISSING_PRODUCER" in codes
    assert "EMPTY_VERIFICATION_CONTRACT" in codes
    assert "FRAGMENTED_ARTIFACT_IDENTITY" in codes
    fragmented = next(
        row
        for row in audit["issues"]
        if row["code"] == "FRAGMENTED_ARTIFACT_IDENTITY"
        and row["semantic_key"] == "experiment_plan"
    )
    assert fragmented["identities"] == [
        "artifact.experiment_plan",
        EXPERIMENT_PLAN,
    ]
    assert audit["verdict"] == "fail"


def test_claim_extract_contract_matches_real_paper_only_implementation() -> None:
    capsule = next(
        row for row in _catalog()["capsules"] if row["capsule_id"] == "cap.research-claim-extract"
    )

    assert capsule["consumes"] == [PAPER]
    assert capsule["produces"] == [CLAIMS]


def test_discovery_ingest_contract_is_one_real_collection_primitive() -> None:
    capsule = next(
        row for row in _catalog()["capsules"] if row["capsule_id"] == "cap.research-discovery-ingest"
    )

    assert capsule["consumes"] == [LITERATURE]
    assert capsule["produces"] == [PAPER]
    assert capsule["contract"]["required_outputs"] == [
        {
            "name": "research_papers",
            "type": "collection",
            "schema_ref": "schemas/evidence/research_paper.v1.schema.json",
            "cardinality": "many",
        }
    ]
    assert capsule["operator_compatibility"]["selectable_preferred"] == [
        "discovery_ingest_worker"
    ]
    assert capsule["implementation"]["trust_class"] == "evidence_transform"


def test_discovery_to_ingestion_and_internal_report_plan_compose_exactly() -> None:
    ingest = composition.search_composition_candidates(
        _catalog(), available_inputs=[LITERATURE], target_outputs=[PAPER]
    )
    report = composition.search_composition_candidates(
        _catalog(), available_inputs=[CLAIM_VERDICT], target_outputs=[REPORT]
    )

    assert ingest["verdict"] == "candidates_found"
    assert [step["capsule_id"] for step in ingest["candidates"][0]["steps"]] == [
        "cap.research-discovery-ingest"
    ]
    assert report["verdict"] == "candidates_found"
    assert [step["capsule_id"] for step in report["candidates"][0]["steps"]] == [
        "cap.research-report-plan",
        "cap.scientific-report-draft",
    ]


def test_experiment_run_contract_requires_hash_bound_approval_input() -> None:
    capsule = next(
        row for row in _catalog()["capsules"] if row["capsule_id"] == "cap.research-experiment-run"
    )

    assert capsule["consumes"] == [EXPERIMENT_APPROVAL, EXPERIMENT_PLAN]
    assert capsule["produces"] == [EXPERIMENT_RESULT]
    assert capsule["operator_compatibility"]["selectable_preferred"] == [
        "experiment_run_worker"
    ]
    assert capsule["implementation"]["trust_class"] == "measured_execution"


def test_claim_verification_contract_requires_claims_and_retained_papers() -> None:
    capsule = next(
        row for row in _catalog()["capsules"] if row["capsule_id"] == "cap.research-claim-verify"
    )

    assert capsule["consumes"] == [CLAIMS, PAPER]
    assert capsule["produces"] == [CLAIM_VERDICT]
    assert capsule["operator_compatibility"]["selectable_preferred"] == [
        "claim_verify_worker"
    ]

    missing_papers = composition.search_composition_candidates(
        _catalog(), available_inputs=[CLAIMS], target_outputs=[CLAIM_VERDICT]
    )
    grounded = composition.search_composition_candidates(
        _catalog(), available_inputs=[CLAIMS, PAPER], target_outputs=[CLAIM_VERDICT]
    )

    assert missing_papers["verdict"] == "unsatisfiable"
    assert grounded["verdict"] == "candidates_found"
    assert [step["capsule_id"] for step in grounded["candidates"][0]["steps"]] == [
        "cap.research-claim-verify"
    ]


def test_governed_claim_can_compose_directly_to_experiment_plan() -> None:
    search = composition.search_composition_candidates(
        _catalog(), available_inputs=[CLAIMS], target_outputs=[EXPERIMENT_PLAN]
    )

    assert search["verdict"] == "candidates_found"
    assert [step["capsule_id"] for step in search["candidates"][0]["steps"]] == [
        "cap.research-claim-experiment-design"
    ]


def test_experiment_plan_can_compose_through_approval_to_measured_execution() -> None:
    search = composition.search_composition_candidates(
        _catalog(),
        available_inputs=[EXPERIMENT_PLAN],
        target_outputs=[EXPERIMENT_APPROVAL],
    )

    assert search["verdict"] == "candidates_found"
    assert [step["capsule_id"] for step in search["candidates"][0]["steps"]] == [
        "cap.research-native-experiment-approval"
    ]
    capsule = next(
        row
        for row in _catalog()["capsules"]
        if row["capsule_id"] == "cap.research-native-experiment-approval"
    )
    assert capsule["operator_compatibility"]["selectable_preferred"] == [
        "experiment_approval_gate_worker"
    ]


def test_measured_claim_verification_requires_paper_claim_and_result() -> None:
    catalog = _catalog()
    missing_result = composition.search_composition_candidates(
        catalog,
        available_inputs=[CLAIMS, PAPER],
        target_outputs=[CLAIM_VERDICT],
    )
    measured = composition.search_composition_candidates(
        catalog,
        available_inputs=[CLAIMS, PAPER, EXPERIMENT_RESULT],
        target_outputs=[CLAIM_VERDICT],
    )

    assert missing_result["verdict"] == "candidates_found"
    assert [step["capsule_id"] for step in missing_result["candidates"][0]["steps"]] == [
        "cap.research-claim-verify"
    ]
    measured_candidates = [
        candidate
        for candidate in measured["candidates"]
        if [step["capsule_id"] for step in candidate["steps"]]
        == ["cap.research-measured-claim-verify"]
    ]
    assert measured_candidates
    capsule = next(
        row
        for row in catalog["capsules"]
        if row["capsule_id"] == "cap.research-measured-claim-verify"
    )
    assert capsule["consumes"] == sorted([CLAIMS, EXPERIMENT_RESULT, PAPER])
    assert capsule["operator_compatibility"]["selectable_preferred"] == [
        "claim_verify_worker"
    ]


def test_native_experiment_monitor_requires_no_network_authority() -> None:
    catalog = _catalog()
    search = composition.search_composition_candidates(
        catalog,
        available_inputs=[EXPERIMENT_PLAN, EXPERIMENT_RESULT],
        target_outputs=["schema:schemas/evidence/experiment_status.v1.schema.json"],
        allowed_effects=["read", "write", "execute"],
    )

    assert search["verdict"] == "candidates_found"
    monitor = next(
        candidate
        for candidate in search["candidates"]
        if [step["capsule_id"] for step in candidate["steps"]]
        == ["cap.research-experiment-monitor"]
    )
    assert "network" not in monitor["aggregate_effects"]
    capsule = yaml.safe_load(
        (CAPSULE_DIR / "cap.research-experiment-monitor.yaml").read_text(encoding="utf-8")
    )
    assert capsule["metadata"]["name"] == "Post-run Experiment Result Verification"
    assert "does not observe a live process" in capsule["metadata"]["description"]


def test_report_composition_carries_method_evidence_into_plan_and_draft() -> None:
    catalog = _catalog()
    report = "schema:schemas/evidence/scientific_report.v1.schema.json"
    search = composition.search_composition_candidates(
        catalog,
        available_inputs=[CLAIM_VERDICT, METHODS],
        target_outputs=[report],
        allowed_effects=["read", "write", "execute"],
    )

    assert search["verdict"] == "candidates_found"
    candidate = next(
        row
        for row in search["candidates"]
        if [step["capsule_id"] for step in row["steps"]]
        == [
            "cap.research-method-aware-report-plan",
            "cap.scientific-method-aware-report-draft",
        ]
    )
    for step in candidate["steps"]:
        assert METHODS in step["consumes"]


def test_composer_honors_multi_input_hyperedges() -> None:
    artifact_registry = {
        "schema_version": "solar.artifact_type_registry.v1",
        "artifact_types": [
            {"artifact_type": value, "controller_input": value in {"type.a", "type.b"}}
            for value in ("type.a", "type.b", "type.c", "type.result")
        ],
    }
    catalog = {
        "capsules": [
            {
                "capsule_id": "cap.join",
                "consumes": ["type.a", "type.b"],
                "produces": ["type.c"],
                "verification": {"self_checks": ["check.join"]},
                "implementation": {"declared": True},
                "operator_compatibility": {"selectable_preferred": ["worker"]},
            },
            {
                "capsule_id": "cap.finish",
                "consumes": ["type.c"],
                "produces": ["type.result"],
                "verification": {"self_checks": ["check.finish"]},
                "implementation": {"declared": True},
                "operator_compatibility": {"selectable_preferred": ["worker"]},
            },
        ]
    }
    conversions = {"schema_version": "solar.artifact_conversion_registry.v1", "conversions": []}

    missing_input = composition.search_composition_candidates(
        catalog,
        available_inputs=["type.a"],
        target_outputs=["type.result"],
        artifact_registry=artifact_registry,
        conversion_registry=conversions,
    )
    complete = composition.search_composition_candidates(
        catalog,
        available_inputs=["type.a", "type.b"],
        target_outputs=["type.result"],
        artifact_registry=artifact_registry,
        conversion_registry=conversions,
    )

    assert missing_input["verdict"] == "unsatisfiable"
    assert missing_input["candidates"] == []
    join_frontier = next(
        row for row in missing_input["blocking_frontiers"] if row["capsule_id"] == "cap.join"
    )
    assert join_frontier == {
        "edge_id": "cap.join",
        "capsule_id": "cap.join",
        "produces": ["type.c"],
        "missing_inputs": [
            {"artifact_type": "type.b", "reason_code": "NO_ELIGIBLE_PRODUCER"}
        ],
    }
    assert complete["verdict"] == "candidates_found"
    assert complete["blocking_frontiers"] == []
    assert [row["capsule_id"] for row in complete["candidates"][0]["steps"]] == [
        "cap.join",
        "cap.finish",
    ]


def test_composer_rejects_mixed_lifecycle_instances_but_accepts_one_input_bundle() -> None:
    artifact_registry = {
        "schema_version": "solar.artifact_type_registry.v1",
        "artifact_types": [
            {"artifact_type": "type.request", "controller_input": True},
            {
                "artifact_type": "type.plan",
                "controller_input": True,
                "lineage_family": "experiment",
            },
            {
                "artifact_type": "type.result",
                "controller_input": True,
                "lineage_family": "experiment",
            },
            {
                "artifact_type": "type.status",
                "controller_input": False,
                "lineage_family": "experiment",
            },
        ],
    }
    catalog = {
        "capsules": [
            {
                "capsule_id": "cap.design",
                "consumes": ["type.request"],
                "produces": ["type.plan"],
                "verification": {"self_checks": ["check.plan"]},
                "implementation": {"declared": True},
                "operator_compatibility": {"selectable_preferred": ["designer"]},
            },
            {
                "capsule_id": "cap.monitor",
                "consumes": ["type.plan", "type.result"],
                "produces": ["type.status"],
                "verification": {"self_checks": ["check.status"]},
                "implementation": {"declared": True},
                "operator_compatibility": {"selectable_preferred": ["monitor"]},
            },
        ]
    }
    conversions = {
        "schema_version": "solar.artifact_conversion_registry.v1",
        "conversions": [],
    }

    mixed = composition.search_composition_candidates(
        catalog,
        available_inputs=["type.request", "type.result"],
        target_outputs=["type.status"],
        artifact_registry=artifact_registry,
        conversion_registry=conversions,
    )
    one_bundle = composition.search_composition_candidates(
        catalog,
        available_inputs=["type.plan", "type.result"],
        target_outputs=["type.status"],
        artifact_registry=artifact_registry,
        conversion_registry=conversions,
    )

    assert mixed["verdict"] == "unsatisfiable"
    assert mixed["candidates"] == []
    assert one_bundle["verdict"] == "candidates_found"
    assert [step["capsule_id"] for step in one_bundle["candidates"][0]["steps"]] == [
        "cap.monitor"
    ]


def test_composer_preserves_bounded_alternative_path_signatures() -> None:
    artifact_registry = {
        "schema_version": "solar.artifact_type_registry.v1",
        "artifact_types": [
            {"artifact_type": value, "controller_input": value == "type.source"}
            for value in ("type.source", "type.result")
        ],
    }
    catalog = {
        "capsules": [
            {
                "capsule_id": capsule_id,
                "consumes": ["type.source"],
                "produces": ["type.result"],
                "effects": {"read": ["source"], "write": ["result"]},
                "verification": {"self_checks": [f"check.{capsule_id}"]},
                "implementation": {"declared": True},
                "operator_compatibility": {"selectable_preferred": ["worker"]},
            }
            for capsule_id in ("cap.alternative-a", "cap.alternative-b")
        ]
    }
    conversions = {"schema_version": "solar.artifact_conversion_registry.v1", "conversions": []}

    result = composition.search_composition_candidates(
        catalog,
        available_inputs=["type.source"],
        target_outputs=["type.result"],
        artifact_registry=artifact_registry,
        conversion_registry=conversions,
        max_candidates=2,
    )

    assert [candidate["steps"][0]["capsule_id"] for candidate in result["candidates"]] == [
        "cap.alternative-a",
        "cap.alternative-b",
    ]
    assert all(
        candidate["aggregate_effects"] == ["read", "write"]
        for candidate in result["candidates"]
    )


def test_composer_filters_disallowed_effects_before_candidate_search() -> None:
    network_denied = composition.search_composition_candidates(
        _catalog(),
        available_inputs=[REQUEST_ENVELOPE],
        target_outputs=[EXPERIMENT_PLAN],
        allowed_effects=["read", "write", "execute"],
        max_depth=10,
    )

    assert network_denied["effect_policy"]["allowed_effects"] == ["execute", "read", "write"]
    assert network_denied["verdict"] == "unsatisfiable"
    discovery_exclusion = next(
        row
        for row in network_denied["excluded_capsules"]
        if row["capsule_id"] == "cap.research-literature-discover"
        and row["reason_codes"] == ["EFFECT_POLICY_DISALLOWED"]
    )
    assert discovery_exclusion["disallowed_effects"] == ["network"]


def test_composer_cycles_and_search_bounds_terminate_honestly() -> None:
    artifact_registry = {
        "schema_version": "solar.artifact_type_registry.v1",
        "artifact_types": [
            {"artifact_type": value, "controller_input": value == "type.a"}
            for value in ("type.a", "type.b", "type.never")
        ],
    }
    catalog = {
        "capsules": [
            {
                "capsule_id": "cap.a-to-b",
                "consumes": ["type.a"],
                "produces": ["type.b"],
                "verification": {"self_checks": ["check.a-to-b"]},
                "implementation": {"declared": True},
                "operator_compatibility": {"selectable_preferred": ["worker"]},
            },
            {
                "capsule_id": "cap.b-to-a",
                "consumes": ["type.b"],
                "produces": ["type.a"],
                "verification": {"self_checks": ["check.b-to-a"]},
                "implementation": {"declared": True},
                "operator_compatibility": {"selectable_preferred": ["worker"]},
            },
            {
                "capsule_id": "cap.b-to-result",
                "consumes": ["type.b"],
                "produces": ["type.never"],
                "verification": {"self_checks": ["check.b-to-result"]},
                "implementation": {"declared": True},
                "operator_compatibility": {"selectable_preferred": ["worker"]},
            },
        ]
    }
    conversions = {"schema_version": "solar.artifact_conversion_registry.v1", "conversions": []}

    complete = composition.search_composition_candidates(
        catalog,
        available_inputs=["type.a"],
        target_outputs=["type.never"],
        artifact_registry=artifact_registry,
        conversion_registry=conversions,
        max_states=20,
    )
    bounded = composition.search_composition_candidates(
        catalog,
        available_inputs=["type.a"],
        target_outputs=["type.never"],
        artifact_registry=artifact_registry,
        conversion_registry=conversions,
        max_states=1,
    )

    assert complete["verdict"] == "candidates_found"
    assert [step["capsule_id"] for step in complete["candidates"][0]["steps"]] == [
        "cap.a-to-b",
        "cap.b-to-result",
    ]
    assert complete["search_stats"]["visited_states"] <= 4
    assert bounded["verdict"] == "search_bound_exhausted"
    assert bounded["search_stats"] == {
        "explored_states": 1,
        "visited_states": 2,
        "relevant_edge_count": 3,
        "bound_exhausted": True,
    }


def test_real_ab_design_composition_is_exact_and_auditable() -> None:
    request_envelope = json.loads(
        (ROOT / "tests/harness/fixtures/planner/composition_request_envelope.v1.json").read_text(
            encoding="utf-8"
        )
    )
    request_schema = json.loads(
        (ROOT / "harness/schemas/request-envelope.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(request_schema).validate(request_envelope)
    assert request_envelope["raw_text"]
    assert request_envelope["attachments"]["source_ref"]
    assert (ROOT / request_envelope["attachments"]["source_ref"]).is_file()

    result = composition.search_composition_candidates(
        _catalog(),
        available_inputs=[REQUEST_ENVELOPE],
        target_outputs=[EXPERIMENT_PLAN],
        max_depth=10,
    )

    assert result["verdict"] == "candidates_found"
    assert result["unreachable_targets"] == []
    assert result["search_stats"]["bound_exhausted"] is False
    assert result["effect_policy"]["allowed_effects"] == ["execute", "network", "read", "write"]
    steps = result["candidates"][0]["steps"]
    ids = [row["capsule_id"] for row in steps]
    assert ids == [
        "cap.research-paper-ingest",
        "cap.research-claim-extract",
        "cap.research-claim-experiment-design",
    ]
    design_edge = next(
        row
        for row in result["hyperedges"]
        if row["capsule_id"] == "cap.research-claim-experiment-design"
    )
    assert design_edge["consumes"] == [CLAIMS]
    assert all(row["edge_kind"] == "capability_capsule" for row in steps)
    assert result["candidates"][0]["aggregate_effects"] == [
        "execute",
        "network",
        "read",
        "write",
    ]


def test_real_ab_execution_frontier_reaches_native_approval_and_measured_run() -> None:
    result = composition.search_composition_candidates(
        _catalog(),
        available_inputs=[REQUEST_ENVELOPE],
        target_outputs=[EXPERIMENT_RESULT],
        max_depth=12,
    )
    approval_edge = next(
        row
        for row in result["hyperedges"]
        if row["capsule_id"] == "cap.research-native-experiment-approval"
    )
    run_edge = next(
        row for row in result["hyperedges"] if row["capsule_id"] == "cap.research-experiment-run"
    )

    assert approval_edge["consumes"] == [EXPERIMENT_PLAN]
    assert approval_edge["produces"] == [EXPERIMENT_APPROVAL]
    assert run_edge["consumes"] == [EXPERIMENT_APPROVAL, EXPERIMENT_PLAN]
    assert result["verdict"] == "candidates_found"
    assert any(
        [step["capsule_id"] for step in candidate["steps"]][-2:]
        == ["cap.research-native-experiment-approval", "cap.research-experiment-run"]
        for candidate in result["candidates"]
    )


def test_real_experiment_requirement_uses_measured_capsule_path() -> None:
    result = composition.search_composition_candidates(
        _catalog(),
        available_inputs=[EXPERIMENT_PLAN, EXPERIMENT_APPROVAL],
        target_outputs=[EXPERIMENT_RESULT],
        max_depth=12,
        required_trust_by_output={EXPERIMENT_RESULT: ["measured_execution"]},
    )

    assert result["verdict"] == "candidates_found"
    assert result["candidates"]
    selected = result["candidates"][0]
    assert selected["steps"][-1]["capsule_id"] == "cap.research-experiment-run"
    assert selected["steps"][-1]["produces"] == [EXPERIMENT_RESULT]


def test_requirement_only_ab_frontier_fails_without_fake_adapter() -> None:
    result = composition.search_composition_candidates(
        _catalog(),
        available_inputs=["artifact.requirement_ir"],
        target_outputs=[EXPERIMENT_RESULT],
        max_depth=12,
    )

    assert result["verdict"] == "unsatisfiable"
    assert result["candidates"] == []
    assert result["unreachable_targets"] == [EXPERIMENT_RESULT]
    assert all(row["edge_kind"] != "approved_conversion" for row in result["hyperedges"])


def test_research_only_publication_path_uses_plan_draft_and_review() -> None:
    result = composition.search_composition_candidates(
        _catalog(),
        available_inputs=[REQUEST_ENVELOPE],
        target_outputs=[PUBLICATION_BUNDLE],
        max_depth=16,
        max_states=1000,
    )

    assert result["verdict"] == "candidates_found"
    assert result["unreachable_targets"] == []
    assert [
        step["capsule_id"] for step in result["candidates"][0]["steps"]
    ] == [
        "cap.research-paper-ingest",
        "cap.research-claim-extract",
        "cap.research-claim-verify",
        "cap.research-report-plan",
        "cap.scientific-report-draft",
        "cap.research-artifact-review",
        "cap.research-publication-produce",
    ]
    assert any(
        [step["capsule_id"] for step in candidate["steps"]][:2]
        == ["cap.research-literature-discover", "cap.research-discovery-ingest"]
        for candidate in result["candidates"]
    )


def test_intermediate_artifacts_round_trip_json(tmp_path: Path) -> None:
    audit = composition.build_registry_graph_audit(_catalog())
    search = composition.search_composition_candidates(
        _catalog(), available_inputs=[REQUEST_ENVELOPE], target_outputs=[EXPERIMENT_PLAN]
    )
    audit_path = tmp_path / "registry_graph_audit.json"
    search_path = tmp_path / "composition_candidates.json"

    composition.write_json(audit_path, audit)
    composition.write_json(search_path, search)

    assert json.loads(audit_path.read_text(encoding="utf-8")) == audit
    assert json.loads(search_path.read_text(encoding="utf-8")) == search
