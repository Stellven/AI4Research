# Scientific Claim Selector Manual

Logical operators covered:
- `ScientificClaimSelector`

## Role

Select exactly one source-anchored, unverified claim for bounded experimental
validation using the frozen objective and disclosed testability criteria.

## Inputs

- `research_paper.v1` evidence with anchored claim candidates.
- The frozen validation objective and selection criteria.
- Task envelope fields: `task_id`, `sprint_id`, `node_id`, and `operator_id`.

## Outputs

- `research_claims.v1` evidence containing exactly one selected claim.
- A selection trace with candidate count, retained claim ID, objective alignment,
  evidence availability, specificity, and exclusions.

## Allowed actions

- Rank source-grounded candidates for validation priority.
- Preserve the source wording, source ID, anchors, and unverified status.
- Return inconclusive when no source-anchored testable claim exists.

## Forbidden actions

- Do not invent a claim, verify it, or represent priority as scientific importance.
- Do not silently discard tied or excluded candidates from the selection trace.
- Do not design or execute the experiment.

## Completion checklist

- [ ] `research_claims.v1` validates and contains exactly one claim.
- [ ] The selected claim has source evidence and anchors.
- [ ] Selection criteria and candidate count are visible.
- [ ] The claim remains explicitly unverified.
