# AutoSci Phase 7 Progress Log

Logged: 2026-06-17 17:18:54 EDT
Branch: `feature/autosci-solar-native`

## Scope

Phase 7 encoded AutoSci-derived research flows as Solar-native TaskGraph
templates. Each workflow is expressed as explicit `Scientific*` logical operator
nodes with Solar Evidence ABI expectations, dependency edges, read/write scopes,
gates, and architecture policy boundaries.

This phase does not change scheduler behavior, product logic, report logic,
fallback behavior, scoring, routing, quota, leases, model selection, or evaluator
gate implementation.

## Files Changed

| Artifact group | Count | Operation | Commit | Paths |
|---|---:|---|---|---|
| Scientific TaskGraph templates | 7 | Added | this phase commit | `harness/workflows/scientific_*.json` |
| Phase log | 1 | Added | this phase commit | `docs/integrations/autosci/phase7-progress-log.md` |

## Workflow Templates

| Workflow | Nodes | Purpose |
|---|---:|---|
| `scientific_paper_ingestion_v1.json` | 3 | Paper ingestion, paper analysis, and lightweight evidence gate. |
| `scientific_claim_extraction_v1.json` | 3 | Paper ingestion, claim extraction, and lightweight verification. |
| `scientific_claim_verification_v1.json` | 8 | Paper-to-claim-verdict path with method, code, experiment, and report steps. |
| `scientific_experiment_lifecycle_v1.json` | 7 | Idea, experiment design, approval gate, bounded run, monitor, and claim verdict. |
| `scientific_publication_lifecycle_v1.json` | 5 | Report planning, drafting, report gate, publication bundle, and approved memory update. |
| `scientific_research_lifecycle_full_v1.json` | 19 | Full native scientific lifecycle from literature discovery through workflow evolution. |
| `scientific_research_resume_v1.json` | 8 | Resume path from existing evidence without rerunning the full lifecycle. |

## Required Shape Coverage

| Plan shape | Status | Notes |
|---|---|---|
| `ScientificPaperIngestor -> ScientificClaimExtractor -> VerifierLite` | ok | Implemented by `scientific_claim_extraction_v1.json`. |
| Claim verification chain through `ScientificReportDrafter` | ok | Implemented by `scientific_claim_verification_v1.json` with 8 ordered nodes. |
| Full research lifecycle through `ScientificWorkflowEvolver` | ok | Implemented by `scientific_research_lifecycle_full_v1.json` with 19 ordered nodes, including the final memory update. |

## Node Contract

Each workflow node includes:

- `id`
- `goal`
- `logical_operator`
- `required_capabilities`
- `read_scope`
- `write_scope`
- `gate`
- `acceptance`
- `pass_conditions`
- `depends_on`
- `architecture_policy`

Experiment run and monitor nodes also include bounded execution policy and human
approval gates for non-fixture execution.

## Checks Run

| Check | Status | Note |
|---|---|---|
| Solar context injection | ok with warning | Used repo-local `HARNESS_DIR=<OpenSolar>/harness bash solar-harness.sh context inject`; Mirage source was degraded. |
| JSON parse for all scientific workflows | ok | `python3 -m json.tool workflows/scientific_*.json` passed. |
| Plan human JSON parse | ok | `python3 -m json.tool workflows/scientific_claim_verification_v1.json >/tmp/scientific_claim_verification_v1.valid.json` passed. |
| Claim verification architecture guard | ok | `python3 lib/architecture_guard.py validate --graph workflows/scientific_claim_verification_v1.json --strict` returned `ok: true`. |
| Full lifecycle architecture guard | ok | `python3 lib/architecture_guard.py validate --graph workflows/scientific_research_lifecycle_full_v1.json --strict` returned `ok: true`. |
| Scheduler validation | ok | `python3 lib/graph_scheduler.py validate --graph <workflow>` returned `ok: true` for all 7 workflows. |
| TaskGraph schema validation | ok | Existing repo `.venv/bin/python` with `jsonschema` validated all 7 workflow files against `schemas/task-graph.schema.json`. |
| Required minimum shapes | ok | Script verified the three plan-defined operator chains exactly. |
| Node field checklist | ok | Script verified every node has logical operator, required capabilities, read/write scope, gate, and explicit dependencies. |
| Black-box workflow guard | ok | Script verified no node uses `AutoSciRunner` or a full-workflow command; nodes carry explicit forbidden-policy markers for hidden full workflows. |
| Experiment safety | ok | Script verified experiment runner and monitor nodes require bounded mode or human approval. |

## Notes

- Workflow templates use Solar-native logical operators and Evidence ABI schema
  names; they do not require reading AutoSci internals.
- `architecture_policy.package_boundary` is present on every node so strict
  architecture guard validation can confirm package/plugin boundaries.
- `VerifierLite` is used only as a Solar gate node for lightweight evidence
  checks, not as a scientific truth verifier.
- Existing unrelated dirty files were left untouched.

## Done State

Phase 7 is complete when a human can inspect the TaskGraph templates and see the
scientific workflow, dependencies, gates, evidence expectations, and approval
boundaries without invoking a single AutoSci-owned full workflow runner.
