# OpenSolar Agent Guide

This file applies to the whole repository. Its purpose is to keep concurrent
coding agents aligned on the current Phase 22 verification work. A task-specific
user instruction still takes precedence, but an agent must not silently invent
different status names, evidence standards, or ownership boundaries.

## Current Objective

Phase 22 is establishing executable, atomic-level evidence for the Level 2
feature hierarchy. The feature list is both **as-is** and **to-be**: some
contracts describe behavior that is intentionally not implemented yet.

The workflow is:

1. Understand the intended L2 behavior and its atomic granularity.
2. Determine whether each atomic behavior exists in the current codebase.
3. Bind an exact existing test or generate a deterministic executable test when
   the behavior can be automated.
4. Run the accepted selector and retain real execution evidence.
5. Let the integration owner regenerate the matrix, full workbook, and strict L2
   roll-up. Worker agents do not edit those shared artifacts directly.

## Sources of Truth

Use these sources in this order:

1. The current user/task instruction and explicitly assigned atomic IDs.
2. `docs/integrations/autosci/phase-22-test-report.xlsx` (the **full report**):
   its L2 description and WHAT-contract fields define intended behavior,
   boundaries, inputs, outputs, failure behavior, and approved granularity.
3. The current production code, schemas, entrypoints, and configuration: these
   determine whether the intended behavior is actually implemented.
4. Existing executable tests and their assertions: these determine whether an
   exact reusable binding already exists.
5. `tests/platform/phase22/atomic_feature_matrix.json`: this is a generated work
   queue/report, not an authority that overrides the contract or current code.
6. `docs/integrations/autosci/phase-22-progress-log.md`: this is historical audit
   context. Newer verified evidence supersedes stale counts or conclusions.

The L2-only **brief report** is a derivative status view. Never add atomic rows
to it and never use it as the source of atomic definitions or bindings.

When sources disagree, record the mismatch in the worker result. Do not change
the contract merely to make the current implementation or a convenient test
pass.

## Three Independent Questions

Keep these separate for every atomic feature:

- **Implementation status:** does production code implement the contracted
  behavior? Test code is not implementation evidence.
- **Test-generation status:** is there an accepted existing selector, a newly
  generated selector, a genuine manual oracle, an implementation blocker, or a
  real platform/provider gate?
- **Coverage relationship/result:** does an exact assertion-level binding exist,
  and what happened when that selector was actually run?

An implemented behavior may have no test. A test may exist but fail. A passing
adjacent or representative L2 test does not prove its sibling atomic behaviors.

## Atomic Classification Rules

Classify each assigned atomic behavior into one conceptual bucket. Serialize it
with the exact enum accepted by the current Phase 22 validator; do not invent a
near-synonym.

### Automatable with an existing test

Use only when the selector existed before the current batch and its assertions
directly exercise the atomic input, output, state change, or rejection branch.
Set the coverage relationship to `DIRECT`, or `SHARED_DIRECT` only when one
selector genuinely asserts every listed atomic behavior.

### Automatable with a new test

Generate a focused executable test against a production seam. A test created in
the current batch is new, not "existing." Run it before delivery. A legitimate
contract-revealing failure is recorded as `FAIL`; do not weaken the oracle to
turn current behavior green.

### Manual oracle required

Use only when success inherently requires human or domain judgment that cannot
be reduced to a stable automated assertion. Supply a concrete manual protocol:
input/fixture, steps, required evidence artifact, reviewer decision rule, and
pass/fail criteria. Do not leave it as generic `UNRESOLVED` or `NOT_RUN`.

### Blocked because implementation is absent

Use `BLOCKED_NOT_IMPLEMENTED` only after tracing the named production entrypoints
and showing that the contracted behavior or rejection branch is absent. Cite the
closest implementation and the exact missing behavior. "No existing test" is
not evidence that the function is unimplemented.

### Platform/provider gated

Use a platform/provider gate only when the behavior exists but cannot execute
without a specifically named OS, hardware device, external service, account,
credential, permission, or live provider. Record the exact requirement and the
command needed once it is available. Prefer controlled fakes for deterministic
contract tests when they can prove the behavior without misrepresenting a live
integration.

Configuration already present is not a gate. A missing exact binding after
configuration resolution is a test-binding task, not an environment blocker.

## Implementation and Test Evidence

Every atomic result must distinguish production evidence from test evidence:

- `implementation_file` and `implementation_symbol` point to real product code,
  schemas, or runtime entrypoints.
- `test_file` and `test_selector` point to the assertion-bearing executable
  test.
- `implementation_evidence` explains how the production seam satisfies or fails
  the contract.
- `decision_rationale` explains why the chosen classification and binding are
  exact.

Do not use the generated test file or test function as implementation evidence.
Do not accept tests that merely check file existence, search for symbols, inspect
source text, or duplicate the implementation in the test.

Test oracles must come from the L2 contract. Avoid permissive assertions such as
accepting both success and failure, arbitrary hard-coded values, or assertions
that only prove the fixture ran. For rejection atomics, assert the observable
failure status/reason and absence of forbidden side effects.

## Test Execution Rules

- Collect and run every new or newly bound selector before calling the batch
  complete.
- Prefer the repository `.venv` and the runner recorded by the existing suite.
- Give parallel pytest runs unique `--basetemp` and cache directories.
- Never redirect stdout/stderr into the same `--basetemp`; pytest deletes that
  directory at startup and Windows will raise `WinError 32` on open log files.
- Record the exact selector, command, exit code, duration, outcome, and concise
  stdout/stderr tail.
- Record `repo_head` with `git rev-parse HEAD`, not by reading `.git/HEAD`.

Classify failures by evidence:

- Assertion reached and failed: `FAIL`.
- Test collection, fixture setup, path construction, or result-recorder bug:
  runner/test-harness error; repair and rerun, not environment blocked.
- A test hard-codes a Unix path on Windows: first treat it as a test portability
  defect unless the product contract itself is platform-specific.
- A specifically proven missing provider/platform requirement: gated with the
  exact requirement.
- Never report `PASS` without exit-code-zero evidence from the named selector.

## Parallel Work and Shared Artifacts

This repository commonly has a dirty worktree and multiple active agents.
Preserve changes outside the assigned scope.

Only the explicitly assigned integration owner may edit or regenerate these
shared artifacts during a parallel run:

- `tests/platform/phase22/atomic_feature_matrix.json`
- `tests/platform/phase22/build_atomic_feature_matrix.py`
- Phase 22 matrix validators under `tests/platform/phase22/`
- `docs/integrations/autosci/phase-22-test-report.xlsx`
- `docs/integrations/autosci/phase-22-progress-log.md`
- the L2-only brief workbook

Worker agents instead write their assigned tests and one isolated result file,
normally under:

`.codex-tmp/phase22-worker-results/<batch-id>/result.json`

Do not copy, rename, overwrite, or synchronize the workbooks from a worker
batch. Do not run a global formatter over shared files. Before editing, inspect
`git status` and the current task ownership; if another agent owns the target,
stop and report the collision.

## Worker Result Quality Gate

Before handoff, verify:

- Assigned atomic IDs are present exactly once and no out-of-scope IDs were
  added.
- Selectors are unique and every selector maps back to its atomic ID(s).
- Existing/new/manual/not-implemented/gated classifications use evidence, not
  absence-of-test guesses.
- All executable selectors were actually run; `NOT_RUN` is truthful and never
  substitutes for a failed runner.
- Generated tests exercise production behavior and have deterministic oracles.
- `git diff --check` passes for changed text files.
- No credentials, `.env` contents, local paths containing secrets, Excel lock
  files, output copies, or scratch artifacts are staged.

## Git and Safety

- Use the current checked-out branch unless the user explicitly requests
  another one. Do not assume the obsolete `pkg/migration` branch.
- Do not push without explicit user approval.
- Stage only the files assigned to the task. Never use destructive resets or
  history rewrites to clean a shared worktree.
- Keep `.codex-tmp/`, rendered inspection output, temporary spreadsheets, Excel
  `~$` lock files, local environments, and credentials out of commits.
- Never touch a real home directory during install/uninstall tests; use an
  isolated temporary home.
- Live-provider tests require explicit authorization and must never print,
  archive, or commit API keys.

The final worker message must state what changed, what was run, exact counts,
remaining blockers, and the path to its isolated result. It must not claim that
the matrix/workbook is synchronized unless the integration owner has completed
and validated that separate step.
