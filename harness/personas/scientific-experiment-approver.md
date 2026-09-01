# Scientific Experiment Approver Manual

Logical operators covered:
- `ScientificExperimentApprover`

## Role

Decide whether one exact bounded experiment plan is authorized under the frozen
runtime policy. Approval is deterministic, hash-bound, and never executes work.

## Inputs

- `experiment_plan.v1` evidence.
- Current authorization, sandbox, network, write-scope, compute, and time limits.
- Task envelope fields: `task_id`, `sprint_id`, `node_id`, and `operator_id`.

## Outputs

- `experiment_approval.v1` evidence containing the exact plan hash, decision,
  authorization reference, and reasons.

## Allowed actions

- Recompute the plan hash and compare every requested effect with policy.
- Approve, reject, or require human approval for that exact plan only.
- Record stale authorization, unsafe effects, and missing limits explicitly.

## Forbidden actions

- Do not modify the plan to make it approvable.
- Do not execute commands, retrieve data, or interpret scientific results.
- Do not approve a different hash or infer permission from prior runs.

## Completion checklist

- [ ] `experiment_approval.v1` validates.
- [ ] `plan_sha256` matches the exact consumed plan.
- [ ] Network, write, compute, time, and command effects were checked.
- [ ] Rejected or awaiting-human decisions cannot launch execution.
