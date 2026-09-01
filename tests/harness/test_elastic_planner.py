import copy
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "harness" / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import elastic_planner as planner
import apo_plan_compiler as apo
import capsule_composition as composition
import workflow_contract
import scheduler_input as scheduler_input_runtime
from intent_compiler import sha256_payload


def _requirement_ir() -> dict:
    return {
        "schema_version": "solar.requirement_ir.v1",
        "id": "req-elastic-test",
        "requirements": [
            {
                "id": "REQ-001",
                "source_text": "Implement the requested change.",
                "verification_method": "check.patch.v1",
            },
            {
                "id": "REQ-002",
                "source_text": "Run focused verification.",
                "verification_method": "check.tests.v1",
            },
        ],
    }


def _battery_research_requirement_ir() -> dict:
    return {
        "schema_version": "solar.requirement_ir.v2",
        "requirement_ir_id": "req-battery-research",
        "requirements": [
            {
                "requirement_id": "R1",
                "statement": "Produce the final grid-storage battery comparison report.",
                "acceptance": {
                    "kind": "artifact_fields",
                    "required_values": ["answer", "supporting_evidence", "limitations"],
                },
                "check": "check.information_outcome_completeness.v1",
            },
            {
                "requirement_id": "R2",
                "statement": "Compare the four specified battery chemistries for grid storage.",
                "acceptance": {
                    "kind": "coverage",
                    "required_values": [
                        "lithium-ion, sodium-ion, solid-state, and lithium-sulfur batteries"
                    ],
                },
                "check": "check.intent_constraint_coverage.v1",
            },
            {
                "requirement_id": "R3",
                "statement": "Evaluate every requested comparison criterion.",
                "acceptance": {
                    "kind": "coverage",
                    "required_values": [
                        "energy density, lifetime, safety, material availability, cost, and commercial readiness"
                    ],
                },
                "check": "check.intent_constraint_coverage.v1",
            },
        ],
    }


def _r16_research_requirement_ir() -> dict:
    statements = {
        "R1": "Produce a comparison of at least four RAG evaluation approaches.",
        "R2": "Preserve source links and evidence supporting material claims.",
        "R3": "Produce a concise research report with limitations and a recommendation.",
        "R4": "Research must focus on current methods and public benchmarks.",
        "R5": "Include public benchmarks for factual accuracy and citation correctness.",
        "R6": "The research scope is retrieval-augmented generation systems.",
        "R7": "Use live public sources.",
        "R8": "Compare at least four distinct evaluation approaches.",
        "R9": "Preserve source links and evidence for material claims.",
        "R10": "Identify disagreements and limitations.",
        "R11": "Produce a concise research report.",
        "R12": "Include a reproducible evaluation recommendation.",
        "R13": "Do not claim a benchmark was executed unless it was actually run.",
        "R14": "Resolve which current public sources, methods, and benchmarks are available.",
        "R15": "Resolve which four approaches should be selected for comparison.",
        "R16": "Resolve disagreements and limitations across the selected approaches.",
        "R17": "Resolve the reproducible evaluation recommendation.",
    }
    rows = []
    for requirement_id, statement in statements.items():
        if requirement_id in {f"R{index}" for index in range(4, 14)}:
            acceptance = {"kind": "coverage", "required_values": [statement]}
            check = "check.intent_constraint_coverage.v1"
        elif requirement_id in {"R14", "R15", "R16", "R17"}:
            acceptance = {"kind": "artifact_fields", "required_values": ["resolution"]}
            check = "check.unknown_resolution_trace.v1"
        else:
            acceptance = {"kind": "artifact_fields", "required_values": ["answer"]}
            check = (
                "check.artifact_outcome_completeness.v1"
                if requirement_id == "R3"
                else "check.information_outcome_completeness.v1"
            )
        rows.append(
            {
                "requirement_id": requirement_id,
                "statement": statement,
                "acceptance": acceptance,
                "check": check,
            }
        )
    return {
        "schema_version": "solar.requirement_ir.v2",
        "requirement_ir_id": "req-r16-research",
        "requirements": rows,
    }


def _r16_research_plan_body(*, overassign_discovery: bool = False) -> dict:
    discovery_ids = ["R4", "R5", "R6", "R7", "R9", "R14"]
    if overassign_discovery:
        discovery_ids.extend(["R8", "R10", "R11", "R12", "R13"])
    return {
        "nodes": [
            {
                "node_id": "discover_current_public_evidence",
                "logical_operator": "ScientificLiteratureDiscoverer",
                "objective": "Discover live public RAG methods, benchmarks, sources, and evidence.",
                "depends_on": [],
                "consumes": ["schema:request-envelope.schema.json"],
                "produces": [
                    {
                        "artifact_type": "schema:schemas/evidence/literature_discovery.v1.schema.json",
                        "verifier_ids": [
                            "check.scientific.literature_discovery.v1",
                            "check.intent_constraint_coverage.v1",
                            "check.unknown_resolution_trace.v1",
                        ],
                        "materialization": {
                            "kind": "file",
                            "path": "evidence/literature-discovery.json",
                            "route": "sprint_private",
                        },
                    }
                ],
                "requirement_ids": discovery_ids,
                "operator_requirements": {
                    "capabilities": ["research_synthesis", "scientific_evidence"],
                    "network": "required",
                    "execution_trust": "any",
                    "minimum_context_tokens": 8000,
                    "effects": ["read", "write", "execute", "network"],
                },
                "gate_requirement": "Discovery is source-backed and in scope.",
                "workspace_reads": [],
            },
            {
                "node_id": "synthesize_comparative_report",
                "logical_operator": "ResearchSynthesizer",
                "objective": "Synthesize the source-linked comparison, limitations, and recommendation.",
                "depends_on": ["discover_current_public_evidence"],
                "consumes": [
                    "schema:schemas/evidence/literature_discovery.v1.schema.json"
                ],
                "produces": [
                    {
                        "artifact_type": "schema:schemas/evidence/scientific_report.v1.schema.json",
                        "verifier_ids": [
                            "check.scientific.scientific_report.v1",
                            "check.information_outcome_completeness.v1",
                            "check.artifact_outcome_completeness.v1",
                            "check.intent_constraint_coverage.v1",
                            "check.unknown_resolution_trace.v1",
                        ],
                        "materialization": {
                            "kind": "file",
                            "path": "report/research-report.json",
                            "route": "workspace_publish",
                        },
                    }
                ],
                "requirement_ids": [
                    "R1", "R2", "R3", "R8", "R10", "R11", "R12", "R13",
                    "R15", "R16", "R17",
                ],
                "operator_requirements": {
                    "capabilities": [
                        "academic_critique", "data_extraction", "long_context",
                        "research_synthesis", "scientific_evidence",
                    ],
                    "network": "required",
                    "execution_trust": "evidence_transform",
                    "minimum_context_tokens": 16000,
                    "effects": ["read", "write", "execute", "network"],
                },
                "gate_requirement": "The final report covers every owned requirement.",
                "workspace_reads": [],
            },
        ]
    }


def _catalog() -> dict:
    catalog = planner.build_planning_catalog_snapshot()
    assert "ImplementationWorker" in {
        row["logical_operator"] for row in catalog["logical_operators"]
    }
    return catalog


def _planning_context(requirement_ir: dict) -> dict:
    return {
        "schema_version": "solar.planning_context.v1",
        "artifact_role": "runtime_artifact",
        "planning_context_id": f"planning-context-{requirement_ir['id']}",
        "artifacts": [
            {
                "name": "requirement_ir",
                "relative_path": "requirement_ir.json",
                "sha256": sha256_payload(requirement_ir),
            }
        ],
    }


def test_strategy_prompt_exposes_only_planner_reusable_workflows() -> None:
    catalog = planner.build_planning_catalog_snapshot()
    deepdive = next(
        row
        for row in catalog["workflows"]
        if row["workflow_id"] == "research.deepdive.rsi_demo"
    )
    assert deepdive["planner_reusable"] is False
    assert deepdive["reuse_blockers"] == [
        {
            "code": "UNREGISTERED_LOGICAL_OPERATORS",
            "detail": (
                "The workflow references logical operators that are absent "
                "from the current planning registry."
            ),
            "logical_operators": [
                "DeepDiveArtifactPublisher",
                "DeepDiveBriefCapture",
                "DeepDiveChiefEditor",
                "DeepDiveClaimCompiler",
                "DeepDiveContradictionScanner",
                "DeepDiveSourceCollector",
            ],
        }
    ]

    prompt = json.loads(
        planner._decision_prompt(_requirement_ir(), catalog, {}, generation=0)
    )
    exposed = {
        row["workflow_id"]
        for row in prompt["planning_catalog"]["workflows"]
    }
    assert "code.cli_smoke" in exposed
    assert "research.deepdive.rsi_demo" not in exposed
    assert "research.evidence_to_poc.v1" not in exposed


def _decision(requirement_ir: dict, decision: str = "generate") -> dict:
    workflow_ref = None
    if decision == "exact_reuse":
        workflow = next(
            row
            for row in _catalog()["workflows"]
            if row["workflow_id"] == "code.cli_smoke"
        )
        workflow_ref = {
            "workflow_id": workflow["workflow_id"],
            "version": workflow["version"],
        }
    return {
        "schema_version": "solar.planning_decision.v1",
        "artifact_role": "runtime_artifact",
        "planning_decision_id": "planning-decision-test-g0",
        "generation": 0,
        "requirement_ir_ref": {
            "requirement_ir_id": requirement_ir["id"],
            "sha256": sha256_payload(requirement_ir),
        },
        "planning_context_ref": {
            "planning_context_id": _planning_context(requirement_ir)["planning_context_id"],
            "sha256": sha256_payload(_planning_context(requirement_ir)),
        },
        "producer": {"method": "model", "provider": "test", "model": "test-model"},
        "decision": decision,
        "rationale": ["This request needs executable work."],
        "requirement_ids": ["REQ-001", "REQ-002"],
        "workflow_ref": workflow_ref,
        "workflow_inputs": (
            [{"name": "tool", "value": "elastic_demo"}]
            if decision == "exact_reuse"
            else []
        ),
        "workflow_bindings": (
            [
                {"requirement_id": "REQ-001", "stage_ids": ["S1"]},
                {"requirement_id": "REQ-002", "stage_ids": ["S2"]},
            ]
            if decision == "exact_reuse"
            else []
        ),
        "requirements_gap": None,
    }


def _plan_body(logical_operator: str = "ImplementationWorker") -> dict:
    return {
        "nodes": [
            {
                "node_id": "implement",
                "logical_operator": logical_operator,
                "objective": "Implement the requested change and produce a reviewable patch.",
                "depends_on": [],
                "consumes": ["requirement_ir.v1"],
                "produces": [
                    {
                        "artifact_type": "artifact.patch_diff",
                        "verifier_ids": ["check.patch.v1"],
                        "materialization": {
                            "kind": "file",
                            "path": "implementation.diff",
                            "route": "sprint_private",
                        },
                    },
                    {
                        "artifact_type": "artifact.handoff_md",
                        "verifier_ids": ["check.tests.v1"],
                        "materialization": {
                            "kind": "file",
                            "path": "handoff.md",
                            "route": "sprint_private",
                        },
                    },
                ],
                "workspace_reads": [],
                "requirement_ids": ["REQ-001", "REQ-002"],
                "operator_requirements": {
                    "capabilities": ["code_impl", "test_generation"],
                    "network": "forbidden",
                    "execution_trust": "any",
                    "minimum_context_tokens": 16000,
                    "effects": ["read", "write", "execute"],
                },
                "gate_requirement": "deterministic_test_and_patch_review",
            }
        ]
    }


def _composition_plan_body() -> dict:
    return {
        "nodes": [
            {
                "node_id": "design_reproducibility_experiment",
                "logical_operator": "ScientificExperimentDesigner",
                "objective": (
                    "Turn the admitted research request into a source-grounded, "
                    "claim-linked reproducibility experiment plan."
                ),
                "depends_on": [],
                "consumes": ["schema:request-envelope.schema.json"],
                "produces": [
                    {
                        "artifact_type": "schema:schemas/evidence/experiment_plan.v1.schema.json",
                        "verifier_ids": ["check.patch.v1", "check.tests.v1"],
                        "materialization": {
                            "kind": "file",
                            "path": "experiment_plan.json",
                            "route": "sprint_private",
                        },
                    }
                ],
                "workspace_reads": [],
                "requirement_ids": ["REQ-001", "REQ-002"],
                "operator_requirements": {
                    "capabilities": [
                        "literature_discovery",
                        "claim_extraction",
                        "experiment_design",
                    ],
                    "network": "required",
                    "execution_trust": "any",
                    "minimum_context_tokens": 16000,
                    "effects": ["read", "write", "execute", "network"],
                },
                "gate_requirement": "source_grounded_experiment_plan_review",
            }
        ]
    }


def _wrapped_plan(requirement_ir: dict, decision: dict, body: dict | None = None) -> dict:
    return planner._wrap_plan_ir(
        requirement_ir,
        decision,
        body or _plan_body(),
        generation=0,
        producer={"method": "model", "provider": "test", "model": "test-model"},
    )


class ScriptedModel:
    provider = "test"
    model = "test-model"

    def __init__(
        self,
        *,
        decision: str = "generate",
        decision_bodies=None,
        plan_bodies=None,
        fidelity_reviews=None,
        response_reviews=None,
        capsule_selections=None,
        capsule_fit_reviews=None,
        composition_selections=None,
        composition_fit_reviews=None,
    ):
        self.decision = decision
        self.decision_bodies = list(decision_bodies or [])
        self.plan_bodies = list(plan_bodies or [_plan_body()])
        self.fidelity_reviews = list(fidelity_reviews or [])
        self.response_reviews = list(response_reviews or [])
        self.capsule_selections = list(capsule_selections or [])
        self.capsule_fit_reviews = list(capsule_fit_reviews or [])
        self.composition_selections = list(composition_selections or [])
        self.composition_fit_reviews = list(composition_fit_reviews or [])
        self.calls = []
        self.prompts = []

    def generate(self, prompt, schema_path, work_dir):
        self.calls.append(schema_path.name)
        self.prompts.append(prompt)
        if schema_path == planner.DECISION_BODY_SCHEMA:
            if self.decision_bodies:
                return copy.deepcopy(self.decision_bodies.pop(0))
            workflow_ref = None
            workflow_inputs = []
            workflow_bindings = []
            if self.decision == "exact_reuse":
                workflow_ref = {"workflow_id": "code.cli_smoke", "version": "1.0"}
                workflow_inputs = [{"name": "tool", "value": "elastic_demo"}]
                workflow_bindings = [
                    {"requirement_id": "REQ-001", "stage_ids": ["S1"]},
                    {"requirement_id": "REQ-002", "stage_ids": ["S2"]},
                ]
            return {
                "decision": self.decision,
                "rationale": ["Smallest sufficient strategy selected."],
                "requirement_ids": ["REQ-001", "REQ-002"],
                "workflow_ref": workflow_ref,
                "workflow_inputs": workflow_inputs,
                "workflow_bindings": workflow_bindings,
                "requirements_gap": None,
            }
        if schema_path == planner.PLAN_BODY_SCHEMA:
            return copy.deepcopy(self.plan_bodies.pop(0))
        if schema_path == planner.DIRECT_RESPONSE_BODY_SCHEMA:
            return {
                "answer": "A concise answer covering both accepted requirements.",
                "requirement_ids": ["REQ-001", "REQ-002"],
                "limitations": ["No external execution or retrieval was performed."],
            }
        if schema_path == planner.DIRECT_RESPONSE_REVIEW_BODY_SCHEMA:
            if self.response_reviews:
                return copy.deepcopy(self.response_reviews.pop(0))
            return {
                "checks": [
                    {"kind": "requirement_coverage", "status": "pass", "reason": "Both requirements are addressed."},
                    {"kind": "answer_fidelity", "status": "pass", "reason": "The answer preserves the admitted request."},
                    {"kind": "factual_restraint", "status": "pass", "reason": "No unperformed work is claimed."},
                ],
                "errors": [],
                "warnings": [],
            }
        if schema_path == planner.FIDELITY_REVIEW_SCHEMA:
            if self.fidelity_reviews:
                return copy.deepcopy(self.fidelity_reviews.pop(0))
            return {
                "checks": [
                    {"kind": "requirement_preservation", "status": "pass", "reason": "All requirements are owned."},
                    {"kind": "smallest_sufficient_plan", "status": "pass", "reason": "One node is sufficient."},
                    {"kind": "dependency_soundness", "status": "pass", "reason": "The graph has no unnecessary edge."},
                    {"kind": "no_unrequested_effects", "status": "pass", "reason": "Effects match implementation."},
                ],
                "errors": [],
                "warnings": [],
            }
        if schema_path == planner.CAPSULE_SELECTION_BODY_SCHEMA:
            if self.capsule_selections:
                return copy.deepcopy(self.capsule_selections.pop(0))
            return {
                "nodes": [
                    {
                        "node_id": "implement",
                        "selected_capsule_id": "cap.requirement-compiler-implementation",
                        "fallback_capsule_ids": [],
                        "rationale": "This capsule implements scoped requirements and produces the declared patch and handoff artifacts.",
                    }
                ]
            }
        if schema_path == planner.COMPOSITION_SELECTION_BODY_SCHEMA:
            if self.composition_selections:
                return copy.deepcopy(self.composition_selections.pop(0))
            payload = json.loads(prompt)
            nodes = []
            for proof in payload["composition_catalog"]["nodes"]:
                candidate_id = proof["admitted_candidate_ids"][0]
                nodes.append(
                    {
                        "node_id": proof["node_id"],
                        "selected_candidate_id": candidate_id,
                        "rationale": "This is the smallest proven capsule chain that fulfils the logical objective.",
                    }
                )
            return {"nodes": nodes}
        if schema_path == planner.CAPSULE_FIT_REVIEW_BODY_SCHEMA:
            if "\"composition_selection\"" in prompt:
                if self.composition_fit_reviews:
                    return copy.deepcopy(self.composition_fit_reviews.pop(0))
                payload = json.loads(prompt)
                return {
                    "nodes": [
                        {
                            "node_id": row["node_id"],
                            "status": "pass",
                            "reason": "The selected chain is semantically sufficient for this logical objective.",
                        }
                        for row in payload["plan_ir"]["nodes"]
                    ],
                    "errors": [],
                    "warnings": [],
                }
            if self.capsule_fit_reviews:
                return copy.deepcopy(self.capsule_fit_reviews.pop(0))
            return {
                "nodes": [
                    {"node_id": "implement", "status": "pass", "reason": "The capsule meaningfully performs the implementation objective."}
                ],
                "errors": [],
                "warnings": [],
            }
        raise AssertionError(schema_path)


def test_planning_decision_is_hash_bound_and_covers_exact_requirement_set() -> None:
    requirement_ir = _requirement_ir()
    decision = _decision(requirement_ir)

    assert planner.validate_planning_decision(requirement_ir, decision, _catalog()) == []

    decision["requirement_ids"] = ["REQ-001"]
    codes = {
        row["code"]
        for row in planner.validate_planning_decision(requirement_ir, decision, _catalog())
    }
    assert "REQUIREMENT_SET_MISMATCH" in codes


def test_direct_answer_hint_cannot_be_promoted_to_generated_runtime_graph() -> None:
    requirement_ir = _requirement_ir()
    requirement_ir["planner_hints"] = {
        "preferred_outcome": "direct_answer",
        "runtime_handoff_allowed": False,
    }

    generated = _decision(requirement_ir, "generate")
    codes = {
        row["code"]
        for row in planner.validate_planning_decision(
            requirement_ir,
            generated,
            _catalog(),
        )
    }
    assert "DIRECT_RESPONSE_ROUTE_VIOLATED" in codes

    direct = _decision(requirement_ir, "direct_response")
    direct_codes = {
        row["code"]
        for row in planner.validate_planning_decision(
            requirement_ir,
            direct,
            _catalog(),
        )
    }
    assert "DIRECT_RESPONSE_ROUTE_VIOLATED" not in direct_codes


def test_exact_reuse_requires_registered_id_and_version() -> None:
    requirement_ir = _requirement_ir()
    decision = _decision(requirement_ir, "exact_reuse")
    assert planner.validate_planning_decision(requirement_ir, decision, _catalog()) == []

    decision["workflow_ref"] = {"workflow_id": "missing.workflow", "version": "1"}
    codes = {
        row["code"]
        for row in planner.validate_planning_decision(requirement_ir, decision, _catalog())
    }
    assert "WORKFLOW_REF_UNKNOWN" in codes


def test_invalid_generate_strategy_repairs_once_to_honest_generate_decision(
    tmp_path: Path,
) -> None:
    requirement_ir = _requirement_ir()
    invalid_decision = {
        "decision": "generate",
        "rationale": [
            "Generate a new graph; the referenced workflow was considered but rejected."
        ],
        "requirement_ids": ["REQ-001", "REQ-002"],
        "workflow_ref": {"workflow_id": "code.cli_smoke", "version": "1.0"},
        "workflow_inputs": [],
        "workflow_bindings": [],
        "requirements_gap": None,
    }
    model = ScriptedModel(decision_bodies=[invalid_decision])

    result = planner.run_elastic_planning_request(
        requirement_ir,
        tmp_path,
        model,
        ScriptedModel(),
        sprint_id="sprint-invalid-strategy",
        catalog=_catalog(),
    )

    assert result["status"] == "accepted"
    assert result["verification_errors"] == []
    assert result["semantic"]["planning_decision"]["generation"] == 1
    assert result["semantic"]["planning_decision"]["decision"] == "generate"
    assert result["semantic"]["planning_decision"]["workflow_ref"] is None
    assert result["semantic"]["plan_acceptance"]["repair"]["attempted"] is True
    strategy_repair = json.loads(
        (tmp_path / "semantic" / "strategy_repair_record.json").read_text()
    )
    assert strategy_repair["status"] == "completed"
    assert model.calls.count(planner.DECISION_BODY_SCHEMA.name) == 2
    assert "workflow_ref must be null" in model.prompts[0]
    assert "Correct only the listed defects" in model.prompts[1]


def test_exact_reuse_catalog_exposes_and_validator_requires_real_placeholders() -> None:
    requirement_ir = _requirement_ir()
    catalog = planner.build_planning_catalog_snapshot()
    workflow = next(
        row for row in catalog["workflows"] if row["workflow_id"] == "code.cli_smoke"
    )
    assert workflow["required_inputs"] == [
        {"name": "tool", "occurrences": ["<tool>.py", "tests/test_<tool>.py"]}
    ]
    assert workflow["stages"][1]["depends_on"] == ["S1"]

    decision = _decision(requirement_ir, "exact_reuse")
    decision["workflow_inputs"] = []
    codes = {
        row["code"]
        for row in planner.validate_planning_decision(requirement_ir, decision, catalog)
    }
    assert "WORKFLOW_INPUT_REQUIRED" in codes


def test_exact_reuse_compiles_registered_topology_and_explicit_requirement_bindings() -> None:
    requirement_ir = _requirement_ir()
    requirement_ir["scope"] = {"implementation": {"network": "forbidden"}}
    decision = _decision(requirement_ir, "exact_reuse")

    plan_ir = planner.compile_exact_reuse_plan(requirement_ir, decision)
    validation = planner.validate_plan_ir(requirement_ir, decision, plan_ir, _catalog())
    trace = planner.build_binding_trace(requirement_ir, plan_ir)

    expected_stages = next(
        row["stage_ids"]
        for row in _catalog()["workflows"]
        if row["workflow_id"] == "code.cli_smoke"
    )
    assert [node["node_id"] for node in plan_ir["nodes"]] == expected_stages
    assert plan_ir["nodes"][0]["requirement_ids"] == ["REQ-001"]
    assert plan_ir["nodes"][1]["requirement_ids"] == ["REQ-002"]
    assert plan_ir["nodes"][0]["produces"][0]["materialization"]["path"] == "elastic_demo.py"
    assert plan_ir["nodes"][0]["operator_requirements"]["network"] == "forbidden"
    assert plan_ir["nodes"][0]["operator_requirements"]["execution_trust"] == "any"
    s3_consumes = set(plan_ir["nodes"][2]["consumes"])
    assert "workflow.code.cli_smoke.S1.output.1.python" in s3_consumes
    assert "workflow.code.cli_smoke.S2.output.2.markdown" in s3_consumes
    assert validation["status"] == "pass"
    assert trace["verdict"] == "pass"


def test_exact_reuse_rejects_missing_or_invented_stage_binding() -> None:
    requirement_ir = _requirement_ir()
    decision = _decision(requirement_ir, "exact_reuse")
    decision["workflow_bindings"] = [
        {"requirement_id": "REQ-001", "stage_ids": ["S1"]},
        {"requirement_id": "REQ-002", "stage_ids": ["invented-stage"]},
    ]

    codes = {
        row["code"]
        for row in planner.validate_planning_decision(requirement_ir, decision, _catalog())
    }

    assert "WORKFLOW_BINDING_STAGE_UNKNOWN" in codes


def test_exact_reuse_rejects_workflow_with_unregistered_logical_operators() -> None:
    requirement_ir = _requirement_ir()
    decision = _decision(requirement_ir, "exact_reuse")
    decision["workflow_ref"] = {
        "workflow_id": "research.deepdive.rsi_demo",
        "version": "1.3",
    }
    decision["workflow_inputs"] = []
    decision["workflow_bindings"] = [
        {"requirement_id": "REQ-001", "stage_ids": ["D1"]},
        {"requirement_id": "REQ-002", "stage_ids": ["D5"]},
    ]

    errors = planner.validate_planning_decision(
        requirement_ir, decision, _catalog()
    )

    defect = next(
        row
        for row in errors
        if row["code"] == "WORKFLOW_LOGICAL_OPERATOR_UNKNOWN"
    )
    assert "DeepDiveBriefCapture" in defect["message"]
    assert defect["repairable"] is True


def test_rejected_exact_reuse_repairs_strategy_once_to_generate(tmp_path: Path) -> None:
    exact_reuse = {
        "decision": "exact_reuse",
        "rationale": ["Reuse the smallest apparently matching research workflow."],
        "requirement_ids": ["REQ-001", "REQ-002"],
        "workflow_ref": {
            "workflow_id": "research.deepdive.rsi_demo",
            "version": "1.3",
        },
        "workflow_inputs": [],
        "workflow_bindings": [
            {"requirement_id": "REQ-001", "stage_ids": ["D1"]},
            {"requirement_id": "REQ-002", "stage_ids": ["D5"]},
        ],
        "requirements_gap": None,
    }
    generate = {
        "decision": "generate",
        "rationale": ["The selected workflow is not planner-compatible."],
        "requirement_ids": ["REQ-001", "REQ-002"],
        "workflow_ref": None,
        "workflow_inputs": [],
        "workflow_bindings": [],
        "requirements_gap": None,
    }
    model = ScriptedModel(decision_bodies=[exact_reuse, generate])

    result = planner.run_semantic_planning_pipeline(
        _requirement_ir(),
        tmp_path,
        model,
        ScriptedModel(),
        catalog=_catalog(),
    )

    assert result["planning_decision"]["generation"] == 1
    assert result["planning_decision"]["decision"] == "generate"
    assert result["plan_acceptance"]["decision"] == "accepted"
    assert model.calls.count(planner.DECISION_BODY_SCHEMA.name) == 2
    repair = json.loads((tmp_path / "strategy_repair_record.json").read_text())
    assert repair["status"] == "completed"
    assert (tmp_path / "strategy-generation-0" / "planning_decision.json").exists()
    assert (tmp_path / "strategy-generation-1" / "planning_decision.json").exists()
    assert not (tmp_path / "generation-0" / "planning_decision.json").exists()


def test_failed_validation_reason_names_the_actual_defect_codes() -> None:
    requirement_ir = _requirement_ir()
    decision = _decision(requirement_ir)
    plan_ir = _wrapped_plan(requirement_ir, decision)
    validation = {
        "validation_id": "validation-test",
        "status": "fail",
        "errors": [
            {
                "code": "NO_FEASIBLE_CAPSULE_COMPOSITION",
                "message": "No admitted capsule chain.",
                "repairable": False,
            }
        ],
    }

    acceptance = planner.decide_plan_acceptance(
        requirement_ir,
        _planning_context(requirement_ir),
        decision,
        plan_ir,
        validation,
        None,
        None,
        None,
        None,
        repair_attempted=True,
    )

    assert acceptance["decision"] == "failed"
    assert acceptance["reasons"] == [
        "Deterministic plan validation failed "
        "(NO_FEASIBLE_CAPSULE_COMPOSITION)."
    ]


def test_plan_repair_cannot_weaken_semantic_node_contract() -> None:
    previous = {
        "nodes": [
            {
                "node_id": "run_experiment",
                "logical_operator": "ScientificExperimentRunner",
                "depends_on": ["design_experiment"],
                "requirement_ids": ["REQ-001"],
                "operator_requirements": {
                    "execution_trust": "measured_execution"
                },
            }
        ]
    }
    repaired = {
        "nodes": [
            {
                "node_id": "run_experiment",
                "logical_operator": "ArtifactCurator",
                "depends_on": [],
                "requirement_ids": ["REQ-002"],
                "operator_requirements": {"execution_trust": "any"},
            }
        ]
    }

    codes = {
        row["code"]
        for row in planner._repair_preservation_errors(
            previous,
            repaired,
            {"ScientificExperimentRunner", "ArtifactCurator"},
        )
    }

    assert codes == {
        "REPAIR_DEPENDENCY_WEAKENED",
        "REPAIR_LOGICAL_OPERATOR_CHANGED",
        "REPAIR_REQUIREMENT_OWNERSHIP_CHANGED",
        "REPAIR_EXECUTION_TRUST_WEAKENED",
    }


def test_plan_repair_may_add_exact_requirement_named_by_reviewer() -> None:
    previous = {
        "nodes": [
            {
                "node_id": "discover_live_literature",
                "logical_operator": "ScientificLiteratureDiscoverer",
                "depends_on": [],
                "requirement_ids": ["R3", "R4"],
            },
            {
                "node_id": "synthesize_report",
                "logical_operator": "ScientificReportDrafter",
                "depends_on": ["discover_live_literature"],
                "requirement_ids": ["R2"],
            },
        ]
    }
    repaired = copy.deepcopy(previous)
    repaired["nodes"][0]["requirement_ids"] = ["R2", "R3", "R4"]
    defects = [
        {
            "code": "DISCOVERY_COVERAGE_REQUIREMENT_OMITTED",
            "path": "plan_ir.nodes[0].requirement_ids",
            "repairable": True,
            "requirement_ids": ["R2"],
        }
    ]

    assert planner._repair_preservation_errors(
        previous,
        repaired,
        {"ScientificLiteratureDiscoverer", "ScientificReportDrafter"},
        repair_defects=defects,
    ) == []


def test_plan_repair_may_add_exact_requirements_at_named_reviewer_node() -> None:
    previous = {
        "nodes": [
            {
                "node_id": "literature_discovery",
                "logical_operator": "ScientificLiteratureDiscoverer",
                "depends_on": [],
                "requirement_ids": ["R5"],
            },
            {
                "node_id": "combined_report",
                "logical_operator": "ScientificReportDrafter",
                "depends_on": ["literature_discovery"],
                "requirement_ids": ["R1"],
            },
        ]
    }
    repaired = copy.deepcopy(previous)
    repaired["nodes"][0]["requirement_ids"] = ["R4", "R5", "R15"]
    defects = [
        {
            "code": "DISCOVERY_REQUIREMENT_COVERAGE_OMITTED",
            "path": "plan_ir.nodes[literature_discovery]",
            "repairable": True,
            "requirement_ids": ["R4", "R15"],
        }
    ]

    assert planner._repair_preservation_errors(
        previous,
        repaired,
        {"ScientificLiteratureDiscoverer", "ScientificReportDrafter"},
        repair_defects=defects,
    ) == []


def test_plan_repair_may_add_exact_requirement_to_reviewer_node_slice() -> None:
    previous = {
        "nodes": [
            {
                "node_id": "literature_discovery",
                "logical_operator": "ScientificLiteratureDiscoverer",
                "requirement_ids": ["R4"],
            },
            {
                "node_id": "paper_ingestion",
                "logical_operator": "ScientificPaperIngestor",
                "requirement_ids": [],
            },
            {
                "node_id": "evidence_extraction",
                "logical_operator": "ScientificClaimExtractor",
                "requirement_ids": [],
            },
            {
                "node_id": "claim_verification",
                "logical_operator": "ScientificClaimVerifier",
                "requirement_ids": [],
            },
            {
                "node_id": "landscape_synthesis_plan",
                "logical_operator": "ScientificReportPlanner",
                "requirement_ids": ["R6", "R7"],
            },
            {
                "node_id": "technical_landscape_report",
                "logical_operator": "ScientificReportDrafter",
                "requirement_ids": ["R1", "R2", "R3", "R5"],
            },
        ]
    }
    repaired = copy.deepcopy(previous)
    repaired["nodes"][4]["requirement_ids"] = ["R4", "R6", "R7"]
    repaired["nodes"][5]["requirement_ids"] = ["R1", "R2", "R3", "R4", "R5"]
    defects = [
        {
            "code": "MATERIAL_REQUIREMENT_OWNERSHIP_OMISSION",
            "path": "$.plan_ir.nodes[4:6].requirement_ids",
            "repairable": True,
            "requirement_ids": ["R4"],
        }
    ]

    assert planner._repair_preservation_errors(
        previous,
        repaired,
        {
            "ScientificLiteratureDiscoverer",
            "ScientificPaperIngestor",
            "ScientificClaimExtractor",
            "ScientificClaimVerifier",
            "ScientificReportPlanner",
            "ScientificReportDrafter",
        },
        repair_defects=defects,
    ) == []


def test_plan_repair_uses_structured_requirement_ids_not_error_code_wording() -> None:
    previous = {
        "nodes": [
            {
                "node_id": "produce_landscape_report",
                "logical_operator": "ScientificReportDrafter",
                "requirement_ids": ["R1"],
            }
        ]
    }
    repaired = copy.deepcopy(previous)
    repaired["nodes"][0]["requirement_ids"] = ["R1", "R6", "R7"]
    defects = [
        {
            "code": "FINAL_SCOPE_VERIFICATION_GAP",
            "path": "plan_ir.nodes[0]",
            "repairable": True,
            "requirement_ids": ["R6", "R7"],
        }
    ]

    assert planner._repair_preservation_errors(
        previous,
        repaired,
        {"ScientificReportDrafter"},
        repair_defects=defects,
    ) == []


def test_named_requirement_defect_does_not_authorize_another_node() -> None:
    previous = {
        "nodes": [
            {
                "node_id": "literature_discovery",
                "logical_operator": "ScientificLiteratureDiscoverer",
                "depends_on": [],
                "requirement_ids": ["R5"],
            },
            {
                "node_id": "combined_report",
                "logical_operator": "ScientificReportDrafter",
                "depends_on": ["literature_discovery"],
                "requirement_ids": ["R1"],
            },
        ]
    }
    repaired = copy.deepcopy(previous)
    repaired["nodes"][1]["requirement_ids"] = ["R1", "R4", "R15"]
    defects = [
        {
            "code": "DISCOVERY_REQUIREMENT_COVERAGE_OMITTED",
            "path": "plan_ir.nodes[literature_discovery]",
            "repairable": True,
            "requirement_ids": ["R4", "R15"],
        }
    ]

    errors = planner._repair_preservation_errors(
        previous,
        repaired,
        {"ScientificLiteratureDiscoverer", "ScientificReportDrafter"},
        repair_defects=defects,
    )

    assert [row["code"] for row in errors] == [
        "REPAIR_REQUIREMENT_OWNERSHIP_CHANGED"
    ]


def test_non_ownership_field_defect_does_not_authorize_requirement_addition() -> None:
    previous = {
        "nodes": [
            {
                "node_id": "combined_report",
                "logical_operator": "ScientificReportDrafter",
                "depends_on": [],
                "requirement_ids": ["R1"],
            }
        ]
    }
    repaired = copy.deepcopy(previous)
    repaired["nodes"][0]["requirement_ids"] = ["R1", "R11"]
    defects = [
        {
            "code": "REPORT_REQUIREMENT_INPUTS_MISSING",
            "path": "plan_ir.nodes[combined_report].consumes",
            "repairable": True,
            "requirement_ids": ["R11"],
        }
    ]

    errors = planner._repair_preservation_errors(
        previous,
        repaired,
        {"ScientificReportDrafter"},
        repair_defects=defects,
    )

    assert [row["code"] for row in errors] == [
        "REPAIR_REQUIREMENT_OWNERSHIP_CHANGED"
    ]


def test_plan_repair_rejects_requirement_addition_not_named_by_reviewer() -> None:
    previous = {
        "nodes": [
            {
                "node_id": "discover_live_literature",
                "logical_operator": "ScientificLiteratureDiscoverer",
                "depends_on": [],
                "requirement_ids": ["R3", "R4"],
            }
        ]
    }
    repaired = copy.deepcopy(previous)
    repaired["nodes"][0]["requirement_ids"] = ["R2", "R3", "R4", "R9"]
    defects = [
        {
            "code": "DISCOVERY_COVERAGE_REQUIREMENT_OMITTED",
            "path": "plan_ir.nodes[0].requirement_ids",
            "repairable": True,
            "requirement_ids": ["R2"],
        }
    ]

    errors = planner._repair_preservation_errors(
        previous,
        repaired,
        {"ScientificLiteratureDiscoverer"},
        repair_defects=defects,
    )

    assert [row["code"] for row in errors] == [
        "REPAIR_REQUIREMENT_OWNERSHIP_CHANGED"
    ]


def _duplicate_claim_producer_repair() -> tuple[dict, dict, list[dict]]:
    paper = "schema:schemas/evidence/research_paper.v1.schema.json"
    claims = "schema:schemas/evidence/research_claims.v1.schema.json"
    plan = "schema:schemas/evidence/experiment_plan.v1.schema.json"
    trust = {"execution_trust": "evidence_transform"}
    previous = {
        "nodes": [
            {
                "node_id": "ingest",
                "depends_on": [],
                "produces": [{"artifact_type": paper}],
                "operator_requirements": trust,
            },
            {
                "node_id": "extract_claims",
                "depends_on": ["ingest"],
                "consumes": [paper],
                "produces": [{"artifact_type": claims}],
                "operator_requirements": trust,
            },
            {
                "node_id": "select_claims",
                "depends_on": ["ingest"],
                "consumes": [paper],
                "produces": [{"artifact_type": claims}],
                "requirement_ids": [],
                "operator_requirements": trust,
            },
            {
                "node_id": "design",
                "depends_on": ["select_claims"],
                "consumes": [claims],
                "produces": [{"artifact_type": plan}],
                "requirement_ids": ["R-DESIGN"],
                "operator_requirements": trust,
            },
        ]
    }
    repaired = {
        "nodes": [
            copy.deepcopy(previous["nodes"][0]),
            copy.deepcopy(previous["nodes"][1]),
            {
                **copy.deepcopy(previous["nodes"][3]),
                "depends_on": ["extract_claims"],
            },
        ]
    }
    defects = [
        {
            "code": "ARTIFACT_PRODUCER_DUPLICATE",
            "path": "nodes.2.produces",
            "repairable": True,
        }
    ]
    return previous, repaired, defects


def test_plan_repair_may_consolidate_exact_duplicate_producer_named_by_validator() -> None:
    previous, repaired, defects = _duplicate_claim_producer_repair()

    assert planner._repair_preservation_errors(
        previous,
        repaired,
        repair_defects=defects,
    ) == []


def test_plan_repair_cannot_consolidate_duplicate_without_exact_validator_defect() -> None:
    previous, repaired, _ = _duplicate_claim_producer_repair()

    errors = planner._repair_preservation_errors(previous, repaired)

    assert [row["code"] for row in errors] == ["REPAIR_DEPENDENCY_WEAKENED"]


def test_artifact_outcome_does_not_force_workspace_plan() -> None:
    planning_inputs = {
        "intent_ir": {
            "outcomes": [
                {
                    "class": "artifact",
                    "description": "A concise answer returned in the conversation.",
                }
            ]
        }
    }

    assert planner._accepted_inputs_declare_workspace_io(planning_inputs) is False


def test_execution_outcome_still_forces_governed_plan() -> None:
    planning_inputs = {
        "intent_ir": {
            "outcomes": [
                {
                    "class": "execution",
                    "description": "Run the requested benchmark.",
                }
            ]
        }
    }

    assert planner._accepted_inputs_declare_workspace_io(planning_inputs) is True


def _folded_report_plan_repair() -> tuple[dict, dict, dict]:
    claim_verdict = "schema:schemas/evidence/claim_verdict.v1.schema.json"
    report_plan = "schema:schemas/evidence/scientific_report_plan.v1.schema.json"
    report = "schema:schemas/evidence/scientific_report.v1.schema.json"
    previous = {
        "nodes": [
            {
                "node_id": "claim_verification",
                "logical_operator": "ScientificClaimVerifier",
                "depends_on": [],
                "requirement_ids": ["REQ-VERIFY"],
                "produces": [{"artifact_type": claim_verdict}],
            },
            {
                "node_id": "report_planning",
                "logical_operator": "ScientificReportPlanner",
                "depends_on": ["claim_verification"],
                "requirement_ids": [],
                "consumes": [claim_verdict],
                "produces": [{"artifact_type": report_plan}],
            },
            {
                "node_id": "report_draft",
                "logical_operator": "ScientificReportDrafter",
                "depends_on": ["claim_verification", "report_planning"],
                "requirement_ids": ["REQ-REPORT"],
                "consumes": [claim_verdict, report_plan],
                "produces": [{"artifact_type": report}],
            },
        ]
    }
    repaired = {
        "nodes": [
            copy.deepcopy(previous["nodes"][0]),
            {
                "node_id": "report_draft",
                "logical_operator": "ScientificReportDrafter",
                "depends_on": ["claim_verification"],
                "requirement_ids": ["REQ-REPORT"],
                "consumes": [claim_verdict],
                "produces": [{"artifact_type": report}],
            },
        ]
    }
    composition_catalog = {
        "nodes": [
            {
                "node_id": "report_draft",
                "execution_trust": "any",
                "admitted_candidate_ids": ["composition-001"],
                "search": {
                    "candidates": [
                        {
                            "candidate_id": "composition-001",
                            "steps": [
                                {
                                    "capsule_id": "cap.research-report-plan",
                                    "consumes": [claim_verdict],
                                    "produces": [report_plan],
                                },
                                {
                                    "capsule_id": "cap.scientific-report-draft",
                                    "consumes": [claim_verdict, report_plan],
                                    "produces": [report],
                                },
                            ],
                        }
                    ]
                },
            }
        ]
    }
    return previous, repaired, composition_catalog


def test_plan_repair_may_fold_requirement_free_support_node_into_composition() -> None:
    previous, repaired, composition_catalog = _folded_report_plan_repair()

    errors = planner._repair_preservation_errors(
        previous,
        repaired,
        {
            "ScientificClaimVerifier",
            "ScientificReportPlanner",
            "ScientificReportDrafter",
        },
        composition_catalog,
    )

    assert errors == []


def test_plan_repair_may_remove_duplicate_requirement_ownership() -> None:
    previous = {
        "nodes": [
            {"node_id": "discovery", "requirement_ids": ["R2", "R3"]},
            {"node_id": "report", "requirement_ids": ["R1", "R2", "R3"]},
        ]
    }
    repaired = {
        "nodes": [
            {"node_id": "discovery", "requirement_ids": ["R2", "R3"]},
            {"node_id": "report", "requirement_ids": ["R1"]},
        ]
    }

    errors = planner._repair_preservation_errors(previous, repaired)

    assert errors == []


def test_plan_repair_cannot_fold_dependency_that_owns_a_requirement() -> None:
    previous, repaired, composition_catalog = _folded_report_plan_repair()
    previous["nodes"][1]["requirement_ids"] = ["REQ-PLAN"]

    errors = planner._repair_preservation_errors(
        previous, repaired, None, composition_catalog
    )

    assert [row["code"] for row in errors] == ["REPAIR_DEPENDENCY_WEAKENED"]


def test_plan_repair_cannot_fold_dependency_without_inheriting_upstream_order() -> None:
    previous, repaired, composition_catalog = _folded_report_plan_repair()
    repaired["nodes"][1]["depends_on"] = []

    errors = planner._repair_preservation_errors(
        previous, repaired, None, composition_catalog
    )

    assert [row["code"] for row in errors] == ["REPAIR_DEPENDENCY_WEAKENED"]


def test_plan_repair_requires_every_admitted_path_to_preserve_folded_output() -> None:
    previous, repaired, composition_catalog = _folded_report_plan_repair()
    report = "schema:schemas/evidence/scientific_report.v1.schema.json"
    composition_catalog["nodes"][0]["admitted_candidate_ids"].append(
        "composition-002"
    )
    composition_catalog["nodes"][0]["search"]["candidates"].append(
        {
            "candidate_id": "composition-002",
            "steps": [
                {
                    "capsule_id": "cap.unsafe-direct-report",
                    "consumes": [
                        "schema:schemas/evidence/claim_verdict.v1.schema.json"
                    ],
                    "produces": [report],
                }
            ],
        }
    )

    errors = planner._repair_preservation_errors(
        previous, repaired, None, composition_catalog
    )

    assert [row["code"] for row in errors] == ["REPAIR_DEPENDENCY_WEAKENED"]


def test_plan_repair_cannot_fold_stronger_trust_into_weaker_composition() -> None:
    previous, repaired, composition_catalog = _folded_report_plan_repair()
    previous["nodes"][1]["operator_requirements"] = {
        "execution_trust": "measured_execution"
    }
    composition_catalog["nodes"][0]["execution_trust"] = "evidence_transform"

    errors = planner._repair_preservation_errors(
        previous, repaired, None, composition_catalog
    )

    assert [row["code"] for row in errors] == ["REPAIR_DEPENDENCY_WEAKENED"]


def test_plan_repair_may_remove_redundant_direct_dependency_still_implied_transitively() -> None:
    previous = {
        "nodes": [
            {"node_id": "ingest", "depends_on": []},
            {"node_id": "assess", "depends_on": ["ingest"]},
            {
                "node_id": "report",
                "depends_on": ["ingest", "assess"],
            },
        ]
    }
    repaired = copy.deepcopy(previous)
    repaired["nodes"][2]["depends_on"] = ["assess"]

    assert planner._repair_preservation_errors(previous, repaired) == []


def test_plan_repair_still_rejects_dependency_removed_from_all_paths() -> None:
    previous = {
        "nodes": [
            {"node_id": "ingest", "depends_on": []},
            {"node_id": "assess", "depends_on": []},
            {
                "node_id": "report",
                "depends_on": ["ingest", "assess"],
            },
        ]
    }
    repaired = copy.deepcopy(previous)
    repaired["nodes"][2]["depends_on"] = ["assess"]

    errors = planner._repair_preservation_errors(previous, repaired)

    assert [row["code"] for row in errors] == ["REPAIR_DEPENDENCY_WEAKENED"]


def test_valid_semantic_plan_passes_and_builds_truthful_binding_trace() -> None:
    requirement_ir = _requirement_ir()
    decision = _decision(requirement_ir)
    plan_ir = _wrapped_plan(requirement_ir, decision)

    validation = planner.validate_plan_ir(requirement_ir, decision, plan_ir, _catalog())
    trace = planner.build_binding_trace(requirement_ir, plan_ir)

    assert validation["status"] == "pass"
    assert validation["errors"] == []
    assert trace["verdict"] == "pass"
    assert trace["bindings"]["REQ-001"] == {
        "owners": ["implement"],
        "artifacts": ["artifact.patch_diff"],
        "verifiers": ["check.patch.v1"],
    }


def test_plan_validation_rejects_verifier_bound_to_wrong_artifact_type() -> None:
    requirement_ir = {
        "schema_version": "solar.requirement_ir.v1",
        "id": "req-verifier-artifact-fit",
        "requirements": [
            {
                "id": "REQ-001",
                "source_text": "Produce a reproducibility experiment plan.",
                "verification_method": "check.scientific.experiment_plan.v1",
            }
        ],
    }
    decision = _decision(requirement_ir)
    decision["requirement_ids"] = ["REQ-001"]
    plan_ir = _wrapped_plan(
        requirement_ir,
        decision,
        {
            "nodes": [
                {
                    "node_id": "literature_shortlist",
                    "logical_operator": "ScientificLiteratureDiscoverer",
                    "objective": "Discover a bounded literature shortlist.",
                    "depends_on": [],
                    "consumes": ["schema:request-envelope.schema.json"],
                    "produces": [
                        {
                            "artifact_type": "schema:schemas/evidence/literature_discovery.v1.schema.json",
                            "verifier_ids": ["check.scientific.experiment_plan.v1"],
                            "materialization": {
                                "kind": "file",
                                "path": "literature_discovery.json",
                                "route": "sprint_private",
                            },
                        }
                    ],
                    "requirement_ids": ["REQ-001"],
                    "operator_requirements": {
                        "capabilities": ["research_synthesis"],
                        "network": "required",
                        "execution_trust": "any",
                        "minimum_context_tokens": 2000,
                        "effects": ["read", "write", "execute", "network"],
                    },
                    "gate_requirement": "shortlist_traceable",
                    "workspace_reads": [],
                }
            ]
        },
    )

    validation = planner.validate_plan_ir(
        requirement_ir,
        decision,
        plan_ir,
        _catalog(),
    )

    assert "VERIFIER_ARTIFACT_TYPE_MISMATCH" in {
        row["code"] for row in validation["errors"]
    }


def test_plan_prompt_exposes_semantic_capsule_abi_not_physical_catalog() -> None:
    requirement_ir = _requirement_ir()
    prompt = planner._plan_prompt(
        requirement_ir,
        _decision(requirement_ir),
        _catalog(),
        {"requirement_ir": requirement_ir},
        planner.evaluation_planning.load_evaluation_check_registry(),
        generation=0,
    )
    payload = json.loads(prompt)

    assert "capability_capsules" not in payload
    assert payload["capability_capsule_abis"]
    assert payload["evaluation_check_abis"]
    assert payload["controller_input_artifact_types"] == sorted(
        planner._CONTROLLER_INPUT_TYPES
    )
    assert "schema:request-envelope.schema.json" in payload[
        "controller_input_artifact_types"
    ]
    assert "implementation-only support steps out of PlanIR" in payload["instruction"]
    assert "type `collection`" in payload["instruction"]
    assert "source- or literature-discovery node must own" in payload["instruction"]
    assert "full research query, not a generic topic summary" in payload["instruction"]
    assert "permission envelope for the capsule" in payload["instruction"]
    assert "include `execute` whenever a required capsule ABI lists `execute`" in payload[
        "instruction"
    ]
    assert "at most one logical Critic, Verifier, or Evaluator node" in payload[
        "instruction"
    ]
    assert "files that already exist in the source" in payload["instruction"]
    assert "declare that upstream artifact's exact artifact_type in consumes" in payload[
        "instruction"
    ]
    experiment_check = next(
        row
        for row in payload["evaluation_check_abis"]
        if row["check_id"] == "check.scientific.experiment_plan.v1"
    )
    assert experiment_check["artifact_types"] == [
        "schema:schemas/evidence/experiment_plan.v1.schema.json"
    ]
    first = payload["capability_capsule_abis"][0]
    assert set(first) == {
        "capsule_id",
        "description",
        "task_types",
        "consumes",
        "produces",
            "active_effects",
            "executable",
            "execution_trust",
        }
    assert "operator_compatibility" not in prompt
    assert len(prompt.encode("utf-8")) < 60000


def test_plan_repair_prompt_explains_unrequested_capsule_effect() -> None:
    requirement_ir = _requirement_ir()
    prompt = planner._plan_prompt(
        requirement_ir,
        _decision(requirement_ir),
        _catalog(),
        {"requirement_ir": requirement_ir},
        planner.evaluation_planning.load_evaluation_check_registry(),
        generation=1,
        previous=_plan_body(),
        defects=[
            {
                "code": "NO_FEASIBLE_CAPSULE_COMPOSITION",
                "closest_exclusions": [
                    {
                        "capsule_id": "cap.research-literature-discover",
                        "reason_codes": ["UNREQUESTED_EXECUTE_EFFECT"],
                    }
                ],
            }
        ],
    )
    payload = json.loads(prompt)

    assert "UNREQUESTED_<EFFECT>_EFFECT" in payload["repair_instruction"]
    assert "operator_requirements.effects" in payload["repair_instruction"]
    assert payload["defects"][0]["closest_exclusions"][0]["reason_codes"] == [
        "UNREQUESTED_EXECUTE_EFFECT"
    ]
    assert "Do not delete or bypass an established dependency" in payload[
        "repair_instruction"
    ]
    assert "replacing invalid consumed/produced artifact identities" in payload[
        "repair_instruction"
    ]
    assert payload["previous"]["nodes"]


def test_discovery_plan_enriches_only_model_owned_scope_in_runtime_goal(tmp_path: Path) -> None:
    requirement_ir = _battery_research_requirement_ir()
    decision = {
        "planning_decision_id": "planning-decision-battery",
        "decision": "generate",
    }
    body = {
        "nodes": [
            {
                "node_id": "discover",
                "logical_operator": "ScientificLiteratureDiscoverer",
                "objective": "Collect literature for a grid-storage battery comparison.",
                "depends_on": [],
                "consumes": ["schema:request-envelope.schema.json"],
                "produces": [
                    {
                        "artifact_type": "schema:schemas/evidence/literature_discovery.v1.schema.json",
                        "verifier_ids": ["check.scientific.literature_discovery.v1"],
                        "materialization": {
                            "kind": "file",
                            "path": "literature_discovery.json",
                            "route": "sprint_private",
                        },
                    }
                ],
                "requirement_ids": ["R2", "R3"],
                "operator_requirements": {
                    "capabilities": ["source_discovery"],
                    "network": "required",
                    "execution_trust": "measured_execution",
                    "minimum_context_tokens": 2000,
                    "effects": ["read", "write", "execute", "network"],
                },
                "gate_requirement": "literature_is_source_backed_and_in_scope",
                "workspace_reads": [],
            }
        ]
    }
    model = ScriptedModel(plan_bodies=[body])

    plan_ir = planner.compile_plan_candidate(
        requirement_ir,
        decision,
        _catalog(),
        {"requirement_ir": requirement_ir},
        planner.evaluation_planning.load_evaluation_check_registry(),
        model,
        tmp_path,
    )

    node = plan_ir["nodes"][0]
    # Requirement ownership is semantic model output. The deterministic
    # enrichment below may expose details and verifiers, but must not assign it.
    assert node["requirement_ids"] == ["R2", "R3"]
    assert "R1" not in node["requirement_ids"]
    assert "lithium-ion, sodium-ion, solid-state, and lithium-sulfur" in node["objective"]
    assert "energy density, lifetime, safety, material availability" in node["objective"]
    assert "commercial readiness" in node["objective"]
    assert node["objective"].count("Authoritative discovery scope:") == 1
    assert "check.intent_constraint_coverage.v1" in node["produces"][0]["verifier_ids"]

    graph = planner._generated_task_graph_proposal(
        requirement_ir,
        plan_ir,
        {
            "nodes": [
                {
                    "node_id": "discover",
                    "selected_capsule_id": "cap.research-retrieval",
                    "dispatch_task_type": "research",
                    "fallback_capsule_ids": [],
                    "rationale": "Source-backed discovery capsule.",
                }
            ]
        },
        sprint_id="sprint-battery-scope",
    )
    runtime_node = graph["nodes"][0]
    assert runtime_node["requirement_ids"] == ["R2", "R3"]
    assert runtime_node["goal"] == node["objective"]


def test_r16_compile_preserves_exact_model_owned_discovery_requirements(
    tmp_path: Path,
) -> None:
    requirement_ir = _r16_research_requirement_ir()
    decision = {
        "planning_decision_id": "planning-decision-r16",
        "decision": "generate",
    }
    raw_body = _r16_research_plan_body()
    raw_discovery_ids = copy.deepcopy(raw_body["nodes"][0]["requirement_ids"])

    plan_ir = planner.compile_plan_candidate(
        requirement_ir,
        decision,
        _catalog(),
        {"requirement_ir": requirement_ir},
        planner.evaluation_planning.load_evaluation_check_registry(),
        ScriptedModel(plan_bodies=[raw_body]),
        tmp_path,
    )

    discovery = plan_ir["nodes"][0]
    assert raw_discovery_ids == ["R4", "R5", "R6", "R7", "R9", "R14"]
    assert discovery["requirement_ids"] == raw_discovery_ids
    assert "[R4]" in discovery["objective"]
    assert "[R9]" in discovery["objective"]
    assert "[R8]" not in discovery["objective"]
    assert "[R10]" not in discovery["objective"]


def test_r16_single_repair_removes_downstream_discovery_ownership_and_passes(
    tmp_path: Path,
) -> None:
    requirement_ir = _r16_research_requirement_ir()
    requirement_ids = [row["requirement_id"] for row in requirement_ir["requirements"]]
    decision_body = {
        "decision": "generate",
        "rationale": ["The request needs discovery and source-grounded synthesis."],
        "requirement_ids": requirement_ids,
        "workflow_ref": None,
        "workflow_inputs": [],
        "workflow_bindings": [],
        "requirements_gap": None,
    }
    fidelity_failure = {
        "checks": [
            {
                "kind": "requirement_preservation",
                "status": "fail",
                "reason": "Discovery overclaims downstream report requirements.",
            },
            {
                "kind": "smallest_sufficient_plan",
                "status": "pass",
                "reason": "Discovery and synthesis are the smallest sufficient plan.",
            },
            {
                "kind": "dependency_soundness",
                "status": "pass",
                "reason": "Synthesis consumes the discovery artifact.",
            },
            {
                "kind": "no_unrequested_effects",
                "status": "pass",
                "reason": "Declared effects are required by the two nodes.",
            },
        ],
        "errors": [
            {
                "code": "DISCOVERY_OVERCLAIMS_DOWNSTREAM_REQUIREMENTS",
                "path": "nodes.0.requirement_ids",
                "message": "Remove R8 and R10-R13 from discovery; synthesis already owns them.",
                "repairable": True,
                "requirement_ids": ["R8", "R10", "R11", "R12", "R13"],
            }
        ],
        "warnings": [],
    }
    planner_model = ScriptedModel(
        decision_bodies=[decision_body],
        plan_bodies=[
            _r16_research_plan_body(overassign_discovery=True),
            _r16_research_plan_body(),
        ],
    )
    reviewer_model = ScriptedModel(fidelity_reviews=[fidelity_failure])

    result = planner.run_semantic_planning_pipeline(
        requirement_ir,
        tmp_path,
        planner_model,
        reviewer_model,
        catalog=_catalog(),
    )

    discovery = next(
        row
        for row in result["plan_ir"]["nodes"]
        if row["node_id"] == "discover_current_public_evidence"
    )
    assert planner_model.calls.count(planner.PLAN_BODY_SCHEMA.name) == 2
    assert result["plan_ir"]["generation"] == 1
    assert discovery["requirement_ids"] == ["R4", "R5", "R6", "R7", "R9", "R14"]
    assert result["plan_validation"]["status"] == "pass"
    assert result["plan_fidelity"]["status"] == "pass"
    assert result["plan_acceptance"]["decision"] == "accepted"


def test_fidelity_prompt_does_not_confuse_runtime_execute_with_experiment() -> None:
    requirement_ir = _requirement_ir()
    prompt = planner._fidelity_prompt(
        requirement_ir,
        _decision(requirement_ir),
        _wrapped_plan(requirement_ir, _decision(requirement_ir)),
        {"requirement_ir": requirement_ir},
    )
    instruction = json.loads(prompt)["instruction"]

    assert "generic `execute` effect" in instruction
    assert "does not itself mean scientific experiment execution" in instruction
    assert "claim_verdict.v1 carries verified claim_text and evidence_ids" in instruction
    assert "Do not call a support node unnecessary solely" in instruction
    assert "changes authorization, execution status, claim evaluation, or final synthesis" in instruction


def test_uncovered_requirement_fails_without_default_owner_mapping() -> None:
    requirement_ir = _requirement_ir()
    decision = _decision(requirement_ir)
    body = _plan_body()
    body["nodes"][0]["requirement_ids"] = ["REQ-001"]
    plan_ir = _wrapped_plan(requirement_ir, decision, body)

    validation = planner.validate_plan_ir(requirement_ir, decision, plan_ir, _catalog())
    trace = planner.build_binding_trace(requirement_ir, plan_ir)

    assert validation["status"] == "fail"
    assert "REQUIREMENTS_UNCOVERED" in {row["code"] for row in validation["errors"]}
    assert trace["verdict"] == "fail"
    assert trace["uncovered"] == ["REQ-002"]
    assert "REQ-002" not in trace["bindings"]


def test_invented_verifier_cannot_manufacture_requirement_coverage() -> None:
    requirement_ir = _requirement_ir()
    decision = _decision(requirement_ir)
    body = _plan_body()
    body["nodes"][0]["produces"][0]["verifier_ids"] = ["verify.combined-made-up.v1"]
    plan_ir = _wrapped_plan(requirement_ir, decision, body)

    validation = planner.validate_plan_ir(requirement_ir, decision, plan_ir, _catalog())
    trace = planner.build_binding_trace(requirement_ir, plan_ir)
    codes = {row["code"] for row in validation["errors"]}

    assert "REQUIREMENT_VERIFIER_MISSING" in codes
    assert "VERIFIER_NOT_OWNED" in codes
    assert trace["verdict"] == "fail"
    assert trace["uncovered"] == ["REQ-001"]


def test_compatible_auto_artifact_gate_can_coexist_with_requirement_check() -> None:
    requirement_ir = {
        "schema_version": "solar.requirement_ir.v1",
        "id": "req-auto-artifact-gate",
        "requirements": [
            {
                "id": "REQ-001",
                "source_text": "Ground every material claim in retained evidence.",
                "verification_method": "check.claim_evidence_resolved",
            }
        ],
    }
    decision = _decision(requirement_ir)
    decision["requirement_ids"] = ["REQ-001"]
    body = {
        "nodes": [
            {
                "node_id": "verify_claims",
                "logical_operator": "ScientificClaimVerifier",
                "objective": "Verify the source-grounded claims.",
                "depends_on": [],
                "consumes": [],
                "produces": [
                    {
                        "artifact_type": "schema:schemas/evidence/claim_verdict.v1.schema.json",
                        "verifier_ids": [
                            "check.claim_evidence_resolved",
                            "check.scientific.claim_verdict.v1",
                        ],
                        "materialization": {
                            "kind": "file",
                            "path": "claim_verdict.json",
                            "route": "sprint_private",
                        },
                    }
                ],
                "requirement_ids": ["REQ-001"],
                "operator_requirements": {
                    "capabilities": ["claim_verification"],
                    "network": "optional",
                    "execution_trust": "evidence_transform",
                    "minimum_context_tokens": 4000,
                    "effects": ["read", "write", "execute"],
                },
                "gate_requirement": "claim_evidence_review",
                "workspace_reads": [],
            }
        ]
    }
    plan_ir = _wrapped_plan(requirement_ir, decision, body)

    validation = planner.validate_plan_ir(
        requirement_ir,
        decision,
        plan_ir,
        _catalog(),
    )

    assert "VERIFIER_NOT_OWNED" not in {
        row["code"] for row in validation["errors"]
    }


def test_plan_prompt_exposes_only_explicit_typed_upstream_artifacts() -> None:
    requirement_ir = _requirement_ir()
    explicit_type = "schema:schemas/evidence/research_claims.v1.schema.json"
    prompt = planner._plan_prompt(
        requirement_ir,
        _decision(requirement_ir),
        _catalog(),
        {
            "requirement_ir": requirement_ir,
            "supplied_claim": {
                "artifact_type": explicit_type,
                "schema_version": "research_claims.v1",
            },
            "untyped_attachment": {"schema_version": "experiment_plan.v1"},
        },
        planner.evaluation_planning.load_evaluation_check_registry(),
        generation=0,
    )

    admitted = json.loads(prompt)["controller_input_artifact_types"]
    assert explicit_type in admitted
    assert "experiment_plan.v1" not in admitted


def test_plan_validation_accepts_explicit_upstream_artifact_without_producer() -> None:
    requirement_ir = _requirement_ir()
    decision = _decision(requirement_ir)
    plan_ir = _wrapped_plan(requirement_ir, decision, _plan_body())
    external_type = "artifact.explicit_upstream_input"
    plan_ir["nodes"][0]["consumes"].append(external_type)

    validation = planner.validate_plan_ir(
        requirement_ir,
        decision,
        plan_ir,
        _catalog(),
        upstream_artifact_types={external_type},
    )

    assert not any(
        row["code"] == "ARTIFACT_INPUT_UNRESOLVED"
        and external_type in row["message"]
        for row in validation["errors"]
    )


def test_collection_capsule_requires_directory_materialization() -> None:
    requirement_ir = {
        "schema_version": "solar.requirement_ir.v1",
        "id": "req-discovery-ingest",
        "requirements": [
            {
                "id": "REQ-001",
                "source_text": "Ingest the discovered papers.",
                "verification_method": "check.scientific.research_paper.v1",
            }
        ],
    }
    decision = _decision(requirement_ir)
    decision["requirement_ids"] = ["REQ-001"]
    body = {
        "nodes": [
            {
                "node_id": "ingest_discovered_sources",
                "logical_operator": "ScientificPaperIngestor",
                "objective": "Ingest every selected discovery candidate.",
                "depends_on": [],
                "consumes": [
                    "schema:schemas/evidence/literature_discovery.v1.schema.json"
                ],
                "produces": [
                    {
                        "artifact_type": "schema:schemas/evidence/research_paper.v1.schema.json",
                        "verifier_ids": ["check.scientific.research_paper.v1"],
                        "materialization": {
                            "kind": "file",
                            "path": "research_paper.json",
                            "route": "sprint_private",
                        },
                    }
                ],
                "requirement_ids": ["REQ-001"],
                "operator_requirements": {
                    "capabilities": ["data_extraction", "scientific_evidence"],
                    "network": "required",
                    "execution_trust": "evidence_transform",
                    "minimum_context_tokens": 4000,
                    "effects": ["read", "write", "execute", "network"],
                },
                "gate_requirement": "paper_evidence_review",
                "workspace_reads": [],
            }
        ]
    }
    plan_ir = _wrapped_plan(requirement_ir, decision, body)
    catalog = _catalog()
    composition_catalog = planner.build_plan_composition_catalog(
        requirement_ir,
        _planning_context(requirement_ir),
        plan_ir,
        catalog,
    )

    validation = planner.validate_plan_ir(
        requirement_ir,
        decision,
        plan_ir,
        catalog,
        composition_catalog,
    )

    assert "COLLECTION_MATERIALIZATION_REQUIRES_DIRECTORY" in {
        row["code"] for row in validation["errors"]
    }


def test_consumed_artifact_requires_real_upstream_dependency() -> None:
    requirement_ir = _requirement_ir()
    decision = _decision(requirement_ir)
    body = _plan_body()
    body["nodes"].append(
        {
            "node_id": "review",
            "logical_operator": "Verifier",
            "objective": "Review the produced patch against the accepted requirements.",
            "depends_on": [],
            "consumes": ["artifact.patch_diff"],
            "produces": [
                {
                    "artifact_type": "artifact.eval_md",
                    "verifier_ids": ["check.review.v1"],
                    "materialization": {
                        "kind": "file",
                        "path": "review.md",
                        "route": "sprint_private",
                    },
                }
            ],
            "requirement_ids": [],
            "operator_requirements": {
                "capabilities": ["test_execution"],
                "network": "forbidden",
                "execution_trust": "any",
                "minimum_context_tokens": 8000,
                "effects": ["read"],
            },
            "gate_requirement": "independent_review",
            "workspace_reads": [],
        }
    )
    plan_ir = _wrapped_plan(requirement_ir, decision, body)

    validation = planner.validate_plan_ir(requirement_ir, decision, plan_ir, _catalog())

    assert "ARTIFACT_DEPENDENCY_MISSING" in {
        row["code"] for row in validation["errors"]
    }


def test_pipeline_repairs_once_then_accepts_and_hash_chain_verifies(tmp_path: Path) -> None:
    bad = _plan_body("NotARegisteredLogicalOperator")
    good = _plan_body()
    planner_model = ScriptedModel(plan_bodies=[bad, good])
    reviewer_model = ScriptedModel()

    result = planner.run_semantic_planning_pipeline(
        _requirement_ir(), tmp_path, planner_model, reviewer_model, catalog=_catalog()
    )

    assert result["plan_ir"]["generation"] == 1
    assert result["plan_acceptance"]["decision"] == "accepted"
    assert result["plan_acceptance"]["runtime_handoff_allowed"] is False
    assert result["plan_acceptance"]["repair"] == {
        "attempted": True,
        "maximum_attempts": 1,
    }
    assert planner_model.calls.count(planner.PLAN_BODY_SCHEMA.name) == 2
    assert planner.verify_semantic_planning_chain(tmp_path) == []


def test_pipeline_can_apply_two_distinct_bounded_plan_repairs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(planner, "MAX_REPAIRS", 2)
    bad = _plan_body("NotARegisteredLogicalOperator")
    planner_model = ScriptedModel(plan_bodies=[bad, bad, _plan_body()])
    reviewer_model = ScriptedModel()

    result = planner.run_semantic_planning_pipeline(
        _requirement_ir(), tmp_path, planner_model, reviewer_model, catalog=_catalog()
    )

    assert result["plan_ir"]["generation"] == 2
    assert result["plan_validation"]["status"] == "pass"
    assert result["plan_acceptance"]["decision"] == "accepted"
    assert result["plan_acceptance"]["repair"] == {
        "attempted": True,
        "maximum_attempts": 2,
    }
    assert planner_model.calls.count(planner.PLAN_BODY_SCHEMA.name) == 3
    assert planner.verify_semantic_planning_chain(tmp_path) == []


def test_pipeline_combines_mechanical_and_semantic_defects_before_one_repair(
    tmp_path: Path,
) -> None:
    semantic_failure = {
        "checks": [
            {
                "kind": "requirement_preservation",
                "status": "pass",
                "reason": "The requirements remain represented.",
            },
            {
                "kind": "smallest_sufficient_plan",
                "status": "fail",
                "reason": "The first logical plan contains an unnecessary support node.",
            },
            {
                "kind": "dependency_soundness",
                "status": "pass",
                "reason": "The declared dependency is ordered correctly.",
            },
            {
                "kind": "no_unrequested_effects",
                "status": "pass",
                "reason": "No extra effect is requested.",
            },
        ],
        "errors": [
            {
                "code": "UNNECESSARY_LOGICAL_NODE",
                "path": "nodes.0",
                "message": "Remove the implementation-only support node.",
                "repairable": True,
                "requirement_ids": [],
            }
        ],
        "warnings": [],
    }
    planner_model = ScriptedModel(
        plan_bodies=[_plan_body("NotARegisteredLogicalOperator"), _plan_body()]
    )
    reviewer_model = ScriptedModel(fidelity_reviews=[semantic_failure])

    result = planner.run_semantic_planning_pipeline(
        _requirement_ir(),
        tmp_path,
        planner_model,
        reviewer_model,
        catalog=_catalog(),
    )

    repair_prompt = next(
        json.loads(prompt)
        for prompt in planner_model.prompts
        if '"repair_instruction"' in prompt
    )
    assert {row["code"] for row in repair_prompt["defects"]} >= {
        "LOGICAL_OPERATOR_UNKNOWN",
        "UNNECESSARY_LOGICAL_NODE",
    }
    assert result["plan_ir"]["generation"] == 1
    assert result["plan_validation"]["status"] == "pass"
    assert result["plan_fidelity"]["status"] == "pass"
    assert result["plan_acceptance"]["decision"] == "accepted"


def test_pipeline_repairs_generation_zero_capsule_unsat_to_viable_plan(tmp_path: Path) -> None:
    unsatisfiable = _plan_body()
    unsatisfiable["nodes"][0]["operator_requirements"]["effects"] = ["read"]
    planner_model = ScriptedModel(plan_bodies=[unsatisfiable, _plan_body()])

    result = planner.run_semantic_planning_pipeline(
        _requirement_ir(), tmp_path, planner_model, ScriptedModel(), catalog=_catalog()
    )
    generation_zero_validation = json.loads(
        (tmp_path / "generation-0" / "plan_validation.json").read_text(encoding="utf-8")
    )
    viability_error = next(
        row
        for row in generation_zero_validation["errors"]
            if row["code"] == "NO_FEASIBLE_CAPSULE_COMPOSITION"
    )

    assert viability_error["node_id"] == "implement"
    assert 1 <= len(viability_error["closest_exclusions"]) <= 3
    assert result["plan_ir"]["generation"] == 1
    assert result["plan_validation"]["status"] == "pass"
    assert result["plan_acceptance"]["decision"] == "accepted"
    assert planner_model.calls.count(planner.PLAN_BODY_SCHEMA.name) == 2


def test_pipeline_stops_after_generation_one_capsule_unsat_persists(tmp_path: Path) -> None:
    unsatisfiable = _plan_body()
    unsatisfiable["nodes"][0]["operator_requirements"]["effects"] = ["read"]
    planner_model = ScriptedModel(
        plan_bodies=[copy.deepcopy(unsatisfiable), copy.deepcopy(unsatisfiable)]
    )

    result = planner.run_semantic_planning_pipeline(
        _requirement_ir(), tmp_path, planner_model, ScriptedModel(), catalog=_catalog()
    )

    assert result["plan_ir"]["generation"] == 1
    assert result["plan_validation"]["status"] == "fail"
    assert "NO_FEASIBLE_CAPSULE_COMPOSITION" in {
        row["code"] for row in result["plan_validation"]["errors"]
    }
    assert result["plan_fidelity"]["status"] == "pass"
    assert result["binding_trace"] is None
    assert result["plan_acceptance"]["decision"] == "failed"
    assert result["plan_acceptance"]["repair"] == {
        "attempted": True,
        "maximum_attempts": 1,
    }
    assert planner_model.calls.count(planner.PLAN_BODY_SCHEMA.name) == 2


def test_direct_response_stops_without_plan_or_runtime_handoff(tmp_path: Path) -> None:
    planner_model = ScriptedModel(decision="direct_response")
    reviewer_model = ScriptedModel()

    result = planner.run_semantic_planning_pipeline(
        _requirement_ir(), tmp_path, planner_model, reviewer_model, catalog=_catalog()
    )

    assert result["plan_ir"] is None
    assert result["direct_response"]["answer"]
    assert result["planning_decision"]["producer"]["role"] == "planner"
    assert result["planning_decision"]["producer"]["component"] == "elastic_planner"
    assert result["direct_response"]["producer"]["role"] == "planner"
    assert result["direct_response"]["producer"]["component"] == "elastic_planner"
    assert result["direct_response_review"]["status"] == "pass"
    assert result["direct_response_review"]["reviewer"]["role"] == "evaluator"
    assert (
        result["direct_response_review"]["reviewer"]["component"]
        == "direct_response_reviewer"
    )
    assert result["plan_acceptance"]["decision"] == "direct_response"
    assert result["plan_acceptance"]["runtime_handoff_allowed"] is False
    assert planner.PLAN_BODY_SCHEMA.name not in planner_model.calls
    assert planner.verify_semantic_planning_chain(tmp_path) == []


def test_authoritative_direct_answer_route_is_planner_policy_not_compiler_answer(
    tmp_path: Path,
) -> None:
    requirement_ir = _requirement_ir()
    requirement_ir.update(
        {
            "request_type": "direct_answer",
            "planner_hints": {
                "preferred_outcome": "direct_answer",
                "runtime_handoff_allowed": False,
                "response_authority": "planner",
            },
        }
    )
    planner_model = ScriptedModel()

    result = planner.run_semantic_planning_pipeline(
        requirement_ir,
        tmp_path,
        planner_model,
        ScriptedModel(),
        catalog=_catalog(),
    )

    assert result["planning_decision"]["decision"] == "direct_response"
    assert result["planning_decision"]["producer"] == {
        "method": "policy",
        "provider": "solar",
        "model": "planner-direct-route-v1",
        "role": "planner",
        "component": "elastic_planner",
    }
    assert planner.DECISION_BODY_SCHEMA.name not in planner_model.calls
    assert planner_model.calls.count(planner.DIRECT_RESPONSE_BODY_SCHEMA.name) == 1
    assert result["plan_acceptance"]["runtime_handoff_allowed"] is False


def test_generated_plan_rejects_multiple_llm_evaluator_nodes() -> None:
    requirement_ir = _requirement_ir()
    decision = _decision(requirement_ir)
    body = _plan_body()
    first = body["nodes"][0]
    first["logical_operator"] = "Critic"
    second = copy.deepcopy(first)
    second["node_id"] = "final_verifier"
    second["logical_operator"] = "Verifier"
    second["depends_on"] = [first["node_id"]]
    body["nodes"].append(second)
    plan_ir = _wrapped_plan(requirement_ir, decision, body)

    validation = planner.validate_plan_ir(
        requirement_ir,
        decision,
        plan_ir,
        _catalog(),
    )

    assert "MULTIPLE_LLM_EVALUATOR_NODES" in {
        row["code"] for row in validation["errors"]
    }


def test_direct_response_has_one_bounded_repair(tmp_path: Path) -> None:
    failed_review = {
        "checks": [
            {"kind": "requirement_coverage", "status": "fail", "reason": "One requirement is too implicit."},
            {"kind": "answer_fidelity", "status": "pass", "reason": "No changed meaning."},
            {"kind": "factual_restraint", "status": "pass", "reason": "No fabricated execution."},
        ],
        "errors": [
            {
                "code": "DIRECT_REQUIREMENT_IMPLICIT",
                "message": "Make both requirements explicit.",
                "repairable": True,
            }
        ],
        "warnings": [],
    }
    reviewer = ScriptedModel(
        response_reviews=[failed_review, ScriptedModel().generate(
            "", planner.DIRECT_RESPONSE_REVIEW_BODY_SCHEMA, tmp_path / "unused"
        )]
    )
    planner_model = ScriptedModel(decision="direct_response")

    result = planner.run_semantic_planning_pipeline(
        _requirement_ir(), tmp_path / "run", planner_model, reviewer, catalog=_catalog()
    )

    assert result["direct_response"]["generation"] == 1
    assert result["plan_acceptance"]["decision"] == "direct_response"
    assert result["plan_acceptance"]["repair"]["attempted"] is True
    assert planner_model.calls.count(planner.DIRECT_RESPONSE_BODY_SCHEMA.name) == 2


def test_hash_chain_detects_plan_tampering(tmp_path: Path) -> None:
    planner_model = ScriptedModel()
    result = planner.run_semantic_planning_pipeline(
        _requirement_ir(), tmp_path, planner_model, ScriptedModel(), catalog=_catalog()
    )
    assert result["plan_acceptance"]["decision"] == "accepted"

    plan_ir = json.loads((tmp_path / "plan_ir.json").read_text(encoding="utf-8"))
    plan_ir["nodes"][0]["objective"] = "Tampered after admission"
    (tmp_path / "plan_ir.json").write_text(json.dumps(plan_ir), encoding="utf-8")

    assert "acceptance.refs.plan_ir.hash_mismatch" in planner.verify_semantic_planning_chain(
        tmp_path
    )


def test_upstream_artifact_bundle_is_visible_and_hash_bound(tmp_path: Path) -> None:
    planner_model = ScriptedModel(decision="direct_response")
    upstream = {
        "input": {
            "schema_version": "solar.input.v1",
            "text": "Explain the accepted request without changing files.",
        },
        "intent_ir": {
            "schema_version": "solar.intent_ir.v3",
            "intent_ir_id": "intent-context-test",
        },
        "requirement_acceptance": {
            "schema_version": "solar.requirement_acceptance.v1",
            "decision": "accepted",
        },
        "supplied_claim": {
            "artifact_type": "schema:schemas/evidence/research_claims.v1.schema.json",
            "schema_version": "research_claims.v1",
        },
    }
    result = planner.run_semantic_planning_pipeline(
        _requirement_ir(),
        tmp_path,
        planner_model,
        ScriptedModel(),
        catalog=_catalog(),
        upstream_artifacts=upstream,
    )

    context = json.loads((tmp_path / "planning_context.json").read_text())
    assert {row["name"] for row in context["artifacts"]} == {
        "input",
        "intent_ir",
        "requirement_acceptance",
        "requirement_ir",
        "supplied_claim",
    }
    supplied_claim_row = next(
        row for row in context["artifacts"] if row["name"] == "supplied_claim"
    )
    assert supplied_claim_row["artifact_type"] == (
        "schema:schemas/evidence/research_claims.v1.schema.json"
    )
    assert result["planning_decision"]["planning_context_ref"]["sha256"] == (
        sha256_payload(context)
    )
    assert any("Explain the accepted request" in prompt for prompt in planner_model.prompts)
    assert planner.verify_semantic_planning_chain(tmp_path) == []

    input_path = tmp_path / "inputs" / "input.json"
    input_path.write_text('{"tampered": true}\n', encoding="utf-8")
    assert "planning_context.artifacts.hash_mismatch:input" in (
        planner.verify_semantic_planning_chain(tmp_path)
    )


def _write_operator_catalog(path: Path, operators: dict) -> Path:
    path.write_text(json.dumps({"operators": operators}), encoding="utf-8")
    return path


def test_apo_retains_every_candidate_or_typed_exclusion(tmp_path: Path) -> None:
    catalog_path = _write_operator_catalog(
        tmp_path / "operators.json",
        {
            "ready-builder": {
                "enabled": True,
                "available": True,
                "health_status": "ok",
                "roles": ["builder"],
                "backend": "command",
            },
            "disabled-builder": {
                "enabled": False,
                "available": True,
                "health_status": "ok",
                "roles": ["builder"],
            },
            "wrong-role": {
                "enabled": True,
                "available": True,
                "health_status": "ok",
                "roles": ["planner"],
            },
            "forbidden-builder": {
                "enabled": True,
                "available": True,
                "health_status": "ok",
                "roles": ["builder"],
            },
        },
    )

    result = apo.enumerate_physical_candidate_decisions(
        role="builder",
        operator_constraints={"forbidden": ["forbidden-builder"]},
        operators_path=catalog_path,
    )

    assert [row["operator_id"] for row in result["candidates"]] == ["ready-builder"]
    excluded = {row["operator_id"]: row["reasons"] for row in result["excluded"]}
    assert set(excluded) == {"disabled-builder", "wrong-role", "forbidden-builder"}
    assert "STATIC_DISABLED" in excluded["disabled-builder"]
    assert "ROLE_MISMATCH" in excluded["wrong-role"]
    assert "CAPSULE_FORBIDDEN" in excluded["forbidden-builder"]


def test_static_candidate_list_excludes_unrelated_role_only_workers(
    tmp_path: Path,
) -> None:
    catalog_path = _write_operator_catalog(
        tmp_path / "operators.json",
        {
            "research-worker": {
                "enabled": True,
                "available": True,
                "health_status": "ok",
                "roles": ["builder"],
                "task_classes": ["research", "evidence"],
            },
            "unrelated-command-worker": {
                "enabled": True,
                "available": True,
                "health_status": "ok",
                "roles": ["builder"],
            },
        },
    )

    decisions = apo.enumerate_physical_candidate_decisions(
        role="builder",
        task_type="research",
        require_task_class_fit=True,
        operators_path=catalog_path,
    )

    assert [row["operator_id"] for row in decisions["candidates"]] == [
        "research-worker"
    ]
    assert decisions["excluded"] == [
        {
            "operator_id": "unrelated-command-worker",
            "reasons": ["TASK_CLASS_UNDECLARED"],
            "observed": {
                "roles": ["builder"],
                "enabled": True,
                "available": True,
                "deprecated": False,
                "health_status": "ok",
            },
        }
    ]


def test_whole_request_physical_plan_fails_before_runtime_when_no_candidate(tmp_path: Path) -> None:
    catalog_path = _write_operator_catalog(
        tmp_path / "operators.json",
        {
            "planner-only": {
                "enabled": True,
                "available": True,
                "health_status": "ok",
                "roles": ["planner"],
            }
        },
    )
    capsule_plan = {
        "schema_version": "solar.capsule_plan_ir.v1",
        "sprint_id": "sprint-test",
        "nodes": [
            {
                "node_id": "implement",
                "logical_operator": "ImplementationWorker",
                "capability_capsule_id": "cap.requirement-compiler-implementation",
                "dispatch_task_type": "implementation",
                "artifact_types": {},
                "effect_union": {},
                "proof_obligations": [],
                "stages": [
                    {
                        "stage_id": "implement:capability",
                        "stage_kind": "capability",
                        "dispatch_mode": "execute",
                        "role": "builder",
                        "task_type": "implementation",
                        "operator_constraints": {},
                    }
                ],
            }
        ],
    }

    physical = apo.build_physical_plan_ir(capsule_plan, operators_path=catalog_path)

    assert physical["verdict"] == "fail"
    assert physical["unsatisfiable_nodes"][0]["code"] == "UNSATISFIABLE_BINDING"
    assert physical["nodes"][0]["execution_candidates"] == []
    assert physical["nodes"][0]["execution_excluded"][0]["operator_id"] == "planner-only"


def test_measured_experiment_capsule_freezes_native_run_worker_before_runtime() -> None:
    graph = {
        "sprint_id": "sprint-measured-experiment",
        "dag_variant": "generated",
        "nodes": [
            {
                "id": "run_experiment",
                "logical_operator": "ScientificExperimentRunner",
                "capability_capsule_id": "cap.research-experiment-run",
                "dispatch_task_type": "experiment-run",
                "allowed_operators": {"role": "builder"},
                "semantic_artifact_contract": {
                    "consumes": [
                        "schema:schemas/evidence/experiment_plan.v1.schema.json",
                        "schema:schemas/evidence/experiment_approval.v1.schema.json",
                    ],
                    "produces": [
                        "schema:schemas/evidence/experiment_result.v1.schema.json"
                    ],
                },
            }
        ],
    }

    execution = apo.compile_whole_request_execution_plan(graph)

    assert execution["verdict"] == "pass"
    physical = execution["physical_plan"]["nodes"][0]
    assert physical["selected_operator_id"] == "experiment_run_worker"
    assert [row["operator_id"] for row in physical["execution_candidates"]] == [
        "experiment_run_worker"
    ]
    excluded = {
        row["operator_id"]: row["reasons"] for row in physical["execution_excluded"]
    }
    assert "EXECUTION_TRUST_UNSATISFIED" in excluded[
        "autosci-experiment-run-worker"
    ]
    assert "EXECUTION_TRUST_UNSATISFIED" in excluded[
        "autosci-exec-experiment-run-worker"
    ]


def test_single_claim_capsule_freezes_native_selector_before_runtime() -> None:
    graph = {
        "sprint_id": "sprint-single-claim-selection",
        "dag_variant": "generated",
        "nodes": [
            {
                "id": "select_one_testable_claim",
                "logical_operator": "ScientificClaimExtractor",
                "capability_capsule_id": "cap.research-single-testable-claim-extract",
                "dispatch_task_type": "claim-extraction",
                "allowed_operators": {"role": "builder"},
                "semantic_artifact_contract": {
                    "consumes": [
                        "schema:schemas/evidence/research_paper.v1.schema.json"
                    ],
                    "produces": [
                        "schema:schemas/evidence/research_claims.v1.schema.json"
                    ],
                },
            }
        ],
    }

    execution = apo.compile_whole_request_execution_plan(graph)

    assert execution["verdict"] == "pass"
    physical = execution["physical_plan"]["nodes"][0]
    assert physical["selected_operator_id"] == "claim_select_one_worker"
    assert [row["operator_id"] for row in physical["execution_candidates"]] == [
        "claim_select_one_worker"
    ]


def test_whole_request_capsule_plan_fails_before_runtime_when_capsule_is_unknown() -> None:
    graph = {
        "sprint_id": "sprint-capsule-unsat",
        "dag_variant": "generated",
        "nodes": [
            {
                "id": "implement",
                "logical_operator": "ImplementationWorker",
                "capability_capsule_id": "cap.not-registered",
                "dispatch_task_type": "implementation",
                "allowed_operators": {"role": "builder"},
            }
        ],
    }

    execution = apo.compile_whole_request_execution_plan(graph)

    assert execution["verdict"] == "fail"
    assert execution["capsule_plan"]["verdict"] == "fail"
    assert execution["capsule_plan"]["unsatisfiable_nodes"] == [
        {
            "node_id": "implement",
            "code": "UNSATISFIABLE_CAPSULE",
            "message": "The declared capability capsule is not registered.",
            "declared_capsule_id": "cap.not-registered",
        }
    ]
    assert execution["physical_plan"]["nodes"] == []
    assert execution["physical_plan"]["unsatisfiable_nodes"][0]["code"] == (
        "UNSATISFIABLE_CAPSULE"
    )


def test_generated_graph_uses_admitted_semantic_capsule_selection() -> None:
    plan_ir = {
        "plan_ir_id": "plan-test-runner",
        "nodes": [
            {
                "node_id": "run_performance_regression_tests",
                "logical_operator": "TestRunner",
                "objective": "Run focused performance regression tests for the Python service.",
                "depends_on": [],
                "consumes": ["requirement_ir.v1"],
                "produces": [],
                "requirement_ids": ["REQ-002"],
                "operator_requirements": {},
                "gate_requirement": "tests_exit_zero",
            }
        ],
    }

    selection = {
        "nodes": [
            {
                "node_id": "run_performance_regression_tests",
                "selected_capsule_id": "cap.requirement-compiler-verification",
                "dispatch_task_type": "tests",
                "fallback_capsule_ids": [],
                "rationale": "The admitted capsule runs and evaluates focused tests.",
            }
        ]
    }
    graph = planner._generated_task_graph_proposal(
        _requirement_ir(), plan_ir, selection, sprint_id="sprint-logical-capsule"
    )

    node = graph["nodes"][0]
    assert node["capability_capsule_id"] == "cap.requirement-compiler-verification"
    assert node["approved_fallback_capsule_ids"] == []


def test_planning_catalog_freezes_canonical_capsule_contracts() -> None:
    catalog = _catalog()
    retrieval = next(
        row for row in catalog["capsules"] if row["capsule_id"] == "cap.research-retrieval"
    )
    experiment = next(
        row for row in catalog["capsules"] if row["capsule_id"] == "cap.research-experiment-design"
    )
    experiment_run = next(
        row for row in catalog["capsules"] if row["capsule_id"] == "cap.research-experiment-run"
    )

    assert retrieval["consumes"] == ["artifact.research_question"]
    assert retrieval["produces"] == ["artifact.source_pack"]
    assert experiment["produces"] == [
        "schema:schemas/evidence/experiment_plan.v1.schema.json"
    ]
    assert experiment["contract"]["required_outputs"][0]["schema_ref"] == (
        "schemas/evidence/experiment_plan.v1.schema.json"
    )
    assert experiment_run["implementation"]["trust_class"] == "measured_execution"
    assert experiment_run["operator_compatibility"]["selectable_preferred"] == [
        "experiment_run_worker"
    ]
    assert retrieval["manifest_sha256"]


def test_composition_catalog_admits_native_worker_for_measured_execution() -> None:
    node = {
        "node_id": "run_real_experiment",
        "logical_operator": "ScientificExperimentRunner",
        "objective": "Execute the approved experiment and retain measured results.",
        "depends_on": [],
        "consumes": [
            "schema:schemas/evidence/experiment_plan.v1.schema.json",
            "schema:schemas/evidence/experiment_approval.v1.schema.json",
        ],
        "produces": [
            {
                "artifact_type": "schema:schemas/evidence/experiment_result.v1.schema.json",
                "verifier_ids": ["check.scientific.experiment_result.v1"],
                "materialization": {"kind": "file", "path": "experiment_result.json"},
            }
        ],
        "requirement_ids": ["REQ-001"],
        "operator_requirements": {
            "capabilities": ["experiment_execution"],
            "network": "optional",
            "minimum_context_tokens": 0,
            "effects": ["read", "write", "execute", "network"],
            "execution_trust": "measured_execution",
        },
        "gate_requirement": "measured_experiment_result_review",
    }

    row = planner._node_composition_row(
        node,
        _catalog(),
        artifact_registry=composition.load_artifact_type_registry(),
        conversion_registry=composition.load_conversion_registry(),
    )

    assert row["execution_trust"] == "measured_execution"
    assert row["status"] == "candidates_available"
    assert row["admitted_candidate_ids"]
    selected = row["search"]["candidates"][0]
    assert [step["capsule_id"] for step in selected["steps"]] == [
        "cap.research-experiment-run"
    ]


def test_output_policy_prevents_model_from_weakening_measured_result_trust() -> None:
    node = {
        "node_id": "run_real_experiment",
        "logical_operator": "ScientificExperimentRunner",
        "objective": "Execute the approved experiment and retain measured results.",
        "depends_on": [],
        "consumes": [
            "schema:schemas/evidence/experiment_plan.v1.schema.json",
            "schema:schemas/evidence/experiment_approval.v1.schema.json",
        ],
        "produces": [
            {
                "artifact_type": "schema:schemas/evidence/experiment_result.v1.schema.json",
                "verifier_ids": ["check.scientific.experiment_result.v1"],
                "materialization": {"kind": "file", "path": "experiment_result.json"},
            }
        ],
        "requirement_ids": ["REQ-001"],
        "operator_requirements": {
            "capabilities": ["experiment_execution"],
            "network": "optional",
            "minimum_context_tokens": 0,
            "effects": ["read", "write", "execute", "network"],
            "execution_trust": "any",
        },
        "gate_requirement": "measured_experiment_result_review",
    }

    row = planner._node_composition_row(
        node,
        _catalog(),
        artifact_registry=composition.load_artifact_type_registry(),
        conversion_registry=composition.load_conversion_registry(),
    )

    assert row["declared_execution_trust"] == "any"
    assert row["minimum_execution_trust"] == "measured_execution"
    assert row["execution_trust"] == "measured_execution"
    assert row["status"] == "invalid_request"
    assert row["admitted_candidate_ids"] == []
    assert row["errors"] == [
        {
            "code": "EXECUTION_TRUST_BELOW_OUTPUT_MINIMUM",
            "message": (
                "node run_real_experiment declares execution_trust=any, "
                "but its output contract requires at least measured_execution"
            ),
        }
    ]


def test_composition_may_retain_outputs_from_multiple_ordered_steps() -> None:
    request = "schema:request-envelope.schema.json"
    result = "schema:schemas/evidence/experiment_result.v1.schema.json"
    status = "schema:schemas/evidence/experiment_status.v1.schema.json"
    catalog = {
        "capsules": [
            {
                "capsule_id": "cap.execute",
                "consumes": [request],
                "produces": [result],
                "effects": {"execute": ["run"]},
                "verification": {"self_checks": ["check.result"]},
                "implementation": {"declared": True, "trust_class": "measured_execution"},
                "operator_compatibility": {"selectable_preferred": ["runner"]},
            },
            {
                "capsule_id": "cap.monitor",
                "consumes": [result],
                "produces": [status],
                "effects": {"execute": ["monitor"]},
                "verification": {"self_checks": ["check.status"]},
                "implementation": {"declared": True, "trust_class": "evidence_transform"},
                "operator_compatibility": {"selectable_preferred": ["monitor"]},
            },
        ]
    }
    node = {
        "node_id": "execute_and_monitor",
        "logical_operator": "ScientificExperimentRunner",
        "objective": "Execute and monitor one bounded experiment.",
        "depends_on": [],
        "consumes": [request],
        "produces": [
            {"artifact_type": result},
            {"artifact_type": status},
        ],
        "requirement_ids": ["REQ-EXECUTE"],
        "operator_requirements": {
            "effects": ["execute"],
            "network": "forbidden",
            "execution_trust": "measured_execution",
        },
    }

    row = planner._node_composition_row(
        node,
        catalog,
        artifact_registry=composition.load_artifact_type_registry(),
        conversion_registry={
            "schema_version": "solar.artifact_conversion_registry.v1",
            "conversions": [],
        },
    )

    assert row["status"] == "candidates_available"
    assert row["candidate_exclusions"] == []
    trust_policy = row["search"]["execution_trust_policy"]["required_by_output"]
    assert trust_policy == [
        {
            "artifact_type": result,
            "allowed_trust_classes": ["measured_execution"],
        }
    ]
    candidate = row["search"]["candidates"][0]
    assert [step["capsule_id"] for step in candidate["steps"]] == [
        "cap.execute",
        "cap.monitor",
    ]


def _expanded_poc_repair() -> tuple[dict, dict]:
    claims = "type.claims"
    plan = "type.plan"
    result = "type.result"
    verdict = "type.verdict"
    report = "type.report"
    previous = {
        "nodes": [
            {
                "node_id": "research",
                "logical_operator": "ResearchSynthesizer",
                "depends_on": [],
                "requirement_ids": ["REQ-RESEARCH"],
                "produces": [{"artifact_type": claims}],
            },
            {
                "node_id": "poc_execution",
                "logical_operator": "ScientificExperimentRunner",
                "depends_on": ["research"],
                "consumes": [claims],
                "produces": [
                    {"artifact_type": result},
                    {"artifact_type": verdict},
                ],
                "requirement_ids": ["REQ-POC"],
                "operator_requirements": {"execution_trust": "measured_execution"},
            },
            {
                "node_id": "final_report",
                "logical_operator": "ScientificReportDrafter",
                "depends_on": ["research", "poc_execution"],
                "consumes": [claims, result, verdict],
                "produces": [{"artifact_type": report}],
                "requirement_ids": ["REQ-REPORT"],
            },
        ]
    }
    repaired = {
        "nodes": [
            copy.deepcopy(previous["nodes"][0]),
            {
                "node_id": "design",
                "logical_operator": "ScientificExperimentDesigner",
                "depends_on": ["research"],
                "consumes": [claims],
                "produces": [{"artifact_type": plan}],
                "requirement_ids": [],
            },
            {
                "node_id": "execute",
                "logical_operator": "ScientificExperimentRunner",
                "depends_on": ["research", "design"],
                "consumes": [claims, plan],
                "produces": [{"artifact_type": result}],
                "requirement_ids": ["REQ-POC"],
                "operator_requirements": {"execution_trust": "measured_execution"},
            },
            {
                "node_id": "verify",
                "logical_operator": "ScientificClaimVerifier",
                "depends_on": ["research", "execute"],
                "consumes": [claims, result],
                "produces": [{"artifact_type": verdict}],
                "requirement_ids": [],
            },
            {
                "node_id": "final_report",
                "logical_operator": "ScientificReportDrafter",
                "depends_on": ["research", "execute", "verify"],
                "consumes": [claims, result, verdict],
                "produces": [{"artifact_type": report}],
                "requirement_ids": ["REQ-REPORT"],
            },
        ]
    }
    return previous, repaired


def test_plan_repair_may_expand_one_broad_node_into_typed_subgraph() -> None:
    previous, repaired = _expanded_poc_repair()

    assert planner._repair_preservation_errors(previous, repaired) == []


def test_plan_repair_expansion_must_preserve_requirement_and_execution_trust() -> None:
    previous, repaired = _expanded_poc_repair()
    execute = next(row for row in repaired["nodes"] if row["node_id"] == "execute")
    execute["requirement_ids"] = []
    execute["operator_requirements"]["execution_trust"] = "evidence_transform"

    errors = planner._repair_preservation_errors(previous, repaired)

    assert [row["code"] for row in errors] == ["REPAIR_DEPENDENCY_WEAKENED"]


def test_planning_catalog_self_hash_detects_capsule_contract_tampering(tmp_path: Path) -> None:
    planner.run_semantic_planning_pipeline(
        _requirement_ir(), tmp_path, ScriptedModel(), ScriptedModel(), catalog=_catalog()
    )
    path = tmp_path / "planning_catalog_snapshot.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["capsules"][0]["description"] = "Tampered after planning."
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert "planning_catalog_snapshot.catalog_sha256.hash_mismatch" in (
        planner.verify_semantic_planning_chain(tmp_path)
    )


def test_candidate_filter_retains_multiple_exactly_compatible_capsules() -> None:
    requirement_ir = _requirement_ir()
    plan_ir = _wrapped_plan(requirement_ir, _decision(requirement_ir))
    catalog = _catalog()
    primary = next(
        copy.deepcopy(row)
        for row in catalog["capsules"]
        if row["capsule_id"] == "cap.requirement-compiler-implementation"
    )
    primary["capsule_id"] = "cap.test-equivalent-implementation"
    catalog["capsules"].append(primary)
    context = _planning_context(requirement_ir)

    candidates = planner.build_capsule_candidate_catalog(
        requirement_ir, context, plan_ir, catalog
    )

    assert candidates["verdict"] == "candidates_available"
    assert candidates["nodes"][0]["eligible_candidate_ids"] == [
        "cap.requirement-compiler-implementation",
        "cap.test-equivalent-implementation",
    ]


def test_r12_document_authoring_admits_audit_not_patch_implementation() -> None:
    requirement_ir = _requirement_ir()
    plan_ir = _wrapped_plan(requirement_ir, _decision(requirement_ir))
    plan_ir["nodes"] = [
        {
            "node_id": "inspect-and-document",
            "logical_operator": "ArtifactCurator",
            "objective": (
                "Inspect README.md and package.json without modifying them, then "
                "create ARCHITECTURE_SUMMARY.md."
            ),
            "depends_on": [],
            "consumes": ["artifact.requirement_ir", "artifact.task_graph_node"],
            "produces": [
                {
                    "artifact_type": "artifact.handoff_md",
                    "verifier_ids": ["check.artifact_outcome_completeness.v1"],
                    "materialization": {
                        "kind": "file",
                        "path": "ARCHITECTURE_SUMMARY.md",
                        "route": "workspace_publish",
                    },
                }
            ],
            "requirement_ids": ["REQ-001"],
            "operator_requirements": {
                "capabilities": ["research_synthesis"],
                "network": "forbidden",
                "execution_trust": "any",
                "minimum_context_tokens": 2000,
                "effects": ["read", "write", "execute"],
            },
            "gate_requirement": "Create only the declared documentation artifact.",
            "workspace_reads": [
                {"kind": "file", "path": "README.md"},
                {"kind": "file", "path": "package.json"},
            ],
        },
        {
            "node_id": "verify-summary",
            "logical_operator": "Verifier",
            "objective": "Verify the declared summary artifact.",
            "depends_on": ["inspect-and-document"],
            "consumes": ["artifact.handoff_md", "artifact.requirement_ir"],
            "produces": [
                {
                    "artifact_type": "artifact.eval_md",
                    "verifier_ids": ["check.action_outcome_completeness.v1"],
                    "materialization": {
                        "kind": "file",
                        "path": "verification.md",
                        "route": "sprint_private",
                    },
                }
            ],
            "requirement_ids": ["REQ-002"],
            "operator_requirements": {
                "capabilities": ["test_execution"],
                "network": "forbidden",
                "execution_trust": "any",
                "minimum_context_tokens": 1000,
                "effects": ["read", "write", "execute"],
            },
            "gate_requirement": "The summary must exist before verification.",
            "workspace_reads": [],
        },
    ]
    catalog = _catalog()
    context = _planning_context(requirement_ir)

    candidates = planner.build_capsule_candidate_catalog(
        requirement_ir, context, plan_ir, catalog
    )
    by_node = {row["node_id"]: row for row in candidates["nodes"]}
    document_row = by_node["inspect-and-document"]
    implementation_exclusion = next(
        row
        for row in document_row["exclusions"]
        if row["capsule_id"] == "cap.requirement-compiler-implementation"
    )

    assert document_row["eligible_candidate_ids"] == [
        "cap.requirement-compiler-audit"
    ]
    assert implementation_exclusion["reason_codes"] == [
        "MANDATORY_PROOF_CLASS_UNSATISFIABLE"
    ]
    assert implementation_exclusion["unsatisfied_proof_classes"] == ["patch_proof"]
    assert by_node["verify-summary"]["eligible_candidate_ids"] == [
        "cap.requirement-compiler-verification"
    ]
    compositions = planner.build_plan_composition_catalog(
        requirement_ir, context, plan_ir, catalog
    )
    compositions_by_node = {row["node_id"]: row for row in compositions["nodes"]}
    document_compositions = compositions_by_node["inspect-and-document"]
    admitted_document_steps = [
        [step["capsule_id"] for step in candidate["steps"]]
        for candidate in document_compositions["search"]["candidates"]
        if candidate["candidate_id"] in document_compositions["admitted_candidate_ids"]
    ]
    assert admitted_document_steps == [["cap.requirement-compiler-audit"]]
    verification_compositions = compositions_by_node["verify-summary"]
    assert any(
        [step["capsule_id"] for step in candidate["steps"]]
        == ["cap.requirement-compiler-verification"]
        and candidate["candidate_id"] in verification_compositions["admitted_candidate_ids"]
        for candidate in verification_compositions["search"]["candidates"]
    )
    assert all(
        "cap.requirement-compiler-implementation"
        not in [step["capsule_id"] for step in candidate["steps"]]
        for candidate in verification_compositions["search"]["candidates"]
        if candidate["candidate_id"] in verification_compositions["admitted_candidate_ids"]
    )

    # Defense in depth: selection validation recomputes proof compatibility;
    # it must not trust a stale or forged candidate list that re-admits the
    # patch capsule for this artifact-only PlanIR node.
    forged_candidates = copy.deepcopy(candidates)
    forged_document_row = next(
        row
        for row in forged_candidates["nodes"]
        if row["node_id"] == "inspect-and-document"
    )
    forged_document_row["eligible_candidate_ids"].append(
        "cap.requirement-compiler-implementation"
    )
    forged_document_row["eligible_candidate_ids"].sort()
    forged_document_row["exclusions"] = [
        row
        for row in forged_document_row["exclusions"]
        if row["capsule_id"] != "cap.requirement-compiler-implementation"
    ]
    forged_by_node = {
        row["node_id"]: row for row in forged_candidates["nodes"]
    }
    forged_selection = {
        "schema_version": "solar.capsule_selection.v1",
        "artifact_role": "runtime_artifact",
        "selection_id": "selection-forced-patch-for-document",
        "generation": 0,
        "planning_context_ref": {"sha256": sha256_payload(context)},
        "requirement_ir_ref": {"sha256": sha256_payload(requirement_ir)},
        "plan_ir_ref": {"sha256": sha256_payload(plan_ir)},
        "candidate_catalog_ref": {"sha256": sha256_payload(forged_candidates)},
        "producer": {"method": "model", "provider": "test", "model": "test-model"},
        "nodes": [
            {
                "node_id": "inspect-and-document",
                "selected_capsule_id": "cap.requirement-compiler-implementation",
                "dispatch_task_type": "implementation",
                "fallback_capsule_ids": [],
                "rationale": "Forced stale selection for the regression.",
                "requirement_ids": forged_by_node["inspect-and-document"]["requirement_ids"],
                "eligible_candidate_ids": forged_by_node["inspect-and-document"]["eligible_candidate_ids"],
                "candidate_exclusions": forged_by_node["inspect-and-document"]["exclusions"],
            },
            {
                "node_id": "verify-summary",
                "selected_capsule_id": "cap.requirement-compiler-verification",
                "dispatch_task_type": "evidence",
                "fallback_capsule_ids": [],
                "rationale": "Retain the registered independent verifier.",
                "requirement_ids": forged_by_node["verify-summary"]["requirement_ids"],
                "eligible_candidate_ids": forged_by_node["verify-summary"]["eligible_candidate_ids"],
                "candidate_exclusions": forged_by_node["verify-summary"]["exclusions"],
            },
        ],
    }

    forced_validation = planner.validate_capsule_selection(
        requirement_ir,
        context,
        plan_ir,
        forged_candidates,
        catalog,
        forged_selection,
    )
    assert forced_validation["status"] == "fail"
    assert "CAPSULE_MANDATORY_PROOF_CLASS_UNSATISFIABLE" in {
        row["code"] for row in forced_validation["errors"]
    }


def test_plan_ir_v1_workspace_reads_admit_exact_files_not_directories() -> None:
    requirement_ir = _requirement_ir()
    decision = _decision(requirement_ir)
    plan_ir = _wrapped_plan(requirement_ir, decision)
    plan_ir["nodes"][0]["workspace_reads"] = [
        {"kind": "directory", "path": "docs"}
    ]

    validation = planner.validate_plan_ir(
        requirement_ir,
        decision,
        plan_ir,
        _catalog(),
    )

    assert "WORKSPACE_READ_INVALID" in {
        row["code"] for row in validation["errors"]
    }


def _r15_artifact_handoff_plan(requirement_ir: dict, decision: dict) -> dict:
    return _wrapped_plan(
        requirement_ir,
        decision,
        {
            "nodes": [
                {
                    "node_id": "author-summary",
                    "logical_operator": "ArtifactCurator",
                    "objective": "Author the requested architecture summary artifact.",
                    "depends_on": [],
                    "consumes": ["requirement_ir.v1"],
                    "produces": [
                        {
                            "artifact_type": "artifact.report",
                            "verifier_ids": ["check.patch.v1"],
                            "materialization": {
                                "kind": "file",
                                "path": "ARCHITECTURE_SUMMARY.md",
                                "route": "workspace_publish",
                            },
                        }
                    ],
                    "workspace_reads": [],
                    "requirement_ids": ["REQ-001"],
                    "operator_requirements": {
                        "capabilities": ["research_synthesis"],
                        "network": "forbidden",
                        "execution_trust": "any",
                        "minimum_context_tokens": 1000,
                        "effects": ["write"],
                    },
                    "gate_requirement": "Author the declared summary only.",
                },
                {
                    "node_id": "verify-summary",
                    "logical_operator": "Verifier",
                    "objective": "Verify the generated architecture summary artifact.",
                    "depends_on": ["author-summary"],
                    "consumes": ["requirement_ir.v1"],
                    "produces": [
                        {
                            "artifact_type": "artifact.verification",
                            "verifier_ids": ["check.tests.v1"],
                            "materialization": {
                                "kind": "file",
                                "path": "verification.json",
                                "route": "sprint_private",
                            },
                        }
                    ],
                    "workspace_reads": [
                        {"kind": "file", "path": "ARCHITECTURE_SUMMARY.md"}
                    ],
                    "requirement_ids": ["REQ-002"],
                    "operator_requirements": {
                        "capabilities": ["test_execution"],
                        "network": "forbidden",
                        "execution_trust": "any",
                        "minimum_context_tokens": 1000,
                        "effects": ["read", "write"],
                    },
                    "gate_requirement": "Verify the generated summary.",
                },
            ]
        },
    )


def _r15_workspace_authority(tmp_path: Path, *, files: tuple[str, ...] = ()) -> dict:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    for relative in files:
        path = workspace / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"source:{relative}\n", encoding="utf-8")
    return {"workspace_root": str(workspace.resolve())}


def test_r15_generated_artifact_cannot_be_redeclared_as_workspace_source(
    tmp_path: Path,
) -> None:
    requirement_ir = _requirement_ir()
    decision = _decision(requirement_ir, "exact_reuse")
    plan_ir = _r15_artifact_handoff_plan(requirement_ir, decision)

    validation = planner.validate_plan_ir(
        requirement_ir,
        decision,
        plan_ir,
        _catalog(),
        workspace_authority=_r15_workspace_authority(tmp_path),
    )
    defects = [
        row
        for row in validation["errors"]
        if row["code"] == "WORKSPACE_READ_SOURCE_MISSING_USE_ARTIFACT"
    ]

    assert len(defects) == 1
    assert defects[0]["repairable"] is True
    assert defects[0]["path"] == "nodes.1.workspace_reads.0"
    assert defects[0]["producer_node_ids"] == ["author-summary"]
    assert defects[0]["required_artifact_types"] == ["artifact.report"]
    assert defects[0]["required_consumes"] == ["artifact.report"]
    assert "depends_on" in defects[0]["message"]
    assert "consumes" in defects[0]["message"]
    assert "remove this workspace_read" in defects[0]["message"]


def test_r15_generation_zero_bundles_handoff_and_other_plan_defects(tmp_path: Path) -> None:
    requirement_ir = _requirement_ir()
    decision = _decision(requirement_ir, "exact_reuse")
    plan_ir = _r15_artifact_handoff_plan(requirement_ir, decision)
    plan_ir["nodes"][1]["produces"].append(
        {
            "artifact_type": "artifact.report",
            "verifier_ids": ["check.tests.v1"],
            "materialization": {
                "kind": "file",
                "path": "duplicate-report.md",
                "route": "sprint_private",
            },
        }
    )

    validation = planner.validate_plan_ir(
        requirement_ir,
        decision,
        plan_ir,
        _catalog(),
        workspace_authority=_r15_workspace_authority(tmp_path),
    )
    codes = {row["code"] for row in validation["errors"]}

    assert plan_ir["generation"] == 0
    assert {
        "WORKSPACE_READ_SOURCE_MISSING_USE_ARTIFACT",
        "ARTIFACT_PRODUCER_DUPLICATE",
    } <= codes


def test_r15_one_repair_receives_missing_source_and_second_defect_together(
    tmp_path: Path,
) -> None:
    requirement_ir = _requirement_ir()
    decision = _decision(requirement_ir)
    generation_zero = _r15_artifact_handoff_plan(requirement_ir, decision)["nodes"]
    generation_zero[1]["produces"].append(
        {
            "artifact_type": "artifact.report",
            "verifier_ids": ["check.tests.v1"],
            "materialization": {
                "kind": "file",
                "path": "duplicate-report.md",
                "route": "sprint_private",
            },
        }
    )
    planner_model = ScriptedModel(
        plan_bodies=[{"nodes": generation_zero}, _plan_body()]
    )
    authority = _r15_workspace_authority(tmp_path / "authority")

    result = planner.run_semantic_planning_pipeline(
        requirement_ir,
        tmp_path / "run",
        planner_model,
        ScriptedModel(),
        catalog=_catalog(),
        upstream_artifacts={"workspace_authority": authority},
    )

    plan_prompts = [
        json.loads(prompt)
        for call, prompt in zip(planner_model.calls, planner_model.prompts)
        if call == planner.PLAN_BODY_SCHEMA.name
    ]
    assert len(plan_prompts) == 2
    assert {
        "WORKSPACE_READ_SOURCE_MISSING_USE_ARTIFACT",
        "ARTIFACT_PRODUCER_DUPLICATE",
    } <= {row["code"] for row in plan_prompts[1]["defects"]}
    repair_record = json.loads(
        (tmp_path / "run" / "repair_record.json").read_text(encoding="utf-8")
    )
    assert {
        "WORKSPACE_READ_SOURCE_MISSING_USE_ARTIFACT",
        "ARTIFACT_PRODUCER_DUPLICATE",
    } <= {row["code"] for row in repair_record["defects"]}
    assert result["plan_ir"]["generation"] == 1
    assert result["plan_validation"]["status"] == "pass"


def test_r15_corrected_artifact_handoff_and_source_read_validate(tmp_path: Path) -> None:
    requirement_ir = _requirement_ir()
    decision = _decision(requirement_ir, "exact_reuse")
    plan_ir = _r15_artifact_handoff_plan(requirement_ir, decision)
    verifier = plan_ir["nodes"][1]
    verifier["consumes"].append("artifact.report")
    verifier["workspace_reads"] = [{"kind": "file", "path": "package.json"}]

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    package_path = workspace / "package.json"
    package_path.write_text('{"name":"fixture"}\n', encoding="utf-8")
    authority_path = tmp_path / "workspace_authority.json"
    authority = {
        "schema_version": "solar.workspace_authority.v1",
        "artifact_role": "controller_frozen_authority",
        "authority_id": "workspace-authority-r15-corrected",
        "path": str(authority_path.resolve()),
        "sprint_id": "sprint-r15-corrected",
        "workspace_root": str(workspace.resolve()),
    }
    authority_path.write_text(json.dumps(authority), encoding="utf-8")
    validation = planner.validate_plan_ir(
        requirement_ir,
        decision,
        plan_ir,
        _catalog(),
        workspace_authority=authority,
    )

    assert validation["status"] == "pass"
    assert validation["errors"] == []
    component = planner.run_elastic_planning_request(
        _requirement_ir(),
        tmp_path / "component",
        ScriptedModel(),
        ScriptedModel(),
        sprint_id="sprint-r15-template",
        catalog=_catalog(),
    )["execution"]
    capsule_template = component["capsule_plan"]["nodes"][0]
    physical_template = component["physical_plan"]["nodes"][0]
    evaluation_template = component["evaluation_plan"]["nodes"][0]
    selection = {
        "nodes": [
            {
                "node_id": row["node_id"],
                "selected_capsule_id": capsule_template["capability_capsule_id"],
                "dispatch_task_type": capsule_template["dispatch_task_type"],
                "fallback_capsule_ids": [],
                "rationale": "Reuse an admitted execution template for scheduler serialization.",
            }
            for row in plan_ir["nodes"]
        ]
    }
    task_graph = planner._generated_task_graph_proposal(
        requirement_ir,
        plan_ir,
        selection,
        sprint_id="sprint-r15-corrected",
    )

    def projected_rows(template: dict) -> list[dict]:
        rows = []
        for plan_node in plan_ir["nodes"]:
            row = copy.deepcopy(template)
            row["node_id"] = plan_node["node_id"]
            row["logical_operator"] = plan_node["logical_operator"]
            row["requirement_ids"] = copy.deepcopy(plan_node["requirement_ids"])
            rows.append(row)
        return rows

    capsule_plan = {**component["capsule_plan"], "nodes": projected_rows(capsule_template)}
    physical_plan = {**component["physical_plan"], "nodes": projected_rows(physical_template)}
    evaluation_plan = {
        **component["evaluation_plan"],
        "nodes": projected_rows(evaluation_template),
    }
    scheduler_input = planner.compile_scheduler_input(
        task_graph,
        capsule_plan,
        physical_plan,
        evaluation_plan,
        sprint_id="sprint-r15-corrected",
        workspace_authority=authority,
    )
    scheduler_nodes = {
        row["id"]: row for row in scheduler_input["graph"]["nodes"]
    }
    assert "artifact.report" in scheduler_nodes["verify-summary"]["artifact_contract"][
        "consumes"
    ]
    assert scheduler_nodes["verify-summary"]["workspace_reads"] == [
        {
            "kind": "file",
            "relative_path": "package.json",
            "sha256": scheduler_input_runtime.file_sha256(package_path),
        }
    ]
    assert task_graph["nodes"][1]["read_scope"] == [
        "workspace/ARCHITECTURE_SUMMARY.md"
    ]
    scheduler_path = tmp_path / "scheduler_input.json"
    scheduler_path.write_text(json.dumps(scheduler_input), encoding="utf-8")
    runtime_graph_path = scheduler_input_runtime.prepare_runtime_graph(
        scheduler_path,
        tmp_path / "runtime",
    )
    runtime_graph = json.loads(runtime_graph_path.read_text(encoding="utf-8"))
    runtime_nodes = {row["id"]: row for row in runtime_graph["nodes"]}
    staged_report = runtime_nodes["author-summary"]["artifact_routes"]["produces"][
        "artifact.report"
    ]
    assert runtime_nodes["verify-summary"]["artifact_routes"]["consumes"][
        "artifact.report"
    ] == staged_report
    assert runtime_nodes["verify-summary"]["read_scope"] == [
        "requirement_ir.v1",
        staged_report,
        str(package_path.resolve()),
    ]


def test_non_ancestor_same_filename_is_not_inferred_as_artifact_handoff(tmp_path: Path) -> None:
    requirement_ir = _requirement_ir()
    decision = _decision(requirement_ir, "exact_reuse")
    plan_ir = _r15_artifact_handoff_plan(requirement_ir, decision)
    plan_ir["nodes"][1]["depends_on"] = []

    validation = planner.validate_plan_ir(
        requirement_ir,
        decision,
        plan_ir,
        _catalog(),
        workspace_authority=_r15_workspace_authority(tmp_path),
    )

    codes = {row["code"] for row in validation["errors"]}
    assert "WORKSPACE_READ_SOURCE_MISSING" in codes
    assert "WORKSPACE_READ_SOURCE_MISSING_USE_ARTIFACT" not in codes


def test_existing_source_file_wins_over_same_name_generated_outputs(tmp_path: Path) -> None:
    requirement_ir = _requirement_ir()
    decision = _decision(requirement_ir, "exact_reuse")
    plan_ir = _r15_artifact_handoff_plan(requirement_ir, decision)
    verifier = plan_ir["nodes"][1]
    verifier["consumes"].append("artifact.report")
    authority = _r15_workspace_authority(
        tmp_path,
        files=("ARCHITECTURE_SUMMARY.md",),
    )

    validation = planner.validate_plan_ir(
        requirement_ir,
        decision,
        plan_ir,
        _catalog(),
        workspace_authority=authority,
    )

    assert validation["status"] == "pass"
    assert not {
        "WORKSPACE_READ_SOURCE_MISSING",
        "WORKSPACE_READ_SOURCE_MISSING_USE_ARTIFACT",
    } & {
        row["code"] for row in validation["errors"]
    }


def test_same_node_may_read_existing_source_before_publishing_same_path(
    tmp_path: Path,
) -> None:
    requirement_ir = _requirement_ir()
    decision = _decision(requirement_ir, "exact_reuse")
    plan_ir = _r15_artifact_handoff_plan(requirement_ir, decision)
    author = plan_ir["nodes"][0]
    author["workspace_reads"] = [
        {"kind": "file", "path": "ARCHITECTURE_SUMMARY.md"}
    ]
    author["operator_requirements"]["effects"].append("read")
    verifier = plan_ir["nodes"][1]
    verifier["consumes"].append("artifact.report")
    verifier["workspace_reads"] = []
    authority = _r15_workspace_authority(
        tmp_path,
        files=("ARCHITECTURE_SUMMARY.md",),
    )

    validation = planner.validate_plan_ir(
        requirement_ir,
        decision,
        plan_ir,
        _catalog(),
        workspace_authority=authority,
    )

    assert validation["status"] == "pass"
    assert not {
        "WORKSPACE_READ_SOURCE_MISSING",
        "WORKSPACE_READ_SOURCE_MISSING_USE_ARTIFACT",
    } & {row["code"] for row in validation["errors"]}


def test_scheduler_workspace_source_freezing_wraps_missing_file_and_hashes_present_file(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    authority = {"workspace_root": str(workspace)}
    node = {
        "workspace_reads": [{"kind": "file", "path": "package.json"}]
    }

    try:
        planner._bound_workspace_reads(node, authority)
    except planner.ElasticPlannerError as error:
        assert str(error) == "WORKSPACE_READ_SOURCE_UNAVAILABLE:package.json"
    else:
        raise AssertionError("missing source workspace read escaped as valid")

    package_path = workspace / "package.json"
    package_path.write_text('{"name":"fixture"}\n', encoding="utf-8")
    frozen = planner._bound_workspace_reads(node, authority)
    assert frozen == [
        {
            "kind": "file",
            "relative_path": "package.json",
            "sha256": scheduler_input_runtime.file_sha256(package_path),
        }
    ]



def test_code_change_still_admits_patch_implementation() -> None:
    requirement_ir = _requirement_ir()
    plan_ir = _wrapped_plan(requirement_ir, _decision(requirement_ir))

    candidates = planner.build_capsule_candidate_catalog(
        requirement_ir, _planning_context(requirement_ir), plan_ir, _catalog()
    )

    assert candidates["nodes"][0]["eligible_candidate_ids"] == [
        "cap.requirement-compiler-implementation"
    ]


def test_candidate_filter_rejects_capsule_that_ignores_declared_node_input() -> None:
    requirement_ir = _requirement_ir()
    plan_ir = _wrapped_plan(requirement_ir, _decision(requirement_ir))
    plan_ir["nodes"][0]["consumes"].append("artifact.extra_context")
    catalog = _catalog()

    candidates = planner.build_capsule_candidate_catalog(
        requirement_ir, _planning_context(requirement_ir), plan_ir, catalog
    )
    exclusion = next(
        row
        for row in candidates["nodes"][0]["exclusions"]
        if row["capsule_id"] == "cap.requirement-compiler-implementation"
    )

    assert "DECLARED_NODE_INPUT_UNSUPPORTED" in exclusion["reason_codes"]
    assert exclusion["unsupported_node_inputs"] == ["artifact.extra_context"]
    assert "cap.requirement-compiler-implementation" not in (
        candidates["nodes"][0]["eligible_candidate_ids"]
    )


def test_candidate_filter_keeps_independent_verifier_separate_from_capsule_self_checks() -> None:
    requirement_ir = _requirement_ir()
    plan_ir = _wrapped_plan(requirement_ir, _decision(requirement_ir))
    catalog = _catalog()
    capsule = next(
        row
        for row in catalog["capsules"]
        if row["capsule_id"] == "cap.requirement-compiler-implementation"
    )

    candidates = planner.build_capsule_candidate_catalog(
        requirement_ir, _planning_context(requirement_ir), plan_ir, catalog
    )

    assert "check.patch.v1" not in capsule["verification"]["self_checks"]
    assert "check.tests.v1" not in capsule["verification"]["self_checks"]
    assert "cap.requirement-compiler-implementation" in (
        candidates["nodes"][0]["eligible_candidate_ids"]
    )
    assert candidates["verdict"] == "candidates_available"


def test_candidate_filter_rejects_capsule_without_verification_contract() -> None:
    requirement_ir = _requirement_ir()
    plan_ir = _wrapped_plan(requirement_ir, _decision(requirement_ir))
    catalog = _catalog()
    capsule = next(
        row
        for row in catalog["capsules"]
        if row["capsule_id"] == "cap.requirement-compiler-implementation"
    )
    capsule["verification"] = {
        "self_checks": [],
        "pass_conditions": [],
        "external_required": False,
    }

    candidates = planner.build_capsule_candidate_catalog(
        requirement_ir, _planning_context(requirement_ir), plan_ir, catalog
    )
    exclusion = next(
        row
        for row in candidates["nodes"][0]["exclusions"]
        if row["capsule_id"] == "cap.requirement-compiler-implementation"
    )

    assert "VERIFICATION_CONTRACT_MISSING" in exclusion["reason_codes"]
    assert "cap.requirement-compiler-implementation" not in (
        candidates["nodes"][0]["eligible_candidate_ids"]
    )
    assert candidates["verdict"] == "unsatisfiable"


def test_candidate_filter_fails_closed_when_no_capsule_has_exact_output() -> None:
    requirement_ir = _requirement_ir()
    plan_ir = _wrapped_plan(requirement_ir, _decision(requirement_ir))
    plan_ir["nodes"][0]["produces"][0]["artifact_type"] = "artifact.not_registered"
    catalog = _catalog()
    context = _planning_context(requirement_ir)

    candidates = planner.build_capsule_candidate_catalog(
        requirement_ir, context, plan_ir, catalog
    )
    validation = planner.validate_capsule_selection(
        requirement_ir, context, plan_ir, candidates, catalog, None
    )

    assert candidates["verdict"] == "unsatisfiable"
    assert validation["status"] == "fail"
    assert {row["code"] for row in validation["errors"]} == {
        "NO_COMPATIBLE_CAPSULE"
    }


def test_capsule_selection_rejects_model_choice_outside_frozen_candidates(tmp_path: Path) -> None:
    requirement_ir = _requirement_ir()
    context = _planning_context(requirement_ir)
    plan_ir = _wrapped_plan(requirement_ir, _decision(requirement_ir))
    catalog = _catalog()
    candidates = planner.build_capsule_candidate_catalog(
        requirement_ir, context, plan_ir, catalog
    )
    model = ScriptedModel(
        capsule_selections=[
            {
                "nodes": [
                    {
                        "node_id": "implement",
                        "selected_capsule_id": "cap.flashmlx-performance-debugger",
                        "fallback_capsule_ids": [],
                        "rationale": "Adversarial selection outside the eligible set.",
                    }
                ]
            }
        ]
    )
    selection = planner.compile_capsule_selection(
        requirement_ir,
        context,
        {"requirement_ir": requirement_ir},
        plan_ir,
        catalog,
        candidates,
        model,
        tmp_path,
    )
    validation = planner.validate_capsule_selection(
        requirement_ir, context, plan_ir, candidates, catalog, selection
    )

    assert validation["status"] == "fail"
    assert "CAPSULE_SELECTION_NOT_ELIGIBLE" in {
        row["code"] for row in validation["errors"]
    }


def test_capsule_fit_review_allows_only_one_bounded_selection_repair(tmp_path: Path) -> None:
    requirement_ir = _requirement_ir()
    semantic = planner.run_semantic_planning_pipeline(
        requirement_ir,
        tmp_path / "semantic",
        ScriptedModel(),
        ScriptedModel(),
        catalog=_catalog(),
    )
    selection_body = {
        "nodes": [
            {
                "node_id": "implement",
                "selected_capsule_id": "cap.requirement-compiler-implementation",
                "fallback_capsule_ids": [],
                "rationale": "The capsule performs scoped implementation and emits the required artifacts.",
            }
        ]
    }
    failed_review = {
        "nodes": [
            {"node_id": "implement", "status": "fail", "reason": "The rationale does not establish scope fit."}
        ],
        "errors": [
            {
                "code": "CAPSULE_SCOPE_FIT_UNPROVEN",
                "node_id": "implement",
                "message": "Explain why the capsule remains inside the accepted implementation scope.",
                "repairable": True,
            }
        ],
        "warnings": [],
    }
    planner_model = ScriptedModel(capsule_selections=[selection_body, selection_body])
    reviewer_model = ScriptedModel(capsule_fit_reviews=[failed_review])

    binding = planner.run_generated_capsule_binding(
        requirement_ir, semantic, tmp_path / "execution", planner_model, reviewer_model
    )

    assert binding["accepted"] is True
    assert binding["repair_attempted"] is True
    assert binding["selection"]["generation"] == 1
    assert planner_model.calls.count(planner.CAPSULE_SELECTION_BODY_SCHEMA.name) == 2


def test_fit_review_failure_without_error_row_becomes_typed_bounded_failure(
    tmp_path: Path,
) -> None:
    requirement_ir = _requirement_ir()
    semantic = planner.run_semantic_planning_pipeline(
        requirement_ir,
        tmp_path / "semantic",
        ScriptedModel(plan_bodies=[_composition_plan_body()]),
        ScriptedModel(),
        catalog=_catalog(),
    )
    failed_review = {
        "nodes": [
            {
                "node_id": "design_reproducibility_experiment",
                "status": "fail",
                "reason": "The chain omits an essential semantic operation.",
            }
        ],
        "errors": [],
        "warnings": [],
    }

    binding = planner.run_generated_composition_binding(
        requirement_ir,
        semantic,
        tmp_path / "execution",
        ScriptedModel(),
        ScriptedModel(composition_fit_reviews=[failed_review, failed_review]),
    )

    assert binding["accepted"] is False
    assert binding["repair_attempted"] is True
    assert binding["fit_review"]["status"] == "fail"
    assert binding["fit_review"]["errors"] == [
        {
            "code": "COMPOSITION_FIT_FAILURE_UNTYPED",
            "node_id": "design_reproducibility_experiment",
            "message": "The chain omits an essential semantic operation.",
            "repairable": True,
        }
    ]


def test_capsule_binding_validation_rejects_undeclared_generic_coercion() -> None:
    capsule_plan = {
        "sprint_id": "sprint-binding-gap",
        "nodes": [
            {
                "node_id": "research",
                "stages": [
                    {
                        "stage_id": "research:adapter:1",
                        "stage_kind": "adapter",
                        "capability_capsule_id": "adapter.artifact-type-bridge",
                        "adapter_rule": {
                            "missing_required_inputs": ["artifact.discovery_query"],
                            "registry_match": {
                                "source_artifacts": [],
                                "target_artifacts": [],
                            },
                        },
                    }
                ],
            }
        ],
    }

    result = planner.validate_capsule_bindings(capsule_plan)

    assert result["status"] == "fail"
    assert result["errors"][0]["code"] == "UNREGISTERED_ADAPTER_COERCION"
    assert result["errors"][0]["target_artifacts"] == ["artifact.discovery_query"]


def test_capsule_binding_validation_accepts_registered_target_mapping() -> None:
    capsule_plan = {
        "sprint_id": "sprint-binding-declared",
        "nodes": [
            {
                "node_id": "design",
                "stages": [
                    {
                        "stage_id": "design:adapter:1",
                        "stage_kind": "adapter",
                        "capability_capsule_id": "adapter.requirement-ir-to-design-brief",
                        "adapter_rule": {
                            "missing_required_inputs": ["artifact.design_md"],
                            "registry_match": {
                                "source_artifacts": ["artifact.requirement_ir"],
                                "target_artifacts": ["artifact.design_md"],
                            },
                        },
                    }
                ],
            }
        ],
    }

    result = planner.validate_capsule_bindings(capsule_plan)

    assert result["status"] == "pass"
    assert result["errors"] == []


def test_plan_validator_registry_reads_canonical_cross_directory_capsules() -> None:
    registry = workflow_contract.load_capsule_registry(planner.CONFIG_DIR)

    assert "cap.requirement-compiler-implementation" in registry
    assert "cap.research-experiment-design" in registry
    assert Path(registry["cap.research-experiment-design"]["manifest_path"]).is_file()
    assert "cap.research-report-draft" in registry
    assert "cap.scientific-report-draft" in registry
    assert registry["cap.research-report-draft"]["task_type_in"] == [
        "report-writing"
    ]
    assert registry["cap.scientific-report-draft"]["task_type_in"] == [
        "report-drafting",
        "scientific-research",
    ]
    assert registry["cap.research-report-draft"]["manifest_path"] != registry[
        "cap.scientific-report-draft"
    ]["manifest_path"]


def test_patch_artifact_is_code_only_when_registry_capsule_declares_patch() -> None:
    node = {"write_scope": ["workspace/planning/implement/change.diff"]}

    assert workflow_contract.classify_node_kind(node, capsule_is_code=True) == "code"
    assert workflow_contract.classify_node_kind(node, capsule_is_code=False) == "artifact"


def test_generated_capsule_selection_freezes_one_runtime_authority(tmp_path: Path) -> None:
    requirement_ir = _requirement_ir()
    semantic = planner.run_semantic_planning_pipeline(
        requirement_ir,
        tmp_path / "semantic",
        ScriptedModel(),
        ScriptedModel(),
        catalog=_catalog(),
    )

    result = planner.compile_and_freeze_execution_bundle(
        requirement_ir,
        semantic,
        tmp_path / "execution",
        sprint_id="sprint-elastic-test",
        workspace_root="workspace",
        planner_model=ScriptedModel(),
        reviewer_model=ScriptedModel(),
    )

    assert result["capsule_selection"]["nodes"][0]["selected_capsule_id"] == (
        "cap.requirement-compiler-implementation"
    )
    assert result["capsule_selection_validation"]["status"] == "pass"
    assert result["capsule_fit_review"]["status"] == "pass"
    assert result["capsule_plan"]["nodes"][0]["approved_fallback_capsule_ids"] == []
    assert result["capsule_plan"]["nodes"][0]["capsule_selection_rationale"]
    assert result["physical_plan"]["verdict"] == "pass"
    assert result["evaluation_plan"]["verdict"] == "pass"
    assert result["evaluation_plan_validation"]["status"] == "pass"
    assert result["evaluation_check_registry"]["registry_id"] == (
        "solar-evaluation-checks-v1"
    )
    assert result["plan_acceptance"]["decision"] == "accepted"
    assert result["plan_acceptance"]["runtime_handoff_allowed"] is True
    assert result["run_contract_frozen"]["planning_authority"] == "frozen_execution_plan_v1"
    scheduler_input = result["scheduler_input"]
    assert scheduler_input["schema_version"] == "solar.scheduler_input.v1"
    assert scheduler_input["planning_authority"] == "frozen_execution_plan_v1"
    assert [row["id"] for row in scheduler_input["graph"]["nodes"]] == [
        row["id"] for row in result["task_graph_contract"]["nodes"]
    ]
    assert all(row["physical_candidates"] for row in scheduler_input["graph"]["nodes"])
    capsule_nodes = {
        row["node_id"]: row for row in result["capsule_plan"]["nodes"]
    }
    for row in scheduler_input["graph"]["nodes"]:
        assert row["capability_capsule_id"] == capsule_nodes[row["id"]][
            "capability_capsule_id"
        ]
        assert row["capability_capsule_id"] in row["capsule_binding"]["capsule_ids"]
    assert scheduler_input_runtime.validate(
        scheduler_input, require_runtime_authority=True
    ) == {"ok": True, "errors": []}
    assert "artifact.handoff_md" not in scheduler_input["graph"]["nodes"][0][
        "artifact_contract"
    ]["consumes"]
    assert planner._scheduler_attempt_budget(
        {"timeout_retry_policy": {"max_retries": 1}}
    ) == 2
    assert result["run_contract_frozen"]["scheduler_input_ref"]["sha256"] == (
        planner.sha256_payload(scheduler_input)
    )

    repeated_capsule_plan = copy.deepcopy(result["capsule_plan"])
    first_stage = copy.deepcopy(repeated_capsule_plan["nodes"][0]["stages"][0])
    repeated_capsule_plan["nodes"][0]["stages"].append(first_stage)
    normalized_scheduler_input = planner.compile_scheduler_input(
        result["task_graph_contract"],
        repeated_capsule_plan,
        result["physical_plan"],
        result["evaluation_plan"],
        sprint_id="sprint-elastic-test-deduplicated",
    )
    normalized_capsule_ids = normalized_scheduler_input["graph"]["nodes"][0][
        "capsule_binding"
    ]["capsule_ids"]
    assert normalized_capsule_ids == list(dict.fromkeys(normalized_capsule_ids))

    assert planner.verify_frozen_execution_chain(
        tmp_path / "semantic", tmp_path / "execution"
    ) == []

    scheduler_path = tmp_path / "execution" / "scheduler_input.json"
    tampered_scheduler = json.loads(scheduler_path.read_text(encoding="utf-8"))
    tampered_scheduler["graph"]["nodes"][0]["priority"] = 999
    scheduler_path.write_text(json.dumps(tampered_scheduler), encoding="utf-8")
    scheduler_errors = planner.verify_frozen_execution_chain(
        tmp_path / "semantic", tmp_path / "execution"
    )
    assert "scheduler_input.recomputed_mismatch" in scheduler_errors
    assert "frozen.scheduler_input_ref.hash_mismatch" in scheduler_errors
    scheduler_path.write_text(
        json.dumps(scheduler_input, indent=2) + "\n", encoding="utf-8"
    )

    evaluation_path = tmp_path / "execution" / "evaluation_plan.json"
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    evaluation["nodes"][0]["semantic_review"]["criteria"][0] = (
        "Tampered after evaluation admission."
    )
    evaluation_path.write_text(json.dumps(evaluation), encoding="utf-8")
    assert "frozen.evaluation_plan_ref.hash_mismatch" in planner.verify_frozen_execution_chain(
        tmp_path / "semantic", tmp_path / "execution"
    )
    evaluation_path.write_text(
        json.dumps(result["evaluation_plan"], indent=2) + "\n", encoding="utf-8"
    )

    selection_path = tmp_path / "execution" / "capsule_selection.json"
    tampered = json.loads(selection_path.read_text(encoding="utf-8"))
    tampered["nodes"][0]["rationale"] = "Tampered after admission."
    selection_path.write_text(json.dumps(tampered), encoding="utf-8")
    assert "frozen.capsule_selection_ref.hash_mismatch" in planner.verify_frozen_execution_chain(
        tmp_path / "semantic", tmp_path / "execution"
    )


def test_generated_multicapsule_node_expands_and_freezes_static_graph(
    tmp_path: Path,
) -> None:
    requirement_ir = _requirement_ir()
    semantic = planner.run_semantic_planning_pipeline(
        requirement_ir,
        tmp_path / "semantic",
        ScriptedModel(plan_bodies=[_composition_plan_body()]),
        ScriptedModel(),
        catalog=_catalog(),
    )

    assert semantic["plan_acceptance"]["decision"] == "accepted"
    proof = semantic["plan_composition_catalog"]["nodes"][0]
    assert proof["status"] == "candidates_available"
    first_candidate = next(
        row
        for row in proof["search"]["candidates"]
        if row["candidate_id"] == proof["admitted_candidate_ids"][0]
    )
    assert [row["capsule_id"] for row in first_candidate["steps"]] == [
        "cap.research-paper-ingest",
        "cap.research-claim-extract",
        "cap.research-claim-experiment-design",
    ]

    result = planner.compile_and_freeze_execution_bundle(
        requirement_ir,
        semantic,
        tmp_path / "execution",
        sprint_id="sprint-composed-planner",
        planner_model=ScriptedModel(),
        reviewer_model=ScriptedModel(),
    )

    assert result["binding_kind"] == "capsule_composition"
    assert result["composition_selection_validation"]["status"] == "pass"
    assert result["composition_fit_review"]["status"] == "pass"
    graph = result["task_graph_contract"]
    assert graph["dag_variant"] == "elastic_generated_composed"
    assert len(graph["nodes"]) == 3
    assert graph["nodes"][-1]["id"] == "design_reproducibility_experiment"
    assert graph["nodes"][-1]["requirement_ids"] == ["REQ-001", "REQ-002"]
    semantic_ids = set(graph["evaluation_policy"]["semantic_evaluation_node_ids"])
    assert 1 <= len(semantic_ids) <= graph["evaluation_policy"]["semantic_evaluation_budget"]
    assert all(
        node["max_repair_attempts"] == (1 if node["id"] in semantic_ids else 0)
        for node in graph["nodes"]
    )
    assert all(node["approved_physical_operator_ids"] for node in graph["nodes"])
    assert all(
        all(stage["stage_kind"] != "adapter" for stage in node["stages"])
        for node in result["capsule_plan"]["nodes"]
    )
    assert result["capsule_plan"]["nodes"][0]["artifact_types"][
        "required_inputs"
    ] == ["schema:request-envelope.schema.json"]
    assert len(result["evaluation_plan"]["nodes"]) == 3
    assert len(result["scheduler_input"]["graph"]["nodes"]) == 3
    assert all(
        row["capsule_binding"]["capsule_ids"]
        for row in result["scheduler_input"]["graph"]["nodes"]
    )
    assert result["plan_acceptance"]["decision"] == "accepted"
    assert result["run_contract_frozen"]["composition_selection_ref"]
    assert result["run_contract_frozen"]["capsule_selection_ref"] is None
    assert planner.verify_frozen_execution_chain(
        tmp_path / "semantic", tmp_path / "execution"
    ) == []
    selection_path = tmp_path / "execution" / "composition_selection.json"
    tampered = json.loads(selection_path.read_text(encoding="utf-8"))
    tampered["nodes"][0]["rationale"] = "Tampered after composition admission."
    selection_path.write_text(json.dumps(tampered), encoding="utf-8")
    assert "frozen.composition_selection_ref.hash_mismatch" in (
        planner.verify_frozen_execution_chain(
            tmp_path / "semantic", tmp_path / "execution"
        )
    )


def test_composition_expansion_places_requirement_on_step_that_emits_its_verifier() -> None:
    requirement_ir = {
        "requirement_ir_id": "requirement-ir-requirement-placement",
        "requirements": [
            {"requirement_id": "R-EVIDENCE", "check": "check.evidence.v1"},
            {"requirement_id": "R-METHOD", "check": "check.method.v1"},
        ]
    }
    plan_ir = {
        "nodes": [
            {
                "node_id": "prepare_evidence",
                "logical_operator": "ResearchSynthesizer",
                "objective": "Prepare evidence and method artifacts.",
                "depends_on": [],
                "consumes": ["schema:request-envelope.schema.json"],
                "produces": [
                    {
                        "artifact_type": "artifact.evidence",
                        "verifier_ids": ["check.evidence.v1"],
                        "materialization": {
                            "kind": "file",
                            "path": "evidence.json",
                            "route": "sprint_private",
                        },
                    },
                    {
                        "artifact_type": "artifact.method",
                        "verifier_ids": ["check.method.v1"],
                        "materialization": {
                            "kind": "file",
                            "path": "method.json",
                            "route": "sprint_private",
                        },
                    },
                ],
                "workspace_reads": [],
                "requirement_ids": ["R-EVIDENCE", "R-METHOD"],
                "operator_requirements": {"effects": ["read", "write"]},
                "gate_requirement": "",
            }
        ]
    }
    composition_catalog = {
        "nodes": [
            {
                "node_id": "prepare_evidence",
                "search": {
                    "candidates": [
                        {
                            "candidate_id": "composition-001",
                            "steps": [
                                {
                                    "capsule_id": "cap.evidence",
                                    "consumes": ["schema:request-envelope.schema.json"],
                                    "produces": ["artifact.evidence"],
                                },
                                {
                                    "capsule_id": "cap.method",
                                    "consumes": ["artifact.evidence"],
                                    "produces": ["artifact.method"],
                                },
                            ],
                        }
                    ]
                },
            }
        ]
    }
    selection = {
        "nodes": [
            {
                "node_id": "prepare_evidence",
                "selected_candidate_id": "composition-001",
                "rationale": "Use both typed steps.",
                "step_bindings": [
                    {"capsule_id": "cap.evidence", "dispatch_task_type": "extract"},
                    {"capsule_id": "cap.method", "dispatch_task_type": "method"},
                ],
            }
        ]
    }
    catalog = {
        "capsules": [
            {"capsule_id": "cap.evidence", "description": "Extract evidence."},
            {"capsule_id": "cap.method", "description": "Extract methods."},
        ]
    }

    graph = planner._generated_composition_task_graph_proposal(
        requirement_ir,
        plan_ir,
        composition_catalog,
        selection,
        catalog,
        sprint_id="sprint-requirement-placement",
    )

    assert graph["nodes"][0]["requirement_ids"] == ["R-EVIDENCE"]
    assert graph["nodes"][1]["requirement_ids"] == ["R-METHOD"]


def test_composition_catalog_rejects_chains_that_ignore_declared_node_inputs() -> None:
    requirement_ir = _requirement_ir()
    plan_body = _composition_plan_body()
    plan_body["nodes"][0]["consumes"].append("artifact.benchmark_log")
    plan_ir = _wrapped_plan(requirement_ir, _decision(requirement_ir), plan_body)
    catalog = _catalog()
    composition_catalog = planner.build_plan_composition_catalog(
        requirement_ir,
        _planning_context(requirement_ir),
        plan_ir,
        catalog,
    )
    proof = composition_catalog["nodes"][0]
    candidates = {
        row["candidate_id"]: row for row in proof["search"]["candidates"]
    }

    assert any(
        "DECLARED_NODE_INPUTS_UNUSED" in row["reason_codes"]
        for row in proof["candidate_exclusions"]
    )
    for candidate_id in proof["admitted_candidate_ids"]:
        consumed = {
            artifact_type
            for step in candidates[candidate_id]["steps"]
            for artifact_type in step["consumes"]
        }
        assert "artifact.benchmark_log" in consumed


def test_composition_selection_rejects_unproven_candidate_and_tampered_proof(
    tmp_path: Path,
) -> None:
    requirement_ir = _requirement_ir()
    semantic = planner.run_semantic_planning_pipeline(
        requirement_ir,
        tmp_path / "semantic",
        ScriptedModel(plan_bodies=[_composition_plan_body()]),
        ScriptedModel(),
        catalog=_catalog(),
    )
    composition_catalog = semantic["plan_composition_catalog"]
    invalid_model = ScriptedModel(
        composition_selections=[
            {
                "nodes": [
                    {
                        "node_id": "design_reproducibility_experiment",
                        "selected_candidate_id": "composition-invented",
                        "rationale": "Invented candidate must be rejected deterministically.",
                    }
                ]
            }
        ]
    )
    selection = planner.compile_composition_selection(
        requirement_ir,
        semantic["planning_context"],
        semantic["planning_inputs"],
        semantic["plan_ir"],
        semantic["planning_catalog_snapshot"],
        composition_catalog,
        invalid_model,
        tmp_path / "invalid-selection",
    )
    validation = planner.validate_composition_selection(
        requirement_ir,
        semantic["planning_context"],
        semantic["plan_ir"],
        semantic["planning_catalog_snapshot"],
        composition_catalog,
        selection,
        artifact_registry=semantic["artifact_type_registry"],
        conversion_registry=semantic["artifact_conversion_registry"],
    )
    assert validation["status"] == "fail"
    assert "COMPOSITION_SELECTION_NOT_ADMITTED" in {
        row["code"] for row in validation["errors"]
    }

    tampered = copy.deepcopy(composition_catalog)
    tampered["nodes"][0]["search"]["candidates"][0]["step_count"] += 1
    validation = planner.validate_composition_selection(
        requirement_ir,
        semantic["planning_context"],
        semantic["plan_ir"],
        semantic["planning_catalog_snapshot"],
        tampered,
        selection,
        artifact_registry=semantic["artifact_type_registry"],
        conversion_registry=semantic["artifact_conversion_registry"],
    )
    assert "COMPOSITION_PROOF_RECOMPUTE_MISMATCH" in {
        row["code"] for row in validation["errors"]
    }


def test_complete_component_returns_verified_frozen_or_direct_boundary(
    tmp_path: Path,
) -> None:
    frozen = planner.run_elastic_planning_request(
        _requirement_ir(),
        tmp_path / "workflow",
        ScriptedModel(),
        ScriptedModel(),
        sprint_id="sprint-component-workflow",
        catalog=_catalog(),
    )
    direct = planner.run_elastic_planning_request(
        _requirement_ir(),
        tmp_path / "direct",
        ScriptedModel(decision="direct_response"),
        ScriptedModel(),
        sprint_id="sprint-component-direct",
        catalog=_catalog(),
    )

    assert frozen["status"] == "accepted"
    assert frozen["execution"]["capsule_selection_validation"]["status"] == "pass"
    assert frozen["execution"]["capsule_fit_review"]["status"] == "pass"
    assert frozen["execution"]["run_contract_frozen"]
    assert direct["status"] == "direct_response"
    assert direct["verification_errors"] == []
    assert direct["execution"] is None


def test_explicit_machine_check_without_implementation_blocks_runtime_handoff(
    tmp_path: Path,
) -> None:
    requirement_ir = _requirement_ir()
    requirement_ir["requirements"][0]["machine_checkable"] = True
    semantic = planner.run_semantic_planning_pipeline(
        requirement_ir,
        tmp_path / "semantic",
        ScriptedModel(),
        ScriptedModel(),
        catalog=_catalog(),
    )

    result = planner.compile_and_freeze_execution_bundle(
        requirement_ir,
        semantic,
        tmp_path / "execution",
        sprint_id="sprint-evaluation-contract-failure",
        planner_model=ScriptedModel(),
        reviewer_model=ScriptedModel(),
    )

    assert result["evaluation_plan"]["verdict"] == "fail"
    assert result["evaluation_plan_validation"]["status"] == "fail"
    assert result["run_contract_frozen"] is None
    assert result["plan_acceptance"]["decision"] == "failed"
    assert result["plan_acceptance"]["runtime_handoff_allowed"] is False
    assert any(
        row["code"] == "MACHINE_CHECK_IMPLEMENTATION_MISSING"
        for row in result["evaluation_plan"]["unresolved"]
    )


def test_exact_reuse_component_freezes_registered_capsules_and_topology(
    tmp_path: Path,
) -> None:
    result = planner.run_elastic_planning_request(
        _requirement_ir(),
        tmp_path / "exact-reuse",
        ScriptedModel(decision="exact_reuse"),
        ScriptedModel(),
        sprint_id="sprint-component-exact-reuse",
        catalog=_catalog(),
    )

    assert result["status"] == "accepted"
    assert result["verification_errors"] == []
    graph = result["execution"]["task_graph_contract"]
    assert graph["workflow_contract_id"] == "code.cli_smoke"
    assert [node["id"] for node in graph["nodes"]] == ["S1", "S2", "S3"]
    assert [node["capability_capsule_id"] for node in graph["nodes"]] == [
        "cap.requirement-compiler-implementation",
        "cap.requirement-compiler-implementation",
        "cap.requirement-compiler-audit",
    ]
    assert all(node["approved_physical_operator_ids"] for node in graph["nodes"])
    assert all(
        node["planning_authority"] == "frozen_execution_plan_v1"
        for node in graph["nodes"]
    )
    scheduler_nodes = result["execution"]["scheduler_input"]["graph"]["nodes"]
    lifecycle_sidecars = {
        "artifact.guard_decision",
        "artifact.resource_binding",
        "artifact.handoff_md",
        "artifact.eval_md",
        "artifact.eval_json",
    }
    assert all(
        not lifecycle_sidecars.intersection(node["artifact_contract"]["produces"])
        for node in scheduler_nodes
    )
    assert planner.scheduler_input_runtime.validate(
        result["execution"]["scheduler_input"], require_runtime_authority=True
    ) == {"ok": True, "errors": []}
