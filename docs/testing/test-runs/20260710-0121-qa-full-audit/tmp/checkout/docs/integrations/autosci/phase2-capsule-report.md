# AutoSci Phase 2 Capability Capsule Completion Report

Logged: 2026-06-17 10:57:28 EDT
Updated: 2026-06-17 14:53:26 EDT
Branch: `feature/autosci-solar-native`

## Scope

Phase 2 created Solar-native declarative capability capsules for the research
workflow semantics discovered in Phase 0 and typed by the Phase 1 Evidence ABI
schemas. This phase did not add logical operators, physical operators, workflow
templates, evaluators, or AutoSci backend code.

## Files Added Or Modified

| Path group | Operation | Count | Note |
|---|---|---:|---|
| `harness/capability-capsules/cap.research-*.yaml` | Added | 18 | Declarative research capability capsules. |
| `harness/config/capability-capsules.registry.yaml` | Modified | 1 | Registered 18 draft research capsules. |
| `docs/integrations/autosci/phase2-capsule-report.md` | Added | 1 | Phase 2 completion report and human test plan. |

## Commit Coverage

| Commit | Scope | Note |
|---|---|---|
| `4bb21ee0` | Initial capability capsules | Added 18 declarative `cap.scientific-*` capsule manifests and registry entries as the first Phase 2 capsule pass. |
| `3ff701db` | Research-token rename | Renamed capsules and registry entries from `cap.scientific-*` to `cap.research-*` so capability ids describe research work rather than the science domain label. |

## Capsule Coverage

| Capsule | Primary operator target | Evidence ABI |
|---|---|---|
| `cap.research-paper-ingest` | `ScientificPaperIngestor` | `research_paper.v1` |
| `cap.research-literature-discover` | `ScientificLiteratureDiscoverer` | `literature_discovery.v1` |
| `cap.research-memory-update` | `ScientificMemoryUpdater` | `research_memory_update.v1` |
| `cap.research-graph-update` | `ScientificGraphUpdater` | `research_graph_update.v1` |
| `cap.research-paper-analyze` | `ScientificPaperAnalyzer` | `research_paper.v1` |
| `cap.research-claim-extract` | `ScientificClaimExtractor` | `research_claims.v1` |
| `cap.research-method-extract` | `ScientificMethodExtractor` | `research_method.v1` |
| `cap.research-code-evidence-map` | `ScientificCodeEvidenceMapper` | `code_evidence_map.v1` |
| `cap.research-idea-generate` | `ScientificIdeaGenerator` | `idea_candidate.v1` |
| `cap.research-idea-evaluate` | `ScientificIdeaEvaluator` | `idea_evaluation.v1` |
| `cap.research-experiment-design` | `ScientificExperimentDesigner` | `experiment_plan.v1` |
| `cap.research-experiment-run` | `ScientificExperimentRunner` | `experiment_result.v1`, `experiment_status.v1` |
| `cap.research-experiment-monitor` | `ScientificExperimentMonitor` | `experiment_status.v1` |
| `cap.research-claim-verify` | `ScientificClaimVerifier` | `claim_verdict.v1` |
| `cap.research-report-plan` | `ScientificReportPlanner` | `scientific_report.v1` |
| `cap.research-report-draft` | `ScientificReportDrafter` | `scientific_report.v1` |
| `cap.research-publication-produce` | `ScientificPublicationProducer` | `publication_bundle.v1` |
| `cap.research-workflow-evolve` | `ScientificWorkflowEvolver` | `workflow_evolution.v1` |

## Architectural Boundary

The capsule files use generic research capability ids and declare AutoSci only as an
optional backend skill/effect path. No capsule is named `cap.autosci-*`, and no
capsule delegates the full workflow to a single AutoSci runner.

```text
TaskGraph node
  -> logical operator
  -> cap.research-*
  -> physical operator
  -> optional AutoSci backend adapter
  -> Evidence ABI
  -> gate or human-verifiable test
```

## Checks Run

| Check | Status | Note |
|---|---|---|
| YAML parse | ok | Parsed registry and all 18 capsule YAML files with PyYAML. |
| Capsule schema and semantic validation | ok | `validate_capability_capsule` passed for all 18 `cap.research-*` manifests. |
| Registry resolution | ok | `iter_registry_entries(include_draft=True)` found 18 research capsules and loaded each manifest. |
| Phase 2 required-capsule human test | ok | Required sample ids were present in `config/capability-capsules.registry.yaml`. |
| Research-token rename check | ok | Phase 2 capsule report and registry use `cap.research-*`; no `cap.scientific-*` capsule ids remain as the active contract. |

## Human Test Plan

Run from the OpenSolar repo root:

```bash
HARNESS_DIR="$PWD/harness" PYTHONPATH=harness/tools .venv/bin/python - <<'PY'
from pathlib import Path
from capability_capsules import iter_registry_entries, load_capability_capsule_manifest

entries = [e for e in iter_registry_entries(include_draft=True) if e.capability_capsule_id.startswith("cap.research-")]
assert len(entries) == 18, len(entries)
for entry in entries:
    manifest = load_capability_capsule_manifest(Path(entry.manifest_path))
    print(entry.capability_capsule_id, "->", manifest["operator_compatibility"]["preferred"])
PY
```

Manual checklist:

```text
[ ] Capsules are declarative and contract-focused.
[ ] Inputs and outputs reference Evidence ABI schemas.
[ ] Effects declare read, write, execute, network, cost, and risk boundaries.
[ ] Verification includes concrete pass conditions.
[ ] AutoSci is an optional backend binding, not the capability meaning.
[ ] No `AutoSciRunner` capsule or workflow owner was introduced.
```

## Open Questions

| Question | Current handling |
|---|---|
| Should these draft capsules be promoted to stable? | Leave as `draft` until logical operators, physical operators, and evaluator gates exist. |
| Should `cap.research-knowledge-query` be added for `/ask` answer-only mode? | Not in Phase 2 deliverables; Phase 0 maps `/ask` support behavior to `scientific_report.v1` and crystallized writeback to memory update. |
| Should capsule registry entries use research default operator profiles? | Deferred to Phase 3 logical operators and later physical operator binding. |

## Done State

Phase 2 is complete when a human can inspect all 18 capsule manifests, see the
Evidence ABI contracts they govern, and verify that AutoSci remains a backend
binding rather than the owner of the research workflow.
