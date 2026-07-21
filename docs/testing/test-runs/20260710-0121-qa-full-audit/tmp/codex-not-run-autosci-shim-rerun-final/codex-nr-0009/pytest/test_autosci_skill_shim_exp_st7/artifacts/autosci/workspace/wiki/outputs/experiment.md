---
entity_type: "output"
entity_id: "experiment-shim-exp-status-parity-remote-check"
title: "Experiment summary for shim-exp-status-parity-remote-check"
run_id: "shim-exp-status-parity-remote-check"
source_evidence: "artifacts/autosci/runs/shim-exp-status-parity-remote-check/experiment_status.json"
managed_by: "solar-autosci-workspace-projector"
---
# Experiment Summary: `shim-exp-status-parity-remote-check`

## Status

- Experiment id: `exp-remote-parity`
- Plan evidence status: `N/A`
- Result evidence status: `N/A`
- Status evidence status: `completed`
- Outcome: `N/A`
- State: `running`
- Execution mode: `N/A`
- Command run: `N/A`
- Plan evidence: `N/A`
- Result evidence: `N/A`
- Status evidence: `artifacts/autosci/runs/shim-exp-status-parity-remote-check/experiment_status.json`

## Runtime Audit Boundary

- Boundary status: `N/A`
- Stage: `N/A`
- Final runtime audit ready: `N/A`
- Stage audit ready: `N/A`
- Approval contract verified: `N/A`
- Runtime semantic verified: `N/A`
- Result collected: `N/A`
- Collection ledger recorded: `N/A`
- Live remote collection verified: `N/A`

## Metrics

- N/A

## Logs

- N/A

## Artifacts

| Type | Path |
| --- | --- |
| wiki_state_resolver_json | artifacts/autosci/runs/shim-exp-status-parity-remote-check/wiki_state_resolver.json |
| approval_contract_json | artifacts/autosci/runs/shim-exp-status-parity-remote-check/monitor_experiment_approval_contract.json |
| gate_policy_decision_json | artifacts/autosci/runs/shim-exp-status-parity-remote-check/monitor_experiment_gate_policy_decision.json |
| gate_policy_allowlist_json | artifacts/autosci/runs/shim-exp-status-parity-remote-check/monitor_experiment_gate_policy_allowlist.json |
| remote_status_runtime_evidence_json | artifacts/autosci/runs/shim-exp-status-parity-remote-check/remote_status_runtime_evidence.json |
| executor_stdout | artifacts/autosci/runs/shim-exp-status-parity-remote-check/remote_status_executor_stdout.txt |
| executor_stderr | artifacts/autosci/runs/shim-exp-status-parity-remote-check/remote_status_executor_stderr.txt |
| remote_status_file | remote-status-parity-run/status.json |
| solar_evidence_json | artifacts/autosci/runs/shim-exp-status-parity-remote-check/experiment_status.json |

## Limitations

- Experiment status was read by an approved remote status check command; no result collection was performed.
- Remote status was derived from local run-dir artifacts or unverified transport metadata, not a proven live SSH/provider poll.
- Target `exp-remote-parity` was not found in wiki ideas, experiments, outputs, or graph edges.
- Resolver is read-only; it does not mutate wiki state, add graph edges, or rebuild wiki indexes.
- Frontmatter parsing supports scalar values and simple lists only; complex YAML is reported through missing fields.
- No wiki root exists for state resolution.
