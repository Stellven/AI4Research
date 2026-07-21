# Recommended Scientific Workflow Changes

## Scope

scientific_research_lifecycle_full_v1

## Failed Nodes

- `publication_produce` status `failed` gate `G_PUBLICATION_PRODUCE`

## Gate Rejection Reasons

- `G_PUBLICATION_PRODUCE`: publication_produce currently lacks a scheduler-bound publication_bundle.v1 action

## Proposed Changes

- `change.workflow-template.failed-node-recovery` [workflow_template] scientific_research_lifecycle_full_v1: Add or tighten recovery guidance for failed nodes: publication_produce.
- `change.gate.rejection-diagnostics` [gate] scientific evaluator gates: Expose gate rejection reasons in the dispatch/evidence handoff before retry.
- `change.manual.ambiguity-clarification` [manual] scientific dispatch manuals: Clarify ambiguous manual or prompt language cited by the failed run.
- `change.routing.operator-binding` [routing] logical-to-physical operator bindings: Review operator binding constraints for the cited poor bindings.

## Patch Candidates

- Directory: `artifacts/scientific/scheduler-lifecycle-smoke/job-scientific-lifecycle-resume-test/workflow_evolve/task-job-scientific-lifecycle-resume-test-workflow_evolve/patch_candidates`
- Status: proposed-only; no patch candidate is applied by this action.

## Review Controls

- Approval state: proposed
- Protected core runtime edited: false
- Human can accept or reject each proposed change independently.
