# Task: Fixed Research Evidence-to-PoC Workflow (Increment 1)

## Goal

Add a new Solar-owned, deterministic workflow for ordinary research requests. The workflow must use a fixed visible DAG rather than Planner-generated topology, execute Part A through the existing production research operators, and retain an explicit conditional Part-B section without pretending that Part B is available in this increment.

## Frozen product requirements

- New workflow contract id: `research.evidence_to_poc.v1`.
- Ordinary requests classified as `RESEARCH` route to this workflow deterministically.
- Software implementation and debugging requests keep their existing routes.
- The legacy `research.autosci.v1` contract and the existing 24-node scientific lifecycle remain unchanged.
- Planner does not create or replace this workflow's topology.
- Solar owns the TaskGraph, state transitions, evidence paths, evaluation gates, and dashboard-visible status.
- AutoSci/research-synthesis code is used only as bounded physical work behind individual Solar nodes.
- The visible Part-A topology is fixed and ordered:
  1. `seed_fetch`
  2. `source_discovery`
  3. `source_validation`
  4. `evidence_synthesis`
  5. `report_draft`
  6. `independent_review`
  7. `report_revision`
  8. `final_acceptance`
- Conditional Part-B stages remain visible in the graph. With `execution_profile=part_a_only`, each Part-B node is `skipped`/`not_applicable` with a stable reason. `part_a_plus_poc` remains fail-closed as `not_available` until its adapters are implemented.
- Routing uses typed `execution_profile` and `acquisition_mode`; it must not infer topology from prompt regexes.
- `acquisition_mode=source_pack` is the first reliable acquisition mode. A source pack is caller/host-supplied evidence, not generated test truth, and its canonical `sources.jsonl`, `evidence.jsonl`, extracts, byte counts, and SHA-256 digests are validated and bound into the graph.
- Deterministic tests may generate minimal source-pack bytes solely to validate the contract boundary; those tests must say that they are contract tests and must not claim live research success.

## Required execution seam

Each executable Part-A TaskGraph node must follow this bounded path:

`fixed TaskGraph node -> new-contract-only exact dispatcher selection -> command-backed physical adapter -> dispatch_research_node -> default_production_resolver -> exact research-synthesis operator -> research_node_result.v1 -> normal Solar evaluator/reconcile`

The adapter must write hash-bound artifacts only under the node's authorized Solar workdir paths. It must not invoke `SolarResearchRuntime`, `run_scientific_workflow.py`, or another nested scheduler. The old `research.autosci.v1` direct-dispatch helpers remain unchanged.

## Increment-1 scope

- New fixed workflow contract and registry discovery.
- Typed intake/routing contract.
- Source-pack validation and authority binding.
- Exact Part-A logical-to-physical bindings.
- A narrow new-contract-only dispatcher seam and physical adapter.
- Part-A handoff/evidence propagation through the existing evaluator path.
- Deterministic routing, preservation, contract, and real-boundary regressions.
- One non-network real command proof through the shipped dispatcher/operator boundary.

## Explicitly out of scope

- Part-B physical services or evidence-to-PoC schema adapters.
- A Codex-subscription/model adapter.
- Provider discovery, live-network success, Docker, or credentialed UAT.
- Broad scheduler, graph schema, evaluator, or dashboard semantics changes.
- Repairs to relevance, provider archives, model services, concurrency, retry behavior, or the old 24-node workflow.
- Mocks or fixtures used as evidence of live success.

## Stop conditions

Stop and report `NOT_AVAILABLE` if executable Part A requires any of the following:

- hiding all Part-A stages inside one physical node;
- duplicating or nesting the research runtime/scheduler;
- changing broad scheduler or graph-state semantics;
- weakening write-scope, evidence, evaluation, or completion gates;
- accepting caller assertions instead of validated source-pack bytes;
- changing the legacy AutoSci contract or 24-node workflow.

## Acceptance evidence

- The new contract validates, compile-checks, and instantiates the fixed topology.
- Ordinary research selects the new workflow without an explicit AutoSci marker.
- Software/debug routing is unchanged.
- Part-A-only graphs visibly record Part B as skipped/not applicable with reason.
- A supplied canonical source pack is hash-bound into node inputs and invalid packs fail closed.
- At least one Part-A node completes through the exact command-backed production seam and yields a schema-valid, hash-bound `research_node_result.v1` accepted by the existing evaluator.
- Focused and adjacent tests pass; Python and JSON validation and `git diff --check` pass.
- No live-success claim is made without credentials and real provider/model evidence.

## Handoff requirements

Report exact changed files and purpose, exact commands/results, preserved-file hashes or equivalent preservation assertions, deleted files (expected: none), unresolved Part-A/Part-B seams, and all environment-blocked or unverified behavior. Do not commit, push, or apply changes back.
