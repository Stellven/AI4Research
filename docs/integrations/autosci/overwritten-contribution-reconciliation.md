# Overwritten Stellven Contribution Reconciliation

## Result

- Source commits: 425
- Candidate paths: 5438
- Unresolved: 0
- Fixed overwrite proof: `tree(a4ba17ac9) == tree(4b5af7519)` is recorded in the JSON ledger.

## Classification counts

- `INTENTIONALLY_EXCLUDED_GENERATED_STATE`: 1816
- `INTENTIONALLY_EXCLUDED_OBSOLETE_DUPLICATE`: 2126
- `INTENTIONALLY_EXCLUDED_SECRET_OR_LOCAL_STATE`: 1
- `PRESERVED_EXACT`: 818
- `PRESERVED_MOVED`: 247
- `PRESERVED_SEMANTICALLY`: 292
- `RESTORED`: 1
- `SUPERSEDED_BY_NEWER_IMPLEMENTATION`: 137

## Recovery decisions

- `README.md` is restored semantically: AI4Research's governed research/delivery framing is present, while installation commands, release line, and limitations remain those of the final integration.
- Exact blobs and moved tests are retained in their current locations; the ledger records their current path and blob evidence.
- The ignored `Solar_Harness_All_Sources_*` package is not recommitted. Its manifest-backed material is a local archive containing historical duplicates, raw exports, and runtime snapshots; restoring it would violate the repository's explicit local-archive rule.
- Runtime artifacts, test-run reports, locks, caches, and source-tip deletions remain excluded rather than being resurrected.

## Validation

- Reconciliation validator: 4 passed.
- Full pytest collection: 7,033 tests collected.
- Reconciliation, Windows-path, and staging-safety tests: 79 passed.
- `scripts/check-release-coherence.sh`: PASS after making its Python-output comparison CRLF-neutral on Windows.
- Secret scan: 4,503 candidates scanned with no findings; `git diff --check` passed.
- The clone-based tracked-input release regression exceeded the 180-second command limit after the direct gate passed; this is retained as runner-duration evidence, not a product regression.

Every candidate path and source commit is listed in the machine-readable companion: `overwritten-contribution-reconciliation.json`.
