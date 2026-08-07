# AutoSci Full-Parity Progress Report

Logged: 2026-07-01 EDT / 2026-07-02 UTC

## Work Location

| Field | Value |
|---|---|
| agent | Agent B |
| repo | `/Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar` |
| worktree | `/Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar/.worktrees/autosci-parity` |
| branch | `feature/autosci-full-parity-continuation` |
| BetterSolar | not modified |
| native AutoSci | read-only reference |

## Native AutoSci Files Inspected

| File | Purpose |
|---|---|
| `/Users/jamesyuan/Developer/Github Repos (On Git)/AutoSci/tools/research_wiki.py` | P1 OmegaWiki command parity reference |
| `/Users/jamesyuan/Developer/Github Repos (On Git)/AutoSci/i18n/en/skills/*/SKILL.md` | native skill inventory |
| `/Users/jamesyuan/Downloads/Prompt_B_AutoSci_Full_Parity_Agent.md` | Agent B execution contract |
| `/Users/jamesyuan/Downloads/AutoSci_Solar_Prioritized_Integration_Plan_2026-06-30.md` | updated prioritization plan |

## Completed This Slice

| Item | Status | Evidence |
|---|---|---|
| Safe worktree | ok | Used `.worktrees/autosci-parity` because the main OpenSolar checkout was dirty. |
| Baseline repair | ok | Fixed schema validation fallback so isolated product smokes pass without `jsonschema`. |
| Deterministic inventory | ok | Added `harness/tools/autosci_parity_inventory.py`; latest run reports 28 routes, 17 partial, 11 gated, 0 full, 0 missing. |
| P1 OmegaWiki parity slice | ok | Added native-style CLI tests for citation dedup, lifecycle transitions, checkpoint save/load/clear, context compilation, and open-question rebuild. |
| Lifecycle smoke fixture alignment | ok | Updated full-external lifecycle smoke tests to provide validated wiki idea/experiment evidence and structurally valid PDF fixtures instead of weakening report/publication gates. |
| P2 ideate writeback boundary | ok | Direct `/ideate --write` now reports Phase 4 as `pending_approval` without projecting candidate idea pages into durable `wiki/ideas/*.md` unless approval execution and final promotion evidence are both present. |
| P2 ideate promotion/growth boundary | ok | Final promotion now requires completed external novelty plus Review LLM evidence and emits an evidence-only growth report. |
| P2 ideate active dedup | ok | Existing non-failed wiki ideas are checked as active duplicates; overlapping candidates are filtered and excluded from selected writeback. |
| P2 ideate pilot/graph handoff gate | ok | Completed pilot handoff/runtime evidence can close phase 5; approved durable idea projection now requires full pipeline readiness and writes source/pilot graph edges into mutation proof. |
| P3 experiment runtime reports | ok | Approved `/exp-run` and `/exp-run --collect` now emit deploy/run report sidecars; seeded collected metrics emit mean/std aggregate evidence without promoting the route to full. |
| P4 paper-draft full tree | ok | `$paper-draft` now emits full local paper tree artifacts (`math_commands.tex`, standard section files, figures/tables dirs) plus a section evidence map. |
| P5 paper-compile audit report | ok | `$paper-compile` now emits `paper_compile_report_json`; no-tool approved execution is covered and remains inconclusive. |
| P6/P7 poster/rebuttal input parity | ok | Existing poster render/export tests are passing; `$rebuttal` now atomizes comma-separated raw review files supplied as the primary target. |
| P8 live provider env-gated tests | ok | Added default-skipped live provider tests for Review LLM provider proof, Semantic Scholar/novelty proof, remote status proof, remote launch proof, remote collect proof, and real TeX compile proof. |
| Shared handoff | ok | Added `docs/integrations/autosci/parity-to-unification-handoff.md`. |
| Gap matrix | ok | Added `docs/integrations/autosci/native-parity-gap-matrix.md`. |

## Files Changed

| Path | Purpose |
|---|---|
| `harness/evaluators/scientific/common.py` | Limited schema fallback when `jsonschema` is unavailable. |
| `tests/harness/evaluators/scientific/test_common_schema_fallback.py` | Regression coverage for missing `jsonschema` behavior. |
| `harness/tools/autosci_parity_inventory.py` | Prompt B parity inventory tool. |
| `tests/plugins/autosci/test_autosci_parity_inventory_tool.py` | Inventory field/action/capability tests. |
| `tests/plugins/autosci/test_research_wiki_native_parity_commands.py` | P1 OmegaWiki native command parity tests. |
| `tests/plugins/autosci/test_autosci_live_provider_env_gated.py` | P8 live-provider and remote-status acceptance tests, skipped unless explicit live-provider env gates are set. |
| `harness/plugins/autosci/bin/autosci_parity_bridge.py` | Semantic audit verification now supports explicit native/evidence roots for linked-worktree and external-artifact verification. |
| `tools/semantic_parity_runtime_proof.py` | Semantic runtime proof generation now resolves audit refs through explicit native/evidence roots. |
| `tools/semantic_parity_audit_matrix.py` | Full semantic assessment missing-ref checks now use the same explicit evidence-root resolver. |
| `.agents/skills/exp-pilot-eval/SKILL.md` | Corrected the wrapper side-effect policy from stale `dry_run_only` wording to `approval_required`, matching the route config and implementation. |
| `.agents/skills/exp-eval/SKILL.md` | Corrected the wrapper side-effect policy from stale `dry_run_only` wording to `approval_required`, matching the route config and implementation. |
| `harness/plugins/autosci/bin/autosci_bridge.py` | Approved claim verdict writeback now rebuilds `graph/open_questions.md` with native-compatible deterministic gap extraction. |
| `harness/artifacts/autosci/phase19/exp-pilot-eval-semantic-assessment-20260702.json` | Added explicit full semantic assessment for the approved `$exp-pilot-eval` pilot verdict/writeback path. |
| `harness/artifacts/autosci/phase19/semantic-audits-exp-pilot-eval-full/` | Generated `$exp-pilot-eval` full semantic audit and semantic proof manifest from the assessment. |
| `harness/artifacts/autosci/phase19/exp-eval-semantic-assessment-20260702.json` | Added explicit full semantic assessment for the approved `$exp-eval` experiment verdict/writeback path. |
| `harness/artifacts/autosci/phase19/semantic-audits-exp-eval-full/` | Generated `$exp-eval` full semantic audit and semantic proof manifest from the assessment. |
| `harness/artifacts/autosci/phase19/exp-eval-open-questions-proof-*` | Added isolated proof wiki/input fixtures for `$exp-eval` open-questions writeback parity. |
| `harness/artifacts/autosci/phase19/exp-pilot-run-approved-command-proof-inputs/` | Added phase19 allowlisted pilot command inputs for approved `$exp-pilot-run` runtime execution proof. |
| `harness/artifacts/autosci/phase19/exp-pilot-run-semantic-assessment-20260702.json` | Added explicit full semantic assessment for the approved `$exp-pilot-run` runtime/result/no-wiki path. |
| `harness/artifacts/autosci/phase19/semantic-audits-exp-pilot-run-full/` | Generated `$exp-pilot-run` full semantic audit and semantic proof manifest from the assessment. |
| `.agents/skills/ingest/SKILL.md` | Clarified that the base route config remains partial, while root-aware parity reports `$ingest` full when the Phase 19 semantic audit/proof is loaded. |
| `.agents/skills/exp-status/SKILL.md` | Corrected stale wrapper coverage from `full` to `partial` and documented the live remote polling blocker. |
| `harness/artifacts/autosci/phase19/ingest-semantic-assessment-20260702.json` | Added explicit full semantic assessment for source-prepared `$ingest` through final Solar workspace wiki registration. |
| `harness/artifacts/autosci/phase19/semantic-audits-ingest-full/` | Generated `$ingest` full semantic audit and semantic proof manifest from the assessment. |
| `harness/artifacts/autosci/phase19/autosci_feature_parity.ingest.json` | Captured the single-route root-aware `$ingest` parity evidence after semantic full audit loading. |
| `harness/plugins/autosci/config/feature_parity_routes.v1.json` | Reworded the `$ingest` limitation from `fixture-leakage guards` to `sample-content leakage guards` so dynamic full coverage does not look fixture-only; no static route promotion. |
| `harness/plugins/autosci/config/feature_parity_routes.v1.json` | `$exp-pilot-run` limitation now states approved command runtime evidence is supported and wiki verdict/writeback is delegated to `$exp-pilot-eval`; no route was promoted. |
| `tests/plugins/autosci/test_phase19_parity_bridge.py` | Added semantic audit evidence-root portability coverage. |
| `tests/plugins/autosci/test_semantic_parity_runtime_proof.py` | Added semantic proof evidence-root portability coverage. |
| `tests/plugins/autosci/test_semantic_parity_audit_matrix.py` | Added semantic matrix evidence-root portability coverage. |
| `tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py` | Full-external lifecycle smoke fixtures now satisfy current paper-plan and publication gates. |
| `harness/plugins/autosci/bin/autosci_skill_shim.py` | `/ideate --write` is passed to action envelopes and direct ideate idea-page projection is approval-gated. |
| `harness/plugins/autosci/bin/autosci_workspace_projector.py` | Added an `include_idea_pages` projection switch so evidence summaries can remain visible without writing durable candidate pages. |
| `harness/plugins/autosci/bin/autosci_bridge.py` | `/ideate` promotion boundary validates completed novelty/review evidence and writes `ideate_growth_report.json`; approved experiment run/collect now writes deploy/run/multi-seed aggregate reports; `/paper-draft` writes full tree and section evidence map artifacts; `/paper-compile` writes a compile audit report sidecar; `/rebuttal` accepts comma-separated raw review file targets. |
| `harness/plugins/autosci/backends/idea_source.py` | Added active/proposed idea overlap detection alongside failed-idea banlist checks. |
| `docs/integrations/autosci/native-parity-gap-matrix.md` | Current parity matrix and remaining gaps. |
| `docs/integrations/autosci/parity-to-unification-handoff.md` | Shared interface handoff for Agent A/future merge work. |
| `docs/integrations/autosci/full-parity-progress-report.md` | This report. |
| `docs/integrations/autosci/phase19-progress-log.md` | Appended issue log for this continuation slice. |

## Tests Run

| Command | Result |
|---|---|
| `env PYTHONPATH=harness harness/bin/python3 -m pytest -q tests/harness/evaluators/scientific/test_common_schema_fallback.py` | ok: 3 passed |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest -q tests/plugins/autosci/test_autosci_parity_inventory_tool.py` | ok: 2 passed |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest -q tests/plugins/autosci/test_research_wiki_native_parity_commands.py` | ok: 4 passed |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest -q tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py::test_scientific_lifecycle_smoke_accepts_combined_full_external_evidence tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py::test_scientific_lifecycle_smoke_executes_approved_publication_compile tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py::test_scientific_lifecycle_smoke_can_resume_external_blocked_nodes` | ok: 3 passed |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest -q harness/plugins/autosci/tests tests/harness/evaluators/scientific` | warn in sandbox: 332 passed, 3 failed due localhost socket bind permission |
| elevated rerun of socket-bound tests: novelty HTTP provider, Review LLM OpenAI-compatible provider, approved SMTP delivery | ok: 3 passed |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest -q tests/harness/integration/test_autosci_routes_list.py tests/harness/integration/test_autosci_cli_dispatch.py tests/harness/integration/test_autosci_ingest_demo.py tests/harness/integration/test_autosci_review_demo.py tests/harness/integration/test_autosci_research_scheduler_demo.py tests/harness/integration/test_autosci_artifact_root.py` | ok: 6 passed |
| `env PYTHONPATH=harness /Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar/.venv/bin/python -m pytest -q tests/plugins/autosci/test_autosci_skill_shim.py -k 'ideate'` | ok: 9 passed, 142 deselected |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest -q tests/plugins/autosci/test_autosci_skill_shim.py::test_autosci_skill_shim_runs_research_pipeline` | ok: 1 passed |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest -q tests/plugins/autosci/test_autosci_skill_shim.py -k 'novelty'` | ok: 13 passed |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest -q tests/plugins/autosci/test_autosci_skill_shim.py -k 'paper_draft or paper-draft or workspace_projection'` | ok: 2 passed |
| `env PYTHONPATH=harness harness/bin/python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest -q tests/plugins/autosci/test_autosci_skill_shim.py -k 'exp_run or exp_status or exp_collect or exp_design'` | ok: 24 passed |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest -q harness/plugins/autosci/tests tests/harness/evaluators/scientific` | ok: 339 passed |
| `git -c maintenance.auto=false -c gc.auto=0 fsck --connectivity-only --no-dangling` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest -q tests/plugins/autosci/test_autosci_skill_shim.py -k 'paper_draft or paper-draft or paper_compile or paper-compile'` | ok: 13 passed |
| P4 full rerun: `env PYTHONPATH=harness harness/bin/python3 -m pytest -q harness/plugins/autosci/tests tests/harness/evaluators/scientific` | ok: 339 passed |
| `/Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar/.venv/bin/python -m py_compile harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py` | ok |
| `/Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar/.venv/bin/python -m pytest -q tests/plugins/autosci/test_autosci_skill_shim.py -k 'paper_compile'` | ok: 12 passed, 135 deselected |
| `/Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar/.venv/bin/python -m pytest -q tests/plugins/autosci/test_autosci_skill_shim.py -k 'rebuttal or poster'` | ok: 8 passed, 140 deselected |
| Step 11 product integration rerun: `env PYTHONPATH=harness /Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar/.venv/bin/python -m pytest -q tests/harness/integration/test_autosci_routes_list.py tests/harness/integration/test_autosci_cli_dispatch.py tests/harness/integration/test_autosci_ingest_demo.py tests/harness/integration/test_autosci_review_demo.py tests/harness/integration/test_autosci_research_scheduler_demo.py tests/harness/integration/test_autosci_artifact_root.py` | ok: 6 passed |
| P6/P7 full rerun: `env PYTHONPATH=harness /Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar/.venv/bin/python -m pytest -q harness/plugins/autosci/tests tests/harness/evaluators/scientific` | ok: 341 passed |
| P6/P7 smoke pollution cleanup | ok: reverted `harness/artifacts/autosci/workspace/wiki/canvases/knowledge-map.canvas` and `harness/artifacts/autosci/workspace/wiki/log.md` |
| P6/P7 `git diff --check` and `git -c maintenance.auto=false -c gc.auto=0 fsck --connectivity-only --no-dangling` | ok |
| P6/P7 parity inventory rerun | ok: 28 routes, 17 partial, 11 gated, 0 full, 0 missing |
| `/Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar/.venv/bin/python -m pytest -q tests/plugins/autosci/test_autosci_live_provider_env_gated.py` | ok: 6 skipped by design |
| P8 product integration rerun: `env PYTHONPATH=harness /Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar/.venv/bin/python -m pytest -q tests/harness/integration/test_autosci_routes_list.py tests/harness/integration/test_autosci_cli_dispatch.py tests/harness/integration/test_autosci_ingest_demo.py tests/harness/integration/test_autosci_review_demo.py tests/harness/integration/test_autosci_research_scheduler_demo.py tests/harness/integration/test_autosci_artifact_root.py` | ok: 6 passed |
| P8/P2 full module rerun: `env PYTHONPATH=harness /Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar/.venv/bin/python -m pytest -q harness/plugins/autosci/tests tests/harness/evaluators/scientific` | ok: 344 passed, 6 skipped |
| P5 combined runtime/submission regression: `/Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar/.venv/bin/python -m pytest -q tests/plugins/autosci/test_autosci_skill_shim.py::test_autosci_skill_shim_paper_compile_approved_runtime_submission_audit_closes_boundaries` | ok: 1 passed |
| P5 paper-compile subset after combined closure: `/Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar/.venv/bin/python -m pytest -q tests/plugins/autosci/test_autosci_skill_shim.py -k 'paper_compile or paper-compile'` | ok: 13 passed, 136 deselected |
| Sandbox-restricted full module rerun | warn: 339 passed, 6 skipped, 3 failed from local loopback bind denial; rerun with loopback permission passed. |
| P8 smoke pollution cleanup | ok: reverted `harness/artifacts/autosci/workspace/wiki/canvases/knowledge-map.canvas` and `harness/artifacts/autosci/workspace/wiki/log.md` |
| P8/P2 parity inventory rerun | ok: 28 routes, 17 partial, 11 gated, 0 full, 0 missing |
| P8 git safety cleanup | ok: quarantined invalid `.git/refs/.DS_Store` to `/Users/jamesyuan/Desktop/OpenSolar_git_ref_quarantine_20260702_111754/.DS_Store.refs`; repeated Finder ref pollution was later quarantined to `/Users/jamesyuan/Desktop/OpenSolar_git_ref_quarantine_20260702_121720/.DS_Store.refs` and `/Users/jamesyuan/Desktop/OpenSolar_git_ref_quarantine_20260702_130807/.DS_Store.refs`; `git fsck --connectivity-only --no-dangling` passed |
| P8 `git diff --check` | ok |
| Semantic audit portability: `env PYTHONPATH=harness /Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar/.venv/bin/python -m pytest -q tests/plugins/autosci/test_phase19_parity_bridge.py` | ok: 20 passed |
| Semantic audit portability: `env PYTHONPATH=harness /Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar/.venv/bin/python -m pytest -q tests/plugins/autosci/test_semantic_parity_runtime_proof.py tests/plugins/autosci/test_semantic_parity_audit_matrix.py` | ok: 7 passed |
| Semantic audit portability real-root smoke | ok: historical `ask` semantic audit verifies with `AUTOSCI_REPO` and `SOLAR_AUTOSCI_EVIDENCE_ROOTS`, reporting `semantic_full_count=1`; standalone runtime proof CLI writes a proof manifest. |
| Root-aware detailed parity inventory | ok: with `AUTOSCI_REPO` and `SOLAR_AUTOSCI_EVIDENCE_ROOTS`, detailed inventory reports `full_count=7`, `partial_count=10`, `gated_count=11`, `semantic_full_count=15`, `semantic_partial_count=13`, runtime proof counts `{not_required: 5, pending: 0, supplied: 1, verified: 22}`. |
| Root-aware ordinary feature parity gate | ok: `/tmp/autosci_detailed_inventory_with_roots.json` passes the ordinary gate; warnings correctly state that non-full and semantic-partial routes remain authoritative. |
| `$exp-pilot-eval` semantic full audit generation | ok: `semantic_parity_audit_matrix.py generate --skill exp-pilot-eval` produced `semantic_full_count=1`; `semantic_parity_runtime_proof.py from-audit` wrote the semantic proof manifest. |
| `$exp-pilot-eval` route and global gates | ok: single-route gate passed with `semantic_parity=full`, `proof_level=E3`, `coverage_status=gated`; root-aware global inventory now reports `semantic_full_count=16`, `semantic_partial_count=12`, and ordinary gate passes with expected non-full warnings. |
| `$exp-pilot-eval` focused regression | ok: `test_autosci_skill_shim.py -k 'pilot_eval or exp_pilot_eval'` passed 2 tests, 149 deselected. |
| Semantic tooling regression after `$exp-pilot-eval` audit | ok: phase19 parity bridge + semantic proof/matrix tests passed 27 tests. |
| Product integration smoke after `$exp-pilot-eval` audit | ok: route list, CLI dispatch, ingest/review demos, scheduler demo, and artifact-root smoke passed 6 tests. |
| JSON/diff/fsck after `$exp-pilot-eval` audit | ok: new assessment/audit/proof JSON parse with `jq empty`; `git diff --check` and `git fsck --connectivity-only --no-dangling` passed. |
| `$exp-eval` isolated approved proof run | ok: action passed with `final_verdict_ready=true` and generated `graph/open_questions.md` in the phase19 proof wiki. |
| `$exp-eval` semantic full audit generation | ok: `semantic_parity_audit_matrix.py generate --skill exp-eval` produced `semantic_full_count=1`; `semantic_parity_runtime_proof.py from-audit` wrote the semantic proof manifest. |
| `$exp-eval` route and global gates | ok: single-route gate passed with `semantic_parity=full`, `proof_level=E3`, `coverage_status=gated`; root-aware global inventory now reports `semantic_full_count=17`, `semantic_partial_count=11`, and ordinary gate passes with expected non-full warnings. |
| `$exp-pilot-run` approved command proof run | ok: `codex-exp-pilot-run-approved-command-proof-20260702` executed an allowlisted pilot command, wrote runtime/result/stdout/stderr/report artifacts, and did not emit wiki mutation artifacts. |
| `$exp-pilot-run` semantic full audit generation | ok: `semantic_parity_audit_matrix.py generate --skill exp-pilot-run` produced `semantic_full_count=1`; `semantic_parity_runtime_proof.py from-audit` wrote the semantic proof manifest. |
| `$exp-pilot-run` focused regression | ok: approved native command test passed and adjacent `$exp-run` approved native command regression still passed. |
| `$exp-pilot-run` route and global gates | ok: root-aware global inventory now reports `semantic_full_count=18`, `semantic_partial_count=10`, and ordinary gate passes with expected non-full warnings. |
| `$ingest` semantic full audit generation | ok: `semantic_parity_audit_matrix.py generate --skill ingest` produced `semantic_full_count=1`; `semantic_parity_runtime_proof.py from-audit` wrote the semantic proof manifest. |
| `$ingest` route and global inventory | ok: single-route root-aware parity reports `coverage_status=full`, `semantic_parity=full`, `proof_level=E3`, `runtime_proof_status=not_required`; global root-aware inventory now reports `full_count=8`, `partial_count=7`, `gated_count=13`, `semantic_full_count=19`, `semantic_partial_count=9`. |
| `$ingest` / `$exp-run` / `$exp-status` focused regression | ok: 30 passed, 122 deselected. |
| Env-gated live provider/remote hooks | ok: 6 skipped by design; skipped tests are acceptance hooks, not live proof. |
| Final semantic tooling and product smokes | ok: semantic tooling 27 passed; product AutoSci route/CLI/ingest/review/scheduler/artifact-root smokes 6 passed. |
| Final parity gate and Git safety | ok: root-aware inventory gate passed with expected non-full warnings; `git diff --check` passed; `git fsck --connectivity-only --no-dangling` passed after quarantining `.git/refs/.DS_Store` to `/private/tmp/OpenSolar_git_ref_quarantine_20260702_ingest_exp_status/.DS_Store.refs`. |

## Remaining Partial/Gated Routes

| Area | Status | Blocker |
|---|---|---|
| all routes | not full | Lightweight Prompt B inventory still reports `full_count=0`; no route was promoted in config. Root-aware detailed inventory recognizes 8 full routes and 19 semantic-full routes from historical/current semantic audits, but global full parity remains incomplete. |
| provider/live paths | pending | Env-gated tests now exist, but proof remains pending until explicitly run with real provider credentials/endpoints and accepted through route promotion policy. |
| remote experiments | pending | Local approved command and remote-helper report evidence is improved; real external SSH/provider config, execution, and live collection proof remain pending. |
| paper compile | pending | Compile audit report, no-tool inconclusive coverage, and a combined deterministic approved-runtime/PDF/submission-audit regression are wired; full parity still needs live or accepted real-toolchain proof through route promotion policy. |
| poster/rebuttal | pending | Poster/rebuttal local artifacts and input parsing are improved; full parity still needs end-to-end accepted Review LLM/provider proof and approved publication/submission audit evidence. |
| Review LLM paths | pending | Need persisted Review LLM/model request-response or supplied review evidence. |

## Notes

- No route was promoted to `full`.
- No generated artifact under `harness/artifacts` was committed.
- The latest full-suite pass required loopback permission because local provider/SMTP regression tests bind temporary `127.0.0.1` ports.
- The schema fallback is intentionally limited; it checks required top-level fields, required outputs, and provenance fields only when `jsonschema` is unavailable.
- The inventory tool is deterministic reporting and must not be used as a shortcut for route promotion.
- Full-external lifecycle tests now pass by supplying the evidence current gates require: validated idea graph, Review LLM evidence, source/citation evidence, and structurally valid compile/PDF evidence.
- Localhost socket tests require unsandboxed execution in this Codex environment because the sandbox blocks binding `127.0.0.1:0`.
- Direct `/ideate` candidate pages are treated as durable wiki memory and therefore require explicit approval execution; unapproved runs still publish evidence summaries under `wiki/outputs/ideas.md`.
- `/ideate` promotion readiness now distinguishes evidence references from completed evidence; path-only novelty/review references are insufficient.
- Approved direct `/ideate` idea projection now emits a wiki mutation runtime proof; unapproved or non-promoted candidates remain evidence-only.
- Approved direct `/ideate` idea projection now also requires `ideate_pipeline_report.pipeline_ready`; missing pilot handoff/runtime evidence blocks durable idea pages unless `--skip-pilot` is explicit.
- Approved direct `/ideate` idea projection now writes `generated_from` and `has_pilot_handoff` graph edges and includes `wiki/graph/edges.jsonl` in the mutation proof.
- Active/proposed idea dedup is token-overlap based and conservative; Review LLM/external novelty evidence is still required for final promotion.
- Experiment deploy/run/multi-seed reports are audit sidecars only; they do not bypass `experiment_run_final_runtime_audit_boundary` or promote `/exp-run` to `full`.
- Full-suite smoke pollution in `harness/artifacts/autosci/workspace/wiki/canvases/knowledge-map.canvas` and `harness/artifacts/autosci/workspace/wiki/log.md` was reverted after verification.
- `/paper-draft` full tree artifacts improve local manuscript structure only; final manuscript readiness still requires source evidence, Review LLM proof, and compile/PDF handoff.
- `/paper-compile` report artifacts are audit summaries only; missing TeX tools, missing PDF inspection, or missing submission audit must remain inconclusive.
- `/rebuttal` comma-separated target parsing is path-only; pasted reviewer prose with commas is preserved as one direct text source unless each comma-separated value looks path-like.
- `$exp-pilot-run` semantic full is proven for the approved pilot runtime execution/result path; verdict and wiki writeback remain delegated to `$exp-pilot-eval`.
- `$ingest` semantic full is proven for source-prepared ingestion through final Solar workspace wiki registration when the Phase 19 audit/proof is loaded; the static route config remains unpromoted to avoid no-audit full inference.
- `$exp-status` wrapper coverage was corrected to `partial`; live SSH/provider polling and distributed exactly-once remote collection are still real blockers.
- P8 live-provider tests are opt-in only: set `AUTOSCI_LIVE_PROVIDER_TESTS=1` plus the route-specific flag before running them against real providers, remote commands, or real TeX executors.
- In this worktree, `harness/bin/python3` points at a missing worktree `.venv`; use the main OpenSolar `.venv/bin/python` for pytest until a local worktree venv is restored.
- When verifying historical semantic audits from a linked worktree, set `AUTOSCI_REPO` to the native AutoSci checkout and `SOLAR_AUTOSCI_EVIDENCE_ROOTS` to the artifact root containing ignored smoke-run outputs; missing evidence still blocks full semantic verification.
