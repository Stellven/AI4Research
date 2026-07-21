# QA workbook coloring changelog

- Source workbook path: `/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/control-material/ai4research_recursive_feature_split_qa_execution.xlsx`
- Test result directory used: `/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit`
- Output workbook path: `/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/ai4research_recursive_feature_split_qa_execution_colored.xlsx`
- Matched feature IDs: 2117 unique feature IDs (8468 matched sheet rows)
- Unmatched feature IDs: 0
- Ambiguous mappings: none
- Status values outside approved taxonomy: none

## Rows colored per sheet

| Sheet | Result-colored rows | Pre-test gray rows | Whole rows colored | Matched | Unmatched |
|---|---:|---:|---:|---:|---:|
| Entrypoint Map | 2117 | 0 | 2117 | 2117 | 0 |
| Existing Test Map | 2117 | 0 | 2117 | 2117 | 0 |
| Missing Test Plan | 2117 | 0 | 2117 | 2117 | 0 |
| Pass Fail Criteria | 2117 | 0 | 2117 | 2117 | 0 |

## Final status counts per target sheet

Each target sheet contains the same 2,117 feature IDs and final result mapping:

- BLOCKED_EXPECTED: 36
- FAIL: 112
- INCONCLUSIVE_EXPECTED: 381
- PASS: 843
- SKIPPED_ENV: 126
- SKIPPED_NA: 619

The `test_result_status` color takes precedence for the whole row. A non-empty `pre_test_status` remains gray in its own status cell; if no terminal result color exists, gray would be used for the row. Blank/NOT_RUN result cells receive no approved status color.
