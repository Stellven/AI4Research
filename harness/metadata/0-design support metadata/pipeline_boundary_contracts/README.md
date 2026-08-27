# Pipeline boundary contracts

This directory states what crosses each compiler/runtime boundary. It is design
metadata for maintainers and model prompts; it is not itself runtime authority.

The central rule is:

> Semantic stages exchange typed artifacts. The scheduler receives one frozen
> `scheduler_input.json` and may schedule it, but may not redesign it.

The authoritative artifact shapes live under `harness/schemas/`. At runtime,
the content-hashed `run_contract.frozen.json` and its referenced artifacts are
the execution authority.

`pipeline_boundary_contracts.json` records:

- the exact RequirementIR fields the Elastic Planner consumes;
- the separation between PlanIR, CapsulePlan, PhysicalPlan, and EvaluationPlan;
- the exact frozen `scheduler_input.json` fields the scheduler requires;
- the decisions the scheduler is allowed to make; and
- the decisions it must never make at runtime.

`scheduler_input.json` is the only direct static input to the target scheduler.
It contains the executable dependency graph plus the already-admitted capsule,
physical-candidate, artifact, evaluator, resource, effect, priority, and failure
contracts. RequirementIR is not a scheduler input. Only requirement IDs survive
for traceability. Mutable node status, selected operators, attempts, and leases
are scheduler outputs and therefore do not appear in this frozen artifact.
