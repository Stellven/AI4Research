---
entity_type: "output"
entity_id: "experiment-shim-exp-remote-parity-collect"
title: "Experiment summary for shim-exp-remote-parity-collect"
run_id: "shim-exp-remote-parity-collect"
source_evidence: "artifacts/autosci/runs/shim-exp-remote-parity-collect/experiment_status.json"
managed_by: "solar-autosci-workspace-projector"
---
# Experiment Summary: `shim-exp-remote-parity-collect`

## Status

- Experiment id: `exp-remote-parity-collect`
- Plan evidence status: `N/A`
- Result evidence status: `N/A`
- Status evidence status: `completed`
- Outcome: `N/A`
- State: `completed`
- Execution mode: `N/A`
- Command run: `N/A`
- Plan evidence: `N/A`
- Result evidence: `N/A`
- Status evidence: `artifacts/autosci/runs/shim-exp-remote-parity-collect/experiment_status.json`

## Runtime Audit Boundary

- Boundary status: `stage_runtime_audit_ready`
- Stage: `collect`
- Final runtime audit ready: `False`
- Stage audit ready: `True`
- Approval contract verified: `True`
- Runtime semantic verified: `True`
- Result collected: `True`
- Collection ledger recorded: `True`
- Live remote collection verified: `False`

## Metrics

- N/A

## Logs

- N/A

## Artifacts

| Type | Path |
| --- | --- |
| wiki_state_resolver_json | artifacts/autosci/runs/shim-exp-remote-parity-collect/wiki_state_resolver.json |
| approval_contract_json | artifacts/autosci/runs/shim-exp-remote-parity-collect/monitor_experiment_approval_contract.json |
| gate_policy_decision_json | artifacts/autosci/runs/shim-exp-remote-parity-collect/monitor_experiment_gate_policy_decision.json |
| gate_policy_allowlist_json | artifacts/autosci/runs/shim-exp-remote-parity-collect/monitor_experiment_gate_policy_allowlist.json |
| experiment_runtime_evidence_json | artifacts/autosci/runs/shim-exp-remote-parity-collect/monitor_experiment_runtime_evidence.json |
| executor_stdout | artifacts/autosci/runs/shim-exp-remote-parity-collect/monitor_experiment_executor_stdout.txt |
| executor_stderr | artifacts/autosci/runs/shim-exp-remote-parity-collect/monitor_experiment_executor_stderr.txt |
| remote_collected_file | remote-parity-results/results.json |
| collection_ledger_json | artifacts/autosci/workspace/wiki/collections/collection-ledger.json |
| experiment_run_report_json | artifacts/autosci/runs/shim-exp-remote-parity-collect/experiment_run_report.json |
| wiki_experiment_state | artifacts/autosci/workspace/wiki/experiments/exp-remote-parity-collect.md |
| wiki_log | artifacts/autosci/workspace/wiki/log.md |
| wiki_graph_edges | artifacts/autosci/workspace/wiki/graph/edges.jsonl |
| experiment_run_final_runtime_audit_boundary_json | artifacts/autosci/runs/shim-exp-remote-parity-collect/experiment_run_final_runtime_audit_boundary.json |
| solar_evidence_json | artifacts/autosci/runs/shim-exp-remote-parity-collect/experiment_status.json |

## Limitations

- Experiment status was completed from approved runtime evidence; this bridge verified evidence and mutated wiki state but did not pull remote results directly.
- Remote results were collected from local files or unverified transport metadata, not a proven live SSH/provider pull-results operation.
- Target `exp-remote-parity-collect` was not found in wiki ideas, experiments, outputs, or graph edges.
- Resolver is read-only; it does not mutate wiki state, add graph edges, or rebuild wiki indexes.
- Frontmatter parsing supports scalar values and simple lists only; complex YAML is reported through missing fields.
- No wiki root exists for state resolution.
- Final collect audit requires live remote/provider collection boundary proof.
