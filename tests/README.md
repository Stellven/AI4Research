# Test Location Policy

All new executable tests created for the Phase 22 atomic-feature test report
must be stored under this repository's root `tests/` directory.

Categorize new tests by the official hierarchy or platform surface:

- `tests/workflow/<level-1-slug>/`
- `tests/foundation/<level-1-slug>/`
- `tests/vertical/<level-1-slug>/`
- `tests/platform/<surface>/` for installer, CLI, desktop, CI, release, and
  other tests outside the official feature hierarchy
- `tests/shared/fixtures/` and `tests/shared/helpers/` for reusable support code

Do not use a single `tests/atomic/` bucket, and do not place new Phase 22 test
implementations under `core/`, `harness/`, `desktop/`, `skills/`, `docs/`, or
`outputs/`.

The atomic-test registry in the QA workbook is a planning and traceability
inventory. A registry row is not considered executable until it identifies a
real test file under `tests/`, an invocation, prerequisites, and an observable
expected result.

An existing legacy test may be moved into the appropriate category only after
its atomic-feature bindings are identified and its imports, fixtures, runner
commands, and baseline result are verified from the new path. Until that work
is complete, keep the legacy file in place and reference or wrap it from the
categorized root test suite.
