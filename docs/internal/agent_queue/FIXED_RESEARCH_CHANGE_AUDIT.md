# Fixed research workflow change audit

This is a review aid, not a product file. Exclude `docs/internal/`, `.gstack/`,
and `artifacts/` from the product commit.

## Production files

- `harness/config/capability-capsules.registry.yaml` — registers the exact
  least-privilege research and Part-B capsules.
- `harness/config/physical-operators.json` — registers the exact command-backed
  workers for all fixed workflow stages.
- `harness/config/workflows/research.evidence_to_poc.v1.workflow.json` — defines
  the registered v1.3 fixed 15-node A1-A8/B1-B7 contract.
- `harness/config/capability-capsules/cap.research-seed-snapshot.yaml` — A1
  request/source-authority snapshot capsule.
- `harness/config/capability-capsules/cap.research-public-source-discovery.yaml`
  — A2 governed pack/live/hybrid discovery capsule.
- `harness/config/capability-capsules/cap.research-source-validation.yaml` — A3
  provenance, relevance, integrity, and source-count gate capsule.
- `harness/config/capability-capsules/cap.research-experiment-approval.yaml` —
  B4 exact plan/policy approval capsule without unrelated repository binding.
- `harness/config/capability-capsules/cap.research-evidence-poc-experiment-run.yaml`
  — B5 fixed no-network benchmark capsule.
- `harness/config/capability-capsules/cap.research-evidence-poc-claim-verification.yaml`
  — B6 four-artifact experiment reconciliation capsule.
- `harness/config/capability-capsules/cap.research-evidence-poc-final-delivery.yaml`
  — B7 accepted integrated delivery capsule.
- `harness/lib/fixed_research_workflow.py` — validates typed profiles and source
  authority, snapshots external inputs, specializes the fixed graph, and
  creates controller retrieval/experiment policy bindings.
- `harness/lib/workflow_intake.py` — routes the fixed contract through its safe
  specialized intake and preserves exact inputs/conditional state.
- `harness/lib/workflow_router.py` — prevents unsafe generic instantiation of
  the specialized fixed contract.
- `harness/lib/workflow_contract.py` — preserves declared evidence schemas in
  instantiated output contracts.
- `harness/lib/graph_node_dispatcher.py` — exact fixed-worker admission,
  envelopes, dependency/ledger/manifest authority, one-shot approval, and
  deterministic evaluator integration.
- `harness/lib/graph_scheduler.py` — intentionally unchanged from the base;
  no shared scheduler exception is part of this increment.
- `harness/lib/symphony/status-server.py` — existing dashboard intake profile,
  shipped-harness launcher precedence, declared deep deliverables, and public
  fixed-run input forwarding.
- `harness/status-server/routes/orchestration_routes.py` — projects scheduler
  state and exact fixed bindings truthfully without legacy autopilot metadata.
- `harness/solar-harness.sh` — routes persisted research intent to the fixed
  contract before Epic/Planner and forwards typed acquisition/retrieval/PoC
  policies.
- `harness/plugins/autosci/bin/fixed_research_node_adapter.py` — validates the
  Solar envelope and runs one bounded physical stage with output/side-effect
  accounting.
- `harness/plugins/autosci/operators/fixed_research_poc.py` — B1-B7 evidence
  handoff, idea/design, approval validation, benchmark, claim verification,
  and integrated final delivery.
- `harness/plugins/autosci/services/codex_research.py` — schema-bound fresh
  Codex subscription calls for A4-A7 with bounded calls and retained evidence.
- `harness/plugins/autosci/services/production_research.py` — governed public
  discovery failover/archive and deterministic model evidence accounting.
- `harness/plugins/autosci/backends/literature_discover.py` — bounded no-key
  public provider behavior and traceable failure metadata.
- `harness/plugins/autosci/operators/research_synthesis/source_discovery.py` —
  pack/live/hybrid candidate merge with channel/provider lineage.
- `harness/plugins/autosci/operators/research_synthesis/source_validation.py` —
  query relevance, integrity, accepted-source policy, and limitations.
- `harness/plugins/autosci/operators/research_synthesis/evidence_synthesis.py`
  — carries accepted source/channel limitations into synthesis.
- `harness/plugins/autosci/operators/research_synthesis/report_draft.py` —
  retains evidence-lineage and limitation obligations in the draft.
- `harness/plugins/autosci/operators/research_synthesis/report_revision.py` —
  enforces conclusion/method/limitation preservation across bounded repair
  calls and accounts for every call artifact.
- `harness/tools/fixed_research_benchmark.py` — real deterministic integrity
  benchmark designed for `unshare -Urn` with network disabled.
- `harness/tools/fixed_research_uat.py` — shipped local/dashboard continuation
  driver and reproducibility preflight/source inventory.
- `harness/schemas/evidence/fixed_research_human_approval.v1.schema.json` — B4
  policy/human approval evidence schema.
- `harness/schemas/evidence/fixed_research_part_b.v1.schema.json` — typed B1-B7
  artifact schemas and cross-stage authority fields.

## Test files

- `tests/harness/workflow_contract/test_fixed_research_workflow.py` — fixed
  intake, source authority, exact workers, non-dry operatord, Codex Part A,
  one-shot approval, real benchmark, tamper, ledger, and final lineage coverage.
- `tests/harness/tools/test_fixed_research_uat.py` — UAT driver/preflight,
  dashboard continuation, and Codex symlink/hash coverage.
- `tests/harness/test_status_server_deliverables.py` — dashboard profile,
  stale-launcher prevention, and declared deep-deliverable coverage.
- `tests/harness/test_s04_orchestration_routes.py` — exact fixed-binding and
  authoritative state-sidecar projection coverage.
- `tests/plugins/autosci/research_synthesis_operators/test_research_synthesis_operators.py`
  — governed source merge/relevance/lineage and report preservation cases.
- `tests/plugins/autosci/test_production_research_services.py` — bounded public
  failover and model-call evidence accounting.
- `tests/harness/workflow_contract/conftest.py`,
  `tests/harness/workflow_contract/test_contract_schema.py`, and
  `tests/harness/workflow_contract/test_router_cli.py` — canonical registry,
  compilation, and router catalog expectations for the added contract.
- `harness/tests/workflow_contract/conftest.py`,
  `harness/tests/workflow_contract/test_contract_schema.py`, and
  `harness/tests/workflow_contract/test_router_cli.py` — shipped mirror of the
  same contract-catalog checks.

## Excluded evidence and notes

- `.gstack/` — local browser state.
- `artifacts/` — retained UAT, provider, screenshot, and freeze evidence.
- `docs/internal/` — task state, handoff, and this review audit.

## 2026-08-18 dashboard-to-final path corrections

Found by running the real dashboard front door end to end for the first time.
Full evidence and failing payloads:
`artifacts/dashboard-full-uat-r5-20260818/RUN-SUMMARY.md`.

### Product changes

- `harness/lib/workflow_intake.py` — new `_intake_request_id()` re-sanitizes
  `SOLAR_INTAKE_REQUEST_ID` and stamps it on the sprint `status.json` as
  `request_id`. The status server exported that variable and no component
  consumed it, so a dashboard-created sprint could not be attributed and
  `dashboard-to-final` polled until timeout.
- `harness/tools/fixed_research_uat.py` — extracted `_dashboard_runtime_env()`
  and added `SOLAR_INTENT_GATEWAY_DIR`. Without it the dispatch-time
  specialization guard resolved the binding manifest under the default
  installed gateway and rejected a valid binding as
  `fixed_research_intent_binding_evidence_invalid`.
- `harness/tools/fixed_research_uat.py` — new `_is_transient_dispatch_noop()`
  and `CommandRunner.run(tolerate_transient_noop=)`. `graph-dispatch` exits 2
  whenever its payload is `ok: false`, including a poll tick that dispatched
  nothing because the deterministic gate is still waiting for its builder. Only
  that exact shape is tolerated; guard rejections, unknown skip reasons, and any
  tick that moved the graph stay fatal.
- `harness/lib/graph_node_dispatcher.py` — `_node_requires_human_search()`
  returns false for a node with an exact `required_operator_id`. A2 declares
  `source.search` / `research.source.web` / `research.source.academic` because
  its command worker queries those providers; those strings are also in
  `HUMAN_SEARCH_CAPABILITIES`, so the generic human-in-the-loop lane preempted
  the exact worker. Only the fixed-contract compiler assigns
  `required_operator_id`, so legacy planner nodes are unaffected.

### Test changes

- `tests/harness/workflow_contract/test_workflow_intake.py` and its shipped
  mirror `harness/tests/workflow_contract/test_workflow_intake.py` — request-id
  stamped, absent, and re-sanitized cases.
- `tests/harness/tools/test_fixed_research_uat.py` — two seam tests that run the
  real intake and feed its real output to the real dashboard reader, three
  `_dashboard_runtime_env` cases, and six transient-noop classification cases
  including the real guard-rejection payload.
- `tests/harness/workflow_contract/test_fixed_research_workflow.py` — exact-bound
  nodes are never diverted to human search, asserted both on a literal node and
  over every entry in `PHYSICAL_OPERATOR_BY_NODE`, plus one case proving an
  unbound node still uses the human-search lane.

### Why the gap survived

The two pre-existing dashboard attribution tests constructed `status.json` by
hand with a `request_id`, so they passed even though nothing ever wrote one.
The producer and the consumer were each tested against a fixture of the other.
The new seam tests wire the real producer to the real consumer.

## 2026-08-18 (later) — model tier and stage capsule corrections

### Codex model tier

`gpt-5.5` (the adapter default in `_codex_services`) was quota-exhausted until
2026-08-19 23:46. The `gpt-5.3-codex-spark` tier was not. The workflow already
exposed `SOLAR_CODEX_RESEARCH_MODEL` / `SOLAR_CODEX_REVIEW_MODEL`, so no code
change was needed; the run env pins Spark and the UAT entry manifest records it
(`SOLAR_CODEX_RESEARCH_MODEL=gpt-5.3-codex-spark`), keeping the run reproducible.
Spark returned schema-valid structured output on its first A4 call.

### Product change: dedicated capsules for A4-A8 and B1-B3

Eight stages were still bound to generic capsules:

| stage | was | now |
|---|---|---|
| evidence_synthesis | cap.requirement-research-synthesizer | cap.research-evidence-synthesis |
| report_draft | cap.requirement-research-synthesizer | cap.research-report-draft |
| independent_review | cap.requirement-compiler-verification | cap.research-independent-review |
| report_revision | cap.requirement-research-synthesizer | cap.research-report-revision |
| final_acceptance | cap.requirement-compiler-verification | cap.research-final-acceptance |
| poc_handoff | cap.requirement-research-synthesizer | cap.research-evidence-poc-handoff |
| idea_evaluation | cap.requirement-compiler-verification | cap.research-poc-idea-evaluation |
| experiment_design | cap.requirement-compiler-planner | cap.research-poc-experiment-design |

`cap.requirement-research-synthesizer` declares the legacy AutoSci 13-output
research bundle and postconditions `output_present` on `claims_jsonl`,
`report_ast_json`, `final_md`, and `research_eval_json`. The fixed workflow's A4
produces exactly one declared artifact, `evidence_synthesis.json`. The proof
gate therefore blocked A4 with `proof_obligations_failed` naming those four
fields, even though the operator completed with exit 0, the manifest recorded
`all_outputs_present: true` with no violations, and the deterministic content
gate returned PASS.

This is the same defect class already fixed for B4-B7. A4-A8 and B1-B3 were
missed because no run had ever reached their proof gate: every earlier attempt
died at or before A4 on a model/quota failure, so the obligations were never
evaluated.

New capsule manifests under `harness/config/capability-capsules/`, registered in
`harness/config/capability-capsules.registry.yaml`, bound in
`harness/config/workflows/research.evidence_to_poc.v1.workflow.json`, and added
to the load-bearing inventory in `harness/tools/fixed_research_uat.py`. Each
declares no repository/GitHub resource capsule, matching the B4 correction.

### Test changes

`tests/harness/workflow_contract/test_fixed_research_workflow.py`:

- every stage pins exactly one capsule and it must be a `cap.research-*` one,
  so no stage can silently fall back to a generic requirement-compiler capsule;
- each stage capsule's `output_present` field must name an artifact that stage
  actually declares, under the same `<name>_json` -> `<name>.json` convention
  `graph_node_dispatcher._proof_field_presence` applies;
- no stage capsule may require a resource capsule.

The first two would have caught this without needing a live model call.

## 2026-08-18 (later still) — A7 preservation contract corrections

Runs r7-r11 all reached A7 `report_revision` and stopped there. Two genuine
defects were found and fixed; the residual is a model-capability limit.

### Defect: an empty matching heading masked a populated method section

`report_revision._markdown_section` returned on the **first heading match**,
even when that section had no body. A real Spark draft emitted:

```
## Method and evidence protocol
## Evidence scope and processing

Sources used (as supplied IDs):
...
## Evidence method
1. No external tool calls or outside sources were used.
...
```

The first matching heading is empty, so the extractor returned `""` and A7
rejected a report whose method section was present, with
`lineage_incomplete: "Original accepted report has no conclusions or
substantive method section to preserve"`.

Fixed to return the first matching section that actually has content. Verified
against the real failing artifact: the extractor now recovers 413 characters
and `revision_preservation_requirements` builds. Four regressions cover the
masking case, first-populated-match precedence, the all-empty case, and the
genuinely-absent case (so the guard still fires).

### Defect: the preservation requirement was not actionable

`verify_revision_response_preservation` requires the original normalized method
text to remain a substring of the revised method section, and every accepted
conclusion to be reproduced unchanged. The reviser request forwarded only
`preserved_conclusion_ids`, `preserved_method_sha256`, and
`preserved_limitations` — that is, an ID list and a digest. A model cannot act
on a SHA-256.

The request now also forwards `original_method` and `original_conclusions`, the
exact text the check compares against. A regression asserts both keys are in the
forwarded set.

Effect observed across runs: with `original_method` forwarded, A7 stopped
failing the method check and advanced to the conclusion check (r10); with
`original_conclusions` also forwarded, it oscillates between the two.

### Residual: model capability, not a defect

`gpt-5.3-codex-spark` cannot reliably satisfy A7's verbatim preservation
contract even when handed the exact text to reproduce. Across r7, r9, r10 and
r11 it alternated between rewording the method section and rewording an
accepted conclusion. Both rejections are the preservation guard working as
designed.

`gpt-5.5` quota returns 2026-08-19 23:46. The earlier audit records a gpt-5.5
run that reached A7 and produced a revision, failing only on limitation
rendering — a separate issue since fixed. A7 should be retried on gpt-5.5
before any further change to the preservation contract is considered.

Do not weaken the preservation checks to make Spark pass. They are the only
thing preventing a revision from silently dropping accepted conclusions or
recorded limitations.
