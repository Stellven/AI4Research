---
entity_type: "experiment"
entity_id: "exp-idea-skillgen-ready"
title: "Validate evidence coverage for `idea-skillgen-ready` using an approval-gated native experiment."
run_id: "shim-exp-design-execution-ready"
source_evidence: "artifacts/autosci/runs/shim-exp-design-execution-ready/experiment_plan.json"
status: planned
outcome: N/A
managed_by: "solar-autosci-workspace-projector"
---
# Validate evidence coverage for `idea-skillgen-ready` using an approval-gated native experiment.

- Experiment id: `exp-idea-skillgen-ready`
- Status: `planned`
- Outcome: `N/A`
- Execution mode: `human_approved`
- Approval required: `True`
- Plan evidence: `artifacts/autosci/runs/shim-exp-design-execution-ready/experiment_plan.json`
- Result evidence: `N/A`

## Hypothesis

A verified approved runtime will produce result artifacts without relying on surrogate outcomes.

## Procedure

- Resolve the target idea, claim, or experiment plan evidence.
- Require explicit approval and allowlisted runtime command evidence before execution.
- Collect runtime logs, metrics, and produced result artifacts.
- Validate experiment_result.v1 and experiment_status.v1 from supplied runtime evidence.
- Attach completed Review LLM design validation before execution approval.

## Success Criteria

- approval_present == true
- runtime_evidence_verified == true
- result_artifact_present == true
- review_llm_design_validation == completed
- final_execution_boundary == execution_ready

## Result Metrics

- N/A

## Result Evidence IDs

- N/A
