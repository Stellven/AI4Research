# Artifact Refinement Proposal

Target: `report-001`

## Proposed Changes

- `change.manual.refine_artifact` [manual]: Record the approved refine artifact checklist, requested target, and rollback notes.
- `change.gate.refine_artifact` [gate]: Keep side-effect execution blocked until approval evidence and before/after artifact evidence are present.

## Controls

- Approval state: proposed
- Protected runtime changed: false
- Side effects executed: false
- Approval contract state: approval_required
