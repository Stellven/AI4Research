---
entity_type: "experiment"
entity_id: "exp-demo"
title: "Validate evidence coverage for `exp-demo` using an approval-gated native experiment."
run_id: "priority-b-exp-run-workspace-933636f4eb974ea5b70538886e30d894"
source_evidence: "artifacts/autosci/runs/priority-b-exp-run-workspace-933636f4eb974ea5b70538886e30d894/experiment_result.json"
status: planned
outcome: inconclusive
managed_by: "solar-autosci-workspace-projector"
---
# Validate evidence coverage for `exp-demo` using an approval-gated native experiment.

- Experiment id: `exp-demo`
- Status: `planned`
- Outcome: `inconclusive`
- Execution mode: `human_approved`
- Approval required: `True`
- Plan evidence: `artifacts/autosci/runs/priority-b-exp-run-workspace-933636f4eb974ea5b70538886e30d894/experiment_plan.json`
- Result evidence: `artifacts/autosci/runs/priority-b-exp-run-workspace-933636f4eb974ea5b70538886e30d894/experiment_result.json`

## Hypothesis

A verified approved runtime will produce result artifacts without relying on surrogate outcomes.

## Procedure

- Resolve the target idea, claim, or experiment plan evidence.
- Require explicit approval and allowlisted runtime command evidence before execution.
- Collect runtime logs, metrics, and produced result artifacts.
- Validate experiment_result.v1 and experiment_status.v1 from supplied runtime evidence.

## Success Criteria

- approval_present == true
- runtime_evidence_verified == true
- result_artifact_present == true

## Result Metrics

- approval_present: `False`

## Result Evidence IDs

- `exp-demo`
- `Validate evidence coverage for `exp-demo` using an approval-gated native experiment.`
