# End-to-end artifact architecture incubator

This folder contains reviewed JSON examples for Solar's proposed artifact-only
control plane. It does not modify or connect the current gateway, planner,
scheduler, dispatcher, worker runtime, dashboard, evaluator, or registry.

The governing model is:

> Models author semantic artifacts. Deterministic components validate,
> reference, freeze, schedule, and account for artifacts. No model output
> directly changes runtime state.

## Artifact sequence

### Input and semantic compilation

1. `raw_intent.json` - immutable captured request.
2. `intent_ir.json` - grounded goals, outcomes, constraints, and unresolved
   issues.
3. `intent_validation.json` - deterministic structural and reference verdict.
4. `intent_fidelity.json` - independent semantic-fidelity verdict.
5. `clarification.json` - conditional artifact for blocking ambiguity or
   conflict.
6. `requirement_ir.json` - workflow-independent obligations, scope,
   assumptions, approvals, and rollback semantics.
7. `requirement_validation.json` and `requirement_coverage.json` - registered
   check integrity and complete IntentIR coverage.

### Planning and freezing

8. `strategy.json` - the Elastic Planner's smallest-sufficient strategy.
9. `planning_catalog_snapshot.json` and `check_registry.json` - immutable
   planning and verification choices visible to the request.
10. `plan_ir.json` - logical nodes decorated with capsules, physical-operator
    alternatives, artifact ports, obligations, dependencies, and gates.
11. `plan_validation.json` - deterministic plan and policy admission.
12. `binding_trace.json` - mechanical requirement-to-node/artifact/verifier
    join.
13. `run_contract.frozen.json` - content-hashed run authority. Runtime must not
    reread mutable repository contracts.

### Runtime control and evidence

14. `task_graph_state.json` - mutable execution ledger separate from PlanIR.
15. `dispatch_record.json`, `lease_record.json`, and `approval_record.json` -
    physical choice, fenced ownership, and exact effect authorization.
16. `node_envelope.json` - typed worker result boundary.
17. `repair_record.json` - conditional record of the single permitted repair.
18. `gate_ledger.json` and `operator_state_log.json` - gate/evaluator agreement
    and typed operator availability transitions.
19. `domain_evidence.json` and `artifact_manifest.json` - domain-owned evidence
    plus run-wide content identity and completeness.

### Final truth, delivery, and learning

20. `evidence_ir.json` - independent recomputation and the only path to GREEN.
21. `delivery_scope.json` and `final_delivery_manifest.json` - honest scope and
    content-hashed publication.
22. `experience_record.json` and `promotion_record.json` - learning without
    allowing memory to become registry authority.
23. `compilation_trace.json` - digest-bound audit of the complete example.

## Design-support metadata

- `artifact_registry.json` names each artifact's producer, engine, consumers,
  and decision.
- `field_consumer_matrix.json` applies the schema law: a field survives only
  when a named consumer changes a real decision from its value.
- `generalization_cases.json` challenges the front-end contracts with twelve
  materially different prompts.
- `architecture_invariants.json` records the non-negotiable cross-stage laws.

The methane example is intentionally **not executed**. Runtime-shaped examples
are labeled as contract examples, graph admission is blocked, EvidenceIR exits
non-zero, no delivery is published, and no workflow is promotion-eligible.
That fail-closed ending demonstrates the metadata semantics without pretending
that the current product executed the proposed architecture.

These are ordinary reviewed JSON examples, not formal JSON Schema files and
not production runtime output. Formal schemas and runtime wiring are separate
future increments.
