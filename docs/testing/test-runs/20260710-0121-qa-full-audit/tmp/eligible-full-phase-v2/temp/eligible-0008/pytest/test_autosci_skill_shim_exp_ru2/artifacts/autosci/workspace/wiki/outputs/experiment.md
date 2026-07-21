---
entity_type: "output"
entity_id: "experiment-shim-exp-run-parity-demo-command"
title: "Experiment summary for shim-exp-run-parity-demo-command"
run_id: "shim-exp-run-parity-demo-command"
source_evidence: "artifacts/autosci/runs/shim-exp-run-parity-demo-command/experiment_result.json"
managed_by: "solar-autosci-workspace-projector"
---
# Experiment Summary: `shim-exp-run-parity-demo-command`

## Status

- Experiment id: `exp-parity-001`
- Plan evidence status: `completed`
- Result evidence status: `inconclusive`
- Status evidence status: `N/A`
- Outcome: `inconclusive`
- State: `N/A`
- Execution mode: `human_approved`
- Command run: `python3 plugins/autosci/bin/autosci_bridge.py run --action run_experiment`
- Plan evidence: `artifacts/autosci/runs/shim-exp-run-parity-demo-command/experiment_plan.json`
- Result evidence: `artifacts/autosci/runs/shim-exp-run-parity-demo-command/experiment_result.json`
- Status evidence: `N/A`

## Runtime Audit Boundary

- Boundary status: `runtime_audit_incomplete`
- Stage: `run`
- Final runtime audit ready: `False`
- Stage audit ready: `False`
- Approval contract verified: `True`
- Runtime semantic verified: `False`
- Result collected: `False`
- Collection ledger recorded: `False`
- Live remote collection verified: `False`

## Metrics

| Metric | Value |
| --- | --- |
| approval_present | True |
| runtime_evidence_verified | False |

## Logs

| Log |
| --- |
| execution_mode=human_approved |
| experiment_id=exp-parity-001 |
| command_run=python3 plugins/autosci/bin/autosci_bridge.py run --action run_experiment |
| approval_state=verified |
| runtime_semantic_status=incomplete |
| blocked missing verified runtime evidence for approval-gated execution |

## Artifacts

| Type | Path |
| --- | --- |
| wiki_state_resolver_json | artifacts/autosci/runs/shim-exp-run-parity-demo-command/wiki_state_resolver.json |
| experiment_design_final_execution_boundary_json | artifacts/autosci/runs/shim-exp-run-parity-demo-command/experiment_design_final_execution_boundary.json |
| solar_evidence_json | artifacts/autosci/runs/shim-exp-run-parity-demo-command/experiment_plan.json |
| experiment_run_log | artifacts/autosci/runs/shim-exp-run-parity-demo-command/exp-parity-001.log |
| approval_contract_json | artifacts/autosci/runs/shim-exp-run-parity-demo-command/run_experiment_approval_contract.json |
| gate_policy_decision_json | artifacts/autosci/runs/shim-exp-run-parity-demo-command/run_experiment_gate_policy_decision.json |
| gate_policy_allowlist_json | artifacts/autosci/runs/shim-exp-run-parity-demo-command/run_experiment_gate_policy_allowlist.json |
| experiment_runtime_evidence_json | artifacts/autosci/runs/shim-exp-run-parity-demo-command/run_experiment_runtime_evidence.json |
| experiment_run_final_runtime_audit_boundary_json | artifacts/autosci/runs/shim-exp-run-parity-demo-command/experiment_run_final_runtime_audit_boundary.json |
| solar_evidence_json | artifacts/autosci/runs/shim-exp-run-parity-demo-command/experiment_result.json |

## Limitations

- Approval-gated native experiment design; no command is executed by this planning action.
- Target `idea-001` was not found in wiki ideas, experiments, outputs, or graph edges.
- Resolver is read-only; it does not mutate wiki state, add graph edges, or rebuild wiki indexes.
- Frontmatter parsing supports scalar values and simple lists only; complex YAML is reported through missing fields.
- No wiki root exists for state resolution.
- Review LLM design validation was not supplied.
- Experiment design final execution readiness requires resolved target evidence, completed Review LLM validation, approval preflight, command handoff, and expected artifact handoff.
- Experiment execution was not marked complete because approval/runtime evidence did not pass semantic verification.
- Auto-approved by gate policy mode `parity_demo`; runtime verification still failed or remained incomplete.
- Final runtime audit requires semantic runtime verification to pass.
- Final runtime audit requires collected experiment result evidence.
- Final runtime audit requires wiki experiment state, log, and graph mutation proof.
- Final lifecycle audit also requires an approved monitor/collect stage with collection ledger evidence.
