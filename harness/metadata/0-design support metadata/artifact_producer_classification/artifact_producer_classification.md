# Metadata artifact producer classification

This form separates the JSON produced by a pipeline step from JSON produced by
an evaluator or gate for that step. It also identifies control and support
artifacts that do not honestly belong to either category.

## Labels

- `STEP_OUTPUT` - the named pipeline component produces this as its work or
  operational decision.
- `EVALUATOR_OUTPUT` - an independent validator, reviewer, verifier, gate, or
  admission controller judges another artifact or step.
- `CONTROL_OR_SUPPORT` - a catalog, frozen authority, audit record, repair
  record, or design reference used across steps. It is neither the primary work
  nor a quality verdict on that work.

The directory holding a file is a presentation grouping. The `Producer` and
`Label` columns are the source of truth for artifact ownership.

| Stage | JSON file | Producer | Label | What it produces or evaluates |
| --- | --- | --- | --- | --- |
| Design support | `architecture_invariants.json` | Architecture governance | `CONTROL_OR_SUPPORT` | Cross-stage rules; does not evaluate one run artifact. |
| Design support | `artifact_registry.json` | Artifact-model registry | `CONTROL_OR_SUPPORT` | Registry of artifact producers, consumers, and decisions. |
| Design support | `field_consumer_matrix.json` | Architecture governance | `CONTROL_OR_SUPPORT` | Design-time proof that each field has a decision-making consumer. |
| Design support | `generalization_cases.json` | Test/design author | `CONTROL_OR_SUPPORT` | Prompt cases used to pressure-test the artifact design. |
| Input normalizer | `raw_intent.json` | `input_normalizer` | `STEP_OUTPUT` | Immutable normalized capture of the user's request. |
| Intent Compiler | `intent_ir.json` | `intent_compiler` | `STEP_OUTPUT` | Semantic interpretation of the normalized request. |
| Intent Compiler | `intent_validation.json` | `intent_validator` | `EVALUATOR_OUTPUT` | Mechanically validates `intent_ir.json`. |
| Intent Compiler | `intent_fidelity.json` | `independent_intent_reviewer` | `EVALUATOR_OUTPUT` | Reviews whether `intent_ir.json` preserved the meaning of `raw_intent.json`. |
| Intent Compiler | `intent_acceptance.json` | `intent_acceptance_gate` | `EVALUATOR_OUTPUT` | Combines validation and fidelity into accept, clarify, or fail. |
| Intent Compiler | `clarification.json` | `clarification_gate` | `CONTROL_OR_SUPPORT` | Records a blocking question and user resolution; it is an admission-control artifact, not compiler work. |
| Requirements Compiler | `requirement_ir.json` | `requirement_compiler` | `STEP_OUTPUT` | Workflow-independent obligations compiled from accepted intent. |
| Requirements Compiler | `requirement_format_evaluation.json` | `requirement_format_evaluator` | `EVALUATOR_OUTPUT` | Deterministic preflight of RequirementIR template shape, references, hashes, and accepted-intent binding; does not replace validation or coverage. |
| Requirements Compiler | `requirement_validation.json` | `requirement_validator` | `EVALUATOR_OUTPUT` | Validates references, scope, checks, and checkability in `requirement_ir.json`. |
| Requirements Compiler | `requirement_coverage.json` | `requirement_coverage_verifier` | `EVALUATOR_OUTPUT` | Verifies that accepted IntentIR items were not dropped. |
| Elastic Planner | `strategy.json` | `elastic_planner` | `STEP_OUTPUT` | Chooses direct response, reuse, parameterization, extension, composition, or generation. |
| Elastic Planner | `planning_catalog_snapshot.json` | `registry_snapshotter` | `CONTROL_OR_SUPPORT` | Freezes workflows, capsules, operators, gates, and availability visible to planning. |
| Elastic Planner | `check_registry.json` | `registry_snapshotter` | `CONTROL_OR_SUPPORT` | Freezes registered verification checks available to requirements, planning, and final verification. |
| TaskGraph compiler and validator | `plan_ir.json` | `elastic_planner` | `STEP_OUTPUT` | Proposed logical graph, artifact ports, capsules, operator alternatives, obligations, and gates. |
| TaskGraph compiler and validator | `plan_validation.json` | `plan_policy_validator` | `EVALUATOR_OUTPUT` | Validates the proposed PlanIR structure, registrations, effects, and complexity. |
| TaskGraph compiler and validator | `binding_trace.json` | `requirement_binder` | `EVALUATOR_OUTPUT` | Verifies and records requirement-to-node, artifact, and verifier coverage. |
| TaskGraph compiler and validator | `run_contract.frozen.json` | `contract_freezer` | `CONTROL_OR_SUPPORT` | Immutable execution authority assembled only after plan admission. |
| Scheduler | `task_graph_state.json` | `scheduler` | `STEP_OUTPUT` | Mutable node readiness and execution state. |
| Scheduler | `dispatch_record.json` | `scheduler` | `STEP_OUTPUT` | Physical-operator choice and reasons alternatives were skipped. |
| Scheduler | `lease_record.json` | `scheduler` | `STEP_OUTPUT` | Fenced ownership decision for one node attempt. |
| Dispatcher | `approval_record.json` | `approval_controller` | `EVALUATOR_OUTPUT` | Evaluates and authorizes an exact approval-bound effect before dispatch. |
| Physical operator | `domain_evidence.json` | `workflow_nodes` | `STEP_OUTPUT` | Domain work and evidence produced by executing workflow nodes. |
| Physical operator | `node_envelope.json` | `worker_harness` | `STEP_OUTPUT` | Typed wrapper around the worker result, error, artifacts, and attempt identity. |
| Physical operator | `artifact_manifest.json` | `artifact_ledger` | `CONTROL_OR_SUPPORT` | Content-hashed inventory of declared and missing run artifacts. |
| Physical operator | `repair_record.json` | `repair_controller` | `CONTROL_OR_SUPPORT` | Conditional record binding evaluator defects to one permitted repair generation. |
| Evaluators and gates | `gate_ledger.json` | `gate_executor` | `EVALUATOR_OUTPUT` | Records deterministic gate and independent evaluator decisions for the same generation. |
| Evaluators and gates | `evidence_ir.json` | `independent_final_verifier` | `EVALUATOR_OUTPUT` | Independently recomputes obligation outcomes and the final run verdict. |
| Evaluators and gates | `operator_state_log.json` | `failure_classifier` | `CONTROL_OR_SUPPORT` | Typed operator-availability transition used by scheduling; not a work-quality verdict. |
| Final delivery | `delivery_scope.json` | `delivery_assembler` | `STEP_OUTPUT` | User-facing disclosure of assumptions and tested-versus-not-tested boundaries. |
| Final delivery | `final_delivery_manifest.json` | `delivery_assembler` | `STEP_OUTPUT` | Content-hashed publication assembled after independent green evidence. |
| Final delivery | `experience_record.json` | `experience_compressor` | `STEP_OUTPUT` | Post-run learning record used as planner experience, not registry authority. |
| Final delivery | `promotion_record.json` | `promotion_controller` | `EVALUATOR_OUTPUT` | Evaluates whether a workflow is eligible for registry promotion. |
| Final delivery | `compilation_trace.json` | `artifact_controller` | `CONTROL_OR_SUPPORT` | Digest-bound audit of the complete artifact chain. |

## Important boundary

An artifact being deterministic does not automatically make it an evaluator
output. For example, `dispatch_record.json` is deterministic but is still the
scheduler's own decision. Conversely, `intent_fidelity.json` is model-authored
but is evaluator output because its purpose is to judge `intent_ir.json`.
