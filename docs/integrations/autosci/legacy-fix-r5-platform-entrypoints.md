# Legacy Fix R5 Platform Entrypoints

Date: 2026-08-07

Branch: `codex/legacy-fix-r5-platform`

Baseline: `6a96d40153b919d97a2018c8267d7796d5e3e1d5`

Committed portion: `96a9097bd23c247011ed8d042fc153a77923143d`

## Scope and initial inspection

The initial worktree had 17 modified tracked files and an untracked
`outputs/phase22-real-journeys/` evidence directory. The tracked diff contained
87 insertions and 39 deletions. Every tracked change was reviewed and belongs
to the assigned Windows/WSL installer portability, sandboxed install/doctor,
status-server lifecycle, or J01 journey scope. The untracked output directory
is excluded from the supplemental commit.

The tracked changes make the installer consistently use the detected
`SOLAR_PYTHON`, reject WindowsApps Python aliases, support native Windows OS
detection and venv layout, avoid unavailable automatic package managers on
native Windows, and make the status-server lifecycle use the selected Python
interpreter. J01/J15 journey helpers now select Git Bash and the repository
Python without relying on the real user home.

The requested source files
`docs/integrations/autosci/legacy-issue-closure-ledger.md` and
`.codex-tmp/legacy-issue-audit-20260806/github-issue-map.json` were absent from
the main worktree, all R1-R8 worktrees, and Git history. No Legacy or L2 closure
claim is inferred from those missing inputs.

## Status-server correctness repair

The production `/status` route now fails closed when status-payload generation
raises an exception:

- `ok` is `false`;
- `status` is `degraded`;
- `error` is the stable code `status_payload_unavailable`;
- exception type, message, local paths, provider details, and secret material
  are not returned;
- the HTTP server remains available after the error.

`harness/tests/test_status_server_status_route.py` starts the production
`StatusHandler`, injects a payload failure containing path/token markers,
requests `/status`, verifies the exact sanitized response, and confirms that a
subsequent `/healthz` request succeeds.

## Verification

All pytest commands used the repository `.venv`, unique basetemp/cache paths,
and no log file inside basetemp. Installer commands used a sandboxed
`HOME`/`USERPROFILE` and a test-only Bash environment shim for the repository
Python.

1. J01, J15, J18 batch:
   `python -m pytest tests/journeys/phase22/code/test_j01_install_status.py tests/journeys/phase22/code/test_j15_cross_platform_install_matrix.py tests/journeys/phase22/code/test_j18_tmux_cli_status_config.py -q --basetemp .../r5-journeys-bt -o cache_dir=.../r5-journeys-cache`
   - Exit `0`: `2 passed, 1 skipped` in 49.04s.
   - J18 skip reason: `PHASE22_ENABLE_SERIAL_TMUX_JOURNEYS=1` was not enabled.
2. Installer/doctor scripts:
   `bash harness/tests/installer/test-s1-installer.sh` and
   `bash harness/tests/installer/test-tvs-doctor.sh`
   - Exit `0`: installer `38/38` checks passed; TVS doctor skipped because no
     sandbox TVS installation was present.
3. Status route tests:
   `python -m pytest harness/tests/test_status_server_status_route.py harness/tests/test_status_server_contract_route.py harness/tests/test_status_server_deliverables.py harness/tests/test_status_server_session_scoping.py -q --basetemp .../r5-status-targeted-bt -o cache_dir=.../r5-status-targeted-cache`
   - Exit `0`: `14 passed` in 4.94s.
4. Existing self-running P0 dashboard script:
   `python harness/tests/test-status-server-p0-dashboard.py`
   - Exit `1`: its legacy assertion expects `settings.write_supported is
     False`, while current production settings behavior reports write support.
     This is an existing test/contract mismatch outside the R5 platform diff;
     it is not relabeled as a product or environment pass.
5. An over-broad first combined pytest invocation produced `9 passed, 1
   skipped, 16 failed, 2 teardown errors`. The failures were runner/platform
   defects from resolving `bash` to WSL for Windows paths, using unavailable
   `SIGKILL` on Windows, and missing external test commands. The production R5
   journeys and status assertions were then rerun through Git Bash in the
   scoped commands above.

## Remaining limitations

- J18 serial TMUX execution remains not tested in this native Windows batch.
- The packaged Windows desktop application and macOS lifecycle were not run;
  J15 covers only its current local runnable surface.
- TVS doctor integration was not executed because the sandbox contained no TVS
  checkout.
- The P0 dashboard write-support expectation remains a test/contract mismatch.
- No report, workbook, ledger, or GitHub Issue state was changed.
