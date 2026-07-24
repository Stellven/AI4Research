# OpenSolar Global Test Execution Plan

Status: authoritative execution plan for the current full test-report campaign

Canonical branch: `Coconut-ch1ken/OpenSolar:openJiuwen-Solar`

Primary execution host: Windows 11 with native PowerShell and WSL2

Required secondary lane: a smaller, targeted macOS lane

This file is intentionally named with a `0000_` prefix so it appears before
the other files in `tests/` when names are sorted in ascending order.

## 1. Objective

Produce a defensible test report for every current official feature by:

1. approving the feature and atomic-feature hierarchy;
2. binding every atomic test specification to a real executable test or an
   explicit non-executable disposition;
3. executing every ready binding against one frozen canonical commit;
4. retaining reproducible evidence for every result;
5. rolling atomic results up to atomic features, Level 2 features, Level 1
   features, and the final release verdict.

Mapping is not execution. A historical PASS, a plausible filename, or a test
name in a workbook is not a current PASS result.

## 2. Current Planning Baseline

The canonical planning and execution-report workbook is:

`docs/integrations/autosci/phase-22-test-report.xlsx`

Update this workbook in place after each mapping or test-execution batch. Do
not create numbered or thread-specific report copies.

At the time this plan was written, its static inspection reported:

| Item | Count / state |
|---|---:|
| Official Level 2 features | 142 |
| Atomic Feature Registry rows | 2,047 |
| Atomic Test Registry rows | 2,297 |
| Draft-bound/planned atomic tests | 2,047 |
| Unmapped historical tests | 250 |
| Static file-bound atomic-test rows | 30 |
| Missing test implementation rows | 2,267 |
| Test File Binding rows | 263 |
| File-binding rows with unresolved atomic identity | 233 |
| Tracked test source files inspected by the workbook | 55 |
| Source files with direct mapping | 1 |
| Source files with indirect/structural-only mapping | 3 |
| Source files unresolved | 51 |

These numbers are a planning baseline, not execution results. Recalculate and
record them after each mapping or implementation batch.

## 3. Sources Of Truth

Use these sources in this order:

1. the frozen Git commit under test;
2. the official Level 1 and Level 2 hierarchy in the planning workbook;
3. the approved `Atomic Feature Registry`;
4. the reviewed `Atomic Test Registry` and `Test File Binding` sheets;
5. tracked test implementations and runner configuration;
6. evidence produced by the current run;
7. historical workbooks and receipts, for provenance only.

When sources disagree, do not silently choose one. Record the conflict,
identify an owner, and block only the affected rows.

## 4. Required Result Levels

The final report must preserve this traceability chain:

```text
Level 1 feature
  -> Level 2 feature
    -> atomic feature
      -> atomic test registry row
        -> execution binding
          -> execution attempt
            -> evidence manifest
              -> current result
```

No roll-up level may claim better coverage than its children support.

## 5. Execution Binding Contract

An atomic test is execution-ready only when its binding contains all required
fields below.

| Field | Requirement |
|---|---|
| Atomic Test Registry ID | Stable, unique ID from the workbook. |
| Feature lineage | Official sheet, Level 1, Level 2, and Atomic Feature ID. |
| Scenario identity | Exact positive, negative, edge, evidence, or lifecycle behavior. |
| Test implementation | Tracked repository path or an explicitly documented manual procedure. |
| Test selector | Function, parameter ID, node ID, script section, or manual case ID. |
| Coverage relationship | `DIRECT`, `SHARED_DIRECT`, `INDIRECT`, or `UNRESOLVED`. |
| Runner command | Exact command, working directory, and required environment variables. |
| Platform lane | Windows native, Windows WSL2, macOS, CI/Linux, cross-platform primary, or manual/external. |
| Prerequisites | Runtime, packages, services, credentials, fixtures, network, and provider state. |
| Isolation contract | Temporary HOME, sandbox checkout, ports, cleanup, and side-effect limits. |
| Expected result | Observable output, exit status, artifact, state transition, or rejection behavior. |
| Expected evidence | Required logs, JSON, screenshots, artifacts, hashes, and before/after state. |
| Timeout and retry rule | Maximum duration and whether a retry is permitted. |
| Mapping basis | Code/assertion evidence that justifies this atomic-test mapping. |
| Review state | Reviewer and `APPROVED`, `REVISE`, `REJECTED`, or `PENDING`. |

Binding rules:

- Every executable atomic-test row must have at least one approved binding.
- One physical test may cover multiple atomic rows only when each asserted
  behavior is independently identifiable in the test and evidence.
- One atomic row may have multiple bindings when platform or configuration
  variants are required.
- `INDIRECT` coverage cannot be promoted to `DIRECT` without assertion-level
  evidence.
- A missing prerequisite is `BLOCKED_ENV`, not
  `MISSING_TEST_IMPLEMENTATION`.
- A real test file with no defensible atomic identity remains
  `UNRESOLVED_TEST_FILE_MAPPING`.
- Historical result fields never populate the current result field.

## 6. Platform-Lane Policy

Most execution will occur on the Windows machine. This is the default because
that host can cover native PowerShell, the supported Windows-to-WSL2 boundary,
and the majority of platform-neutral Python, Bash, and TypeScript tests inside
WSL2.

The full report must still include a smaller macOS-specific lane. Windows and
WSL2 cannot prove Darwin, launchd, macOS package, or native macOS filesystem
behavior.

### 6.1 Windows Primary Lane

Run the following on Windows unless a binding proves another platform is
required:

- all `WINDOWS_POWERSHELL` bindings with PowerShell and Pester 5+;
- all `WINDOWS_WITH_WSL` bindings in the designated WSL2 distribution;
- platform-neutral pytest suites;
- platform-neutral Bun/Node suites;
- shell, CLI, harness, AutoSci, ingestion, orchestration, evaluator, and gate
  tests that operate correctly in WSL2;
- Windows installer, reboot-resume, autostart, path quoting, long-path, CRLF,
  host-to-WSL networking, and portable desktop executable tests;
- the primary full Solar intake to autonomous AutoSci end-to-end run;
- the majority of negative, edge, stress, and evidence-schema cases.

`CROSS_PLATFORM_CANDIDATE` means Windows/WSL2 is the primary execution lane;
it does not mean the row has already been proven cross-platform.

### 6.2 Required macOS Lane

The macOS lane is intentionally smaller and targeted. It must include:

- installer and uninstall smoke with an isolated HOME;
- the macOS system Bash 3.2 compatibility leg plus the supported live-harness
  Bash configuration;
- launchd/LaunchAgent rendering, registration, start, status, and removal;
- macOS-only components such as Calendar integration when enabled;
- executable-bit, permission, symlink, case-sensitivity, and LF behavior that
  differs from Windows checkouts;
- DMG build/package verification and at least one real launch smoke;
- tmux cockpit startup and one official-intake Solar runtime smoke;
- one targeted Solar intake to AutoSci integration regression, including
  evaluator/gate evidence;
- a compact shared smoke set covering core CLI, harness startup, and status
  reporting.

The Mac does not need to duplicate every platform-neutral Windows test. It
must execute every binding classified `MACOS_REQUIRED` or `DARWIN_ONLY`, plus
the shared smoke set above.

### 6.3 CI/Linux Lane

CI provides repeatable clean-host checks for static validation, unit tests,
installation matrices, packaging, privacy, and repository hygiene. CI results
may satisfy a binding only when the workflow, job, tested commit, and retained
evidence directly match that binding.

CI does not replace real-machine proof for interactive login, native desktop
launch, launchd, Windows reboot-resume, live WSL networking, credentials, or
external providers.

### 6.4 Manual And External Lane

Use this lane for live providers, accounts, regional restrictions, browser
approval, destructive external writes, real hardware, and other scenarios
that cannot be made deterministic. Each row still requires exact steps,
expected evidence, and a named blocker when not executed.

## 7. Environment And Reproducibility Rules

Before any execution batch:

1. fetch `Coconut-ch1ken/OpenSolar`;
2. check out the exact approved `openJiuwen-Solar` commit;
3. record `git rev-parse HEAD` and require a clean `git status --porcelain`;
4. record OS, architecture, shell, Python, Bun/Node, PowerShell/Pester, WSL,
   tmux, and relevant provider versions;
5. install only declared dependencies and record their locked versions;
6. use temporary HOME and application-data directories for lifecycle tests;
7. never run install/uninstall/reset tests against the real user HOME;
8. keep credentials outside Git and redact them from logs;
9. reserve ports deterministically and clean up started processes;
10. stop the batch if the checked-out commit changes.

Both machines must test the same commit. Results from different commits remain
separate runs and cannot be combined into one release verdict.

## 8. Evidence Storage Contract

Raw evidence must remain outside the source checkout, for example:

```text
OpenSolar-QA-Evidence/
  <tested-commit>/
    <run-id>/
      windows-native/
      windows-wsl2/
      macos/
      ci-linux/
      manual-external/
```

Every execution attempt must have a manifest containing:

- atomic-test ID and binding ID;
- tested commit and dirty-state check;
- platform, host lane, and tool versions;
- exact command or manual steps;
- start/end timestamps and duration;
- exit code and normalized result;
- stdout/stderr or equivalent log paths;
- produced artifact paths and hashes;
- cleanup status;
- defect ID or blocker reason when applicable.

Do not commit raw logs, caches, browser profiles, virtual environments,
credentials, screenshots, or per-attempt evidence to `docs/testing/test-runs/`.
A curated report may be committed only after privacy review.

## 9. Result Vocabulary

Use only these current-run statuses:

| Status | Meaning |
|---|---|
| `PASS` | Current execution met every pass criterion with valid evidence. |
| `FAIL` | Current execution contradicted a pass criterion. |
| `BLOCKED_IMPLEMENTATION` | Required behavior exists in scope but no executable/manual implementation is ready. |
| `BLOCKED_ENV` | Binding exists but a declared environment, dependency, credential, service, or platform is unavailable. |
| `INCONCLUSIVE` | Execution completed but evidence cannot distinguish pass from fail. |
| `SKIPPED_NA` | Reviewed and proven not applicable to the tested product/configuration. |
| `NOT_RUN` | Ready or planned but no current execution attempt exists. |

`SKIPPED_NA` requires a written scope justification. `BLOCKED_ENV` requires the
missing prerequisite and remediation. Neither counts as PASS.

## 10. Defect Severity

| Severity | Definition |
|---|---|
| Blocker | Prevents installation, startup, evidence collection, or broad continuation of testing. |
| Critical | Breaks a primary workflow, safety/security boundary, data integrity, or autonomous gate with no practical workaround. |
| High | Breaks an important Level 2 behavior or platform lane while the broader campaign can continue. |
| Medium | Partial impairment with a documented workaround or limited scope. |
| Low | Cosmetic, documentation, observability, or narrow edge-case defect. |

Every FAIL must reference a defect or an explicitly accepted known issue.

## 11. Ordered Execution Procedure

### Step 0: Freeze The Campaign Baseline

- Select one canonical commit after all required mapping and plan updates.
- Record the workbook blob hash and sheet dimensions.
- Assign a campaign ID and evidence root.
- Confirm both machines can fetch and verify the same commit.

Exit gate: one commit, one workbook version, clean checkouts, evidence roots
created, and no unresolved repository synchronization issue.

### Step 1: Approve Atomic Features

- Review all 2,047 `Atomic Feature Registry` rows against their Level 2 parent.
- Approve, revise, move, merge, split, remove, or add atomic features.
- Resolve duplicates without losing historical provenance.
- Confirm every Level 2 feature has sufficient positive, guardrail, and
  evidence/auditability behavior where applicable.

Exit gate: every in-scope atomic feature has an explicit review decision.

### Step 2: Review Atomic-Test Semantics

- Review the 2,047 draft-bound/planned tests after atomic-feature approval.
- Adjudicate all 250 unmapped historical tests as remap, retain as platform/
  QA coverage, obsolete, duplicate, or out of scope.
- Split tests that assert multiple independent behaviors.
- Add missing boundary, failure, side-effect, and recovery scenarios.
- Freeze stable registry IDs before implementation begins.

Exit gate: all 2,297 registry rows have a reviewed scope disposition.

### Step 3: Perform Repository-Wide Test Discovery

- Scan the entire tracked repository, including legacy suites under
  `harness/tests/`, plugin tests, desktop tests, root `tests/`, scripts, CI
  workflows, and manual verification tools.
- Extract exact selectors and assertions, not just filenames.
- Compare discovered cases to `Test Source Inventory`.
- Add missing source files and cases to the inventory.
- Do not create a new test until existing implementation reuse has been
  checked.

Exit gate: every tracked executable test source has a reviewed inventory row.

### Step 4: Complete Execution Bindings

- Resolve the 233 currently unresolved file-binding rows.
- Bind existing cases to atomic IDs using assertion/code evidence.
- Review the six current indirect mappings.
- For each of the 2,267 current implementation gaps, classify it as:
  existing-but-unmapped, new automated test required, manual test required,
  environment-blocked, not applicable, duplicate, obsolete, or feature not
  found.
- Populate every field in the execution binding contract.
- Assign Windows, Mac, CI, or manual lanes.

Exit gate: no in-scope atomic row has an unexplained blank binding state.

### Step 5: Implement Missing Tests

- Put new tests under the categorized root locations defined in
  `tests/README.md`.
- Prefer deterministic fixtures and mocked providers for the default suite.
- Add live-provider variants only as explicit opt-in tests.
- Add negative and no-side-effect assertions, not only happy paths.
- Keep wrappers thin when a legacy suite already proves the behavior.
- Add collection/syntax tests for every new test module or script.

Exit gate: every automated binding resolves to a tracked file and selector;
every manual binding has reproducible steps and an evidence oracle.

### Step 6: Validate Runner Readiness

- Collect pytest tests without running them.
- Parse shell and PowerShell scripts.
- Enumerate Bun/Node tests.
- Validate fixtures, imports, paths, permissions, timeouts, and cleanup.
- Run one known-pass and one planted-failure control per runner family.
- Confirm evidence manifests are written outside the checkout.

Exit gate: runner failures are separated from product failures.

### Step 7: Run Deterministic Fast Tests

Run static checks, schemas, contracts, pure unit tests, CLI parsing, registry
consistency, mapping integrity, and repository hygiene first. Execute the
majority on Windows/WSL2 and use CI as independent clean-host confirmation.

Exit gate: blockers are triaged before expensive integration runs.

### Step 8: Run Integration And Lifecycle Tests

Run component integration, daemon/status server, installer/uninstaller,
filesystem mutation, orchestration, evaluator/gate, desktop/runtime bridge,
and recovery tests in isolated environments.

Execute Windows-native and WSL2 cases on Windows. Execute the required Darwin,
launchd, Bash 3.2, DMG, and Mac permission cases on macOS.

### Step 9: Run Full Workflow And AutoSci Tests

- Start from the official Solar intake, not a manually invoked AutoSci shim.
- Require the intended workflow contract and DAG.
- Verify the correct AutoSci operators are selected and executed.
- Verify artifacts are passed through declared manifests/envelopes.
- Verify evaluator results become gate-consumable records.
- Run red and green scenarios so a failed verification demonstrably blocks
  the stage and a valid result proceeds.
- Capture intake, intent, graph, operator, artifact, eval, gate, and final
  report evidence.

Windows/WSL2 is the primary full-run lane. macOS performs one targeted full
integration regression rather than duplicating the entire workflow matrix.

### Step 10: Run External, Stress, And Manual Cases

Run approved live-provider, network, geo-restriction, large-input, timeout,
concurrency, corrupted-input, and real-desktop cases. Apply rate limits and
explicit write approvals. Record unavailable external conditions as blockers,
not product failures.

### Step 11: Triage, Fix, And Rerun

- Reproduce every FAIL from its exact binding.
- Separate product defects, test defects, mapping defects, and environment
  defects.
- Fix on a reviewed branch and record the fix commit.
- Start a new result set for a changed commit.
- Rerun the failed test, its atomic-feature siblings, affected Level 2 tests,
  and the appropriate regression smoke set.

Never overwrite the original failing evidence.

### Step 12: Roll Up Results

- Atomic test: status comes only from its current evidence manifest.
- Atomic feature: PASS only when all required atomic tests pass; otherwise use
  the worst supported non-PASS status and list the affected tests.
- Level 2 feature: PASS only when all required atomic features pass and all
  required platform variants are satisfied.
- Level 1 feature: summarize child Level 2 results without hiding failures or
  blockers.
- Product verdict: apply release gates and defect severity, not a simple pass
  percentage.

Keep Windows and macOS evidence visible as separate lanes before roll-up.

### Step 13: Produce The Final Test Report

The final report must contain:

- executive verdict and Go/No-Go recommendation;
- tested commit, workbook hash, environments, dates, and runner versions;
- feature and atomic-test scope;
- binding completeness and implementation-gap metrics;
- Windows, WSL2, macOS, CI, and manual lane summaries;
- pass/fail/blocked/inconclusive/not-run counts;
- Level 1 and Level 2 pass/fail table;
- defect list with severity, reproduction, and affected features;
- AutoSci full-run red/green evidence;
- current limitations and untested risk;
- evidence manifest index;
- explicit statement that historical results were not counted as current
  results unless rerun against the tested commit.

## 12. Completion Criteria

The campaign is complete only when:

- all 142 Level 2 features have a final supported status;
- all 2,047 atomic features have a review decision and roll-up status;
- all 2,297 atomic-test registry rows have a reviewed disposition;
- every in-scope executable row has an approved execution binding;
- all implementation gaps are resolved or explicitly reported as blockers;
- all ready tests have been executed against the frozen commit;
- every current result has evidence and every FAIL has defect linkage;
- Windows primary testing is complete;
- the required smaller macOS lane is complete;
- AutoSci official-intake red and green scenarios are complete;
- no Blocker or Critical defect remains open for a Go recommendation;
- the final report distinguishes tested, blocked, not applicable, and not run
  scope without converting any of them into PASS.

## 13. Immediate Next Actions

1. Freeze the next canonical commit and workbook hash.
2. Complete atomic-feature review.
3. Run full repository-wide test-source discovery, not only root `tests/`.
4. Resolve the 233 unresolved file-binding rows.
5. Classify the 2,267 implementation-gap rows.
6. Add explicit platform-lane values, including the required Mac lane.
7. Approve the first Windows deterministic smoke batch.
8. Approve the smaller macOS smoke and platform-specific batch.
9. Execute only after binding and runner-readiness gates pass.
