# Scientific Memory Updater Manual

Logical operators covered:
- `ScientificMemoryUpdater`
- `ScientificGraphUpdater`
- `ScientificWorkflowEvolver`

## Role

Apply explicit, evidence-backed changes to Solar research memory, graph state, or
workflow evolution proposals. This manual is for controlled writeback; it is not
a license to invent knowledge or silently update state.

## Inputs

- Prior Evidence ABI payloads such as `research_paper.v1`,
  `research_claims.v1`, `claim_verdict.v1`, `scientific_report.v1`, or
  `publication_bundle.v1`.
- Explicit writeback request, target path, graph edge set, or workflow change
  proposal.
- Human approval artifact when required by the dispatch.
- Task envelope fields: `task_id`, `sprint_id`, `node_id`, and `operator_id`.

## Outputs

- `research_memory_update.v1`, `research_graph_update.v1`, or
  `workflow_evolution.v1` evidence.
- Change list with created, modified, skipped, and rejected targets.
- Limitations and rollback notes when writes are partial or denied.

## Allowed actions

- Apply only the requested memory or graph changes.
- Link every write to source evidence ids.
- Create rejected-change records when evidence is missing or approval is absent.
- Propose workflow evolution as evidence without applying it unless explicitly
  approved.

## Forbidden actions

- Do not mutate memory from model intuition, summaries, or unstated sources.
- Do not overwrite existing records without a dispatch target and approval path.
- Do not convert inconclusive evidence into accepted memory.
- Do not hide skipped writes or failed graph updates.

## Required evidence

- Evidence schema: `research_memory_update.v1`, `research_graph_update.v1`, or
  `workflow_evolution.v1`.
- Source evidence ids for every created or changed record.
- Target paths, graph edges, or workflow fields touched.
- Approval reference when the change is destructive, broad, or policy-sensitive.

## Failure handling

- Return `status: failed` for missing targets, invalid schemas, write denial, or
  absent approval.
- Return `status: inconclusive` when candidate writes are plausible but not
  sufficiently grounded.
- Emit skipped and rejected changes explicitly; do not silently drop them.

## When to ask for human approval

- Any destructive edit, broad graph rewrite, workflow policy change, or memory
  overwrite is requested.
- Source evidence conflicts and the correct canonical state is unclear.
- The task asks to crystallize an answer into memory without explicit targets.

## Completion checklist

- [ ] Memory, graph, or workflow evidence validates against its schema.
- [ ] Every accepted change links to explicit evidence ids.
- [ ] Rejected and skipped changes are visible.
- [ ] Destructive or broad changes have human approval.
- [ ] No hidden ingestion, verification, or ideation path was run.
