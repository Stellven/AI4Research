---
entity_type: "output"
entity_id: "experiment-priority-b-exp-run-workspace-dc7f3be2e376457c8fc8abf60627de81"
title: "Experiment summary for priority-b-exp-run-workspace-dc7f3be2e376457c8fc8abf60627de81"
run_id: "priority-b-exp-run-workspace-dc7f3be2e376457c8fc8abf60627de81"
source_evidence: "artifacts/autosci/runs/priority-b-exp-run-workspace-dc7f3be2e376457c8fc8abf60627de81/experiment_result.json"
managed_by: "solar-autosci-workspace-projector"
---
# Experiment Summary: `priority-b-exp-run-workspace-dc7f3be2e376457c8fc8abf60627de81`

## Status

- Experiment id: `exp-demo`
- Plan evidence status: `completed`
- Result evidence status: `inconclusive`
- Status evidence status: `N/A`
- Outcome: `inconclusive`
- State: `N/A`
- Execution mode: `human_approved`
- Command run: `python3 plugins/autosci/bin/autosci_bridge.py run --action run_experiment`
- Plan evidence: `artifacts/autosci/runs/priority-b-exp-run-workspace-dc7f3be2e376457c8fc8abf60627de81/experiment_plan.json`
- Result evidence: `artifacts/autosci/runs/priority-b-exp-run-workspace-dc7f3be2e376457c8fc8abf60627de81/experiment_result.json`
- Status evidence: `N/A`

## Runtime Audit Boundary

- Boundary status: `runtime_audit_incomplete`
- Stage: `run`
- Final runtime audit ready: `False`
- Stage audit ready: `False`
- Approval contract verified: `False`
- Runtime semantic verified: `False`
- Result collected: `False`
- Collection ledger recorded: `False`
- Live remote collection verified: `False`

## Metrics

| Metric | Value |
| --- | --- |
| approval_present | False |

## Logs

| Log |
| --- |
| execution_mode=human_approved |
| experiment_id=exp-demo |
| command_run=python3 plugins/autosci/bin/autosci_bridge.py run --action run_experiment |
| blocked missing approval for non-fixture execution |

## Artifacts

| Type | Path |
| --- | --- |
| wiki_state_resolver_json | artifacts/autosci/runs/priority-b-exp-run-workspace-dc7f3be2e376457c8fc8abf60627de81/wiki_state_resolver.json |
| experiment_design_final_execution_boundary_json | artifacts/autosci/runs/priority-b-exp-run-workspace-dc7f3be2e376457c8fc8abf60627de81/experiment_design_final_execution_boundary.json |
| solar_evidence_json | artifacts/autosci/runs/priority-b-exp-run-workspace-dc7f3be2e376457c8fc8abf60627de81/experiment_plan.json |
| experiment_run_log | artifacts/autosci/runs/priority-b-exp-run-workspace-dc7f3be2e376457c8fc8abf60627de81/exp-demo.log |
| approval_contract_json | artifacts/autosci/runs/priority-b-exp-run-workspace-dc7f3be2e376457c8fc8abf60627de81/run_experiment_approval_contract.json |
| gate_policy_decision_json | artifacts/autosci/runs/priority-b-exp-run-workspace-dc7f3be2e376457c8fc8abf60627de81/run_experiment_gate_policy_decision.json |
| experiment_run_final_runtime_audit_boundary_json | artifacts/autosci/runs/priority-b-exp-run-workspace-dc7f3be2e376457c8fc8abf60627de81/experiment_run_final_runtime_audit_boundary.json |
| side_effect_access_request_json | artifacts/autosci/runs/priority-b-exp-run-workspace-dc7f3be2e376457c8fc8abf60627de81/run_experiment_side_effect_access_request.json |
| solar_evidence_json | artifacts/autosci/runs/priority-b-exp-run-workspace-dc7f3be2e376457c8fc8abf60627de81/experiment_result.json |

## Limitations

- Approval-gated native experiment design; no command is executed by this planning action.
- Target `idea-001` was not found in wiki ideas, experiments, outputs, or graph edges.
- Resolver is read-only; it does not mutate wiki state, add graph edges, or rebuild wiki indexes.
- Frontmatter parsing supports scalar values and simple lists only; complex YAML is reported through missing fields.
- No wiki root exists for state resolution.
- Review LLM design validation was not supplied.
- Experiment design final execution readiness requires resolved target evidence, completed Review LLM validation, approval preflight, command handoff, and expected artifact handoff.
- Experiment execution was blocked because approval is required and absent; no experiment command was executed.
- Approval/runtime evidence contract is not fully verified: approval_ref, allowlist_evidence, before_artifacts, runtime_evidence, after_artifacts
- Final runtime audit requires a fully verified approval contract with runtime and after-artifact evidence.
- Final runtime audit requires semantic runtime verification to pass.
- Final runtime audit requires collected experiment result evidence.
- Final runtime audit requires wiki experiment state, log, and graph mutation proof.
- Final lifecycle audit also requires an approved monitor/collect stage with collection ledger evidence.
- Side-effect access is required; no protected native side effects were executed.
