# Overwritten Stellven Contribution Reconciliation

## Result

- Source commits: 425
- Candidate paths: 5438
- Unresolved (legacy): 0
- Needs human decision: 0
- Tracked target missing: 1685
- Fixed overwrite proof: `tree(a4ba17ac9) == tree(4b5af7519)` is recorded in the JSON ledger.

## Classification counts

- `INTENTIONALLY_EXCLUDED_GENERATED_STATE`: 1816
- `INTENTIONALLY_EXCLUDED_OBSOLETE_DUPLICATE`: 2126
- `INTENTIONALLY_EXCLUDED_SECRET_OR_LOCAL_STATE`: 1
- `PRESERVED_EXACT`: 1357
- `SUPERSEDED_BY_NEWER_IMPLEMENTATION`: 138

## Recovery decisions

- `README.md` and every source-tip blob classified as preserved are restored verbatim at their original paths from `4d60f1e...`.
- `PRESERVED_EXACT` records direct source-tip equivalence at the original path. For a source-tip deletion, it records exact absence rather than recreating an obsolete intermediate file.
- Source-archive, runtime-artifact, test-run, lock, and cache material is retained only when its source-tip blob was explicitly part of the prior moved/semantic recovery set; all other excluded material remains excluded with its recorded reason.

## Validation

- Reconciliation validator: 4 passed.
- Full pytest collection: 7,033 tests collected.
- Reconciliation, Windows-path, and staging-safety tests: 79 passed.
- `scripts/check-release-coherence.sh`: PASS after making its Python-output comparison CRLF-neutral on Windows.
- Secret scan: 4,503 candidates scanned with no findings; `git diff --check` passed.
- The clone-based tracked-input release regression exceeded the 180-second command limit after the direct gate passed; this is retained as runner-duration evidence, not a product regression.

Every candidate path and source commit is listed in the machine-readable companion: `overwritten-contribution-reconciliation.json`.
