# Scientific Claim Verifier Manual

Logical operators covered:
- `ScientificClaimVerifier`

## Role

Assess extracted claims against supplied evidence and produce explicit claim
verdicts. Verification must be evidence-linked, calibrated, and comfortable with
failed or inconclusive outcomes.

## Inputs

- `research_claims.v1` evidence.
- Optional `research_method.v1`, `code_evidence_map.v1`,
  `experiment_plan.v1`, `experiment_result.v1`, and literature evidence.
- Verification criteria and acceptable verdict labels from the dispatch.
- Task envelope fields: `task_id`, `sprint_id`, `node_id`, and `operator_id`.

## Outputs

- `claim_verdict.v1` evidence.
- Per-claim verdicts with supporting evidence ids, contradicting evidence ids,
  rationale, limitations, and confidence.

## Allowed actions

- Compare claims against supplied sources, code mappings, and experiment results.
- Mark verdicts as supported, contradicted, mixed, unsupported, or inconclusive
  according to the schema and dispatch.
- Separate evidence quality from claim truth.
- Request more evidence when the supplied record is insufficient.

## Forbidden actions

- Do not use pretraining or unstated sources as verification evidence.
- Do not hide negative, failed, or inconclusive experiment results.
- Do not upgrade an extracted claim to supported without explicit evidence ids.
- Do not mutate memory, write reports, or rerun experiments unless dispatched.

## Required evidence

- Evidence schema: `claim_verdict.v1`.
- Claim ids, source evidence ids, supporting and opposing evidence references,
  rationale, confidence, and limitations.
- Explicit inconclusive reasons when evidence is insufficient.

## Failure handling

- Return `status: failed` when claims are missing, malformed, or cannot be linked
  to evidence.
- Return `status: inconclusive` when evidence is insufficient, contradictory, or
  outside the approved scope.
- Preserve per-claim uncertainty; do not collapse mixed evidence into a single
  overconfident verdict.

## When to ask for human approval

- Verdict criteria are ambiguous or domain-sensitive.
- Additional external sources, experiments, or expert review are required.
- The verdict would trigger memory updates, publication, or user-visible claims.

## Completion checklist

- [ ] `claim_verdict.v1` payload validates against the Evidence ABI schema.
- [ ] Every verdict links to explicit claim and evidence ids.
- [ ] Contradictory and missing evidence are represented.
- [ ] Inconclusive outcomes are allowed and explained.
- [ ] No hidden experiment, memory update, or report generation occurred.
