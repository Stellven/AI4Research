# Complete QA Test Report - 2026-07-09

## Executive Decision

Status: **NO-GO**

This run attempted the remaining local automated test surface after the earlier repo-derived QA pass. The result is comprehensive enough to say the repository is **not release-green**. It is not accurate to say every product capability is verified, because live CI, real-account, real-network, and full autonomous LLM/pane workflows still require their own environments. It is accurate to say all discovered local pytest files, harness shell tests, root TypeScript tests, desktop tests, and root check/smoke gates were attempted or explicitly classified.

## Artifact Index

- Raw command logs and status files: `docs/testing/test-runs/20260709-qa-execution/`
- Command status table: `command_summary.tsv`
- Complete machine summary: `complete_test_summary.json`
- Per-file pytest matrix: `pytest_file_matrix_latest.tsv`
- Shell sweep matrix: `shell_sweep_latest.tsv`
- Root TypeScript matrix: `root_ts_individual_latest.tsv`
- Previous first-pass report: `qa_test_execution_report.md`

## What Was Tested

| Test Surface | Coverage Method | Result |
|---|---:|---|
| `harness/tests/**/*.py` | 482 pytest files executed individually with per-file logs | 395 pass, 87 nonzero, 0 timeouts |
| `harness/tests/**/*.sh` | 185 shell tests executed individually with isolated HOME and 60s timeout | 44 pass, 141 nonzero, 0 timeouts |
| Root `tests/*.test.ts` | 17 Bun/TypeScript tests executed individually | 1 pass, 16 nonzero |
| Desktop tests | Bootstrap, runtime-detect, gate, screens, functional, rapid-switch, frontend-scenarios, overhaul visual | PASS after scoped desktop dependency setup |
| Root scripts/gates | `check-*`, `smoke-*`, mempalace, install/front-door/status/UI gates | Mixed; key install/status gates pass, smoke install/status fail |
| Static validation | Python syntax, shell syntax, workflow YAML, component manifests, JSON manifests | PASS |
| AutoSci deterministic path | evaluator dispatch, product smoke, full scientific evaluator suite | PASS for deterministic local tests |
| Status server | full top-level route pytest suite and subset | PASS |

Raw status count, including duplicates and reruns: **780 command status files**, 496 exit 0, 284 nonzero.

## Matrix Summaries

### Pytest File Matrix

Latest per-source result after rerun normalization:

- Total files: 482
- Pass: 395
- Nonzero: 87
- Timeouts: 0

Failure classification:

| Classification | Count |
|---|---:|
| assertion or contract failure | 26 |
| other nonzero | 21 |
| missing file or fixture | 14 |
| missing module or import | 11 |
| API drift: missing attribute | 7 |
| collection error | 5 |
| API drift: type/signature | 3 |

Notable pytest failures:

- Graph orchestration: `multi_task_runner` missing APIs, pane hygiene/capability inference failures.
- Runtime operators: browser research job, browser session pool, compat mapping, Webwright integration.
- Data plane: missing `~/Knowledge/_sources`, `_meta/source-manifest.jsonl`, and QMD/source fixtures.
- Research survey: API drift around `narrative_backend`, `require_golden_style`, missing golden/audience fields, missing runtime artifacts.
- Research integration: missing/removed S6 helpers such as `write_s6_evidence_entry` and `compile_figures_to_dag`.
- AutoSci premerge: tracked generated artifacts violate the gate.
- Status/dashboard top-level files: several route/status tests fail outside the subset that already passed.
- AI influence/Youtube tests: multiple missing literal `~/Solar/...` fixtures or import paths.

### Shell Sweep

Executed all 185 discovered `harness/tests/**/*.sh` scripts with isolated HOME.

- Pass: 44
- Nonzero: 141
- Timeouts: 0

Failure classification:

| Classification | Count |
|---|---:|
| missing file or fixture | 80 |
| assertion or contract failure | 33 |
| other nonzero | 22 |
| missing module or import | 6 |

Interpretation: many shell tests are not self-contained under an isolated HOME and expect a particular installed harness/runtime layout. That is itself useful QA evidence: those tests cannot be treated as portable premerge gates without setup documentation or fixture repair.

### Root TypeScript Tests

Executed each root `tests/*.test.ts` individually.

- Total: 17
- Pass: 1 (`tests/ui-engine.test.ts`)
- Fail: 16

All 16 failures are module resolution failures for `tvs`, `tvs/v2`, `tvs/v2/display`, `tvs/v2/sdk`, `tvs/termplane/llm`, or `tvs/termplane/render/grid`.

## Important Passing Areas

| Area | Evidence |
|---|---|
| AutoSci deterministic evaluator/dispatch | `autosci_eval_dispatch_and_intake`, `autosci_product_smoke_subset`, `scientific_evaluators_full_pytest` |
| Desktop | all desktop browser/static gates passed after `desktop/npm ci` and local Playwright install |
| Status server core routes | `status_server_full_pytest`, `status_server_pytest_subset` |
| Packaging/installer subset | `pipx_distribution_pytest_harness`, `script_check_installer_contract`, `script_check_autosci_install_closure` |
| Static repo validation | `python_syntax_static`, `shell_syntax_static`, `workflow_yaml_static`, `component_manifest_static`, `physical_operators_json` |
| Research unit/core pieces | `research_unit_pytest`, many individual research unit pytest files |
| Browser/code-signal/influence units | `browser_pytest`, `code_signal_pytest`, `influence_pytest` |
| Root scripts subset | `check-daemons-*`, `check-installed-clean`, `check-kernel-gen`, `check-update`, `mempalace-check`, `check-privacy`, `check-solar-status`, `check-solar-ui-lite` |

## Release-Blocking Failures

1. **Root TypeScript/TVS is broken**
   - `bun test` and 16/17 individual root TS tests fail because `tvs` modules are unresolved.

2. **Graph orchestration is not green**
   - Directory suite and per-file tests show missing `multi_task_runner` APIs and graph/pane/capability behavior failures.

3. **Runtime operator layer is not green**
   - Runtime pytest has failures in browser research jobs, browser session pool, compat mapping, and Webwright integration.

4. **Research survey/integration is not green**
   - API drift, missing fields, command quoting issues, missing runtime artifacts, and missing S6 helpers.

5. **Data-plane tests require unrepaired environment/fixtures**
   - Tests expect real `~/Knowledge` source/index state. They should be converted to isolated fixtures or documented as environment acceptance tests.

6. **AutoSci premerge hygiene fails**
   - `harness/artifacts/autosci/runs/*` contains tracked generated artifacts, while the premerge gate expects them to remain untracked.

7. **Front-door/intake is still failing**
   - `test-intake-entrypoint.sh` expects one sprint status and finds zero.
   - `check-solar-harness-front-door.sh` expects old Claude wording while actual output uses Codex wording.

8. **Root package smoke scripts are stale**
   - `smoke:skills` points to missing `scripts/smoke-skills.ts`.
   - `smoke-core-policy.ts` calls missing `scripts/ensure-background-services.sh`.

9. **Install smoke fails in this environment**
   - `smoke-install.sh`, `smoke-install-matrix.sh`, and `smoke-status-server-e2e.sh` fail because the install flow attempts `pip install --user` from a virtualenv where user site packages are not visible.

10. **Shell harness tests are not portable**
   - 141/185 shell tests fail under isolated HOME, mostly due missing files/fixtures or installed-layout assumptions.

## Not Fully Proved

These are outside the completed local automated sweep and should not be marked PASS:

- Full official AutoSci live run through intake to autonomous completion.
- Real LLM pane behavior and owner-manual verification inside tmux panes.
- GitHub Actions CI jobs on hosted runners.
- Windows/WSL install workflow.
- Real network ingestion for arXiv, Semantic Scholar, Wikipedia, YouTube, social media, or live browser accounts.
- Tests requiring personal/local `~/Knowledge`, `~/.solar`, browser profiles, external secrets, or authenticated provider accounts.

## Dependency Work Performed

Desktop:

- Ran `npm ci` in `desktop/`.
- Installed local Playwright Chromium with `PLAYWRIGHT_BROWSERS_PATH=0`.
- Wrote project-local `desktop/node_modules`.
- npm reported one high-severity audit finding; no automatic fix was applied.

Root:

- Ran `bun install --frozen-lockfile`.
- Wrote project-local `node_modules`.
- `bun.lock` was not changed.

## Final Recommendation

Do not release from this state.

The highest-priority fixes are:

1. Restore/fix TVS module resolution.
2. Repair graph orchestration API drift around `multi_task_runner`.
3. Fix intake/front-door regression and Codex/Claude test wording drift.
4. Repair research survey and S6 integration API drift.
5. Convert data-plane and shell tests to isolated fixtures or explicitly document required installed runtime state.
6. Decide whether AutoSci generated artifacts should be tracked; then align the premerge gate with that policy.
7. Remove or restore stale root smoke scripts.

