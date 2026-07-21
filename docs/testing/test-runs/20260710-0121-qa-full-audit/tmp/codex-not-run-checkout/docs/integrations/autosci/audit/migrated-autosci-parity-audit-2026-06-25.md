# Solar AutoSci Migrated Runtime Parity Audit - 2026-06-25

## Executive summary

```text
╔════════════════════════════════╦════════════════════════════════════════════════════════════════════╗
║ Field                          ║ Value                                                              ║
╠════════════════════════════════╬════════════════════════════════════════════════════════════════════╣
║ Final verdict                  ║ failed                                                             ║
║ Full parity                    ║ no                                                                 ║
║ Canonical AutoSci remote        ║ https://github.com/skyllwt/AutoSci.git                            ║
║ Canonical AutoSci commit        ║ 6f5a9f6ed877d5c52e87620d79ef7738ff213989                           ║
║ Canonical branch/status         ║ main / clean                                                       ║
║ Fork candidate                  ║ Coconut-ch1ken/AutoSci @ 71469e89... / dirty, not baseline         ║
║ OpenSolar commit                ║ 721e6eee4eff39cd3a35cf7d240a67f2d493864f                           ║
║ OpenSolar branch/status         ║ feature/autosci-solar-native / dirty                              ║
║ Audit timestamp                 ║ 2026-06-25T16:26:58Z                                               ║
║ Audit root                      ║ /tmp/solar-autosci-parity-audit-20260625T122123-rerun                    ║
╚════════════════════════════════╩════════════════════════════════════════════════════════════════════╝
```

Observed fact: this rerun used the corrected prompt snapshot `/tmp/solar-autosci-parity-audit-20260625T122123-rerun/source_snapshots/solar_autosci_strict_parity_audit_prompt.md`. The canonical baseline was verified with `git remote -v`, HEAD, branch, and porcelain status in `/tmp/solar-autosci-parity-audit-20260625T122123-rerun/commands/002-canonical-autosci-baseline`. The fork candidate was verified separately in `/tmp/solar-autosci-parity-audit-20260625T122123-rerun/commands/003-fork-autosci-candidate` and was not used as original behavior truth.

Observed fact: current route config no longer declares any `full` routes: route coverage is `partial=18`, `gated=10`. This fixes the earlier class of explicit `full` overclaim, but does not establish runtime parity.

Inference: the current migrated runtime is still not full parity. SkillGen ingestion fails, Review LLM review fails, real experiment execution is gated and unexecuted, paper compile does not produce PDF, and integrated `$research` does not complete/resume an end-to-end pipeline.

## Scope actually executed

- Re-read corrected strict audit prompt and required docs; snapshots saved under `/tmp/solar-autosci-parity-audit-20260625T122123-rerun/source_snapshots`.
- Re-verified OpenSolar, canonical AutoSci, and fork AutoSci Git state.
- Ran isolated Workspace A/B/C shim tests with `HARNESS_DIR=/tmp/solar-autosci-parity-audit-20260625T122123-rerun/workspaces/...`.
- Did not modify code, install dependencies, commit, push, start servers, approve gates, run remote jobs, or incur API cost.

## Native command parity matrix

| command | original syntax | migrated syntax | parser support | native execution | fallback | side effect executed | classification | evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| setup | /setup | text `$setup` | accepted | gated setup_status only | no | no | gated_unexecuted | /tmp/solar-autosci-parity-audit-20260625T122123-rerun/commands/010-workspace-a-cli-and-flags/A01-setup |
| init | /init <topic> --no-introduction | text `$init ... --no-introduction` | accepted | partial/schema_only source manifest | no | no | schema_only | /tmp/solar-autosci-parity-audit-20260625T122123-rerun/commands/010-workspace-a-cli-and-flags/F01-init-no-intro |
| ingest | /ingest <pdf> [--discover] [--visualize] | text `$ingest ...`; skill ingest --paper | accepted | failed PDF parse; no SkillGen facts extracted | no fixture abstract now; parse-failure section | no | failed | /tmp/solar-autosci-parity-audit-20260625T122123-rerun/commands/011-skillgen-pdf-oracle-and-ingest |
| ask | /ask <question> | text `$ask ...` | accepted | partial/schema_only query capture | no | no | schema_only | /tmp/solar-autosci-parity-audit-20260625T122123-rerun/commands/011-skillgen-pdf-oracle-and-ingest/Q01-ask |
| ideate | /ideate <topic> --max-ideas ... | text `$ideate ... --max-ideas 3` | accepted | partial local deterministic candidate/evaluation | local surrogate | workspace projection only | native_partial | /tmp/solar-autosci-parity-audit-20260625T122123-rerun/commands/012-components-and-integrated/B05-ideate-full |
| novelty | /novelty <idea> --verbose --write | text `$novelty ...` | accepted | partial; external evidence unavailable | local surrogate | no validated writeback | native_partial | /tmp/solar-autosci-parity-audit-20260625T122123-rerun/commands/012-components-and-integrated/B06-novelty-full |
| review | /review <idea> --difficulty --focus | text `$review ...` | accepted | failed without resolved artifact/Review LLM | local surrogate disclosed | no | failed | /tmp/solar-autosci-parity-audit-20260625T122123-rerun/commands/012-components-and-integrated/B07-review-hard |
| exp-run | /exp-run <slug> --review --env local | text `$exp-run ...` | accepted | gated; no command executed; outcome inconclusive | no fixture execution; approval absent | no | gated_unexecuted | /tmp/solar-autosci-parity-audit-20260625T122123-rerun/commands/012-components-and-integrated/B11-exp-run-deploy |
| exp-status | /exp-status --pipeline <slug> | text `$exp-status --pipeline ...` | accepted | partial action_count=0 | no | no | native_partial | /tmp/solar-autosci-parity-audit-20260625T122123-rerun/commands/012-components-and-integrated/C02-exp-status-pipeline |
| survey | /survey <slug> --format latex | text `$survey ... --format latex` | rejected | parser error | N/A | no | failed | /tmp/solar-autosci-parity-audit-20260625T122123-rerun/commands/012-components-and-integrated/B15-survey |
| paper-compile | /paper-compile paper/ --fix|--checklist | text `$paper-compile ...` | accepted | gated/schema_only; no PDF | no | no | gated_unexecuted | /tmp/solar-autosci-parity-audit-20260625T122123-rerun/commands/012-components-and-integrated/B18-paper-compile-fix |
| research | /research <dir> --venue; --start-from | text `$research ...` | accepted | gated single workflow artifact; no pipeline progress/report | no | no | gated_unexecuted | /tmp/solar-autosci-parity-audit-20260625T122123-rerun/commands/012-components-and-integrated/C01-research |

## Evidence / artifact matrix

| stage | expected artifact | observed artifact | content valid | state valid | evidence path | classification |
| --- | --- | --- | --- | --- | --- | --- |
| setup | .venv/.env/.claude/CLAUDE.md | workflow_evolution.setup.json only | partial | no real setup writes | /tmp/solar-autosci-parity-audit-20260625T122123-rerun/commands/010-workspace-a-cli-and-flags/A01-setup | gated_unexecuted |
| init | checkpoints + wiki scaffold | literature discovery/init sidecar only | no | no full wiki scaffold | /tmp/solar-autosci-parity-audit-20260625T122123-rerun/commands/010-workspace-a-cli-and-flags/F01-init-no-intro | schema_only |
| check | red/yellow/blue counts | not rerun dynamically | N/A | N/A | N/A | missing |
| visualize | wiki graph/canvas + web UI | gated visualizer evidence; OpenSolar lacks original tools/app paths | no | no real UI health | /tmp/solar-autosci-parity-audit-20260625T122123-rerun/commands/014-web-ui-static-check | gated_unexecuted |
| ideate | wiki/ideas + IDEA_REPORT + Pilot Spec | idea_candidate/idea_evaluation only | partial | no pilot spec | /tmp/solar-autosci-parity-audit-20260625T122123-rerun/commands/012-components-and-integrated/B05-ideate-full | native_partial |
| novelty | novelty score + external sources + reviewer | local evaluation only | partial | no independent reviewer/source ids | /tmp/solar-autosci-parity-audit-20260625T122123-rerun/commands/012-components-and-integrated/B06-novelty-full | native_partial |
| review | Review Report | failed review_artifact | no | no | /tmp/solar-autosci-parity-audit-20260625T122123-rerun/commands/012-components-and-integrated/B07-review-hard | failed |
| pilot_run | pilot code/log/results | schema_only gated pilot result | no | no real execution | /tmp/solar-autosci-parity-audit-20260625T122123-rerun/commands/012-components-and-integrated/B08-exp-pilot-run | gated_unexecuted |
| experiment_deploy | code/log/running state | approval-gated inconclusive result | no | not running | /tmp/solar-autosci-parity-audit-20260625T122123-rerun/workspaces/workspace-b-components/artifacts/autosci/runs/exp-run-14fa71b9f9/experiment_result.json | gated_unexecuted |
| experiment_collect | results/seed_*.json + completed state | schema_only monitor/collect evidence | no | no | /tmp/solar-autosci-parity-audit-20260625T122123-rerun/commands/012-components-and-integrated/B13-exp-run-collect | schema_only |
| paper_draft | paper/main.tex and sections | action_count=0 | no | no | /tmp/solar-autosci-parity-audit-20260625T122123-rerun/commands/012-components-and-integrated/B16-paper-draft | missing |
| paper_compile | paper/main.pdf | gated/schema_only; no PDF | no | no | /tmp/solar-autosci-parity-audit-20260625T122123-rerun/commands/012-components-and-integrated/B18-paper-compile-fix | gated_unexecuted |
| integrated_pipeline | pipeline-progress.md + PIPELINE_REPORT.md | gated workflow artifacts only | no | no completed pipeline | /tmp/solar-autosci-parity-audit-20260625T122123-rerun/commands/012-components-and-integrated/C01-research | gated_unexecuted |

## Missing-block matrix

| block | status | evidence-backed note |
| --- | --- | --- |
| skill-specific CLI | warn | Many original flags now parse, but `--format latex` still fails and several parsed flags produce action_count=0 or gated/no-op semantics. |
| wiki state resolver | warn | Resolver is read-only; target misses are recorded; no real mutation/index rebuild verified. |
| real ideate pipeline | warn | No dual-model brainstorm, landscape scan, Review LLM, or pilot spec. |
| novelty/review gates | error | No Semantic Scholar/DeepXiv/live search evidence or independent Review LLM acceptance. |
| pilot lifecycle | error | Gated/schema_only; no pilot code execution/result JSON. |
| experiment lifecycle | error | Approval gate is truthful, but no real planned->running->completed flow executed. |
| publication compile | error | No draft LaTeX/PDF compile artifact. |
| source evidence | error | SkillGen PDF source text not extracted by migrated ingest. |
| route truthfulness | warn | No `full` route claims remain; remaining issue is missing primary_tools/native paths and action_count=0 routes. |
| web UI | error | Original tools/serve.py, tools/visualize.py, app files missing in OpenSolar tree. |
| resume/recovery | error | `--start-from` parses but only emits gated workflow evidence; no resume state/progress report. |

## Regression matrix

| area | observed still working | remaining gap | status |
| --- | --- | --- | --- |
| Codex core/model | registry resolves default `codex-gpt-5.5`; `codex` -> `gpt-5.5` | no AutoSci model invocation logs proving end-to-end model path | warn |
| native CLI args | `--no-introduction`, `--start-from`, `--pipeline`, `--all`, `--max-rounds`, `--target-score` now parse | `--format latex` fails; parsing still not semantic execution | warn |
| online evidence fetching | not executed | external novelty unavailable | error |
| novelty gate | local evaluation output only | no independent reviewer/source evidence | error |
| wiki resolver | exists | read-only; no state transition writes verified | warn |
| artifact propagation | sidecars produced | many inconclusive/schema_only/gated | warn |
| approved compile/poster executors | not approved/executed | no PDF/poster output | error |

## State-transition matrix

| entity | required transition | observed transition | status |
| --- | --- | --- | --- |
| Idea | proposed -> in_progress -> tested -> validated/failed | not observed; no validated state from real result | failed |
| Experiment | planned -> running -> completed/abandoned | plan says approval_required; run blocked missing approval; no running/completed | gated_unexecuted |
| Pipeline | stage0 -> stage1 -> gate1 -> stage2 -> stage3 -> stage4 -> gate2 -> stage5 -> completed | research/start-from emit gated workflow evidence only; no progress/report | gated_unexecuted |

## SkillGen semantic-fidelity matrix

| expected fact | observed extraction | artifact path | source page | pass/fail |
| --- | --- | --- | --- | --- |
| Title: SKILLGEN: Verified Inference-Time Agent Skill Synthesis | SkillGen(1); parse_status failed | /tmp/solar-autosci-parity-audit-20260625T122123-rerun/workspaces/workspace-b-components/runs/B02-ingest-paper/research_paper.json | PDF p1 | fail |
| 3 stages | missing | same | PDF p2-p3 | fail |
| Z=(a0,F,S,C) | missing | same | PDF p4/p15 | fail |
| s=(u,a,P,R) | missing | same | PDF p3 | fail |
| repairs/regressions/net gain | missing | same | PDF p2-p4 | fail |
| best-of-K and verification gate | missing | same | PDF p3/p6/p12 | fail |
| +3.27 to +10.08 pp; 50/25/5 | missing | same | PDF p2/p8 | fail |
| seed 42, temperature 0, GPT-5.4-Mini, 70/30, eight rounds, 30 guards, gate formula | missing | same | PDF appendix | fail |

## YAML coverage summary

```json
{
  "total_stages": 23,
  "native_full": 0,
  "native_partial": 4,
  "gated_unexecuted": 8,
  "environment_blocked": 0,
  "fixture_only": 0,
  "smoke_only": 0,
  "schema_only": 5,
  "fallback": 0,
  "failed": 2,
  "missing": 4,
  "extension": 0
}
```

## Route truthfulness notes

- `coverage_status=full` is no longer present in `feature_parity_routes.v1.json`; this is an improvement over the earlier report.
- Remaining route truthfulness issues are semantic: `visualize` still references original tools/app paths missing from OpenSolar, `survey --format latex` is not parsed, `exp-status --pipeline` returns `action_count=0`, and research resume does not persist pipeline progress/report.

## Flaw register

### F-001 blocker - PDF ingestion
- expected_original_behavior: Original /ingest extracts real paper content into wiki artifacts.
- observed_migrated_behavior: SkillGen PDF parse_status=failed; section is Parse Failure; all semantic checks fail.
- classification: `failed`
- evidence_paths: /tmp/solar-autosci-parity-audit-20260625T122123-rerun/commands/011-skillgen-pdf-oracle-and-ingest
- minimal_fix: Fix PDF extraction path or dependency gating; add semantic acceptance checks.
- impact_on_final_parity: blocks full parity

### F-002 critical - Review gate
- expected_original_behavior: Independent Review LLM evidence with score/verdict/fixes.
- observed_migrated_behavior: /review exits 2; no artifact/Review LLM evidence.
- classification: `failed`
- evidence_paths: /tmp/solar-autosci-parity-audit-20260625T122123-rerun/commands/012-components-and-integrated/B07-review-hard
- minimal_fix: Wire resolver and Review LLM evidence, or return blocked without review parity claim.
- impact_on_final_parity: blocks full parity

### F-003 critical - Experiment lifecycle
- expected_original_behavior: Real deploy/monitor/collect/eval changes experiment and idea states.
- observed_migrated_behavior: exp-run is approval-gated and correctly inconclusive; no real execution/state transition.
- classification: `gated_unexecuted`
- evidence_paths: /tmp/solar-autosci-parity-audit-20260625T122123-rerun/commands/012-components-and-integrated/B11-exp-run-deploy
- minimal_fix: Implement approved runtime evidence ingestion and state mutation after execution.
- impact_on_final_parity: blocks full parity

### F-004 critical - Paper pipeline
- expected_original_behavior: Draft/refine/compile creates paper/main.pdf.
- observed_migrated_behavior: paper-draft action_count=0; compile gated/schema_only; no PDF.
- classification: `gated_unexecuted`
- evidence_paths: /tmp/solar-autosci-parity-audit-20260625T122123-rerun/commands/012-components-and-integrated/B18-paper-compile-fix
- minimal_fix: Implement draft artifacts and approved compile executor with PDF checks.
- impact_on_final_parity: blocks full parity

### F-005 major - CLI parity
- expected_original_behavior: All original argument-hint flags are first-class.
- observed_migrated_behavior: `$survey --format latex` rejected; some parsed flags still produce no-op/gated-only evidence.
- classification: `failed/native_partial`
- evidence_paths: /tmp/solar-autosci-parity-audit-20260625T122123-rerun/commands/012-components-and-integrated/B15-survey
- minimal_fix: Add skill-specific parser coverage and semantic flag consumption checks.
- impact_on_final_parity: blocks full parity

### F-006 major - Integrated pipeline
- expected_original_behavior: Research pipeline resumes and writes pipeline progress/report.
- observed_migrated_behavior: research and start-from emit gated workflow artifacts only; exp-status --pipeline action_count=0.
- classification: `gated_unexecuted`
- evidence_paths: /tmp/solar-autosci-parity-audit-20260625T122123-rerun/commands/012-components-and-integrated/C03-research-start-from
- minimal_fix: Persist pipeline state and implement resume/status handlers.
- impact_on_final_parity: blocks full parity

### F-007 major - Web UI
- expected_original_behavior: Serve/graph/reader available over real wiki data.
- observed_migrated_behavior: OpenSolar lacks original tools/serve.py, tools/visualize.py, app/index.html, app/modules/graph.js.
- classification: `missing`
- evidence_paths: /tmp/solar-autosci-parity-audit-20260625T122123-rerun/commands/014-web-ui-static-check
- minimal_fix: Migrate tools or update route claims and provide Solar equivalent health checks.
- impact_on_final_parity: blocks full parity

### F-008 major - Ask/wiki QA
- expected_original_behavior: Ask answers SkillGen facts from source-grounded wiki.
- observed_migrated_behavior: Ask returns schema_only query capture after failed ingestion.
- classification: `schema_only`
- evidence_paths: /tmp/solar-autosci-parity-audit-20260625T122123-rerun/commands/011-skillgen-pdf-oracle-and-ingest/Q01-ask
- minimal_fix: Fix ingestion then add answer synthesis with source ids.
- impact_on_final_parity: blocks full parity


## Minimum repair plan

1. Blocker: fix PDF ingestion and SkillGen semantic extraction. Retest: `env HARNESS_DIR=/tmp/solar-autosci-ret python3 harness/plugins/autosci/bin/autosci_skill_shim.py text '$ingest /Users/jamesyuan/Downloads/SkillGen(1).pdf'`.
2. Critical runtime semantics: wire Review LLM evidence and artifact resolver. Retest: `$review <real-idea-slug> --difficulty hard --focus method`.
3. State/evidence correctness: implement approved experiment deploy/monitor/collect/eval state transitions. Retest: `$exp-run <experiment-slug> --review --env local`, then `$exp-status`, `$exp-run <experiment-slug> --collect`, `$exp-eval <experiment-slug>`.
4. Paper pipeline: generate real LaTeX and approved compile to `paper/main.pdf`. Retest: `$paper-draft ... --review`, `$refine paper/main.tex --max-rounds 3 --target-score 8 --focus writing`, `$paper-compile paper/ --fix`.
5. UI/reporting: migrate original web UI tools or update route claims to a verified Solar equivalent. Retest: server health/graph/reader checks against isolated wiki data.

## Final verdict rule application

`full parity` is not met because mandatory stages are not `native_full`, no real experiment deploy/monitor/collect/eval completed, no idea reached validated from real results, no real LaTeX compile generated `paper/main.pdf`, and several mandatory paths are `failed`, `schema_only`, or `gated_unexecuted`.

Final verdict: **failed**.
