---
entity_type: "output"
entity_id: "experiment-shim-exp-status-collected"
title: "Experiment summary for shim-exp-status-collected"
run_id: "shim-exp-status-collected"
source_evidence: "artifacts/autosci/runs/shim-exp-status-collected/experiment_status.json"
managed_by: "solar-autosci-workspace-projector"
---
# Experiment Summary: `shim-exp-status-collected`

## Status

- Experiment id: `exp-skillgen`
- Plan evidence status: `N/A`
- Result evidence status: `N/A`
- Status evidence status: `completed`
- Outcome: `N/A`
- State: `completed`
- Execution mode: `N/A`
- Command run: `N/A`
- Plan evidence: `N/A`
- Result evidence: `N/A`
- Status evidence: `artifacts/autosci/runs/shim-exp-status-collected/experiment_status.json`

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
| wiki_state_resolver_json | artifacts/autosci/runs/shim-exp-status-collected/wiki_state_resolver.json |
| wiki_experiment_markdown | artifacts/autosci/workspace/wiki/experiments/exp-skillgen.md |
| solar_evidence_json | artifacts/autosci/runs/shim-exp-status-collected/experiment_status.json |

## Limitations

- Experiment status was read from wiki experiment state; no command was executed and no remote results were collected.
- Resolver is read-only; it does not mutate wiki state, add graph edges, or rebuild wiki indexes.
- Frontmatter parsing supports scalar values and simple lists only; complex YAML is reported through missing fields.
