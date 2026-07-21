# Scientific Paper Ingestor Manual

Logical operators covered:
- `ScientificPaperIngestor`
- `ScientificPaperAnalyzer`

## Role

Turn a bounded paper source into Solar Evidence ABI records that other scientific
operators can trust. Preserve provenance, source anchors, and limitations.

## Inputs

- Paper source path, URL artifact, PDF text extraction, or markdown source.
- Optional metadata hints such as title, authors, venue, year, DOI, arXiv id, or
  source collection.
- Task envelope fields: `task_id`, `sprint_id`, `node_id`, and `operator_id`.
- Prior evidence only when explicitly attached to the dispatch.

## Outputs

- `research_paper.v1` evidence.
- Artifact entries for normalized paper text, metadata, extraction notes, or
  failure diagnostics.
- Limitations for missing sections, low-confidence extraction, inaccessible
  content, or contradictory metadata.

## Allowed actions

- Normalize supplied paper metadata.
- Extract title, authors, abstract, methods summary, claims, source anchors, and
  citation pointers when present in the source.
- Record unknown fields as missing, incomplete, or inconclusive.
- Emit failed or inconclusive Evidence ABI payloads when the source cannot be
  parsed or the provenance is insufficient.

## Forbidden actions

- Do not invent title, authors, venue, DOI, claims, or citations.
- Do not verify scientific truth during ingestion; verification belongs to
  `ScientificClaimVerifier`.
- Do not fetch new sources unless the dispatch explicitly permits network access
  and lists the retrieval target.
- Do not run a hidden full research workflow or mutate research memory.

## Required evidence

- Evidence schema: `research_paper.v1`.
- Source identifier and source path or artifact reference.
- Provenance with operator id, implementation package, timestamp, and task
  identifiers.
- At least one source anchor or a limitation explaining why anchors are missing.
- Explicit limitations for unreadable pages, OCR uncertainty, missing metadata,
  or partial extraction.

## Failure handling

- Return `status: failed` when the source cannot be opened, decoded, or linked to
  the requested task.
- Return `status: inconclusive` when partial extraction is possible but key
  paper identity or source anchors are uncertain.
- Preserve diagnostic artifacts instead of replacing them with summaries.
- Surface dependency, permission, or format failures without fallback guesses.

## When to ask for human approval

- The source requires credentials, paid access, or network retrieval not listed
  in the dispatch.
- Metadata conflicts materially change paper identity.
- The operator would need to overwrite an existing canonical paper record.
- A downstream task requests truth verification or memory mutation during paper
  ingestion.

## Completion checklist

- [ ] `research_paper.v1` payload validates against the Evidence ABI schema.
- [ ] Source provenance and anchors are present or explicitly limited.
- [ ] Claims are marked as extracted observations, not verified facts.
- [ ] Failure or inconclusive status includes actionable diagnostics.
- [ ] No memory update, graph update, or hidden verification was performed.
