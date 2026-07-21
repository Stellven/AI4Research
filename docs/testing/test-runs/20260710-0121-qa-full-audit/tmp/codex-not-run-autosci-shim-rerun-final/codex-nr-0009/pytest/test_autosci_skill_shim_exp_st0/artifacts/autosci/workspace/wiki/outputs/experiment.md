---
entity_type: "output"
entity_id: "experiment-shim-exp-status-pipeline"
title: "Experiment summary for shim-exp-status-pipeline"
run_id: "shim-exp-status-pipeline"
source_evidence: "artifacts/autosci/runs/shim-exp-status-pipeline/experiment_status.json"
managed_by: "solar-autosci-workspace-projector"
---
# Experiment Summary: `shim-exp-status-pipeline`

## Status

- Experiment id: `skillgen-main`
- Plan evidence status: `N/A`
- Result evidence status: `N/A`
- Status evidence status: `inconclusive`
- Outcome: `N/A`
- State: `unknown`
- Execution mode: `N/A`
- Command run: `N/A`
- Plan evidence: `N/A`
- Result evidence: `N/A`
- Status evidence: `artifacts/autosci/runs/shim-exp-status-pipeline/experiment_status.json`

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
| wiki_state_resolver_json | artifacts/autosci/runs/shim-exp-status-pipeline/wiki_state_resolver.json |
| solar_evidence_json | artifacts/autosci/runs/shim-exp-status-pipeline/experiment_status.json |

## Limitations

- Experiment status is unknown because result evidence is missing; no default exp-001 fallback was used.
- Target `skillgen-main` was not found in wiki ideas, experiments, outputs, or graph edges.
- Resolver is read-only; it does not mutate wiki state, add graph edges, or rebuild wiki indexes.
- Frontmatter parsing supports scalar values and simple lists only; complex YAML is reported through missing fields.
- No wiki root exists for state resolution.
