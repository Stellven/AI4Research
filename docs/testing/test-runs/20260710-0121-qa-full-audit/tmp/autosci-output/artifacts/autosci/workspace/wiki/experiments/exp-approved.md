---
entity_type: "experiment"
entity_id: "exp-approved"
title: "Validate evidence coverage for `exp-approved` using an approval-gated native experiment."
run_id: "shim-exp-run-runtime-verified"
source_evidence: "artifacts/autosci/runs/shim-exp-run-runtime-verified/experiment_result.json"
status: completed
outcome: supports
managed_by: "solar-autosci-workspace-projector"
---
# Validate evidence coverage for `exp-approved` using an approval-gated native experiment.

- Experiment id: `exp-approved`
- Status: `completed`
- Outcome: `supports`
- Execution mode: `human_approved`
- Approval required: `True`
- Plan evidence: `artifacts/autosci/runs/shim-exp-run-runtime-verified/experiment_plan.json`
- Result evidence: `artifacts/autosci/runs/shim-exp-run-runtime-verified/experiment_result.json`

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

- accuracy: `0.91`

## Result Evidence IDs

- `exp-approved`
- `Validate evidence coverage for `exp-approved` using an approval-gated native experiment.`
- `runtime:exp-approved`
- `task-exp-approved-runtime`
- `node-exp-approved-runtime`
- `/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/system-tmp/pytest-of-jamesyuan/pytest-1/test_autosci_skill_shim_exp_ru1/exp-runtime.json`
