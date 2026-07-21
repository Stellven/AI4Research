# AutoSci Native Parity Gap Matrix

Logged: 2026-07-01 EDT / 2026-07-02 UTC

Scope: Agent B parity continuation in OpenSolar only. Native AutoSci was read as a reference snapshot and was not modified.

## Inventory Snapshot

Source command:

```bash
env PYTHONPATH=harness harness/bin/python3 \
  harness/tools/autosci_parity_inventory.py \
  --native-repo "/Users/jamesyuan/Developer/Github Repos (On Git)/AutoSci" \
  --out /tmp/autosci_parity_inventory_current.json
```

| Field | Status |
|---|---:|
| route_count | 28 |
| full_count | 0 |
| partial_count | 17 |
| gated_count | 11 |
| missing_route_count | 0 |
| manifest_registry_drift | none |
| route_capabilities_missing_from_registry | 0 |
| route_logical_operators_missing | 0 |
| route_physical_operator_binding_missing | 0 |
| route_evidence_schemas_missing | 0 |
| route_backend_actions_missing | 0 |
| route_gate_missing | 0 |

## Root-Aware Semantic Snapshot

This snapshot uses the detailed parity bridge with explicit native/evidence
roots. It is evidence recognition, not a route-config promotion.

| Field | Status |
|---|---:|
| full_count | 8 |
| partial_count | 7 |
| gated_count | 13 |
| semantic_full_count | 19 |
| semantic_partial_count | 9 |
| runtime_proof_pending | 0 |
| runtime_proof_verified | 22 |

## Native Reference Inspected

| Native file | Purpose | Result |
|---|---|---|
| `/Users/jamesyuan/Developer/Github Repos (On Git)/AutoSci/tools/research_wiki.py` | P1 OmegaWiki command surface | Native commands match OpenSolar command surface for init, slug, log, read/set metadata, graph/citation operations, context rebuilds, lifecycle transitions, stats/maturity, and checkpoints. |
| `/Users/jamesyuan/Developer/Github Repos (On Git)/AutoSci/i18n/en/skills/*/SKILL.md` | Native skill inventory | 28 native skills discovered; all have corresponding Solar routes. |

## Priority Matrix

| Priority | Native behavior | Solar status | Test path | Evidence schema | Gate | Remaining gap |
|---|---|---|---|---|---|---|
| P1 | OmegaWiki `init`, metadata, citations, dedup, transitions, context, checkpoints | implemented, route still partial/gated by higher-level model/write evidence | `harness/plugins/autosci/tests/test_research_wiki_native_parity_commands.py` | `research_memory_update.v1`, `research_graph_update.v1` | `memory_update_gate.py`, `graph_update_gate.py` | Route-level semantic full parity still needs audited route evidence and approved writeback proof where mutation is requested. |
| P1a | `/ingest` source preparation through final source registration | semantic full with Phase 19 audit loaded | `harness/plugins/autosci/tests/test_autosci_skill_shim.py -k 'ingest'` plus `codex-ingest-wiki-proof-20260630` evidence | `research_paper.v1`, `research_memory_update.v1`, `research_graph_update.v1` | `research_paper_gate.py`, `memory_update_gate.py`, `graph_update_gate.py` | Root-aware inventory reports `$ingest` full/E3/not_required when `semantic-audits-ingest-full` is loaded; static route config remains partial to avoid no-audit full inference. |
| P2 | `/ideate` full five-phase provider-backed novelty path | partial | `harness/plugins/autosci/tests/test_autosci_skill_shim.py -k 'ideate'` | `idea_candidate.v1`, `idea_evaluation.v1` | `idea_gate.py` | Source/model/Review LLM evidence, banlist/dedup proof, approved writeback gating, graph-edge projection, and pilot handoff/runtime evidence closure are covered; route still needs live provider-backed dual-model brainstorming and audited route promotion. |
| P3 | `/exp-run` deploy/collect/full local and remote-gated behavior | gated/partial | `harness/plugins/autosci/tests/test_autosci_skill_shim.py -k 'exp_run or exp_collect or exp_pilot_run'` plus env-gated live remote tests | `experiment_plan.v1`, `experiment_status.v1`, `experiment_result.v1` | `experiment_plan_gate.py`, `experiment_status_gate.py`, `experiment_result_gate.py` | `$exp-pilot-run` is now semantic full for approved pilot runtime execution without wiki mutation; `/exp-run` still needs real external SSH/provider execution and collection proof before full promotion. |
| P4 | `/paper-draft` full paper tree | partial | `harness/plugins/autosci/tests/test_autosci_skill_shim.py -k 'paper_draft or paper-draft or paper_compile or paper-compile'` | `scientific_report.v1` | `report_gate.py` | Local full tree, citation plan, section evidence map, Review LLM boundary, and compile handoff evidence are wired; route remains partial until real source/review/compile evidence is audited end to end and promotion policy is satisfied. |
| P5 | `/paper-compile` TeX/PDF/submission checks | gated | `harness/plugins/autosci/tests/test_autosci_skill_shim.py -k 'paper_compile'` | `publication_bundle.v1` | `publication_gate.py` | Compile diagnostics, approved TeX execution, pdflatex fallback, no-tool inconclusive behavior, PDF structural checks, submission profile, PDF inspection, submission audit boundaries, and a combined deterministic approved-runtime/PDF/submission-audit run are covered; route still needs live or accepted real-toolchain proof before full promotion. |
| P6 | `/poster` render path | gated | `harness/plugins/autosci/tests/test_autosci_skill_shim.py -k 'rebuttal or poster'` | `publication_bundle.v1` | `publication_gate.py` | HTML/DAG/report/validation generation, Review LLM critique boundary, render flag, approval contract, and approved PNG render executor are covered; route remains gated until accepted browser/render proof and publication audit are present end to end. |
| P7 | `/rebuttal` reviewer-thread/stress-test/submission audit | partial | `harness/plugins/autosci/tests/test_autosci_skill_shim.py -k 'rebuttal or poster'` | `publication_bundle.v1` | `publication_gate.py` | Reviewer-thread ingestion, raw comment atomization, evidence mapping, Review LLM stress boundary, formal export, submission audit boundary, and comma-separated review target parsing are covered; route remains partial until accepted Review LLM/provider and submission audit proof are present end to end. |
| P8 | Live provider and remote-host proofs | pending | `harness/plugins/autosci/tests/test_autosci_live_provider_env_gated.py`; full default module suite: 344 passed, 6 skipped | route-dependent | route-dependent | Opt-in live Review LLM, Semantic Scholar/novelty, remote status, remote launch, remote collect, and real TeX compile tests now exist and skip by default; no provider/remote/compile route is promoted to full until those tests are explicitly run with real credentials/endpoints/commands/tools and accepted through route policy. |

## Current Proof Status

| Proof area | Status | Reason |
|---|---|---|
| provider_live_proof_status | pending | Env-gated live provider tests now exist, but skipped default runs are not proof; route config alone is not live proof. |
| remote_experiment_proof_status | pending | Local/remote-helper proof hooks, approval boundaries, collection ledger, duplicate collection, multi-seed aggregation, and live-collection final audit boundaries are wired; full remote proof still needs an audited real external SSH/provider run and collection. |
| paper_compile_proof_status | pending | Paper compile now has audit-report coverage, focused runtime-boundary tests, and one combined deterministic approved-runtime/PDF/submission-audit run; full route proof still needs live or accepted real-toolchain evidence through promotion policy. |
| review_llm_proof_status | pending | Review LLM parity needs persisted model/review evidence; local surrogate output is not final acceptance. |

## Promotion Policy

No route was promoted in `feature_parity_routes.v1.json` during this slice. The lightweight Prompt B inventory still confirms `full_count=0`; the root-aware detailed bridge recognizes existing/current semantic audits and reports 19 semantic-full routes, but global full parity remains blocked by the remaining semantic-partial and approval/provider-gated routes.
