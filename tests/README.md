# OpenSolar test layout

All executable repository tests live below this directory.

- `foundation/`, `workflow/`, and `vertical/`: feature-oriented tests.
- `journeys/phase22/`: the 24 real-task Phase 22 journey tests and fixtures.
- `harness/`: Solar Harness unit, integration, runtime, shell, and scenario tests.
- `plugins/autosci/`: AutoSci plugin tests and their fixtures.
- `integrations/`: integration-specific tests that previously lived beside implementation code.
- `desktop/`, `distribution/`, `skills/`, `mempalace/`, and `scripts/`: component-specific tests.
- `quarantine/`: retained historical tests that are not valid evidence because their target API or module no longer exists, or because they collide with another test namespace.

Test fixtures are deliberately excluded from repository-wide discovery. A
fixture can contain a miniature `tests/` directory, but those files are inputs
to the owning journey and are not executed as top-level OpenSolar tests.

Python test modules use `test_*.py` or `*_test.py`. Hyphenated Python test
names are not permitted because pytest does not discover them consistently.

Runner-specific tests remain in the same tree: TypeScript tests require Bun,
the Windows `*.Tests.ps1` suites require Pester 5.x, and CommonJS desktop tests
use `.test.cjs` so they are not misinterpreted by the repository's ESM package
mode. Missing runner dependencies are setup failures, not product failures.

## Evidence and isolation rules

- Phase 22 journey tests are the primary user-task evidence; atomic tests are
  retained for regression and diagnosis.
- A fixture, static marker, or test file that was not executed is not PASS
  evidence.
- Pytest gives each case an isolated user home. Standalone shell, Node, Pester,
  install, and lifecycle tests must create their own temporary user and output
  directories.
- Tests that require an installed personal runtime, fixed developer path, or
  live service without a controlled fixture belong in `quarantine/` until they
  are made self-contained.
- A real product assertion failure remains a failure; only broken, unsafe, or
  misleading test machinery is repaired or quarantined.
