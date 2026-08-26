# Scheduler input contract

`scheduler_input.json` is the complete static input to the target scheduler.
It is produced only after planning, capsule binding, physical-candidate binding,
evaluation binding, and policy admission have succeeded.

The scheduler may assume the artifact passed those upstream checks. It still
validates the JSON shape before starting.

## Scheduler decisions

1. Initialize mutable node state in `task_graph_state.json`; never write status
   or lease data into `scheduler_input.json`.
2. A node is ready only when every `depends_on` node has passed.
3. When multiple nodes are ready, higher `priority` runs first. Equal priorities
   may run concurrently when resources allow.
4. For a ready node, test `physical_candidates` in ascending `rank` order
   against current operator availability and resource requirements.
5. If a candidate is available, emit `dispatch_record.json` and
   `lease_record.json`; the selected operator is a runtime output, not frozen
   input.
6. If no candidate is currently available, keep the node queued. Do not invent
   a worker, capsule, evaluator, or dependency.
7. After the permitted attempt budget is exhausted, apply `failure_policy`
   exactly as written.

## Upstream decisions the scheduler cannot change

- logical nodes and dependencies;
- requirement ownership;
- capsule or capsule-composition bindings;
- the ordered set of eligible physical operators;
- artifact inputs and outputs;
- deterministic gates and semantic evaluators;
- resource requirements and allowed effects; and
- terminal failure behavior.

RequirementIR is intentionally not included. The static compiler has already
reduced it to `requirement_ids` attached to executable nodes. Those IDs preserve
traceability without asking the scheduler to interpret user requirements.

The example uses placeholder identifiers and all-zero digests because it is a
design contract, not runtime evidence. In a live run, the contract freezer
hashes the completed scheduler input into `run_contract.frozen.json`.
