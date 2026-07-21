---
entity_type: "output"
entity_id: "lifecycle-summary-shim-research-human-gate"
title: "Lifecycle summary for shim-research-human-gate"
run_id: "shim-research-human-gate"
source_evidence: "artifacts/autosci/runs/shim-research-human-gate/scheduler_lifecycle/scientific_lifecycle_runtime.json"
managed_by: "solar-autosci-workspace-projector"
---
# Lifecycle Summary: `shim-research-human-gate`

## Status

- Lifecycle status: `blocked`
- Workflow id: `scientific_research_lifecycle_full_v1`
- Job id: `shim-research-human-gate-scheduler`
- Execution owner: `solar.operator_runtime.scheduler_lifecycle_smoke`
- Dispatch boundary: `bounded_smoke`
- Production ready: `False`
- Lifecycle gate: `inconclusive`
- Node count: `15`
- Blocked node count: `1`

## Evidence

- Skill run: `artifacts/autosci/runs/shim-research-human-gate/autosci_skill_run.json`
- Lifecycle summary: `artifacts/autosci/runs/shim-research-human-gate/scheduler_lifecycle/scientific_lifecycle_runtime.json`
- Runtime manifest: `N/A`

## Node Results

| Node | Node Status | Gate Status | Artifact |
| --- | --- | --- | --- |
| claim_extract | passed | passed | artifacts/scientific/scheduler-lifecycle-smoke/shim-research-human-gate-scheduler/claim_extract/task-shim-research-human-gate-scheduler-claim_extract/research_claims.json |
| claim_verify | passed | passed | artifacts/scientific/scheduler-lifecycle-smoke/shim-research-human-gate-scheduler/claim_verify/task-shim-research-human-gate-scheduler-claim_verify/claim_verdict.json |
| code_evidence_map | passed | passed | artifacts/scientific/scheduler-lifecycle-smoke/shim-research-human-gate-scheduler/code_evidence_map/task-shim-research-human-gate-scheduler-code_evidence_map/code_evidence_map.json |
| experiment_design | passed | passed | artifacts/scientific/scheduler-lifecycle-smoke/shim-research-human-gate-scheduler/experiment_design/task-shim-research-human-gate-scheduler-experiment_design/experiment_plan.json |
| experiment_monitor | passed | passed | artifacts/scientific/scheduler-lifecycle-smoke/shim-research-human-gate-scheduler/experiment_monitor/task-shim-research-human-gate-scheduler-experiment_monitor/experiment_status.json |
| experiment_run | passed | passed | artifacts/scientific/scheduler-lifecycle-smoke/shim-research-human-gate-scheduler/experiment_run/task-shim-research-human-gate-scheduler-experiment_run/experiment_result.json |
| graph_update | passed | passed | artifacts/scientific/scheduler-lifecycle-smoke/shim-research-human-gate-scheduler/graph_update/task-shim-research-human-gate-scheduler-graph_update/research_graph_update.json |
| idea_acceptance_gate | passed | passed | artifacts/scientific/scheduler-lifecycle-smoke/shim-research-human-gate-scheduler/idea_acceptance_gate/idea_acceptance_gate.json |
| idea_evaluate | passed | passed | artifacts/scientific/scheduler-lifecycle-smoke/shim-research-human-gate-scheduler/idea_evaluate/task-shim-research-human-gate-scheduler-idea_evaluate/idea_evaluation.json |
| idea_generate | passed | passed | artifacts/scientific/scheduler-lifecycle-smoke/shim-research-human-gate-scheduler/idea_generate/task-shim-research-human-gate-scheduler-idea_generate/idea_candidate.json |
| literature_discover | passed | passed | artifacts/scientific/scheduler-lifecycle-smoke/shim-research-human-gate-scheduler/literature_discover/task-shim-research-human-gate-scheduler-literature_discover/literature_discovery.json |
| memory_update_initial | passed | passed | artifacts/scientific/scheduler-lifecycle-smoke/shim-research-human-gate-scheduler/memory_update_initial/task-shim-research-human-gate-scheduler-memory_update_initial/research_memory_update.json |
| method_extract | passed | passed | artifacts/scientific/scheduler-lifecycle-smoke/shim-research-human-gate-scheduler/method_extract/task-shim-research-human-gate-scheduler-method_extract/research_method.json |
| paper_analyze | passed | passed | artifacts/scientific/scheduler-lifecycle-smoke/shim-research-human-gate-scheduler/paper_analyze/task-shim-research-human-gate-scheduler-paper_analyze/research_paper_analysis.json |
| paper_ingest | passed | passed | artifacts/scientific/scheduler-lifecycle-smoke/shim-research-human-gate-scheduler/paper_ingest/task-shim-research-human-gate-scheduler-paper_ingest/research_paper.json |

## Blocked Nodes

| Node | Reason | Required Evidence | Unblock Condition |
| --- | --- | --- | --- |
| results_acceptance_gate | Waiting for durable human approval of experiment results before publication planning. | Human approval evidence for accepted/rejected experiment verdict | Provide --results-approval-ref or resume with recorded results approval evidence. |

## Notes

- This page is projected from Solar-managed evidence; it is not the execution ledger.
- Missing provider, model, approval, or runtime evidence remains visible as blocked or inconclusive state.
