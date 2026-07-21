---
entity_type: "output"
entity_id: "lifecycle-summary-shim-research-generic-scheduler-authorization"
title: "Lifecycle summary for shim-research-generic-scheduler-authorization"
run_id: "shim-research-generic-scheduler-authorization"
source_evidence: "artifacts/scientific/workflow-runs/shim-research-generic-scheduler-authorization-scheduler/scientific_lifecycle_runtime.json"
managed_by: "solar-autosci-workspace-projector"
---
# Lifecycle Summary: `shim-research-generic-scheduler-authorization`

## Status

- Lifecycle status: `blocked`
- Workflow id: `scientific_research_lifecycle_full_v1`
- Job id: `shim-research-generic-scheduler-authorization-scheduler`
- Execution owner: `solar.operator_runtime.generic_scientific_workflow_runner`
- Dispatch boundary: `generic_workflow_runner`
- Production ready: `False`
- Lifecycle gate: `failed`
- Node count: `0`
- Blocked node count: `1`

## Evidence

- Skill run: `artifacts/autosci/runs/shim-research-generic-scheduler-authorization/autosci_skill_run.json`
- Lifecycle summary: `artifacts/scientific/workflow-runs/shim-research-generic-scheduler-authorization-scheduler/scientific_lifecycle_runtime.json`
- Runtime manifest: `artifacts/autosci/runs/shim-research-generic-scheduler-authorization/scheduler_lifecycle/scientific_workflow_runtime_manifest.json`

## Node Results

- N/A

## Blocked Nodes

| Node | Reason | Required Evidence | Unblock Condition |
| --- | --- | --- | --- |
| literature_discover | Waiting for supplied provider/runtime evidence or explicit approval. | provider/runtime evidence or upstream node artifact | Resume the workflow after supplying the missing evidence. |

## Notes

- This page is projected from Solar-managed evidence; it is not the execution ledger.
- Missing provider, model, approval, or runtime evidence remains visible as blocked or inconclusive state.
