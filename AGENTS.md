# OpenSolar Agent Guide

This file applies to the whole repository. It aligns agents on the current
Phase 22 verification strategy. A task-specific user instruction takes
precedence.

## Current Objective

Phase 22 now uses a three-layer test strategy. The goal is to show which real
user tasks OpenSolar can complete, while retaining the earlier atomic work for
regression and diagnosis.

1. **Real-task journey tests are the primary acceptance evidence.** A small set
   of end-to-end tasks uses realistic inputs, runs production entrypoints, and
   retains user-visible outputs and logs.
2. **Reliable existing tests are the regression layer.** They run before or
   after journeys to detect breakage and help localize failures. They do not by
   themselves establish the final product verdict.
3. **The atomic inventory is the diagnostic layer.** The full workbook and
   atomic matrix preserve detailed behavior, test, implementation, platform,
   and known-limitation evidence. Phase 22 no longer requires every atomic row
   to have an exact executable selector before the journey report can finish.

Do not resume a campaign to complete all atomic bindings unless the user
explicitly requests it.

## Canonical Artifacts

- Human-readable journey plan:
  `tests/journeys/phase22/journey-test-plan.md`
- Journey test code:
  `tests/journeys/phase22/code/`
- Reusable journey fixtures:
  `tests/journeys/phase22/fixtures/`
- Local raw run evidence:
  `outputs/phase22-real-journeys/<run-id>/`
- Final journey report:
  `docs/integrations/autosci/phase-22-journey-test-report.md`
- Detailed diagnostic workbook, called the **full report**:
  `docs/integrations/autosci/phase-22-test-report.xlsx`
- Historical decision and execution log:
  `docs/integrations/autosci/phase-22-progress-log.md`
- Level-2 stakeholder summary, called the **brief report**:
  `C:/Users/j50058254/Downloads/AI4RnD Feature List.xlsx`

The brief report remains part of the required reporting workflow. It contains
Level 2 results only and must never contain atomic rows. It is synchronized from
accepted journey results, not used as a source of atomic definitions.

## Sources of Truth

Use these sources in order:

1. Current user/task instruction.
2. The journey plan and its stated task, input, success conditions, and mapped
   Level 2 features.
3. Current production code, schemas, entrypoints, and configuration.
4. Current journey run evidence: commands, exit codes, outputs, logs, generated
   artifacts, environment, and Git commit.
5. Reliable regression tests and their actual execution evidence.
6. The full report and atomic matrix as diagnostic references.
7. The progress log as historical context.

When sources disagree, preserve and report the disagreement. Do not weaken a
success condition or delete a known limitation merely to turn a result green.

## Journey Result States

Use these conceptual states in the journey report and brief report:

- `PASS`: the realistic task completed and its minimum observable success
  conditions were met.
- `PASS_WITH_KNOWN_LIMITATIONS`: the core task completed, but a real non-core
  variant, edge case, or limitation remains.
- `FAIL`: an implemented path failed or the produced result did not meet the
  task's minimum success conditions.
- `NOT_TESTED`: no accepted journey exercised the feature or variant.
- `ENVIRONMENT_BLOCKED`: a specifically named platform, hardware, credential,
  account, permission, or provider prevented execution.
- `NOT_AVAILABLE`: the required product behavior is not implemented.

A journey may prove only the feature paths that it actually exercised. Never
copy a green result to file formats, platforms, providers, failure branches, or
other variants that the journey did not use.

## Minimum Journey Evidence

Every accepted journey must record:

- journey ID and task description;
- realistic input or fixture;
- exact production command or entrypoint;
- required environment and configuration, without secrets;
- minimum observable success conditions;
- Level 2 features actually exercised;
- exit code and concise stdout/stderr evidence;
- generated artifact paths and basic usability checks;
- Git commit and run ID;
- final result and known limitations.

Do not pass a journey merely because a process started or a file exists. Check
that the intended input was processed and that the resulting artifact is
non-empty, structurally usable, and relevant to the requested task.

## How Old Atomic Failures Affect Journeys

An old atomic failure does not automatically fail a successful journey, but it
must not be silently ignored. Triage it once:

1. If it affects a core journey step, data integrity, privacy, security, or the
   truthfulness of the result, the journey is `FAIL`.
2. If it is a real edge case or unexercised variant, the journey may be
   `PASS_WITH_KNOWN_LIMITATIONS`; retain the limitation in the full report and
   summarize it in the journey report.
3. If the old test has a broken fixture, runner, path assumption, or incorrect
   expected result, quarantine or repair the test. Do not record it as a product
   failure.
4. If the journey did not exercise the behavior, record that behavior as
   `NOT_TESTED`; do not infer a pass.

Use the old atomic tests after a journey failure to narrow the cause. Add a
small regression test when fixing a journey-blocking defect so the same defect
does not return.

## Full Report and Atomic Evidence

The full report remains the detailed known-limitation and diagnostic record. It
keeps the existing independent fields for implementation, test generation,
coverage relationship, and current result. Existing atomic enums remain valid
inside that report and its generator; journey statuses do not overwrite their
meaning.

Only integrate worker evidence that has been reviewed and actually run. A test
or worker-result file is not accepted evidence merely because it exists. Record
unaccepted attempts as review notes rather than converting them into product
PASS or FAIL results.

The generated atomic matrix is a diagnostic work queue/report. It does not
override the journey plan, current code, or actual journey evidence.

## Test Execution Rules

- Prefer the repository `.venv` and the runner used by the existing suite.
- Give parallel pytest runs unique `--basetemp` and cache directories.
- Never redirect logs into the same `--basetemp` directory.
- Use sandbox homes for install, uninstall, privacy, and configuration tests.
- Record exact commands, exit codes, durations, and concise output tails.
- Record `repo_head` with `git rev-parse HEAD`.
- An assertion failure is `FAIL`; a broken fixture or runner must be repaired
  and rerun rather than mislabeled as an environment block.
- A Unix-only path in a cross-platform test is first a test portability defect
  unless the product requirement is explicitly platform-specific.
- Live-provider tests require explicit user authorization and must never print,
  archive, or commit credentials.

## Parallel Work and Shared Artifacts

This repository commonly has a dirty worktree and concurrent agents. Preserve
changes outside the assigned scope.

Only the explicitly assigned integration owner may edit or regenerate:

- `tests/platform/phase22/atomic_feature_matrix.json`
- the Phase 22 matrix/workbook generators and validators;
- `docs/integrations/autosci/phase-22-test-report.xlsx`;
- `docs/integrations/autosci/phase-22-progress-log.md`;
- `docs/integrations/autosci/phase-22-journey-test-report.md`;
- the brief report.

Worker agents write only their assigned journey tests, fixtures, and isolated
result files unless explicitly given integration ownership. A normal worker
result belongs under `.codex-tmp/phase22-worker-results/<batch-id>/result.json`.

Before editing, inspect `git status` and current ownership. Do not copy, rename,
or overwrite shared workbooks from a worker batch.

Every accepted Phase 22 test, status change, report synchronization, product or
test repair, superseded decision, and remaining blocker must be appended to
`docs/integrations/autosci/phase-22-progress-log.md`. Worker agents record their
isolated evidence in `result.json`; the integration owner records the accepted
decision in the shared progress log after review. Do not claim a report is
synchronized until the progress-log entry and report validation both exist.

## Worker Quality Gate

Before handoff, verify:

- assigned journeys or diagnostic IDs are present exactly once;
- generated tests exercise production behavior through defensible assertions;
- all claimed executable tests were actually run;
- failures are separated into product, test/runner, platform/provider, and
  not-implemented causes;
- outputs and limitations are recorded truthfully;
- `git diff --check` passes for changed text files;
- no credentials, `.env` contents, Excel lock files, local output copies, or
  scratch artifacts are staged.

The final worker message must state what changed, what was run, exact counts,
remaining limitations, and the isolated result path. It must not claim that a
shared report is synchronized unless the integration owner has regenerated and
validated it.

## Git and Safety

- Use the current checked-out branch unless the user asks otherwise.
- Do not push without explicit user approval.
- Stage only files assigned to the current task.
- Never use destructive resets or history rewrites to clean a shared worktree.
- Keep `.codex-tmp/`, rendered inspections, temporary spreadsheets, Excel
  `~$` files, local environments, and credentials out of commits.
- Never touch the real home directory during install or uninstall tests.

### Required Pre-Push Integration Gate

Before pushing `openJiuwen-Solar` to either `origin` or `stellven`, treat that
branch as the sole publishing branch and complete all of the following checks:

1. Fetch and prune both remotes. Verify that the current
   `origin/openJiuwen-Solar` and `stellven/openJiuwen-Solar` tips are ancestors
   of the candidate local `openJiuwen-Solar` tip.
2. Maintain an explicit ledger of candidate fixes using immutable commit
   hashes. Classify each candidate individually as `accepted`, `superseded`,
   `obsolete`, or `rejected`, with a reason or replacement hash. Only fixes
   explicitly marked `accepted` may be integrated. For each accepted fix,
   verify with `git merge-base --is-ancestor` that its exact commit is reachable
   from the candidate publishing tip.
3. If an accepted fix was cherry-picked or squashed, record the original and
   integrated commit hashes, verify the integrated hash is reachable, and
   review patch equivalence. Never treat a similar subject line as proof.
4. Review `git branch --no-merged openJiuwen-Solar` as an inventory only.
   Never bulk-merge all local branches, all worktree branches, or every branch
   reported by `--no-merged`; the existence of a branch is not approval to
   integrate it. Classify each relevant branch and integrate only its
   individually reviewed fixes that the ledger marks `accepted`.
5. Require a clean publishing worktree, relevant passing tests, and explicit
   user approval. Block the push if any accepted fix or remote tip is missing
   or its disposition is unclear.
6. Push the same verified `openJiuwen-Solar` commit to both remotes, then fetch
   and verify that both remote branch tips resolve to that exact commit. Never
   force-push unless the user explicitly authorizes the specific history
   rewrite after reviewing its impact.
