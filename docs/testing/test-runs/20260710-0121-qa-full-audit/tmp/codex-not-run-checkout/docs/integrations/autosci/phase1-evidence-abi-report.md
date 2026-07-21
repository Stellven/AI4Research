# AutoSci Phase 1 Evidence ABI Completion Report

Logged: 2026-06-16 16:39:17 EDT
Updated: 2026-06-17 14:53:26 EDT
Branch: `feature/autosci-solar-native`

## Scope

Phase 1 created Solar-native scientific Evidence ABI schemas and fixture
artifacts only. No runtime binding, plugin adapter, logical operator registry,
physical operator registry, capsule registry, or TaskGraph workflow behavior was
changed in this phase.

## Files Added

| Artifact group | Count | Paths |
|---|---:|---|
| Evidence ABI schemas | 16 | `harness/schemas/evidence/*.schema.json` |
| Passing fixtures | 16 | `harness/schemas/evidence/fixtures/sample_*.json` |
| Failed-state fixtures | 4 | `harness/schemas/evidence/fixtures/sample_failed_*.json` |
| Inconclusive-state fixtures | 4 | `harness/schemas/evidence/fixtures/sample_inconclusive_*.json` |
| Completion report | 1 | `docs/integrations/autosci/phase1-evidence-abi-report.md` |

## Commit Coverage

| Commit | Scope | Note |
|---|---|---|
| `72fa1178` | Initial Evidence ABI schemas and passing fixtures | Added 16 Solar-native scientific Evidence ABI schema files, 16 matching passing fixtures, and the initial completion report. |
| `9cd32b79` | Claim verdict wording correction | Aligned claim verdict evidence labels without changing runtime behavior or schema ownership. |
| `894ea941` | Failed and inconclusive fixtures | Added 4 failed fixtures and 4 inconclusive fixtures for `research_paper.v1`, `research_claims.v1`, `experiment_plan.v1`, and `claim_verdict.v1`. |
| `275a8b63` | Validation dependency availability | Recorded the global `jsonschema==4.26.0` CLI install used for human-testable schema validation outside the project venv. |

## Schema Coverage

| Schema | Fixture | Solar-native owner |
|---|---|---|
| `research_paper.v1` | `sample_research_paper.v1.json` | `ScientificPaperIngestor` / `ScientificPaperAnalyzer` |
| `literature_discovery.v1` | `sample_literature_discovery.v1.json` | `ScientificLiteratureDiscoverer` |
| `research_memory_update.v1` | `sample_research_memory_update.v1.json` | `ScientificMemoryUpdater` |
| `research_graph_update.v1` | `sample_research_graph_update.v1.json` | `ScientificGraphUpdater` |
| `research_claims.v1` | `sample_research_claims.v1.json` | `ScientificClaimExtractor` |
| `research_method.v1` | `sample_research_method.v1.json` | `ScientificMethodExtractor` |
| `code_evidence_map.v1` | `sample_code_evidence_map.v1.json` | `ScientificCodeEvidenceMapper` |
| `idea_candidate.v1` | `sample_idea_candidate.v1.json` | `ScientificIdeaGenerator` |
| `idea_evaluation.v1` | `sample_idea_evaluation.v1.json` | `ScientificIdeaEvaluator` |
| `experiment_plan.v1` | `sample_experiment_plan.v1.json` | `ScientificExperimentDesigner` |
| `experiment_status.v1` | `sample_experiment_status.v1.json` | `ScientificExperimentMonitor` |
| `experiment_result.v1` | `sample_experiment_result.v1.json` | `ScientificExperimentRunner` |
| `claim_verdict.v1` | `sample_claim_verdict.v1.json` | `ScientificClaimVerifier` |
| `scientific_report.v1` | `sample_scientific_report.v1.json` | `ScientificReportPlanner` / `ScientificReportDrafter` |
| `publication_bundle.v1` | `sample_publication_bundle.v1.json` | `ScientificPublicationProducer` |
| `workflow_evolution.v1` | `sample_workflow_evolution.v1.json` | `ScientificWorkflowEvolver` |

Additional failed/inconclusive fixtures cover the Phase 1 core schemas:

| Schema | Failed fixture | Inconclusive fixture |
|---|---|---|
| `research_paper.v1` | `sample_failed_research_paper.v1.json` | `sample_inconclusive_research_paper.v1.json` |
| `research_claims.v1` | `sample_failed_research_claims.v1.json` | `sample_inconclusive_research_claims.v1.json` |
| `experiment_plan.v1` | `sample_failed_experiment_plan.v1.json` | `sample_inconclusive_experiment_plan.v1.json` |
| `claim_verdict.v1` | `sample_failed_claim_verdict.v1.json` | `sample_inconclusive_claim_verdict.v1.json` |

## ABI Envelope

Every schema requires:

```text
schema
task_id
sprint_id
node_id
status: completed | failed | inconclusive
inputs
outputs
artifacts[]
provenance.operator_id
provenance.implementation_package
provenance.timestamp
limitations[]
```

Every artifact entry requires:

```text
type
path
sha256 optional in Phase 1
```

## Checks Run

| Check | Command | Status | Note |
|---|---|---|---|
| JSON parse for all schemas and fixtures | `python -m json.tool schemas/evidence/*.schema.json schemas/evidence/fixtures/*.json` equivalent loop | ok | All 32 JSON files parsed cleanly. |
| One-to-one fixture validation | `jsonschema.Draft202012Validator` over every `*.schema.json` and matching `sample_*.json` | ok | 16 schemas validated against 16 fixtures. |
| Plan core pretty-print | `python -m json.tool schemas/evidence/fixtures/sample_research_claims.v1.json` | ok | Wrote `/tmp/sample_research_claims.pretty.json`. |
| Plan core pretty-print | `python -m json.tool schemas/evidence/fixtures/sample_claim_verdict.v1.json` | ok | Wrote `/tmp/sample_claim_verdict.pretty.json`. |
| Plan core schema validation | `python -m jsonschema schemas/evidence/research_claims.v1.schema.json -i schemas/evidence/fixtures/sample_research_claims.v1.json` | ok | CLI emitted only deprecation warning. |
| Plan core schema validation | `python -m jsonschema schemas/evidence/claim_verdict.v1.schema.json -i schemas/evidence/fixtures/sample_claim_verdict.v1.json` | ok | CLI emitted only deprecation warning. |
| Failed/inconclusive fixture validation | `jsonschema.Draft202012Validator` using each fixture's `schema` field | ok | 8 additional failed/inconclusive fixtures validated. |

## Human Test Plan

```text
[ ] Confirm schemas use generic scientific names, not AutoSci-only names.
[ ] Confirm every schema can represent completed, failed, and inconclusive states.
[ ] Confirm every schema records task, sprint, node, artifact, and provenance fields.
[ ] Confirm fixtures are inspectable without reading AutoSci internals.
[ ] Confirm claim extraction fixtures do not mark claims verified at extraction time.
[ ] Confirm experiment and verdict fixtures keep execution result separate from claim verdict.
```

## Open Questions

| Question | Phase impact | Current assumption |
|---|---|---|
| Should `sha256` become required once artifact hashing lands? | Later schema revision | Optional for Phase 1, as requested by plan. |
| Should `ScientificKnowledgeQuerier` get a dedicated evidence ABI? | Later capability design | Phase 0 maps read-only `/ask` to `scientific_report.v1`; crystallized writeback uses `research_memory_update.v1`. |
| Should lifecycle evidence ledger become a separate ABI? | Later TaskGraph phase | Phase 1 covers major stage artifacts; full lifecycle templates remain future work. |

## Done State

Phase 1 is complete when a reviewer can inspect the fixture for each Evidence
ABI and understand what each Solar-native scientific workflow node promises to
emit before any AutoSci backend adapter exists.
