# Recommended Scientific Workflow Changes

## Scope

scientific_research_lifecycle_full_v1

## Failed Nodes

- `experiment_run` status `failed` gate `G_EXPERIMENT_RUN`

## Gate Rejection Reasons

- `G_EXPERIMENT_RUN`: experiment_result.v1 missing non-empty metrics; experiment_result.v1 missing logs artifact

## Proposed Changes

- `change.workflow-template.failed-node-recovery` [workflow_template] scientific_research_lifecycle_full_v1: Add or tighten recovery guidance for failed nodes: experiment_run.
- `change.gate.rejection-diagnostics` [gate] scientific evaluator gates: Expose gate rejection reasons in the dispatch/evidence handoff before retry.
- `change.manual.ambiguity-clarification` [manual] scientific dispatch manuals: Clarify ambiguous manual or prompt language cited by the failed run.
- `change.schema.required-field-tightening` [schema] scientific Evidence ABI schemas: Review whether missing fields should become schema requirements or deterministic gate checks.
- `change.routing.operator-binding` [routing] logical-to-physical operator bindings: Review operator binding constraints for the cited poor bindings.

## Patch Candidates

- Directory: `artifacts/scientific/smoke/patch_candidates`
- Status: proposed-only; no patch candidate is applied by this action.

## Review Controls

- Approval state: proposed
- Protected core runtime edited: false
- Human can accept or reject each proposed change independently.
