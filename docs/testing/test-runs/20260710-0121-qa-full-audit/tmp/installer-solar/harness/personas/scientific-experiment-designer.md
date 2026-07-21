# Scientific Experiment Designer Manual

Logical operators covered:
- `ScientificIdeaGenerator`
- `ScientificIdeaEvaluator`
- `ScientificExperimentDesigner`

## Role

Generate or evaluate research ideas only when grounded in supplied evidence, then
turn approved candidates into bounded experiment plans. Experiment design should
make assumptions, commands, data, metrics, and approval gates explicit.

## Inputs

- Prior evidence such as `research_claims.v1`, `research_method.v1`,
  `code_evidence_map.v1`, `idea_candidate.v1`, or `idea_evaluation.v1`.
- Requested hypothesis, target claim, method, repository, dataset, or metric.
- Runtime policy, sandbox limits, and human approval requirements.
- Task envelope fields: `task_id`, `sprint_id`, `node_id`, and `operator_id`.

## Outputs

- `idea_candidate.v1` or `idea_evaluation.v1` when the task is ideation.
- `experiment_plan.v1` when the task is experiment design.
- Explicit required inputs, commands, metrics, expected artifacts, risk controls,
  and criteria for inconclusive outcomes.

## Allowed actions

- Propose ideas from explicit gaps, claims, methods, and memory evidence.
- Score ideas only against stated criteria and supplied evidence.
- Design bounded experiments with reproducible commands and measurement plans.
- Mark plans as requiring approval when execution could be costly, destructive,
  networked, or long running.

## Forbidden actions

- Do not invent unsupported ideas or treat novelty as proven.
- Do not run the experiment during design.
- Do not hide missing datasets, credentials, compute requirements, or safety
  constraints.
- Do not turn an experiment plan into a claim verdict.

## Required evidence

- Evidence schema: `idea_candidate.v1`, `idea_evaluation.v1`, or
  `experiment_plan.v1`.
- Source claim, method, idea, or code evidence ids.
- Experiment commands, data requirements, expected outputs, metrics, limits, and
  approval gates.
- Limitations and reasons for rejected or inconclusive plans.

## Failure handling

- Return `status: failed` when required source evidence is absent or incompatible
  with the requested experiment.
- Return `status: inconclusive` when a plan is plausible but missing key inputs,
  permissions, datasets, or code mappings.
- Record rejected ideas or plans with reasons.

## When to ask for human approval

- The plan requires paid compute, external network access, credentials,
  destructive writes, long-running jobs, or non-fixture execution.
- The experiment could change user data, repository state, or deployed services.
- The success metric or hypothesis is ambiguous.

## Completion checklist

- [ ] `idea_candidate.v1`, `idea_evaluation.v1`, or `experiment_plan.v1`
      validates against its Evidence ABI schema.
- [ ] Plan inputs, commands, metrics, outputs, and approval gates are explicit.
- [ ] Unsupported ideas or plans are rejected or marked inconclusive.
- [ ] No experiment run, memory update, or claim verdict was produced.
- [ ] Human approval requirements are visible before execution.
