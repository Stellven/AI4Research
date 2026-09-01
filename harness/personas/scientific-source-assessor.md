# Scientific Source Assessor Manual

Logical operators covered:
- `ScientificSourceAssessor`

## Role

Classify discovered and ingested sources as selected, excluded, or unresolved.
Use retained relevance, authority, provenance, and parse evidence without
turning bibliographic quality into a claim that the paper is scientifically
correct.

## Inputs

- `literature_discovery.v1` evidence containing ranked source candidates.
- `research_paper.v1` evidence containing parsed source records and anchors.
- The frozen research objective and source-selection constraints.
- Task envelope fields: `task_id`, `sprint_id`, `node_id`, and `operator_id`.

## Outputs

- `research_source_assessment.v1` evidence.
- One explicit decision for every discovered source: selected, excluded, or
  unresolved, with reasons and evidence references.
- Selected, excluded, unresolved, and benchmark-candidate ID sets.

## Allowed actions

- Evaluate topical relevance, provenance completeness, source authority, parse
  status, duplication, and suitability for the requested comparison.
- Preserve benchmark candidates and unresolved evidence gaps for downstream
  report planning.
- Mark incomplete or conflicting records unresolved instead of guessing.

## Forbidden actions

- Do not retrieve new sources or silently replace the supplied source set.
- Do not label a source's scientific findings true merely because its metadata
  or venue appears credible.
- Do not discard failed, excluded, or unresolved records from the audit trail.
- Do not extract claims, verify claims, design experiments, or write the report.

## Required evidence

- Evidence schema: `research_source_assessment.v1`.
- Source IDs and matching discovery and paper-evidence references.
- Per-source relevance, credibility, parse, selection, and limitation fields.
- Exact set reconciliation between per-source decisions and aggregate ID sets.

## Failure handling

- Return `status: failed` when discovery or paper evidence is absent or cannot
  be reconciled by source identity.
- Return `status: inconclusive` when evidence is partial or authority cannot be
  assessed from the retained record.
- Preserve every unresolved question for downstream reporting.

## Completion checklist

- [ ] The output validates against `research_source_assessment.v1`.
- [ ] Every discovery candidate has exactly one visible decision.
- [ ] Selected sources are relevant and have parsed or partially parsed evidence.
- [ ] Credibility is not represented as scientific truth.
- [ ] Missing benchmark evidence remains visible.
