# R3 Experiment Lifecycle Repair

Date: 2026-08-07
Branch: `codex/legacy-fix-r3-experiment`
Baseline: `6a96d40153b919d97a2018c8267d7796d5e3e1d5`

## Scope

This repair closes the deterministic local experiment lifecycle path for R3:
design, approval-gated execution, monitoring/status projection, evaluation,
resume, external evidence import validation, lease/concurrency, and Windows
claim-lock recovery.

## Changes

- `exp-design` now builds a bounded POC asset package under the product artifact
  tree: runner, sample input, expected result path, allowlist, manifest, and
  minimum usability check.
- `exp-run` now executes approved experiment commands through
  `ResearchLeaseAdapter`, records heartbeat, duplicate-probe rejection, release,
  stdout/stderr, runtime evidence, result package, deploy/run reports, and a
  durable lease report.
- Skill/action summaries now surface product result paths so journey tests can
  resolve production artifacts without fixture-only handoff.
- Research evidence operators and lease/state validation paths now use
  Windows-safe filesystem helpers for long artifact paths.
- Phase 5 lifecycle recovery tests now verify long-path artifacts with
  Windows-safe test helpers instead of failing on ordinary Win32 path limits.
- Git provenance now fails closed for non-checkout roots, preventing artifact
  scratch directories from inheriting parent checkout identity.

## Verification

All commands used isolated `--basetemp` and pytest cache directories under the
worktree. A temporary test venv was created under `.codex-tmp/r3-test-venv`
because no project pytest environment was present.

- `py_compile` on touched production and journey/test files: passed.
- `pytest tests/journeys/phase22/code/test_j21_experiment_build_handoff.py::test_p22_j21_real_experiment_build_and_handoff`: passed.
- `pytest harness/tests/research_orchestration/generalization/test_phase5_lifecycle_recovery.py`: passed, 4 tests.
- `pytest harness/tests/research_orchestration/test_research_runtime_lease.py`: passed, 25 tests.
- Combined regression: J07, J21, state store, result validation, orchestrator,
  and production runtime: passed, 121 tests.
- Final core regression: Phase 5 lifecycle recovery plus runtime lease: passed,
  29 tests.

## Notes

The accepted evidence is deterministic local execution. No live provider run was
needed for the repair proof; provider behavior remains bounded by existing
approval/environment gates and should be recorded separately if a provider
specific result is required.
