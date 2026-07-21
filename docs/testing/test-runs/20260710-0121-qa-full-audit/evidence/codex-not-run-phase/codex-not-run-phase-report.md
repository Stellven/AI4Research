# Codex-relevant NOT_RUN remediation and execution report

## Scope

- Locked commit: `fb3f589b08e4167ac3cb0043fb3d59801a0f110b`
- Source NOT_RUN population: 1435
- Included as Codex-relevant: 861
- Excluded as Claude-related: 123
- Excluded as SciDAG-related: 439
- Excluded as SciMem-related: 22

The exclusions are feature-contract exclusions, not filename-only exclusions. Generic task graph and non-scientific memory surfaces remain in scope.

## Mapping remediation

- Exact locked-checkout product mappings: 673
- Audit-only structural entrypoints with unresolved product behavior mapping: 188
- All 861 included rows passed structural preconditions after correction.

Audit-only mappings do not promote a feature to PASS. They keep the row executable and expose the remaining behavioral mapping gap.

## Result summary

| Status | Count |
|---|---:|
| FAIL | 14 |
| INCONCLUSIVE_EXPECTED | 583 |
| NOT_RUN | 26 |
| PASS | 228 |
| SKIPPED_ENV | 10 |

The 26 NOT_RUN rows are deliberately pending explicit user acknowledgment for HITL/provider/protected-side-effect gates. The 10 SKIPPED_ENV rows are Desktop/platform cases blocked by unavailable Playwright browser binaries or renderer dependencies; no dependency download was performed.

## Executed audit suites

| Suite | Tests | Failures | Errors | Skipped |
|---|---:|---:|---:|---:|
| Evidence schema | 52 | 0 | 0 | 0 |
| QA inventory | 88 | 0 | 0 | 0 |
| Scientific gate CLI | 34 | 0 | 0 | 0 |
| CI workflow | 15 | 6 | 0 | 0 |
| Structural precondition | 861 | 0 | 0 | 0 |
| Installer/component | 6 | 6 | 0 | 0 |

In addition, the existing target sweep attempted 282 isolated targets (1,903 pytest passes, 284 failures, 9 errors, 14 skips in the first sweep), followed by infrastructure-corrected reruns, reviewed shell tests, and the AutoSci shim rerun (162 pass, 11 fail). Raw target failure is not automatically an atomic feature failure.

## Direct failures

| Feature | Status | Reason |
|---|---|---|
| `WF-0008-INTAKE-ROUTES-GRAPH-SPRINT-45CDE3` | FAIL | PM intake research request raised KeyError for capability_capsule_id instead of routing a complete capsule. |
| `WF-0086-SOURCE-FULLY-REGISTERED-ONLY-1F8E0A` | FAIL | PDF ingest returned registration_incomplete where the exact shim contract required registration_ready. |
| `WF-0091-TARGET-RESOLVED-REJECTED-ACTIONABLE-B20BDE` | FAIL | Novelty provider payload reference was not canonicalized to the encoded file URI in a checkout path containing spaces. |
| `WF-0260-REPORTS-MISSING-PRESENT-CONFIG-234895` | FAIL | setup_status evidence referenced missing plugins/autosci/config/.env.example and the exact route returned failed. |
| `WF-0261-NONINTERACTIVE-MISSING-VALUES-PRODUCE-0C96FF` | FAIL | Noninteractive setup could not emit the expected gated remedy because its declared .env.example artifact is absent. |
| `WF-0421-RUNS-RECORDS-BROWSER-AUTOMATION-D5E6FF` | FAIL | At least one assertion-level testcase matching this exact command/action and atomic behavior failed. |
| `WF-0434-JOB-FAILS-FAILING-UNDERLYING-EE12FB` | FAIL | Exact workflow contract failed: diagnostic artifact/job summary is absent. |
| `WF-0435-EXPECTED-ARTIFACTS-STATUS-SUMMARIES-B115CE` | FAIL | Exact workflow contract failed: diagnostic artifact/job summary is absent. |
| `WF-0438-JOB-FAILS-FAILING-UNDERLYING-DD0F6A` | FAIL | Exact workflow contract failed: diagnostic artifact/job summary is absent. |
| `WF-0439-EXPECTED-ARTIFACTS-STATUS-SUMMARIES-0F1251` | FAIL | Exact workflow contract failed: diagnostic artifact/job summary is absent. |
| `WF-0442-JOB-FAILS-FAILING-UNDERLYING-74BC93` | FAIL | Exact workflow contract failed: diagnostic artifact/job summary is absent. |
| `WF-0443-EXPECTED-ARTIFACTS-STATUS-SUMMARIES-9BB2AA` | FAIL | Exact workflow contract failed: diagnostic artifact/job summary is absent. |
| `MISC-0279-ACCEPTED-FLAGS-ENV-CONFIG-F0A876` | FAIL | release/build.sh --dry-run emits the plan but exits 1 because tar/head trips pipefail. |
| `MISC-0282-DRY-RUN-WRITES-NOTHING-898484` | FAIL | release/build.sh --dry-run emits the plan but exits 1 because tar/head trips pipefail. |

## Evidence boundaries

- PASS requires an exact schema/gate/CI/artifact contract or an assertion-level testcase that matches the same command/action and atomic behavior.
- Related or partial tests remain INCONCLUSIVE_EXPECTED.
- Fixture evidence is not reported as live provider or full runtime parity.
- No real email, remote execution, external provider, credential write, release publication, tag, push, or real-home mutation was performed.
- AutoSci SciDAG/SciMem and Claude-specific features are outside this phase by user direction.

## Remaining decision

The pending gate list is in `pending-acknowledgment-features.csv`. The phase cannot be declared complete until the user explicitly approves or declines those routes.
