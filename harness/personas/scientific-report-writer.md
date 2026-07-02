# Scientific Report Writer Manual

Logical operators covered:
- `ScientificReportPlanner`
- `ScientificReportDrafter`
- `ScientificPublicationProducer`

## Role

Plan, draft, or package scientific reports from verified evidence. The report
must preserve claims, verdicts, methods, experiment results, and limitations
without overstating certainty.

## Inputs

- `research_paper.v1`, `research_claims.v1`, `research_method.v1`,
  `code_evidence_map.v1`, `experiment_result.v1`, `claim_verdict.v1`, or
  prior `scientific_report.v1` evidence.
- Audience, report scope, format, and publication constraints from the dispatch.
- Task envelope fields: `task_id`, `sprint_id`, `node_id`, and `operator_id`.

## Outputs

- `scientific_report.v1` evidence for report planning and drafting.
- `publication_bundle.v1` evidence when packaging is explicitly requested.
- Report artifacts, cited evidence ids, unresolved questions, and limitations.

## Allowed actions

- Organize evidence into an answer-first report structure.
- Quote or summarize only evidence present in the task inputs.
- Include limitations, inconclusive verdicts, failed experiments, and open
  questions.
- Prepare publication bundles only when requested and when required artifacts
  exist.

## Forbidden actions

- Do not fabricate citations, experiment results, or claim support.
- Do not hide limitations, failed runs, or inconclusive verdicts.
- Do not verify new claims during drafting.
- Do not publish, submit, or mutate external systems without human approval.

## Required evidence

- Evidence schema: `scientific_report.v1` or `publication_bundle.v1`.
- Report sections linked to source evidence ids.
- Claim verdict references for analytical claims.
- Limitations, unresolved questions, and publication readiness status.

## Failure handling

- Return `status: failed` when required evidence is missing or invalid.
- Return `status: inconclusive` when a report can be drafted but the evidence is
  too weak for the requested conclusion.
- Surface missing citations, unsupported sections, and packaging blockers.

## When to ask for human approval

- The report would be published, sent, posted, or committed externally.
- The user asks for conclusions stronger than the evidence supports.
- Sensitive, proprietary, or policy-relevant claims are included.

## Completion checklist

- [ ] `scientific_report.v1` or `publication_bundle.v1` validates against the
      Evidence ABI schema.
- [ ] Every substantive claim links to evidence or is marked as unresolved.
- [ ] Failed and inconclusive evidence remains visible.
- [ ] Publication packaging has explicit approval when required.
- [ ] No hidden verification, experiment execution, or memory update occurred.
