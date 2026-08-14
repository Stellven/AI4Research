# OpenSolar Test Layout and Correctness Audit

Baseline: `4b5af751956f8ef1d2eb6bbce8baf9088e694d00`

Read-only audit only. No production or test source files were modified.

## Summary

| Metric | Value | Notes |
| --- | ---: | --- |
| Test-like files | 1118 | Executable test-like files across `.py`, `.ts`, `.js`, `.sh`, `.ps1`, etc. |
| Root `tests/` outside count | 991 | Executable test-like files that live outside the repo root `tests/` tree. |
| Collection errors | 131 | From a `pytest --collect-only` pass in an isolated temp venv. |
| Pollution risks | 2 | Fixed-port / shared-state hazards found in `core/hive/cli`. |
| Misleading tests | 14 | Manual self-tests, static text under `tests/`, and live-provider collection-only tests. |

## High-priority findings

| File(s) | Line(s) | Type | Severity | Recommended move target | Fix suggestion |
| --- | --- | --- | --- | --- | --- |
| `tests/0000_READ_FIRST_GLOBAL_TEST_EXECUTION_PLAN.md` | `1` | Static text under `tests/` | Medium | `docs/integrations/autosci/phase22/test-execution-plan.md` | Move the document out of `tests/` so it is not mistaken for an executable test file. |
| `core/test-monitor.ts`; `core/test-agents.ts`; `core/test-e2e.ts`; `core/test-call-agent.ts`; `core/test-call-quick.ts`; `core/message-listener/test-priorities.ts` | `28`; `46`; `17`; `22`; `1`; `1` | Misnamed executable self-tests outside root `tests/` | Medium | `tests/core/` | Relocate the executable self-tests under the root `tests/` tree with standard discoverable names. |
| `core/hive/cli/test-discovery.ts`; `core/hive/cli/test-integration.ts` | `31`; `54` | Fixed port / shared-state pollution | High | `tests/core/hive/cli/` | Replace hard-coded ports with ephemeral allocation and isolated temp dirs. |
| `desktop/bootstrap-contract.test.js`; `desktop/screens.test.js`; `desktop/frontend-scenarios.test.js`; `desktop/functional.test.js`; `desktop/overhaul-visual.test.js`; `desktop/rapid-switch.test.js`; `desktop/selftest-electron.test.js`; `desktop/src/runtime-detect.test.js`; `desktop/src/selftest-verdict.test.js` | `1`; `61`; `1`; `1`; `1`; `1`; `1`; `1`; `1` | Test suite outside root `tests/` | Medium | `tests/desktop/` | Move the desktop suite under `tests/` or register it explicitly so discovery is consistent across runners. |
| `harness/tests/external-integrations/test_schema_health.sh`; `harness/tests/control_plane/test-autopilot-kb-probe-starts-qmd-proxy.sh`; `harness/tests/benchmark/test-terminal-bench-adapter.sh` | `1`; `1`; `1` | Test-like shell files outside root `tests/` | Medium | `tests/harness/` | Keep executable tests in the root `tests/` tree and leave `harness/` for production code, fixtures, and helpers. |
| `tmp-j21-smoke/harness/plugins/autosci/tests/test_autosci_live_provider_env_gated.py` | `1` | Duplicate / snapshot test tree outside root `tests/` | Medium | `tests/quarantine/tmp-j21-smoke/` | Either promote the snapshot into the canonical journey tree or remove it after the underlying gap is closed. |
| `harness/plugins/autosci/tests/test_autosci_live_provider_env_gated.py`; `harness/plugins/autosci/tests/test_autosci_skill_shim.py`; `harness/plugins/autosci/tests/test_phase19_parity_bridge.py` | `1`; `1`; `1` | Plugin tests outside root `tests/` | Medium | `tests/integrations/autosci/` | Relocate plugin tests under root `tests/` and keep provider-gated cases behind an explicit opt-in marker. |
| `harness/vendor/autoresearch/tests/test_git_push.sh` | `1` | Vendored executable test-like file | Medium | `tests/vendor/autoresearch/` | Move the vendor regression wrapper into root `tests/` and keep the vendored source tree non-executable. |
| `harness/lib/github_intelligence/test_v3_budget_enforcement.py` | `1` | Library tests outside root `tests/` | Low | `tests/harness/lib/` | Relocate library-level tests into the root `tests/` tree so discovery does not depend on a package-local path. |
| `skills/email-to-calendar/scripts/tests/test_activity_ops.py` | `1` | Script tests outside root `tests/` | Low | `tests/skills/email-to-calendar/` | Move the script tests into root `tests/` and keep `scripts/` free of executable test entrypoints. |
| `distribution/pipx/tests/test_cli.py` | `1` | Package-local tests outside root `tests/` | Low | `tests/distribution/pipx/` | Relocate the pipx tests into root `tests/` so discovery is centralized. |
| `harness/scripts/youtube_influence_digest.py` | `50` | Collection dependency blocker | High | No move required | Declare or vendor the missing `requests` dependency in the audit/test environment, or make the import optional so `pytest --collect-only` does not abort. |
| `tests/journeys/phase22/code/test_j02_live_coding_task.py`; `tests/journeys/phase22/code/test_j05_literature_discovery.py`; `tests/journeys/phase22/code/test_j16_tmux_requirements_builder.py`; `tests/journeys/phase22/code/test_j17_tmux_capsule_operator_core.py`; `tests/journeys/phase22/code/test_j20_research_synthesis.py` | `209`; `150`; `857`; `748`; `597` | Live-provider collection-only tests | High | `tests/journeys/phase22/live-provider/` | Keep these collected only and require an explicit `live_provider` opt-in so the default suite never executes live-provider calls. |
| `tests/journeys/phase22/journey-test-plan.md` | `33` | Journey plan mapping gap | Medium | `tests/journeys/phase22/journey-test-plan.md` | Extend the plan to include J11-J24 and keep a direct mapping from each journey file to its plan row. |

## Journey completeness

- Journey code directory is complete: `tests/journeys/phase22/code/` contains `24/24` journey files, `J01` through `J24`.
- Journey plan mapping is incomplete: `tests/journeys/phase22/journey-test-plan.md` enumerates `J01` through `J10` only.
- Live-provider journey files were collected but not executed: `J02`, `J05`, `J16`, `J17`, and `J20`.

## Notes

- The `pytest --collect-only` pass reported `131` collection errors in the isolated audit environment.
- The root cause observed in this pass was a missing `requests` dependency while importing `harness/scripts/youtube_influence_digest.py`.
- No additional repo/home/shared-basetemp write hazards were surfaced in the inspected journey files beyond the fixed-port cases called out above.
- The broad outside-root inventory is still large: `harness/tests` dominates the remainder, followed by `tmp-j21-smoke/harness`, `harness/plugins`, `harness/vendor`, `harness/lib`, `skills/email-to-calendar/scripts/tests`, and smaller buckets such as `harness/integrations`, `harness/status-server`, `harness/docker`, `core/hive`, `core/message-listener`, `distribution/pipx`, `desktop`, and `mempalace`.
