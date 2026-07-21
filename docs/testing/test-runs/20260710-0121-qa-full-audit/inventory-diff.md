# Inventory Diff

## Control taxonomy baseline

- Atomic feature rows: 2117
- By part: {'workflow': 652, 'foundations': 844, 'misc.': 621}
- Duplicate feature paths: 0
- Duplicate atomic labels (labels only; paths may differ legitimately): 236

## Repository surfaces discovered

- Tracked files at locked SHA: 5259
- Scannable source/config/spec files: 4929
- Function/module/route/script/package/config inventory rows: 31463
- Existing test files: 1752
- Package scripts: 25
- Inventory classifications: {'mapped': 22556, 'test-only': 8729, 'missing-feature-row': 15, 'support-only': 162, 'generated': 1}

## Taxonomy reconciliation

- Feature rows without a static implementation/entrypoint candidate: 1150
- Candidate stale rows: 0
- Public production entrypoints with no feature mapping (`missing-feature-row`): 15
- Validated existing-test coverage classifications: {'missing': 973, 'indirect': 608, 'direct': 232, 'partial': 215, 'gated': 73, 'manual-only': 16}

Static candidate mappings were validated against committed executable testcase/file names. Token/path similarity alone was not accepted as evidence.

## Strict eligible execution phase

- Eligible atomic features executed: 448
- Unique test targets attempted: 107 of 107
- Target results: {'PASS': 93, 'FAIL': 14}
- Testcase results: {'testcase_pass': 523, 'testcase_fail': 15, 'testcase_error': 3, 'testcase_skip': 1}
- Feature execution outcomes: {'PASS': 404, 'FAIL': 44}
- Conservative feature interpretations: {'INCONCLUSIVE_EXPECTED': 402, 'FAIL': 4, 'PASS': 42}
- Heuristic mappings reclassified to missing: 355

### Excluded from this phase

- `approval_or_authorization_gate`: 513
- `coverage_gated`: 73
- `coverage_manual-only`: 16
- `coverage_missing`: 618
- `external_environment_or_credentials`: 94
- `no_semantically_relevant_executable_test`: 354
- `no_tracked_executable_test`: 1

The superseded v1/v2 eligibility runs are retained under `evidence/eligible-full-phase*` for provenance, but only v3 strict evidence is authoritative for feature attribution.

## Candidate missing feature rows

See `function-inventory.csv` rows classified `missing-feature-row` and `missing-test-plan.csv` for all validated missing or insufficient test mappings.

## Post-NOT_RUN inventory reconciliation

- Originally selected Codex-relevant NOT_RUN rows: 861.
- Final selected-subset outcomes: PASS 639, FAIL 72, SKIPPED_ENV 105, SKIPPED_NA 45.
- Remaining selected-subset NOT_RUN: 0.
- Remaining selected-subset INCONCLUSIVE_EXPECTED: 0.
- Explicitly excluded and archived: 576 rows — Claude 125, SciDAG 429, SciDAG+SciMem 10, SciMem 12.
- `skills-md` was confirmed absent; two rows were corrected from an erroneous `skills/solar/SKILL.md` association to `SKIPPED_NA`.
- Office and browser-automation are documentation/setup-only surfaces, not executable integrations; they are recorded as product/testability failures rather than silently skipped.
- Obsidian, Calendar, RAGFlow, Codex operator, browser job runtime, social-browser CLI, and Gemini Deep Research entrypoints were corrected to concrete locked-checkout files/functions and exercised with isolated fixtures.

Evidence: `evidence/codex-not-run-phase/remaining-blocker-summary.json`, `excluded-feature-ledger.csv`, `remediation-feature-decisions.csv`, and `gated-approved/remaining-app-browser-provider-contracts.junit.xml`.
