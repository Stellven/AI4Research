# Pipeline boundary contracts

This directory states what crosses each compiler/runtime boundary. It is design
metadata for maintainers and model prompts; it is not itself runtime authority.

The central rule is:

> Semantic stages exchange typed artifacts. The scheduler receives one frozen,
> executable TaskGraph and may schedule it, but may not redesign it.

The authoritative artifact shapes live under `harness/schemas/`. At runtime,
the content-hashed `run_contract.frozen.json` and its referenced artifacts are
the execution authority.

`pipeline_boundary_contracts.json` records:

- the exact RequirementIR fields the Elastic Planner consumes;
- the separation between PlanIR, CapsulePlan, PhysicalPlan, and EvaluationPlan;
- the frozen TaskGraph fields the scheduler requires;
- the decisions the scheduler is allowed to make; and
- the decisions it must never make at runtime.
