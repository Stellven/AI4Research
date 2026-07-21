---
entity_type: "output"
entity_id: "experiment-shim-exp-live-remote-collect"
title: "Experiment summary for shim-exp-live-remote-collect"
run_id: "shim-exp-live-remote-collect"
source_evidence: "artifacts/autosci/runs/shim-exp-live-remote-collect/experiment_status.json"
managed_by: "solar-autosci-workspace-projector"
---
# Experiment Summary: `shim-exp-live-remote-collect`

## Status

- Experiment id: `exp-live-remote-collect`
- Plan evidence status: `N/A`
- Result evidence status: `N/A`
- Status evidence status: `completed`
- Outcome: `N/A`
- State: `completed`
- Execution mode: `N/A`
- Command run: `N/A`
- Plan evidence: `N/A`
- Result evidence: `N/A`
- Status evidence: `artifacts/autosci/runs/shim-exp-live-remote-collect/experiment_status.json`

## Runtime Audit Boundary

- Boundary status: `final_runtime_audit_ready`
- Stage: `collect`
- Final runtime audit ready: `True`
- Stage audit ready: `True`
- Approval contract verified: `True`
- Runtime semantic verified: `True`
- Result collected: `True`
- Collection ledger recorded: `True`
- Live remote collection verified: `True`

## Metrics

- N/A

## Logs

- N/A

## Artifacts

| Type | Path |
| --- | --- |
| wiki_state_resolver_json | artifacts/autosci/runs/shim-exp-live-remote-collect/wiki_state_resolver.json |
| approval_contract_json | artifacts/autosci/runs/shim-exp-live-remote-collect/monitor_experiment_approval_contract.json |
| experiment_runtime_evidence_json | artifacts/autosci/runs/shim-exp-live-remote-collect/monitor_experiment_runtime_evidence.json |
| executor_stdout | artifacts/autosci/runs/shim-exp-live-remote-collect/monitor_experiment_executor_stdout.txt |
| executor_stderr | artifacts/autosci/runs/shim-exp-live-remote-collect/monitor_experiment_executor_stderr.txt |
| remote_collected_file | live-remote-results/results.json |
| collection_ledger_json | artifacts/autosci/workspace/wiki/collections/collection-ledger.json |
| experiment_run_report_json | artifacts/autosci/runs/shim-exp-live-remote-collect/experiment_run_report.json |
| wiki_experiment_state | artifacts/autosci/workspace/wiki/experiments/exp-live-remote-collect.md |
| wiki_log | artifacts/autosci/workspace/wiki/log.md |
| wiki_graph_edges | artifacts/autosci/workspace/wiki/graph/edges.jsonl |
| experiment_run_final_runtime_audit_boundary_json | artifacts/autosci/runs/shim-exp-live-remote-collect/experiment_run_final_runtime_audit_boundary.json |
| provider_source_runtime_proof_manifest_json | artifacts/autosci/runs/shim-exp-live-remote-collect/monitor_experiment_final_runtime_proof.json |
| solar_evidence_json | artifacts/autosci/runs/shim-exp-live-remote-collect/experiment_status.json |

## Limitations

- Experiment status was completed from approved runtime evidence; this bridge verified evidence and mutated wiki state but did not pull remote results directly.
- Target `exp-live-remote-collect` was not found in wiki ideas, experiments, outputs, or graph edges.
- Resolver is read-only; it does not mutate wiki state, add graph edges, or rebuild wiki indexes.
- Frontmatter parsing supports scalar values and simple lists only; complex YAML is reported through missing fields.
- No wiki root exists for state resolution.
- Final runtime audit passed with approved runtime, live collection, collection ledger, and wiki mutation evidence.
