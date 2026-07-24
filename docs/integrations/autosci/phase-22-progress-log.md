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
| Historical colored workbook located | complete | Located the historical workbook at `docs/testing/test-runs/20260710-0121-qa-full-audit/ai4research_recursive_feature_split_qa_execution_colored.xlsx` in commit `718aae9a`, including its test-status colors and historical atomic-test inventory. Raw run evidence is no longer stored in the current source tree. |
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
| Commit `718aae9a`, path `docs/testing/test-runs/20260710-0121-qa-full-audit/ai4research_recursive_feature_split_qa_execution_colored.xlsx` | Historical colored test workbook and old test inventory; retained in Git history rather than the current source tree. |
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
| Historical workbook file mapping | absent | In the old colored workbook, all 2,117 `Existing Test Map` rows have blank `existing test files` and `existing test cases` fields. All 2,117 `Function Inventory` rows also have blank discovered-path and symbol fields. The colored workbook therefore does not identify an executable file for any atomic row. |
| Historical execution receipts | located | At commit `718aae9a`, `docs/testing/test-runs/20260709-qa-execution/` contained 780 status JSON receipts. Of these, 685 name a source file, representing 684 unique source paths: 667 under `harness/tests/` and 17 under root `tests/`. In the original checkout, 666 of those paths still exist and 18 are missing. These receipts show which suites were executed, but they are not bound one-to-one to the 2,117 atomic rows and are no longer stored in the current source tree. |
| Original repository test-file inventory | complete | The original local history contains 988 tracked executable test-like files: 37 under root `tests/` and 951 elsewhere. The largest existing locations are `harness/tests/` (814), other `harness/` test files (70), and `harness/plugins/autosci/tests/` (22). |
| New-source test-file inventory | complete | The requested `Coconut-ch1ken/OpenSolar` branch contains 773 tracked executable test-like files: 32 under root `tests/` and 741 elsewhere, primarily under `harness/`. |
| Phase 22 atomic-test location | required | Every new atomic-test implementation created for this campaign must be stored under the repository root `tests/` directory. Categorize tests as `tests/workflow/<level-1-slug>/`, `tests/foundation/<level-1-slug>/`, `tests/vertical/<level-1-slug>/`, or `tests/platform/<surface>/`; shared fixtures and helpers belong under `tests/shared/`. Do not use a single `tests/atomic/` bucket. |
| Legacy relocation | conditional | Existing repository suites have not been moved wholesale. A legacy file may move into the appropriate root-`tests/` category only after its atomic-feature bindings are reconstructed and its imports, fixtures, runner commands, and baseline result pass from the new path. Until then, keep it in place and reference or wrap it from the new categorized suite. |

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

## Contract-Gated Missing-Test Case Design

Logged: 2026-07-23 EDT

Intent: convert the 180 generic seed tests for the 60 previously uncovered
Level 2 features into observable atomic test-case designs while the generated
L2 contracts are under user review.

### Eligibility And Scope

| Item | Result | Evidence / interpretation |
|---|---:|---|
| Current L2 contracts inspected | 142 | Workflow 54, Foundation 65, and Vertical 23 in `outputs/019f8b0a-6f79-7900-9b1a-cb3fc9f875d3/AI4RnD Feature List - L2 what annotated.xlsx`. |
| Previously uncovered L2 features needing concrete cases | 60 | This is the historical-coverage gap recorded in `Uncovered L2 Resolution`, not the larger set of L2s that still lack a finished current-file binding. |
| Eligible L2s with a generated contract | 60 | Every previously uncovered L2 matched a nonblank generated contract after ordinal-prefix normalization. |
| Contract-less eligible L2s skipped | 0 | The contract gate excluded no member of the 60-L2 set. |
| Generic seed tests represented | 180 | All core-behavior, input-guardrail, and evidence/auditability seed registry IDs are referenced by at least one generated scenario. |
| Observable atomic scenarios designed | 490 | The contract `Granularity / Separate Atomic Contracts` field was expanded into named scenario-level cases; a fallback core, guardrail, or evidence case was added only when a contract list did not explicitly contain that seed category. |

### Generated Case Inventory

| Category | L2 manifests | Atomic scenario cases |
|---|---:|---:|
| Workflow | 21 | 178 |
| Foundation | 31 | 237 |
| Vertical | 8 | 75 |
| **Total** | **60** | **490** |

Each L2 has one JSON case manifest under its required categorized root:
`tests/workflow/<level-1-slug>/`, `tests/foundation/<level-1-slug>/`, or
`tests/vertical/<level-1-slug>/`. Each case records a stable case ID, a readable
`test_*` name, its source seed registry ID, input focus, prerequisites, steps,
expected result, state/side-effect oracle, required evidence, supported
boundary, current implementation surfaces, and execution status.

The cross-category explanation and validator are stored in
`tests/platform/phase22/README.md` and
`tests/platform/phase22/test_l2_case_specifications.py`.

### Implementation And Execution Status

| Status | L2 count | Interpretation |
|---|---:|---|
| Current surface identified | 52 | At least one current tracked implementation/interface/schema/evidence file referenced by the contract was resolved. The cases remain `DESIGNED_NOT_YET_IMPLEMENTED` until a behavioral adapter invokes the surface and asserts the oracle. |
| No current implementation | 8 | Cases are retained for traceability but marked `BLOCKED_NO_CURRENT_IMPLEMENTATION`; no passing result is implied. |

The eight implementation-absent L2s are `Qualified Channel Signal Intake`,
`Model Policies and Weights (SFT / LoRA / DPO / GRPO / Agent RL)`, `Dataset
Graph Management`, `Policy Graph Management`, `Model Construction`, `Prototype
Assembly`, `Account Registration`, and `Discord`.

No product capability result was assigned in this step. These are concrete
test-case specifications, not behavioral pass evidence. This separation avoids
treating AI-generated structure or the existence of a referenced source file as
proof that the underlying feature works.

### Verification

| Check | Result |
|---|---|
| Validator command | `python tests/platform/phase22/test_l2_case_specifications.py` |
| Standard-library validator | PASS: 4 tests in 0.433 seconds. |
| Manifest count | PASS: 60 unique L2 manifests. |
| Case identity | PASS: 490 unique case IDs and `test_*` names. |
| Seed traceability | PASS: all 180 unique seed registry IDs represented. |
| Contract gate | PASS: every manifest contains all 13 nonblank contract/evidence fields. |
| Current-surface check | PASS: all referenced surfaces for the 52 surface-identified L2s resolve to files in the current repository. |
| Missing-implementation guard | PASS: all cases for the eight implementation-absent L2s are marked blocked. |

Next step: after the corresponding L2 contracts are approved or revised,
implement behavioral adapters for the approved scenarios in small batches,
starting with deterministic local surfaces. Bind only executed cases and retain
current-repository evidence before assigning pass/fail status.

## Implemented-L2 Execution Audit Checkpoint

Logged: 2026-07-23 EDT

Intent: shift the Phase 22 report from design-only coverage to an executable
three-state audit of every Level 2 feature.

### Classification Rule

| Result | Working definition |
|---|---|
| Function implemented and test passed | A direct current implementation performs a meaningful core part of the L2 and its feature-relevant executable probe passes. |
| Function implemented but test failed | A direct current implementation exists, but its executable probe fails, including current-machine dependency or platform failures that prevent the behavior from running. |
| Function not implemented and test blocked | No direct core implementation exists. Adjacent or similarly named surfaces do not count as implementation evidence. |

Ten L2s are currently classified as implementation-blocked by the contract and
code-surface review: the eight previously explicit gaps plus `Strategic
Opportunity Screening` and `Hypothesis Pool & Mechanism Formation`, whose
contracts identify only adjacent/partial surfaces rather than their direct core
behavior. Partial umbrella L2s with a meaningful current subset remain eligible
for execution, with the tested subset recorded as a limitation.

### Work Completed Before Pause

| Area | Result |
|---|---|
| Intake and requirement compilation | Representative capture, binding, consumption, qualification, compilation, and rejection probes pass after using an isolated UTF-8 test environment. |
| Search and ingestion | Paper preparation and local/provider-retry literature discovery probes pass. |
| Ideation | Deduplication passes; the mixed wiki/discovery ideation probe fails because the provider-source proof omits the expected method evidence reference. |
| Claims and experiment workflow | Claim/converter probes pass. Experiment-design and pilot-run probes fail on their current expected evidence/execution boundaries. |
| Evaluation and delivery | Grounded synthesis, artifact evaluation, claim-verdict, artifact-review, status-next, paper-draft, and publication/deliverable probes pass. |
| Capability capsules | Definition, registry, and resolution probes pass. |
| GEPA promotion | Capsule evolution/promotion probes fail on Windows because the tests use POSIX `/tmp` paths that are unavailable to the Windows Python runtime. |
| Benchmarking | Registry and report-schema probes pass; the Terminal-Bench dry-run execution probe returns `pending` where the test expects `ok`. New direct core benchmark tests pass under Node's TypeScript loader. |
| TypeScript runtime adapters | Added passing executable Node tests for benchmark metadata/results, the agent message bus, and Hive cluster registration/capability matching. |
| Windows portability findings | Existing operator-selection/model-audit probes cannot collect because `fcntl` is unavailable; the Apple Notes/WeChat shell probe fails because Windows Python cannot resolve the MSYS `/tmp` fixture path. These remain implemented/test-failed candidates, not implementation-blocked features. |

New executable test support added under the required root test hierarchy:

- `tests/platform/phase22/node_typescript_loader.mjs`
- `tests/platform/phase22/bin/python3`
- `tests/workflow/benchmarking/test_core_benchmark_behavior.mjs`
- `tests/foundation/harness_core/test_agent_bus_behavior.mjs`
- `tests/foundation/data_foundations/test_bun_data_foundation_behavior.test.ts`
- `tests/vertical/system_configurations/test_hive_cluster_behavior.mjs`

Pause state: the complete 142-row execution matrix, full run, final three-state
counts, and classified workbook export are not yet complete. No commit or push
was performed at this checkpoint.

## Implemented-L2 Execution Audit Completion

Logged: 2026-07-23 EDT

The paused audit was resumed and completed against the same checkout. The
classification uses one representative, feature-relevant core probe per L2;
shared probes are executed once and their evidence is bound to each applicable
L2. This is an executable smoke classification, not exhaustive proof of every
atomic contract scenario.

### Final Classification

| Category | Implemented / passed | Implemented / failed | Not implemented / blocked | Total |
|---|---:|---:|---:|---:|
| Workflow | 41 | 10 | 3 | 54 |
| Foundation | 43 | 17 | 5 | 65 |
| Vertical | 10 | 11 | 2 | 23 |
| **Total** | **94** | **38** | **10** | **142** |

The 132 implemented L2s resolve to 79 unique executable probes. The run
completed with 58 passing probes and 21 failing probes. Every one of the 142
L2 rows has exactly one final classification; the ten no-implementation rows
have explicit blockers and no fabricated executable result.

### Execution And Evidence Artifacts

- Matrix builder: `tests/platform/phase22/build_l2_execution_matrix.py`
- Complete binding matrix: `tests/platform/phase22/l2_execution_matrix.json`
- Matrix runner: `tests/platform/phase22/run_l2_execution_matrix.py`
- Structural validators: `tests/platform/phase22/test_l2_execution_matrix.py` and `tests/platform/phase22/test_l2_case_specifications.py`
- Machine-readable results: `outputs/019f8b0a-6f79-7900-9b1a-cb3fc9f875d3/phase22_l2_execution/phase22_l2_execution_results.json`
- Review tables: `outputs/019f8b0a-6f79-7900-9b1a-cb3fc9f875d3/phase22_l2_execution/phase22_l2_classification.csv` and `.md`
- Classified workbook: `outputs/019f8b0a-6f79-7900-9b1a-cb3fc9f875d3/AI4RnD Feature List - L2 execution classified.xlsx`

The runner isolates `HOME` and `USERPROFILE`, enables UTF-8 Python I/O, and
records commands, return codes, durations, stdout/stderr tails, implementation
entrypoints, tested boundaries, and blocker or failure summaries. Supported
runners are pytest, Python script, Node, Node with the local TypeScript loader,
Git Bash, and Bun; an unavailable required runner is recorded as a test failure
for an implemented capability rather than as an unimplemented feature.

### Principal Failure Groups

- Several Python runtime/operator probes cannot import `fcntl` on Windows.
- Bun-backed ontology/SMI tests cannot run because Bun is unavailable.
- Desktop GUI coverage cannot run because `desktop/node_modules/playwright` is missing.
- Some existing tests use POSIX `/tmp` paths that Windows Python cannot resolve.
- Remaining behavioral mismatches include logical-schema validation, macOS
  release gating, status-dashboard write support, benchmark dry-run verdicts,
  experiment evidence/parity, and ideation evidence references.

These class-2 results are retained as evidence of current implementation that
did not pass on this machine; they are not reclassified as missing features.
The class-3 set is limited to Qualified Channel Signal Intake, Strategic
Opportunity Screening, Hypothesis Pool & Mechanism Formation, Model Policies
and Weights, Dataset Graph Management, Policy Graph Management, Model
Construction, Prototype Assembly, Account Registration, and Discord.

No commit or push was performed as part of this audit.
