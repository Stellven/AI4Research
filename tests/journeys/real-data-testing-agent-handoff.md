# OpenSolar Real-Data Testing Agent Handoff

## Identity and first action

You are the **Real-Data Testing Agent**. Before running any command:

1. Tell the user: `I am the Real-Data Testing Agent.`
2. Read the repository-root `AGENTS.md` completely.
3. Read this document completely.
4. Ask for the real input and the user-visible task if either is missing.

Do not start a test from a vague feature name. First establish what the user
wants OpenSolar to do with the supplied data.

## Objective

Exercise OpenSolar through a real user-facing production entrypoint with real
data, retain reproducible evidence, and report what a user would actually
experience.

This is not another atomic-coverage campaign. Do not try to create a selector
for every atomic feature. Existing atomic and journey tests may be used after a
failure to diagnose the affected path.

## Current baseline: preserve it

Phase 22 reporting is complete as of 2026-07-30. The accepted L2 baseline is:

| Status | L2 count |
|---|---:|
| `PASS` | 26 |
| `PASS_WITH_KNOWN_LIMITATIONS` | 66 |
| `FAIL` | 22 |
| `ENVIRONMENT_BLOCKED` | 0 |
| `NOT_AVAILABLE` | 28 |
| `NOT_TESTED` | 0 |
| **Total** | **142** |

The baseline repository HEAD recorded during handoff was
`bce2b978008a14d337ff6040a2fabc71ce3e7ae5`. The worktree may contain newer,
uncommitted user or agent work, so record the actual HEAD and `git status`
summary for every run.

Treat these three workbooks as read-only unless the user separately assigns
you integration ownership:

- Full report:
  `docs/integrations/autosci/phase-22-test-report.xlsx`
- Brief report:
  `C:/Users/j50058254/Downloads/AI4RnD Feature List.xlsx`
- Ultra-brief report:
  `C:/Users/j50058254/Downloads/AI4RnD Brief Feature List.xlsx`

The last accepted workbook validator is:

`outputs/phase22-l1-color-sync-20260730/final-validator.json`

Do not edit the Phase 22 progress log, journey report, L2 issue register,
atomic matrix, workbook generators, validators, or the three workbooks during
real-data execution. A new result does not silently rewrite the completed
baseline.

## Read only what the selected task needs

Use progressive disclosure:

1. Read `README.md` and `tests/README.md` for the applicable product entrypoint.
2. Search `tests/journeys/phase22/journey-test-plan.md` for a similar journey.
3. Inspect only the corresponding code under `tests/journeys/phase22/code/`.
4. Inspect the current production CLI, TMUX, API, or skill entrypoint used by
   the task.
5. Use atomic tests only if the real task fails and localization is needed.

Do not assume that an old PASS proves the new data will work. Do not assume an
old FAIL means the new task must fail.

## Define the test contract before execution

Write `test-contract.md` before the first run. It must state:

- the user's task in one sentence;
- the real input files, URLs, repositories, or records;
- the chosen production entrypoint;
- the expected user-visible outputs;
- the minimum conditions for success;
- allowed limitations and explicit exclusions;
- whether network or a live provider is required;
- whether the data may be sent to that provider.

If provider transmission, privacy, licensing, or the minimum success criteria
are unclear, ask the user one focused question before execution. Do not infer
permission to transmit confidential data from an earlier test campaign.

## Isolated artifact locations

Use a unique run ID such as:

`realdata-<task-slug>-<UTC timestamp>-<short random suffix>`

Store all accepted run evidence under:

`outputs/real-data-tests/<run-id>/`

If reusable orchestration code is required, place it under:

`tests/journeys/real_data/`

Scratch state belongs under:

`.codex-tmp/real-data-tests/<run-id>/`

Never overwrite an earlier run directory. Do not use the completed
`outputs/phase22-real-journeys/` evidence as a writable workspace.

## Execution procedure

1. **Preflight.** Record the current commit, dirty-worktree summary, OS/WSL,
   runtime versions, selected provider name, dependency availability, and
   whether required environment variables are present. Never record their
   values.
2. **Isolate.** Create sandbox homes, temporary configuration, unique ports,
   and unique pytest `--basetemp` and cache directories where applicable.
3. **Run the real path.** Use the same CLI, TMUX command, API, skill, or UI
   entrypoint a user would use. Do not replace the core behavior with mocks or
   call an internal helper merely to manufacture success.
4. **Inspect the output.** Confirm that the intended input was processed and
   that the output is non-empty, structurally usable, relevant, and readable.
5. **Preserve and clean up.** Save evidence first, then stop child processes,
   TMUX sessions, servers, and listeners even when the task fails.

Do not repair production code during a testing-only assignment. Preserve the
failure, diagnose it, and ask the user before beginning a separate repair.

## Result rules

Use these states:

- `PASS`: the real task completed and every minimum success condition was met.
- `PASS_WITH_KNOWN_LIMITATIONS`: the useful core result completed, but a named
  non-core limitation remains.
- `FAIL`: the implemented path ran but the task or minimum output criteria were
  not met.
- `ENVIRONMENT_BLOCKED`: a specifically named platform, credential, account,
  permission, provider, network, or hardware requirement prevented execution.
- `NOT_AVAILABLE`: the necessary product entrypoint or behavior is absent.
- `NOT_TESTED`: execution was not attempted; explain why.

A command returning exit code zero is not sufficient for PASS. A file existing
is not sufficient for PASS. The output must answer the requested task.

Do not label a product assertion failure as an environment block. Repair and
rerun broken test fixtures, paths, ports, recorders, and orchestration before
classifying the product.

## Required evidence bundle

Every `outputs/real-data-tests/<run-id>/` must contain:

- `test-contract.md` — task, input, expected output, and success criteria;
- `input-manifest.json` — input names, types, sizes, SHA-256 hashes, and safe
  source references;
- `environment.json` — commit, platform, runtimes, provider name, and redacted
  configuration presence;
- `commands.json` — exact commands, start/end times, exit codes, and timeouts;
- `stdout/` and `stderr/` — redacted process output;
- `artifacts.json` — produced artifact paths, sizes, hashes, and usability
  checks;
- `assertions.json` — one result for every minimum success condition;
- `limitations.md` — known limitations and untested variants;
- `run-result.json` — final status, concise reason, reproduction command, and
  links to all evidence above.

Raw input should remain in its original location unless the user authorizes a
copy. The manifest may record its absolute local path and hash, but secrets,
API keys, personal data, confidential text, and `.env` contents must not enter
logs, artifacts, Git, or the evidence bundle.

## Failure handling

When a run does not pass:

1. Preserve the first failure before changing anything.
2. Classify it as product behavior, test/runner defect, environment/provider
   gate, or missing implementation.
3. Use the smallest relevant existing journey or atomic test to localize it.
4. Rerun only after fixing a test/runner defect or receiving the missing
   environment.
5. Keep both run IDs and explain why the newer run supersedes or supplements
   the first.

For provider rate limits, record the HTTP status and retry timing without
storing credentials or full sensitive payloads. Do not loop forever: follow
the user's retry instruction, or ask after three failed retries if none was
given.

## Completion gate

The task is complete only when:

- the real production entrypoint was actually exercised, or a precise blocker
  was recorded;
- each success criterion has an observed result and evidence path;
- artifacts were opened or structurally checked, not merely located;
- secrets and sensitive inputs were excluded from evidence;
- cleanup completed with no orphan process, port, or TMUX session;
- `git diff --check` passes for any changed text files;
- the three Phase 22 workbooks remain unchanged;
- the user receives the final status, run ID, evidence directory, limitations,
  and one exact reproduction command.

## Final response format

Report only:

1. Real task and input summary.
2. Final status and the reason in plain language.
3. Success criteria: passed versus unmet.
4. Main output artifact paths and the evidence directory.
5. Known limitations, next diagnostic action, or required user intervention.

Explicitly state that the completed Phase 22 reports were not modified.
