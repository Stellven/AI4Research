# Phase 0 Research Orchestration Contract

This contract freezes the generic research orchestration boundary for Phase 0.
It is intentionally about contracts, schemas, architecture boundaries, and
validators only. It does not define runtime behavior, route wiring, workflow
templates, or reports.

## Ownership Boundary

Solar is the only global orchestrator for research runs. Solar owns task
planning, graph state, node readiness, evaluation gates, resume/import
decisions, and committed run state.

Codex and AutoSci physical operators are bounded workers. They receive a typed
node request, operate only inside the declared authorization and artifact
scopes, and return a typed node result. A physical operator does not own the
research lifecycle, cannot silently advance graph state, and cannot convert its
self-report into acceptance.

The normal evidence flow is:

1. `execute`: Solar dispatches a typed node request to a bounded worker.
2. `evidence`: the worker returns typed artifacts, evidence, hashes, usage,
   errors, limitations, and a secret-redaction assertion.
3. `evaluate`: Solar evaluates the returned evidence through the appropriate
   validator or gate.
4. `commit state`: Solar commits node and run state after evaluation.

Supplied evidence is only admissible for `resume` and `import_evidence` modes.
It cannot be used as a pre-existing node result for a new `execute` run. An
`execute` run must create or evaluate fresh node evidence through the normal
flow above.

## Public Enums

These enum values are public contracts and must not be renamed without a new
version:

- `seed_kind`: `url`, `pdf`, `markdown`, `topic`, `research_brief`,
  `external_evidence`
- `workflow_kind`: `research_synthesis`, `paper_ingestion`,
  `literature_synthesis`, `scientific_lifecycle`, `workflow_evolution`
- `run_mode`: `execute`, `resume`, `import_evidence`
- `node_status`: `pending`, `ready`, `running`, `awaiting_human`,
  `awaiting_external`, `completed`, `failed`, `blocked`, `cancelled`
- `run_status`: `pending`, `running`, `awaiting_human`,
  `awaiting_external`, `completed`, `failed`, `blocked`, `cancelled`

## Contract Documents

`research_task_contract.v1` is the run-level request accepted by Solar. It
contains `task_id`, `run_id`, `user_intent`, `seed_inputs`, `deliverable`,
`workflow_kind`, `run_mode`, `constraints`, provider/platform requirements, and
success criteria. If `run_mode` is `execute`, imported or supplied evidence is
forbidden. If the task is a resume or evidence import, imported evidence must be
declared with provenance.

`research_node_request.v1` is the Solar-to-worker dispatch envelope. It
contains task, run, workflow, and node IDs; logical and physical operator IDs;
typed inputs; input artifact references; scoped authorization; allowed read and
write scopes; and timeout/retry policy. Live-provider authorization is valid
only when network access is enabled and an explicit approval reference is
present.

`research_node_result.v1` is the worker-to-Solar result envelope. It contains a
terminal or nonterminal node status, output artifacts, evidence references and
payload summaries, hashes, model/provider usage, concise errors, limitations,
and a secret-redaction assertion. A terminal status is one of `completed`,
`failed`, `blocked`, or `cancelled`; a nonterminal status is one of `pending`,
`ready`, `running`, `awaiting_human`, or `awaiting_external`. A completed node
must carry evidence and cannot carry errors; a failed node must carry a concise
error record.

`research_run_state.v1` is the Solar-owned committed state document. It contains
graph identity, node states, ready nodes, current blockers,
resume/import provenance, and final run status. The final status is a generic
`run_status` value and must not depend on a dedicated evidence schema name such
as `real_data_research`. A completed run requires every required node to be
completed with a result reference, every optional node to be terminal, no
current blockers, and at least one final status evidence reference.

## Reuse From Real Data Research

The following specialized `real_data_research` ideas are reusable in the
generic architecture:

- explicit source provenance and source hashes;
- artifact references instead of large inline blobs;
- provider/platform requirements and limitations;
- evaluator-owned acceptance rather than worker-owned acceptance;
- resume provenance that explains which artifacts came from earlier runs.

The following specialized ideas must not enter the generic architecture:

- hard-coded source channels, publishers, domains, years, or locale assumptions;
- fixed language or length requirements that only fit one report format;
- schema names that define final run status;
- direct coupling between a physical operator and lifecycle ownership;
- supplied evidence treated as the output of a new execution.

## Non-Goals

This Phase 0 contract does not implement runtime dispatch, route registration,
workflow mutation, live provider execution, report synchronization, or
historical Phase 22 artifact updates.
