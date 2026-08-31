# Requirement semantics and retrieval contract

This repair separates interpretation from validation. It does not claim arbitrary
LLM outputs or public-provider behavior are deterministic.

## Authoritative path

1. Accepted IntentIR enters `lib/requirement_compiler/semantic.py`. A schema-bound
   LLM emits requirements, source references, priorities, semantic roles, and an
   optional discovery contract. An independent LLM checks fidelity. Schema/source
   checks are mandatory, with one bounded repair and no deterministic fallback.
2. RequirementIR v2 retains its existing envelope and adds `semantic_contract`
   (`solar.requirement_semantics.v1`). Source constraints are copied exactly,
   including category, expression operators, and source spans. Role classification
   and requirement text remain LLM outputs, not script inference.
3. PlanIR binds `retrieval_contract_ref` to the accepted discovery contract ID.
   Planner does not compile requirements or rewrite their meaning. Missing/wrong
   references and incompatible ownership fail validation and enter bounded repair.
   No deterministic function appends requirement prose to Discovery objectives.
4. Execution compilation copies the referenced contract into SchedulerInput.
   The frozen hash and runtime projection verification cover it. Dispatcher puts
   the same object in the operator envelope; the bridge cannot replace it with
   objective/topic prose. Composed discovery steps require a parent PlanIR reference.
5. Discovery uses the declared queries and executable selection predicates. Empty
   candidates, missing audit, unmet required coverage or absent provider evidence
   fail before successful handoff, including rapid smoke. Incomplete best-effort
   coverage remains a visible limitation rather than fabricated evidence.

## Schemas (relative to harness)

- `schemas/compiler/requirement-semantics.v1.schema.json`: LLM body.
- `schemas/compiler/requirement-semantic-review.v1.schema.json`: fidelity verdict.
- `schemas/compiler/retrieval-contract.v1.schema.json`: research subject, queries,
  source-linked inclusion/exclusion, coverage, time bounds and minimum candidates.
- `schemas/planning/plan-ir.semantic.structured.v2.schema.json`: model generation
  shape requiring a nullable contract reference. Historical PlanIR v2 remains readable.
- `schemas/planning/scheduler-input.v1.schema.json`: optional immutable retrieval
  contract, embedded for offline validation; a regression checks exact schema equality.

Selection predicates match case-insensitive literal alternatives in title/abstract
or publication type. All inclusion predicates must match; any exclusion excludes.
Dates with explicit bounds reject missing years. The LLM must supply appropriate
synonyms; lexical checks cannot establish scientific truth. Rapid mode skips bundled
semantic evaluation, not compiler admission or producer checks. A rapid journey is
workflow evidence, not independent scientific quality assurance.

Workflow/process and delivery requirements still belong in RequirementIR and in
the downstream artifact's acceptance contract. They are not source-selection terms.
Real negative source constraints (e.g. exclude reviews) stay in exclusion_criteria.

## Compatibility and environment

`compile_requirement_ir` now requires work_dir for model receipts. Legacy callers
must explicitly request `legacy=True`; normal GUI/CLI never silently falls back.
Model settings: optional `SOLAR_REQUIREMENT_MODEL`,
`SOLAR_REQUIREMENT_REVIEWER_MODEL`, `SOLAR_REQUIREMENT_TIMEOUT_SEC` (default 240).
Use the existing authenticated model CLI. No backend URL, user path, project title,
or research domain is hard-coded in this repair.

Offline regression: `python -m pytest -q tests/test_semantic_retrieval_contract.py
tests/test_typed_planner_wiring.py plugins/autosci/tests/test_production_research_discovery_scope.py`.
Run it from the approved runtime, with isolated pytest temporary/cache directories.
Test infrastructure needs pytest; deployment dependencies and model credentials
remain as specified in NEW-MACHINE-START-HERE.md. Journey evidence and failures are
recorded separately in pre-scheduler-stabilization-log-20260829.md.
