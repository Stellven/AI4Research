# Skill Dispatch Task

- Task ID: `T2`
- Sprint: `N/A`
- Node: `N/A`
- Logical Operator: `N/A`
- Task Type: `N/A`
- Execution Surface: `prompt_guided_cli`
- Template Profile: `cli_tooling`
- Specialization Family: `pdf_cli_artifact`
- Dispatch Strategy: `tool_first_cli_execution`
- Delivery Expectation: `command_log_and_artifact_delta`

## Objective

Use selected skills to complete the task.

## Selected Skills

- skill.nano-pdf

## Resolved Skill Records

- `skill.nano-pdf` level=injectable surface=prompt_guided_cli profile=cli_tooling path=/tmp/nano-pdf/SKILL.md cli_bins=N/A first_cmd=nano-pdf --help verify_cmd=nano-pdf --version cli_template=nano-pdf <args> desc=PDF CLI

## Required Skills

- nano-pdf

## Required Capabilities

- documentation

## Acceptance

- Produce an updated PDF.

## Verification Hooks

- check.skill_dispatch_result_written

## Workflow Phases

- inspect_tool_contract
- run_primary_command_path
- verify_outputs_and_exit_signals
- record_command_evidence

## Output Contract

- Write your main closeout to: `/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/codex-not-run-phase/codex-nr-0276/pytest/test_run_request_writes_prompt0/closeout.md`
- Operator artifacts live next to: `/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/codex-not-run-phase/codex-nr-0276/pytest/test_run_request_writes_prompt0`
- Delivery expectation: `command_log_and_artifact_delta`

## Rules

- Use the selected installed skills as the primary methodology/tooling layer.
- Keep evidence concise and concrete.

## Specialization Discipline

- Preserve citations, links, and visible structure unless the objective explicitly says otherwise.
- Treat the artifact delta as the primary deliverable and call out any irreversible edit risk.

## CLI Execution Discipline

- Prefer the declared CLI/tooling path before improvising a generic workflow.
- Record exact commands, flags, and any file outputs you touched.
- Start with the suggested first command when it helps establish the tool contract.
- Run a lightweight verification command when available and include the outcome in your closeout.
- If the CLI path is blocked, state the blocker explicitly before falling back.
