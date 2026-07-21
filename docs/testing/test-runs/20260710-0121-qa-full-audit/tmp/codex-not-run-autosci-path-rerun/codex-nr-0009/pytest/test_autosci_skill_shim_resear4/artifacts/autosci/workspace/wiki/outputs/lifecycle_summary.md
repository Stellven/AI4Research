---
entity_type: "output"
entity_id: "lifecycle-summary-shim-research-generic-scheduler-run"
title: "Lifecycle summary for shim-research-generic-scheduler-run"
run_id: "shim-research-generic-scheduler-run"
source_evidence: "artifacts/scientific/workflow-runs/shim-research-generic-scheduler-run-scheduler/scientific_lifecycle_runtime.json"
managed_by: "solar-autosci-workspace-projector"
---
# Lifecycle Summary: `shim-research-generic-scheduler-run`

## Status

- Lifecycle status: `passed`
- Workflow id: `scientific_research_lifecycle_full_v1`
- Job id: `shim-research-generic-scheduler-run-scheduler`
- Execution owner: `solar.operator_runtime.generic_scientific_workflow_runner`
- Dispatch boundary: `generic_workflow_runner`
- Production ready: `True`
- Lifecycle gate: `passed`
- Node count: `1`
- Blocked node count: `0`

## Evidence

- Skill run: `artifacts/autosci/runs/shim-research-generic-scheduler-run/autosci_skill_run.json`
- Lifecycle summary: `artifacts/scientific/workflow-runs/shim-research-generic-scheduler-run-scheduler/scientific_lifecycle_runtime.json`
- Runtime manifest: `artifacts/autosci/runs/shim-research-generic-scheduler-run/scheduler_lifecycle/scientific_workflow_runtime_manifest.json`

## Node Results

| Node | Node Status | Gate Status | Artifact |
| --- | --- | --- | --- |
| paper_ingest | passed | passed | artifacts/autosci/runs/shim-research-generic-scheduler-run/scheduler_lifecycle/paper_ingest/task-shim-research-generic-scheduler-run-scheduler-paper_ingest/research_paper.json |

## Blocked Nodes

- N/A

## Notes

- This page is projected from Solar-managed evidence; it is not the execution ledger.
- Missing provider, model, approval, or runtime evidence remains visible as blocked or inconclusive state.
