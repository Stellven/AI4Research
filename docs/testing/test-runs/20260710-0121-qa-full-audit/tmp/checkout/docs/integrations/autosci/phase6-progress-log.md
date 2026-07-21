# AutoSci Phase 6 Progress Log

Logged: 2026-06-17 15:28:45 EDT
Updated: 2026-06-17 17:18:52 EDT
Branch: `feature/autosci-solar-native`

## Scope

Phase 6 added procedural manuals and dispatch templates for native Solar
scientific operators. Hard contracts still live in capability capsules, Evidence
ABI schemas, logical operators, physical operators, and later evaluator gates.

This phase does not change product logic, scheduler behavior, report logic,
fallback behavior, scoring, routing, quota, leases, or model selection.

## Files Changed

| Artifact group | Count | Operation | Commit | Paths |
|---|---:|---|---|---|
| Scientific personas/manuals | 9 | Added | this phase commit | `harness/personas/scientific-*.md` |
| Dispatch templates | 11 | Added/updated | this phase commit + follow-up wiring | `harness/templates/dispatch/scientific-*.dispatch.md` |
| Physical operator registry wiring | 1 | Updated | follow-up wiring | `harness/config/physical-operators.json` |
| Phase log | 1 | Added/updated | this phase commit + follow-up wiring | `docs/integrations/autosci/phase6-progress-log.md` |

## Manual Coverage

| Manual | Logical operators covered | Evidence ABI references |
|---|---|---|
| `scientific-paper-ingestor.md` | `ScientificPaperIngestor`, `ScientificPaperAnalyzer` | `research_paper.v1` |
| `scientific-literature-discoverer.md` | `ScientificLiteratureDiscoverer` | `literature_discovery.v1` |
| `scientific-memory-updater.md` | `ScientificMemoryUpdater`, `ScientificGraphUpdater`, `ScientificWorkflowEvolver` | `research_memory_update.v1`, `research_graph_update.v1`, `workflow_evolution.v1` |
| `scientific-claim-extractor.md` | `ScientificClaimExtractor`, `ScientificMethodExtractor` | `research_claims.v1`, `research_method.v1` |
| `scientific-code-evidence-mapper.md` | `ScientificCodeEvidenceMapper` | `code_evidence_map.v1` |
| `scientific-experiment-designer.md` | `ScientificIdeaGenerator`, `ScientificIdeaEvaluator`, `ScientificExperimentDesigner` | `idea_candidate.v1`, `idea_evaluation.v1`, `experiment_plan.v1` |
| `scientific-experiment-runner.md` | `ScientificExperimentRunner`, `ScientificExperimentMonitor` | `experiment_result.v1`, `experiment_status.v1` |
| `scientific-claim-verifier.md` | `ScientificClaimVerifier` | `claim_verdict.v1` |
| `scientific-report-writer.md` | `ScientificReportPlanner`, `ScientificReportDrafter`, `ScientificPublicationProducer` | `scientific_report.v1`, `publication_bundle.v1` |

## Dispatch Templates

| Template | Primary output | Guardrail |
|---|---|---|
| `scientific-paper-ingest.dispatch.md` | `research_paper.v1` | No verification or memory mutation. |
| `scientific-claim-extract.dispatch.md` | `research_claims.v1` | No truth verdicts. |
| `scientific-code-evidence-map.dispatch.md` | `code_evidence_map.v1` | No experiment execution. |
| `scientific-experiment-design.dispatch.md` | `experiment_plan.v1` | No experiment run during design. |
| `scientific-experiment-run.dispatch.md` | `experiment_result.v1` | Run only approved commands. |
| `scientific-claim-verify.dispatch.md` | `claim_verdict.v1` | Use only supplied evidence ids. |
| `scientific-report-write.dispatch.md` | `scientific_report.v1` | No fabricated citations or hidden verification. |
| `scientific-literature-discover.dispatch.md` | `literature_discovery.v1` | Search only approved channels. |
| `scientific-memory-update.dispatch.md` | `research_memory_update.v1` | No intuition-based memory writes. |
| `scientific-graph-update.dispatch.md` | `research_graph_update.v1` | No unapproved broad graph rewrites. |
| `scientific-workflow-evolve.dispatch.md` | `workflow_evolution.v1` | No silent scheduler, routing, quota, lease, scoring, or model-selection changes. |

## AutoSci Operator Wiring

| AutoSci operator | Manual | Dispatch | Registry binding |
|---|---|---|---|
| `autosci-paper-ingest-worker` | `scientific-paper-ingestor.md` | `scientific-paper-ingest.dispatch.md` | ok |
| `autosci-claim-extract-worker` | `scientific-claim-extractor.md` | `scientific-claim-extract.dispatch.md` | ok |
| `autosci-memory-update-worker` | `scientific-memory-updater.md` | `scientific-memory-update.dispatch.md` | ok; operator remains disabled until backend action is implemented |
| `autosci-idea-worker` | `scientific-experiment-designer.md` | `scientific-experiment-design.dispatch.md` | ok; operator remains disabled until backend action is implemented |
| `autosci-experiment-design-worker` | `scientific-experiment-designer.md` | `scientific-experiment-design.dispatch.md` | ok |
| `autosci-experiment-run-worker` | `scientific-experiment-runner.md` | `scientific-experiment-run.dispatch.md` | ok |
| `autosci-claim-verify-worker` | `scientific-claim-verifier.md` | `scientific-claim-verify.dispatch.md` | ok |
| `autosci-report-worker` | `scientific-report-writer.md` | `scientific-report-write.dispatch.md` | ok |

## Checks Run

| Check | Status | Note |
|---|---|---|
| Solar context injection | ok with warning | Used repo-local `HARNESS_DIR=<OpenSolar>/harness bash solar-harness.sh context inject`; Mirage source was degraded. |
| Required file presence | ok | Script verified all 9 manuals and 7 templates exist. |
| Required manual headings | ok | Script verified every manual has Role, Inputs, Outputs, Allowed actions, Forbidden actions, Required evidence, Failure handling, When to ask for human approval, and Completion checklist. |
| Evidence ABI grep | ok | `grep -R "research_claims.v1\|experiment_plan.v1\|claim_verdict.v1" personas templates/dispatch` returned matching manual and template lines. |
| Forbidden-action grep | ok | `grep -R "Do not\|must not\|forbidden\|Forbidden" personas templates/dispatch` returned forbidden-action guardrails across manuals and templates. |
| Scientific operator coverage | ok | Script verified all 18 `Scientific*` logical operators from Phase 3 are named in manuals/templates. |
| Failure and approval behavior | ok | Script verified manuals and templates document failure/inconclusive behavior and approval gates. |
| AutoSci-only assumption guard | ok | Script verified manuals/templates contain no positive AutoSci-only backend assumption. |

## Follow-up Wiring Checks

| Check | Status | Note |
|---|---|---|
| Missing dispatch templates | ok | Added dispatch templates for literature discovery, memory update, graph update, and workflow evolution. |
| AutoSci persona bindings | ok | All 8 `autosci-*` physical operators resolve to a `scientific-*` persona file. |
| AutoSci dispatch template bindings | ok | All 8 `autosci-*` physical operators declare an existing `templates/dispatch/scientific-*.dispatch.md` path. |
| Scientific operator dispatch coverage | ok | All 18 `Scientific*` logical operator types are named in dispatch templates. |
| Full physical registry schema validation | warn | Existing non-AutoSci registry entries still fail schema validation (`mini-glm51-*` missing `billing_surface`; `mini-reasonix-deepseek-v4-builder` uses `AdvisoryReview`). |

## Follow-up Tweaks and Fixes

| Item | Status | Fix |
|---|---|---|
| Dispatch template gaps | ok | Added the missing scientific dispatch templates for literature discovery, memory update, graph update, and workflow evolution so every `Scientific*` logical operator has template coverage. |
| Generic AutoSci personas | ok | Replaced generic `builder`, `planner`, and `evaluator` persona bindings on `autosci-*` physical operators with the appropriate `scientific-*` personas. |
| Missing registry template binding | ok | Added `dispatch_template` metadata to every `autosci-*` physical operator so scheduler/runtime follow-up work has an explicit template path to consume. |
| Disabled placeholder operators | ok | Kept `autosci-memory-update-worker` and `autosci-idea-worker` disabled because their backend bridge actions are intentionally not implemented yet; the fix only added guidance bindings. |
| Non-AutoSci schema warnings | noted | Left existing non-AutoSci physical registry schema warnings out of scope for this Phase 6 AutoSci wiring fix. |

## Notes

- Manuals intentionally describe procedures and failure behavior; they do not
  replace schemas, capsules, gates, or runtime policy.
- Some manuals cover adjacent logical operators so all Phase 3 scientific
  operators have guidance without creating redundant files.
- Existing unrelated dirty files were left untouched.

## Done State

Phase 6 is complete when a coding agent or worker can read a scientific manual
or dispatch template and know what artifacts to produce, what not to do, when to
ask for human approval, and what counts as a complete Evidence ABI handoff.
