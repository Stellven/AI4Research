# Overwritten Stellven Contribution Reconciliation

## Result

- Source commits: 425
- Candidate paths: 5438
- Unresolved: 0
- Fixed overwrite proof: `tree(a4ba17ac9) == tree(4b5af7519)` is recorded in the JSON ledger.

## Classification counts

- `INTENTIONALLY_EXCLUDED_GENERATED_STATE`: 1817
- `INTENTIONALLY_EXCLUDED_OBSOLETE_DUPLICATE`: 2126
- `INTENTIONALLY_EXCLUDED_SECRET_OR_LOCAL_STATE`: 1
- `PRESERVED_EXACT`: 805
- `PRESERVED_MOVED`: 246
- `PRESERVED_SEMANTICALLY`: 294
- `SUPERSEDED_BY_NEWER_IMPLEMENTATION`: 149

## Recovery decisions

- `README.md` is retained verbatim from `4d60f1e...` at its original path.
- `PRESERVED_EXACT` means the source-tip blob exists at the same current path; `PRESERVED_MOVED` records byte-identical content at its canonical moved path.
- Relocated or refactored tests remain under the canonical `tests/` tree and are recorded as `PRESERVED_SEMANTICALLY`; legacy duplicates are not recreated.
- Source archives, runtime artifacts, test-run outputs, locks, and caches remain excluded unless independently tracked by the current product tree.

## Validation

- Reconciliation, migrated canonical contribution, and compiled-planner tests: 9 passed.
- Desktop self-test verdict cases: 9/9 passed.
- Full pytest collection: 7,190 tests collected.
- `git diff --check` passed for the repair's text changes.
- The clone-based tracked-input release regression exceeded the 180-second command limit after the direct gate passed; this is retained as runner-duration evidence, not a product regression.

Every candidate path and source commit is listed in the machine-readable companion: `overwritten-contribution-reconciliation.json`.
