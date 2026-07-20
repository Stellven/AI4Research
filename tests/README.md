# Test Location Policy

All new executable tests created for the Phase 22 atomic-feature test report
must be stored under this repository's root `tests/` directory.

Use `tests/atomic/` as the default parent directory and organize tests below it
by product surface or Level 1 feature. Do not place new Phase 22 test
implementations under `core/`, `harness/`, `desktop/`, `skills/`, `docs/`, or
`outputs/`.

The atomic-test registry in the QA workbook is a planning and traceability
inventory. A registry row is not considered executable until it identifies a
real test file under `tests/`, an invocation, prerequisites, and an observable
expected result.

Existing legacy tests outside `tests/` are not moved by this policy. Relocating
them requires a separate migration that updates their runners, imports,
fixtures, and package-specific assumptions.
