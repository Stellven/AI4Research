---
entity_type: "output"
entity_id: "experiment-shim-exp-remote-empty"
title: "Experiment summary for shim-exp-remote-empty"
run_id: "shim-exp-remote-empty"
source_evidence: "artifacts/autosci/runs/shim-exp-remote-empty/experiment_status.json"
managed_by: "solar-autosci-workspace-projector"
---
# Experiment Summary: `shim-exp-remote-empty`

## Status

- Experiment id: `exp-remote-empty`
- Plan evidence status: `N/A`
- Result evidence status: `N/A`
- Status evidence status: `inconclusive`
- Outcome: `N/A`
- State: `unknown`
- Execution mode: `N/A`
- Command run: `N/A`
- Plan evidence: `N/A`
- Result evidence: `N/A`
- Status evidence: `artifacts/autosci/runs/shim-exp-remote-empty/experiment_status.json`

## Runtime Audit Boundary

- Boundary status: `runtime_audit_incomplete`
- Stage: `collect`
- Final runtime audit ready: `False`
- Stage audit ready: `False`
- Approval contract verified: `True`
- Runtime semantic verified: `False`
- Result collected: `False`
- Collection ledger recorded: `False`
- Live remote collection verified: `False`

## Metrics

- N/A

## Logs

- N/A

## Artifacts

| Type | Path |
| --- | --- |
| wiki_state_resolver_json | artifacts/autosci/runs/shim-exp-remote-empty/wiki_state_resolver.json |
| approval_contract_json | artifacts/autosci/runs/shim-exp-remote-empty/monitor_experiment_approval_contract.json |
| experiment_runtime_evidence_json | artifacts/autosci/runs/shim-exp-remote-empty/monitor_experiment_runtime_evidence.json |
| executor_stdout | artifacts/autosci/runs/shim-exp-remote-empty/monitor_experiment_executor_stdout.txt |
| executor_stderr | artifacts/autosci/runs/shim-exp-remote-empty/monitor_experiment_executor_stderr.txt |
| experiment_run_report_json | artifacts/autosci/runs/shim-exp-remote-empty/experiment_run_report.json |
| experiment_run_final_runtime_audit_boundary_json | artifacts/autosci/runs/shim-exp-remote-empty/experiment_run_final_runtime_audit_boundary.json |
| solar_evidence_json | artifacts/autosci/runs/shim-exp-remote-empty/experiment_status.json |

## Limitations

- Collect/status remains inconclusive because approved runtime evidence did not pass semantic verification.
- Target `exp-remote-empty` was not found in wiki ideas, experiments, outputs, or graph edges.
- Resolver is read-only; it does not mutate wiki state, add graph edges, or rebuild wiki indexes.
- Frontmatter parsing supports scalar values and simple lists only; complex YAML is reported through missing fields.
- No wiki root exists for state resolution.
- Final runtime audit requires semantic runtime verification to pass.
- Final runtime audit requires collected experiment result evidence.
- Final runtime audit requires wiki experiment state, log, and graph mutation proof.
- Final collect audit requires a collection ledger entry.
- Final collect audit requires live remote/provider collection boundary proof.
