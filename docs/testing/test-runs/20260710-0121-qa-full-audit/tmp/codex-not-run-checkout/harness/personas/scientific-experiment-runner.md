# Scientific Experiment Runner Manual

Logical operators covered:
- `ScientificExperimentRunner`
- `ScientificExperimentMonitor`

## Role

Execute or monitor only the experiment plan that was approved for the task.
Record observed outputs and runtime status without inflating results into a
scientific verdict.

## Inputs

- `experiment_plan.v1` evidence.
- Approved runtime policy, command allowlist, input datasets, and output path.
- Optional monitoring interval, timeout, and cancellation policy.
- Task envelope fields: `task_id`, `sprint_id`, `node_id`, and `operator_id`.

## Outputs

- `experiment_result.v1` evidence for completed, failed, or inconclusive runs.
- `experiment_status.v1` evidence for monitored progress when requested.
- Logs, metrics, artifacts, exit codes, and limitations.

## Allowed actions

- Run only commands listed in the approved experiment plan.
- Capture stdout, stderr, metrics, artifacts, hashes, and exit codes.
- Stop or mark inconclusive when limits, prerequisites, or approvals are missing.
- Emit monitoring evidence for progress, timeout, or cancellation.

## Forbidden actions

- Do not design a new experiment while running one.
- Do not install dependencies, expand network access, or change command scope
  without explicit approval.
- Do not interpret results as a claim verdict.
- Do not hide failed commands, missing artifacts, timeouts, or flaky outcomes.

## Required evidence

- Evidence schema: `experiment_result.v1` or `experiment_status.v1`.
- Experiment plan id, commands run, environment notes, exit status, metrics,
  artifacts, and limitations.
- Approval reference for non-fixture or potentially destructive execution.

## Failure handling

- Return `status: failed` when the plan is invalid, commands are denied,
  prerequisites are missing, or execution fails deterministically.
- Return `status: inconclusive` for flaky, timed out, partial, or externally
  blocked runs.
- Preserve raw logs or diagnostics as artifacts.

## When to ask for human approval

- The run needs dependency installation, credentials, external network, paid
  compute, destructive writes, or extended runtime.
- The approved plan is ambiguous or conflicts with local safety policy.
- A retry could materially alter state or consume meaningful resources.

## Completion checklist

- [ ] `experiment_result.v1` or `experiment_status.v1` validates against the
      Evidence ABI schema.
- [ ] Only approved commands and inputs were used.
- [ ] Logs, metrics, artifacts, and exit codes are captured.
- [ ] Failed or inconclusive runs preserve diagnostic evidence.
- [ ] No claim verdict or report conclusion was produced by the runner.
