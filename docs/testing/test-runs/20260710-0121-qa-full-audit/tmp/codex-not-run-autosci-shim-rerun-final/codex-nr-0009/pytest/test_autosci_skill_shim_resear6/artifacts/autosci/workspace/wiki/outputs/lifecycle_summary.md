---
entity_type: "output"
entity_id: "lifecycle-summary-shim-research-demo-scheduler"
title: "Lifecycle summary for shim-research-demo-scheduler"
run_id: "shim-research-demo-scheduler"
source_evidence: "artifacts/scientific/workflow-runs/shim-research-demo-scheduler-scheduler/scientific_lifecycle_runtime.json"
managed_by: "solar-autosci-workspace-projector"
---
# Lifecycle Summary: `shim-research-demo-scheduler`

## Status

- Lifecycle status: `passed`
- Workflow id: `scientific_research_lifecycle_full_v1`
- Job id: `shim-research-demo-scheduler-scheduler`
- Execution owner: `solar.operator_runtime.generic_scientific_workflow_runner`
- Dispatch boundary: `generic_workflow_runner`
- Production ready: `True`
- Lifecycle gate: `passed`
- Node count: `4`
- Blocked node count: `0`

## Evidence

- Skill run: `artifacts/autosci/runs/shim-research-demo-scheduler/autosci_skill_run.json`
- Lifecycle summary: `artifacts/scientific/workflow-runs/shim-research-demo-scheduler-scheduler/scientific_lifecycle_runtime.json`
- Runtime manifest: `artifacts/autosci/runs/shim-research-demo-scheduler/scheduler_lifecycle/scientific_workflow_runtime_manifest.json`

## Node Results

| Node | Node Status | Gate Status | Artifact |
| --- | --- | --- | --- |
| claim_extract | passed | passed | artifacts/autosci/runs/shim-research-demo-scheduler/scheduler_lifecycle/claim_extract/task-shim-research-demo-scheduler-scheduler-claim_extract/research_claims.json |
| method_extract | passed | passed | artifacts/autosci/runs/shim-research-demo-scheduler/scheduler_lifecycle/method_extract/task-shim-research-demo-scheduler-scheduler-method_extract/research_method.json |
| paper_analyze | passed | passed | artifacts/autosci/runs/shim-research-demo-scheduler/scheduler_lifecycle/paper_analyze/task-shim-research-demo-scheduler-scheduler-paper_analyze/research_paper_analysis.json |
| paper_ingest | passed | passed | artifacts/autosci/runs/shim-research-demo-scheduler/scheduler_lifecycle/paper_ingest/task-shim-research-demo-scheduler-scheduler-paper_ingest/research_paper.json |

## Blocked Nodes

- N/A

## Notes

- This page is projected from Solar-managed evidence; it is not the execution ledger.
- Missing provider, model, approval, or runtime evidence remains visible as blocked or inconclusive state.
