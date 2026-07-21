# Defects

Audit commit: `fb3f589b08e4167ac3cb0043fb3d59801a0f110b`

No P0 defect was observed. The isolated installer and doctor completed without touching the real home, and no unauthorized external side effect was executed.

## P1

### D-001 — `auto-chain.sh` is syntactically invalid

- Surface: `harness/auto-chain.sh:33`
- Evidence: `phase4_static_repo_checks`; `evidence/static-repo-checks.json`
- Reproduction: GNU Bash reports an unexpected `(` while parsing the doubly quoted `grep -E` pattern.
- Impact: the automatic chain runner cannot start, so a core workflow entrypoint is broken before runtime.

### D-002 — graph status suite cannot collect because an imported function is absent

- Surface: `harness/lib/multi_task_runner.py`; `harness/tests/graph/test_multi_task_runner_status_surface.py`
- Evidence: `phase4_pytest_matrix_installed_home`; `evidence/pytest-matrix-installed-home/graph.stdout.txt`
- Reproduction: `ImportError: cannot import name 'epic_child_status_lines'`.
- Impact: graph/epic child status behavior has no executable contract and the graph suite stops at collection.

### D-003 — approved AutoSci experiment commands break on workspace paths containing spaces

- Surface: AutoSci experiment allowlist/command normalization and lifecycle status propagation.
- Evidence: `phase4_scientific_evaluator_pytest_final` (103 pass, 1 fail), `phase4_scientific_experiment_inconclusive_repro`, and `phase4_autosci_plugin_pytest_final`.
- Reproduction: the allowlisted command is assembled from unquoted absolute paths under `Github Repos (On Git)`; approved local run/pilot actions remain `schema_only` or `inconclusive`, and the lifecycle converts the typed inconclusive boundary into an ordinary failure/exit 1 instead of the expected blocked exit 3.
- Impact: core approved experiment execution and continuation semantics are broken in a valid user path. Fixture evidence was not promoted to live parity.

### D-004 — root TypeScript/TVS test surface has unresolved package imports

- Surface: root `package.json`, `core/llm`, `core/ui`, `core/daemon/ui-watcher.ts`, and root TypeScript tests.
- Evidence: `phase4_bun_test`; `evidence/commands/phase4_bun_test.stderr.txt`
- Reproduction: imports such as `tvs`, `tvs/v2`, `tvs/v2/sdk`, and `tvs/termplane/*` cannot be resolved; root `package.json` does not declare a TVS dependency.
- Impact: the root Bun test command exits 2 and core TypeScript modules cannot be tested as packaged. The standalone UI engine sub-suite still reports 18 passing assertions.

## P2

### D-005 — research-survey CLI and implementation signatures have drifted

- Surface: `harness/lib/research/cli.py` and `harness/lib/research/survey/*`.
- Evidence: `phase4_pytest_matrix_installed_home`; 11 failures in the research-survey suite.
- Reproduction: `continue_survey_run()` rejects `narrative_backend`; `evaluate_survey()` rejects `require_golden_style`; expected `golden_style`, `audience_hygiene`, and `paper_trend_ids` fields are absent.
- Impact: auto-continue, strict evaluation, style gating, and paper enrichment are partially broken.

### D-006 — survey local-command backends do not quote executable paths

- Surface: `harness/lib/research/survey/chief_editor.py` and local-command writer backend.
- Evidence: `phase4_pytest_matrix_installed_home`; chief-editor and section-compiler failures.
- Reproduction: `/bin/sh` parses the `(` in the workspace path as shell syntax because command strings are executed with `shell=True` without path quoting.
- Impact: local command providers fail in ordinary paths containing spaces; exit-status reporting is consequently wrong.

### D-007 — AutoSci setup/parity route references missing `.env.example`

- Surface: AutoSci `$setup` and Phase 19 parity inventory.
- Evidence: `phase4_autosci_plugin_pytest_final`; three setup failures and two parity-inventory failures.
- Reproduction: parity evidence reports `items[25].missing_primary_tools must be empty: .env.example`; `.env.example` is not tracked at the locked commit.
- Impact: setup cannot produce the promised gated/readiness evidence, and parity inventory is failed.

### D-008 — AutoSci local ingest/provider proof contracts are incomplete

- Surface: PDF ingest and Paper Copilot file-provider CLI.
- Evidence: `phase4_autosci_plugin_pytest_final`.
- Reproduction: valid extracted PDF ingest returns `ingest_source_registration_incomplete`; file-provider runs remain `inconclusive`, and the runtime proof manifest remains `not_written`.
- Impact: deterministic local evidence cannot reach its documented completed/registered state.

### D-009 — browser-research compatibility APIs are absent

- Surface: `harness/lib/browser_job_runtime.py` and `chatgpt_conversation_ingest` compatibility boundary.
- Evidence: `phase4_pytest_matrix_installed_home`; 15 related runtime failures.
- Reproduction: missing `resolve_monthly_project_name`, `submit_research_job`, `BrowserSessionPool`, and `capture_for_research`; expected pool-lease evidence is not written.
- Impact: browser-research job submission, pooling, collection, and secret-scrubbing contracts are unavailable through the tested API.

### D-010 — physical-operator compatibility registry does not meet its schema contract

- Surface: physical operator configuration and runtime compatibility mapping.
- Evidence: `phase4_pytest_matrix_installed_home`; five `test_compat_mapping.py` failures.
- Reproduction: 67 entries are returned where 45 compatibility entries are expected; entries lack `compat_alias_for`, deprecation, or carrier-hint fields.
- Impact: operator compatibility routing is ambiguous or incomplete.

### D-011 — terminal-benchmark prerequisite and dry-run verdict semantics disagree

- Surface: `harness/lib/benchmark/terminal_bench_adapter.py`.
- Evidence: `phase4_pytest_matrix_installed_home`; 34 pass, 2 fail.
- Reproduction: missing prerequisites omit `harbor_cli`; an explicitly empty missing-prerequisite list still yields `pending` instead of `ok`.
- Impact: benchmark readiness/dry-run evidence can report the wrong prerequisite set or verdict.

### D-012 — isolated installed harness omits runtime sprint scaffolding

- Surface: installed `~/.solar/harness` layout and experience-memory E2E.
- Evidence: `phase5_install_isolated`, followed by `phase4_pytest_matrix_installed_home`; three experience failures.
- Reproduction: installed harness lacks `harness/sprints`, causing file creation/listing failures and preventing expected memory categories from appearing.
- Impact: the installer doctor is green but does not detect a runtime directory required by an important feature.

### D-013 — livework hook fail-open and path-expansion contracts are broken

- Surface: livework heartbeat/deadlock hooks.
- Evidence: `phase4_pytest_matrix_installed_home`; 182 pass, 8 fail.
- Reproduction: hook command strings fail to parse in the spaced workspace path, and literal `~/.solar` is used from an arbitrary working directory rather than expanded.
- Impact: hooks can return exit 2 instead of failing open and may not emit runtime events.

## P3

### D-014 — DeepResearch Markdown status omits its quality-gates section

- Evidence: `phase4_pytest_matrix_installed_home`; 91 pass, 10 skip, 1 fail in research integration.
- Reproduction: generated Markdown lacks `## DeepResearch Quality Gates`.
- Impact: an important status signal is hidden from the rendered report, while underlying execution continues.

### D-015 — file-provider URI is not RFC-safe in paths containing spaces

- Evidence: `phase4_autosci_plugin_pytest_final` novelty-route failure.
- Reproduction: expected `Path.as_uri()` percent-encoding is replaced by a raw `file:///...Github Repos (On Git)...` URI.
- Impact: downstream URI consumers may reject or misparse local provider evidence.

### D-016 — broad pytest discovery has import/package collisions

- Evidence: `phase4_pytest_matrix_installed_home`; 20 collection errors across graph, research, integration, and top-level tests.
- Reproduction: YouTube migration modules cannot be imported; nested `cli` test packages collide; graph has the separate D-002 import error.
- Impact: the repository's broad test command cannot collect all committed Python tests, reducing confidence even where narrower suites pass.

### D-017 — tracked `.json` evidence files are empty/malformed

- Evidence: `phase4_static_repo_checks`; four parse failures in committed artifact/tmp/test-state paths.
- Impact: generic JSON validation and consumers that treat tracked `.json` as machine-readable fail on these files.

### D-018 — missing-approval status taxonomy is inconsistent

- Evidence: `phase4_autosci_plugin_pytest_final`, `test_phase12_unapproved_external_experiment_is_failed_evidence`.
- Reproduction: implementation emits `inconclusive`, while the committed test expects `failed`; neither surface expresses the audit taxonomy's explicit `BLOCKED_EXPECTED` classification.
- Impact: approval-blocked behavior is difficult to aggregate consistently and may be mistaken for an ordinary failure.

### D-019 — environment-dependent data-plane tests fail rather than self-skip

- Evidence: `phase4_pytest_matrix_installed_home`; raw result 49 pass, 29 fail, 4 skip.
- Reproduction: tests assert real `~/Knowledge`, QMD index, canonical papers, and MinerU state that were intentionally not provisioned.
- Impact: CI/local results are noisy and can misclassify missing optional data as product regression. These 29 raw failures are classified `SKIPPED_ENV` in this audit, not product failures.

## Eligible-feature strict phase additions

The strict phase attempted all 107 selected targets. Existing D-003, D-006, D-007, D-010, D-011, D-016, and D-019 reproduced within this narrower selection.

### D-020 — research intake omits the required capability capsule ID (P2)

- Surface: `harness/tests/test_codex_pm_router.py::test_build_pm_intake_emits_capsule_plan_for_research_request`.
- Evidence: `evidence/eligible-full-phase-v3/junit/eligible-0069.xml`.
- Reproduction: the emitted research intake payload raises `KeyError: capability_capsule_id`.
- Impact: research intake artifacts do not satisfy the direct stable-ID/capsule contract.

### D-021 — graph dispatch hygiene/reuse APIs have drifted (P2)

- Evidence: `eligible-0027` and `eligible-0032` in `target-failure-summary.csv`.
- Reproduction: dirty-pane dispatch omits `pane_hygiene_dirty`; `multi_task_runner.tmux_window_records` is absent.
- Impact: pane safety and compact-session reuse cannot satisfy their committed tests.

### D-022 — actor/logical-operator registries and schemas disagree (P2)

- Evidence: `eligible-0062` and `eligible-0083` in `target-failure-summary.csv`.
- Reproduction: actor aliases and physical operator IDs are not bijective; new logical roles/capabilities are rejected by the tracked schema; a binding candidate is missing from the actor registry.
- Impact: capability routing and operator declarations cannot be validated consistently.

### D-023 — legacy ThunderOMLX knowledge alias is not resolved (P2)

- Evidence: `eligible-0081` in `target-failure-summary.csv`.
- Reproduction: mocked healthy Qwen runtime is rejected when `proxy_model=mini-thunderomlx-qwen36-knowledge`.
- Impact: knowledge health reports a false negative for the documented legacy alias.

### Strict-phase failing-target index

See `evidence/eligible-full-phase-v3/target-failure-summary.csv` for all raw failures, including collection failures already covered by D-016 and local-corpus failures classified under D-019.

## Post-NOT_RUN and approved-gate remediation additions

The exact feature-level failures are recorded in `feature-results.csv` and `evidence/codex-not-run-phase/remediation-feature-decisions.csv`. The following group common root causes; they do not count every failed feature as a separate defect.

| ID | Severity | Surface | Finding |
|---|---|---|---|
| D-024 | P1 | Survey, office, Obsidian, Calendar, browser write gates | The survey route writes wiki/archive state without approval, and four integration skills/policies expose write-ready behavior without an explicit human approval input. Only disposable fixtures were touched. |
| D-025 | P2 | Reset/check dry-run and missing-state routes | Missing scope defaults to mutation-capable behavior, dry-run is labeled completed, requested fixes are omitted, or inconclusive runs still report passed actions/create artifacts. |
| D-026 | P2 | Provider provenance and failure contracts | Several fetch/provider outputs omit query/parameter, retrieval time, limitations, or typed provider-failure evidence; arXiv collapses failure into an empty successful list. |
| D-027 | P2 | Health/audit/circuit routes | Read-only health routes can migrate/write state and their JSON omits required blocker/recommendation or severity separation. |
| D-028 | P2 | Office and browser-automation skills | The advertised office and browser packages are documentation/setup metadata only and ship no executable request/provider boundary. |
| D-029 | P2 | Codex operator | A missing `codex` executable raises an uncaught `FileNotFoundError` traceback and emits no typed failure artifact. |
| D-030 | P2 | Social browser capture | The stored social capture does not bind source URL and screenshot evidence into the timestamped raw/queue output contract. |
| D-031 | P2 | Method extraction and idea generation | Background text is invented into a method procedure instead of marked incomplete, and generated ideas omit explicit source-gap links. |
| D-032 | P2 | Model configuration CLI | `models set-main` mutates without `--apply`, and invalid aliases omit the allowed-option remedy. |
| D-033 | P2 | Capability/intent proof routes | Capability config, activation, certification, and intent route contracts have drifted; some missing rules return `ok: true` or declared capabilities are silently union-enriched. |
| D-034 | P2 | Miscellaneous direct contracts | Component listing is silent, wrappers cache the wrong HOME, an enhanced-search symbol is absent, and a spaced path breaks the local knowledge pipeline. |
| D-035 | P3 | QA taxonomy/integration mapping | Two `skills-md` rows describe no shipped surface, and the Obsidian manifest contains a developer-specific default path. |
| D-036 | P3 | CI diagnostics | Install/CI workflows omit required uploaded diagnostics and/or `GITHUB_STEP_SUMMARY` evidence for several atomic contracts. |
| D-037 | P2 | Release dry-run | `release/build.sh --dry-run` fails under `pipefail` because the tar listing is piped through `head`; the isolated real local build succeeds. |
| D-038 | P3 | Installer hygiene | Installer regression evidence reports missing `.env.example` plus incomplete ignore protection for env/key/runtime state patterns. |

No production fix was applied. No P0 event or real unauthorized external mutation was observed during the audit.
