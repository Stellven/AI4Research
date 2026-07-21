---
entity_type: "experiment"
entity_id: "exp-idea-skillgen-design"
title: "Validate evidence coverage for `idea-skillgen-design` using a bounded fixture experiment."
run_id: "shim-exp-design-review-llm"
source_evidence: "artifacts/autosci/runs/shim-exp-design-review-llm/experiment_plan.json"
status: planned
outcome: N/A
managed_by: "solar-autosci-workspace-projector"
---
# Validate evidence coverage for `idea-skillgen-design` using a bounded fixture experiment.

- Experiment id: `exp-idea-skillgen-design`
- Status: `planned`
- Outcome: `N/A`
- Execution mode: `fixture`
- Approval required: `False`
- Plan evidence: `artifacts/autosci/runs/shim-exp-design-review-llm/experiment_plan.json`
- Result evidence: `N/A`

## Hypothesis

Fixture execution will emit result evidence, a ledger entry, and a monitorable status without external side effects.

## Procedure

- Confirm the experiment plan evidence is present.
- Run the AutoSci bridge in fixture mode only.
- Record command, metrics, logs, and produced evidence paths.
- Validate experiment_result.v1 and experiment_status.v1 gates.
- Attach completed Review LLM design validation before execution approval.

## Success Criteria

- result_json_written == true
- evidence_jsonl_written == true
- fixture_passed == true
- review_llm_design_validation == completed

## Result Metrics

- N/A

## Result Evidence IDs

- N/A
