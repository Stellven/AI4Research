---
entity_type: "experiment"
entity_id: "exp-remote"
title: "Validate evidence coverage for `exp-remote` using an approval-gated native experiment."
run_id: "shim-exp-run-remote-helper"
source_evidence: "artifacts/autosci/runs/shim-exp-run-remote-helper/experiment_result.json"
status: completed
outcome: supports
managed_by: "solar-autosci-workspace-projector"
---
# Validate evidence coverage for `exp-remote` using an approval-gated native experiment.

- Experiment id: `exp-remote`
- Status: `completed`
- Outcome: `supports`
- Execution mode: `human_approved`
- Approval required: `True`
- Plan evidence: `artifacts/autosci/runs/shim-exp-run-remote-helper/experiment_plan.json`
- Result evidence: `artifacts/autosci/runs/shim-exp-run-remote-helper/experiment_result.json`

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

- accuracy: `0.92`

## Result Evidence IDs

- `exp-remote`
- `Validate evidence coverage for `exp-remote` using an approval-gated native experiment.`
- `remote-runtime:exp-remote`
- `remote-launch-exp-remote`
- `node-remote-launch-exp-remote`
- `/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/system-tmp/pytest-of-jamesyuan/pytest-1/test_autosci_skill_shim_exp_ru4/exp-remote-runtime.json`
- `experiment-runtime:exp-remote`
- `task-autosci-skillgen-run_experiment`
- `node-run-experiment`
- `artifacts/autosci/runs/shim-exp-run-remote-helper/run_experiment_runtime_evidence.json`
