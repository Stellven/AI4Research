# End-to-end artifact architecture and current runtime index

## Current runtime / new-machine entry — 2026-08-30

Start with [NEW-MACHINE-START-HERE.md](NEW-MACHINE-START-HERE.md) for the project
purpose, current production pipeline, exact schema/validator paths, known issues
and environment requirements. The formal intake now reaches Intent compilation,
native deterministic Requirement compilation, Elastic Planner, frozen SchedulerInput,
Scheduler and operators. Requirement/Discovery semantic defects remain open.

The numbered artifacts below are design/reference examples, NOT proof that every
described stage is emitted or enforced in the running product. In particular,
RequirementIR v2 uses a template-based format evaluator; do not substitute the
different legacy requirement-ir.schema.json. The current entry document explicitly
distinguishes JSON Schema, code validation and design-only examples.

## Historical architecture-incubator notes

This folder contains reviewed JSON examples for Solar's artifact-only control
plane. The Intent Compiler increment is now connected inside the current
gateway when a semantic compiler provider is configured. The examples in this
folder remain explicitly non-live; the planner, scheduler, dispatcher, worker
runtime, final evaluator, and registry are not migrated by this increment.

The governing model is:

> Models author semantic artifacts. Deterministic components validate,
> reference, freeze, schedule, and account for artifacts. No model output
> directly changes runtime state.

## Directory layout

The examples follow the numbered pipeline-stage structure used by the
AI4Research schema reference. Each artifact is stored at
`<stage>/<artifact>/<artifact>.json`.

| Stage directory | Contents |
| --- | --- |
| `0-design support metadata/` | Cross-stage architecture, registry, field-consumer, and generalization metadata. |
| `1-input normalizer output/` | Immutable normalized request capture. |
| `2-intent compiler output/` | Intent interpretation, validation, fidelity, acceptance, and clarification artifacts. |
| `3-requirements compiler output/` | Requirement IR, validation, and coverage artifacts. |
| `4-elastic planner output/` | Strategy and immutable planning/check catalog snapshots. |
| `5-taskgraph compiler and validator output/` | Plan IR, plan admission, binding, frozen run authority, and the frozen scheduler input. |
| `6-scheduler output/` | Task-graph state, dispatch choice, and lease records. |
| `7-dispatcher output/` | Exact effect-approval records used during dispatch. |
| `8-physical operator output/` | Typed worker results, repair records, domain evidence, and artifact inventory. |
| `9-evaluator and gates output/` | Gate, operator-state, and final evidence verdicts. |
| `10-final delivery output/` | Delivery scope/manifests, learning records, promotion, and full-chain audit. |

Stage `0` is an explicit extension for the design-support files that apply to
multiple pipeline stages and therefore do not belong to one producer-output
stage in the reference structure.

## Requirement Compiler input fixtures

The Stage 2 directory includes `requirement-compiler-input-fixtures/`,
containing 25 synthetic `intent_ir.json` artifacts used as Requirement
Compiler inputs. Intent validation, fidelity, and acceptance remain separate
evaluator artifacts and are not included in those compiler-input fixtures.

The corrected Requirement Compiler run is retained under Stage 3 in
`native-intent-ir-compiler-evaluation-20260825/`. Each trial consumes only
`intent_ir.json`, emits only `requirement_ir.json`, and records its separate
deterministic format evaluation. The earlier
`current-v1-compiler-evaluation-20260825/` run is marked superseded.

## Historical integration boundary (before the later typed runtime wiring)

The current `intent_gateway.py` activates this compiler when
`SOLAR_INTENT_COMPILER_PROVIDER=codex` is present. Compiler and reviewer calls
are fresh, schema-bound invocations; their optional model selections come from
`SOLAR_INTENT_COMPILER_MODEL` and `SOLAR_INTENT_REVIEWER_MODEL`. An accepted
IntentIR is now passed directly to the native deterministic Requirement
Compiler, followed by a separate deterministic format and reference evaluator.
`needs_clarification`, `failed`, and failed RequirementIR evaluations stop
before downstream handoff. When no semantic compiler provider is configured,
the existing gateway behavior remains unchanged during this migration.

The connected boundary has been exercised through the real dashboard intake
route with Codex as both compiler and independent reviewer. Accepted research
and direct-answer requests produced exact hash-bound `input.json` artifacts;
an ambiguous external action returned its clarification questions without a
sprint; and an impossible constraint pair failed without RequirementIR or a
sprint. The bounded repair path remains implemented and mechanically tested,
but a naturally triggered live model repair has not yet been observed.

## Artifact sequence

### Input and semantic compilation

1. `raw_intent.json` - immutable captured request.
2. `intent_ir.json` - grounded goals, outcomes, constraints, and unresolved
   issues.
3. `intent_validation.json` - deterministic structural and reference verdict.
4. `intent_fidelity.json` - independent semantic-fidelity verdict.
5. `intent_acceptance.json` - the single accepted, needs-clarification, or
   failed admission decision, with one bounded internal repair.
6. `clarification.json` - conditional artifact for blocking ambiguity or
   conflict.
7. `requirement_ir.json` - workflow-independent obligations, scope,
   assumptions, approvals, and rollback semantics.
8. `requirement_validation.json` and `requirement_coverage.json` - registered
   check integrity and complete IntentIR coverage.

The live migration path additionally emits
`requirement_format_evaluation.json` as a deterministic preflight evaluator
artifact. It does not replace the full requirement validator or coverage
verifier described in step 8.

### Planning and freezing

9. `strategy.json` - the Elastic Planner's smallest-sufficient strategy.
10. `planning_catalog_snapshot.json` and `check_registry.json` - immutable
   planning and verification choices visible to the request.
11. `plan_ir.json` - semantic logical nodes, typed artifact ports, effects,
    requirement ownership, dependencies, and gate requirements. Capsule,
    physical-operator, and evaluator bindings are compiled afterward and are
    frozen into `scheduler_input.json`.
12. `plan_validation.json` - deterministic plan and policy admission.
13. `binding_trace.json` - mechanical requirement-to-node/artifact/verifier
    join.
14. `run_contract.frozen.json` - content-hashed run authority. Runtime must not
    reread mutable repository contracts.
15. `scheduler_input.json` - the single frozen executable graph handed to the
    scheduler. It contains dependency, capsule, ordered physical-candidate,
    artifact, evaluator, resource, effect, priority, and failure contracts. It
    excludes mutable status, selected operators, attempts, and leases.

### Runtime control and evidence

16. `task_graph_state.json` - mutable execution ledger separate from PlanIR and
    `scheduler_input.json`.
17. `dispatch_record.json`, `lease_record.json`, and `approval_record.json` -
    physical choice, fenced ownership, and exact effect authorization.
18. `node_envelope.json` - typed worker result boundary.
19. `repair_record.json` - conditional record of the single permitted repair.
20. `gate_ledger.json` and `operator_state_log.json` - gate/evaluator agreement
    and typed operator availability transitions.
21. `domain_evidence.json` and `artifact_manifest.json` - domain-owned evidence
    plus run-wide content identity and completeness.

### Final truth, delivery, and learning

22. `evidence_ir.json` - independent recomputation and the only path to GREEN.
23. `delivery_scope.json` and `final_delivery_manifest.json` - honest scope and
    content-hashed publication.
24. `experience_record.json` and `promotion_record.json` - learning without
    allowing memory to become registry authority.
25. `compilation_trace.json` - digest-bound audit of the complete example.

## Design-support metadata

- `artifact_registry.json` names each artifact's producer, engine, consumers,
  and decision.
- `field_consumer_matrix.json` applies the schema law: a field survives only
  when a named consumer changes a real decision from its value.
- `generalization_cases.json` challenges the front-end contracts with twelve
  materially different prompts.
- `architecture_invariants.json` records the non-negotiable cross-stage laws.
- [`artifact_producer_classification.md`](<0-design support metadata/artifact_producer_classification/artifact_producer_classification.md>)
  labels every JSON example as step output, evaluator output, or
  control/support, and names its actual producer.

The methane example is intentionally **not executed**. Runtime-shaped examples
are labeled as contract examples, graph admission is blocked, EvidenceIR exits
non-zero, no delivery is published, and no workflow is promotion-eligible.
That fail-closed ending demonstrates the metadata semantics without pretending
that the current product executed the proposed architecture.

These remain reviewed examples rather than production runtime output. The
Intent Compiler's enforceable schema mirrors live under
`harness/schemas/compiler/`. Planner/Scheduler schema mirrors now live under
`harness/schemas/planning/`, and scientific operator contracts under
`harness/schemas/evidence/`. See the current entry document for actual wiring;
the historical examples do not define the present implementation boundary.
