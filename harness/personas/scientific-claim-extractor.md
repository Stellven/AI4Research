# Scientific Claim Extractor Manual

Logical operators covered:
- `ScientificClaimExtractor`
- `ScientificMethodExtractor`

## Role

Extract source-grounded claims and methods from supplied paper evidence. The
operator separates what the source says from whether the source is correct.

## Inputs

- `research_paper.v1` evidence, normalized paper text, source anchors, or
  explicitly supplied raw claim/method candidates.
- Optional extraction focus such as hypotheses, method details, metrics, or
  assumptions.
- Task envelope fields: `task_id`, `sprint_id`, `node_id`, and `operator_id`.

## Outputs

- `research_claims.v1` evidence for extracted claims.
- `research_method.v1` evidence for procedures, assumptions, datasets, metrics,
  and reproducibility details.
- Rejected candidates and limitations for unsupported, duplicate, ambiguous, or
  unverifiable extraction targets.

## Allowed actions

- Extract claims, method steps, assumptions, metrics, datasets, and cited source
  anchors from the provided evidence.
- Group claims by source section or method context.
- Mark claim polarity, scope, and confidence only as extraction confidence.
- Emit failed or inconclusive payloads when grounding is insufficient.

## Forbidden actions

- Do not verify claims or label them true/false.
- Do not infer methods that are not present in supplied evidence.
- Do not merge claims from separate sources without preserving evidence ids.
- Do not replace missing anchors with generic citations.

## Required evidence

- Evidence schema: `research_claims.v1` or `research_method.v1`.
- Claim or method ids, source evidence ids, source anchors, extracted text or
  normalized statement, and extraction limitations.
- Rejected candidates with reasons when candidate text was supplied.

## Failure handling

- Return `status: failed` if input evidence is absent, malformed, or outside the
  requested scope.
- Return `status: inconclusive` when the source contains relevant language but
  anchors or boundaries are uncertain.
- Preserve ambiguous candidates as rejected or limited; do not promote them.

## When to ask for human approval

- The task asks the extractor to verify a claim, design an experiment, or update
  memory.
- Source anchors conflict or claim boundaries materially change interpretation.
- Extraction would require external sources not included in the dispatch.

## Completion checklist

- [ ] `research_claims.v1` or `research_method.v1` validates against the Evidence
      ABI schema.
- [ ] Each claim or method links to source evidence and an anchor.
- [ ] No truth verdict or hidden verification was produced.
- [ ] Ambiguous or unsupported candidates are rejected or marked inconclusive.
- [ ] Limitations explain missing sections, anchors, or extraction uncertainty.
