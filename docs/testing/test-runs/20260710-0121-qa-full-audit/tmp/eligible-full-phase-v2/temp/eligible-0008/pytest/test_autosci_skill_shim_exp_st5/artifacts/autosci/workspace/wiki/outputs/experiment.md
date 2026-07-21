---
entity_type: "output"
entity_id: "experiment-shim-exp-session-status"
title: "Experiment summary for shim-exp-session-status"
run_id: "shim-exp-session-status"
source_evidence: "artifacts/autosci/runs/shim-exp-session-status/experiment_status.json"
managed_by: "solar-autosci-workspace-projector"
---
# Experiment Summary: `shim-exp-session-status`

## Status

- Experiment id: `exp-session`
- Plan evidence status: `N/A`
- Result evidence status: `N/A`
- Status evidence status: `completed`
- Outcome: `N/A`
- State: `running`
- Execution mode: `N/A`
- Command run: `N/A`
- Plan evidence: `N/A`
- Result evidence: `N/A`
- Status evidence: `artifacts/autosci/runs/shim-exp-session-status/experiment_status.json`

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
| wiki_state_resolver_json | artifacts/autosci/runs/shim-exp-session-status/wiki_state_resolver.json |
| wiki_experiment_markdown | artifacts/autosci/workspace/wiki/experiments/exp-session.md |
| experiment_session_registry_json | artifacts/autosci/workspace/wiki/experiments/session-registry.json |
| solar_evidence_json | artifacts/autosci/runs/shim-exp-session-status/experiment_status.json |

## Limitations

- Experiment status was read from the local session registry; no remote process was polled and no results were collected in this status call.
- Resolver is read-only; it does not mutate wiki state, add graph edges, or rebuild wiki indexes.
- Frontmatter parsing supports scalar values and simple lists only; complex YAML is reported through missing fields.
