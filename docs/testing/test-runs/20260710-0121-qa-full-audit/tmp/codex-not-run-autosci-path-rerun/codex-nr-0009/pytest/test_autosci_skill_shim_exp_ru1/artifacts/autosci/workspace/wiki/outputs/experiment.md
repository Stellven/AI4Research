---
entity_type: "output"
entity_id: "experiment-shim-exp-run-runtime-verified"
title: "Experiment summary for shim-exp-run-runtime-verified"
run_id: "shim-exp-run-runtime-verified"
source_evidence: "artifacts/autosci/runs/shim-exp-run-runtime-verified/experiment_result.json"
managed_by: "solar-autosci-workspace-projector"
---
# Experiment Summary: `shim-exp-run-runtime-verified`

## Status

- Experiment id: `exp-approved`
- Plan evidence status: `completed`
- Result evidence status: `completed`
- Status evidence status: `N/A`
- Outcome: `supports`
- State: `N/A`
- Execution mode: `human_approved`
- Command run: `python run_exp.py --experiment exp-approved`
- Plan evidence: `artifacts/autosci/runs/shim-exp-run-runtime-verified/experiment_plan.json`
- Result evidence: `artifacts/autosci/runs/shim-exp-run-runtime-verified/experiment_result.json`
- Status evidence: `N/A`

## Runtime Audit Boundary

- Boundary status: `stage_runtime_audit_ready`
- Stage: `run`
- Final runtime audit ready: `False`
- Stage audit ready: `True`
- Approval contract verified: `True`
- Runtime semantic verified: `True`
- Result collected: `True`
- Collection ledger recorded: `False`
- Live remote collection verified: `False`

## Metrics

| Metric | Value |
| --- | --- |
| accuracy | 0.91 |

## Logs

| Log |
| --- |
| execution_mode=human_approved |
| experiment_id=exp-approved |
| command_run=python3 plugins/autosci/bin/autosci_bridge.py run --action run_experiment |
| approval_state=verified |
| approved runtime evidence verified |
| approved experiment runtime completed |

## Artifacts

| Type | Path |
| --- | --- |
| wiki_state_resolver_json | artifacts/autosci/runs/shim-exp-run-runtime-verified/wiki_state_resolver.json |
| experiment_design_final_execution_boundary_json | artifacts/autosci/runs/shim-exp-run-runtime-verified/experiment_design_final_execution_boundary.json |
| solar_evidence_json | artifacts/autosci/runs/shim-exp-run-runtime-verified/experiment_plan.json |
| experiment_run_log | artifacts/autosci/runs/shim-exp-run-runtime-verified/exp-approved.log |
| approval_contract_json | artifacts/autosci/runs/shim-exp-run-runtime-verified/run_experiment_approval_contract.json |
| gate_policy_decision_json | artifacts/autosci/runs/shim-exp-run-runtime-verified/run_experiment_gate_policy_decision.json |
| experiment_runtime_evidence_json | exp-runtime.json |
| run_experiment_result_json | exp-after.json |
| wiki_experiment_state | artifacts/autosci/workspace/wiki/experiments/exp-approved.md |
| wiki_log | artifacts/autosci/workspace/wiki/log.md |
| wiki_graph_edges | artifacts/autosci/workspace/wiki/graph/edges.jsonl |
| experiment_run_final_runtime_audit_boundary_json | artifacts/autosci/runs/shim-exp-run-runtime-verified/experiment_run_final_runtime_audit_boundary.json |
| solar_evidence_json | artifacts/autosci/runs/shim-exp-run-runtime-verified/experiment_result.json |

## Limitations

- Approval-gated native experiment design; no command is executed by this planning action.
- Target `idea-001` was not found in wiki ideas, experiments, outputs, or graph edges.
- Resolver is read-only; it does not mutate wiki state, add graph edges, or rebuild wiki indexes.
- Frontmatter parsing supports scalar values and simple lists only; complex YAML is reported through missing fields.
- No wiki root exists for state resolution.
- Review LLM design validation was not supplied.
- Experiment design final execution readiness requires resolved target evidence, completed Review LLM validation, approval preflight, command handoff, and expected artifact handoff.
- Experiment result was completed from approved runtime evidence and mutated wiki state.
- Final lifecycle audit also requires an approved monitor/collect stage with collection ledger evidence.
