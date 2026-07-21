---
entity_type: "output"
entity_id: "lifecycle-summary-shim-research-experiment-runtime"
title: "Lifecycle summary for shim-research-experiment-runtime"
run_id: "shim-research-experiment-runtime"
source_evidence: "artifacts/autosci/runs/shim-research-experiment-runtime/scheduler_lifecycle/scientific_lifecycle_runtime.json"
managed_by: "solar-autosci-workspace-projector"
---
# Lifecycle Summary: `shim-research-experiment-runtime`

## Status

- Lifecycle status: `blocked`
- Workflow id: `scientific_research_lifecycle_full_v1`
- Job id: `shim-research-experiment-runtime-scheduler`
- Execution owner: `solar.operator_runtime.scheduler_lifecycle_smoke`
- Dispatch boundary: `bounded_smoke`
- Production ready: `False`
- Lifecycle gate: `inconclusive`
- Node count: `14`
- Blocked node count: `2`

## Evidence

- Skill run: `artifacts/autosci/runs/shim-research-experiment-runtime/autosci_skill_run.json`
- Lifecycle summary: `artifacts/autosci/runs/shim-research-experiment-runtime/scheduler_lifecycle/scientific_lifecycle_runtime.json`
- Runtime manifest: `N/A`

## Node Results

| Node | Node Status | Gate Status | Artifact |
| --- | --- | --- | --- |
| claim_extract | passed | passed | artifacts/scientific/scheduler-lifecycle-smoke/shim-research-experiment-runtime-scheduler/claim_extract/task-shim-research-experiment-runtime-scheduler-claim_extract/research_claims.json |
| claim_verify | passed | passed | artifacts/scientific/scheduler-lifecycle-smoke/shim-research-experiment-runtime-scheduler/claim_verify/task-shim-research-experiment-runtime-scheduler-claim_verify/claim_verdict.json |
| code_evidence_map | passed | passed | artifacts/scientific/scheduler-lifecycle-smoke/shim-research-experiment-runtime-scheduler/code_evidence_map/task-shim-research-experiment-runtime-scheduler-code_evidence_map/code_evidence_map.json |
| experiment_design | passed | passed | artifacts/scientific/scheduler-lifecycle-smoke/shim-research-experiment-runtime-scheduler/experiment_design/task-shim-research-experiment-runtime-scheduler-experiment_design/experiment_plan.json |
| experiment_monitor | passed | passed | artifacts/scientific/scheduler-lifecycle-smoke/shim-research-experiment-runtime-scheduler/experiment_monitor/task-shim-research-experiment-runtime-scheduler-experiment_monitor/experiment_status.json |
| experiment_run | passed | passed | artifacts/scientific/scheduler-lifecycle-smoke/shim-research-experiment-runtime-scheduler/experiment_run/task-shim-research-experiment-runtime-scheduler-experiment_run/experiment_result.json |
| graph_update | passed | passed | artifacts/scientific/scheduler-lifecycle-smoke/shim-research-experiment-runtime-scheduler/graph_update/task-shim-research-experiment-runtime-scheduler-graph_update/research_graph_update.json |
| idea_evaluate | passed | passed | artifacts/scientific/scheduler-lifecycle-smoke/shim-research-experiment-runtime-scheduler/idea_evaluate/task-shim-research-experiment-runtime-scheduler-idea_evaluate/idea_evaluation.json |
| idea_generate | passed | passed | artifacts/scientific/scheduler-lifecycle-smoke/shim-research-experiment-runtime-scheduler/idea_generate/task-shim-research-experiment-runtime-scheduler-idea_generate/idea_candidate.json |
| literature_discover | passed | passed | artifacts/scientific/scheduler-lifecycle-smoke/shim-research-experiment-runtime-scheduler/literature_discover/task-shim-research-experiment-runtime-scheduler-literature_discover/literature_discovery.json |
| memory_update_initial | passed | passed | artifacts/scientific/scheduler-lifecycle-smoke/shim-research-experiment-runtime-scheduler/memory_update_initial/task-shim-research-experiment-runtime-scheduler-memory_update_initial/research_memory_update.json |
| method_extract | passed | passed | artifacts/scientific/scheduler-lifecycle-smoke/shim-research-experiment-runtime-scheduler/method_extract/task-shim-research-experiment-runtime-scheduler-method_extract/research_method.json |
| paper_analyze | passed | passed | artifacts/scientific/scheduler-lifecycle-smoke/shim-research-experiment-runtime-scheduler/paper_analyze/task-shim-research-experiment-runtime-scheduler-paper_analyze/research_paper_analysis.json |
| paper_ingest | passed | passed | artifacts/scientific/scheduler-lifecycle-smoke/shim-research-experiment-runtime-scheduler/paper_ingest/task-shim-research-experiment-runtime-scheduler-paper_ingest/research_paper.json |

## Blocked Nodes

| Node | Reason | Required Evidence | Unblock Condition |
| --- | --- | --- | --- |
| publication_produce | Waiting for LaTeX/PDF compile evidence or approved compile runtime evidence. | publication_bundle.v1 with existing files and compile/PDF evidence | Provide a compile target with LaTeX/PDF artifacts or approved runtime evidence, then dispatch publication_produce. |
| report_plan | Waiting for completed Review LLM artifact_review.v1 evidence. | artifact_review.v1 with review_mode=review_llm and review_llm.status=completed | Provide completed Review LLM-backed artifact_review.v1 evidence, then dispatch report_plan. |

## Notes

- This page is projected from Solar-managed evidence; it is not the execution ledger.
- Missing provider, model, approval, or runtime evidence remains visible as blocked or inconclusive state.
