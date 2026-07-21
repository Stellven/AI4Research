---
entity_type: "output"
entity_id: "experiment-shim-exp-collect-runtime-verified"
title: "Experiment summary for shim-exp-collect-runtime-verified"
run_id: "shim-exp-collect-runtime-verified"
source_evidence: "artifacts/autosci/runs/shim-exp-collect-runtime-verified/experiment_status.json"
managed_by: "solar-autosci-workspace-projector"
---
# Experiment Summary: `shim-exp-collect-runtime-verified`

## Status

- Experiment id: `exp-collect`
- Plan evidence status: `N/A`
- Result evidence status: `N/A`
- Status evidence status: `completed`
- Outcome: `N/A`
- State: `completed`
- Execution mode: `N/A`
- Command run: `N/A`
- Plan evidence: `N/A`
- Result evidence: `N/A`
- Status evidence: `artifacts/autosci/runs/shim-exp-collect-runtime-verified/experiment_status.json`

## Runtime Audit Boundary

- Boundary status: `runtime_audit_incomplete`
- Stage: `collect`
- Final runtime audit ready: `False`
- Stage audit ready: `False`
- Approval contract verified: `True`
- Runtime semantic verified: `True`
- Result collected: `True`
- Collection ledger recorded: `False`
- Live remote collection verified: `False`

## Metrics

- N/A

## Logs

- N/A

## Artifacts

| Type | Path |
| --- | --- |
| wiki_state_resolver_json | artifacts/autosci/runs/shim-exp-collect-runtime-verified/wiki_state_resolver.json |
| approval_contract_json | artifacts/autosci/runs/shim-exp-collect-runtime-verified/monitor_experiment_approval_contract.json |
| experiment_runtime_evidence_json | collect-runtime.json |
| wiki_experiment_state | artifacts/autosci/workspace/wiki/experiments/exp-collect.md |
| wiki_log | artifacts/autosci/workspace/wiki/log.md |
| wiki_graph_edges | artifacts/autosci/workspace/wiki/graph/edges.jsonl |
| experiment_run_final_runtime_audit_boundary_json | artifacts/autosci/runs/shim-exp-collect-runtime-verified/experiment_run_final_runtime_audit_boundary.json |
| solar_evidence_json | artifacts/autosci/runs/shim-exp-collect-runtime-verified/experiment_status.json |

## Limitations

- Experiment status was completed from approved runtime evidence; this bridge verified evidence and mutated wiki state but did not pull remote results directly.
- Target `exp-collect` was not found in wiki ideas, experiments, outputs, or graph edges.
- Resolver is read-only; it does not mutate wiki state, add graph edges, or rebuild wiki indexes.
- Frontmatter parsing supports scalar values and simple lists only; complex YAML is reported through missing fields.
- No wiki root exists for state resolution.
- Final collect audit requires a collection ledger entry.
- Final collect audit requires live remote/provider collection boundary proof.
