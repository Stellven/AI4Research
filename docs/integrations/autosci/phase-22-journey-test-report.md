# Phase 22 Journey Test Report

Generated: 2026-08-14
Run ID: `phase22-final-report-sync-20260814`
Repo head before report synchronization: `71a68eeef`

## Repair Closure Synchronization Addendum

This addendum supersedes older conclusions for the 25 repair IDs listed below.
It integrates the accepted blocker-review evidence plus the later Windows,
WSL, macOS, live-provider, external-delivery, external-data, trust-anchor, and
attributable human-approval evidence. It does not convert unexercised features
or variants to PASS.

Current L2 status counts:

| Status | L2 count |
|---|---:|
| PASS | 30 |
| PASS_WITH_KNOWN_LIMITATIONS | 86 |
| FAIL | 0 |
| ENVIRONMENT_BLOCKED | 0 |
| NOT_AVAILABLE | 25 |
| NOT_TESTED | 1 |
| Total | 142 |

Accepted repair synchronization:

| Repair ID | Current L2 conclusion | Accepted evidence and retained boundary |
|---|---|---|
| P22-REPAIR-044 | PASS_WITH_KNOWN_LIMITATIONS | The hash-bound retrieval comparison passed with a policy-pinned trust registry, protocol commit/blob checks, 13/13 journey assertions, and adversarial rejection tests. The GitHub release is an immutable external anchor published after the result, not a claim of a pre-result release timestamp; broad-domain benchmarking remains untested. |
| P22-REPAIR-045 | PASS_WITH_KNOWN_LIMITATIONS | A live OpenRouter writer and OpenAI reviewer completed with independent provider provenance and 4/4 assertions. This proves the authorized provider pair, not every provider/model combination. |
| P22-REPAIR-047 | PASS_WITH_KNOWN_LIMITATIONS | The production evaluator accepted preregistered arXiv and OpenAlex holdouts at 18/20 each; signatures, receipts, hashes, timestamps, and registry pins verified. The conclusion is limited to the fixed corpus, matching rule, providers, and collection time. |
| P22-REPAIR-054 | PASS_WITH_KNOWN_LIMITATIONS | The authorized Phase 22 handoff was delivered through Gmail and J09 passed 30/30 assertions. Recipient acceptance was explicitly not required; other channels and long-term lifecycle variants remain untested. |
| P22-REPAIR-069 | PASS_WITH_KNOWN_LIMITATIONS | The local legal/IP gate passed fail-closed checks and the named artifact received attributable internal approval for the stated CA, 30-day, no-personal-data use. This is internal approval, not legal advice or external counsel. |
| P22-REPAIR-071 | PASS_WITH_KNOWN_LIMITATIONS | The focused lifecycle journey entered human review, resumed with attributable approval, recorded the transition, and rejected replay. Broader parity variants remain outside this focused proof. |
| P22-REPAIR-121 | PASS | The current production trace selector passed project, actor, run, and future-since filters. |
| P22-REPAIR-125 | PASS | A real Darwin arm64 run passed the macOS App lane. Per explicit user direction, the evidence is accepted despite the retained `desktop/package.json` build-command delta note. |
| P22-REPAIR-126 | PASS | The same real Darwin arm64 run passed the macOS CLI install/status/uninstall lane; CLI-relevant files were unchanged against the reviewed head. |
| P22-REPAIR-131 | PASS_WITH_KNOWN_LIMITATIONS | The Windows UI-lite path no longer crashes, and both WSL Ubuntu tmux/status selectors passed. Other Linux distributions, terminal implementations, and full live-Claude pane operation were not inferred. |

Accepted blocker-review reconciliation:

| Repair ID | Current L2 conclusion | Accepted evidence and retained boundary |
|---|---|---|
| P22-REPAIR-018 | PASS_WITH_KNOWN_LIMITATIONS | The live research route extracted 15 exact-span, hash-linked technical signals from 9 real sources. Unseen full text and exhaustive coverage are not claimed. |
| P22-REPAIR-020 | PASS_WITH_KNOWN_LIMITATIONS | The same run validated 3 cross-source trends and 2 evidence-linked gaps. These are bounded themes, not causal longitudinal findings. |
| P22-REPAIR-033 | PASS_WITH_KNOWN_LIMITATIONS | J06 generated complete source-backed falsifiability fields. External novelty and Review LLM variants remain outside scope. |
| P22-REPAIR-034 | PASS | J07 passed a durable verification-ready plan with exact command admission, bound assets, safe outputs, and replay. |
| P22-REPAIR-037 | PASS_WITH_KNOWN_LIMITATIONS | J21 bound the generated plan, assets, configuration, and exact argv to the command executed on the local Python experiment path. |
| P22-REPAIR-039 | PASS_WITH_KNOWN_LIMITATIONS | J21 produced a schema-validated, hash-linked, replayable handoff package; unrelated package families were not inferred. |
| P22-REPAIR-055 | NOT_TESTED | The old atomic failure is stale and 14 capability tests pass, but no accepted real-task journey maps to this L2. |
| P22-REPAIR-066 | PASS_WITH_KNOWN_LIMITATIONS | J21 accepted valid contracts and rejected invalid, unsupported, provenance-corrupt, and identity-corrupt variants for the exercised evaluator family. |
| P22-REPAIR-070 | PASS_WITH_KNOWN_LIMITATIONS | The overbroad worldwide claim is now rejected while bounded claims pass; unexercised Review LLM/final-verdict variants remain limited. |
| P22-REPAIR-095 | PASS_WITH_KNOWN_LIMITATIONS | J21 proved lease acquire, heartbeat, duplicate rejection, release, expiry, stale recovery, and recovery audit for the exercised adapter. |
| P22-REPAIR-110 | PASS_WITH_KNOWN_LIMITATIONS | J21 generated and replayed durable experiment assets for the tested Python path; other asset types remain untested. |
| P22-REPAIR-113 | PASS_WITH_KNOWN_LIMITATIONS | J09 produced a schema-valid decision artifact with a complete criterion matrix and checked evidence provenance; external approval variants remain limited. |
| P22-REPAIR-115 | PASS_WITH_KNOWN_LIMITATIONS | The accepted macOS J16 run completed the physical Spark integration path with 12/12 assertions; other providers, models, and platforms are not inferred. |
| P22-REPAIR-116 | PASS_WITH_KNOWN_LIMITATIONS | The same macOS run reproduced the defect, applied the scoped repair, and passed the before/after suite; the missing formal eval sidecar remains an audit note. |
| P22-REPAIR-119 | PASS_WITH_KNOWN_LIMITATIONS | J25 passed bundle construction, Git-preimage checks, offline lifecycle checks, uninstall, and rollback on WSL/Linux CPython 3.12. |

The synchronized full and brief workbooks retain the atomic inventory as a
diagnostic layer. Journey conclusions do not overwrite atomic enums. There are
no current L2 FAIL rows, but 25 features remain NOT_AVAILABLE and one remains
NOT_TESTED, so this is not a claim that all 142 Level 2 features passed.

## Final Integration Addendum

This addendum supersedes the 2026-07-30 stakeholder roll-up below. The final
integration pass cherry-picked the nine repair commits onto fixed baseline
`4b5af751956f8ef1d2eb6bbce8baf9088e694d00`, ran the current targeted and
journey suites, and downgraded positive inference-only rows unless production
journey evidence was present.

Final L2 status counts:

| Status | L2 count |
|---|---:|
| PASS | 26 |
| PASS_WITH_KNOWN_LIMITATIONS | 68 |
| FAIL | 14 |
| ENVIRONMENT_BLOCKED | 2 |
| NOT_AVAILABLE | 22 |
| NOT_TESTED | 10 |
| Total | 142 |

Accepted final validation highlights:

| Scope | Result |
|---|---|
| Changed targeted regression set | 89 passed, 3 skipped |
| Pytest collection | 7029 collected, 0 collection errors |
| J01-J24 final journey suite | 15 passed, 11 skipped |
| Broad root shards | 2101 passed, 179 failed, 6 errors, 1 skipped, 3 xfailed, non-deduplicated |
| Broad harness sub-shard A | incomplete; no terminal pytest summary |
| Workbook formula scan | 0 formula-error matches in full and brief reports |

The final journey suite is not treated as an all-product PASS: skipped journeys
remain environment or platform blocks, and the broad suite still contains real
failures/errors. Live providers were not rerun in this final pass without fresh
explicit authorization and configured credentials.

## Executive Result

Historical 2026-07-30 result retained for traceability; use the Final
Integration Addendum above for the current verdict.

Phase 22 L2 ledger completion reached 100% for the 142 brief-report Level 2 rows:
every row has an explicit final status, issue statement, and traceable evidence
basis. Eight management-requested likely-state inferences are labeled as
inferences rather than direct journey proof; no L2 remains `NOT_TESTED` or
`ENVIRONMENT_BLOCKED` in the current stakeholder roll-up.

Final L2 status counts:

| Status | L2 count |
|---|---:|
| PASS | 26 |
| PASS_WITH_KNOWN_LIMITATIONS | 66 |
| FAIL | 22 |
| ENVIRONMENT_BLOCKED | 0 |
| NOT_AVAILABLE | 28 |
| NOT_TESTED | 0 |
| Total | 142 |

Post-checkpoint J02 live rerun addendum: on 2026-07-29, Windows/WSL batch
`phase22-j02-live-windows-008` reran P22-J02 with authorized live Codex
provider execution and produced `PASS_WITH_KNOWN_LIMITATIONS` evidence for all
22 planned J02 L2s. This supersedes the earlier J02 environment block and is
included in the synchronized final ledger above.

Completion checks:

| Check | Result |
|---|---|
| L2_CHECK_COMPLETION_RATE | 100% |
| NOT_TESTED | 0 |
| UNRESOLVED | 0 |
| Management-requested likely-state inference | 8 rows, explicitly labeled rather than presented as direct journey proof |
| No accepted journey evidence | 0 rows left without an explicit current conclusion |
| unmatched observed_l2 | 0 |

The canonical full, brief, and ultra-brief report workbooks were synchronized
in place. The ultra-brief workbook omits atomic columns; its broken atomic
summary formulas were removed during validation.

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
| P22-J02 | PASS_WITH_KNOWN_LIMITATIONS | Windows/WSL live Codex rerun passed: Planner and Builder operator-result artifacts were recorded, the isolated repo diff changed `calculator.py`, target pytest passed, and `eval-verdict` moved the sprint to `passed`; known limitation: legacy `eval.md` sidecar was not emitted. Evidence: `outputs/phase22-real-journeys/p22j02-20260729T163246Z-126196/journey-result.json`. |
| P22-J03 | PASS | The official benchmarking process completed, wrote consistent JSON/Markdown/evidence artifacts, and correctly reported that the measured target scored 25/100. That target-quality finding remains visible but no longer incorrectly fails the benchmarking feature. Evidence: `outputs/phase22-real-journeys/p22j03-20260730T183907Z-30832/journey-result.json`. |
| P22-J04 | PASS_WITH_KNOWN_LIMITATIONS | Local paper ingest/re-ingest worked; wiki registration boundary incomplete. |
| P22-J05 | PASS_WITH_KNOWN_LIMITATIONS | Authorized live Semantic Scholar topic and anchor discovery passed on Windows. Both modes returned five unique, non-fixture candidates with stable identity, source-channel provenance, completed provider boundaries, and durable artifacts. Technical Signal Extraction and Trend & Gap Analysis are limited-pass management inferences, not direct J05 proof. Evidence: `outputs/phase22-real-journeys/p22j05-20260730T125408Z-13396/journey-result.json`. |
| P22-J06 | FAIL | Idea generation produced usable candidates: 7 mapped L2s are limited passes, while Falsifiability Screening & Hypothesis Contracting and Verification-Ready POC Design remain failed. |
| P22-J07 | PASS_WITH_KNOWN_LIMITATIONS | The local experiment process and metric checks completed. Runtime lifecycle is a limited pass, but `exp-status` remained unknown/inconclusive; seven planned L2s lacked direct assertions. |
| P22-J08 | FAIL | Claim & Acceptance-Criteria Comparison failed because an overbroad all-inputs/all-environments claim was marked supported. Later J22 evidence and explicitly labeled management inferences provide current conclusions for the related review L2s without converting the J08 defect to a pass. |
| P22-J09 | PASS_WITH_KNOWN_LIMITATIONS | The report package, compiled PDF, policy-bound review artifacts, and authorized Gmail delivery completed; 30/30 assertions passed. Other delivery channels and long-term lifecycle variants remain untested. Evidence: `outputs/phase22-real-journeys/p22j09-20260812T172710Z-22124/journey-result.json`. |
| P22-J10 | ENVIRONMENT_BLOCKED | Git Bash/MINGW install lifecycle probe returned unsupported OS. |
| P22-J11 | PASS_WITH_KNOWN_LIMITATIONS | Capsule/operator/model registry probes passed with version/governance limitations. |
| P22-J12 | ENVIRONMENT_BLOCKED | Queue/failure recovery path imports Unix-only `fcntl`; WSL preflight access denied. |
| P22-J13 | PASS_WITH_KNOWN_LIMITATIONS | The Windows UI-lite path no longer crashes and the current selector passed. WSL tmux/status coverage is supplied separately by the accepted P22-J18 rerun; packaged Electron launch was not part of J13. Evidence: `outputs/phase22-real-journeys/p22j13-20260812T172016Z-20044/journey-result.json`. |
| P22-J14 | NOT_AVAILABLE | No implemented WeChat channel intake entrypoint was found. |
| P22-J15 | PASS | The imported evidence bundle records a real Darwin arm64 run with the macOS App and CLI lanes passing. The App result is accepted by explicit user direction with the `desktop/package.json` delta retained as an audit note. Evidence: `.codex-tmp/phase22-worker-results/p22-125-126-macos-import/result.json`. |
| P22-J16 | FAIL | Authorized live-provider TMUX journey ran in SolarUbuntu. The journey-level result is FAIL: harness-start returned inner exit 1 and the scoped defect repair was not verified by a passing diff/tests path. L2 outcomes: 7 PASS, 2 PASS_WITH_KNOWN_LIMITATIONS, 2 FAIL. Evidence: outputs/phase22-real-journeys/p22-j16-20260730T120542Z-1126077/journey-result.json. |
| P22-J17 | FAIL | Authorized live-provider TMUX journey ran in SolarUbuntu. The journey-level result is FAIL because harness-start, harness-restart-after-interruption, and eval-verdict-pass returned inner exit 1. L2 outcomes: 12 PASS, 1 PASS_WITH_KNOWN_LIMITATIONS. Evidence: outputs/phase22-real-journeys/p22-j17-20260730T121910Z-1142293/journey-result.json. |
| P22-J18 | PASS_WITH_KNOWN_LIMITATIONS | Ubuntu-24.04 WSL2 ran the tmux CLI/status selector and real Linux lifecycle selector successfully; the latter passed 11/11 assertions. Other distributions and full live-Claude pane operation remain untested. Evidence: `outputs/phase22-real-journeys/p22-j18-real-linux-status-20260812T210634Z-384/journey-result.json`. |
| P22-J19 | PASS_WITH_KNOWN_LIMITATIONS | Production web/status dashboard rendered in installed Chrome headless against a sandbox status-server, persisted Codex settings through the backend, reflected values in the Settings UI, and captured a non-empty screenshot. Evidence: outputs/phase22-real-journeys/p22-j19-real-gui-dashboard-20260730T055154Z-14104/journey-result.json. |
| P22-J20 | ENVIRONMENT_BLOCKED | The research-synthesis attempt reached the provider boundary but did not obtain a usable provider-backed paper set. Its two affected L2 stakeholder conclusions are explicitly labeled management inferences, so this journey block does not create a current L2 environment block. Evidence: `outputs/phase22-real-journeys/p22-j20-20260730T160702Z/journey-result.json`. |
| P22-J21 | FAIL with mixed L2 outcomes | The real experiment/build/handoff task produced 1 PASS, 5 limited passes, and 2 failures in the worker evidence; the accepted L2 roll-up retains the reviewed per-feature conclusions. Evidence: `.codex-tmp/phase22-worker-results/J21-experiment-build-001/result.json`. |
| P22-J22 | FAIL with mixed L2 outcomes | Evidence completeness and follow-up recording worked, but the overbroad claim still received an unsafe supported verdict. Evidence: `.codex-tmp/phase22-worker-results/J22-evidence-review-001/result.json`. |
| P22-J23 | PASS | The exact WSL2 selector completed a real OpenRouter gpt-5.5 request through the production AutoSci review entrypoint with no fallback. Requested and observed routes matched, and request/response hashes plus token/cost usage were retained. Provider latency is optional when the provider does not return it under the accepted J23 criteria. Evidence: `outputs/phase22-real-journeys/p22-j23-20260730T203137Z-277/journey-result.json`. |
| P22-J24 | ENVIRONMENT_BLOCKED | The Windows install preflight stopped at the unsupported-OS boundary before privacy lifecycle actions ran. The affected L2 stakeholder conclusion remains an explicitly labeled implementation-based inference rather than direct journey proof. Evidence: `.codex-tmp/phase22-worker-results/J24-privacy-lifecycle-001/result.json`. |

## Commands Run

| Command group | Result |
|---|---|
| Initial collect-only for J01-J10 | 10 tests collected, exit 0 |
| Final collect-only for J01-J15 | 15 tests collected, exit 0 |
| Full non-live journeys | 13 selected: 5 passed, 4 skipped, 4 failed, exit 1 |
| Live/provider journeys | 2 selected: J02 skipped, J05 failed, exit 1 |
| J02 Windows/WSL live rerun | 1 selected: P22-J02 passed as `PASS_WITH_KNOWN_LIMITATIONS`, 22/22 planned L2s supported, exit 0 |
| J05 live-provider rerun | Exact selector passed, exit 0. Topic and anchor Semantic Scholar modes each returned five durable candidates after transient 429/500 provider responses. |
| J16/J17 live-provider TMUX reruns | User-authorized SolarUbuntu live-provider runs executed. J16 journey-level result is FAIL with 7 PASS, 2 limited pass, and 2 FAIL L2 outcomes; J17 journey-level result is FAIL with 12 PASS and 1 limited pass L2 outcomes. |
| J18/J19 local runtime reruns | J18 Linux/status/TMUX lifecycle and J19 headless GUI dashboard are accepted as PASS_WITH_KNOWN_LIMITATIONS from production-entrypoint local runtime evidence. |
| J03 benchmark criterion correction | Exact selector passed, exit 0. Benchmark-process completion is now evaluated separately from the measured target-quality score. |
| J20-J24 focused journeys | J20 and J24 retained journey-level environment blocks; J21 and J22 retained mixed/product failures; J23 exact WSL2 live-provider selector passed. |
| J23 live-provider rerun | Exact WSL2 selector passed, exit 0. OpenRouter gpt-5.5 routing plus request/response hashes and token/cost audit fields were verified; missing optional provider latency does not reduce the result. |
| Worker B J03/J04/J06 | 1 passed, 2 failed |
| Worker C J07/J08/J09 | 2 passed, 1 failed |
| Worker D J11-J15 | 2 passed, 2 skipped, 1 failed |
| Workbook render/formula checks | full and staged brief formula-error scans: 0 |
| Final validator | passed |

## Principal Product Failures

- P22-J06 idea cards lacked verification-ready falsifiability/minimum-experiment fields; only the two directly affected L2s remain failed.
- P22-J08 exp-eval supported a deliberately overbroad claim.
- P22-J16 live-provider TMUX journey failed harness/eval and scoped defect-repair acceptance criteria.
- P22-J17 live-provider TMUX journey failed required harness start/restart/eval-verdict command assertions.

## Environment And Availability Blocks

- Linux/WSL install lifecycle: Git Bash/MINGW unsupported OS; WSL enumeration
  returned `Wsl/EnumerateDistros/Service/E_ACCESSDENIED`.
- J02 live coding: resolved by Windows/WSL batch
  `phase22-j02-live-windows-008`; no J02 environment blocker remains. The only
  retained limitation is the missing legacy `eval.md` sidecar after
  `eval-verdict` accepted the sprint.
- J12 failure recovery: Unix-only `fcntl` path blocked on Windows.
- J14 WeChat identity: no current production entrypoint.
- J15 macOS App and macOS CLI: resolved by the accepted Darwin arm64 evidence bundle. Both lanes are recorded as `PASS`; the App package-command delta remains an audit note by explicit user direction, not an environment blocker.
- J05 literature discovery: the earlier Semantic Scholar rate-limit block is resolved. The accepted Windows live run used Semantic Scholar search/reference channels; other providers/source families remain untested, and Technical Signal Extraction plus Trend & Gap Analysis still lack direct journey evidence.
- J16/J17/TMUX: environment blocker is resolved by authorized SolarUbuntu live-provider runs; both journeys now record product-level FAIL boundaries rather than platform blocks.
- J18 Linux CLI/status/TMUX: the current Ubuntu-24.04 WSL2 selectors passed; remote hosts, concurrent sessions, other terminal implementations, distribution variants, and full live repair journeys remain untested.
- J19 GUI: local Chrome headless status-dashboard evidence is accepted as PASS_WITH_KNOWN_LIMITATIONS; packaged Electron/manual attach/accessibility/account-channel variants remain untested or unavailable.
- J20 and J24: these individual attempts remain environment-blocked, but the current L2 roll-up uses clearly labeled management inferences rather than environment-blocked conclusions. They are not direct proof.
- J23 model routing/auditing: the earlier Windows 10013 attempt is superseded by the accepted WSL2 live-provider run. Provider latency is optional when absent, and both routed-call and audit L2 criteria passed.
- Brief report overwrite: resolved after Excel released
  `C:\Users\j50058254\Downloads\AI4RnD Feature List.xlsx`; the synchronized
  staged workbook was copied in place and validated.

## Artifacts

| Artifact | Path |
|---|---|
| L2 ledger | `outputs/phase22-final-sync-20260730T132000Z/final-l2-ledger.json` |
| Full report | `docs/integrations/autosci/phase-22-test-report.xlsx` |
| Brief report | `C:\Users\j50058254\Downloads\AI4RnD Feature List.xlsx` |
| Ultra-brief report | `C:\Users\j50058254\Downloads\AI4RnD Brief Feature List.xlsx` |
| Staged synchronized brief report | `outputs/phase22-overnight-environment-resolution-20260730T122000Z/staged-reports/AI4RnD Feature List.xlsx` |
| Historical brief sync blocker | `.codex-tmp/phase22-worker-results/overnight-phase22/brief-sync-blocker.json` |
| Final validator | `outputs/phase22-j23-pass-sync-20260730/final-validator.json` |
| Integrated L2 issue register | `docs/integrations/autosci/phase-22-l2-issue-register.md` |
| J05 live-provider result | `.codex-tmp/phase22-worker-results/J05-live-provider-001/result.json` |
| J16-J19 serial result | `.codex-tmp/phase22-worker-results/TMUX-serial-001/result.json` |
| J03 accepted evidence | `outputs/phase22-real-journeys/p22j03-20260730T183907Z-30832/journey-result.json` |
| J23 accepted evidence | `outputs/phase22-real-journeys/p22-j23-20260730T203137Z-277/journey-result.json` |
| Current integration validator | `outputs/phase22-j23-pass-sync-20260730/final-validator.json` |

## Validator State

The 2026-07-30 unified review contains 142 canonical L2 rows. Current
counts are 26 `PASS`, 66 `PASS_WITH_KNOWN_LIMITATIONS`, 22 `FAIL`, 0
`ENVIRONMENT_BLOCKED`, 28 `NOT_AVAILABLE`, and 0 `NOT_TESTED`. One observed
J07 label, `Experiment Status & Evaluation`, is retained as unmatched evidence
metadata because it is not a canonical row in the 142-L2 feature list.

The full report is synchronized from this reviewed ledger. The brief and
ultra-brief reports were generated and validated as staged workbooks, then
copied to their canonical Downloads paths and revalidated there.

## Final J23 PASS Synchronization

Logged: 2026-07-30

The accepted J23 criteria no longer require a latency field when the provider
does not return one. Route completion, exact provider/model matching, no
fallback, request/response linkage, and token/cost usage evidence remain
required. The exact WSL2 selector passed with exit code 0 and run ID
`p22-j23-20260730T203137Z-277`; both `Model Routing & Selection` and `Model
Usage Auditing` are now `PASS`.

Current counts are `PASS=26`, `PASS_WITH_KNOWN_LIMITATIONS=66`, `FAIL=22`,
`ENVIRONMENT_BLOCKED=0`, `NOT_AVAILABLE=28`, and `NOT_TESTED=0`.

## Historical Integration Rework Validator

Current rework validator: outputs/phase22-final-sync-20260730T132000Z/final-validator.json.

## Historical Overnight Environment Blocker Resolution

Logged: 2026-07-30

The original 35-row environment-blocker follow-up produced PASS=19, PASS_WITH_KNOWN_LIMITATIONS=7, FAIL=2, and ENVIRONMENT_BLOCKED=7. The later accepted J05 live-provider run supersedes the seven remaining provider-blocked L2 entries: five are limited passes and two are `NOT_TESTED` because the journey did not exercise technical-signal extraction or trend/gap analysis. J16/J17 live-provider TMUX journeys ran and exposed product-level failures; J18/J19 local runtime blockers are resolved as limited passes.

Validator: outputs/phase22-final-sync-20260730T132000Z/final-validator.json.

## Historical J05 Live Provider Sync

Logged: 2026-07-30

The accepted exact J05 selector completed with exit code 0 on Windows. Topic
search and anchor-reference discovery each returned five unique live Semantic
Scholar candidates, with stable identities, source-channel provenance,
completed provider boundaries, and durable artifacts. Earlier HTTP 429/500
responses are retained as a provider-stability limitation rather than an
environment block.

At that checkpoint, the 142-L2 counts were `PASS=20`,
`PASS_WITH_KNOWN_LIMITATIONS=51`, `FAIL=21`, `ENVIRONMENT_BLOCKED=0`,
`NOT_AVAILABLE=27`, and `NOT_TESTED=23`. The two J05 rows retained as
`NOT_TESTED` are `Technical Signal Extraction` and `Trend & Gap Analysis`.
