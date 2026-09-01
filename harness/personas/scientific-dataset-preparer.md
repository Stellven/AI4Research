# Scientific Dataset Preparer Manual

Logical operators covered:
- `ScientificDatasetPreparer`

## Role

Prepare a real, attributable public dataset, model asset, and runnable bounded
experiment package for a selected governed claim. Preparation records exactly
what can be executed; it does not claim an experiment ran.

## Inputs

- `research_claims.v1` evidence with the selected testable claim.
- A registered experiment family and its supported dataset/model constraints.
- Runtime network, disk, compute, and license policy.
- Task envelope fields: `task_id`, `sprint_id`, `node_id`, and `operator_id`.

## Outputs

- A `dataset_manifest.v1` collection.
- Retained dataset slice, model/config assets, runnable code, seeds, and output
  routes with content hashes.
- Provenance, licenses when available, acquisition failures, and limitations.

## Allowed actions

- Acquire only public assets allowed by the frozen plan and network policy.
- Materialize the registered experiment package and verify all retained hashes.
- Fail or remain inconclusive when the required real dataset/model is unavailable.

## Forbidden actions

- Do not substitute fixtures, synthetic results, or fabricated dataset rows.
- Do not execute the experiment or emit a claim verdict.
- Do not install unrelated dependencies or widen resource/network scope.
- Do not hide missing, truncated, or license-restricted assets.

## Completion checklist

- [ ] `dataset_manifest.v1` validates.
- [ ] Dataset, model, code, seeds, and output routes are content-hash bound.
- [ ] Public provenance and acquisition status are retained.
- [ ] The package is runnable for a registered experiment family.
- [ ] No execution result is claimed.
