# QA Test Execution Report - 2026-07-09

## Scope

This run picks up from the repo-derived QA inventory and executes local, reproducible tests against the current BetterSolar checkout.

Source inventory used:

- `docs/testing/qa_feature_inventory.csv`
- `docs/testing/qa_master_pass_fail_table.md`
- `docs/testing/qa_inventory_manifest.json`

Run artifact directory:

- `docs/testing/test-runs/20260709-qa-execution/`

## Environment

- Repo: `/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar`
- Python test runtime: `harness/bin/python3`
- Node runtime: `node v26.1.0`
- npm: `11.14.1`
- Bun: `1.3.14`
- Network was used only for scoped dependency setup of desktop Playwright browsers after initial desktop tests were blocked.

Dependency setup performed during this run:

- `desktop/npm ci`
  - Manifest/lockfile: `desktop/package.json`, `desktop/package-lock.json`
  - Project-local path written: `desktop/node_modules`
  - npm cache identified before install: `/Users/jamesyuan/.npm`
  - Result: install succeeded; npm reported 1 high severity audit finding. No audit fix was applied.
- `PLAYWRIGHT_BROWSERS_PATH=0 npx playwright install chromium`
  - Browser binaries written under `desktop/node_modules/playwright-core/.local-browsers`
  - This avoided the default home-level Playwright browser cache.
- `bun install --frozen-lockfile`
  - Manifest/lockfile: `package.json`, `bun.lock`
  - Project-local path written: `node_modules`
  - Bun cache: `/Users/jamesyuan/.bun/install/cache`
  - Result: install succeeded; lockfile was not changed.

## Command Summary

Raw command status files are stored as `*.status.json` in this run directory.

Total command attempts: 67

- Exit 0: 39
- Non-zero: 28

Important note: this count includes pre-dependency failures and their later reruns. For example, desktop Playwright tests initially failed because `desktop/node_modules` did not exist, then passed after scoped dependency installation.

## Overall Decision

Status: NO-GO for a full repository release.

Reason: several acceptance groups still have failing deterministic tests, especially graph orchestration, runtime operators, research survey, root TypeScript/Bun suite, data-plane fixtures, benchmark adapter behavior, AutoSci premerge hygiene, and front-door intake checks.

Narrower conclusion: the AutoSci evaluator/dispatch component path is green in deterministic tests, but the broader repo is not green, and the front-door/intake plus premerge gates are not fully passing.

## Passing Evidence

| Area | Evidence | Result |
|---|---|---|
| QA inventory generator | `qa_inventory_py_compile`, `qa_inventory_regenerate`, `json_manifest_sanity` | PASS |
| Static syntax and metadata | `python_syntax_static`, `shell_syntax_static`, `workflow_yaml_static`, `component_manifest_static`, `physical_operators_json` | PASS |
| AutoSci evaluator and contract path | `autosci_eval_dispatch_and_intake`, `autosci_scientific_runtime_smoke`, `autosci_product_smoke_subset` | PASS |
| Desktop app after dependency setup | `desktop_gate_after_install`, `desktop_screens_after_install`, `desktop_functional_after_install`, `desktop_rapid_switch_after_install`, `desktop_overhaul_visual_after_install`, `desktop_frontend_scenarios_after_install_with_repo_harness` | PASS |
| Status server routes | `status_server_full_pytest`, `status_server_pytest_subset` | PASS |
| Packaging and installer subset | `pipx_distribution_pytest_harness`, `script_check_installer_contract`, `desktop_prepackage_check` | PASS |
| Repository gates subset | `script_check_core_imports_after_bun_install`, `script_check_harness_plumbing`, `script_check_privacy`, `script_check_solar_status`, `script_check_solar_ui_lite`, `script_check_dry_run` | PASS |
| Research unit tests | `research_unit_pytest` | PASS |
| Browser, code-signal, influence units | `browser_pytest`, `code_signal_pytest`, `influence_pytest` | PASS |
| Harness smoke subset | `shell_smoke_core`, `shell_state_read_preflight`, `model_registry_guard`, `model_config_single_source` | PASS |

## Failing Or Blocked Evidence

| Area | Evidence | Classification | Key proof |
|---|---|---|---|
| Root Bun suite / TVS | `root_bun_test_after_bun_install` | FAIL | unresolved imports for `tvs/termplane/render/grid`, `tvs/v2`, `tvs/v2/display`, and package `tvs`; desktop frontend scenario also requires explicit env when invoked by root test discovery |
| Graph orchestration | `graph_pytest_suite`, `graph_pytest_without_status_surface` | FAIL | collection error for missing `epic_child_status_lines`; rerun excluding that file still had 18 failures around capability inference, pane hygiene, and missing `multi_task_runner` APIs |
| Runtime operators | `runtime_pytest` | FAIL | 21 failed, 154 passed; failures include browser research job, browser session pool, compat mapping, and Webwright integration |
| Research survey | `research_survey_pytest` | FAIL | 11 failed, 106 passed; API drift around `narrative_backend`, `require_golden_style`, missing `golden_style`/`audience_hygiene`, and shell command quoting failure with repo path containing spaces/parentheses |
| Research integration | `research_integration_pytest` | FAIL | 1 failed, 91 passed, 10 skipped; markdown report expected `## DeepResearch Quality Gates` but output used a different heading |
| Data plane and config | `config_data_plane_pytest` | BLOCKED/FAIL | 29 failed, 52 passed, 3 skipped; tests expect real `/Users/jamesyuan/Knowledge/_sources` and `_meta/source-manifest.jsonl` state |
| Benchmark adapter | `benchmark_pytest` | FAIL | 2 failed, 34 passed; TerminalBench adapter does not propagate expected missing prereqs and dry-run remains `pending` instead of `ok` |
| Full integration collection | `integration_pytest` | FAIL | collection fails on missing `youtube_001_subtitle_tracks` import in `test_youtube_e2e.py` |
| Livework | `livework_pytest` | FAIL | 2 failed, 188 passed; one failure attempts cwd `~/.solar/harness` literally/without an existing path |
| Remote dispatch | `orchestration_remote_pytest` | FAIL | 3 failed, 62 passed; remote CLI tests look for `/Users/jamesyuan/.solar/bin/solar-remote-dispatch` |
| AutoSci premerge | `autosci_premerge_gate` | FAIL | generated artifacts are tracked under `harness/artifacts/autosci/runs/*`; gate expected them to remain untracked |
| Intake/front door | `intake_entrypoint`, `script_check_solar_harness_front_door` | FAIL | isolated `intake --no-dispatch` expected one sprint status but found 0; front-door script expects old `Claude` wording while status output says `Codex` |
| Physical operator registry | `physical_operator_registry` | FAIL | `kb` selector falls back to generic builder with `operator_selector_no_match` |
| Definition of Done policy | `shell_definition_of_done` | FAIL | Solar `CLAUDE.md` lacks expected system DoD and evidence wording, while harness prompt/template checks pass |
| AI influence daily recency | `ai_influence_pytest` | FAIL | 4 failed, 46 passed; tests resolve literal `~/Solar/harness/scripts/ai_influence_daily.py` under the repo path |
| Root package smoke scripts | `root_smoke_skills_after_bun_install` | FAIL | `package.json` references missing `scripts/smoke-skills.ts` |
| Health monitor smoke | `root_smoke_health_monitor_after_bun_install` | BLOCKED | requires live dashboard server at `localhost:3721` and a Solar DB; not valid as a standalone command in this test run |

## Acceptance Group Status

| Master area | Status | Basis |
|---|---|---|
| AutoSci | PARTIAL | evaluator/dispatch fixtures pass; premerge artifact hygiene fails; full live autonomous intake was not executed |
| Benchmarks | FAIL | `benchmark_pytest` has TerminalBench adapter failures |
| Browser | PASS | `browser_pytest` passes |
| CI workflows | STATIC PASS ONLY | workflow YAML parses; remote CI jobs were not executed |
| CLI / front-door | FAIL | intake entrypoint and front-door smoke fail |
| Components | PASS STATIC | component manifests and shell syntax pass |
| Core TypeScript runtime | FAIL | root Bun suite still fails on TVS package/module resolution |
| Dashboard / desktop | PASS AFTER DEPS | desktop gates pass after scoped dependency setup |
| Harness graph orchestration | FAIL | graph pytest suite has collection/API failures |
| Harness Python/runtime library | PARTIAL | syntax/static/smoke subsets pass; runtime and graph suites fail |
| Hooks | PASS STATIC ONLY | shell syntax passes; hook behavior was not exhaustively exercised |
| Ingestion | PARTIAL | fixture/product smoke subsets pass; YouTube integration collection and data-plane source tests fail/block |
| Installer / packaging | PARTIAL PASS | pipx and installer contract pass; front-door smoke still fails |
| QA gates | PARTIAL | core imports pass after root Bun install; DoD, package smoke, and front-door gates fail |
| Research | FAIL | unit tests pass; survey and one integration report test fail |
| Runtime policies/operators | FAIL | runtime pytest has 21 failures |
| Skills | FAIL | package `smoke:skills` points to a missing script; skill wrapper behavior not fully signed off |
| Status server | PASS | full top-level status-server route suite passes |
| TVS | FAIL | UI engine test passes, but root Bun suite cannot resolve `tvs` modules |

## What Was Not Proven

- Full official AutoSci live run through intake was not executed to completion. Deterministic AutoSci evaluator/dispatch tests passed, but live autonomous operation through panes/LLM remains a separate end-to-end acceptance run.
- CI jobs were not run in GitHub Actions. Local evidence only includes YAML parsing and equivalent local subsets.
- Live network ingestion for arXiv, Semantic Scholar, Wikipedia, and arbitrary YouTube was not run. Tests were mostly fixture-based or executed with `AUTOSCI_DISABLE_NETWORK_FETCH=1`.
- Health monitor smoke was not proven because it requires a live dashboard server and a compatible Solar DB fixture.

## Recommended Next Fix Order

1. Fix front-door/intake regression and Codex/Claude wording drift in `scripts/check-solar-harness-front-door.sh`.
2. Fix graph orchestration API drift in `harness/lib/multi_task_runner.py` and related graph tests.
3. Fix root TVS module/package resolution so `bun test` can collect cleanly.
4. Fix research survey API drift and shell quoting for repo paths with spaces/parentheses.
5. Decide whether data-plane tests should use isolated fixtures or explicitly be classified as local-environment acceptance tests.
6. Clean AutoSci generated artifact tracking policy or update `test_autosci_phase_c_premerge_readiness.py` if the tracked artifacts are intentional.
7. Restore or remove stale package scripts such as `smoke:skills`.

