# Requirement semantics and retrieval contract

This repair separates interpretation from validation. It does not claim arbitrary
LLM outputs or public-provider behavior are deterministic.

## Authoritative path

1. Accepted IntentIR enters `lib/requirement_compiler/semantic.py`. A schema-bound
   LLM fills only the editable values of a program-owned template: requirements,
   source references, priorities, semantic roles, and an optional discovery contract.
   An independent LLM checks fidelity against the same fixed definitions. Schema/source
   checks are mandatory. Contract v2 allows one structural and one semantic repair,
   at most three compiler/two reviewer calls within the existing four per-call
   timeout slots. There is no deterministic semantic fallback.
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

- `schemas/compiler/requirement-semantic-contract.v3.json`: current shared
  semantic definition, ownership, field descriptions and count/evidence policies.
- `schemas/compiler/requirement-semantics.v2.schema.json`: current LLM values body.
- `schemas/compiler/requirement-semantic-review.v2.schema.json`: structured fidelity
  verdict with rule ID, field pointer, Intent/policy evidence references and reason.
  The v1 files remain unchanged for historical interpretation.
- `schemas/compiler/retrieval-contract.v1.schema.json`: research subject, queries,
  source-linked inclusion/exclusion, coverage, time bounds and minimum candidates.
- `schemas/planning/plan-ir.semantic.structured.v2.schema.json`: model generation
  shape requiring a nullable contract reference. Historical PlanIR v2 remains readable.
- `schemas/planning/scheduler-input.v1.schema.json`: optional immutable retrieval
  contract, embedded for offline validation; a regression checks exact schema equality.

## Program-owned template and model permissions

`lib/requirement_compiler/template_contract.py` loads the definition and referenced
schemas once per compilation. It creates `template.json` with a hash-bound
`contract_ref`, `read_only` definitions/registry/original constraints/item templates,
and blank editable `values`. The Compiler sees that complete template but returns
only the values object. Strict schema validation rejects unknown fields and changes
to fixed constants; the program deep-copies valid values into the original template.
Each generation retains `filled_template.json`; the Reviewer sees exactly the same
read-only snapshot and the filled values. Validation records retain its contract ref.
Neither model may rewrite definitions, descriptions, policies or original constraints.

Contract v2 freezes registry check IDs and Intent source IDs as enums in the actual
provider schema, not just the prompt. The same instantiated schema validates the
response; its files are `compiler-output.schema.json` and `reviewer-output.schema.json`
beside the template. `selection_authority` contains exact field pointers, Intent
references and model-authored justification for hard retrieval restrictions. The
program checks target/reference coverage; the reviewer decides whether the cited
Intent really authorizes each restriction. Topic queries and best-effort corpus
coverage need no such authority, and never remove mandatory report scope.

Program-owned count/evidence policies are copied separately into
`semantic_contract.runtime_policies`, not synthesized as user requirements.
Missing evidence must remain visible; disclosure does not establish task success.

The shared count policy distinguishes a future runtime handoff floor from a claim
about sources already available before planning. With no explicit user count,
`minimum_candidates=1` is required for nonempty discovery handoff, not an invented
user requirement and not proof of report sufficiency. An explicit final source or
evidence-corpus lower bound may authorize the same accepted-candidate lower bound
when those sources must enter through this discovery/ingestion path. This is a
necessary upstream execution condition, not proof that the final artifact uses the
required number of valid sources. Both models see this same rule; no reviewer
error-string whitelist or automatic acceptance is used.
The source_constraints copy contains ALL original constraints, while only actual
source-selection constraints may become discovery predicates. Corpus coverage is
aggregate coverage, not a per-paper requirement to discuss every technique.

The RequirementIR v2 base envelope and retrieval/SchedulerInput shapes are unchanged.
New semantic extensions retain selection_authority, runtime_policies and template_ref;
historical semantic extensions without these fields remain readable. Frozen historical
artifacts are not rewritten. The filled template is compilation audit evidence, not a
new scheduler authority or extra agent stage. Do not edit a published contract's
meaning in place: use a new version for a subsequent semantic-policy change.

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
