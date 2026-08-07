# Legacy Fix Integration and Correctness Repair

Date: 2026-08-07

Baseline: `6a96d40153b919d97a2018c8267d7796d5e3e1d5`

Branch: `codex/legacy-fix-integration-repair`

Worktree: `C:\Users\j50058254\Desktop\Github repo\.legacy-fix-worktrees\legacy-fix-integration`

Final-correction rework baseline: `e85f3bb069bb2861cf7442e2aa2d3747c010c34e`

No Phase 22 workbook, brief report, legacy issue ledger, or GitHub Issue was
changed.

## Inputs and integration order

The inputs were cherry-picked in the requested order. No whole-file
`ours`/`theirs` resolution was used.

| Order | Input | Input commit | Integration commit |
|---:|---|---|---|
| 1 | R1 | `8b8acb7397496e62b48e5b781e933339445774b0` | `c2a897eab` |
| 2 | R2 | `3bc9f20e2b675f9285b7720fd24cdaf3aafb5997` | `359255a33` |
| 3 | R3 | `c88680e49257cfd02fd520c4324cdd72a4f59fdd` | `32b4fc8d1` |
| 4 | R4 | `182df830eb50e88e4e84f48fdda3822ce1b1afb1` | `d1a99171f` |
| 5 | R5 committed | `96a9097bd23c247011ed8d042fc153a77923143d` | `d16300009` |
| 6 | R5 supplemental | `dead34b7e1f88bdc42fed68f3d80568cccfdd1e7` | `3acd97eff` |
| 7 | R6 | `9a5e1390f2291bcaf5c1cbcf5a9f1bf85aed92e8` | `2f129af5c` |
| 8 | R7 | `34f5cb017c68690bd6930eaaa1f3d895005ad091` | `5b55a8db8` |
| 9 | R8 | `2a7aeb9af6bd83db7c149be95a303100fe9dd307` | `44c5c4c34` |

Before the R5 supplemental commit, its 17 modified tracked files were reviewed
with `git status --short`, `git diff --stat`, and the full `git diff`. All 17
belonged to Windows/WSL installer portability, sandboxed install/doctor,
J01/status lifecycle, or status fail-closed handling. The untracked `outputs/`
evidence was retained and not committed. R5 has no uncommitted tracked code.

## Conflict resolutions

Two textual conflicts were resolved paragraph by paragraph:

- `harness/lib/research_orchestration/runtime.py`: retained R1 prompt,
  requirements, readiness, and persisted contract semantics together with R3
  experiment lifecycle, resume/import, exact-checkout provenance, and
  Windows-safe evidence behavior.
- `tests/journeys/phase22/code/journey_runner.py`: retained R2 Windows
  sidecar/path handling, R4 cache/copytree portability, and the R5 installer
  journey interpreter/sandbox behavior.

`autosci_bridge.py` and `bin/solar` did not have textual conflicts. Their
R2/R3/R4 and R5/R6 behavior composed cleanly and was verified through combined
production-path tests.

## Correctness repairs

### R4 benchmark semantics

- Benchmark process completion and target quality are separate:
  `benchmark_execution_verdict=PASS` means the scoring process completed;
  insufficient target quality is `target_quality_verdict=FAIL`; a dry run with
  no target execution is `target_quality_verdict=NOT_TESTED`.
- Legacy dry-run fields, new schema fields, JSON, Markdown, and CLI output use
  the same meaning.
- Both production package copies, `harness/lib/benchmark` and the installable
  `harness/tools/benchmark` mirror, were repaired. A regression test now fails
  if those copies drift.

### R5 status and Windows entrypoints

- `/status` payload exceptions return `ok=false`, `status=degraded`, and stable
  code `status_payload_unavailable`. Exception strings, paths, tokens, and
  provider details are not exposed; the server remains alive.
- Both installed `harness-config.sh` copies honor `SOLAR_PYTHON`. This prevents
  Git Bash from invoking the WindowsApps `python3` alias and contaminating
  `SOLAR_PANE_RUNTIME` with installer output.
- The production J01 install, doctor, CLI status, and HTTP status-server path
  passes in a sandbox home after this repair.

### R6 token and identity safety

- Register and login responses return each newly issued token once to the
  caller. The token is not placed in subprocess argv.
- Later session, profile, privacy, and logout responses do not echo the token.
  Raw tokens are not retained in the identity store, export, audit trail, or
  ordinary logs. Authentication failures do not disclose whether a username
  exists.
- Session/profile/privacy/logout read tokens from stdin by default;
  `--token-stdin` is explicit. Deprecated `--token` compatibility remains a
  known limitation and is warned against in the CLI documentation.

### R7 production binding

- `autosci-advanced-ai4rnd-worker` is bound in the physical operator registry
  and is dispatchable by TaskGraph.
- Bayesian optimization and the CPU-safe SFT adapter are executed through the
  production `bin/solar advanced` CLI, not by directly importing
  `execute_operator` as the only evidence.
- TaskGraph state, evidence ledger, model lineage, artifacts, and output hashes
  are traceable. All non-reference algorithms remain explicit `unsupported`;
  results are not copied across algorithm names.
- Final correction added a real dispatcher integration path:
  `TaskGraph -> graph scheduler -> exact physical-operator selection ->
  operator_runtime inbox -> operatord command backend ->
  advanced_ai4rnd_operator.py -> TaskGraph state -> evidence ledger`. The
  Bayesian reference path records the same output hash in node state and the
  ledger; LoRA remains explicit `unsupported` and produces no PASS.

### R8 enforced governance

- `.github/workflows/solar-ci.yml` executes safe-staging, secret-scan, Windows
  filename, hygiene, and sandbox fixture tests. The job now sets up Python 3.12
  and installs pytest on a fresh runner.
- Secret scanning covers tracked files, exact staged index blobs, and untracked
  commit candidates. Output is restricted to rule, path, and line; matched
  values are never printed.
- `.env.example`, `.env.template`, and `.env.sample` are scanned normally;
  none is a whole-file exception. Reviewed placeholders can only use an exact
  rule/path/line SHA-256 exception, which fails closed after any line change.
- Safe-staging keeps its local staged-file default and also accepts explicit
  changed-path, all-tracked, and stdin scopes. CI checks the pull-request merge
  base or push `before` commit, falling back to every tracked path for a missing
  or all-zero push base rather than performing an empty clean-checkout scan.
- The Windows registry-root parent index was fixed.
- Sandbox tests launch real child processes. Allowed writes succeed and
  outside writes fail where an OS sandbox exists. Native Windows has no
  configured OS-level enforcement here, so S01 remains explicitly unresolved
  and skipped; transport metadata is not treated as a sandbox.

### R1 parity, R2 live paths, R3 lifecycle, and R4 claim scope

- Captured upstream parity fixtures remain as offline regression. The
  configurable `harness/tools/autosci_upstream_parity.py` sends the same prompt
  to Solar and a configured real upstream command, comparing intent, workflow
  stages, input type, language, deliverable type, and required evidence.
- No executable same-prompt upstream AutoSci entrypoint was found in this
  repository or the read-only sibling AutoSci checkout. A09/T06 therefore
  remain `PARTIAL`.
- R3 deterministic lifecycle, J07/J21, resume, external evidence import, crash
  recovery, and lease/concurrency all pass after combining the R1 contract.
- Claim scope compares population, environment, time range, input domain,
  metric, and confidence/uncertainty. Regexes are guardrails only. Tests cover
  bounded support, universal overclaim, insufficient evidence, contradiction,
  and Chinese terms `所有`, `任何环境`, `始终`, and `百分之百`.

### Repository hygiene cleanup

- The baseline `skills/obsidian-daily/SKILL.md` contained committed Git merge
  markers around its frontmatter metadata. The integration cleanup removed
  only those markers and retained `author: github.com/bastos` and version
  `2.0`.
- This is repository hygiene cleanup, not an Obsidian behavior or feature
  change.

### Native Windows final correction

The rework baseline reproduced `tests/harness/test_operatord_daemon.py` as
**21 passed, 7 failed**. The seven failures were classified and repaired
without skips or weaker assertions:

| Failing test | Classification | Final repair |
|---|---|---|
| `test_end_to_end` | Product portability | The local backend no longer requires `sh`; it runs the deterministic stub with the selected Python interpreter. |
| `test_output_log_written` | Product portability | The same native local backend now starts successfully and writes `output.log`. |
| `test_recovers_expired_lease_and_processes_task` | Product portability | Expired-lease recovery uses the same native command path and reaches `completed`. |
| `test_command_backend_uses_materialized_dispatch_file` | Fixture portability plus command transport | The fixture no longer hard-codes `python3`; command indirection accepts JSON argv and executes without POSIX shell quoting. |
| `test_pm_dispatch_result_path_and_complete_hook` | Fixture portability | The command fixture uses the repository interpreter as argv, and its completion output is ASCII-safe on a Windows cp1252 console. |
| `test_pm_result_file_exists_when_restricted_operator_starts` | Fixture portability | The checker uses exact argv rather than POSIX `shlex` text, preserving the pre-created result-file contract. |
| `test_signal_during_pm_task_records_terminal_failure` | Product and fixture portability | Native Windows uses a cooperative shutdown request instead of uncatchable `SIGTERM`; POSIX retains SIGTERM. Windows PID probing uses `OpenProcess`/`GetExitCodeProcess`, never `os.kill(pid, 0)`, and active workers terminate through the exact `Popen` handle. |

The Windows `file_lock_compat` implementation now accepts either an open file
object or an integer file descriptor. It prepares and positions the dedicated
one-byte lock through fd-level operations, preserves `LOCK_EX`, `LOCK_NB`, and
`LOCK_UN`, converts only recognized non-blocking contention to
`BlockingIOError`, and no longer swallows unlock failures. Five tests cover
file objects, integer descriptors, two-process contention, post-unlock
reacquisition, and the existing `operator_flow_control` fileno call. Failure
flow-control results no longer contain `'int' object has no attribute 'seek'`.

The all-tracked safety gate initially failed on the committed Excel lock file
`docs/testing/xlsx/~$qa_inventory_test_mapping_and_pass_fail_merged.xlsx`.
Only that 165-byte temporary lock file was removed from Git tracking; the
formal workbook was not changed. The existing `.gitignore` rule `~$*` already
covers the filename, so no duplicate rule was added. Safe-staging failure text
now names the actual staged, changed, tracked, or supplied scope, and a real
Git integration test proves `--all-tracked` rejects a forbidden file already
committed in repository history.

## Live-provider evidence

The authorized provider environment was inherited only by the test processes;
names/values were not printed, copied into artifacts, or committed.

- J05: `ENVIRONMENT_BLOCKED`. The topic attempt timed out at the bounded
  60-second provider boundary; the anchored attempt completed locally but did
  not establish a complete provider boundary. No 429 was observed. Evidence:
  `outputs/phase22-real-journeys/p22j05-20260807T050859Z-5500/journey-result.json`.
- J20: `ENVIRONMENT_BLOCKED`. Discovery used three bounded attempts with
  delays 0/2/5 seconds; each ended `provider_incomplete`. Survey and research
  each ran once and ended `provider_inconclusive`. No 429 was observed.
  Evidence:
  `outputs/phase22-real-journeys/p22-j20-20260807T051219Z/journey-result.json`.
- Writer/reviewer independence remains limited. Distinct invocation contexts
  and reloaded artifact hashes are proven, but no separate live reviewer
  provider completed. Metadata alone is not claimed as independent review.

## Test execution

All pytest runs used the repository `.venv`, a unique `--basetemp`, and a
unique cache outside basetemp. Logs were not redirected into basetemp.

The final combined acceptance command was:

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'harness')
& 'C:\Users\j50058254\Desktop\Github repo\OpenSolar-Canonical\.venv\Scripts\python.exe' -m pytest -q tests/harness/benchmark/test_benchmark_report_schema.py tests/harness/benchmark/test_terminal_bench_adapter.py tests/harness/test_status_server_status_route.py tests/harness/test_advanced_ai4rnd_operator.py tests/harness/test_advanced_ai4rnd_product_entrypoint.py tests/harness/test_harness_config_python_selection.py tests/harness/evaluators/scientific/test_claim_verdict_gate.py tests/vertical/account_management/test_local_identity_privacy_channel_security.py tests/vertical/account_management/test_phase22_privacy_uninstall_atomic.py tests/repository/governance/test_safe_staging.py tests/repository/governance/test_secret_scan.py tests/repository/governance/test_windows_filenames.py tests/harness/research_orchestration/test_sandbox_fallback_matrix.py tests/journeys/phase22/code/test_j01_install_status.py tests/journeys/phase22/code/test_j15_cross_platform_install_matrix.py tests/journeys/phase22/code/test_j18_tmux_cli_status_config.py tests/journeys/phase22/code/test_j24_privacy_lifecycle.py --basetemp C:\tmp\oslf-final-combo-bt-20260807 -o cache_dir=C:\tmp\oslf-final-combo-cache-20260807
```

Exit `0`: **154 passed, 0 failed, 2 skipped**, 14 warnings, 127.05s. The skips
were J18 serial-TMUX authorization and native-Windows S01 OS sandbox
enforcement.

The final-correction rerun used the same file list with a new unique
basetemp/cache. It exited `0`: **159 passed, 0 failed, 2 skipped**, 14 warnings,
102.39s. The count increased by five because the secret-scanner and
safe-staging files now contain the added negative/integration tests; the two
skip reasons are unchanged.

The native-Windows final-correction rework reran that same fixed file list
with `PYTHONPATH=harness` and a new unique basetemp/cache. It exited `0`:
**160 passed, 0 failed, 2 skipped**, 14 warnings, 104.46s. The additional pass
is the new committed-history `--all-tracked` integration test; the two skip
reasons remain unchanged.

Other executed suites:

| Scope | Exit | Result |
|---|---:|---|
| R1 control plane, intent, workflow selection, routing/runtime, intake | 0 | 65 passed |
| R2 synthesis/action operators, paper/source CLI, non-live journeys | 0 | 102 operator tests plus accepted journey passes |
| R3 lifecycle recovery, lease, J07/J21, resume/import/crash | 0 | 121 passed |
| R4 TaskGraph/scheduler/claim/benchmark/J03/J08/J09/J22 | 0 | 42 passed |
| R7 GEPA, TaskGraph state, model registry, logical router | 0 | 170 passed |
| R8 governance and real sandbox subprocess matrix | 0 | 127 passed, 1 skipped |
| Status-server final route group | 0 | 14 passed |
| J15/J18 rerun | 0 | 1 passed, 1 skipped |
| J01 post-fix rerun | 0 | 1 passed |
| Interpreter-selection regression | 0 | 2 passed |
| Final-correction focused safety/advanced/dispatcher set | 0 | 121 passed, 1 skipped |
| Direct graph dispatch, lease, TaskGraph state, and operator runtime | 0 | 143 passed |
| Real advanced TaskGraph dispatcher through operatord command backend | 0 | 2 passed |
| Final-correction required eight files | 0 | 123 passed |
| Windows file-lock compatibility contract | 0 | 5 passed |
| Native Windows operatord final file | 0 | 29 passed |

The final-correction file-by-file commands all used the repository `.venv` and
separate directories below `C:\tmp\legacy-final-correction-20260807-1710-*`:

| Command scope | Exit | Result |
|---|---:|---|
| `tests/repository/governance/test_secret_scan.py` | 0 | 26 passed |
| `tests/repository/governance/test_safe_staging.py` | 0 | 34 passed |
| `tests/harness/test_advanced_ai4rnd_operator.py` | 0 | 3 passed |
| `tests/harness/test_advanced_ai4rnd_product_entrypoint.py` | 0 | 4 passed |
| `tests/harness/graph/test_advanced_ai4rnd_dispatcher_integration.py` | 0 | 2 passed |
| `tests/harness/runtime/test_operator_runtime.py` | 0 | 24 passed |
| `tests/harness/graph/test_runtime_status.py` | 0 | 1 passed |
| `tests/harness/test_operatord_daemon.py` | 0 | 29 passed |
| `tests/harness/test_file_lock_compat.py` | 0 | 5 passed |

One pre-fix non-live journey batch had J01 fail because WindowsApps `python3`
output polluted the configured runtime. This was a real product portability
failure, not relabeled. The interpreter-selection fix was added and both J01
and the final combined command then passed. An earlier broad pytest command
without `PYTHONPATH=harness` failed during collection; it was a runner
configuration error and was rerun successfully with the production package
path.

Additional exact executable checks:

```powershell
& 'C:\Program Files\Git\bin\bash.exe' tests/harness/installer/test_s1_installer.sh
& 'C:\Program Files\Git\bin\bash.exe' tests/harness/installer/test_tvs_doctor.sh
& 'C:\Program Files\Git\bin\bash.exe' scripts/check-repo-hygiene.sh
& 'C:\Program Files\Git\bin\bash.exe' tests/repository/governance/test_repo_hygiene.sh
& 'C:\Users\j50058254\Desktop\Github repo\OpenSolar-Canonical\.venv\Scripts\python.exe' scripts/check-safe-staging.py
& 'C:\Users\j50058254\Desktop\Github repo\OpenSolar-Canonical\.venv\Scripts\python.exe' scripts/check-secret-scan.py
& 'C:\Users\j50058254\Desktop\Github repo\OpenSolar-Canonical\.venv\Scripts\python.exe' scripts/check-windows-filenames.py
```

Results: installer 38/38 passed; TVS doctor exited 0 with an explicit skip
because no sandbox TVS checkout exists; hygiene positive and negative controls
passed; CI YAML parsed; safe staging passed; Windows filenames passed; secret
scan passed over 4,447 tracked/staged/untracked candidates with no secret.

The final-correction safety rerun also exited `0` for every required command:
`check-safe-staging.py --all-tracked` reported no forbidden tracked paths;
secret scan checked 4,447 candidates; Windows filename scan checked 4,447
paths; `bash tests/repository/governance/test_repo_hygiene.sh` passed its negative controls; and
`git diff --check` passed.

## Legacy and L2 disposition

The canonical pre-repair ledger and issue map were found and read, without
modification, in the Phase 5 integration worktree:

- `C:\Users\j50058254\Desktop\Github repo\.phase5-worktrees\integration\docs\integrations\autosci\legacy-issue-closure-ledger.md`
- `C:\Users\j50058254\Desktop\Github repo\.phase5-worktrees\integration\.codex-tmp\legacy-issue-audit-20260806\github-issue-map.json`

This code repair does not update those sources. The following is the
integration agent's evidence disposition for final-checker review:

- Legacy IDs fully fixed: `E06`, `E07`, `E12`, `G01`, `G04`, `G05`, `G06`,
  `N05`, `P01`, `P02`, `P04`, `P05`, `P06`, `P08`, `S02`, `S04`, `S05`.
- Legacy IDs still partial/open: `A02`, `A08`, `A09`, `E02`, `E03`, `E04`,
  `E05`, `N09`, `P03`, `P07`, `P09`, `S01`, `S03`, `T02`, `T06`.
- L2 fully fixed by new direct evidence: `Claim & Acceptance-Criteria
  Comparison`, `Evidence, Factuality & Scientific Validity Evaluator`,
  `Verdict, Blocker & Residual-Risk Classification`, `Execution Admission,
  Lease & Concurrency Control`, `Experimental Asset Construction`, and
  `Runtime Control Loop & Run Lifecycle Management`.
- L2 still partial/open: upstream parity and request-taxonomy variants;
  provider-backed `Search Strategy Formation`, `Technical Signal Extraction`,
  and `Trend & Gap Analysis`; live reviewer independence; native Windows OS
  sandbox enforcement; packaged Windows/macOS apps, remote/multi-session TMUX,
  GUI/TUI; hosted account registration/provider revocation; live WeChat and
  Discord routing; full dataset/policy/model graph services.
- L2 not available: MIPROv2, TextGrad, bandit routing, cost-aware RL, AFlow,
  MCTS, ADAS, LoRA, DPO, GRPO, agent RL, judge calibration, reward modeling,
  CEGIS, memory/retrieval learning, Self-RAG, and reranker training. Only the
  Bayesian and CPU-safe SFT reference paths are implemented.

## Final quality gates

- `git diff --check`: passed before staging.
- Merge-marker scan: no unresolved markers.
- Safe-staging, Windows filename, hygiene, and secret scans: passed.
- The tracked Excel `~$` lock file was removed; no formal workbook changed.
- No credential, `.env` content, workbook lock file, output evidence,
  `.pytest-*`, or `.codex-tmp` artifact is committed.
- The branch is not pushed. Clean post-commit status and the final commit are
  recorded in `.codex-tmp/legacy-fix-integration-repair/result.json`.

The correction commit's authoritative full SHA is written to the ignored
post-commit result JSON. A Git commit cannot embed its own final SHA in its
tracked contents without changing that SHA; this record instead binds the
correction to the rework baseline, branch, exact commands, and results.
