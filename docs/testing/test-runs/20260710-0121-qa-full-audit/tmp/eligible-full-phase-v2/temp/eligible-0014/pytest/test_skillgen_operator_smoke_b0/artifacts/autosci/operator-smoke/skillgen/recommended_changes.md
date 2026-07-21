# Recommended Scientific Workflow Changes

## Scope

skillgen-operator-smoke

## Failed Nodes

- `node-review-llm` status `inconclusive` gate `claim_verdict_gate`

## Gate Rejection Reasons

- `claim_verdict_gate`: Review LLM is not available in fixture smoke.

## Proposed Changes

- `change.workflow-template.failed-node-recovery` [workflow_template] scientific_research_lifecycle_full_v1: Add or tighten recovery guidance for failed nodes: node-review-llm.
- `change.gate.rejection-diagnostics` [gate] scientific evaluator gates: Expose gate rejection reasons in the dispatch/evidence handoff before retry.
- `change.manual.ambiguity-clarification` [manual] scientific dispatch manuals: Clarify ambiguous manual or prompt language cited by the failed run.
- `change.routing.operator-binding` [routing] logical-to-physical operator bindings: Review operator binding constraints for the cited poor bindings.

## Patch Candidates

- Directory: `artifacts/autosci/operator-smoke/skillgen/patch_candidates`
- Status: proposed-only; no patch candidate is applied by this action.

## Review Controls

- Approval state: proposed
- Protected core runtime edited: false
- Human can accept or reject each proposed change independently.
