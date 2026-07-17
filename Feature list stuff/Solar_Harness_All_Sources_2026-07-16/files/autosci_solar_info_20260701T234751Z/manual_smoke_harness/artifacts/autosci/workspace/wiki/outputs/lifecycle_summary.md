---
entity_type: "output"
entity_id: "lifecycle-summary-info-smoke-research"
title: "Lifecycle summary for info-smoke-research"
run_id: "info-smoke-research"
source_evidence: "artifacts/scientific/workflow-runs/info-smoke-research-scheduler/scientific_lifecycle_runtime.json"
managed_by: "solar-autosci-workspace-projector"
---
# Lifecycle Summary: `info-smoke-research`

## Status

- Lifecycle status: `passed`
- Workflow id: `scientific_research_lifecycle_full_v1`
- Job id: `info-smoke-research-scheduler`
- Execution owner: `solar.operator_runtime.generic_scientific_workflow_runner`
- Dispatch boundary: `generic_workflow_runner`
- Production ready: `True`
- Lifecycle gate: `passed`
- Node count: `1`
- Blocked node count: `0`

## Evidence

- Skill run: `artifacts/autosci/runs/info-smoke-research/autosci_skill_run.json`
- Lifecycle summary: `artifacts/scientific/workflow-runs/info-smoke-research-scheduler/scientific_lifecycle_runtime.json`
- Runtime manifest: `artifacts/autosci/runs/info-smoke-research/scheduler_lifecycle/scientific_workflow_runtime_manifest.json`

## Node Results

| Node | Node Status | Gate Status | Artifact |
| --- | --- | --- | --- |
| paper_ingest | passed | passed | artifacts/autosci/runs/info-smoke-research/scheduler_lifecycle/paper_ingest/task-info-smoke-research-scheduler-paper_ingest/research_paper.json |

## Blocked Nodes

- N/A

## Notes

- This page is projected from Solar-managed evidence; it is not the execution ledger.
- Missing provider, model, approval, or runtime evidence remains visible as blocked or inconclusive state.
