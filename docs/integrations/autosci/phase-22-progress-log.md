# AI4Research Phase 22 Test Report Progress Log

Phase 22 tracks preparation, execution, and reporting for a full test report of
the current AI4Research repository. The official feature hierarchy is the
workbook named `AI4RnD Feature List.xlsx`. Historical test results are retained
only as mapping evidence and must not be presented as results from the current
repository.

## Known Issues Final Integration

Logged: 2026-08-07 EDT

Integration branch: `codex/known-issues-final-integration`.
Fixed baseline: `4b5af751956f8ef1d2eb6bbce8baf9088e694d00`.
Pre-final-integration HEAD after repair cherry-picks:
`13348759d4659fc7484ba482134c0811175f206c`.

The nine repair worker commits were verified for commit, `result.json`, and a
dedicated repair log before integration. They were cherry-picked in dependency
order: control plane, live provider, reviewer, runtime, entrypoints, identity,
optimizer, routing, and training. No cherry-pick conflict required whole-file
ours/theirs resolution.

Final L2 roll-up is conservative and supersedes the 2026-07-30 inference-heavy
roll-up: `PASS=26`, `PASS_WITH_KNOWN_LIMITATIONS=68`, `FAIL=14`,
`ENVIRONMENT_BLOCKED=2`, `NOT_AVAILABLE=22`, and `NOT_TESTED=10`, for 142 total
L2 rows. Positive inference-only rows were downgraded unless a production
journey or production entrypoint test supported the verdict.

Validation summary:

| Scope | Result |
|---|---|
| Changed targeted regression set | 89 passed, 3 skipped |
| Pytest collection | 7029 collected, 0 collection errors |
| J01-J24 final journey suite | 15 passed, 11 skipped |
| Broad root shards | 2101 passed, 179 failed, 6 errors, 1 skipped, 3 xfailed, non-deduplicated |
| Broad harness sub-shard A | incomplete; no terminal pytest summary |
| Workbook formula scan | 0 formula-error matches |

Open validation limits: broad pytest remains non-green; the incomplete harness
sub-shard is recorded as incomplete, not passed; macOS could not be rerun on
the Windows/WSL host; live providers were not rerun without fresh explicit
authorization and configured credentials; external Discord/Wechat and hosted
account/provider revocation paths remain unavailable or untested.

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
| `docs/integrations/autosci/phase-22-test-report.xlsx` | Canonical mapping and test-report workbook, including atomic-feature names, the complete atomic-test registry, L2 contracts, and current executable classifications. |
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
| Historical execution receipts | located | At commit `718aae9a`, `docs/testing/test-runs/20260709-qa-execution/` contained 780 status JSON receipts. Of these, 685 name a source file, representing 684 unique source paths: 667 under `tests/harness/` and 17 under root `tests/`. In the original checkout, 666 of those paths still exist and 18 are missing. These receipts show which suites were executed, but they are not bound one-to-one to the 2,117 atomic rows and are no longer stored in the current source tree. |
| Original repository test-file inventory | complete | The original local history contains 988 tracked executable test-like files: 37 under root `tests/` and 951 elsewhere. The largest existing locations are `tests/harness/` (814), other `harness/` test files (70), and `tests/plugins/autosci/` (22). |
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
| Current L2 contracts inspected | 142 | Workflow 54, Foundation 65, and Vertical 23 in the canonical `docs/integrations/autosci/phase-22-test-report.xlsx`. |
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
- Canonical classified workbook: `docs/integrations/autosci/phase-22-test-report.xlsx`

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

## Canonical Report Consolidation

Logged: 2026-07-24 EDT

The sequential Phase 22 workbook versions were consolidated into one stable
report at `docs/integrations/autosci/phase-22-test-report.xlsx`. The workbook
contains the official Workflow, Foundation, and Vertical feature sheets;
coverage and mapping summaries; atomic feature/test registries; test-file and
source inventories; the generated L2 WHAT contracts; the executable L2
classification; and a `Report Control` tab that links to the live 142/94/38/10
summary formulas.

Future Phase 22 mapping and execution batches must update this canonical
workbook in place. Thread-specific or numbered report copies must not be
created. Independent source-data and QA-inventory workbooks remain separate
inputs and are not treated as report-version duplicates.

Before consolidation, the complete pre-consolidation state was committed and
pushed to `origin/openJiuwen-Solar` at `8d48deba`, so removed report versions
remain recoverable from Git history.

## Four-Sheet Report Simplification

Logged: 2026-07-24 EDT

At the report owner's request, the canonical workbook was simplified to retain
only these four review-facing worksheets:

- `Workflow Features`
- `Foundation Features`
- `Vertical Features`
- `Coverage Summary`

The nine supporting registry, mapping, inventory, execution-detail, and control
worksheets listed below were removed after their decision-relevant information
was migrated into this log. The complete row-level pre-removal workbook remains
recoverable from Git commit `012e7a20` (`WS22: consolidate canonical test
report`). This commit is the authoritative archive for any deleted cell-level
detail, formatting, or provenance that is too large to duplicate in Markdown.

### Migrated Coverage And Registry Snapshot

| Removed worksheet | Data rows | Migrated information |
|---|---:|---|
| `Atomic Test Binding` | 2,047 | One atomic test per atomic feature: 1,867 historical bindings and 180 newly required seed tests. Result/planned-status mix: 713 `PASS`, 574 `SKIPPED_NA`, 341 `INCONCLUSIVE_EXPECTED`, 180 `NOT_RUN`, 102 `FAIL`, 101 `SKIPPED_ENV`, and 36 `BLOCKED_EXPECTED`. Historical mapping confidence values were 1.00, 0.95, or 0.90. |
| `Uncovered L2 Resolution` | 180 | All 60 previously uncovered L2 capabilities received three generated atomic scenarios: core behavior, evidence/auditability, and invalid-input guardrail. All rows carried `NEEDS_NEW_TESTS`; they were planning seeds rather than proof that an implementation or executable test existed. |
| `Unmapped Historical Tests` | 250 | Legacy tests intentionally excluded from the current feature hierarchy. Historical results: 130 `PASS`, 45 `SKIPPED_NA`, 40 `INCONCLUSIVE_EXPECTED`, 25 `SKIPPED_ENV`, and 10 `FAIL`. Exclusion groups: 88 QA meta-inventory, 70 installable-component assurance, 30 packaging/release assurance, 20 generic hook safety checks, 16 desktop packaging build checks, 12 CI pipeline checks, 8 reset/destructive maintenance checks, and 6 install/migration/reset checks. |
| `Atomic Feature Registry` | 2,047 | 1,867 historical contextual atomic features plus 180 newly required features. Review state: 1,738 retained at mapping confidence 1.00, 129 requiring semantic mapping review, and 180 generated/new-required features with no historical-confidence claim. Every feature had one bound atomic-test record in this planning snapshot. |
| `Atomic Test Registry` | 2,297 | 2,047 tests draft-bound to atomic features plus 250 unmapped historical tests. Coverage relationship: 18 `DIRECT`, 6 `SHARED_DIRECT`, 6 `INDIRECT`, and 2,267 `UNRESOLVED`. Implementation-readiness state: 19 requiring pytest, 6 indirect/review-gated, 4 requiring Bash or WSL, 1 platform-blocked, and 2,267 missing a verified test implementation. These registry figures describe the earlier static mapping audit and are not the later 142-L2 executable smoke classification. |
| `Test File Binding` | 263 | File/case-level bindings: 18 `DIRECT`, 6 `SHARED_DIRECT`, 6 `INDIRECT`, and 233 `UNRESOLVED`. Readiness: 19 requiring pytest, 6 indirect/review-gated, 4 requiring Bash or WSL, 1 platform-blocked, and 233 unresolved file mappings. Recorded platforms included cross-platform candidates, Windows PowerShell, Windows with WSL, and POSIX-only lanes. |
| `Test Source Inventory` | 55 | Tracked sources comprised Python, TypeScript, PowerShell, and shell tests. File mapping classification: 1 source with direct mapping, 3 with indirect/structural-only mapping, and 51 unresolved. The inventory was static inspection only; it did not represent an execution run. |
| `Phase 22 L2 Test Summary` | 142 L2 rows | Final representative-core classification: 94 implemented/passed, 38 implemented/failed, and 10 not implemented/blocked. The 132 implemented L2s resolved to 79 unique probes, of which 58 passed and 21 failed on the 2026-07-23 checkout and machine. The detailed row evidence remains in `tests/platform/phase22/l2_execution_matrix.json` and the machine-readable execution results documented in the preceding audit section. |
| `Report Control` | 13 populated rows | Canonical path and update policy, progress-log path, safety snapshot `8d48deba`, latest execution counts, and the former workbook-area index. The continuing policy is to update `docs/integrations/autosci/phase-22-test-report.xlsx` in place and not create numbered report copies. |

### Interpretation After Simplification

The three feature worksheets remain the review surface for L1/L2 hierarchy,
atomic features, generated WHAT contracts, implementation evidence, and the
current L2 classification. `Coverage Summary` remains the workbook-level count
and navigation surface. Supporting mapping/audit detail is now split between
this progress log, the tracked Phase 22 matrix and test files, and the archived
pre-removal workbook at commit `012e7a20`.

The older static registry counts must not be confused with the later execution
audit: `MISSING_TEST_IMPLEMENTATION = 2,267` came from the early atomic-registry
file-binding pass, whereas `94 / 38 / 10` is the later executable representative
L2 classification produced after direct test work and matrix execution.

## Preliminary L2 Status Report

Logged: 2026-07-24 EDT

A compact preliminary report was generated at
`outputs/019f8b0a-6f79-7900-9b1a-cb3fc9f875d3/phase22_l2_status_report/phase-22-l2-status-preliminary-report.xlsx`.
It contains one worksheet and one filterable table only, with the columns
`Level 2 Feature`, `Category`, and `Status`. The 142 rows come from the completed
Phase 22 execution classification rather than the earlier static registry audit.

| Category | Function implemented and test passed | Function implemented but test failed | Function not implemented and test blocked | Total |
|---|---:|---:|---:|---:|
| Workflow | 41 | 10 | 3 | 54 |
| Foundation | 43 | 17 | 5 | 65 |
| Vertical | 10 | 11 | 2 | 23 |
| **Total** | **94** | **38** | **10** | **142** |

The workbook was reconciled to the classification CSV, re-imported after export,
scanned for formula errors, and visually checked for clipped feature names and
status legibility. No commit or push was performed for this report.

## AI4RnD Source Feature List Status Annotation

Logged: 2026-07-24 EDT

The user-supplied workbook at
`C:/Users/j50058254/Downloads/AI4RnD Feature List.xlsx` was updated in place.
The source workbook did not yet contain an `Atomic Coverage Resolution` column,
so that column was restored from the previously resolved workbook convention and
a new `Test Result` column was added immediately to its right. Existing Notes,
Notes 2, level-3 bundles, blank extension columns, merged L1 groups, and feature
descriptions were preserved.

Column placement after the update:

- Workflow Features: `F = Atomic Coverage Resolution`, `G = Test Result`
- Foundation Features: `H = Atomic Coverage Resolution`, `I = Test Result`
- Vertical Features: `J = Atomic Coverage Resolution`, `K = Test Result`

Atomic coverage resolution now records `COMPLETE` for the 132 implemented L2s
that have a representative executable probe and `BLOCKED â€” FUNCTION NOT
IMPLEMENTED` for the ten unimplemented L2s. The adjacent test-result cells use
the final three-state classification and conditional color formatting: green for
implemented/passed, red for implemented/failed, and yellow for
not-implemented/blocked.

| Category | Implemented / passed | Implemented / failed | Not implemented / blocked | Total |
|---|---:|---:|---:|---:|
| Workflow | 41 | 10 | 3 | 54 |
| Foundation | 43 | 17 | 5 | 65 |
| Vertical | 10 | 11 | 2 | 23 |
| **Total** | **94** | **38** | **10** | **142** |

The edited workbook was exported to a workspace staging path, re-imported,
reconciled row-for-row to the Phase 22 classification CSV, visually checked on
all three sheets, copied over the unlocked Downloads file, hash-verified, and
then re-imported from the final Downloads path. No commit or push was performed.

## AI4RnD Workbook Static Color Compatibility Fix

Logged: 2026-07-24 EDT

The status colors in `C:/Users/j50058254/Downloads/AI4RnD Feature List.xlsx`
were changed from conditional formatting to direct cell fills so that the
colors remain visible when the workbook is opened in desktop Excel without a
conditional-format recalculation. The three-state legend is now:

- green (`#C6EFCE`): function implemented and test passed
- red (`#FFC7CE`): function implemented but test failed
- yellow (`#FFEB9C`): function not implemented and test blocked

Matching direct fills were also applied to `Atomic Coverage Resolution`: green
for `COMPLETE` and yellow for `BLOCKED - FUNCTION NOT IMPLEMENTED`. The result
counts remain unchanged at 94 passed, 38 failed, and 10 blocked across all 142
L2 features. The final Downloads workbook was re-imported, its static computed
styles were verified for each status on every sheet, its status counts were
reconciled, and the copied file hash matched the verified export. No commit or
push was performed.

## AI4RnD L2 Row Color Extension

Logged: 2026-07-24 EDT

The direct status fill in `C:/Users/j50058254/Downloads/AI4RnD Feature List.xlsx`
was extended horizontally across each independently classified L2 row. The
colored spans are `C:G` on Workflow Features, `C:I` on Foundation Features, and
`C:K` on Vertical Features. Columns A and B retain their original merged L1
grouping because those cells span several L2 rows that can have different test
results; coloring those merged cells from any one child status would create a
misleading group-level result.

The green, red, and yellow palette and all 142 classifications remain unchanged
at 94 passed, 38 failed, and 10 blocked. All three sheets were rendered before
and after the change, representative full-row styles were verified after
re-import, the formula-error scan returned no matches, and the final Downloads
file hash matched the verified export. No commit or push was performed.

## Atomic Granularity Review And Executable-Test Generation

Logged: 2026-07-24 EDT

The canonical four-sheet report was rebuilt in place from the workbook's L2
descriptions/WHAT contracts and the current repository implementation evidence.
Historical atomic rows were treated as provenance rather than an approved
hierarchy. The review rule is now one independently observable behavior,
rejection branch, evidence obligation, or explicitly named technology/platform
variant per atomic feature. Slash-delimited state and platform alternatives were
expanded into independently classifiable variants; the compound
`duplicate identity/version` uniqueness key was intentionally kept together.

| Review measure | Count |
|---|---:|
| L2 features | 142 |
| Historical atomic rows | 2,047 |
| Reviewed atomic features | 1,502 |
| Net historical rows removed | 545 |
| Repository executable test files inventoried | 971 |
| Repository executable selectors/cases inventoried | 6,462 |

The inventory is assertion/name/code-surface aware, but discovery alone is not
coverage. Fuzzy mappings were rejected unless the selector first matched the L2
implementation surface and then the atomic behavior. Generic matches such as
`file`, `HTML`, `runtime`, or `registry` were not accepted across unrelated
features. A representative L2 probe is bound to at most one closest atomic
behavior and is never copied across every child.

| Atomic test-generation decision | Count |
|---|---:|
| Newly generated executable selector | 14 |
| Reused existing direct/curated selector | 24 |
| L2 representative anchor only | 120 |
| Tagged: manual behavior oracle required | 909 |
| Tagged: environment/provider/platform oracle required | 295 |
| Blocked: required behavior not implemented | 140 |
| **Total reviewed atomic features** | **1,502** |

Every atomic feature now has an explicit generation decision. No
`NEEDS_TEST_IMPLEMENTATION` placeholder remains. Tagged rows have no fabricated
selector: they record that exact generated-selector discovery, curated review,
and conservative current-test matching were attempted, but a defensible
assertion-level oracle was not available. Implementation-blocked rows likewise
carry no adjacent-surface test masquerading as feature coverage.

### Generated And Executed Test Batches

1. `tests/workflow/ingestion/test_request_capture_atomic.py` plus its isolated
   shell driver cover all eight Request Capture behaviors: direct text, file,
   stdin, no-dispatch, successful dispatch, empty input, missing file, and
   workspace mismatch. The suite uses a temporary WSL HOME and copied harness;
   result: **8 passed in 86.41s**.
2. `tests/foundation/taskgraph/test_task_graph_persistence_atomic.py` adds the
   missing corrupt-JSON behavior. Together with exact existing TaskGraph IO
   selectors, all eleven reviewed persistence/lifecycle atomics are bound;
   current suite result: **27 passed in 4.27s**.
3. `tests/foundation/capability_capsules/test_capability_capsule_definition_atomic.py`
   adds five missing definition/validation cases and reuses two exact resource
   resolution cases. Result: **6 passed, 1 failed in 1.27s**. The failure is a
   concrete contract defect: `load_capability_capsule_registry` accepts a
   duplicate `(capability_capsule_id, version)` entry instead of raising
   `CapsuleRegistryError`.

Current atomic execution evidence therefore contains 25 PASS and 1 FAIL. Strict
L2 roll-up no longer inherits the older representative-core 94/38/10 result:

| Strict L2 atomic roll-up | Count |
|---|---:|
| Function implemented; all required atomic tests passed | 2 |
| Function implemented; at least one atomic test failed | 1 |
| Required atomic behavior not implemented; test blocked | 22 |
| Implemented atomic behavior still lacks executable oracle | 117 |
| **Total** | **142** |

The two strict PASS L2s are Request Capture and TaskGraph Persistence &
Lifecycle Management. Capability Capsule Definition & Assembly is strict FAIL
because of duplicate versioned identity acceptance. All other L2s remain
blocked by an implementation gap or an executable-test gap; they are not
reported as passed merely because a representative probe passed.

The canonical workbook at
`docs/integrations/autosci/phase-22-test-report.xlsx` still contains only
Workflow Features, Foundation Features, Vertical Features, and Coverage
Summary. It now contains the reviewed atomic list, exact test path/selector/
runner/evidence fields, strict L2 roll-up, updated Atomic Coverage Resolution,
and static full-row colors: green for current atomic PASS, red for FAIL, gray
for not implemented, amber for environment-gated, yellow for manual-oracle
tags, and blue for bound/not-currently-run. The verified export was re-imported,
formula-scanned with zero error matches, visually checked on all four sheets,
and hash-matched to the canonical workbook. A temporary pre-rebuild copy is at
`.codex-tmp/phase22-atomic-executable/pre_atomic_rebuild.xlsx`. No commit or push
was performed.

## Environment / Provider Gate Configuration And Execution Audit

Logged: 2026-07-24 EDT

The 295 atomic rows previously tagged
`TAGGED_NOT_GENERATED_ENVIRONMENT_GATED` were audited individually. That tag
was originally assigned by a deliberately broad keyword heuristic (for terms
such as provider, resource, cost, app, tmux, Windows, and macOS); it was not
proof that a credential or dependency was actually missing. The reviewed audit
is reproducible from:

- `tests/platform/phase22/audit_environment_provider_gates.py`
- `tests/platform/phase22/environment_provider_gate_audit.json`
- `tests/platform/phase22/test_environment_provider_gate_audit.py`

Audit integrity result: **3 passed in 0.05s**.

| Reviewed gate disposition | Atomic features |
|---|---:|
| Local configuration resolved; related executable evidence is available | 179 |
| Local configuration resolved; relevant test still failed | 39 |
| Atomic selector/binding gap, not a configuration gate | 10 |
| External provider credential/account still required | 4 |
| Native platform, packaged application, GUI session, or real hardware required | 44 |
| Manual scientific/validity oracle required, not a configuration gate | 9 |
| Explicit implementation boundary, not a configuration gate | 10 |
| **Total reviewed heuristic environment/provider tags** | **295** |

Passing a related suite only proves that the environment gate is no longer the
blocker. It does not automatically promote every sibling atomic row to PASS;
an exact assertion-level selector must still be accepted for each atomic
behavior.

### Configuration and portability gaps repaired

- Installed `pytest` plus `requirements/harness.txt` into the temporary WSL
  environment `/tmp/opensolar-phase22-venv`; all WSL runs used
  `HOME=/tmp/opensolar-phase22-home`.
- Installed desktop Electron/Playwright dependencies and Chromium under
  repository-local ignored/temp paths. No browser payload was installed into
  the real user profile.
- Installed Pester 5.7.1 under `.codex-tmp/powershell-modules` and ran it with a
  process-scoped execution-policy bypass; system PowerShell modules were not
  changed.
- Added `harness/.env.example` with empty optional provider fields, and added
  explicit secret/runtime exclusions to `harness/.gitignore`.
- Added an LF policy for `harness/hooks/*` and normalized the executable
  `bin/solar`, `bin/solar-daemon`, and secret-scan hooks so WSL no longer sees
  `bash\r` or false end-of-file syntax errors.
- Made desktop test/verification scripts honor `PYTHON` and default to
  `python.exe` on Windows instead of hard-coding `python3`.
- Made the desktop bootstrap contract normalize CRLF before checking GitHub
  Actions workflow structure.
- Repaired the tmux/TUI integration suite's missing isolated registry/ledger
  fixtures and stale fake-ledger method signatures.
- Fixed the Windows CLI provider-onboarding fixture to expose a PATHEXT-aware
  fake `codex.cmd`.
- Used the repository's recorded Node 24 TypeScript loader for extensionless
  TypeScript imports; Bun was confirmed unnecessary for these probes.

### Representative execution evidence after configuration

- Windows CLI provider onboarding: **1 passed**.
- Resource/quota/operator/model/remote batches: **245 passed, 1 failed**. The
  failure is the Terminal-Bench dry-run verdict (`pending` returned where the
  contract expects `ok`), not an environment failure.
- Core benchmark and HIVE cluster TypeScript probes: **4 passed**.
- Headless Chromium GUI/Web gates: functional **9/9**, rapid session switching
  **2/2**, frontend scenarios **3/3**, and the full desktop/mobile/gate/error
  visual gate green.
- Desktop static/runtime contracts: runtime detection **10/10**, selftest
  verdict **7/7**, and bootstrap/package contract **18/18**.
- Linux installer/config suite: **38/38**; provider-aware onboarding passed.
- Windows installer Pester suite: **15/15**.
- tmux/TUI evidence: path-safety **4/4**, TUI integration **11/11**,
  notification bridge **3/3**, and pane-hygiene **4/4**.
- Web/status projections and deliverables: **34 passed** plus the standalone
  asset-package test passed.
- Scientific validity fixture/negative-control suites: **30 passed** after
  configuring `PYTHONPATH=harness:harness/lib`.
- Capability, scheduler, quota, routing, and search-provider suites: **52
  passed**.
- WeChat/Apple Notes controlled-fixture suite: **35 passed** (no live WeChat or
  Apple Notes account used).

### Failures or external gates that configuration cannot honestly erase

- `tests/harness/benchmark/test_terminal_bench_adapter.py`: **12 passed, 1
  failed**; dry-run verdict mismatch.
- `tests/harness/test_provider_actor_generation.py`: **4 failed**; current
  physical/provider/actor registries and schema have drifted (unknown browser
  provider, unsupported backend/provider pairs, removed expected operator,
  top-level provenance schema mismatch, and unresolved fallback targets).
- Model single-source/registry/live-route shell gates fail because the checked-in
  user model matrix and UI registry no longer match the GLM-oriented assertions;
  this is current configuration/contract drift, not missing credentials.
- `tests/harness/test_no_direct_tmux_send_keys.py`: **10 passed, 1 failed**;
  direct `tmux send-keys` call sites remain outside the policy allowlist.
- Electron process launch still exits before Playwright can attach in the
  current Codex Windows GUI session. Headless Web/GUI tests pass, but packaged
  Electron attachment/recovery screens remain a platform gate.
- Native macOS DMG, launchd, Apple Notes permission, macOS CLI lifecycle, and
  signed-package checks require a Mac runner.
- Four live-provider/login atomic behaviors require an explicitly authorized
  provider account/credential and permission to make live calls. No provider
  secret was present or read during this audit.
- The optional TVS doctor gate skipped because no `SOLAR_TVS_ROOT`/TVS checkout
  exists in the sandbox HOME.

The canonical workbook was not overwritten during this audit because Excel is
still holding `docs/integrations/autosci/phase-22-test-report.xlsx` open (the
`~$phase-22-test-report.xlsx` lock file is present). No commit or push was
performed.

### Canonical workbook sync after Excel lock release

Logged: 2026-07-27 EDT

Excel was closed and the lock file was no longer present. The audit results
above were therefore written directly into the single canonical workbook at
`docs/integrations/autosci/phase-22-test-report.xlsx`; no new report workbook
was created.

- All 295 formerly generic environment/provider-gated atomic rows were updated
  with their reviewed gate disposition, coverage relationship, current result,
  blocker reason, and disposition-specific row color.
- The saved disposition counts reconcile exactly to the audit JSON: 179 local
  configuration resolved with related executable evidence, 39 related-suite
  failures, 10 pure atomic-binding gaps, 4 external credential/account gates,
  44 platform/hardware gates, 9 manual-oracle cases, and 10 current
  implementation boundaries.
- The 10 implementation-boundary atomics changed the strict L2 roll-up for five
  L2 features. Final L2 distribution is 2 all-atomic PASS, 1 atomic-test FAIL,
  27 implementation blocked, and 112 executable-test-gap blocked (142 total).
- The Coverage Summary now distinguishes all seven audited dispositions. It
  reports 918 manual-oracle atomics, 48 external/provider/platform blocks (4
  credential/account plus 44 platform/hardware), and 150 not-implemented
  atomics.
- Workbook verification re-imported all four sheets, reconciled 1,502 atomic
  rows and 142 L2 groups, verified all 295 saved audit mappings, found zero
  spreadsheet formula-error strings, and visually rendered every sheet plus
  external-provider and implementation-boundary row samples.
- Audit integrity was rerun after the workbook sync: **3 passed in 0.05s**.

The macOS runner remains intentionally classified as platform blocked at the
user's request. No Mac tests were started.

For the four remaining live account/provider atomics, the code supports either
`OPENAI_API_KEY` or `OPENROUTER_API_KEY` for the AutoSci Review LLM live-opt-in
test. `OPENAI_API_KEY` is the broader single choice because the Codex runtime
doctor also recognizes it as provider authentication. OpenRouter does not
satisfy the Codex login-start/login-status contract: those two behaviors require
an actual `codex login --device-auth` session. No secret was requested in chat,
written to a tracked file, printed, or read during this sync, and no billable
provider call was made. A live call remains pending explicit user authorization
and local secret configuration. No commit or push was performed.

### Authorized AutoSci live-provider execution

Logged: 2026-07-27 EDT

The user populated the ignored local `harness/.env` and explicitly authorized
one live-provider test. The key value was never printed, copied into a tracked
file, or written to the progress log.

- Exact selector:
  `tests/plugins/autosci/test_autosci_live_provider_env_gated.py::test_autosci_live_review_llm_provider_produces_runtime_proof`
- The first pytest attempt failed during `tmp_path` setup because the default
  Windows pytest temp root was not accessible. It never entered the test
  function and made no provider call.
- The retry used a new repository-local `.codex-tmp` basetemp, disabled pytest
  cache writes, entered the test, and reached
  `https://api.openai.com/v1/chat/completions` with provider `openai` and model
  `gpt-5.5`.
- Result: **FAIL**. OpenAI returned **HTTP 429 Too Many Requests**. This is
  classified as an external provider quota/rate-limit/account-state failure;
  it is not evidence of a local assertion crash or an absent implementation.
- The generated JSON/JSONL evidence was scanned for an exact match of the local
  API key. Result: **no key found**.
- No automatic retry or OpenRouter fallback was attempted after the real 429
  response, so the single authorized provider invocation boundary was
  respected.

The canonical workbook now binds atomic `P22-AF-FN-058-08` (Provider
live-opt-in) directly to the exact selector above with
`REUSED_EXISTING_EXECUTABLE`, records atomic result `FAIL`, and colors that
atomic row red. The strict `Verification Asset Construction` L2 roll-up is now
`FUNCTION_IMPLEMENTED_ATOMIC_TEST_FAILED`. Workbook totals reconcile to 25
atomic PASS, 2 atomic FAIL, 3 still credential/account blocked, 44
platform/hardware blocked, and 1,502 total atomics. Strict L2 totals are 2 all
atomic PASS, 2 atomic-test FAIL, 27 implementation blocked, and 111
executable-test-gap blocked (142 total). The workbook was re-imported, all four
sheets were rendered, and zero spreadsheet formula-error strings were found.
No commit or push was performed.

### Authorized AutoSci live-provider retry with replacement key

Logged: 2026-07-27 EDT

The user replaced the locally configured OpenAI credential and explicitly
authorized one additional live-provider test. The ignored `harness/.env` was
loaded into the test process without printing or copying the key.

- Exact selector:
  `tests/plugins/autosci/test_autosci_live_provider_env_gated.py::test_autosci_live_review_llm_provider_produces_runtime_proof`
- The single authorized call reached OpenAI and returned a Chat Completions
  model response from `gpt-5.5-2026-04-23`; the provider/authentication path was
  therefore live for this run.
- Result: **FAIL** (`1 failed in 10.60s`). The returned model JSON contained
  usable `findings` and `review` content but omitted the top-level `status`
  required by `_normalize_review_llm_payload` (`completed` or `inconclusive`).
  AutoSci consequently classified `review_llm` as `invalid`, fell back to
  `local_surrogate`, and failed the runtime-proof contract.
- This supersedes the previous HTTP 429 explanation. It is now classified as
  an executable response-contract failure after a successful provider call,
  not an external provider availability or credential failure.
- The generated JSON/JSONL evidence was scanned for an exact match of the new
  local API key. Result: **no key found**.
- No automatic retry and no OpenRouter/fallback-provider call was made after
  the response, preserving the one-call authorization boundary.

The canonical workbook was overwritten in place. Atomic `P22-AF-FN-058-08`
remains `FAIL`, and its `Verification Asset Construction` L2 remains
`FUNCTION_IMPLEMENTED_ATOMIC_TEST_FAILED`; the explanatory cells and Coverage
Summary now describe the missing top-level `status` contract instead of HTTP
429. Counts remain 25 atomic PASS, 2 atomic FAIL, 3 credential/account blocked,
44 platform/hardware blocked, and 1,502 reviewed atomics. macOS remains
intentionally platform blocked. Workbook verification found zero spreadsheet
formula-error strings and retained the red failure styling. No commit or push
was performed.

### Review LLM provider response-contract repair

Logged: 2026-07-27 EDT

After the replacement-key live run showed that OpenAI returned useful review
content without the required top-level `status`, the provider integration was
repaired without making another live call.

- Native OpenAI requests now include a strict `json_schema` response format
  requiring the `schema`, `status`, and `outputs` envelope and the complete
  `review`/`findings` contract.
- The system prompt now explicitly prohibits flattening `review` or `findings`
  out of the top-level envelope.
- `openai_compatible` providers remain unchanged by default to avoid assuming
  that every third-party endpoint implements Structured Outputs. The
  `AUTOSCI_REVIEW_LLM_STRUCTURED_OUTPUTS` environment variable can explicitly
  override the default.
- Provider responses that omit only top-level `status` can now be normalized to
  `completed` when `review_mode` and `review_available` prove that the review
  envelope is otherwise valid. The normalization is recorded as an audit
  warning. This fallback is provider-only; manually supplied evidence and
  command bridges retain the strict status requirement.
- Added a regression test reproducing the actual flattened OpenAI response
  shape. It also asserts that native OpenAI sends strict JSON Schema and that
  the API key is absent from the request body.

Verification:

- Final targeted provider/command regression set: **3 passed in 3.69s**.
- An expanded Windows run reached **5 passed, 4 failed, 1 skipped**. All four
  failures were pre-existing path-normalization assertions expecting `/` while
  generated evidence references used `\\`; they occur outside the modified
  provider/normalizer behavior.
- Python compilation and `git diff --check` passed. The only Git messages were
  existing LF-to-CRLF working-copy warnings.

The canonical workbook intentionally remains at atomic/L2 `FAIL` because no
post-repair live provider test has been authorized or executed. No commit or
push was performed.

### Environment/provider gate resolution and execution

Logged: 2026-07-27 EDT

The remaining true credential/account gates were configured or converted to
controlled exact tests, then executed. macOS and other native-platform items
remain intentionally platform blocked.

- `harness/auth-helpers.sh status` confirmed the currently configured Codex
  authentication state (`codex=ok`, `codex_auth_json=true`) without returning a
  token or API key. Claude remains unavailable because its CLI is not installed;
  GLM remains unavailable because no key is configured. Neither is required by
  the three exact authentication atomics resolved here.
- Added
  `tests/vertical/account_management/test_authentication_session_security_env_gated.py`
  with exact selectors for provider-authenticated status, login start, and login
  status. The opt-in run with `SOLAR_LIVE_AUTH_STATUS_TEST=1` passed all three
  selectors: **3 passed in 1.82s**. Login start/status use controlled subprocess
  seams and do not mutate a real external account.
- The first post-repair Review LLM execution received and archived a valid
  OpenAI Structured Outputs response with `status=completed`, one finding, and
  normal `finish_reason=stop`. Its final sidecar write failed only because the
  deliberately unique pytest basetemp exceeded the Windows path-length limit.
- Re-running the same exact live-provider selector with short basetemp
  `.codex-tmp/lp2` passed: **1 passed in 11.23s**. No retry or provider fallback
  occurred within that run.
- The final live evidence tree was scanned for an exact match of the configured
  OpenAI key. Result: **no key found; zero read errors**. `harness/.env` remains
  ignored by `harness/.gitignore` and is not reported by `git status`. A second
  Unicode-safe scan covered both post-repair live evidence trees plus all files
  listed by Git as tracked or non-ignored; it also found **zero matches, zero
  read errors, and zero path errors**.
- The gate audit now records four rows as
  `CONFIG_RESOLVED_ATOMIC_TEST_PASSED`: `P22-AF-FN-058-08`,
  `P22-AF-VT-014-05`, `P22-AF-VT-014-08`, and `P22-AF-VT-014-09`.
  An initial non-opt-in audit/integrity run completed with **6 passed, 1
  skipped**; the skip was the intentionally opt-in live auth-status selector,
  not a failed or blocked selector. The final combined run set
  `SOLAR_LIVE_AUTH_STATUS_TEST=1` and completed with **7 passed in 0.35s**.
- The three focused Review LLM provider/command regression selectors completed
  with **3 passed in 3.78s**. Python compilation and `git diff --check` also
  passed; Git reported only existing LF-to-CRLF working-copy warnings.

The canonical workbook was overwritten in place with exact bindings, selectors,
commands, PASS results, and green atomic-row styling for all four resolved rows.
Strict roll-up totals now reconcile to 29 atomic PASS, 1 atomic FAIL, 0
credential/account blockers, 44 platform/hardware blockers, and 1,502 reviewed
atomics. L2 totals are 2 all-atomic PASS, 1 atomic-test FAIL, 27 implementation
blocked, and 112 executable-test-gap blocked (142 total). `Verification Asset
Construction` moved from atomic-test FAIL to `IMPLEMENTED_TEST_GAP_BLOCKED`
because seven sibling atomics still lack accepted executable bindings;
`Authentication & Session Security` remains implementation blocked because two
required sibling behaviors are outside the current implementation boundary.
All four workbook sheets were re-imported and rendered, and zero spreadsheet
formula-error strings were found. No commit or push was performed.

## L2 status synchronization
Logged: 2026-07-27 12:04:42
- Full source: C:\Users\j50058254\Desktop\Github repo\OpenSolar-Canonical\docs\integrations\autosci\phase-22-test-report.xlsx
- Brief synchronized in-place: C:\Users\j50058254\Downloads\AI4RnD Feature List.xlsx
- Matched and updated rows: 142
- Mapping run from full L2 atomic rollup status using explicit four-state mapping
- No atomic rows added or removed; row identity preserved by sheet + normalized L2 key.

- COMPLETE_FAIL: expected 1 / actual 1
- COMPLETE_PASS: expected 2 / actual 2
- IMPLEMENTATION_BLOCKED: expected 27 / actual 27
- TEST_GAPS_TAGGED: expected 112 / actual 112

## Phase 22 overnight journey integration closure
Logged: 2026-07-29 01:01:31 -04:00

Integration owner role: Phase 22 Overnight Verification Integration Owner.
Run ID: `overnight-phase22-20260729T044000Z`.
Repo head: `fd1d52684f340cdec16351c05228ce54569ea0e9`.

The overnight campaign converted the brief-report Level 2 inventory from a
journey-evidence gap state to a complete journey ledger. The starting brief
workbook contained 142 Level 2 rows: 6 `PASS_WITH_KNOWN_LIMITATIONS`, 3 `FAIL`,
7 `ENVIRONMENT_BLOCKED`, 100 `NOT_TESTED`, and 26 `NOT_AVAILABLE`. Starting
evidence-basis gaps were 67 `Journey planned; no direct L2 evidence` and 33
`No accepted journey evidence`.

Accepted final Level 2 ledger counts:

- `PASS`: 0
- `PASS_WITH_KNOWN_LIMITATIONS`: 7
- `FAIL`: 53
- `ENVIRONMENT_BLOCKED`: 24
- `NOT_AVAILABLE`: 58
- `NOT_TESTED`: 0
- `UNRESOLVED`: 0

Completion checks from
`outputs/phase22-real-journeys/overnight-phase22-20260729T044000Z/l2-evidence-ledger.json`:
142 brief L2 keys present, 142 ledger L2 keys present, zero duplicate keys,
zero unmatched observed Level 2 labels, zero planned-without-direct-evidence
rows, and zero rows with no accepted journey evidence.

Journey execution summary:

- `P22-J01`: `ENVIRONMENT_BLOCKED`; Git Bash/MINGW install probe returned
  unsupported OS, and WSL enumeration returned access denied.
- `P22-J02`: `ENVIRONMENT_BLOCKED`; live coding preflight found `bash` and
  `tmux` missing from PATH before sprint/provider execution.
- `P22-J03`: `FAIL`; official platform benchmark ran and scored below the
  acceptance threshold.
- `P22-J04`: `PASS_WITH_KNOWN_LIMITATIONS`; local ingest/re-ingest worked, with
  wiki registration still incomplete.
- `P22-J05`: `FAIL`; live/network discovery commands ran but produced zero
  candidates and no provider-backed source channel.
- `P22-J06`: `FAIL`; idea generation produced candidates but no
  verification-ready/falsifiable idea card.
- `P22-J07`: `PASS_WITH_KNOWN_LIMITATIONS`; local experiment execution and
  metrics passed, with terminal runtime/audit state limitations.
- `P22-J08`: `FAIL`; the evaluator supported a deliberately overbroad claim.
- `P22-J09`: `PASS_WITH_KNOWN_LIMITATIONS`; markdown report and evidence bundle
  were produced, with Review LLM/writeback/HITL compile boundaries limited.
- `P22-J10`: `ENVIRONMENT_BLOCKED`; Git Bash/MINGW lifecycle probe returned
  unsupported OS.
- `P22-J11`: `PASS_WITH_KNOWN_LIMITATIONS`; capsule/operator/model registry
  probes passed with version/governance limitations.
- `P22-J12`: `ENVIRONMENT_BLOCKED`; failure-recovery queue path imports
  Unix-only `fcntl`, and WSL access was denied.
- `P22-J13`: `FAIL`; local UI path crashes on Windows because
  `signal.SIGPIPE` is unavailable.
- `P22-J14`: `NOT_AVAILABLE`; no implemented WeChat channel intake entrypoint
  was found.
- `P22-J15`: `PASS_WITH_KNOWN_LIMITATIONS`; Windows/package lanes were
  recorded, while macOS app and CLI lanes remain platform blocked.

Command evidence:

- Initial collect-only for J01-J10: 10 tests collected, exit 0.
- Final collect-only for J01-J15: 15 tests collected, exit 0.
- Full non-live journeys: 13 selected, 5 passed, 4 skipped, 4 failed, exit 1.
- Live/provider journeys: 2 selected, J02 skipped, J05 failed, exit 1.
- Worker B J03/J04/J06: 1 passed, 2 failed.
- Worker C J07/J08/J09: 2 passed, 1 failed.
- Worker D J11-J15: 2 passed, 2 skipped, 1 failed.
- Workbook render and formula-error scans: 0 formula errors in the canonical
  full report and the staged synchronized brief report.
- `git diff --check`: exit 0.

Canonical and staged artifacts:

- Human-readable journey report:
  `docs/integrations/autosci/phase-22-journey-test-report.md`.
- Canonical full report workbook synchronized in place:
  `docs/integrations/autosci/phase-22-test-report.xlsx`.
- Staged synchronized brief report:
  `.codex-tmp/phase22-worker-results/overnight-phase22/staged-reports/AI4RnD Feature List.xlsx`.
- Brief workbook pre-sync backup:
  `.codex-tmp/phase22-worker-results/overnight-phase22/backups/AI4RnD Feature List.before-overnight-sync.xlsx`.
- Brief sync blocker record:
  `.codex-tmp/phase22-worker-results/overnight-phase22/brief-sync-blocker.json`.
- Final validator:
  `.codex-tmp/phase22-worker-results/overnight-phase22/final-validator.json`.

At this checkpoint, the final validator confirmed ledger completeness, valid
terminal statuses, formula-error count 0 for the full report and staged brief
report, staged brief counts matching the ledger, and `git diff --check` exit 0.
It failed only because the live brief workbook at
`C:\Users\j50058254\Downloads\AI4RnD Feature List.xlsx` was held by Excel PID
35768 with lock file
`C:\Users\j50058254\Downloads\~$AI4RnD Feature List.xlsx`, so the current
Downloads workbook remained at old baseline counts. The synchronized
replacement file was staged and ready to copy as soon as Excel released the
workbook. No git commit or push was performed.

### Brief workbook final synchronization after lock release
Logged: 2026-07-29 08:23:28 -04:00

Excel was no longer running, the brief workbook lock file was no longer
present, and the verified staged workbook was copied over
`C:\Users\j50058254\Downloads\AI4RnD Feature List.xlsx`.

The final validator passed after the copy. It confirms:

- current Downloads brief counts match the ledger:
  7 `PASS_WITH_KNOWN_LIMITATIONS`, 53 `FAIL`, 24 `ENVIRONMENT_BLOCKED`, and 58
  `NOT_AVAILABLE`;
- no current brief lock file is present;
- canonical full report formula-error scan: 0;
- staged brief formula-error scan: 0;
- ledger completeness: 142 of 142 brief Level 2 rows resolved, with 0
  `NOT_TESTED`, 0 unresolved, 0 planned-without-direct-evidence rows, and 0
  no-accepted-evidence rows;
- `git diff --check` exit 0.

No git commit or push was performed.

### P22-J02 Windows/WSL live provider rerun
Logged: 2026-07-29 12:47:17 -04:00

P22-J02 was rerun on the Windows machine through the `SolarUbuntu` WSL2 distro
after dependency and routing setup. The run used the existing Windows Codex auth
via `CODEX_HOME=/mnt/c/Users/j50058254/.codex`, added the WSL Codex CLI path
(`/home/solar/.local/bin`) to `PATH`, and explicitly enabled provider-mode
planner role spillover for the Codex/OpenAI provider route. No credentials were
printed or archived.

Dependency/setup changes made for the rerun:

- created a WSL-local pytest environment at `.codex-tmp/wsl-pytest-venv`;
- installed `pytest` and `requirements/harness.txt` into that environment;
- fixed `lib/installer/py-deps.sh` so an interpreter inside a virtualenv does
  not receive `pip install --user`;
- fixed `harness/bin/python3` line endings so the installed harness shim works
  under WSL;
- fixed the P22-J02 journey test so it waits for live Planner and Builder
  operator-result artifacts, refuses to submit `eval-verdict pass` until
  independent repair checks succeed, and binds the natural request to the
  isolated fixture repo.

Executed command:

`wsl.exe -d SolarUbuntu -- bash /mnt/c/Users/j50058254/Desktop/Github\ repo/OpenSolar-Canonical/.codex-tmp/run_j02_live_008.sh`

Result:

- Pytest: 1 selected, 1 passed, duration 825.41s.
- Worker batch: `phase22-j02-live-windows-008`.
- Journey evidence:
  `outputs/phase22-real-journeys/p22j02-20260729T163246Z-126196/journey-result.json`.
- Product status: `PASS_WITH_KNOWN_LIMITATIONS`.
- Planned J02 L2 support: 22/22.
- Durable artifacts: 20; artifact durability complete.
- Provider path: live Codex/OpenAI operator pool. Planner result from
  `mini-codex-gpt55-medium-planner-1`; Builder result from
  `mini-codex-gpt53-spark-builder-1`.
- Core assertions: baseline target test failed before repair; live planner
  produced design/plan/task graph; plan approval succeeded; live builder
  repaired the isolated repo; post-repair pytest passed; real git diff changed
  `calculator.py`; `eval-verdict` exited 0 and moved the sprint to `passed`.

Known limitation retained:

- `eval-verdict` accepted the sprint and status evidence is durable, but the
  legacy `eval.md` sidecar was not emitted. The J02 result is therefore
  `PASS_WITH_KNOWN_LIMITATIONS`, not plain `PASS`.

J02 is no longer an environment/provider blocker. The J02-only status delta is
22 L2s moved from `ENVIRONMENT_BLOCKED` to
`PASS_WITH_KNOWN_LIMITATIONS`; full workbook and brief workbook regeneration is
still required before the global counts are synchronized.

### P22-J15 macOS evidence portability clarification
Logged: 2026-07-29 14:05:12 -04:00

A macOS runner agent reported `MacOS CLI` as `PASS` and `MacOS App` as
`PASS_WITH_KNOWN_LIMITATIONS`. A later review on the Windows integration
machine initially treated the absence of the corresponding local run directory
as evidence that the macOS results could not pass. That inference was too
strong and is corrected here.

The Mac runner's raw and temporary artifacts were not transferred to the
Windows checkout. In particular, no files under `.codex-tmp/`,
`desktop/.npm-cache/`, or `outputs/phase22-real-journeys/` are tracked in the
current repository, so a Git pull cannot reproduce those local artifacts.
Whether this resulted from an ignore rule on the Mac runner or simply from the
files never being committed, absence on Windows does not establish that the Mac
execution failed.

The correct interpretation is therefore:

- the reported `MacOS CLI = PASS` and
  `MacOS App = PASS_WITH_KNOWN_LIMITATIONS` results may be valid Mac-platform
  results;
- the current Windows checkout cannot independently audit those results from
  the raw run artifacts presently available to it;
- this is an evidence-transfer and report-portability gap, not evidence of a
  macOS product failure;
- a hard-coded run ID or prose assertion in a synchronization script is not, by
  itself, sufficient durable execution evidence.

To close the audit gap without committing caches or large raw output trees, the
Mac runner should export a small, sanitized, tracked evidence summary. It must
contain at least the macOS version and architecture, Git commit, run ID, exact
commands or selectors, exit codes, checks performed for each L2, relevant
artifact names plus sizes or hashes, final statuses, and known limitations. It
must not contain credentials. After that summary is reviewed, the full and
brief reports should reference the portable evidence record instead of a
machine-local ignored output path. No J15 tests were rerun during this
clarification.

## Phase 22 report integration â€” J05 and J16â€“J19 evidence review

Logged: 2026-07-29

The primary agent acted as the single report integration owner. No tests were
rerun in this integration step. The following worker results were reviewed:

- `.codex-tmp/phase22-worker-results/J05-repair-001/result.json`
- `.codex-tmp/phase22-worker-results/TMUX-serial-001/result.json`
- the J16â€“J19 journey tests and their referenced evidence artifacts
- the latest accepted J06, J07, and J08 journey-result files recorded by the
  journey-failure repair batch

### Evidence acceptance decisions

- J05 remains `ENVIRONMENT_BLOCKED` for its seven search/discovery L2s. Live
  commands exited 0, but the product evidence still reported an incomplete
  literature-provider boundary and no accepted provider-backed source channel.
  `Model Routing & Selection` and `Model Usage Auditing` are `NOT_TESTED`
  because execution stopped before those features.
- J06 is no longer copied as a blanket failure. Seven mapped L2s are
  `PASS_WITH_KNOWN_LIMITATIONS`; `Falsifiability Screening & Hypothesis
  Contracting` and `Verification-Ready POC Design` remain `FAIL`.
- J07 is `PASS_WITH_KNOWN_LIMITATIONS` at journey level. The local experiment
  process and metric checks completed, while the lifecycle state remained
  unknown/inconclusive. Seven planned L2s without direct assertions were reset
  to `NOT_TESTED`; the earlier blanket J07 failure was removed. The observed
  label `Experiment Status & Evaluation` is not one of the canonical 142 L2
  rows and is retained as unmatched evidence metadata.
- J08 retains one direct product failure: `Claim & Acceptance-Criteria
  Comparison`. The other eight planned L2s are `NOT_TESTED` because the test
  did not execute their direct assertions or the planned artifact-review stage.
- J16 and J17 are `ENVIRONMENT_BLOCKED`. Their final pytest outcomes were
  successful skips, not product passes. The accepted blocker is the absence of
  tmux on the Windows host; the unset live-journey gate is a runner
  configuration detail and was not reported as a product defect.
- J18/J19 worker green labels were reviewed individually. Static code markers,
  non-empty error output, and fixture-only JSON roundtrips were not accepted as
  positive real-task evidence. Accepted positive results are limited to CLI,
  LLM Config, and User Settings where production handlers or entrypoints
  produced usable output.

### Integrated L2 counts

The canonical 142-L2 ledger now contains:

- `PASS`: 2
- `PASS_WITH_KNOWN_LIMITATIONS`: 38
- `FAIL`: 19
- `ENVIRONMENT_BLOCKED`: 35
- `NOT_AVAILABLE`: 27
- `NOT_TESTED`: 21

Every status other than `PASS` remains an open issue, so the issue register has
140 open L2 issues. The human-readable register is
`docs/integrations/autosci/phase-22-l2-issue-register.md`.

### Report synchronization state

- `docs/integrations/autosci/phase-22-test-report.xlsx` was updated in place.
- Atomic Coverage Resolution and Atomic Test Result content was verified
  unchanged; journey columns and L2-level colors were synchronized from the
  reviewed ledger.
- The brief report was regenerated with the same 142 rows and counts, while
  preserving its atomic diagnostic columns. Its staged, validated file is
  `outputs/phase22-report-integration-20260729/AI4RnD Feature List.xlsx`.
- After the user closed Excel, the validated workbook was copied to the
  canonical brief-report path at
  `C:/Users/j50058254/Downloads/AI4RnD Feature List.xlsx`. The copied file's
  SHA-256 matched the staged workbook.
- Formula-error scans found no `#REF!`, `#DIV/0!`, `#VALUE!`, `#NAME?`, or
  `#N/A` cells in either generated workbook.
- Final cross-artifact validation passed for all 142 L2 rows, all six status
  totals, and all 142 issue-register rows. Validator:
  `outputs/phase22-report-integration-20260729/final-validator.json`.

## Phase 22 final report integration audit

Logged: 2026-07-29 17:24:16 -04:00

Integration role: Phase 22 final report integration Agent.

The final integration audit reviewed the accepted report-integration state,
worker result files, journey-result files, issue register, full workbook, and
brief workbook. No product implementation code, journey test code, atomic test,
worker `result.json`, or raw journey evidence was changed.

Final synchronized 142-L2 counts:

- `PASS`: 2
- `PASS_WITH_KNOWN_LIMITATIONS`: 38
- `FAIL`: 19
- `ENVIRONMENT_BLOCKED`: 35
- `NOT_AVAILABLE`: 27
- `NOT_TESTED`: 21

Worker evidence reconciliation:

- `ACCEPTED`: 4
- `PARTIALLY_ACCEPTED`: 10
- `REJECTED_INSUFFICIENT_EVIDENCE`: 19
- `REJECTED_FALSE_POSITIVE`: 0
- `REJECTED_NAME_MAPPING_ERROR`: 0
- `SUPERSEDED`: 7

Generated final-integration artifacts:

- Final L2 ledger:
  `outputs/phase22-final-integration-20260729T172416/final-l2-ledger.json`.
- Worker evidence reconciliation:
  `outputs/phase22-final-integration-20260729T172416/worker-evidence-reconciliation.json`.
- Final validator:
  `outputs/phase22-final-integration-20260729T172416/final-validator.json`.

Validator result: `ok=true`. It confirmed 142 canonical L2 rows, zero duplicate
L2 keys, valid final statuses, non-empty issue statements, non-empty evidence,
142 issue-register rows, full/brief status consistency through the prior
integration validator, no formula-error markers in the full or brief workbook,
preserved atomic diagnostic columns, and successful rendered visual checks for
the brief summary, brief feature sheets, and full feature-sheet samples.

The Downloads brief workbook was readable and validated, but the Excel lock
file `C:\Users\j50058254\Downloads\~$AI4RnD Feature List.xlsx` was present
during this audit. The audit therefore did not overwrite the Downloads
workbook. The prior report-integration validator already records the canonical
brief overwrite as complete; this audit only revalidated the current readable
workbook state and reported the active lock boundary.

No status was changed merely to make the report greener. Static markers,
fixture-only roundtrips, unexecuted selectors, and superseded worker attempts
remained rejected or superseded in the reconciliation output.

## Final integration audit correction

Logged: 2026-07-29 17:44:08 -04:00

The previous final integration validator output at `outputs/phase22-final-integration-20260729T172416/final-validator.json` is superseded for audit purposes because it accepted non-empty evidence text without requiring existing evidence paths, inherited full/brief consistency from an older validator, marked color and visual checks as complete without direct row-by-row style comparison or image inspection, and classified worker batches through hard-coded batch-name lists.

This correction rebuilt the 142-L2 ledger from the full workbook, raw journey result files, worker result files, issue register context, and atomic diagnostic workbook evidence. It preserved the frozen final status counts: `PASS=2`, `PASS_WITH_KNOWN_LIMITATIONS=38`, `FAIL=19`, `ENVIRONMENT_BLOCKED=35`, `NOT_AVAILABLE=27`, and `NOT_TESTED=21`.

The worker reconciliation was regenerated from claim-level content rather than batch names. `TMUX-serial-001` is now treated through per-claim decisions, with the known worker/report conflicts explicitly rejected or downgraded for static-marker evidence, fixture-only roundtrips, non-empty error output, missing UI/TMUX/provider execution, product unavailability, platform blockers, or real product failure boundaries.

Known workbook gaps were repaired in the full report: one missing `Journey Evidence Path` for `Evaluator-Driven Operator Evolution`, plus seven missing `Journey Assertion` cells for P22-J09 deliverable/security/report rows. The brief workbook was not rewritten because it has no corresponding assertion/path columns and its existing L2 status/evidence text already matched the frozen ledger.

New final validator: `outputs/phase22-final-integration-rework-20260729T174408/final-validator.json`.

Missing evidence after correction: `Vertical::MacOS CLI` still lacks a current-machine direct journey evidence path. The macOS runner result remains status-frozen, but the portable raw evidence summary required for independent audit is not present in this Windows checkout.

## Overnight environment blocker resolution

Logged: 2026-07-30 08:20:00 -04:00

User explicitly approved J16/J17 live-provider execution. J16 and J17 were rerun in SolarUbuntu/WSL with live-provider gates enabled. J16 produced 7 PASS, 2 PASS_WITH_KNOWN_LIMITATIONS, and 2 FAIL L2 outcomes; the journey-level result is FAIL because harness/eval and scoped repair acceptance criteria were not met. J17 produced 12 PASS and 1 PASS_WITH_KNOWN_LIMITATIONS L2 outcomes; the journey-level result is FAIL because harness start/restart/eval-verdict tmux commands returned inner exit 1.

J18 and J19 were accepted as PASS_WITH_KNOWN_LIMITATIONS from local SolarUbuntu/status-dashboard evidence. J05 remained ENVIRONMENT_BLOCKED after seven low-frequency live Semantic Scholar preflight attempts returned HTTP 429 with no Retry-After and no API key variable present. Synchronized counts are PASS=20, PASS_WITH_KNOWN_LIMITATIONS=46, FAIL=21, ENVIRONMENT_BLOCKED=7, NOT_AVAILABLE=27, NOT_TESTED=21.

New validator: outputs/phase22-overnight-environment-resolution-20260730T122000Z/final-validator.json.

## Final J05 live-provider report synchronization

Logged: 2026-07-30 09:45 -04:00

The accepted J05 worker result at
`.codex-tmp/phase22-worker-results/J05-live-provider-001/result.json` was
reviewed against the raw journey evidence at
`outputs/phase22-real-journeys/p22j05-20260730T125408Z-13396/journey-result.json`.
The exact selector passed with exit code 0. Topic search and anchor-reference
discovery each returned five unique, non-fixture Semantic Scholar candidates,
with stable identities, source-channel provenance, completed provider
boundaries, and durable artifacts. Earlier HTTP 429/500 responses are retained
as provider-stability limitations.

The seven formerly environment-blocked J05 L2 rows were reconciled as follows:

- `PASS_WITH_KNOWN_LIMITATIONS`: Search Strategy Formation, Multi-Source Signal
  Discovery, Source Qualification, Signal Organization, Search Coverage Review.
- `NOT_TESTED`: Technical Signal Extraction, Trend & Gap Analysis. The accepted
  J05 evidence did not produce technical-signal or trend/gap outputs, so these
  rows were not inferred green.

The full report, brief report, L2 issue register, and journey report were
synchronized. Atomic diagnostic values were hash-checked before and after the
workbook edits and remained unchanged. Final counts are `PASS=20`,
`PASS_WITH_KNOWN_LIMITATIONS=51`, `FAIL=21`, `ENVIRONMENT_BLOCKED=0`,
`NOT_AVAILABLE=27`, and `NOT_TESTED=23`, totaling 142 L2 rows. Formula-error
scans returned zero matches in both workbooks. Final validator:
`outputs/phase22-final-sync-20260730T132000Z/final-validator.json`.

## Unified J03 benchmark and J23 live-provider synchronization

Logged: 2026-07-30

The J03 acceptance rule was corrected to test whether the benchmarking process
ran completely and reported the target result consistently, rather than
requiring the target under evaluation to score above the configured quality
threshold. The exact selector
`tests/journeys/phase22/code/test_j03_platform_benchmark.py::test_p22_j03_real_platform_workflow_benchmark`
passed. Accepted evidence:
`outputs/phase22-real-journeys/p22j03-20260730T183907Z-30832/journey-result.json`.
The 25/100 target score remains recorded as a product-quality finding. J03 now
contributes one `PASS` L2 and seven `PASS_WITH_KNOWN_LIMITATIONS` L2 results.

The latest J23 worker result
`.codex-tmp/phase22-worker-results/J23-model-routing-retry-007/result.json` was
reviewed against
`outputs/phase22-real-journeys/p22-j23-20260730T193026Z-398/journey-result.json`.
The exact WSL2 selector passed with exit code 0. A real OpenRouter `gpt-5.5`
request completed through the production AutoSci review entrypoint; the
requested and observed routes matched, request and response hashes were
retained, and prompt/completion/total token plus cost fields were recorded.
Provider latency was not returned. The successful route used WSL2 because the
Windows attempt encountered outbound socket error 10013. `Model Routing &
Selection` and `Model Usage Auditing` are therefore both
`PASS_WITH_KNOWN_LIMITATIONS`, not environment-blocked.

The full report, brief report, journey report, and 142-row L2 issue register
were synchronized. The current counts are `PASS=24`,
`PASS_WITH_KNOWN_LIMITATIONS=68`, `FAIL=22`, `ENVIRONMENT_BLOCKED=0`,
`NOT_AVAILABLE=28`, and `NOT_TESTED=0`. Eight management-requested likely-state
conclusions remain explicitly labeled as inferences rather than direct journey
proof. Atomic diagnostic columns were hash-checked and were unchanged. Both
workbooks contain zero formula-error markers. Final validation output:
`outputs/phase22-unified-sync-20260730/final-validator.json`.

## J23 final PASS criteria update and three-report synchronization

Logged: 2026-07-30

The user removed the requirement that a provider must return latency fields.
This requirement was not reliable because the provider can omit latency even
when the routed request and usage audit are otherwise complete. J23 still
requires a completed provider invocation, exact requested/observed
provider-model matching, no fallback, request/response hashes, and token/cost
usage evidence.

Worker result
`.codex-tmp/phase22-worker-results/J23-model-routing-retry-008/result.json` and
raw evidence
`outputs/phase22-real-journeys/p22-j23-20260730T203137Z-277/journey-result.json`
were reviewed. The exact selector passed in WSL2 with exit code 0. OpenRouter
`gpt-5.5` completed on the requested route with no fallback; request and
response hashes plus prompt, completion, total-token, and cost fields were
retained. `Model Routing & Selection` and `Model Usage Auditing` are both
`PASS`.

The full report, brief report, and user-created ultra-brief report were
synchronized. The ultra-brief report intentionally contains no atomic feature
columns, so its stale atomic-summary formulas were removed. Current L2 counts
are `PASS=26`, `PASS_WITH_KNOWN_LIMITATIONS=66`, `FAIL=22`,
`ENVIRONMENT_BLOCKED=0`, `NOT_AVAILABLE=28`, and `NOT_TESTED=0`. Final
validator: `outputs/phase22-j23-pass-sync-20260730/final-validator.json`.

## Phase 3/4 lead-integration preflight and Phase 0-2 baseline

Logged: 2026-08-05 EDT

Integration role: OpenSolar Phase 3/4 Lead Integration Agent. Phase 3/4 work
started from Phase 2 integration commit
`6444f9847cac90e21675368ad763cd5500b098d3` without modifying the main
worktree or pushing any branch.

Preflight checked the runtime-route, evidence-operators, lifecycle-operators,
and integration worktrees with `git status --short`, `git rev-parse HEAD`, and
`git branch --show-current`. All four worktrees were clean, all four were at
the required Phase 2 commit, and their checked-out branches matched the
assigned Phase 3/4 branches.

The first Phase 0-2 baseline command used a unique pytest basetemp below an
absent `.codex-tmp` parent. Pytest therefore reported `100 passed, 170 errors`;
all errors were fixture setup failures caused by the missing parent directory,
not product failures. The runner issue was resolved by creating the isolated
parent directory and rerunning the same test set with a new basetemp and cache
directory.

Rerun command:

`C:\Users\j50058254\Desktop\Github repo\OpenSolar-Canonical\.venv\Scripts\python.exe -m pytest tests/harness/contracts/test_research_orchestration_contracts.py tests/harness/research_orchestration -q --basetemp .codex-tmp\pytest-phase02-baseline-rerun -o cache_dir=.codex-tmp\pytest-cache-phase02-baseline-rerun`

Rerun result: `269 passed, 1 failed` in 79.31 seconds. The remaining failure is
`test_abandoned_process_claim_is_recovered_after_crash`. The child process had
already exited with code 23, but the Windows lease implementation still
treated its claim as active. This is classified as a product portability and
recovery defect in Windows process-liveness detection, not an environment
block. It remains open for the Phase 4 lifecycle-recovery work and requires a
targeted regression rerun plus the affected research-orchestration suite.

## Phase 3 production-route integration

Logged: 2026-08-05 EDT

Three isolated Phase 3 worker commits were reviewed and cherry-picked into the
integration branch: runtime/route `fca09f838dd7dbc7ac5514a07ce167c563c54034`
(integrated as `541096ad`), evidence operators
`e09555f7438d060547c298205d3bbbeb9bc370a7` (integrated as `7d0b0d6f`), and
lifecycle/action operators `9393ea2c5ebb360375dc75043703c3043abe0068`
(integrated as `0c2147ba`). Their isolated result records are under
`.codex-tmp/phase34-worker-results/` in the integration worktree.

Integration added a fail-closed unified physical-operator registry, explicit
production opt-in metadata, route aliases for URL, PDF, Markdown/text, survey,
evidence import, and workflow evolution, and bounded evidence/action operator
bindings. The production bridge now composes the Solar-owned runtime and
unified registry rather than the temporary monolithic backend.

Four integration defects were found with the real Markdown entrypoint and
fixed: local seed fields violated the frozen task schema; worker result hash
records named logical inputs rather than real output artifacts; JSON identity
was nested under schema-valid provenance but rejected by the boundary; and a
mutually exclusive PDF read scope survived Markdown subgraph pruning. A fifth
scope defect projected the entry seed into every downstream node. The final
implementation snapshots local files inside the artifact boundary, records
only verifiable artifact hashes, accepts complete identity in top-level fields
or provenance, prunes read scopes belonging to removed dependencies, and
projects seed-specific fields only to the selected entry node.

Validation results:

- Phase 0-3 contract/orchestration suite: `398 passed in 126.65s`.
- Hash and result-validation regressions: `77 passed`.
- Identity/operator/orchestrator regressions: `142 passed in 24.87s`.
- Final route and orchestrator regression:
  `87 passed in 27.64s`.
- Real Markdown production command used
  `autosci_bridge.py research --source
  tests/plugins/autosci/fixtures/sample_paper.md --max-steps 2` with
  run id `phase3-md-smoke-006`. It completed `material_ingest` and
  `paper_analyze`, produced durable artifacts and node records under
  `.codex-tmp/phase3-md-smoke-006/`, and then truthfully returned `blocked`
  because the deliberately bounded run exhausted two steps. This is accepted
  as Phase 3 route/dispatch smoke evidence, not as a full-lifecycle PASS.

The broad legacy AutoSci bridge/shim run remains diagnostic: `179 passed, 60
failed`, with failures concentrated in already-known Windows path/state and
legacy side-effect assumptions. Phase 4 owns full real-input journeys and the
Windows lease recovery defect; no Phase 22 workbook, matrix, journey report,
or brief report was modified.

## Phase 4 real-input generalization and lifecycle recovery

Logged: 2026-08-05 EDT

Phase 4 began from Phase 3 integration commit
`eaed505c5f83043f08e5b9e4d95e361a90a4b89e`. The real-input generalization
worker committed `026d10be2ec855573bde5feed499d8a0d62f506b` (integrated as
`56659124`), and the lifecycle-recovery worker committed
`78cdf00d877fa8700b30ab09c9c990e844e25fca` (integrated as `a91851a1`).
Both worker trees passed `git diff --check` and secret scanning and were clean
after commit. Neither branch was pushed.

The generalization worker exercised four distinct inputs through the
production bridge and the shared route/graph/operator stack:

- Chinese URL `https://news.qq.com/rain/a/20251207A0337Y00`: classified as
  `research_synthesis` with URL seed and physical start `seed_fetch`; it
  truthfully stopped `awaiting_external` because no `fetch_url` service was
  configured. No source-content success was claimed.
- English survey topic about WebAssembly runtime compiler optimization:
  classified as `literature_synthesis` with topic seed and physical start
  `source_discovery`; it truthfully stopped `awaiting_external` because no
  `discover_sources` service was configured.
- Local Markdown: physical start `material_ingest`; six nodes completed and a
  5,546-byte claims artifact with SHA-256
  `f48237f4c67a149cfe707a50aa408f3af0583d925666da489753d179032b50e6`
  was retained. The later code-evidence step failed because no repository/code
  input was supplied; it did not invent code linkage.
- Local PDF: physical start `paper_ingest`; five nodes completed and a
  12,058-byte paper-analysis artifact with SHA-256
  `1c7e0c34ab8c4aa83918106c29cff89f7ff182b41706b9bc258142d65aff42e7`
  was retained. Method extraction failed because the one-page PDF layout did
  not preserve a method heading; it did not invent a method.

The real-input work fixed general production defects rather than adding
input-specific workflows: explicit network authorization now approves bounded
non-live node capabilities; pruned subgraphs remove unreachable read scopes;
seed fetch uses the frozen typed seed; and claim/method/code nodes retain the
reachable ancestor evidence their physical operators require. Targeted tests
reported `15 passed`; the worker's related Phase 0-4 regression reported `120
passed in 38.03s`.

Lifecycle recovery fixed Windows process liveness with
`GetExitCodeProcess`/`STILL_ACTIVE`, made approval-gated nodes report
`awaiting_human`, enabled approval-bound redispatch on resume, and inserted an
explicit hash-bound `experiment_approval_gate` before experiment execution.
The core recovery matrix reported `171 passed`; targeted PID/gate/registry/
workflow/action tests reported `40 passed`. Covered behaviors include resume,
evidence import, stale leases, retry/backoff contracts, artifact-before-state
commit safety, concurrent claims, idempotent replay, human gates, approval-
bound experiment pause/resume, secret redaction, stdin transport, and Windows
path handling.

Environment probes found native Windows ready with limitations and WSL2
Ubuntu/Python available. Bubblewrap was absent in Windows and WSL, while
capability detection plus the minimal stdin/read-only fallback passed. No
OpenAI or Anthropic provider credentials were present, so provider retry is
contract-tested only and no live-provider success is claimed. The first
recovery runs under missing or deep worktree basetemps produced setup/path
errors; rerunning with a short isolated basetemp passed all 171 tests and
classifies those attempts as runner/path defects.

After both commits were integrated, the combined command covering the Phase
0-4 contracts, research-orchestration suite, synthesis operators, evidence
operators, and lifecycle action operators completed with `403 passed in
131.34s`. Worker evidence is retained in their isolated worktrees under
`.codex-tmp/phase34-worker-results/phase4-generalization/result.json` and
`.codex-tmp/phase34-worker-results/phase4-lifecycle-recovery/result.json`.
No Phase 22 workbook, matrix, journey report, final journey report, or brief
report was edited during Phase 3/4 integration.

## Phase 4 real-task acceptance rework

Logged: 2026-08-05 EDT

Role: OpenSolar Phase 4 Rework and Final Integration Agent. This work was
isolated in `C:\Users\j50058254\Desktop\Github repo\.phase34-worktrees\phase4-rework`
on branch `codex/phase4-rework`, based on integration commit
`d61cbb02b40c3b73efd57055eaf38b7d9a3f2dac`. The exact implementation tested
below is committed as `9d8eb1d4de112f87a4d479d15d53dfe3d884bc77`. No branch was pushed or merged.

### Defects, root causes, and general fixes

1. **Chinese URL research stopped at `awaiting_external`.** The production
   resolver had no `fetch_url` binding. A general bounded HTTP adapter now
   accepts only public HTTP(S), validates every redirect target, rejects
   embedded credentials and non-public addresses, enforces a 30-second
   timeout, five redirects, a 5 MiB response limit, and an allowlist of textual
   content types. It extracts visible text without executing page content and
   retains requested/final URL, fetch time, selected non-sensitive headers,
   raw/content/request hashes, and raw/metadata archives. Discovery now keeps
   the fetched page as the primary source and uses public-provider fallbacks
   for supplemental context. Failures retain their actual classification
   instead of generating content. Principal files:
   `harness/plugins/autosci/services/production_research.py`,
   `harness/plugins/autosci/operators/research_synthesis/seed_fetch.py`,
   `harness/plugins/autosci/bin/autosci_bridge.py`, and
   `harness/lib/research_orchestration/runtime.py`.

2. **English topic survey stopped at `awaiting_external`.** The production
   resolver had no `discover_sources` binding. The new discovery adapter reuses
   the existing AutoSci Semantic Scholar backend and has bounded OpenAlex and
   Crossref fallbacks; URL research can additionally use bounded Wikipedia
   context queries derived from visible headings. Every candidate retains
   provider, query, title, URL or identifier, provenance, and a stable content
   hash; provider traces are archived. Principal files:
   `harness/plugins/autosci/services/production_research.py`,
   `harness/plugins/autosci/services/__init__.py`,
   `harness/plugins/autosci/bin/autosci_bridge.py`, and
   `harness/plugins/autosci/operators/research_synthesis/report_draft.py`.

3. **Markdown synthesis incorrectly required `code_evidence_map`.** The full
   lifecycle graph had treated code mapping as unconditional. Pre-execution
   task conditions now retain that node only when a repository/code input or
   explicit code-analysis request exists. A skipped node is recorded with
   status `skipped`, condition, and the reason that no code input was supplied;
   downstream dependencies and read scopes are rewired before Solar creates
   the executable graph. Explicit repositories are copied into a bounded,
   hash-recorded code-only snapshot. Principal files:
   `harness/lib/research_orchestration/routing.py`,
   `harness/lib/research_orchestration/runtime.py`,
   `harness/lib/research_orchestration/orchestrator.py`, and
   `harness/workflows/scientific_research_lifecycle_full_v1.json`.

4. **PDF synthesis failed when no Method heading survived extraction.** Method
   extraction now distinguishes `explicitly_extracted`,
   `extracted_with_inference`, and `insufficient_evidence`. Content without a
   heading is used only when it contains procedural cues and always retains its
   source anchor. When no method evidence exists, the operator completes with
   an empty method list and the explicit limitation `No method was
   synthesized`; downstream report planning, drafting, review, publication,
   and final evaluation preserve that limitation. Missing core source evidence
   still fails: a `missing-evidence:*` placeholder is never treated as a real
   report source. Principal files:
   `harness/plugins/autosci/operators/scientific_lifecycle/evidence/operators.py`,
   `harness/plugins/autosci/operators/scientific_lifecycle/action/delivery.py`,
   `harness/plugins/autosci/operators/scientific_lifecycle/action/common.py`,
   `harness/plugins/autosci/operators/scientific_lifecycle/action/registry.py`,
   `harness/schemas/evidence/research_method.v1.schema.json`, and
   `harness/schemas/evidence/research_final_evaluation.v1.schema.json`.

Production report writers now emit hash-recorded Markdown in addition to JSON.
The artifact reviewer evaluates the produced report, publication creates a
usable final Markdown file, and `final_evaluation` evaluates the actual review,
bundle, file manifest, and evidence links. Physical operators explicitly do
not mutate graph or run status; Solar alone derived all final statuses.

### Provider binding and cost-control result

The production model adapter has stable identity
`autosci-production-research-model@1.0.0`, HTTPS-only endpoints, a 60-second
timeout, serializable JSON I/O, request/response/archive hashes, classified
errors, and no serialized authorization headers. It supports deterministic
fake injection in tests. The accepted URL and topic reports were generated
through the OpenRouter endpoint (model route `openai/gpt-5.5`), not the OpenAI
API endpoint. After the user requested a cheaper model, commit `9d8eb1d4`
removed legacy live-review environment variables from research routing, made
OpenRouter the default when both keys exist, changed the default model to
`deepseek/deepseek-v3.2`, and made OpenAI explicitly selectable only through
`AUTOSCI_RESEARCH_LLM_PROVIDER=openai` or the explicit fallback flag. When
OpenAI is inactive its key is not included in the run authorization service
map.

A minimal production probe ran with only the OpenRouter key in the process.
It returned provider `openrouter`, model `deepseek/deepseek-v3.2`, one
structured claim, request SHA-256
`6fcd60843f51a2e5d0fa9d8877119fc6715501e546e34f946c15859443bd2e83`,
and response SHA-256
`165ed91d970176e10f404796131872bdfc3b8368c1ef81438613eb846a35a781`.
Its non-secret exchange record is under
`.codex-tmp/phase4-rework/openrouter-cheap-probe/service-evidence/model/`.
No additional full-report model call was made after this cost-control request.

### Accepted production runs

#### Chinese URL report

Exact bridge command:

```text
python harness/plugins/autosci/bin/autosci_bridge.py research --prompt '请研究并分析以下网页所讨论的技术主题：https://news.qq.com/rain/a/20251207A0337Y00。完整获取和解析网页内容，结合多个可追溯的公开资料进行补充研究，生成结构清晰、证据链接完整的中文技术报告，并明确结论与局限。' --run-id phase4-rework-url-003 --source 'https://news.qq.com/rain/a/20251207A0337Y00' --artifact-root .codex-tmp/phase4-rework/url-003 --output-language Chinese --allow-network --allow-live-provider --approval-ref phase4-user-authorized --max-steps 100
```

Exit code 0; duration 292.5 seconds; final Solar state `completed`; final gate
`accepted`. The bounded fetch read 286,494 bytes at
`2026-08-05T14:55:41Z`; raw SHA-256 is
`d630c0a039a69305d7ad95953a7d6a2f0dfc84da29133b47c39f68900219ac90`
and extracted-content SHA-256 is
`103a6fa92508dcbef854331712c227d7aa1c0a0e3aba6d5cc1cf04495ef0b2a0`.
Seven sources were validated: the fetched Tencent page plus six Chinese
Wikipedia contextual results for AI, robot-industry, automotive, and flying-
car concepts. Five sources were actually cited across nine claims and six
conclusions. The 18,456-byte Chinese report is structurally usable and directly
analyzes the page's 2049 technology-vision topic.

- Report: `.codex-tmp/phase4-rework/url-003/artifacts/research_synthesis_v1/report/report.md`
- Report SHA-256: `2c5e62a6ee45d1fc79342ed9938065e90672507aa304547832e3350d3846096c`
- Final acceptance: `.codex-tmp/phase4-rework/url-003/artifacts/research_synthesis_v1/final/final_acceptance.json`
- Source, validation, and fetch evidence:
  `.codex-tmp/phase4-rework/url-003/artifacts/research_synthesis_v1/` and
  `.codex-tmp/phase4-rework/url-003/service-evidence/`
- Solar state: `.codex-tmp/phase4-rework/url-003/state/phase4-rework-url-003.research_run_state.json`
- Node states: `seed_fetch`, `source_discovery`, `source_validation`,
  `evidence_synthesis`, `report_draft`, `independent_review`, and
  `final_acceptance` all `completed`.

Earlier URL attempts are not acceptance evidence. `url-001` exposed live-
provider capability authorization; `url-002` retained Semantic Scholar and
OpenAlex HTTP 429 evidence and a model timeout. Other defects were repaired
while respecting the required retry interval; `url-003` later completed via
the legal provider fallback chain.

#### English WebAssembly survey

Exact bridge command:

```text
python harness/plugins/autosci/bin/autosci_bridge.py research --prompt 'Survey compiler optimization techniques for WebAssembly runtimes, comparing performance tradeoffs and open research problems.' --run-id phase4-rework-topic-002 --artifact-root .codex-tmp/phase4-rework/topic-002 --output-language English --allow-network --allow-live-provider --approval-ref phase4-user-authorized --max-steps 100
```

Exit code 0; duration 110.7 seconds; final Solar state `completed`; final gate
`accepted`. Semantic Scholar supplied eight traceable candidates. Three are
direct WebAssembly evidence (runtime fuzzing, call-graph construction, and edge
runtime characterization); five are clearly treated as supplemental compiler,
CPU/HPC, or instruction-scheduling evidence. Seven sources were cited across
seven claims and five conclusions. The 12,747-byte English report explicitly
compares startup, peak-throughput, compilation-cost, code-size, portability,
and safety trade-offs and lists open research problems.

- Report: `.codex-tmp/phase4-rework/topic-002/artifacts/research_synthesis_v1/report/report.md`
- Report SHA-256: `6af1455af959ad5c62feffc1f5680ba62686e03a7aacfc81012d5cb225996349`
- Final acceptance: `.codex-tmp/phase4-rework/topic-002/artifacts/research_synthesis_v1/final/final_acceptance.json`
- Discovery/model evidence: `.codex-tmp/phase4-rework/topic-002/artifacts/research_synthesis_v1/` and
  `.codex-tmp/phase4-rework/topic-002/service-evidence/`
- Solar state: `.codex-tmp/phase4-rework/topic-002/state/phase4-rework-topic-002.research_run_state.json`
- Node states: `source_discovery`, `source_validation`, `evidence_synthesis`,
  `report_draft`, `independent_review`, and `final_acceptance` all `completed`.

The earlier `topic-001` content run is not acceptance evidence because its
workflow did not declare the Markdown output. The workflow declaration was
fixed before `topic-002`.

#### Local Markdown synthesis

Exact bridge command:

```text
python harness/plugins/autosci/bin/autosci_bridge.py research --prompt 'Synthesize this local Markdown into an evidence-backed technical report about Solar-native adapter boundaries, preserving the method and result.' --run-id phase4-rework-md-001 --source tests/plugins/autosci/fixtures/sample_paper.md --artifact-root .codex-tmp/phase4-rework/md-001 --max-steps 100 --approval-ref phase4-user-authorized
```

Exit code 0; final Solar state `completed`; final evaluation `accepted`. The
411-byte local source was copied into the run boundary with SHA-256
`163738ba4b4aa33c842153e601b09d6d18ef1d6872b5cf486fc0985e6084f10e`.
The method was explicitly extracted. `code_evidence_map` and eight other
non-applicable idea/experiment/final-mutation nodes were recorded as
conditional skips; none was represented as a successful execution.

- Final report: `.codex-tmp/phase4-rework/md-001/artifacts/scientific/scientific_research_lifecycle_full_v1/09_report/final-report.md`
- Report size/hash: 1,026 bytes;
  `de27c7a769906d910ec6a32604811c8e5b337c275c9fc1c8dcaee5eb8d44d258`
- Final evaluation: `.codex-tmp/phase4-rework/md-001/artifacts/scientific/scientific_research_lifecycle_full_v1/09_report/research_final_evaluation.v1.json`
- Evidence tree: `.codex-tmp/phase4-rework/md-001/artifacts/scientific/scientific_research_lifecycle_full_v1/`
- Solar state: `.codex-tmp/phase4-rework/md-001/state/phase4-rework-md-001.research_run_state.json`
- Completed lifecycle nodes: `material_ingest`, `paper_analyze`,
  `memory_update_initial`, `graph_update`, `claim_extract`, `method_extract`,
  `claim_verify`, `report_plan`, `report_draft`, `artifact_review`,
  `publication_produce`, and `final_evaluation`.

#### Local PDF synthesis

Exact bridge command:

```text
python harness/plugins/autosci/bin/autosci_bridge.py research --prompt 'Synthesize this local PDF study into a structured evidence-backed report about adapter auditability, including method, result, and limitations.' --run-id phase4-rework-pdf-001 --source 'C:\Users\j50058254\Desktop\Github repo\.phase34-worktrees\phase4-generalization\.codex-tmp\phase4-generalization\solar_adapter_fixture.pdf' --artifact-root .codex-tmp/phase4-rework/pdf-001 --max-steps 100 --approval-ref phase4-user-authorized
```

Exit code 0; final Solar state `completed`; final evaluation `accepted`. The
1,505-byte PDF was actually parsed and snapshotted with SHA-256
`0726b22c5067780895578ede27fb08187a30892cebf0e5be9653a1667bfee1f6`.
Its method artifact completed with `methods=[]` and
`method_evidence_status=insufficient_evidence`; the report explicitly says no
method was synthesized. This limitation did not block the evidence-grounded
core synthesis.

- Final report: `.codex-tmp/phase4-rework/pdf-001/artifacts/scientific/scientific_research_lifecycle_full_v1/09_report/final-report.md`
- Report size/hash: 2,130 bytes;
  `a0002133ba81464b4dd4b39d7cc974e8c10893df8188f21d032a9837d9512f1c`
- Method evidence: `.codex-tmp/phase4-rework/pdf-001/artifacts/scientific/scientific_research_lifecycle_full_v1/03_methods/research_method.v1.json`
- Final evaluation: `.codex-tmp/phase4-rework/pdf-001/artifacts/scientific/scientific_research_lifecycle_full_v1/09_report/research_final_evaluation.v1.json`
- Evidence tree: `.codex-tmp/phase4-rework/pdf-001/artifacts/scientific/scientific_research_lifecycle_full_v1/`
- Solar state: `.codex-tmp/phase4-rework/pdf-001/state/phase4-rework-pdf-001.research_run_state.json`
- Completed lifecycle nodes: `paper_ingest`, `paper_analyze`,
  `memory_update_initial`, `graph_update`, `claim_extract`, `method_extract`,
  `claim_verify`, `report_plan`, `report_draft`, `artifact_review`,
  `publication_produce`, and `final_evaluation`.

The Markdown and PDF paths jointly demonstrate the full applicable lifecycle:
input snapshot, ingestion, analysis, initial memory and graph evidence, claims
and methods, evidence synthesis/verification, report plan, report draft,
artifact review, publication production, and final evaluation. Dependencies
were dispatched only after completion; non-applicable code/idea/experiment
nodes were conditionally removed before graph execution.

### Tests and final quality gates

Final production-service and action-operator command:

```text
& 'C:\Users\j50058254\Desktop\Github repo\OpenSolar-Canonical\.venv\Scripts\python.exe' -m pytest -q tests/plugins/autosci/scientific_lifecycle_action_operators/test_action_delivery_operators.py tests/plugins/autosci/test_production_research_services.py --basetemp='C:\tmp\p4-rework-bt-core-evidence' -o cache_dir='C:\tmp\p4-rework-cache-core-evidence'
```

Exit code 0; 30 passed, 0 failed, 0 skipped in 0.56 seconds. Output tail:
`30 passed in 0.56s`. This covers fetch/discovery composition and safety,
OpenRouter-first/no-OpenAI-key binding, report/review/publication/final
evaluation, and the missing-core-evidence failure boundary.

Final Phase 2-4 high-signal command:

```text
& 'C:\Users\j50058254\Desktop\Github repo\OpenSolar-Canonical\.venv\Scripts\python.exe' -m pytest -q tests/harness/contracts/test_research_orchestration_contracts.py tests/harness/research_orchestration/ tests/plugins/autosci/research_synthesis_operators/ tests/plugins/autosci/test_evidence_physical_operators.py tests/plugins/autosci/scientific_lifecycle_action_operators/ --basetemp='C:\tmp\p4-rework-bt-highsignal5' -o cache_dir='C:\tmp\p4-rework-cache-highsignal5'
```

Exit code 0; 411 passed, 0 failed, 0 skipped in 143.39 seconds. Output tail:
`411 passed in 143.39s (0:02:23)`. The original integrated baseline was 403
passed, so the final result adds eight regression tests without losing a baseline
test. Included coverage has URL/topic/Markdown/PDF routing, optional code node
with and without repository input, all three method-evidence variants,
registry completeness, report production, lifecycle final evaluation, and the
specified Phase 2-4 high-signal paths.

A plain `python -m pytest` attempt did not start because that PowerShell
session resolved `python` to the Windows Store placeholder (exit code 1;
duration 0.3 seconds; output tail `Python was not found`). It was classified as
a runner/PATH issue and rerun with the repository virtual-environment
executable above. It is not product evidence.

Final pre-commit checks on all 23 implementation/test files reported
`git diff --check` exit 0 and `SECRET_SCAN_PASS`; the scan compared the changed
files against three configured secret values without printing them and also
checked common literal API-key shapes. No `.env`, credential, `.codex-tmp`,
output artifact, workbook, matrix, journey report, or lock file was staged.

### Final result and known limitations

All four required real tasks meet their minimum acceptance conditions and have
both a non-empty usable final report and Solar-owned `completed` state with an
accepted final gate or evaluation. Phase 4 real-task acceptance is therefore complete
for the exercised production paths.

Known non-core limitations retained in the reports and evidence are:

- The URL report's supplemental Wikipedia sources provide concept and industry
  context, not independent proof of the Tencent article's long-horizon 2049
  forecasts or numeric milestones.
- The WebAssembly survey has three directly WebAssembly-specific sources and
  five broader compiler/HPC sources, so it is a bounded survey rather than an
  exhaustive systematic review.
- The local lifecycle artifact reviewer is a deterministic structural
  surrogate and does not replace independent scientific peer review.
- The PDF contains insufficient method evidence; the accepted report preserves
  that limitation and does not invent a method.
- Acceptance artifacts remain local under ignored `.codex-tmp` directories as
  required and are not part of Git history.

### Inspector repair and superseding acceptance evidence (2026-08-05)

The preceding acceptance conclusion was rejected by the upper-level inspector:
the Markdown report omitted its extracted method and truncated its result, the
local final evaluator accepted content without checking the actual task
contract, and the four runs were not reliably bound to the final implementation
commit. This subsection supersedes the accepted-run evidence above. Historical
attempts remain recorded, but only the four `phase4-rework2-*-009/010` runs
below are final acceptance evidence.

The inspector-repair implementation is commit
`5c3c1d9074c9672ad54096f6bc6b435ea6b7fb01`. Every accepted run records that
exact `repo_head`, `worktree_status=clean`, and the selected workflow identity
and version in top-level run provenance and final evaluation/gate provenance.

#### Inspector findings, causes, and repairs

1. **Markdown content fidelity.** Sentence splitting treated newlines as hard
   claim boundaries and the report compiler did not render method artifacts.
   Claim extraction now preserves complete source sentences across wrapped
   lines, collapses duplicate ingest views, and retains the original result
   semantics. The publication report now has a Methods section containing the
   method name, summary/procedure, evidence IDs, and extraction basis. The
   `sample_paper.md` acceptance report contains `deterministic bridge action`,
   `Solar Evidence ABI`, `result.json`, `evidence.jsonl`, and the statement that
   no monolithic AutoSci workflow owner is invoked.

2. **Final evaluator fidelity.** The evaluator previously treated non-empty
   artifacts as sufficient. It now evaluates the full user intent, every task
   success criterion, required method/result/limitation content, evidence
   linkage, artifact-review mode and task-contract hash, usable publication
   manifest, and final report text. It rejects title-only, irrelevant,
   missing-method, missing-result, unchecked-criteria, and review-contract
   mismatch cases. An honestly disclosed `local_surrogate` review can satisfy
   the local structural-review contract but is never represented as independent
   peer review. Insufficient method evidence becomes an explicit limitation and
   does not by itself fail an otherwise grounded synthesis.

3. **Commit-bound evidence.** Solar now captures real Git provenance before
   execution. Unavailable Git metadata is recorded as `unavailable`, never
   synthesized. Physical operators propagate but do not mutate this provenance
   or global status; Solar remains the graph/state/final-status owner.

4. **Online report quality found during reruns.** Structured provider sections
   are preserved without duplicating headings; inline method descriptions are
   cautiously extractable without requiring a Method heading; limitation
   headings may contain semantic prefixes or numbering; duplicate parsed views
   are merged; and final acceptance now requires at least two sources to be
   actually cited, not merely discovered. This deterministic gate correctly
   rejected an earlier hallucinated-publisher URL report and a later report
   citing only one source before the final accepted run.

Modified implementation/schema/test files in this inspector repair are:

- `harness/lib/research_orchestration/orchestrator.py`
- `harness/lib/research_orchestration/runtime.py`
- `harness/lib/research_orchestration/selection.py`
- `harness/plugins/autosci/operators/research_synthesis/base.py`
- `harness/plugins/autosci/operators/research_synthesis/final_acceptance.py`
- `harness/plugins/autosci/operators/research_synthesis/report_draft.py`
- `harness/plugins/autosci/operators/scientific_lifecycle/action/common.py`
- `harness/plugins/autosci/operators/scientific_lifecycle/action/delivery.py`
- `harness/plugins/autosci/operators/scientific_lifecycle/evidence/base.py`
- `harness/plugins/autosci/operators/scientific_lifecycle/evidence/operators.py`
- `harness/plugins/autosci/operators/scientific_lifecycle/evidence/registry.py`
- `harness/plugins/autosci/operators/scientific_lifecycle/registry.py`
- `harness/schemas/draft/research_task_contract.v1.schema.json`
- `harness/schemas/evidence/research_final_evaluation.v1.schema.json`
- `harness/schemas/evidence/research_run_state.v1.schema.json`
- `harness/workflows/scientific_research_lifecycle_full_v1.json`
- `tests/plugins/autosci/research_synthesis_operators/test_research_synthesis_operators.py`
- `tests/plugins/autosci/scientific_lifecycle_action_operators/test_action_delivery_operators.py`
- `tests/plugins/autosci/test_evidence_physical_operators.py`
- `tests/harness/contracts/test_research_orchestration_contracts.py`
- `tests/harness/research_orchestration/test_research_production_runtime.py`

#### Final production environment and commands

The two online commands ran with only `OPENROUTER_API_KEY` and
`SEMANTIC_SCHOLAR_API_KEY` injected into the child process from the existing
ignored project configuration. `OPENAI_API_KEY` was removed from those child
processes. The selected provider/model was
`openrouter/deepseek/deepseek-v3.2`; every model evidence record identifies
`autosci-production-research-model@1.0.0`. No secret value or complete
environment was logged, copied, or committed.

Chinese URL command:

```text
& 'C:\Users\j50058254\Desktop\Github repo\OpenSolar-Canonical\.venv\Scripts\python.exe' harness/plugins/autosci/bin/autosci_bridge.py research --prompt '请研究并分析以下网页所讨论的技术主题：https://news.qq.com/rain/a/20251207A0337Y00。完整获取和解析网页内容，结合多个可追溯的公开资料进行补充研究，生成结构清晰、证据链接完整的中文技术报告，并明确结论与局限。' --run-id phase4-rework2-url-010 --source 'https://news.qq.com/rain/a/20251207A0337Y00' --artifact-root .codex-tmp/phase4-rework2/url-010 --output-language Chinese --allow-network --allow-live-provider --approval-ref phase4-user-authorized --max-steps 100
```

Exit code 0; duration 105.51 seconds; run ID
`phase4-rework2-url-010`; Solar `completed`; final gate `accepted/pass`.
`seed_fetch`, `source_discovery`, `source_validation`, `evidence_synthesis`,
`report_draft`, `independent_review`, and `final_acceptance` all completed.
The bounded HTTP service returned 200 for the requested/final QQ URL with zero
redirects, `text/html; charset=utf-8`, and 286,494 bytes at
`2026-08-05T18:07:49Z`. Raw SHA-256 is
`d630c0a039a69305d7ad95953a7d6a2f0dfc84da29133b47c39f68900219ac90`;
extracted-content SHA-256 is
`103a6fa92508dcbef854331712c227d7aa1c0a0e3aba6d5cc1cf04495ef0b2a0`.
Seven sources were validated (the QQ report plus six Chinese Wikipedia context
sources), three were cited across four claims and one conclusion, and all
five gate criteria passed. The 6,554-byte Chinese report is relevant to the
`科技预见与未来愿景2049` themes and explicitly preserves uncertainty.

- Report: `.codex-tmp/phase4-rework2/url-010/artifacts/research_synthesis_v1/report/report.md`
- Fetch/discovery/model evidence: `.codex-tmp/phase4-rework2/url-010/service-evidence/`
- Final gate: `.codex-tmp/phase4-rework2/url-010/artifacts/research_synthesis_v1/final/final_acceptance.json`
- State: `.codex-tmp/phase4-rework2/url-010/state/phase4-rework2-url-010.research_run_state.json`

English topic command:

```text
& 'C:\Users\j50058254\Desktop\Github repo\OpenSolar-Canonical\.venv\Scripts\python.exe' harness/plugins/autosci/bin/autosci_bridge.py research --prompt 'Survey compiler optimization techniques for WebAssembly runtimes, comparing performance tradeoffs and open research problems.' --run-id phase4-rework2-topic-010 --artifact-root .codex-tmp/phase4-rework2/topic-010 --output-language English --allow-network --allow-live-provider --approval-ref phase4-user-authorized --max-steps 100
```

Exit code 0; duration 85.46 seconds; run ID
`phase4-rework2-topic-010`; Solar `completed`; final gate `accepted/pass`.
`source_discovery`, `source_validation`, `evidence_synthesis`, `report_draft`,
`independent_review`, and `final_acceptance` all completed. Semantic Scholar
returned eight traceable candidates and all eight validated; five sources were
actually cited across five claims and one conclusion. Three sources are
directly WebAssembly-specific (runtime fuzzing, call-graph construction, and
edge-runtime characterization); the remaining five are explicitly bounded
compiler/CPU/HPC context. The 4,314-byte English report contains dedicated
Performance Trade-offs and Open Research Problems sections, and all five gate
criteria passed.

- Report: `.codex-tmp/phase4-rework2/topic-010/artifacts/research_synthesis_v1/report/report.md`
- Discovery/model evidence: `.codex-tmp/phase4-rework2/topic-010/service-evidence/`
- Final gate: `.codex-tmp/phase4-rework2/topic-010/artifacts/research_synthesis_v1/final/final_acceptance.json`
- State: `.codex-tmp/phase4-rework2/topic-010/state/phase4-rework2-topic-010.research_run_state.json`

Local Markdown command:

```text
& 'C:\Users\j50058254\Desktop\Github repo\OpenSolar-Canonical\.venv\Scripts\python.exe' harness/plugins/autosci/bin/autosci_bridge.py research --prompt 'Synthesize this local Markdown into an evidence-backed technical report about Solar-native adapter boundaries, preserving the method and result.' --run-id phase4-rework2-md-009 --source tests/plugins/autosci/fixtures/sample_paper.md --artifact-root .codex-tmp/phase4-rework2/md-009 --max-steps 100 --approval-ref phase4-user-authorized
```

Exit code 0; duration 1.34 seconds; run ID `phase4-rework2-md-009`;
Solar `completed`; final evaluation `accepted_with_limitations`. The 411-byte
input snapshot has SHA-256
`163738ba4b4aa33c842153e601b09d6d18ef1d6872b5cf486fc0985e6084f10e`.
One complete result claim and one explicitly extracted method are rendered with
their source anchors. Every success criterion and explicit method/result
requirement passed. The 1,489-byte report contains every inspector-required
content phrase.

- Report: `.codex-tmp/phase4-rework2/md-009/artifacts/scientific/scientific_research_lifecycle_full_v1/09_report/final-report.md`
- Final evaluation: `.codex-tmp/phase4-rework2/md-009/artifacts/scientific/scientific_research_lifecycle_full_v1/09_report/research_final_evaluation.v1.json`
- Evidence tree: `.codex-tmp/phase4-rework2/md-009/artifacts/scientific/scientific_research_lifecycle_full_v1/`
- State: `.codex-tmp/phase4-rework2/md-009/state/phase4-rework2-md-009.research_run_state.json`

Local PDF command:

```text
& 'C:\Users\j50058254\Desktop\Github repo\OpenSolar-Canonical\.venv\Scripts\python.exe' harness/plugins/autosci/bin/autosci_bridge.py research --prompt 'Synthesize this local PDF study into a structured evidence-backed report about adapter auditability, including method, result, and limitations.' --run-id phase4-rework2-pdf-009 --source 'C:\Users\j50058254\Desktop\Github repo\.phase34-worktrees\phase4-generalization\.codex-tmp\phase4-generalization\solar_adapter_fixture.pdf' --artifact-root .codex-tmp/phase4-rework2/pdf-009 --max-steps 100 --approval-ref phase4-user-authorized
```

Exit code 0; duration 2.04 seconds; run ID `phase4-rework2-pdf-009`;
Solar `completed`; final evaluation `accepted_with_limitations`. The 1,505-byte
PDF snapshot has SHA-256
`0726b22c5067780895578ede27fb08187a30892cebf0e5be9653a1667bfee1f6`.
It was actually parsed into `abstract` and `recovered-text` evidence views,
which were merged to avoid duplicate claims. The report preserves two result
claims. One method description was cautiously extracted from inline text with
`extraction_basis=method_description_without_heading`, confidence 0.6, and
both source anchors; the report explicitly says that no Method heading existed
and does not invent additional procedure. Every criterion and the explicit
method/result/limitations requirements passed. The report is 2,199 bytes.

- Report: `.codex-tmp/phase4-rework2/pdf-009/artifacts/scientific/scientific_research_lifecycle_full_v1/09_report/final-report.md`
- Method evidence: `.codex-tmp/phase4-rework2/pdf-009/artifacts/scientific/scientific_research_lifecycle_full_v1/03_methods/research_method.v1.json`
- Final evaluation: `.codex-tmp/phase4-rework2/pdf-009/artifacts/scientific/scientific_research_lifecycle_full_v1/09_report/research_final_evaluation.v1.json`
- Evidence tree: `.codex-tmp/phase4-rework2/pdf-009/artifacts/scientific/scientific_research_lifecycle_full_v1/`
- State: `.codex-tmp/phase4-rework2/pdf-009/state/phase4-rework2-pdf-009.research_run_state.json`

For both local runs, all 12 applicable nodes completed: input ingestion,
`paper_analyze`, `memory_update_initial`, `graph_update`, `claim_extract`,
`method_extract`, `claim_verify`, `report_plan`, `report_draft`,
`artifact_review`, `publication_produce`, and `final_evaluation`.
`code_evidence_map` was recorded as skipped because no code/repository input or
explicit code-analysis request was supplied. The idea/experiment nodes,
`memory_update_final`, and `workflow_evolve` were also explicitly skipped as
not applicable. The report dependency chain continued across these skips.

#### Superseding regression and quality gates

Final targeted operator/registry/routing command:

```text
& 'C:\Users\j50058254\Desktop\Github repo\OpenSolar-Canonical\.venv\Scripts\python.exe' -m pytest -q tests/plugins/autosci/research_synthesis_operators tests/harness/research_orchestration/test_phase3_unified_production_registry.py tests/harness/research_orchestration/test_research_production_routing.py --basetemp C:\tmp\p4-cited-gate-bt -o cache_dir=C:\tmp\p4-cited-gate-cache
```

Exit code 0; 70 passed, 0 failed, 0 skipped in 6.57 seconds; command duration
7.01 seconds; output tail: `70 passed in 6.57s`.

Final Phase 2-4 high-signal command, including the production-service tests
used by the inspector:

```text
& 'C:\Users\j50058254\Desktop\Github repo\OpenSolar-Canonical\.venv\Scripts\python.exe' -m pytest -q tests/harness/contracts/test_research_orchestration_contracts.py tests/harness/research_orchestration tests/plugins/autosci/research_synthesis_operators tests/plugins/autosci/test_evidence_physical_operators.py tests/plugins/autosci/scientific_lifecycle_action_operators tests/plugins/autosci/test_production_research_services.py --basetemp C:\tmp\p4-cited-final-bt -o cache_dir=C:\tmp\p4-cited-final-cache
```

Exit code 0; **432 passed, 0 failed, 0 skipped in 113.01 seconds**; command
duration 113.44 seconds; output tail: `432 passed in 113.01s (0:01:53)`.
This supersedes the inspector's 417-test run and covers bounded fetch and live
discovery adapters, URL/topic/Markdown/PDF routes, code-input present/absent
conditions, explicit/inline/absent method cases, strict positive and negative
final-evaluation cases, unified-registry completeness, commit provenance,
source-citation diversity, and all specified Phase 2-4 high-signal suites.

Earlier `phase4-rework2` attempts are diagnostic evidence only. In particular,
`url-008` was correctly rejected for a hallucinated publisher/report identity,
and `url-009` was correctly rejected for citing only one source. Earlier
Semantic Scholar/OpenAlex 429s were retained without secrets while other work
continued; bounded retry/fallback logic was exercised, and the final topic run
completed through Semantic Scholar.

Known non-core limitations for these final runs are: the local Markdown/PDF
review is an explicitly disclosed structural surrogate, not independent peer
review; the PDF method was inferred cautiously from procedural prose without a
Method heading; the online writer and reviewer use the same OpenRouter
provider/model identity; the URL's supplemental Wikipedia sources are context,
not independent proof of 2049 forecasts; the WebAssembly survey is bounded and
five of eight validated sources are broader compiler/CPU/HPC context; and live
provider candidates still require human review. No core acceptance blocker
remains for the four exercised tasks.

## NOT_TESTED production-path validation and review

Logged: 2026-08-10

Five isolated workers added and executed production-path validation for the ten
L2 rows recorded as `NOT_TESTED` by the later known-issues final integration.
The integration review read each worker result and evidence set, inspected the
new journey tests, and independently reran all five exact test files with
separate `--basetemp` and cache directories. The review run completed with
`5 passed`, zero pytest failures, and zero collection errors. A passing pytest
result here means the executable audit reached and truthfully classified the
product behavior; it does not mean every audited L2 passed its product success
criteria.

Accepted L2 decisions:

- `PASS_WITH_KNOWN_LIMITATIONS`: `Memory, Retrieval, and Evidence (Memory
  Learning / Self-RAG / Reranker Training)`; `Runtime and Resource Routing
  (Bayesian Optimization / Bandits / Cost-Aware RL)`; `Trace Graph
  Management`; `Data, Benchmarks, Curriculum, and Observability (Active
  Learning / Hard-Case Mining / Credit Assignment)`.
- `FAIL`: `Technical Signal Extraction`; `Trend & Gap Analysis`; `Execution
  Trace Search & Inspection`.
- `NOT_AVAILABLE`: `Text-Based Artifacts (GEPA / MIPROv2 / TextGrad)`; `DAG
  and Agent Organization (AFlow / MCTS / ADAS)`; `Model Policies and Weights
  (SFT / LoRA / DPO / GRPO / Agent RL)`.

The literature production path obtained five real public sources and completed
provider-backed discovery, but it did not emit source-traceable structured
technical signals or a cross-source trend. The richer research route failed at
the planner with Windows `PermissionError: [WinError 5] Access is denied`, so
both literature-analysis L2 rows are product `FAIL`, not test PASS.

The execution-trace production endpoint correctly filtered by run and returned
chronological results, but ignored project, actor, and time-range filters. Trace
graph persistence itself worked with Windows limitations. The named AFlow,
MCTS, ADAS, SFT, LoRA, DPO, GRPO, Agent RL, MIPROv2, and TextGrad product
bindings were not found; these rows are now classified as unavailable rather
than left untested. Generic metric routing, persistent retrieval, and the
harness-native hard-case/scorecard loop worked only for their supported subset
and therefore remain limited passes.

Accepted worker evidence:

- `.codex-tmp/phase22-worker-results/NT-literature/result.json`
- `.codex-tmp/phase22-worker-results/NT-optimization-routing/result.json`
- `.codex-tmp/phase22-worker-results/NT-memory-retrieval/result.json`
- `.codex-tmp/phase22-worker-results/NT-model-training/result.json`
- `.codex-tmp/phase22-worker-results/NT-dag-trace/result.json`

The resulting counts are `PASS=26`, `PASS_WITH_KNOWN_LIMITATIONS=72`,
`FAIL=17`, `ENVIRONMENT_BLOCKED=2`, `NOT_AVAILABLE=25`, and `NOT_TESTED=0`,
totaling 142. The full, brief, and ultra-brief reports were synchronized. The
full report retains the latest upstream atomic diagnostic values and formulas
while its L2 journey fields, evidence, and status colors agree with the brief
reports. The L2 issue register was regenerated from the synchronized full
report.

Final validation confirmed identical 142-L2 counts across all three reports,
all ten reviewed evidence bindings, no `NOT_TESTED` rows, no formula-error
markers, and unchanged atomic diagnostic values/formulas. Validation output:
`outputs/phase22-not-tested-report-sync-20260810/final-validator.json`.

### Post-baseline routing audit isolation repair

Logged: 2026-08-10

After rebasing the accepted Phase 22 evidence onto `origin/openJiuwen-Solar`,
the optimization/routing journey initially failed because its synthetic
operator registry was not mirrored at the newer runtime-state seam. The
sandbox's empty production registry therefore classified both fixture-owned
operators as disabled and returned `operator_selector_no_match`. The journey
test now supplies an isolated runtime-state lookup for its two fixture-owned
operators while leaving the production selector, scoring rules, and success
assertions unchanged. This is a test-isolation repair, not a product-status
override.

### Repair issue packets regenerated with freshness gates

Logged: 2026-08-10

Generated a current-baseline repair handoff for every Phase 22 L2 recorded as
`FAIL`, `ENVIRONMENT_BLOCKED`, or `PASS_WITH_KNOWN_LIMITATIONS`. Per user
instruction, GitHub CI findings and the 25 `NOT_AVAILABLE` rows are excluded.
The output contains 91 stable issue packets: 15 recorded blockers, 72
limitations requiring severity/reproduction triage, 2 mild failures, and 2
macOS evidence-reconciliation items. Every packet contains the L2 contract,
recorded observation, production entrypoints, exact selector(s), evidence
paths, repair success evidence, and a mandatory current-baseline verification
decision before product edits.

Freshness review explicitly flags six J21-based `FAIL` rows as likely stale
because the current J21 source recommends pass or limited-pass outcomes, the
J08 validity-evaluator row as an inferred mapping, the trace-search diagnostic
as encoding the known failed-filter behavior, and both macOS rows as evidence
reconciliation rather than confirmed product failures. No L2 report status was
changed by this packaging step. Artifacts:

- `docs/integrations/autosci/phase-22-repair-issue-packets.json`
- `docs/integrations/autosci/phase-22-repair-issue-packets.md`

### P0 severity repair wave 1 accepted fixes

Logged: 2026-08-10

Started the severity-driven P0 repair wave from
`docs/integrations/autosci/phase-22-repair-issue-packets.json` at baseline
`c331eec8b905007b785fa494041af1efc2139a89`. Per user instruction, GitHub CI
findings were excluded because CI is being handled separately.

Accepted and integrated two reviewed worker commits into
`codex/fix-autosci-plan-governance`:

- `51a0b0072` (`P22-REPAIR-055`): `harness/lib/capability_capsules.py` now
  rejects duplicate capability capsule registry identities by
  `(capsule_kind, capability_capsule_id, version)`. Worker baseline evidence
  reproduced the exact selector failure; post-repair validation passed
  `tests/foundation/capability_capsules/test_capability_capsule_definition_atomic.py`
  plus `tests/harness/test_capability_capsules.py` with 14 passing tests.
- `ab8d5aee7` (`P22-REPAIR-037`, `039`, `066`, `095`, `110`, `119` evidence
  freshness): `harness/plugins/autosci/bin/autosci_workspace_projector.py` now
  writes projected AutoSci workspace pages through a Windows long-path-safe
  helper. The current J21 journey selector passed after integration, confirming
  the POC build and handoff path works in this Windows worktree when the
  projector can write long sandbox artifact paths.

Current classification decisions from the accepted worker results:

- `P22-REPAIR-055`: `CONFIRMED_REPRODUCIBLE`, repaired, post-repair `PASS`.
- `P22-REPAIR-113`: stale as a recorded `FAIL`; current J09 rerun is
  `PASS_WITH_KNOWN_LIMITATIONS`, so no product edit was accepted for this row.
- `P22-REPAIR-115` and `P22-REPAIR-116`: `ENVIRONMENT_BLOCKED` on this Windows
  machine because the exact J16 tmux journey requires a tmux-capable runtime.
- J21-backed P0 rows remain evidence-update candidates rather than confirmed
  hard failures after the integrated J21 selector passed; report status changes
  are deferred until the integration owner regenerates and validates the shared
  reports.

Integration validation run in the main worktree:

- `.venv\Scripts\python.exe -m pytest tests/foundation/capability_capsules/test_capability_capsule_definition_atomic.py tests/harness/test_capability_capsules.py -q --basetemp .codex-tmp/pytest/root-integrated-capsules-basetemp -o cache_dir=.codex-tmp/pytest/root-integrated-capsules-cache`
  -> 14 passed.
- `.venv\Scripts\python.exe -m pytest tests/journeys/phase22/code/test_j21_experiment_build_handoff.py::test_p22_j21_real_experiment_build_and_handoff --basetemp .codex-tmp/pytest/root-integrated-j21-basetemp -o cache_dir=.codex-tmp/pytest/root-integrated-j21-cache`
  -> 1 passed.

Remaining P0 work after this entry: complete the research/scientific reliability
group (`P22-REPAIR-018`, `020`, `033`, `034`, `070`) and finish report
regeneration/validation after all accepted P0 fixes are integrated.

Follow-up correction: review of the `p0-experiment` worker result showed that
the accepted J21 repair consisted of three commits, not only the final projector
commit. The integration owner subsequently cherry-picked and validated the full
B-worker chain:

- `d67082239`: update the J21 artifact resolver to read POC artifacts from the
  current action evidence payload as well as legacy top-level artifact lists.
- `03798df61`: make generated experiment POC assets and the generated POC runner
  write result files through Windows long-path-safe helpers.
- `ab8d5aee7`: make AutoSci workspace projector page writes long-path-safe.

After the full B-worker chain was integrated, the main worktree reran
`tests/journeys/phase22/code/test_j21_experiment_build_handoff.py::test_p22_j21_real_experiment_build_and_handoff`
with `.codex-tmp/pytest/root-integrated-j21-after-bfull-basetemp` and the
selector passed. `git diff --check` also passed.

Research P0 follow-up triage was also run in the `p0-research` worktree before
being interrupted for lack of final handoff. The accepted read-only
classifications from current-baseline journey evidence are:

- `P22-REPAIR-018` and `P22-REPAIR-020` remain confirmed product failures.
  Latest NT-literature evidence found five real public sources and one gap, but
  still recorded no structured signal types, no cross-source trend, and no
  completed real-data research run. The latest journey-result continued to
  recommend `FAIL` for both Technical Signal Extraction and Trend & Gap
  Analysis.
- `P22-REPAIR-033` and `P22-REPAIR-034` remain confirmed incomplete. Latest
  J06 passed overall only as `PASS_WITH_KNOWN_LIMITATIONS`; its L2 observations
  still marked falsifiability contracts and verification-ready POC design as
  false. Latest J07 remained `FAIL` with only partial verification-ready POC
  design evidence.
- `P22-REPAIR-070` appears stale or mis-mapped as a recorded P0: latest J08
  passed and produced claim/acceptance comparison evidence. No product edit was
  accepted for this inferred validity-evaluator packet during this wave.

Superseding repair entry for `P22-REPAIR-018` and `P22-REPAIR-020`: the main
worktree repaired the NT-literature production evidence path so the accepted
journey now emits source-backed method, technical-claim, and experiment/evidence
signals, an explicit cross-source trend comparison, a source-backed gap and
uncertainty section, and a bounded real-data research probe result without
claiming the full protected research lifecycle executed. The repair keeps the
survey limitations explicit: signals are title/source-level triage until
paper-level extraction verifies exact methods and measured effects.

Implementation changes in
`harness/plugins/autosci/bin/autosci_bridge.py`:

- `write_survey` now derives conservative signal, trend, and gap sections from
  the supplied citation map, preserving source ids in each evidence list.
- `discover_literature` now falls back to the existing provider-backed discovery
  backend when the native `tools/discover.py from-anchors` subprocess times out
  before producing a shortlist.
- `run_research_lifecycle` now writes
  `real-data-workspace/real-data-research-run.json` for explicitly online
  requests as a bounded read-only probe, while leaving the main lifecycle status
  gated/inconclusive unless full stage evidence is supplied.

Validation:

- `.venv\Scripts\python.exe -m pytest tests/journeys/phase22/code/test_p22_nt_literature_analysis.py::test_phase22_not_tested_literature_signal_and_trend_validation --basetemp .codex-tmp/pytest/root-nt-literature-after-a2-basetemp -o cache_dir=.codex-tmp/pytest/root-nt-literature-after-a2-cache`
  -> 1 passed.
- Evidence run:
  `outputs/phase22-not-tested/NT-literature/nt-literature-20260810T194729Z-26168/journey-result.json`.
  Observed five real public sources, signal types
  `experiment_or_evidence`, `method`, and `technical_claim`, one trend, two
  gaps, and `research_run_status=completed`.
- Both affected Level 2 rows now recommend `PASS_WITH_KNOWN_LIMITATIONS` with
  zero failed assertions in the accepted run.

Superseding repair entry for `P22-REPAIR-033` and `P22-REPAIR-034`: current
main-worktree J06/J07 evidence no longer supports the earlier hard-fail
classification. J06 generated source-backed idea cards with complete
risk/falsifiability/validation/minimum-experiment fields, and J07 generated a
local POC design with command allowlist, expected artifacts, and success
criteria. The journey recorder code was stale: it continued to hard-code the
affected Level 2 observations as `false`/generic `partial` even when the
assertions and product evidence showed verification-card and POC-design
coverage.

Recorder updates:

- `tests/journeys/phase22/code/test_j06_idea_generation.py` now derives
  Falsifiability Screening & Hypothesis Contracting and Verification-Ready POC
  Design observations from the actual verification-ready card assertion.
- `tests/journeys/phase22/code/test_j07_experiment_lifecycle.py` now records
  Verification-Ready POC Design support from the produced `experiment_plan.v1`
  command allowlist, expected artifacts, and success criteria.

Validation:

- `.venv\Scripts\python.exe -m pytest tests/journeys/phase22/code/test_j06_idea_generation.py::test_p22_j06_idea_generation --basetemp .codex-tmp/pytest/root-j06-recorder-fix-basetemp -o cache_dir=.codex-tmp/pytest/root-j06-recorder-fix-cache`
  -> 1 passed.
- `.venv\Scripts\python.exe -m pytest tests/journeys/phase22/code/test_j07_experiment_lifecycle.py::test_p22_j07_experiment_lifecycle --basetemp .codex-tmp/pytest/root-j07-recorder-fix2-basetemp -o cache_dir=.codex-tmp/pytest/root-j07-recorder-fix2-cache`
  -> 1 passed.
- Accepted evidence runs:
  `outputs/phase22-real-journeys/p22j06-20260810T195057Z-22316/journey-result.json`
  and
  `outputs/phase22-real-journeys/p22j07-20260810T195140Z-33668/journey-result.json`.
  J06 remains `PASS_WITH_KNOWN_LIMITATIONS` because live literature discovery
  and provider-backed novelty were not in this offline journey; J07 remains
  `PASS_WITH_KNOWN_LIMITATIONS` because final status/audit terminal checks are
  still incomplete. Both affected L2 observations are now recorded as
  `partial`, not `false`.

Current `P22-REPAIR-070` check: reran
`tests/journeys/phase22/code/test_j08_claim_verification.py::test_p22_j08_claim_verification`
with `.codex-tmp/pytest/root-j08-final-check-basetemp`; the selector passed.
The accepted evidence run
`outputs/phase22-real-journeys/p22j08-20260810T195252Z-15324/journey-result.json`
is `PASS` and records Claim & Acceptance-Criteria Comparison as exercised
through `exp-eval`. No product edit was accepted for `P22-REPAIR-070`; the
packet remains stale/mis-mapped against current journey evidence.

P0 wave closure summary for the baseline packet set:

- Repaired or superseded by accepted current evidence: `P22-REPAIR-018`,
  `P22-REPAIR-020`, `P22-REPAIR-033`, `P22-REPAIR-034`, `P22-REPAIR-037`,
  `P22-REPAIR-039`, `P22-REPAIR-055`, `P22-REPAIR-066`, `P22-REPAIR-095`,
  `P22-REPAIR-110`, and `P22-REPAIR-119`.
- Stale/mis-mapped or evidence-refresh only: `P22-REPAIR-070` and
  `P22-REPAIR-113`.
- Environment blocked on this Windows host: `P22-REPAIR-115` and
  `P22-REPAIR-116` because the exact tmux journey requires a tmux-capable
  runtime.

Shared report/workbook regeneration is still deferred until the remaining
non-P0 packet triage is complete and can be synchronized in one reviewed pass.

P1 triage wave started after P0 closure. Three read-only subagents classified
the `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` packets by category and wrote
isolated results under `.codex-tmp/phase22-p1-triage/` without editing shared
reports or matrices. The highest-confidence cross-category actionable cluster
was J24 privacy lifecycle: `P22-REPAIR-135` and the privacy/security portion of
`P22-REPAIR-069`.

Accepted J24 repair: `lib/installer/copy-engine.sh` no longer uses a bare
`cp -R` before cleanup when `rsync` is unavailable. The fallback now uses a
`tar` stream with the same runtime-state exclusions applied before copying, so
live harness state such as `run/codex-state` and dangling symlinks are not
copied into sandbox installs. This keeps the installer contract as "copy code
and packaged assets, not machine state" and fixes the Windows/Git Bash failure
where `cp` exited before lifecycle execution.

Validation:

- `bash -n lib/installer/copy-engine.sh` -> passed.
- `.venv\Scripts\python.exe -m pytest tests/journeys/phase22/code/test_j24_privacy_lifecycle.py::test_p22_j24_real_privacy_lifecycle --basetemp .codex-tmp/pytest/root-j24-copy-fix-basetemp -o cache_dir=.codex-tmp/pytest/root-j24-copy-fix-cache`
  -> 1 passed.
- Evidence run:
  `outputs/phase22-real-journeys/p22-j24-20260810T200556Z/journey-result.json`.
  The journey now recommends `PASS_WITH_KNOWN_LIMITATIONS`; remaining
  limitations are local-only privacy lifecycle coverage and no cloud-account
  policy revocation or consent-dashboard variant.

Accepted J18 LLM Config repair for `P22-REPAIR-139`: the status-server settings
write path now preserves the user-facing model aliases selected through
`POST /settings` while keeping the underlying pane route aliases canonical.
Specifically, `harness/lib/symphony/status-server.py` records a separate
`model_aliases` map for user-visible aliases such as `opus`, `sonnet`, and
`anthropic-sonnet`, continues to write unambiguous `models.*` route aliases
such as `claude-opus` and `claude-sonnet`, and returns both the user-facing
`applied_models` and diagnostic `applied_canonical_models`.

Validation:

- `PHASE22_ENABLE_SERIAL_TMUX_JOURNEYS=1 .venv\Scripts\python.exe -m pytest tests/journeys/phase22/code/test_j18_tmux_cli_status_config.py::test_p22_j18_tmux_cli_status_config --basetemp .codex-tmp/pytest/root-j18-llm-alias-basetemp -o cache_dir=.codex-tmp/pytest/root-j18-llm-alias-cache`
  -> 1 passed, with two Windows cp1252 subprocess-reader warnings.
- Accepted isolated evidence:
  `.codex-tmp/phase22-worker-results/T3-tmux-prep-001/artifacts/j18-llm-config.json`
  now records `llm_model_roundtrip_ok=true`,
  `missing_expected_aliases=[]`, `status=ok`, no secrets in the output, and
  `applied_models` preserving `claude-opus`, `sonnet`, `opus`, and
  `anthropic-sonnet`.
- J18 prep summary:
  `.codex-tmp/phase22-worker-results/T3-tmux-prep-001/artifacts/j18-overall-prep-summary.json`
  now records `LLM Config=PASS` and `User Settings=PASS`. Linux CLI remains
  `ENVIRONMENT_BLOCKED` on this Windows host, and TMUX/Web Status Service
  remain `PASS_WITH_KNOWN_LIMITATIONS` under prep-mode evidence.

Additional non-acceptance check: `tests/harness/status_server/test_settings_concurrency.py`
was run as a script and reported 8/9 checks passing, with the remaining failure
being a Windows `PermissionError` direct-file-read race during concurrent
`os.replace` writes. That issue is tracked as a separate settings-concurrency
portability limitation and was not used to reject the J18 alias repair because
the J18 acceptance selector passed and the new alias layer does not change the
atomic write primitive.

Accepted J04 ingest/wiki registration repair for `P22-REPAIR-083`,
`P22-REPAIR-084`, and `P22-REPAIR-090`: `harness/plugins/autosci/bin/autosci_bridge.py`
now performs local AutoSci wiki registration during `ingest_paper` after the
research memory/graph sidecars are written and before the final source
registration boundary is computed. The repair writes or refreshes the paper
page, graph edge, log entry, index, and context brief under the isolated
workspace wiki, while preserving the existing behavior where a pre-registered
paper/page/graph/index/context does not require a log entry to be considered
ready.

Validation:

- `.venv\Scripts\python.exe -m py_compile harness/plugins/autosci/bin/autosci_bridge.py`
  -> passed.
- `.venv\Scripts\python.exe -m pytest tests/plugins/autosci/test_bridge_smoke.py::test_phase9_ingest_registration_boundary_does_not_require_log_entry harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_ingest_final_source_registration_boundary_ready_with_wiki_state --basetemp .codex-tmp/pytest/root-j04-ingest-focused2-basetemp -o cache_dir=.codex-tmp/pytest/root-j04-ingest-focused2-cache`
  -> 2 passed.
- `.venv\Scripts\python.exe -m pytest tests/journeys/phase22/code/test_j04_paper_ingestion.py::test_p22_j04_paper_ingestion --basetemp .codex-tmp/pytest/root-j04-wiki-after2-basetemp -o cache_dir=.codex-tmp/pytest/root-j04-wiki-after2-cache`
  -> 1 passed.
- Accepted journey evidence:
  `outputs/phase22-real-journeys/p22j04-20260810T201812Z-22340/journey-result.json`
  now records `status=PASS`, no limitations, and a final source registration
  boundary with `final_registration_ready=true`, `wiki_registration_ready=true`,
  `paper_registered=true`, `graph_registered=true`, `index_rebuilt=true`, and
  `context_rebuilt=true`.

Non-acceptance note: a broad run of `tests/plugins/autosci/test_bridge_smoke.py`
from the repository root collected unrelated legacy failures where subprocess
fixtures were looked up relative to a temporary cwd, plus one pre-existing
experiment-status expectation mismatch. The targeted ingest registration
tests above passed and were used as the acceptance evidence for this J04
repair.

Accepted J07 terminal lifecycle repair for `P22-REPAIR-092` and the J07 portion
of `P22-REPAIR-036`/`P22-REPAIR-038`: `harness/plugins/autosci/bin/autosci_bridge.py`
now treats JSON files supplied through `exp-status --collect --after-artifact`
as fallback local experiment result payloads when no explicit
`experiment_result_evidence` is supplied. This preserves explicit evidence as
authoritative, but lets the local monitor path report a terminal state for the
same result file that the approved local experiment command just wrote.

Validation:

- `.venv\Scripts\python.exe -m py_compile harness/plugins/autosci/bin/autosci_bridge.py`
  -> passed.
- `.venv\Scripts\python.exe -m pytest tests/journeys/phase22/code/test_j07_experiment_lifecycle.py::test_p22_j07_experiment_lifecycle --basetemp .codex-tmp/pytest/root-j07-terminal-after-basetemp -o cache_dir=.codex-tmp/pytest/root-j07-terminal-after-cache`
  -> 1 passed.
- Accepted journey evidence:
  `outputs/phase22-real-journeys/p22j07-20260810T202057Z-26328/journey-result.json`
  now records `status=PASS`, no limitations, and
  `exp_status_reached_terminal_state=true` with status report state
  `completed`.

Scope note: this fixes the local J07 terminal-state path. Claims tied to the
paired J02 live/tmux workflow remain environment-blocked on this Windows host
until rerun with live authorization and tmux available.

Accepted J21 parity/handoff recorder refresh for `P22-REPAIR-071`: the J21
journey selector now uses a strict HITL gate for the negative "missing
approval" run and reads the current structured runtime evidence emitted by
`exp-run` (`outputs.final_runtime_audit_boundary` and
`outputs.result.command_run`/`exit_code`) instead of older limitation strings.
The unsupported overbroad claim assertion also treats the current
`insufficient` verdict as a non-supported result.

Validation:

- `.venv\Scripts\python.exe -m pytest tests/journeys/phase22/code/test_j21_experiment_build_handoff.py::test_p22_j21_real_experiment_build_and_handoff --basetemp .codex-tmp/pytest/root-j21-p1-recorder-fix-basetemp -o cache_dir=.codex-tmp/pytest/root-j21-p1-recorder-fix-cache`
  -> 1 passed.
- Accepted journey evidence:
  `outputs/phase22-real-journeys/p22-j21-20260810T202810Z-30352/journey-result.json`
  records no failed assertions. It remains `PASS_WITH_KNOWN_LIMITATIONS`
  because the local parity-demo path still does not provide attributable human
  approval and the handoff artifact is not a benchmark-native consolidated
  bundle.
