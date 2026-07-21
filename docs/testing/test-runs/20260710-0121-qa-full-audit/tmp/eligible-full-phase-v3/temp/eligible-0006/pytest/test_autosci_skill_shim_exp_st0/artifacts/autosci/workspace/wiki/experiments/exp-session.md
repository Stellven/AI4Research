---
entity_type: "experiment"
entity_id: "exp-session"
title: "Validate evidence coverage for `exp-session` using an approval-gated native experiment."
run_id: "shim-exp-session-launch"
source_evidence: "artifacts/autosci/runs/shim-exp-session-launch/experiment_result.json"
status: planned
outcome: inconclusive
managed_by: "solar-autosci-workspace-projector"
---
# Validate evidence coverage for `exp-session` using an approval-gated native experiment.

- Experiment id: `exp-session`
- Status: `planned`
- Outcome: `inconclusive`
- Execution mode: `human_approved`
- Approval required: `True`
- Plan evidence: `artifacts/autosci/runs/shim-exp-session-launch/experiment_plan.json`
- Result evidence: `artifacts/autosci/runs/shim-exp-session-launch/experiment_result.json`

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

- approval_present: `True`
- runtime_evidence_verified: `False`

## Result Evidence IDs

- `exp-session`
- `Validate evidence coverage for `exp-session` using an approval-gated native experiment.`
