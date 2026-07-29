# Phase 22 Journey Test Report

Generated: 2026-07-29
Run ID: `overnight-phase22-20260729T044000Z`
Repo head: `fd1d52684f340cdec16351c05228ce54569ea0e9`

## Executive Result

Phase 22 L2 ledger completion reached 100% for the 142 brief-report Level 2 rows.
No row remains `NOT_TESTED` or unresolved in the generated ledger.

Final L2 status counts:

| Status | L2 count |
|---|---:|
| PASS | 0 |
| PASS_WITH_KNOWN_LIMITATIONS | 7 |
| FAIL | 53 |
| ENVIRONMENT_BLOCKED | 24 |
| NOT_AVAILABLE | 58 |
| Total | 142 |

Completion checks:

| Check | Result |
|---|---|
| L2_CHECK_COMPLETION_RATE | 100% |
| NOT_TESTED | 0 |
| UNRESOLVED | 0 |
| Journey planned but no direct L2 evidence | 0 |
| No accepted journey evidence | 0 |
| unmatched observed_l2 | 0 |

The canonical full report workbook and the brief report workbook were both
synchronized in place. The final validator passed after the verified staged
brief workbook was copied to the Downloads report path.

## Starting Baseline

The starting brief workbook contained 142 L2 rows: 6
`PASS_WITH_KNOWN_LIMITATIONS`, 3 `FAIL`, 7 `ENVIRONMENT_BLOCKED`, 100
`NOT_TESTED`, and 26 `NOT_AVAILABLE`.

Starting evidence-basis gaps were 67 `Journey planned; no direct L2 evidence`
and 33 `No accepted journey evidence`. The baseline is recorded at
`.codex-tmp/phase22-worker-results/overnight-phase22/baseline.json`.

## Journey Results

| Journey | Result | Evidence |
|---|---|---|
| P22-J01 | ENVIRONMENT_BLOCKED | Git Bash/MINGW install probe returned unsupported OS; WSL enumeration was access denied. |
| P22-J02 | ENVIRONMENT_BLOCKED | Live coding preflight found `bash` and `tmux` missing from PATH before sprint/provider execution. |
| P22-J03 | FAIL | Official platform benchmark ran and scored below threshold 80. |
| P22-J04 | PASS_WITH_KNOWN_LIMITATIONS | Local paper ingest/re-ingest worked; wiki registration boundary incomplete. |
| P22-J05 | FAIL | Topic and anchor live/network discovery ran but returned zero candidates and no provider-backed source channel. |
| P22-J06 | FAIL | Idea generation produced candidates, but no verification-ready/falsifiable idea card. |
| P22-J07 | PASS_WITH_KNOWN_LIMITATIONS | Local experiment ran and metrics passed; runtime status/audit terminal state incomplete. |
| P22-J08 | FAIL | Overbroad all-inputs/all-environments claim was incorrectly marked supported. |
| P22-J09 | PASS_WITH_KNOWN_LIMITATIONS | Markdown report and evidence bundle produced; Review LLM/writeback/HITL compile boundaries limited. |
| P22-J10 | ENVIRONMENT_BLOCKED | Git Bash/MINGW install lifecycle probe returned unsupported OS. |
| P22-J11 | PASS_WITH_KNOWN_LIMITATIONS | Capsule/operator/model registry probes passed with version/governance limitations. |
| P22-J12 | ENVIRONMENT_BLOCKED | Queue/failure recovery path imports Unix-only `fcntl`; WSL preflight access denied. |
| P22-J13 | FAIL | Local UI path crashes on Windows because `signal.SIGPIPE` is unavailable. |
| P22-J14 | NOT_AVAILABLE | No implemented WeChat channel intake entrypoint was found. |
| P22-J15 | PASS_WITH_KNOWN_LIMITATIONS | Windows/package probes recorded; macOS app/CLI lanes remain platform blocked. |

## Commands Run

| Command group | Result |
|---|---|
| Initial collect-only for J01-J10 | 10 tests collected, exit 0 |
| Final collect-only for J01-J15 | 15 tests collected, exit 0 |
| Full non-live journeys | 13 selected: 5 passed, 4 skipped, 4 failed, exit 1 |
| Live/provider journeys | 2 selected: J02 skipped, J05 failed, exit 1 |
| Worker B J03/J04/J06 | 1 passed, 2 failed |
| Worker C J07/J08/J09 | 2 passed, 1 failed |
| Worker D J11-J15 | 2 passed, 2 skipped, 1 failed |
| Workbook render/formula checks | full and staged brief formula-error scans: 0 |
| Final validator | passed |

## Principal Product Failures

- P22-J03 benchmark score below threshold.
- P22-J05 live discovery returned empty/inconclusive provider-backed shortlists.
- P22-J06 idea cards lacked verification-ready falsifiability/minimum-experiment fields.
- P22-J08 exp-eval supported a deliberately overbroad claim.
- P22-J13 Windows local UI crashed on missing `signal.SIGPIPE`.

## Environment And Availability Blocks

- Linux/WSL install lifecycle: Git Bash/MINGW unsupported OS; WSL enumeration
  returned `Wsl/EnumerateDistros/Service/E_ACCESSDENIED`.
- J02 live coding: `bash` and `tmux` missing from PATH before provider/runtime
  execution.
- J12 failure recovery: Unix-only `fcntl` path blocked on Windows.
- J14 WeChat identity: no current production entrypoint.
- J15 macOS App and macOS CLI: Mac runner intentionally not used in this phase.
- Brief report overwrite: resolved after Excel released
  `C:\Users\j50058254\Downloads\AI4RnD Feature List.xlsx`; the synchronized
  staged workbook was copied in place and validated.

## Artifacts

| Artifact | Path |
|---|---|
| L2 ledger | `outputs/phase22-real-journeys/overnight-phase22-20260729T044000Z/l2-evidence-ledger.json` |
| Full report | `docs/integrations/autosci/phase-22-test-report.xlsx` |
| Brief report | `C:\Users\j50058254\Downloads\AI4RnD Feature List.xlsx` |
| Staged synchronized brief report | `.codex-tmp/phase22-worker-results/overnight-phase22/staged-reports/AI4RnD Feature List.xlsx` |
| Historical brief sync blocker | `.codex-tmp/phase22-worker-results/overnight-phase22/brief-sync-blocker.json` |
| Final validator | `.codex-tmp/phase22-worker-results/overnight-phase22/final-validator.json` |

## Validator State

The final validator passed. It confirms ledger completeness, allowed statuses,
formula-error count 0 for the full report and staged brief report, current
Downloads brief counts matching the ledger, no active brief lock file, and
`git diff --check` exit 0.
