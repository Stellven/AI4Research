# QA Process Status

This file is the navigation layer for the repo-derived QA workflow.

## Original Sequence

1. Generate repo-derived function inventory.
2. Normalize into an L1/L2/L3 feature hierarchy.
3. Map every feature to existing tests.
4. Finalize the master pass/fail table.
5. Execute tests and produce a test report.

## Current Status

| Step | Status | Artifact |
|---|---|---|
| 1. Generate repo-derived function inventory | Complete | `docs/testing/qa_feature_inventory.csv` |
| 2. Normalize into L1/L2 feature hierarchy plus specific I/O | Complete | `docs/testing/qa_feature_inventory.csv`, columns `l1`, `l2`, `specific_inputs_outputs` |
| 3. Map every feature to existing tests | Complete as static mapping | `docs/testing/qa_feature_inventory.csv`, column `existing_tests` |
| 4. Finalize master acceptance table | Complete as acceptance grouping | `docs/testing/qa_master_pass_fail_table.md` |
| 5. Execute local automated tests | Historical run complete; current rerun required | Raw evidence is retained in commit `718aae9a`; see `docs/testing/test-runs/README.md` for the current evidence policy. |

## Simplified Feature List

- CSV: `docs/testing/qa_feature_list.csv`
- Rows: 1,724 raw feature rows
- Columns:
  - `Level 1 Feature`
  - `Level 2 Feature`
  - `Specific Inputs / Outputs Supported`

This is the reader-facing feature list. It intentionally omits L3 while preserving the original row-level function/feature granularity.

## Main Artifacts

### Raw Function Inventory

- CSV: `docs/testing/qa_feature_inventory.csv`
- Markdown: `docs/testing/qa_feature_inventory.md`
- Rows: 1,724 raw feature rows
- Columns: `feature_id`, `l1`, `l2`, `specific_inputs_outputs`, `source_type`, `source_paths`, `entrypoints`, `existing_tests`, `coverage_status`, `pass_criteria`, `why_testable`, `notes`

This is the source-of-truth inventory used for traceability and test mapping.

### Acceptance Groups

- CSV: `docs/testing/qa_master_pass_fail_table.csv`
- Markdown: `docs/testing/qa_master_pass_fail_table.md`
- Rows: 61 acceptance groups

This is the normalized L1/L2 acceptance table. It groups the 1,724 raw feature rows into human-testable areas and keeps pass criteria/test-planning metadata.

### Inventory Summary

- Markdown: `docs/testing/qa_inventory_summary.md`
- Manifest: `docs/testing/qa_inventory_manifest.json`

Current inventory counts:

- Tracked files scanned: 4,383
- Test files detected: 931
- Feature rows generated: 1,724
- Coverage mapping:
  - covered: 1,550
  - missing-or-indirect: 133
  - partial-or-unmapped: 20
  - static-validation-required: 21

### Test Execution Report

The historical report, command summary, and pytest/shell/TypeScript matrices
remain recoverable from commit `718aae9a`. They are not current results and are
not stored in the source tree. New raw evidence belongs outside the checkout;
see `docs/testing/test-runs/README.md`.

## Important Clarification

The 61-row master table is an acceptance-group table, not the raw function inventory.

The raw function inventory is the 1,724-row `qa_feature_inventory.csv`; it no longer exposes L3 in the CSV and instead uses `specific_inputs_outputs`.

The current gap is that the executed test results have not yet been merged back into a final reader-facing table with one row per acceptance group and columns like:

- `Final Status`
- `Evidence Logs`
- `Failure Summary`
- `Blocked Reason`
- `Release Impact`

That merge should be the next reporting step if the goal is a single final pass/fail table.
