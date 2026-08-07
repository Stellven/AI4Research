# Runtime and platform repair log

## Scope

- Baseline: `4b5af751956f8ef1d2eb6bbce8baf9088e694d00`
- Branch: `codex/known-issues-runtime-platform`
- Isolated evidence: `.codex-tmp/known-issue-repairs/runtime-platform/result.json`

## Repairs

- J01: native Windows `/status` no longer calls `os.getuid()` through the macOS-only launchctl path. Status startup waits for both a listener and `/runtime-info`, writes the actual Python PID, and Windows stop validates ownership then terminates the complete process tree.
- J01: cold dashboard projection is warmed asynchronously; lifecycle callers receive an explicit `warming` projection instead of a false readiness timeout.
- S01: readiness reports now expose an explicit restricted-fallback permission matrix. Without bubblewrap, fallback declares sandbox-root-only writes and denies home, network, and secret access.
- S03: actor leases reclaim expired active states; pane release removes lock files only after unlocking so native Windows does not retain stale locks.

## Verification

`tests/repairs/runtime_platform/test_runtime_platform_repairs.py` uses port `18250` only, cleans child processes and temporary state, and exercises fallback permissions, lease contention/recovery, pane lock cleanup, and repeated status-server lifecycle.

- Windows: `test_p22_j01_install_status.py` passed after a clean install; ready endpoint, status endpoint, stop, port release, PID removal, and repeated local lifecycle checks passed.
- WSL Ubuntu: direct lifecycle on port `18251` passed: `/runtime-info`, `/status`, SIGTERM, port release, and PID/port record removal.
- Experiment lifecycle: the existing Phase 5 interruption/resume and external-evidence regression file currently has a fixture portability defect on this baseline: it resolves `harness/tests/.../sample_paper.md`, while the fixture is under `tests/harness/...`. It was recorded as a test-fixture defect rather than a product result; no shared journey report was changed.
