# AI4Research Phase 22 Test Report Progress Log

Phase 22 tracks preparation, execution, and reporting for a full test report of
the current AI4Research repository. The official feature hierarchy is the
workbook named `AI4RnD Feature List.xlsx`. Historical test results are retained
only as mapping evidence and must not be presented as results from the current
repository.

## Test Report Planning And Feature Mapping

Logged: 2026-07-20 EDT

Intent: establish a traceable hierarchy from the current official Level 2
features to atomic features and atomic tests before generating executable test
cases and running them against the current repository.

| Item | Status | Evidence |
|---|---|---|
| Official hierarchy | complete | The current feature list contains 142 Level 2 features: 54 Workflow, 65 Foundation, and 23 Vertical. |
| Historical test inventory | complete | The old colored QA workbook contains 2,117 historical atomic test rows. |
| Historical test remapping | complete | 1,867 historical tests map to 82 current Level 2 features. |
| Unmapped historical tests | recorded | 250 historical tests do not map to the current official hierarchy and remain separately tagged. |
| Previously uncovered Level 2 features | resolved for planning | 60 Level 2 features had no confident historical atomic-feature mapping. |
| Provisional coverage | complete for planning | 180 new atomic features and 180 seed atomic tests were added, using core-behavior, guardrail, and evidence/auditability coverage for each previously uncovered Level 2 feature. |
| Atomic hierarchy | complete | The working workbook now represents `Level 1 -> Level 2 -> atomic feature -> atomic test(s)`. |
| Expanded feature sheets | complete | Workflow, Foundation, and Vertical sheets directly display their atomic features and atomic tests; vertically repeated hierarchy cells are merged and bordered by parent group. |
| Current-repository execution | not started | No historical result is accepted as a current-repository result. Every atomic test still requires an execution-readiness review and current evidence. |

## Spreadsheet Work Completed

Logged: 2026-07-20 EDT

Intent: record the spreadsheet investigation and restructuring completed before
the current-repository test-case generation and execution phases.

### Source Workbooks And Hierarchy Decision

| Item | Status | Evidence |
|---|---|---|
| Historical colored workbook located | complete | Located `docs/testing/test-runs/20260710-0121-qa-full-audit/ai4research_recursive_feature_split_qa_execution_colored.xlsx`, including its test-status colors and historical atomic-test inventory. |
| Official feature hierarchy selected | complete | `AI4RnD Feature List.xlsx` was designated as the authoritative current Level 1 and Level 2 hierarchy. |
| Historical workbook authority | limited | The old colored workbook is used for historical atomic features, atomic tests, and old results; it is not used as the current feature hierarchy. |
| Repository-version equivalence | unresolved by decision | No conclusive evidence was established that the code tested by the historical workbook is identical to the current repository. Historical results therefore remain historical evidence only. |

### Historical Test Remapping

| Item | Status | Evidence |
|---|---|---|
| Historical atomic tests inventoried | complete | Reviewed 2,117 historical test rows from the old colored workbook. |
| Tests mapped to current hierarchy | complete | Mapped 1,867 historical tests to 82 current Level 2 features. |
| Unmapped tests identified | complete | Identified 250 historical tests with no defensible mapping to the official hierarchy. |
| Unmapped tests tagged | complete | Tagged these rows as `UNMAPPED_TO_OFFICIAL_HIERARCHY` in the historical colored workbook and retained their reasons separately. |
| Official workbook mapping added | complete | Added current-hierarchy mapping information so historical tests can be traced to their official feature sheet, Level 1 feature, and Level 2 feature. |

The 250 unmapped historical tests were retained rather than forced into the new
hierarchy. Their main areas include QA inventory, installable components,
installer and release packaging, hook/runtime reminder surfaces, desktop
package scripts, CI workflows, reset workflows, and Solar harness
installation/migration assurance.

### Atomic Feature And Atomic Test Structure

| Item | Status | Evidence |
|---|---|---|
| Historical atomic-feature reuse assessed | complete | Historical atomic descriptions are reusable when their old feature path or surface context is retained. Atomic descriptions alone can be ambiguous because templates repeat across different feature contexts. |
| Explicit atomic-feature layer added | complete | Added an `Atomic Feature Registry` sheet as the parent layer between the current Level 2 hierarchy and atomic tests. |
| Explicit atomic-test binding added | complete | Rebuilt the `Atomic Test Binding` sheet so every atomic test references an `Atomic Feature ID`. |
| Complete atomic-test inventory added | complete | Added an `Atomic Test Registry` sheet containing all 2,297 known tests: 2,047 bound/planned tests and 250 unmapped historical tests. |
| Historical atomic features preserved | complete | Preserved 1,867 contextual historical atomic features and their links to historical tests. |
| Previously uncovered Level 2 features resolved | complete for planning | Added 180 provisional atomic features for the 60 Level 2 features without confident historical coverage. |
| Provisional atomic tests bound | complete for planning | Added 180 seed atomic tests and bound each one to its generated atomic feature. |
| Full planning hierarchy | complete | All 142 current Level 2 features now have at least one atomic feature and atomic test at the planning layer. |

The `Atomic Feature Source` field distinguishes
`HISTORICAL_OLD_FEATURE` from `NEW_REQUIRED_FEATURE`. It is retained in the
registry for auditability; it does not change the feature hierarchy or the
current test result.

### Expanded Feature Sheets And Formatting

| Feature sheet | Current Level 2 features | Expanded atomic rows | Spreadsheet result |
|---|---:|---:|---|
| Workflow Features | 54 | 549 | Expanded to show Level 1, Level 2, atomic feature, and bound atomic test details. |
| Foundation Features | 65 | 1,240 | Expanded to show Level 1, Level 2, atomic feature, and bound atomic test details. |
| Vertical Features | 23 | 258 | Expanded to show Level 1, Level 2, atomic feature, and bound atomic test details. |

The expanded sheets now present the visible relationship:

`Level 1 -> Level 2 -> atomic feature -> atomic test(s)`

Formatting work completed:

- Preserved the blue official-feature visual hierarchy.
- Added a purple atomic-feature section and a teal atomic-test section.
- Used outer borders to show which atomic features and tests are included under
  each Level 2 feature.
- Vertically merged adjacent repeated Level 1 and Level 2 cells.
- Vertically merged repeated atomic-feature cells when an atomic feature has
  multiple test rows.
- Added visible current/planned test status formatting.
- Retained the separate registry and binding sheets as the unmerged audit
  tables behind the expanded presentation sheets.
- Re-imported and rendered the workbook for visual verification and found no
  spreadsheet formula-error markers.

### Current Spreadsheet Boundary

The spreadsheet work establishes complete planning coverage, but it does not
establish current-repository pass/fail coverage. The 1,867 historical results
must be re-executed or otherwise reproduced against the current repository, and
the 180 provisional tests must be converted from generic seed specifications
into concrete repository-specific test cases.

### Working Artifacts

| Artifact | Purpose |
|---|---|
| `outputs/019f706d-a7ff-7f63-8b69-abcc7bb68135/AI4RnD Feature List - atomic coverage resolved.xlsx` | Current mapping and test-report planning workbook, including atomic-feature names and the complete atomic-test registry. |
| `docs/testing/test-runs/20260710-0121-qa-full-audit/ai4research_recursive_feature_split_qa_execution_colored.xlsx` | Historical colored test workbook and old test inventory. |
| `outputs/019f706d-a7ff-7f63-8b69-abcc7bb68135/unmapped_historical_tests.md` | Detailed list of historical tests that do not map to the current hierarchy. |

### Interpretation Guardrails

| Issue | Status | Guardrail |
|---|---|---|
| A mapped historical test can look like proof that the current feature passes. | guarded | Mapping establishes relevance only; the test must be executed against the current repository before assigning a current result. |
| Provisional tests can look execution-ready because they have names and expected outcomes. | guarded | Seed tests are planning specifications until concrete code surfaces, commands, prerequisites, and evidence locations are identified. |
| Atomic feature descriptions can be ambiguous when read without context. | guarded | Preserve the mapped Level 2 feature and old feature path/context when interpreting a historical atomic feature. |
| Unmapped historical tests can distort current feature coverage. | guarded | Keep them in a separate inventory and do not force them into the official hierarchy without evidence. |
| Issue categories can be applied inconsistently. | pending | Finalize the severity rubric before full execution and use it consistently across all test results. |

## Atomic Feature Naming And Review Preparation

Logged: 2026-07-20 EDT

Intent: make the atomic-feature layer reviewable before accepting or revising
any atomic-test bindings.

| Item | Status | Evidence |
|---|---|---|
| Atomic feature names | complete | Assigned a readable `Atomic Feature Name` to all 2,047 atomic-feature rows. |
| Name coverage | verified | Post-export verification found 2,047 named rows and zero blank names. |
| Reusable names | expected | The workbook contains 524 unique names because historical templates repeat across different Level 2 and old-path contexts. Atomic Feature ID and context remain the disambiguators. |
| Generated feature naming | complete | Provisional features use consistent `Core Behavior`, `Input Guardrail`, and `Evidence & Auditability` names. |
| Registry synchronization | verified | `Atomic Feature Registry` is the canonical name source. All 2,047 rows in `Atomic Test Binding` have the matching registry name with zero mismatches. |
| Expanded sheet synchronization | verified | Workflow has 549 named atomic rows across 54 Level 2 features; Foundation has 1,240 across 65; Vertical has 258 across 23. No expanded row has a blank atomic-feature name. |
| Uncovered-L2 audit | complete | All 180 generated atomic features in `Uncovered L2 Resolution` now have names. |
| Tab-role guidance | complete | Added a nine-tab role table to `Coverage Summary`, separating active atomic-feature review tabs from deferred and audit-only tabs. |
| Test-binding status | deferred | The atomic-test mapping remains visible for provenance but is labelled as draft and should not be reviewed or accepted until atomic features are approved. |
| Original workbook migration | complete | The original atomic-coverage workbook became accessible, so the atomic-feature naming and review changes were migrated into it and verified there. The temporary `AI4RnD Feature List - atomic feature review.xlsx` copy was then deleted. |

## Atomic Test Registry Consolidation

Logged: 2026-07-20 EDT

Intent: maintain one complete inventory of every known atomic test without
forcing excluded historical tests into the current official hierarchy.

| Item | Status | Evidence |
|---|---|---|
| Registry tab | complete | Added `Atomic Test Registry` as the final workbook tab. |
| Bound and planned tests | verified | The registry contains 2,047 tests that are draft-bound to atomic features: 1,867 preserved historical tests and 180 new planned seed tests. |
| Unmapped historical tests | verified | The registry also contains all 250 excluded historical tests, tagged `UNMAPPED_HISTORICAL_TEST` with blank current-hierarchy fields and their exclusion context retained. |
| Total inventory | verified | The registry contains 2,297 uniquely identified atomic tests with zero blank test names and zero duplicate registry IDs. |
| Feature references | verified | Every draft-bound registry row references an existing atomic feature; zero bound rows have a missing atomic-feature ID. |
| Workbook integrity | verified | The final nine-tab workbook was re-imported and rendered; the formula-error scan found zero error markers. |

## Testing Source And Test-File Location

Logged: 2026-07-20 EDT

Intent: keep Phase 22 testing isolated from the original source repository and
establish one predictable location for the atomic-test implementations created
during this test campaign.

| Item | Status | Evidence / rule |
|---|---|---|
| Authoritative test source | confirmed | Phase 22 execution uses `https://github.com/Coconut-ch1ken/OpenSolar/tree/openJiuwen-Solar`. |
| Original-source push restriction | active | Do not push Phase 22 commits to the boss's original source or main branch until testing is complete and approval is given. |
| Local source mismatch | identified | The existing local `openJiuwen-Solar` checkout tracks `Stellven/AI4Research`, not `Coconut-ch1ken/OpenSolar`; the two branch histories have diverged. QA commits must therefore be based explicitly on the `Coconut-ch1ken/OpenSolar` branch history. |
| Atomic registry versus code | verified | The workbook contains 2,297 registry rows representing 524 unique atomic-test names, but exact symbol-name matching found no executable implementation for those names in the original local repository. The registry is currently a test specification and mapping inventory, not a set of existing test files. |
| Original repository test-file inventory | complete | The original local history contains 988 tracked executable test-like files: 37 under root `tests/` and 951 elsewhere. The largest existing locations are `harness/tests/` (814), other `harness/` test files (70), and `harness/plugins/autosci/tests/` (22). |
| New-source test-file inventory | complete | The requested `Coconut-ch1ken/OpenSolar` branch contains 773 tracked executable test-like files: 32 under root `tests/` and 741 elsewhere, primarily under `harness/`. |
| Phase 22 atomic-test location | required | Every new atomic-test implementation created for this campaign must be stored under the repository root `tests/` directory. Use `tests/atomic/` for the organized atomic-test suite and do not add new Phase 22 test implementations under `core/`, `harness/`, `desktop/`, `skills/`, `docs/`, or `outputs/`. |
| Legacy relocation | not performed | Existing repository test suites have not been moved; mass relocation could break their runners, imports, fixtures, and package boundaries and requires a separate migration decision. |

## Next Step: Atomic Feature Review

Logged: 2026-07-20 EDT

Intent: review the atomic-feature layer independently, before deciding which
atomic tests should bind to it.

| Review field | Review question |
|---|---|
| Atomic Feature Name | Does the name clearly identify one behavior or responsibility? |
| Parent Level 2 feature | Does this atomic feature genuinely belong under this Level 2 feature? |
| Atomic Feature Description | Is the behavior precise enough to test later? |
| Old Feature Path / Context | Does the historical context support the proposed current mapping? |
| Duplication | Should repeated or overlapping atomic features be consolidated? |
| Missing behavior | Does the Level 2 definition imply atomic features that are absent? |
| Review decision | Approve, revise, move, merge, split, remove, or add. |

Only after the atomic-feature review is complete should `Atomic Test Binding`
be treated as an active working sheet.

## Deferred Step: Execution-Readiness Review

Intent: after atomic features and their test bindings are approved, convert the
accepted atomic-test inventory into concrete test cases that can be executed
against the current repository.

| Required field | Expected content |
|---|---|
| Current code surface | Relevant file, command, API, UI, configuration, document, or runtime boundary in the current repository. |
| Execution mode | Automated, manual, environment-dependent, feature-not-found, or not-currently-testable. |
| Preconditions | Required installation state, fixtures, credentials, services, providers, or safe sandbox setup. |
| Test steps | Exact reproducible actions for the current repository. |
| Expected result | Observable pass condition and explicit failure condition. |
| Evidence | Logs, command output, screenshots, generated artifacts, file diffs, or status records required for classification. |
| Current result | Not run, pass, fail, blocked, skipped, or inconclusive, based only on current execution evidence. |
| Issue severity | Blocker, significant issue, high, or low when a current failure is confirmed. |

### Proposed Severity Interpretation

| Category | Working definition |
|---|---|
| Blocker | Prevents installation, startup, or broad continuation of the test run. |
| Significant issue | Major workflow, safety, security, or data-integrity failure with broad impact or no practical workaround. |
| High | Important Level 2 behavior or major branch fails, but the broader test run can continue. |
| Low | Minor, cosmetic, documentation, or limited edge-case failure. |

The severity interpretation remains a working rubric until confirmed for the
full test report. The next recorded work should identify execution-ready tests,
test gaps, required environments, and the first smoke-test batch.
