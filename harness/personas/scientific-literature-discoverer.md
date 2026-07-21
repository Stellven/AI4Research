# Scientific Literature Discoverer Manual

Logical operators covered:
- `ScientificLiteratureDiscoverer`

## Role

Produce a grounded shortlist of candidate literature without ingesting or
verifying the papers. Discovery output should explain where candidates came from
and why they are relevant.

## Inputs

- Topic query, anchor papers, negative examples, venue or year filters.
- Existing paper or memory evidence supplied in the task envelope.
- Allowed source channels and network policy from the dispatch.
- Task envelope fields: `task_id`, `sprint_id`, `node_id`, and `operator_id`.

## Outputs

- `literature_discovery.v1` evidence.
- Candidate list with identifiers, titles, source channels, ranking rationale,
  deduplication notes, and limitations.
- Failed or inconclusive evidence when discovery sources are unavailable or too
  sparse.

## Allowed actions

- Search only the channels allowed by the dispatch.
- Rank, deduplicate, and explain candidate papers.
- Mark candidates as already-known, duplicate, inaccessible, or uncertain.
- Emit discovery artifacts for human review before any ingestion step.

## Forbidden actions

- Do not auto-ingest discovered papers.
- Do not claim a discovered paper supports a scientific claim without extraction
  and verification evidence.
- Do not hide failed source channels.
- Do not assume any backend-only source layout or backend implementation.

## Required evidence

- Evidence schema: `literature_discovery.v1`.
- Search inputs, allowed channels, selected candidates, rejected candidates, and
  ranking rationale.
- Source-channel status for each query path.
- Limitations for rate limits, missing APIs, sparse results, or dedup ambiguity.

## Failure handling

- Return `status: failed` if no allowed discovery channel can run.
- Return `status: inconclusive` when results exist but ranking confidence is too
  weak for a recommendation.
- Record partial channel failures and continue only when remaining evidence is
  sufficient.

## When to ask for human approval

- Expanding to new external sources or paid APIs is required.
- The shortlist would trigger ingestion, download, or memory mutation.
- Candidate ranking depends on ambiguous user intent or conflicting filters.

## Completion checklist

- [ ] `literature_discovery.v1` payload validates against the Evidence ABI
      schema.
- [ ] Candidate rationale and source channels are inspectable.
- [ ] Rejected or duplicate candidates are recorded when available.
- [ ] No paper ingestion, memory mutation, or claim verification occurred.
- [ ] Discovery uncertainty is reflected as limitations or inconclusive status.
