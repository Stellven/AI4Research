# AutoSci Phase 19 Progress Log

Logged: 2026-06-19 00:14 EDT
Branch: `feature/autosci-solar-native`

## Scope

Phase 19 is the follow-up parity phase after Phase 18 acceptance. The goal is
to move from fixture-mode scientific lifecycle acceptance toward practical
feature parity with the local AutoSci `main` checkout, while preserving the
Solar-native architecture:

```text
TaskGraph node
  -> Logical operator
  -> Capability capsule
  -> Physical operator
  -> plugins/autosci backend action
  -> Evidence ABI / sidecar artifact
  -> deterministic gate or explicit warning
```

This phase must not introduce a monolithic `AutoSciRunner`, must not make
AutoSci the owner of workflow semantics, and must not silently replace
model-driven or evidence-driven paths with unsupported deterministic guesses.

## Work Completed Tonight

| Item | Status | Evidence |
|---|---|---|
| Phase 18 closeout | ok | Added `docs/integrations/autosci/phase18-progress-log.md`. |
| Phase 18 commit | ok | Commit `6dda794f docs: record autosci phase 18 acceptance`. |
| Phase 18 push | ok | Pushed `feature/autosci-solar-native` to GitHub. |
| Solar context injection | warn | Re-ran as `bash harness/solar-harness.sh context inject ...`; Mirage source returned `mirage:nonzero`. |
| AutoSci capability scan | ok | Inspected local `/Users/jamesyuan/Developer/Github Repos (On Git)/AutoSci` README, skills, tools, runtime schema, remote/daily/poster docs. |
| Solar coverage scan | ok | Inspected Solar AutoSci bridge actions, capsules, schemas, evaluators, workflows, personas, templates. |
| Parity finding | warn | Solar covers the scientific lifecycle governance/core, but not all AutoSci `main` concrete product features yet. |
| Phase 19 route parity config | ok | Added `harness/plugins/autosci/config/feature_parity_routes.v1.json` covering all 28 native AutoSci English skills. |
| Phase 19 parity bridge | ok | Added `harness/plugins/autosci/bin/autosci_parity_bridge.py` to scan native skills and emit `autosci_feature_parity.v1` evidence. |
| Phase 19 parity ABI/gate | ok | Added `harness/schemas/evidence/autosci_feature_parity.v1.schema.json` and `harness/evaluators/scientific/autosci_feature_parity_gate.py`. |
| Phase 19 real operator binding | ok | Added `harness/plugins/autosci/config/feature_operator_bindings.v1.json` mapping every native skill to a physical operator binding. |
| Phase 19 skillgen operator smoke | ok | Added `harness/plugins/autosci/bin/autosci_operator_smoke.py`, `autosci_operator_smoke.v1`, and smoke gate/tests. |
| Phase 19 tests | ok | Added bridge and gate tests; targeted suite passes `6 passed`. |
| Phase 19 matrix | ok | Added `docs/integrations/autosci/autosci-solar-feature-parity-matrix.md`. |

## Current Solar Coverage Baseline

| Capability group | Status | Solar surface |
|---|---|---|
| Literature discovery | ok | `discover_literature`, `literature_discovery.v1` |
| Paper ingest/analyze | ok | `ingest_paper`, `analyze_paper`, `research_paper.v1` |
| Memory and graph update | ok | `update_memory`, `update_graph`, memory/graph evidence |
| Claim/method/code extraction | ok | `extract_claims`, `extract_methods`, `map_code_evidence` |
| Idea generation/evaluation | ok | `generate_ideas`, `evaluate_ideas` |
| Experiment design/run/status | ok | `design_experiment`, `run_experiment`, `monitor_experiment` |
| Claim verdict | ok | `verify_claim`, `claim_verdict.v1` |
| Report/publication bundle | ok | `write_report`, report and publication gates |
| Workflow evolution | ok | `evolve_workflow`, `workflow_evolution.v1` |

## AutoSci Features Requiring Phase 19 Parity Work

| AutoSci feature | Current Solar status | Required Phase 19 direction |
|---|---|---|
| `/setup` | missing | Add config/status evidence action without mutating secrets. |
| `/reset` | missing | Add dry-run reset plan evidence; destructive execution must require explicit approval. |
| `/prefill` | missing | Add foundation/background evidence and memory-update path. |
| `/init` | partial | Add prepare/discovery/fan-in parity actions and source manifest evidence. |
| `/ingest` | partial | Move beyond sample markdown fixture toward local file/arXiv source preparation. |
| `/discover` live/topic/venue | partial | Add source-mode evidence for anchor/topic/wiki/venue discovery. |
| `/edit` | missing | Add bounded wiki edit plan/evidence action. |
| `/ask` | missing | Add retrieve/synthesize/crystallize evidence action with explicit confidence. |
| `/check` | missing | Add wiki health check evidence and gate. |
| `/daily-arxiv` | missing | Add prepare/finalize/digest evidence; live feeds/email/GitHub Actions as gated side effects. |
| `/novelty` | partial | Add multi-source novelty evidence and Review LLM warning path. |
| `/review` | partial | Add review report evidence and optional MCP-backed review binding. |
| `/refine` | partial | Add iterative review/fix loop evidence without silent edits. |
| `/exp-pilot-run` | partial | Add pilot-specific execution/result evidence. |
| `/exp-pilot-eval` | partial | Add lenient pilot verdict evidence. |
| `/exp-run --env remote` | partial | Add remote plan/status evidence; real SSH/rsync/screen must be approval-gated. |
| `/exp-status --collect-ready` | partial | Add collect-ready status and collection evidence. |
| `/exp-eval` | partial | Add Review LLM verdict mode and idea status update evidence. |
| `/survey` | missing | Add related-work/survey evidence and report artifact. |
| `/paper-plan` | partial | Add native paper outline/figure/citation plan evidence. |
| `/paper-draft` | partial | Add LaTeX draft bundle evidence. |
| `/paper-compile` | missing | Add compile/checklist evidence; real `latexmk` gated by availability. |
| `/rebuttal` | partial | Add rebuttal response evidence and review-comment mapping. |
| `/poster` | partial | Add full poster tool parity for build/title/header/figures/validate/render/overflow. |
| `/visualize` | missing | Add graph visualization artifacts for Obsidian config, Canvas, and web graph summary. |
| `tools/serve.py` web UI | missing | Add optional local server/runbook surface; not a core evidence ABI yet. |
| `mcp-servers/llm-review` | missing | Add optional physical operator binding and unavailable-state evidence. |

## Proposed Phase 19 Slices

| Slice | Status | Intended output |
|---|---|---|
| 19A parity matrix | ok | `docs/integrations/autosci/autosci-solar-feature-parity-matrix.md` |
| 19B generic parity evidence | ok | `autosci_feature_parity.v1` evidence ABI plus deterministic gate. |
| 19C bridge route expansion | ok | Added route-level bridge actions for setup/reset/prefill/init/check/ask/daily/review/poster/visualize and all other native skills. |
| 19D operator/config binding | ok | Added plugin route config mapping each native skill to Solar capability, logical operator, backend action, and Evidence ABI. |
| 19E gates/tests | ok | Added deterministic checks for route completeness, truthful partial/gated status, and missing-route failure. |
| 19F acceptance | ok | Local AutoSci scan produced 28 native skills, 28 routed, 0 missing. |

## Phase 19 Implementation Details

| File | Status | Purpose |
|---|---|---|
| `harness/plugins/autosci/config/feature_parity_routes.v1.json` | ok | Declarative Solar route map for every native AutoSci English skill. |
| `harness/plugins/autosci/config/feature_operator_bindings.v1.json` | ok | Physical operator binding map for every native AutoSci English skill. |
| `harness/plugins/autosci/bin/autosci_parity_bridge.py` | ok | Discovers AutoSci native skills and emits route parity evidence. |
| `harness/plugins/autosci/bin/autosci_operator_smoke.py` | ok | Runs real AutoSci bridge actions against the SkillGen smoke paper and summarizes route/operator status. |
| `harness/schemas/evidence/autosci_feature_parity.v1.schema.json` | ok | Evidence ABI for route parity inventory. |
| `harness/schemas/evidence/autosci_operator_smoke.v1.schema.json` | ok | Evidence ABI for SkillGen-backed operator smoke results. |
| `harness/evaluators/scientific/autosci_feature_parity_gate.py` | ok | Gate that fails on missing routes, bad counts, or false full-coverage claims. |
| `harness/evaluators/scientific/autosci_operator_smoke_gate.py` | ok | Gate that fails on unbound/failed operator routes and enforces gated side-effect honesty. |
| `harness/plugins/autosci/tests/fixtures/skillgen_operator_smoke_paper.md` | ok | Committed SkillGen smoke paper fixture. |
| `harness/plugins/autosci/tests/test_phase19_parity_bridge.py` | ok | Tests full inventory, single-skill route output, and unmapped future-skill failure. |
| `harness/plugins/autosci/tests/test_phase19_operator_smoke.py` | ok | Tests SkillGen smoke execution, all operator bindings, and generated smoke gate acceptance. |
| `harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py` | ok | Tests honest mixed coverage, missing route rejection, and full+approval misreport rejection. |
| `harness/tests/evaluators/scientific/test_autosci_operator_smoke_gate.py` | ok | Tests mixed completed/partial/gated smoke acceptance and unbound rejection. |
| `docs/integrations/autosci/autosci-solar-feature-parity-matrix.md` | ok | Human-readable matrix and verification record. |

## Phase 19 Verification

| Command | Result |
|---|---|
| `python3 -m json.tool harness/plugins/autosci/config/feature_parity_routes.v1.json` | ok |
| `python3 -m json.tool harness/schemas/evidence/autosci_feature_parity.v1.schema.json` | ok |
| `python3 harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out artifacts/autosci/phase19/parity_inventory.json` | ok: 28 native, 28 routed, 0 missing, 7 full, 11 partial, 10 gated |
| `python3 harness/evaluators/scientific/autosci_feature_parity_gate.py harness/artifacts/autosci/phase19/parity_inventory.json` | ok: passed with non-full route warning |
| `harness/bin/python3 harness/plugins/autosci/bin/autosci_operator_smoke.py skillgen --out artifacts/autosci/operator-smoke/skillgen/autosci_operator_smoke.json` | ok: 28 bound, 0 failed, 0 unbound, 16 core actions |
| `python3 harness/evaluators/scientific/autosci_operator_smoke_gate.py harness/artifacts/autosci/operator-smoke/skillgen/autosci_operator_smoke.json` | ok: passed with approval-gated warning |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_phase19_parity_bridge.py harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py` | ok: 6 passed before operator-smoke expansion |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_phase19_operator_smoke.py harness/tests/evaluators/scientific/test_autosci_operator_smoke_gate.py` | ok: 4 passed |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests harness/tests/evaluators/scientific` | ok: 63 passed |

## Phase 19 Shim Follow-up

| Item | Status | Evidence |
|---|---|---|
| Solar AutoSci skill shim | ok | Added `harness/plugins/autosci/bin/autosci_skill_shim.py` and `solar-harness.sh autosci ...` dispatch. |
| Skill-run Evidence ABI | ok | Added `harness/schemas/evidence/autosci_skill_run.v1.schema.json`. |
| Skill-run gate | ok | Added `harness/evaluators/scientific/autosci_skill_run_gate.py`. |
| Runtime artifact resolver | ok | Scientific gate artifact checks now also resolve paths under runtime `HARNESS_DIR` while schemas remain repo-local. |
| Shim tests | ok | Added `harness/plugins/autosci/tests/test_autosci_skill_shim.py`. |

## Phase 19 Dollar Skill Compatibility Follow-up

Logged: 2026-06-22 EDT

| Item | Status | Evidence |
|---|---|---|
| `$skills` list alias | ok | `autosci_skill_shim.py` normalizes `$skills` to `skills list`. |
| `$skill <name>` alias | ok | `autosci_skill_shim.py` normalizes `$skill ingest ...` to `skill ingest ...`. |
| `$<skill-name>` direct aliases | ok | Any configured native skill name can be invoked as `$ingest`, `$research`, `$exp-design`, etc.; unknown routes still emit failed route evidence instead of silent success. |
| Codex/PM intake routing | ok | `scripts/solar-codex-intake.sh` detects AutoSci `$...` messages and sends them directly to the deterministic shim instead of natural-language intent compilation. |
| Repo-local chat trace behavior | ok | `scripts/solar-chat.sh --trace` treats direct `$...` commands as direct shim runs and does not require a sprint DAG trace. |
| Harness top-level dispatch | ok | `harness/solar-harness.sh` dispatches literal `$skills`, `$skill`, and `$<skill>` arguments to the AutoSci shim. |

### Shim Commands

| Command | Result |
|---|---|
| `bash harness/solar-harness.sh autosci skills list` | ok: lists 28 configured native AutoSci skills. |
| `bash harness/solar-harness.sh '$skills'` | ok: lists 28 configured native AutoSci skills through the AutoSci-compatible command surface. |
| `bash harness/solar-harness.sh '$ingest' --paper "$PWD/harness/plugins/autosci/tests/fixtures/skillgen_operator_smoke_paper.md" --run-id solar-dollar-ingest-smoke` | ok: routes through the deterministic shim and generates `autosci_skill_run.v1` evidence. |
| `python3 harness/evaluators/scientific/autosci_skill_run_gate.py harness/artifacts/autosci/runs/solar-dollar-ingest-smoke/autosci_skill_run.json` | ok: passed. |
| `bash scripts/solar-codex-intake.sh --dry-run '$ingest --paper harness/plugins/autosci/tests/fixtures/skillgen_operator_smoke_paper.md --run-id codex-dollar-dryrun'` | ok: resolves to direct `autosci_skill_shim.py text ...`, not `intake`. |
| `bash scripts/solar-chat.sh --trace '$skills'` | ok: lists 28 skills and reports direct AutoSci command without sprint DAG trace. |
| `~/.solar/bin/solar-harness '$skills'` | ok: active installed harness returns `ok=True`, `count=28`. |
| `bash harness/solar-harness.sh autosci skill ingest --paper "$PWD/harness/plugins/autosci/tests/fixtures/skillgen_operator_smoke_paper.md" --run-id solar-shim-ingest-smoke` | ok: generated `autosci_skill_run.v1`, `research_paper.json`, and `research_paper.analyzed.json`. |
| `bash harness/solar-harness.sh autosci skill research --paper "$PWD/harness/plugins/autosci/tests/fixtures/skillgen_operator_smoke_paper.md" --topic "agent skill learning" --run-id solar-shim-research-smoke` | ok: ran 16 bounded bridge actions; 14 gate-passed, 2 schema-only; route honestly marked `gated`. |
| `bash harness/solar-harness.sh autosci skill setup --run-id solar-shim-setup-smoke` | ok: generated gated route evidence without writing secrets or executing setup side effects. |
| `python3 harness/evaluators/scientific/autosci_skill_run_gate.py harness/artifacts/autosci/runs/solar-shim-research-smoke/autosci_skill_run.json` | ok: passed with gated-route warning. |
| `python3 harness/evaluators/scientific/autosci_skill_run_gate.py harness/artifacts/autosci/runs/solar-shim-setup-smoke/autosci_skill_run.json` | ok: passed with gated-route warning. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok: 4 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok: 8 passed after dollar-command compatibility tests. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests harness/tests/evaluators/scientific` | ok: 71 passed after dollar-command compatibility tests. |

## Phase 19 Solar Skill Projection and Workspace Follow-up

Logged: 2026-06-22 EDT

| Item | Status | Evidence |
|---|---|---|
| Codex-native Solar AutoSci skill projection | ok | Generated 28 wrapper skills under `.agents/skills/*/SKILL.md`; wrappers preserve `$skill_name` UX and require routing through Solar. |
| Projection generator | ok | Added `harness/plugins/autosci/bin/project_autosci_codex_skills.py` to regenerate wrappers from Solar route config. |
| Human-facing workspace projector | ok | Added `harness/plugins/autosci/bin/autosci_workspace_projector.py`; it projects run evidence into `harness/artifacts/autosci/workspace/wiki/`. |
| Solar-managed logs boundary | ok | Workspace pages include research entities and outputs only; envelopes, logs, gate results, and operator state remain under Solar-managed run/runtime paths. |
| Shim workspace handoff | ok | `autosci_skill_shim.py` writes run evidence first, projects workspace pages, then records workspace paths in `outputs.skill_run.workspace`. |
| Skill projection tests | ok | Added `harness/plugins/autosci/tests/test_autosci_skill_projection.py`. |
| Workspace projection tests | ok | Extended `harness/plugins/autosci/tests/test_autosci_skill_shim.py` to assert paper, idea, experiment, and report workspace pages. |

### Projection Output Shape

| Path | Owner | Purpose |
|---|---|---|
| `harness/artifacts/autosci/runs/<run-id>/` | Solar | Execution evidence, envelopes, result JSON, gates, and reproducibility records. |
| `harness/artifacts/autosci/workspace/README.md` | Human/Solar projection | Explains human-facing workspace policy. |
| `harness/artifacts/autosci/workspace/wiki/index.md` | Human/Solar projection | Research navigation index. |
| `harness/artifacts/autosci/workspace/wiki/papers/` | Human/Solar projection | Durable paper pages projected from `research_paper.v1`. |
| `harness/artifacts/autosci/workspace/wiki/methods/` | Human/Solar projection | Method pages projected from `research_method.v1`. |
| `harness/artifacts/autosci/workspace/wiki/ideas/` | Human/Solar projection | Idea pages projected from `idea_candidate.v1`. |
| `harness/artifacts/autosci/workspace/wiki/experiments/` | Human/Solar projection | Experiment pages projected from `experiment_plan.v1`. |
| `harness/artifacts/autosci/workspace/wiki/outputs/` | Human/Solar projection | Claims/report pages intended for direct reading. |
| `harness/artifacts/autosci/workspace/wiki/graph/` | Human/Solar projection | Explicit graph edges and brief/open-question summaries. |

### Projection Commands

| Command | Result |
|---|---|
| `python3 harness/plugins/autosci/bin/project_autosci_codex_skills.py --source-skills "/Users/jamesyuan/Developer/Github Repos (On Git)/AutoSci/.agents/skills"` | ok: generated 28 OpenSolar wrapper skills. |
| `python3 -m py_compile harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/bin/autosci_workspace_projector.py harness/plugins/autosci/bin/project_autosci_codex_skills.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py harness/plugins/autosci/tests/test_autosci_skill_projection.py` | ok: 9 passed. |
| `bash harness/solar-harness.sh '$ingest' --paper "$PWD/harness/plugins/autosci/tests/fixtures/skillgen_operator_smoke_paper.md" --run-id solar-projection-ingest-smoke` | ok: generated Solar run evidence and `workspace/wiki/papers/paper-skillgen-operator-smoke-paper.md`. |
| `python3 harness/evaluators/scientific/autosci_skill_run_gate.py harness/artifacts/autosci/runs/solar-projection-ingest-smoke/autosci_skill_run.json` | ok: passed. |
| `bash harness/solar-harness.sh '$research' --paper "$PWD/harness/plugins/autosci/tests/fixtures/skillgen_operator_smoke_paper.md" --topic "agent skill learning" --run-id solar-projection-research-smoke` | ok: generated gated Solar research run and workspace pages for paper, method, ideas, experiment, claims, and report. |
| `python3 harness/evaluators/scientific/autosci_skill_run_gate.py harness/artifacts/autosci/runs/solar-projection-research-smoke/autosci_skill_run.json` | ok: passed with gated-route warning. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests harness/tests/evaluators/scientific` | ok: 72 passed. |
| `find .agents/skills -maxdepth 2 -name SKILL.md -print \| sort \| xargs -n1 dirname \| xargs -n1 harness/bin/python3 /Users/jamesyuan/.codex/skills/.system/skill-creator/scripts/quick_validate.py` | ok: 28 valid skills. |

## Phase 19 Lab Worktree Skill Discovery Follow-up

Logged: 2026-06-22 EDT

| Item | Status | Evidence |
|---|---|---|
| Root cause | ok | Solar lab Codex panes launch with `--cd .worktrees/lab-builder-*`; those worktrees had 0 `.agents/skills` while the main worktree had 28. |
| Merge decision | ok | No Git branch merge was needed: all four active lab worktrees were clean and based on the same HEAD as the main branch. The missing skills were untracked generated projection files. |
| Startup sync | ok | `harness/pane-launcher.sh` now projects Solar AutoSci wrapper skills into the actual pane `WORK_DIR/.agents/skills` before launching Codex. |
| Runtime route fix | ok | Generated wrapper skills now call `"${HARNESS_DIR:-$HOME/.solar/harness}/solar-harness.sh" '$skill' ...` so lab worktrees do not need uncommitted shim/intake files locally. |
| Active worktree sync | ok | Synced 28 wrapper skills into `.worktrees/lab-builder-{1,2,3,4}/.agents/skills`. |

### Worktree Skill Discovery Commands

| Command | Result |
|---|---|
| `git worktree list --porcelain` | ok: active Solar lab worktrees are `.worktrees/lab-builder-1..4` on `harness-lab-builder-*` branches. |
| `find .agents/skills -maxdepth 2 -name SKILL.md \| wc -l` | ok: main worktree has 28 wrapper skills. |
| `find .worktrees/lab-builder-*/.agents/skills -maxdepth 2 -name SKILL.md` before sync | warn: active lab worktrees had 0 wrapper skills. |
| `python3 harness/plugins/autosci/bin/project_autosci_codex_skills.py --output-dir ".worktrees/lab-builder-N/.agents/skills"` | ok: generated 28 wrapper skills per active lab worktree. |
| `bash -n harness/pane-launcher.sh` | ok |
| `env HARNESS_DIR="$PWD/harness" "$PWD/harness/solar-harness.sh" '$skills'` from `.worktrees/lab-builder-1` | ok: `True 28 True`, including `ingest`. |
| `env HARNESS_DIR="$PWD/harness" "$PWD/harness/solar-harness.sh" '$ingest' --paper ... --run-id worktree-wrapper-ingest-smoke` from `.worktrees/lab-builder-1` | ok: generated completed Solar run evidence and workspace paths. |
| `python3 harness/evaluators/scientific/autosci_skill_run_gate.py harness/artifacts/autosci/runs/worktree-wrapper-ingest-smoke/autosci_skill_run.json` | ok: passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py harness/plugins/autosci/tests/test_autosci_skill_projection.py` | ok: 9 passed. |

## Phase 19 Acceptance State

| Criterion | Status | Evidence |
|---|---|---|
| Every discovered AutoSci native English skill has a Solar route | ok | `missing_route_count=0` in `harness/artifacts/autosci/phase19/parity_inventory.json`. |
| Every discovered AutoSci native English skill has a physical operator binding | ok | `bound_count=28`, `unbound_count=0` in `harness/artifacts/autosci/operator-smoke/skillgen/autosci_operator_smoke.json`. |
| SkillGen paper runs through real core bridge operators | ok | 16 core actions executed; 14 gate-passed and 2 schema-only where no deterministic gate exists. |
| Route status is truthful, not overclaimed | ok | Gate rejects `full` routes that still require approval and warns on partial/gated routes. |
| Side effects remain governed | ok | Config marks reset/edit/setup/remote/email/browser/GitHub Actions/compile paths as approval-gated. |
| Future AutoSci skill drift is detectable | ok | Bridge test adds `new-native-skill` and verifies missing-route failure. |
| No AutoSci black-box owner introduced | ok | Bridge emits route parity evidence; it does not execute or own the research workflow. |

## Guardrails

- Do not call a single AutoSci end-to-end owner.
- Do not mutate user-owned AutoSci `raw/` inputs from Solar parity tests.
- Do not execute remote SSH, SMTP email, browser open, GitHub Actions mutation,
  or destructive reset without explicit approval.
- If live APIs or external tools are unavailable, emit `warn` or `inconclusive`
  evidence instead of a fake success.
- Keep AutoSci-specific mechanics in `harness/plugins/autosci`; keep Solar
  workflow meaning in operators, capsules, workflows, schemas, gates, and docs.

## Current Worktree Note

The OpenSolar worktree already contains substantial modified and untracked
AutoSci integration files from earlier phases. Phase 19 commits should stage
only files intentionally changed for the current slice.

## Phase 19 Codex Pane Worktree Default Follow-up

Logged: 2026-06-22 EDT

| Item | Status | Evidence |
|---|---|---|
| Root cause | ok | Codex discovers skills from its `--cd` directory; lab panes in `.worktrees/lab-builder-*` missed main `.agents/skills` unless wrappers were copied. |
| Default behavior | ok | `SOLAR_BUILDER_WORKTREES` now defaults off; `pane-launcher.sh` and `start-incarnation.sh` keep builder/lab-builder `WORK_DIR` as the original OpenSolar checkout unless `SOLAR_BUILDER_WORKTREES=1` is set. |
| Opt-in isolation | ok | `harness/lib/worktree.sh` exposes `solar_builder_worktrees_enabled`; existing worktree creation remains available only when explicitly enabled. |
| Skill projection | ok | `pane-launcher.sh` still projects Solar AutoSci wrapper skills into the actual `WORK_DIR/.agents/skills`; with worktrees disabled this is the main OpenSolar `.agents/skills`. |
| Live lab refresh | ok | `bash harness/solar-harness.sh models apply-lab` respawned four lab panes; tmux pane cwd values are now the original OpenSolar directory, not `.worktrees/lab-builder-*`. |

### Worktree Default Verification Commands

| Command | Result |
|---|---|
| `bash -n harness/lib/worktree.sh harness/pane-launcher.sh harness/start-incarnation.sh` | ok |
| `bash harness/tests/test-d3-builder-worktree-consistency.sh` | ok: `PASS: 8 FAIL: 0`; verifies default-off and `SOLAR_BUILDER_WORKTREES=1` opt-in semantics. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_projection.py` | ok: 1 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py harness/plugins/autosci/tests/test_autosci_skill_projection.py` | ok: 9 passed. |
| `bash harness/solar-harness.sh models apply-lab` | ok: respawned active lab panes after the default-off change. |
| `tmux list-panes -a -F '#{session_name}:#{window_name}.#{pane_index} #{pane_id} cwd=#{pane_current_path} title=#{pane_title}'` | ok: four `solar-harness-lab` panes use `/Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar` as cwd. |
| `find .agents/skills -mindepth 1 -maxdepth 1 -type d \| wc -l` | ok: 28 wrapper skill directories in the active Codex `--cd` project directory. |
| `rg -n "solar-harness\|do not execute native AutoSci" .agents/skills -g 'SKILL.md'` | ok: wrappers route through Solar Harness and forbid native AutoSci tool execution. |

### Worktree Cleanup Audit

| Worktree group | Status | Recommendation |
|---|---|---|
| `.worktrees/lab-builder-1..4` | not live after respawn; contain `.DS_Store`, generated `.agents/`, and in lab-builder-1 `library/.DS_Store` | Candidate cleanup after user approval if no hidden needed changes are found. |
| `.worktrees/builder` | not live; contains real modified AI influence/report validation code and tests plus untracked nested `.worktrees/` and caches | Do not delete. Review, merge, or explicitly discard these changes first. |
| nested `.worktrees/builder/.worktrees/builder*` | not live; mostly `.DS_Store` / nested worktree metadata | Candidate cleanup only after resolving parent `.worktrees/builder` and explicit approval. |
| `/Users/jamesyuan/.codex/worktrees/05ae/OpenSolar` | not live in current tmux audit; contains real modified core/harness and routing files | Do not delete without review. |
| `/Users/jamesyuan/.codex/worktrees/a0ad/OpenSolar` | not live in current tmux audit; has `codex-recovery/` untracked | Do not delete until recovery contents are reviewed. |
| `/Users/jamesyuan/.codex/worktrees/a0ad/OpenSolar/.worktrees/lab-builder-1..4` | not live in current tmux audit; clean by `git status --short --branch` | Candidate cleanup after user approval. |

No worktrees were deleted during this follow-up.

## Phase 19 Worktree Sync and Cleanup Follow-up

Logged: 2026-06-22 EDT

| Item | Status | Evidence |
|---|---|---|
| User approval | ok | User explicitly requested syncing progress to the original directory and deleting all worktrees. |
| Live pane audit | ok | Active Solar lab panes were already running from `/Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar`; no live pane cwd referenced `.worktrees`. |
| Preservation bundle | ok | Tracked diffs, clean-apply subsets, untracked tarballs, and status inventory were saved under `harness/artifacts/worktree-sync/20260622-worktree-cleanup/`. |
| Clean tracked sync | ok | Non-conflicting tracked changes from `/Users/jamesyuan/.codex/worktrees/05ae/OpenSolar` and `.worktrees/builder` were applied into the original checkout with `git apply --3way`. |
| Conflict handling | warn | Conflicting tracked changes were not overwritten; full patches are preserved in `codex-05ae-tracked.diff` and `local-builder-tracked.diff`. |
| Untracked sync | ok | Meaningful missing untracked files were copied into the original checkout: `codex-recovery/AI4Research-B-threads.md` and `harness/tests/test_report_deep_verifier_repair.py`. |
| Newer original files | ok | Original-checkout versions of `core/harness/harness-client.ts` and `scripts/solar-codex-intake.sh` were kept because they already contained newer Solar routing behavior than the worktree copies. |
| Worktree deletion | ok | All registered non-main worktrees were removed with `git worktree remove --force`; local `.worktrees/` leftovers were removed after confirming they contained only disposable residue. |
| Final worktree state | ok | `git worktree list --porcelain` reports only the original OpenSolar checkout. |

### Preserved Cleanup Artifacts

| Artifact | Purpose |
|---|---|
| `codex-05ae-tracked.diff` | Full tracked diff from `/Users/jamesyuan/.codex/worktrees/05ae/OpenSolar`, including conflicts that were not applied. |
| `codex-05ae-clean-apply.diff` | Clean subset applied into the original checkout. |
| `codex-05ae-untracked.tar.gz` | Untracked file backup from the 05ae Codex worktree. |
| `codex-a0ad-tracked.diff` | Empty tracked diff record for the a0ad Codex worktree. |
| `codex-a0ad-untracked.tar.gz` | Untracked recovery backup from the a0ad Codex worktree. |
| `local-builder-tracked.diff` | Full tracked diff from `.worktrees/builder`, including any paths excluded from clean apply. |
| `local-builder-clean-apply.diff` | Clean subset applied into the original checkout. |
| `local-builder-untracked.tar.gz` | Untracked backup from `.worktrees/builder`. |
| `worktree-status-summary.json` | Inventory of audited worktrees, tracked status, and untracked files before deletion. |

### Sync and Cleanup Verification Commands

| Command | Result |
|---|---|
| `lsof +D .worktrees` and `lsof +D /Users/jamesyuan/.codex/worktrees` | ok: no open file handles were reported before deletion. |
| `git apply --3way --check codex-05ae-clean-apply.diff` | ok: clean subset was applicable. |
| `git apply --3way --check local-builder-clean-apply.diff` | ok: clean subset was applicable. |
| `git worktree remove --force <path>` for every non-main registered worktree | ok: all non-main registered worktrees removed. |
| `git worktree list --porcelain` | ok: only `/Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar` remains. |
| `find .worktrees -maxdepth 2 -print` | ok: no local `.worktrees` directory remains. |
| `find /Users/jamesyuan/.codex/worktrees -maxdepth 2 -print` | ok: only the Codex worktree root and `.metadata_never_index` remain. |
| `bash -n harness/lib/worktree.sh harness/pane-launcher.sh harness/start-incarnation.sh` | ok |
| `bash harness/tests/test-d3-builder-worktree-consistency.sh` | ok: `PASS: 8 FAIL: 0`. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py harness/plugins/autosci/tests/test_autosci_skill_projection.py` | ok: 9 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/test_ai_influence_youtube_report_pane_surface.py harness/tests/test_ai_influence_youtube_report_status_surface.py harness/tests/test_report_validation.py harness/tests/test_report_deep_verifier_repair.py harness/tests/test_unified_selector_binding_policy.py harness/tests/test_pm_dispatch.py harness/tests/test_physical_operator_logical_selector.py` | ok: 33 passed after updating the synced selector test to expect `gpt-5.5`. |
| `bash harness/tests/test-model-registry-guard.sh` | ok: `PASS=23 FAIL=0`. |
| `bash harness/tests/test-model-config-single-source.sh` | ok: `PASS=19 FAIL=0`. |

### Preserved Conflict Notes

| Path | Status | Reason |
|---|---|---|
| `AGENTS.md` | preserved in patch only | Worktree changes conflicted with the current original-checkout file. |
| `harness/config/physical-operators.json` | preserved in patch only | Worktree changes conflicted with the current original-checkout file. |
| `harness/lib/multi_task_runner.py` | preserved in patch only | Worktree changes conflicted with the current original-checkout file. |
| `core/harness/harness-client.ts` | original kept | Original checkout had newer repo-harness resolution behavior. |
| `scripts/solar-codex-intake.sh` | original kept | Original checkout had newer direct AutoSci dollar-command routing. |

## Phase 19 PDF / arXiv Source Preparation Gap Closure

Logged: 2026-06-22 EDT

| Item | Status | Evidence |
|---|---|---|
| Native AutoSci gap | ok | Confirmed original AutoSci `/ingest` and `/init` prepare local PDFs through `tools/prepare_paper_source.py`, recover arXiv IDs, fetch `https://arxiv.org/e-print/<id>`, and fall back to synthetic `.tex`. |
| Solar backend implementation | ok | Added `harness/plugins/autosci/backends/paper_prepare.py` and routed bridge paper reads through it. |
| Supported inputs | ok | Local `.pdf`, `.tex`, markdown, source directories, source archives, and arXiv URLs now share the same Solar AutoSci preparation path. |
| PDF extraction | ok | PyMuPDF-backed PDF text extraction writes explicit `extracted_pdf_text` artifacts under `artifacts/autosci/workspace/raw/tmp/papers/`. |
| arXiv source recovery | ok | Preparation recovers arXiv IDs from explicit inputs, arXiv URLs, filename/path/text, and optional title-based Semantic Scholar lookup, then prefers arXiv source before synthetic fallback. |
| Evidence preservation | ok | `research_paper.v1` now preserves `outputs.paper.preparation` and preparation artifacts. |
| Offline behavior | ok | `inputs.allow_network_fetch=false` or `AUTOSCI_DISABLE_NETWORK_FETCH=1` disables source retrieval and forces synthetic `.tex` fallback when possible. |
| Harness Python entry | ok | Updated `harness/solar-harness.sh` AutoSci skill entries to prefer `harness/bin/python3`, ensuring PyMuPDF and AutoSci dependencies are available during `$ingest`. |
| Skill UX | ok | Updated the `$ingest` Solar wrapper description to show `prepare_paper_source -> ingest_paper`. |

### PDF / arXiv Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/plugins/autosci/backends/paper_prepare.py harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/adapters/autosci_to_research_paper.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_paper_prepare.py -q` | ok: 2 passed. |
| `bash -n harness/solar-harness.sh` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests -q` | ok: 38 passed. |
| `env AUTOSCI_DISABLE_NETWORK_FETCH=1 bash harness/solar-harness.sh '$ingest' --paper /private/tmp/solar-autosci-pdf-smoke-2401.00003.pdf --run-id solar-pdf-ingest-smoke-2` | ok: `execution_status=completed`; `research_paper.v1` has `source_type=latex`, `arxiv=2401.00003`, `source_fetch_status=skipped_network_disabled`, `extracted_pdf_text`, and `synthetic_latex`. |
| `harness/bin/python3 harness/evaluators/scientific/paper_gate.py harness/artifacts/autosci/runs/solar-pdf-ingest-smoke-2/research_paper.json` | ok: `status=passed`. |

## Phase 19 Discover Command Compatibility Gap Closure

Logged: 2026-06-22 EDT

| Item | Status | Evidence |
|---|---|---|
| Native AutoSci reference | ok | Upstream `/discover` supports `--anchor`, `--negative`, `--topic`, `--from-wiki`, `--venue`, `--year`, and `--limit`, implemented by `tools/discover.py`. |
| Shim argument compatibility | ok | `harness/plugins/autosci/bin/autosci_skill_shim.py` now accepts native discovery arguments, including `$discover --from-wiki --limit 10`. |
| Real discovery backend | ok | Added `harness/plugins/autosci/backends/literature_discover.py` for `wiki`, `topic`, `anchors`, and `venue` modes. |
| Fixture fallback policy | ok | Fixture candidates are retained only for explicit smoke fixture mode; real discovery modes emit live candidates or inconclusive evidence. |
| Discovery gate | ok | Added `harness/evaluators/scientific/literature_discovery_gate.py` and registered it in operator smoke. |
| Limit handling | ok | Backend applies `outputs.limit` and fails gate if completed candidate count exceeds limit. |
| Converter regression guard | ok | Updated converter tests so `literature_discovery.v1` only emits a fixture candidate when raw input explicitly sets `mode=fixture`; normal discovery conversion keeps empty candidates empty. |
| Solar Harness smoke | ok | `$discover --from-wiki --limit 10` now parses through the Solar shim, records `mode=wiki`, `from_wiki=true`, `limit=10`, and emits inconclusive evidence without `local_fixture` when network discovery is disabled. |

### Discover Compatibility Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/plugins/autosci/backends/literature_discover.py harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/adapters/autosci_to_literature_discovery.py harness/evaluators/scientific/literature_discovery_gate.py harness/plugins/autosci/bin/autosci_operator_smoke.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_literature_discover.py harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_accepts_discover_from_wiki_limit -q` | ok: 3 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py harness/plugins/autosci/tests/test_phase19_operator_smoke.py harness/plugins/autosci/tests/test_bridge_smoke.py harness/plugins/autosci/tests/test_literature_discover.py -q` | ok: 27 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests -q` | ok: 42 passed. |
| `bash -n harness/solar-harness.sh` | ok |
| `git diff --check -- <discover compatibility files>` | ok |
| `env AUTOSCI_DISABLE_NETWORK_FETCH=1 bash harness/solar-harness.sh '$discover' --from-wiki --limit 10 --run-id solar-discover-from-wiki-smoke` | ok: command parsed and wrote `harness/artifacts/autosci/runs/solar-discover-from-wiki-smoke/literature_discovery.json`; evidence status is `inconclusive`, `outputs.mode=wiki`, `outputs.limit=10`, and no `local_fixture` candidate is present. |

## Phase 19 Native Command Contract and Smoke Boundary Follow-up

Logged: 2026-06-24 EDT

| Item | Status | Evidence |
|---|---|---|
| Pane-output diagnosis | ok | User-provided pane output showed missing native flags, implicit fixture fallbacks, fixture-grade ideas, missing novelty/review gates, unsupported collect/title/checklist paths, and publication compile overclaiming. |
| Native CLI contract | ok | `autosci_skill_shim.py` now accepts native compatibility flags for experiment, ideation, novelty/review, paper planning, and paper compile routes. |
| Explicit smoke boundary | ok | Source-dependent bridge actions no longer run on implicit default fixture input; fixture bridge execution now requires `--smoke` or an explicit `--paper`. |
| Target resolver | ok | Positional native targets such as `exp-001`, `idea-001`, and `paper/` are recorded as `inputs.target` when `--target` is not supplied. |
| Native option evidence | ok | Skill-run evidence records `inputs.native_options` for flags such as `--env`, `--collect`, `--title`, and `--checklist`. |
| Route truthfulness | ok | `exp-status`, `ideate`, `paper-draft`, and `paper-plan` were downgraded from `full`/`executable` to `partial` until wiki state, multi-source evidence, Review LLM, and publication artifacts are fully wired. |
| Bundle fallback guard | ok | `$paper-compile paper/ --checklist` is accepted and recorded, but no longer silently produces a fixture publication bundle without explicit smoke/source context. |
| Experiment fallback guard | ok | `$exp-run exp-001 --env local --collect` is accepted and recorded, but no longer silently runs fixture experiment evidence without explicit smoke/source context. |

### Native Contract Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/bin/autosci_operator_smoke.py harness/plugins/autosci/bin/autosci_parity_bridge.py` | ok |
| `python3 -m json.tool harness/plugins/autosci/config/feature_parity_routes.v1.json` | ok |
| `python3 -m json.tool harness/plugins/autosci/config/feature_operator_bindings.v1.json` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py harness/plugins/autosci/tests/test_phase19_parity_bridge.py harness/plugins/autosci/tests/test_phase19_operator_smoke.py -q` | ok: 18 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests -q` | ok: 46 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py harness/tests/evaluators/scientific/test_autosci_operator_smoke_gate.py -q` | ok: 5 passed. |
| `git diff --check -- <native contract files>` | ok |
| `harness/plugins/autosci/bin/autosci_skill_shim.py '$exp-run' exp-001 --env local --collect --run-id contract-exp-run` | ok: accepted native flags, recorded `target=exp-001`, `env=local`, `collect=true`, `execution_status=gated`, `action_count=0`. |
| `harness/plugins/autosci/bin/autosci_skill_shim.py '$paper-plan' idea-001 --venue ICLR --title "Skill Generation for Inference-Time Agents" --run-id contract-paper-plan` | ok: accepted `--title`, recorded `target=idea-001`, `execution_status=partial`, `action_count=0`. |
| `harness/plugins/autosci/bin/autosci_skill_shim.py '$paper-compile' paper/ --checklist --run-id contract-paper-compile` | ok: accepted `--checklist`, recorded `target=paper/`, `execution_status=gated`, `action_count=0`. |

### Remaining Native Parity Blocks

| Block | Status | Required follow-up |
|---|---|---|
| Full `/ideate` | pending | Wiki maturity scan, failed-idea banlist, external discovery evidence, dual-model brainstorm, novelty/review validation, and wiki writes. |
| Full `/exp-run` | pending | Code generation, dataset/GPU/config inspection, approval loop, local/remote deploy, status mutation, and collect mode. |
| Full `/paper-plan` | pending | Idea-graph evidence map, section/figure/citation plan, `--title` as first-class plan input, and mandatory Review LLM assessment. |
| Full `/paper-compile` | pending | `latexmk`, PDF output, page/font/anonymity/[UNCONFIRMED] checks, and checklist report. |

## Phase 19 Real Ideate Sourcing Follow-up

Logged: 2026-06-24 EDT

| Item | Status | Evidence |
|---|---|---|
| Wiki/discovery sourcing backend | ok | Added `harness/plugins/autosci/backends/idea_source.py` to read Solar workspace wiki pages, graph briefs/open questions, failed ideas, and latest/explicit `literature_discovery.v1` evidence. |
| Non-fixture `/ideate` path | ok | `$ideate <direction>` can now run `generate_ideas -> evaluate_ideas` without a paper fixture when topic/wiki/discovery sources are available. |
| Missing-source behavior | ok | `/ideate` without wiki/discovery/paper evidence now emits inconclusive `idea-source-missing` diagnostics instead of silently generating fixture ideas. |
| Fixture-only guard | ok | `idea_gate.py` rejects fixture-only idea candidates/evaluations unless the evidence is explicit fixture/smoke evidence. |
| Source metadata | ok | Generated ideas include `source_mode`, `generation_path`, `origin_evidence_ids`, `grounding_summary`, and failed-idea overlap status. |
| Evaluation behavior | ok | Real sourced ideas are marked `revise` pending `/novelty` and `/review`; missing-source ideas are marked `inconclusive`; fixture ideas remain allowed only in smoke fixtures. |
| Shim contract | ok | `autosci_skill_shim.py` passes `--from-wiki`, `--wiki-root`, `--discovery-evidence`, `--max-ideas`, `--skip-validation`, and `--skip-pilot` into idea envelopes. |

### Real Ideate Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/plugins/autosci/backends/idea_source.py harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/adapters/autosci_to_idea_candidate.py harness/evaluators/scientific/idea_gate.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py harness/plugins/autosci/tests/test_bridge_smoke.py::test_phase11_generate_and_evaluate_ideas_write_native_evidence harness/tests/evaluators/scientific/test_idea_gate.py -q` | ok: 18 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests -q` | ok: 48 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/evaluators/scientific/test_idea_gate.py harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py harness/tests/evaluators/scientific/test_autosci_operator_smoke_gate.py -q` | ok: 8 passed. |

### Remaining Ideate Blocks

| Block | Status | Required follow-up |
|---|---|---|
| External search | pending | WebSearch, Semantic Scholar, and DeepXiv source collection still need live/degraded evidence paths. |
| Dual-model brainstorming | pending | Codex/Review LLM independent generation and merge/dedup are not wired yet. |
| Deep validation | pending | `/novelty --write` and `/review --difficulty hard --focus method` still need first-class integration into `/ideate`. |
| Wiki mutation | pending | Writing proposed/failed ideas plus graph edges and context rebuild remains approval-gated follow-up work. |
| Pilot loop | pending | Pilot spec generation, `/exp-pilot-run`, and `/exp-pilot-eval` remain separate route work. |

## Phase 19 Local Novelty / Review Signal Follow-up

Logged: 2026-06-24 EDT

| Item | Status | Evidence |
|---|---|---|
| Local novelty backend | ok | Added `harness/plugins/autosci/backends/novelty_review.py` to score idea novelty against local wiki/discovery sources and failed-idea memory. |
| Direct `/novelty` route | ok | `$novelty <target> --from-wiki` now maps to evaluate-only evidence without expanding fixture paper/claim/method dependencies. |
| Ideate deep-validation signal | ok | Non-smoke `/ideate` evaluations now include `closest_prior_work`, `review_score`, `review_mode`, `review_available`, `novelty_label`, and conservative recommendations. |
| Review honesty | ok | Review signal is marked `review_mode=local_surrogate` and `review_available=false`; it does not claim Review LLM MCP was used. |
| Gate hardening | ok | `idea_gate.py` requires sourced `advance`/`revise` evaluations to include closest-prior and review-score fields, and still rejects non-smoke fixture evaluations. |
| Missing source behavior | ok | Missing-source evaluations remain `inconclusive`, not promoted. |

### Novelty / Review Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/plugins/autosci/backends/novelty_review.py harness/plugins/autosci/backends/idea_source.py harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/evaluators/scientific/idea_gate.py` | ok |
| `python3 -m json.tool harness/plugins/autosci/config/feature_parity_routes.v1.json` | ok |
| `python3 -m json.tool harness/plugins/autosci/config/feature_operator_bindings.v1.json` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py harness/plugins/autosci/tests/test_bridge_smoke.py::test_phase11_generate_and_evaluate_ideas_write_native_evidence harness/tests/evaluators/scientific/test_idea_gate.py -q` | ok: 20 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests -q` | ok: 49 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/evaluators/scientific/test_idea_gate.py harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py harness/tests/evaluators/scientific/test_autosci_operator_smoke_gate.py -q` | ok: 9 passed. |

### Remaining Deep Validation Blocks

| Block | Status | Required follow-up |
|---|---|---|
| Live external novelty | pending | Connect WebSearch, Semantic Scholar, and DeepXiv results as explicit source evidence. |
| Review LLM MCP | pending | Replace or augment `local_surrogate` with independent Review LLM evidence when MCP is available. |
| `/novelty --write` | pending | Approval-gated update of `wiki/ideas/{slug}.md` frontmatter `novelty_score`. |
| `/review` standalone | pending | General artifact review report with difficulty/focus and wiki entity mapping remains separate from idea evaluation. |

## Phase 19 Novelty Writeback Follow-up

Logged: 2026-06-24 EDT

| Item | Status | Evidence |
|---|---|---|
| Explicit write gate | ok | `/novelty <idea-slug> --write` is the only path that attempts wiki mutation; normal novelty evaluation remains read-only. |
| Wiki idea resolver | ok | Write-back resolves an existing `wiki/ideas/{slug}.md` file from explicit `--wiki-root`, workspace wiki, or repo workspace wiki roots and refuses unresolved free-text targets. |
| Frontmatter mutation | ok | `autosci_bridge.py` updates the target idea YAML `novelty_score` from the numeric evaluation score and leaves missing-frontmatter targets inconclusive instead of fabricating state. |
| Wiki audit log | ok | Successful writes append a `Novelty Writeback` entry to `wiki/log.md` with idea path, score, and source evidence ids. |
| Sidecar evidence | ok | `evaluate_ideas.result.json` now includes `novelty_writeback_path` and sidecar evidence with `schema=novelty_writeback.v1`, `approval_ref=cli --write`, and applied/skipped status. |

### Novelty Writeback Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py harness/tests/evaluators/scientific/test_idea_gate.py -q` | ok: 20 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests -q` | ok: 50 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/evaluators/scientific/test_idea_gate.py harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py harness/tests/evaluators/scientific/test_autosci_operator_smoke_gate.py -q` | ok: 9 passed. |
| `git diff --check -- harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |

### Remaining Validation Blocks

| Block | Status | Required follow-up |
|---|---|---|
| Live external novelty | pending | Connect WebSearch, Semantic Scholar, and DeepXiv result evidence before using write-back as a final acceptance gate. |
| Review LLM MCP | pending | Replace or augment local surrogate review with independent Review LLM evidence. |
| `/review` standalone | pending | Add first-class artifact review reports with difficulty/focus routing and wiki entity mapping. |

## Phase 19 Standalone Review Follow-up

Logged: 2026-06-24 EDT

| Item | Status | Evidence |
|---|---|---|
| Standalone `/review` action | ok | Non-smoke `$review <target>` now runs `review_artifact` instead of claim-verification fixture steps. |
| Local artifact resolver | ok | Added `harness/plugins/autosci/backends/artifact_review.py` to resolve explicit artifact paths, paper paths, workspace wiki entities, and explicit `--wiki-root` targets. |
| Evidence schema | ok | Added `artifact_review.v1` schema with review mode, difficulty, focus, score, recommendation, findings, artifacts, and limitations. |
| Review honesty | ok | Evidence declares `review_mode=local_surrogate` and `review_available=false`; limitations explicitly state that independent Review LLM evidence is still required. |
| Gate coverage | ok | Added `artifact_review_gate.py` and registered it in the AutoSci operator smoke gate map. |
| Route truthfulness | ok | `/review` route now advertises `artifact_review.v1` and `review_artifact`, while binding limitations keep fixture smoke and Review LLM gaps explicit. |

### Standalone Review Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/plugins/autosci/backends/artifact_review.py harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/bin/autosci_operator_smoke.py harness/evaluators/scientific/artifact_review_gate.py harness/plugins/autosci/tests/test_autosci_skill_shim.py harness/tests/evaluators/scientific/test_artifact_review_gate.py` | ok |
| `python3 -m json.tool harness/plugins/autosci/config/feature_parity_routes.v1.json` | ok |
| `python3 -m json.tool harness/plugins/autosci/config/feature_operator_bindings.v1.json` | ok |
| `python3 -m json.tool harness/schemas/evidence/artifact_review.v1.schema.json` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py harness/tests/evaluators/scientific/test_artifact_review_gate.py harness/tests/evaluators/scientific/test_idea_gate.py -q` | ok: 23 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests -q` | ok: 51 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/evaluators/scientific/test_artifact_review_gate.py harness/tests/evaluators/scientific/test_idea_gate.py harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py harness/tests/evaluators/scientific/test_autosci_operator_smoke_gate.py -q` | ok: 11 passed. |
| `git diff --check -- <standalone review and novelty writeback files>` | ok |

### Remaining Review Blocks

| Block | Status | Required follow-up |
|---|---|---|
| Review LLM MCP | pending | Add real `mcp__llm-review__chat` execution or explicit unavailable evidence when the server is absent. |
| Entity write-back | pending | Add approval-gated wiki metadata updates for review status/review score after independent review evidence exists. |
| Deep rubric | pending | Replace coarse deterministic findings with native AutoSci rubric sections for method, evidence, novelty, clarity, and reproducibility. |

## Phase 19 Review LLM Evidence State Follow-up

Logged: 2026-06-24 EDT

| Item | Status | Evidence |
|---|---|---|
| Unavailable-state evidence | ok | Standalone `/review` now includes `outputs.review.review_llm.status=unavailable` when no MCP bridge or Review LLM evidence path is supplied. |
| Supplied Review LLM evidence path | ok | Added `--review-llm-evidence <json>` support; valid external `artifact_review.v1` evidence promotes output to `review_mode=review_llm` and `review_available=true`. |
| Conservative merge | ok | Local deterministic findings and Review LLM findings are merged; score/recommendation remain conservative when the external reviewer raises a stricter concern. |
| Gate hardening | ok | `artifact_review_gate.py` now requires local surrogate reviews to carry unavailable/invalid Review LLM state, and Review LLM mode to carry completed Review LLM state. |
| Honesty boundary | ok | The bridge records supplied Review LLM evidence as external evidence; it still does not claim direct MCP invocation. |

### Review LLM Evidence Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/plugins/autosci/backends/artifact_review.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/evaluators/scientific/artifact_review_gate.py harness/plugins/autosci/tests/test_autosci_skill_shim.py harness/tests/evaluators/scientific/test_artifact_review_gate.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py harness/tests/evaluators/scientific/test_artifact_review_gate.py -q` | ok: 20 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests -q` | ok: 52 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/evaluators/scientific/test_artifact_review_gate.py harness/tests/evaluators/scientific/test_idea_gate.py harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py harness/tests/evaluators/scientific/test_autosci_operator_smoke_gate.py -q` | ok: 11 passed. |
| `python3 -m json.tool harness/schemas/evidence/artifact_review.v1.schema.json` | ok |
| `git diff --check -- <Review LLM evidence-state files>` | ok |

### Remaining Review LLM Blocks

| Block | Status | Required follow-up |
|---|---|---|
| Direct MCP invocation | pending | Add a safe bridge to call `mcp__llm-review__chat` when the server is actually available in the runtime. |
| MCP response normalization | pending | Validate and normalize live Review LLM response bodies into `artifact_review.v1` before merging. |
| Review write-back | pending | Update wiki review status only after trusted independent review evidence and explicit write approval. |

## Phase 19 External Novelty Evidence Follow-up

Logged: 2026-06-24 EDT

| Item | Status | Evidence |
|---|---|---|
| External novelty unavailable state | ok | Non-smoke `/novelty` now emits `external_novelty.status=unavailable` when no Web/Semantic Scholar/DeepXiv evidence path is supplied. |
| Supplied external evidence | ok | Added `--novelty-evidence <json>` support for external source evidence files containing `sources`, `candidates`, `results`, `papers`, or `items`. |
| Evidence normalization | ok | External sources are normalized into closest-prior rows with provider, title, summary, source id, path, and optional URL. |
| Conservative scoring | ok | External sources are included in overlap scoring; unavailable or invalid external evidence is surfaced as a risk rather than replaced by synthetic sources. |
| Gate hardening | ok | `idea_gate.py` now requires sourced `advance`/`revise` evaluations to carry explicit `external_novelty.status`. |

### External Novelty Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/plugins/autosci/backends/novelty_review.py harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/evaluators/scientific/idea_gate.py harness/plugins/autosci/tests/test_autosci_skill_shim.py harness/tests/evaluators/scientific/test_idea_gate.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py harness/tests/evaluators/scientific/test_idea_gate.py -q` | ok: 23 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests -q` | ok: 53 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/evaluators/scientific/test_idea_gate.py harness/tests/evaluators/scientific/test_artifact_review_gate.py harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py harness/tests/evaluators/scientific/test_autosci_operator_smoke_gate.py -q` | ok: 11 passed. |
| `git diff --check -- <external novelty evidence files>` | ok |

### Remaining External Novelty Blocks

| Block | Status | Required follow-up |
|---|---|---|
| Live source fetch | pending | Add actual Web/Semantic Scholar/DeepXiv fetch operators with degraded-source evidence instead of only supplied JSON imports. |
| Source provenance gate | pending | Validate provider-specific ids, URLs, timestamps, and query metadata before allowing promotion. |
| Novelty write trust | pending | Require completed external novelty evidence, not merely local/wiki evidence, before high-confidence write-back. |

## Phase 19 Novelty Write Trust Follow-up

Logged: 2026-06-24 EDT

| Item | Status | Evidence |
|---|---|---|
| Write trust boundary | ok | `/novelty --write` now requires `external_novelty.status=completed` before mutating `wiki/ideas/{slug}.md`. |
| Local-only write behavior | ok | Local/wiki-only novelty evaluation still runs, but write-back emits an inconclusive skipped sidecar and leaves frontmatter unchanged. |
| Completed external write behavior | ok | Supplied completed external novelty evidence allows the existing approval-gated frontmatter update and wiki log append. |
| Sidecar audit | ok | `novelty_writeback.v1` records `external_novelty_status`, checked target paths, applied/skipped state, and skip reason. |

### Novelty Write Trust Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py harness/tests/evaluators/scientific/test_idea_gate.py -q` | ok: 24 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests -q` | ok: 54 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/evaluators/scientific/test_idea_gate.py harness/tests/evaluators/scientific/test_artifact_review_gate.py harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py harness/tests/evaluators/scientific/test_autosci_operator_smoke_gate.py -q` | ok: 11 passed. |
| `git diff --check -- harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |

### Remaining Novelty Write Blocks

| Block | Status | Required follow-up |
|---|---|---|
| Provider provenance | pending | Require provider/query/timestamp metadata for external novelty evidence before treating it as high-confidence. |
| Live fetch | pending | Add degraded live Web/S2/DeepXiv operators so users do not need to hand-supply novelty evidence JSON. |
| Review-coupled write | pending | Optionally require completed Review LLM evidence for promotion-grade novelty writes. |

## Phase 19 Online Novelty Fetch Follow-up

Logged: 2026-06-24 EDT

| Item | Status | Evidence |
|---|---|---|
| `/novelty --online` | ok | Added online novelty fetch request path through the shim and `native_options.online`. |
| Semantic Scholar path | ok | Online provider can query Semantic Scholar search API, with API-key header when `SEMANTIC_SCHOLAR_API_KEY` is present. |
| Web path | ok | Online provider can use Serper when `SERPER_API_KEY` is present or a configured `AUTOSCI_WEB_SEARCH_EVIDENCE_URL` endpoint. |
| DeepXiv path | ok | Online provider can use configured `AUTOSCI_DEEPXIV_SEARCH_URL`; missing endpoint is explicit provider-level unavailable state. |
| Degraded evidence | ok | Network disabled, missing credentials, unavailable endpoints, HTTP errors, and empty results produce provider statuses instead of synthetic candidates. |
| Provider audit fields | ok | `external_novelty` now carries provider statuses, query, source count, checked paths, and reason. |

### Online Novelty Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/plugins/autosci/backends/novelty_review.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py harness/tests/evaluators/scientific/test_idea_gate.py -q` | ok: 26 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests -q` | ok: 56 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/evaluators/scientific/test_idea_gate.py harness/tests/evaluators/scientific/test_artifact_review_gate.py harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py harness/tests/evaluators/scientific/test_autosci_operator_smoke_gate.py -q` | ok: 11 passed. |
| `git diff --check -- harness/plugins/autosci/backends/novelty_review.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |

### Remaining Online Novelty Blocks

| Block | Status | Required follow-up |
|---|---|---|
| Provider provenance gate | pending | Enforce provider ids, URLs/DOIs/arXiv ids, query metadata, and fetch timestamp before write-grade trust. |
| Live source smoke | pending | Run real online smoke only when network/API keys are approved in the runtime environment. |
| Review-coupled promotion | pending | Require Review LLM evidence in addition to completed external novelty evidence before final promotion. |

## Phase 19 External Novelty Provenance Gate Follow-up

Logged: 2026-06-24 EDT

| Item | Status | Evidence |
|---|---|---|
| Source identifier normalization | ok | External novelty sources now retain URL, DOI, arXiv id, Semantic Scholar id, provider, and source id metadata where supplied. |
| Provider metadata validation | ok | `external_novelty.provenance` validates provider status query metadata, fetch timestamp, and stable source identifiers. |
| Gate hardening | ok | `idea_gate.py` rejects completed external novelty evidence that lacks a provenance status. |
| Write-grade trust | ok | `/novelty --write` now requires both `external_novelty.status=completed` and `external_novelty.provenance.status=passed`. |
| Skipped write audit | ok | Missing provenance produces an inconclusive writeback sidecar and leaves wiki frontmatter/log unchanged. |

### External Novelty Provenance Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/plugins/autosci/backends/novelty_review.py harness/plugins/autosci/bin/autosci_bridge.py harness/evaluators/scientific/idea_gate.py harness/plugins/autosci/tests/test_autosci_skill_shim.py harness/tests/evaluators/scientific/test_idea_gate.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py harness/tests/evaluators/scientific/test_idea_gate.py -q` | ok: 28 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests -q` | ok: 57 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/evaluators/scientific/test_idea_gate.py harness/tests/evaluators/scientific/test_artifact_review_gate.py harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py harness/tests/evaluators/scientific/test_autosci_operator_smoke_gate.py -q` | ok: 12 passed. |
| `git diff --check -- <external novelty provenance files>` | ok |

### Remaining Provenance Blocks

| Block | Status | Required follow-up |
|---|---|---|
| Provider-specific schemas | pending | Add stricter schemas per provider, including S2 paperId/externalIds, DeepXiv ids, web URL/domain, and query hash. |
| Live smoke approval | pending | Run a real online smoke with approved API keys/network and archive provider raw evidence. |
| Review-coupled promotion | pending | Require completed Review LLM evidence in addition to write-grade novelty provenance before promoting an idea. |

## Phase 19 Review-Coupled Novelty Write Follow-up

Logged: 2026-06-24 EDT

| Item | Status | Evidence |
|---|---|---|
| Review evidence propagation | ok | `/novelty` now forwards `--review-llm-evidence` into `evaluate_ideas` instead of limiting it to `/review`. |
| Novelty review normalization | ok | Novelty evaluation now reads the existing `artifact_review.v1` Review LLM evidence shape and emits `review_llm`, `review_mode`, and `review_available`. |
| Promotion gate | ok | `/novelty --write` now requires completed external novelty evidence, passed external provenance, and completed Review LLM evidence before mutating wiki idea frontmatter. |
| Gate hardening | ok | `idea_gate.py` rejects sourced evaluations that claim `review_mode=review_llm` without `review_available=true` and completed `review_llm` evidence. |
| Audit trail | ok | `novelty_writeback.v1` records `review_llm_status` alongside external novelty and provenance status. |

### Review-Coupled Novelty Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/plugins/autosci/backends/novelty_review.py harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/evaluators/scientific/idea_gate.py harness/plugins/autosci/tests/test_autosci_skill_shim.py harness/tests/evaluators/scientific/test_idea_gate.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py harness/tests/evaluators/scientific/test_idea_gate.py -q` | ok: 30 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests -q` | ok: 58 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/evaluators/scientific/test_idea_gate.py harness/tests/evaluators/scientific/test_artifact_review_gate.py harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py harness/tests/evaluators/scientific/test_autosci_operator_smoke_gate.py -q` | ok: 13 passed. |
| `git diff --check -- harness/plugins/autosci/backends/novelty_review.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/bin/autosci_bridge.py harness/evaluators/scientific/idea_gate.py harness/plugins/autosci/tests/test_autosci_skill_shim.py harness/tests/evaluators/scientific/test_idea_gate.py` | ok |

### Remaining Review-Coupled Blocks

| Block | Status | Required follow-up |
|---|---|---|
| Direct Review LLM MCP invocation | pending | Current path accepts supplied Review LLM evidence; direct MCP execution remains unavailable in this bridge. |
| Provider-specific schemas | pending | External novelty provenance still needs stricter per-provider schemas before final parity. |
| Live smoke approval | pending | Run real online novelty and Review LLM smoke only when runtime network/API access is approved. |

## Phase 19 Provider-Specific Novelty Provenance Follow-up

Logged: 2026-06-24 EDT

| Item | Status | Evidence |
|---|---|---|
| Provider canonicalization | ok | Novelty sources now normalize provider aliases such as `s2`, `semantic scholar`, `web_search`, and `deep_xiv`. |
| Semantic Scholar schema | ok | Write-grade Semantic Scholar evidence now requires `paperId`, `externalIds.DOI`, or `externalIds.ArXiv`; URL-only S2 rows fail provenance. |
| Web schema | ok | Web evidence now requires an absolute `http(s)` URL and records URL domain metadata. |
| DeepXiv schema | ok | DeepXiv evidence now requires a DeepXiv id, DOI, arXiv id, or absolute `http(s)` URL. |
| Provenance report | ok | `external_novelty.provenance` now reports provider schemas, required provider fields, and provider-specific identifier issues. |

### Provider-Specific Novelty Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/plugins/autosci/backends/novelty_review.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py -q` | ok: 25 passed. |

### Remaining Provider-Specific Blocks

| Block | Status | Required follow-up |
|---|---|---|
| Live source smoke | pending | Run real online S2/Web/DeepXiv smoke with approved API keys/network and archive raw provider payloads. |
| Direct Review LLM MCP invocation | pending | Current novelty promotion accepts supplied Review LLM evidence; direct MCP execution remains unavailable in this bridge. |
| Provider payload archives | pending | Persist raw provider payload digests alongside normalized source rows for stronger replay/audit parity. |

## Phase 19 Novelty Provider Payload Digest Follow-up

Logged: 2026-06-24 EDT

| Item | Status | Evidence |
|---|---|---|
| Supplied payload digest | ok | Supplied `--novelty-evidence` JSON now records `raw_payload_ref`, `raw_payload_sha256`, `raw_payload_refs`, and `raw_payload_sha256s` in provider status. |
| Online payload digest | ok | Online Semantic Scholar, Web, and DeepXiv fetch paths now hash raw provider payload JSON before normalization. |
| Source provenance digest | ok | Normalized external sources now carry `raw_payload_sha256` and `raw_payload_status` in source provenance. |
| Write-grade provenance | ok | `external_novelty.provenance.required_fields` now includes `raw_payload_sha256`; missing digests fail provenance. |
| Test coverage | ok | Added assertions that supplied evidence and configured web provider paths emit 64-character SHA-256 digests. |

### Provider Payload Digest Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/plugins/autosci/backends/novelty_review.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py -q` | ok: 25 passed. |

### Remaining Provider Payload Blocks

| Block | Status | Required follow-up |
|---|---|---|
| Raw payload archive files | pending | Current fix records digests and refs; it does not yet persist copied raw payload archives into run artifacts. |
| Live smoke approval | pending | Run real online provider smoke only when network/API access is approved. |
| Direct Review LLM MCP invocation | pending | Current novelty promotion still consumes supplied Review LLM evidence rather than invoking MCP directly. |

## Phase 19 Novelty Provider Payload Archive Follow-up

Logged: 2026-06-24 EDT

| Item | Status | Evidence |
|---|---|---|
| Run-local archive dir | ok | `evaluate_ideas` now configures `external_novelty_payloads/` under the run's evaluate output directory. |
| Supplied payload archive | ok | Supplied external novelty JSON is copied into the run-local archive and linked from provider status. |
| Online payload archive | ok | Online S2/Web/DeepXiv JSON payloads are written into the same archive before source normalization. |
| Source provenance archive | ok | Normalized external source provenance now carries `raw_payload_archive_path` and `raw_payload_archive_status`. |
| Write-grade provenance | ok | Missing completed payload archive now fails `external_novelty.provenance`. |

### Provider Payload Archive Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/plugins/autosci/backends/novelty_review.py harness/plugins/autosci/bin/autosci_bridge.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py -q` | ok: 25 passed. |

### Remaining Provider Payload Archive Blocks

| Block | Status | Required follow-up |
|---|---|---|
| Live smoke approval | pending | Archive behavior is covered with supplied JSON and file-backed web provider tests; real network/API smoke still needs approval. |
| Direct Review LLM MCP invocation | pending | Current novelty promotion still consumes supplied Review LLM evidence rather than invoking MCP directly. |

## Phase 19 Novelty Payload Artifact Visibility Follow-up

Logged: 2026-06-24 EDT

| Item | Status | Evidence |
|---|---|---|
| Idea evaluation artifacts | ok | `idea_evaluation.v1` now includes `external_novelty_payload_json` artifacts for archived provider payload files. |
| Adapter passthrough | ok | `autosci_to_idea_evaluation.py` now passes raw artifacts into the Solar Evidence ABI envelope. |
| Artifact de-duplication | ok | Archive artifact paths are de-duplicated before evidence emission. |
| Test coverage | ok | Shim tests assert supplied and file-backed web novelty payload archives appear in `evaluation_evidence.artifacts`. |

### Novelty Payload Artifact Visibility Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/plugins/autosci/adapters/autosci_to_idea_evaluation.py harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py -q` | ok: 25 passed. |

### Remaining Novelty Artifact Blocks

| Block | Status | Required follow-up |
|---|---|---|
| Live smoke approval | pending | Artifact visibility is covered with local payloads; real provider payload archives still need approved network/API smoke. |
| Direct Review LLM MCP invocation | pending | Current novelty promotion still consumes supplied Review LLM evidence rather than invoking MCP directly. |

## Phase 19 Review LLM Command Bridge Follow-up

Logged: 2026-06-24 EDT

| Item | Status | Evidence |
|---|---|---|
| Explicit command bridge | ok | `/review` and `/novelty` now support `--review-llm-command` and `AUTOSCI_REVIEW_LLM_COMMAND` for direct configured Review LLM invocation. |
| Request contract | ok | The command bridge sends `review_llm_request.v1` JSON on stdin, including difficulty, focus, inputs, and review target metadata. |
| Existing output contract | ok | The command bridge must return the existing `artifact_review.v1` Review LLM JSON shape on stdout; no new review schema was introduced. |
| Failure truthfulness | ok | Missing command remains `unavailable`; non-zero exit, timeout, invalid JSON, and invalid review shape are surfaced as `failed` or `invalid`. |
| Novelty promotion | ok | `/novelty --write` can now satisfy the completed Review LLM requirement through the command bridge, not only supplied evidence files. |

### Review LLM Command Bridge Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/plugins/autosci/backends/artifact_review.py harness/plugins/autosci/backends/novelty_review.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py -q` | ok: 27 passed. |

### Remaining Review LLM Blocks

| Block | Status | Required follow-up |
|---|---|---|
| Native MCP tool exposure | pending | Current session does not expose `mcp__llm-review__chat`; the command bridge is the direct configurable invocation path until the MCP tool is available. |
| Live Review LLM smoke | pending | Needs an approved real Review LLM command/tool in the runtime environment. |

## Phase 19 Route Truthfulness Follow-up

Logged: 2026-06-24 EDT

| Item | Status | Evidence |
|---|---|---|
| Exp-design overclaim fixed | ok | `/exp-design` route is now `partial`/`route_plan`/`dry_run_only` instead of `full` while native wiki/runtime/review-backed design validation remains incomplete. |
| Operator binding aligned | ok | `exp-design` physical operator status is now `partial`; limitation no longer claims executable full parity. |
| Gate hardening | ok | `autosci_feature_parity_gate.py` now rejects `full` routes whose limitations describe fixture, smoke-only, local-surrogate, or unimplemented behavior. |
| Regression coverage | ok | Tests now assert `exp-design` is partial and full routes with fixture limitations fail parity evaluation. |

### Route Truthfulness Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/evaluators/scientific/autosci_feature_parity_gate.py harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py harness/plugins/autosci/tests/test_phase19_parity_bridge.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py -q` | ok: 4 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_phase19_parity_bridge.py -q` | ok: 4 passed. |

### Remaining Route Truthfulness Blocks

| Block | Status | Required follow-up |
|---|---|---|
| Full-route live evidence | pending | Remaining full routes still need periodic live evidence audits, especially discovery and ingest under real source conditions. |
| Operator binding audit | pending | Other partial/gated bindings should stay aligned as native capabilities become executable. |

## Phase 19 Wiki State Resolver Fallback Follow-up

Logged: 2026-06-24 EDT

| Item | Status | Evidence |
|---|---|---|
| Design target fallback | ok | Non-smoke experiment design without a resolved claim/idea/target now returns `inconclusive` with `experiment-unresolved` instead of defaulting to `idea-001`. |
| Run plan fallback | ok | Non-smoke experiment execution without experiment plan evidence now returns `inconclusive` with `experiment-unresolved` instead of defaulting to `exp-001`. |
| Monitor fallback | ok | Non-smoke experiment monitoring without plan/result evidence reports unknown state against `experiment-unresolved`. |
| Fixture compatibility | ok | Explicit fixture/smoke paths still keep deterministic `claim-001`, `idea-001`, and `exp-001` fixtures for bounded smoke tests. |
| Test coverage | ok | Bridge tests cover missing-target design and missing-plan run boundaries. |

### Wiki State Resolver Fallback Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/adapters/autosci_to_experiment_plan.py harness/plugins/autosci/tests/test_bridge_smoke.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_bridge_smoke.py -q` | ok: 16 passed. |

### Remaining Wiki Resolver Blocks

| Block | Status | Required follow-up |
|---|---|---|
| Full wiki entity resolver | pending | Experiment and paper routes still need richer lookup across wiki experiments, ideas, graph edges, and run artifacts. |
| Approved wiki mutation | pending | set-meta/add-edge/log/rebuild mutations remain approval-gated and not fully implemented. |

## Phase 19 Paper Compile Checklist Follow-up

Logged: 2026-06-24 EDT

| Item | Status | Evidence |
|---|---|---|
| Native checklist action | ok | `$paper-compile --checklist` now maps to `compile_paper` instead of route-only fallback evidence. |
| Compile diagnostics | ok | The bridge writes `paper_compile_checklist.json` and `paper_compile_diagnostics.md` with target, source, PDF, bibliography, and latexmk checks. |
| Truthful publication evidence | ok | `compile_paper` emits `publication_bundle.v1` using only files that actually exist; missing PDF/source/toolchain state remains explicit. |
| No fake compilation | ok | The path does not run latexmk, mutate sources, or claim a PDF was produced by Solar. Missing compile readiness yields `inconclusive` / schema-only action status. |
| Gate path resolution | ok | `publication_gate.py` now resolves bundle `files[].path` against the active `HARNESS_DIR` artifact root as well as the repo harness root. |

### Paper Compile Checklist Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/evaluators/scientific/publication_gate.py harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/bin/autosci_operator_smoke.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_accepts_paper_compile_checklist_without_bundle_fallback -q` | ok: 1 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests -q` | ok: 63 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/evaluators/scientific/test_idea_gate.py harness/tests/evaluators/scientific/test_artifact_review_gate.py harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py harness/tests/evaluators/scientific/test_autosci_operator_smoke_gate.py harness/tests/evaluators/scientific/test_report_gate.py -q` | ok: 18 passed. |

### Remaining Paper Compile Blocks

| Block | Status | Required follow-up |
|---|---|---|
| Real LaTeX execution | pending | Running latexmk and producing a new PDF still needs an approval-gated toolchain execution path. |
| Auto-fix mode | pending | `--fix` is recorded but not executed; source mutation should remain gated until implemented. |

## Phase 19 Wiki Mutation Layer Follow-up

Logged: 2026-06-24 EDT

| Item | Status | Evidence |
|---|---|---|
| Set-meta path | ok | Promotion-grade `/novelty --write` already updates the targeted idea frontmatter `novelty_score` only after completed external novelty evidence, passed provenance, and completed Review LLM evidence. |
| Structured add-edge | ok | Successful novelty write-back now appends a structured `novelty_evaluated` edge into `wiki/graph/edges.jsonl`. |
| Mutation log | ok | Successful write-back continues to append `wiki/log.md` with timestamp, score, idea path, and evidence ids. |
| Lightweight rebuild | ok | Successful write-back rebuilds `wiki/index.md` and `wiki/graph/context_brief.md`; the workspace projector now preserves mutation target/edge/log context after projection. |
| Truthful skip behavior | ok | Evidence gaps, failed provenance, missing Review LLM, unresolved targets, or missing YAML frontmatter still produce `novelty_writeback.v1` as `inconclusive` without mutating wiki files. |

### Wiki Mutation Layer Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_workspace_projector.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_novelty_write_updates_with_external_and_review_llm_evidence harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_novelty_write_uses_review_llm_command_bridge harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_novelty_write_skips_without_external_evidence harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_novelty_write_skips_without_review_llm_evidence -q` | ok: 4 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_projection.py -q` | ok: 1 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests -q` | ok: 63 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/evaluators/scientific/test_idea_gate.py harness/tests/evaluators/scientific/test_artifact_review_gate.py harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py harness/tests/evaluators/scientific/test_autosci_operator_smoke_gate.py harness/tests/evaluators/scientific/test_report_gate.py -q` | ok: 18 passed. |

### Remaining Wiki Mutation Blocks

| Block | Status | Required follow-up |
|---|---|---|
| General wiki edit route | pending | `/edit`, `/prefill`, `/reset`, and broad wiki/raw mutations remain approval-gated and route-scoped; this follow-up only completes the novelty promotion write path. |
| Destructive mutations | pending | Delete/reset/rebuild actions still need explicit confirmation and before/after evidence before implementation. |

## Phase 19 Experiment Lifecycle Collect Follow-up

Logged: 2026-06-24 EDT

| Item | Status | Evidence |
|---|---|---|
| Collect option routing | ok | `$exp-run --collect` now maps to a bounded `monitor_experiment` diagnostics action instead of emitting route-only evidence. |
| No fake execution | ok | Collect mode does not deploy, run code, SSH, rsync, or pull remote files; missing runtime artifacts remain `unknown` / `inconclusive`. |
| Target preservation | ok | Non-smoke collect diagnostics preserve the explicit experiment target instead of falling back to `exp-001` unless the user supplied that target. |
| Gate truthfulness | ok | Missing result evidence now produces `experiment_status.v1` with top-level `status: inconclusive`, yielding schema-only action status rather than a false pass. |
| Native options surfaced | ok | `env` and `collect` remain visible in native options and monitor inputs for follow-up approved collection. |

### Experiment Lifecycle Collect Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_accepts_exp_run_native_options_without_fixture_fallback harness/plugins/autosci/tests/test_bridge_smoke.py::test_phase12_design_run_and_monitor_experiment_write_native_evidence harness/plugins/autosci/tests/test_bridge_smoke.py::test_phase12_run_without_plan_does_not_default_to_exp_001 -q` | ok: 3 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/evaluators/scientific/test_experiment_status_gate.py -q` | ok: 2 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests -q` | ok: 63 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/evaluators/scientific/test_idea_gate.py harness/tests/evaluators/scientific/test_artifact_review_gate.py harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py harness/tests/evaluators/scientific/test_autosci_operator_smoke_gate.py harness/tests/evaluators/scientific/test_report_gate.py harness/tests/evaluators/scientific/test_experiment_status_gate.py -q` | ok: 20 passed. |

### Remaining Experiment Lifecycle Blocks

| Block | Status | Required follow-up |
|---|---|---|
| Approved run execution | pending | Actual local/remote experiment execution remains approval-gated and requires concrete command allowlists, resource limits, and runtime artifacts. |
| Approved result retrieval | pending | Remote collect/pull-results still needs an approved tool path plus before/after artifact evidence. |

## Phase 19 Publication And Report Native Sidecar Follow-up

Logged: 2026-06-24 EDT

| Item | Status | Evidence |
|---|---|---|
| Paper plan action | ok | `$paper-plan` now runs `plan_report` and emits `scientific_report.v1` plus paper plan JSON/Markdown sidecars. |
| Survey action | ok | `$survey` now runs `write_survey` and emits `scientific_report.v1` plus survey plan/Markdown sidecars. |
| Rebuttal action | ok | `$rebuttal` now runs `draft_rebuttal` and emits `publication_bundle.v1` with rebuttal Markdown and response-map JSON. |
| Poster action | ok | `$poster` now runs `build_poster` and emits `publication_bundle.v1` with local poster HTML and validation JSON. |
| Truthful status | ok | Request-only targets remain `inconclusive` / schema-only; only real source evidence payloads can promote report sidecar status beyond scaffold. |

### Publication And Report Sidecar Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/bin/autosci_operator_smoke.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_accepts_paper_plan_title_without_topic_fallback harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_runs_survey_rebuttal_and_poster_native_sidecars -q` | ok: 2 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests -q` | ok: 64 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/evaluators/scientific/test_report_gate.py harness/tests/evaluators/scientific/test_autosci_operator_smoke_gate.py harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py -q` | ok: 10 passed. |

### Remaining Publication And Report Blocks

| Block | Status | Required follow-up |
|---|---|---|
| Browser/poster rendering | pending | Poster HTML is generated, but browser overflow probe and PNG export remain approval/environment-gated. |
| Citation expansion | pending | Survey and paper plan sidecars do not imply live citation expansion or exhaustive literature coverage. |
| Review stress-test | pending | Rebuttal stress-test still needs Review LLM evidence or an approved Review LLM command/tool. |

## Phase 19 Wiki And Control Proposal Follow-up

Logged: 2026-06-24 EDT

| Item | Status | Evidence |
|---|---|---|
| Prefill proposal action | ok | `$prefill` now runs `prefill_foundations` and emits `research_memory_update.v1` proposed foundation-page evidence without mutating wiki files. |
| Edit proposal action | ok | `$edit` now runs `edit_wiki_plan` and emits `research_memory_update.v1` bounded edit-plan evidence without set-meta/add-edge side effects. |
| Setup status action | ok | `$setup` now runs `setup_status` and emits `workflow_evolution.v1` setup checklist/proposal evidence without writing secrets or config. |
| Reset plan action | ok | `$reset` now runs `reset_plan` and emits `workflow_evolution.v1` reset checklist/proposal evidence without destructive deletes. |
| Approval controls | ok | Setup/reset proposal evidence includes manual and gate changes, human approval controls, recommended-changes Markdown, and patch-candidates directory. |

### Wiki And Control Proposal Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/bin/autosci_operator_smoke.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_runs_wiki_and_control_proposal_actions harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_keeps_setup_gated -q` | ok: 2 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests -q` | ok: 65 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/evaluators/scientific/test_idea_gate.py harness/tests/evaluators/scientific/test_artifact_review_gate.py harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py harness/tests/evaluators/scientific/test_autosci_operator_smoke_gate.py harness/tests/evaluators/scientific/test_report_gate.py harness/tests/evaluators/scientific/test_experiment_status_gate.py harness/tests/evaluators/scientific/test_workflow_evolution_gate.py -q` | ok: 22 passed. |

### Remaining Wiki And Control Blocks

| Block | Status | Required follow-up |
|---|---|---|
| Approved wiki apply | pending | Proposed edit/prefill evidence still needs explicit approval and before/after evidence before mutating wiki/raw files. |
| Secret/config writes | pending | Setup remains proposal-only until the user supplies exact values and approves the write scope. |
| Destructive reset | pending | Reset remains proposal-only until explicit destructive confirmation and rollback evidence are available. |

## Phase 19 Ask Check Init Diagnostic Follow-up

Logged: 2026-06-24 EDT

| Item | Status | Evidence |
|---|---|---|
| Ask diagnostic action | ok | `$ask` now runs `ask_wiki`, writes an answer Markdown artifact, and emits `research_memory_update.v1` no-op evidence marked `inconclusive` until retrieval/model evidence exists. |
| Check diagnostic action | ok | `$check` now runs `check_wiki_health` and emits `workflow_evolution.v1` wiki-health proposal evidence with approval controls. |
| Init diagnostic action | ok | `$init` now runs `init_sources` and emits `literature_discovery.v1` init-plan evidence marked `inconclusive` when no candidates/source manifests are available. |
| Adapter truthfulness | ok | `research_memory_update.v1` adapter now preserves raw `status` and `artifacts`, allowing diagnostics to stay schema-only instead of defaulting to completed. |

### Ask Check Init Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/plugins/autosci/adapters/autosci_to_research_memory_update.py harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/bin/autosci_operator_smoke.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_runs_ask_check_and_init_diagnostics -q` | ok: 1 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests -q` | ok: 66 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/evaluators/scientific/test_idea_gate.py harness/tests/evaluators/scientific/test_artifact_review_gate.py harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py harness/tests/evaluators/scientific/test_autosci_operator_smoke_gate.py harness/tests/evaluators/scientific/test_report_gate.py harness/tests/evaluators/scientific/test_experiment_status_gate.py harness/tests/evaluators/scientific/test_workflow_evolution_gate.py -q` | ok: 22 passed. |

### Remaining Ask Check Init Blocks

| Block | Status | Required follow-up |
|---|---|---|
| Ask model synthesis | pending | `$ask` still needs retrieval-backed model synthesis and confidence calibration before completed answer evidence. |
| Check content quality | pending | `$check` structural proposal does not imply LLM quality review without supplied model output evidence. |
| Init bulk fetch | pending | `$init` still needs approved network/source fetch and fan-in ingest before completed discovery evidence. |

## Phase 19 Remaining Backend Action Mapping Follow-up

Logged: 2026-06-24 EDT

| Item | Status | Evidence |
|---|---|---|
| Daily arXiv action | ok | `$daily-arxiv` now runs `daily_arxiv_prepare_finalize` and emits `literature_discovery.v1` plan evidence without network/email/auto-ingest side effects. |
| Pilot eval action | ok | `$exp-pilot-eval` now runs `evaluate_pilot_result` and emits `claim_verdict.v1` inconclusive evidence until pilot result evidence is supplied. |
| Pilot run action | ok | `$exp-pilot-run` now runs `run_pilot_experiment` and emits `experiment_result.v1` inconclusive diagnostics without local/remote execution. |
| Refine action | ok | `$refine` now runs `refine_artifact` and emits `workflow_evolution.v1` proposed-only refinement evidence. |
| Research lifecycle action | ok | `$research` now runs `run_research_lifecycle` and emits `workflow_evolution.v1` lifecycle proposal evidence instead of route-only fallback. |
| Visualize action | ok | `$visualize` now runs `visualize_graph` and emits `research_graph_update.v1` visualization proposal evidence without serving/opening UI. |
| Backend action coverage | ok | All configured `solar_backend_action` values in `feature_parity_routes.v1.json` now have bridge action handlers. |

### Remaining Backend Action Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/plugins/autosci/adapters/autosci_to_research_memory_update.py harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/bin/autosci_operator_smoke.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_runs_remaining_gated_backend_actions -q` | ok: 1 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests -q` | ok: 67 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/evaluators/scientific/test_idea_gate.py harness/tests/evaluators/scientific/test_artifact_review_gate.py harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py harness/tests/evaluators/scientific/test_autosci_operator_smoke_gate.py harness/tests/evaluators/scientific/test_report_gate.py harness/tests/evaluators/scientific/test_experiment_status_gate.py harness/tests/evaluators/scientific/test_workflow_evolution_gate.py -q` | ok: 22 passed. |
| `backend action coverage script` | ok: `missing_count: 0`. |

### Remaining Full-Parity Blocks

| Block | Status | Required follow-up |
|---|---|---|
| External side effects | pending | Network fetch, SMTP, browser/UI serving, local/remote experiment execution, and destructive reset still require explicit approval and runtime evidence. |
| Completed intelligence outputs | pending | Ask synthesis, check quality review, citation expansion, Review LLM stress-test, and full lifecycle orchestration need actual model/source evidence before completed status. |

## Phase 19 Wiki Retrieval And Graph Gate Follow-up

Logged: 2026-06-24 EDT

| Item | Status | Evidence |
|---|---|---|
| Ask wiki retrieval | ok | `$ask` now performs local lexical retrieval over workspace wiki Markdown and writes `ask_wiki_retrieval.json` plus answer Markdown with source snippets. |
| Ask truthfulness | ok | `$ask` remains `inconclusive` until model synthesis/confidence evidence is supplied; retrieval is not presented as a completed answer. |
| Wiki health diagnostics | ok | `$check` now inspects wiki root existence, expected subdirectories, Markdown page count, and `graph/edges.jsonl` JSON/field validity. |
| Wiki-root routing | ok | `--wiki-root` now propagates into ask/check/init diagnostic actions. |
| Graph update gate | ok | Added deterministic `research_graph_update.v1` gate and registered it in operator smoke; graph update and visualize proposal evidence are now gate-checked. |

### Wiki Retrieval And Graph Gate Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/evaluators/scientific/graph_update_gate.py harness/plugins/autosci/adapters/autosci_to_research_memory_update.py harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/bin/autosci_operator_smoke.py harness/plugins/autosci/tests/test_autosci_skill_shim.py harness/plugins/autosci/tests/test_phase19_operator_smoke.py harness/tests/evaluators/scientific/test_graph_update_gate.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_runs_ask_check_and_init_diagnostics harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_ask_and_check_read_workspace_wiki -q` | ok: 2 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/evaluators/scientific/test_graph_update_gate.py harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_runs_remaining_gated_backend_actions -q` | ok: 3 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests -q` | ok: 68 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/evaluators/scientific/test_idea_gate.py harness/tests/evaluators/scientific/test_artifact_review_gate.py harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py harness/tests/evaluators/scientific/test_autosci_operator_smoke_gate.py harness/tests/evaluators/scientific/test_report_gate.py harness/tests/evaluators/scientific/test_experiment_status_gate.py harness/tests/evaluators/scientific/test_workflow_evolution_gate.py harness/tests/evaluators/scientific/test_graph_update_gate.py -q` | ok: 24 passed. |

### Remaining Wiki Retrieval And Graph Blocks

| Block | Status | Required follow-up |
|---|---|---|
| Ask synthesis | pending | Lexical retrieval still needs model synthesis and confidence/review evidence before completed answer status. |
| Check content review | pending | Structural wiki health does not replace LLM-assisted content quality checks. |
| Visualization rendering | pending | Graph update proposals are gate-checked, but Canvas/browser rendering remains approval-gated. |

## Phase 19 Approval Runtime Contract Follow-up

Logged: 2026-06-24 EDT

| Item | Status | Evidence |
|---|---|---|
| CLI approval inputs | ok | `autosci_skill_shim.py` now accepts `--approval-ref`, `--allowlist-evidence`, `--runtime-evidence`, `--before-artifact`, and `--after-artifact`, and forwards them into bridge envelopes plus `native_options`. |
| Approval contract sidecar | ok | `autosci_bridge.py` now writes `autosci_approval_contract.v1` JSON sidecars with action, side effects, approval ref, allowlist/runtime/before/after artifact paths, readiness flags, and explicit missing fields. |
| Gated source fetch paths | ok | `$init` and `$daily-arxiv` now attach approval contract artifacts instead of only prose limitations for network fetch, digest send, auto-ingest, and wiki fan-in paths. |
| Gated execution paths | ok | `$exp-pilot-run`, `$paper-compile`, `$poster`, `$setup`, `$reset`, `$refine`, `$research`, and `$visualize` now attach approval contract evidence for their protected runtime, browser, compile, mutation, or lifecycle side effects. |
| Truthfulness guard | ok | Approval evidence does not mark these actions as completed; poster/browser rendering, pilot execution, compile execution, and lifecycle mutation remain inconclusive or proposed-only unless real runtime artifacts are supplied and separately interpreted. |
| Graph artifact preservation | ok | `research_graph_update.v1` adapter now preserves raw `artifacts` and `status`, allowing visualization approval contracts to remain visible to gates and smoke tests. |

### Approval Runtime Contract Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/adapters/autosci_to_research_graph_update.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py -q` | ok: 33 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests -q` | ok: 69 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/evaluators/scientific/test_artifact_review_gate.py harness/tests/evaluators/scientific/test_claim_verdict_gate.py harness/tests/evaluators/scientific/test_claims_gate.py harness/tests/evaluators/scientific/test_code_evidence_gate.py harness/tests/evaluators/scientific/test_experiment_plan_gate.py harness/tests/evaluators/scientific/test_experiment_result_gate.py harness/tests/evaluators/scientific/test_experiment_status_gate.py harness/tests/evaluators/scientific/test_graph_update_gate.py harness/tests/evaluators/scientific/test_idea_gate.py harness/tests/evaluators/scientific/test_lifecycle_gate.py harness/tests/evaluators/scientific/test_report_gate.py harness/tests/evaluators/scientific/test_workflow_evolution_gate.py -q` | ok: 38 passed. |
| `env PYTHONPATH=harness HARNESS_DIR=/tmp/autosci-operator-smoke harness/bin/python3 harness/plugins/autosci/bin/autosci_operator_smoke.py skillgen --out /tmp/autosci-operator-smoke/operator_smoke.json` | ok: 28 routes, 28 bound, 0 failed, 10 gated. |
| `git diff --check -- harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/adapters/autosci_to_research_graph_update.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |

### Remaining Approval Runtime Blocks

| Block | Status | Required follow-up |
|---|---|---|
| Semantic runtime verification | ok | Implemented in the Semantic Runtime Verification follow-up below; remaining work is schema hardening and real executors. |
| Real side-effect executors | pending | Network fetch, SMTP, browser render/export, latexmk compile, local/remote pilot execution, and destructive reset remain blocked unless a separate approved executor is implemented. |
| Full lifecycle orchestration | pending | `$research` still emits a workflow proposal; it does not yet orchestrate every native AutoSci stage into one real multi-step run. |

## Phase 19 Semantic Runtime Verification Follow-up

Logged: 2026-06-24 EDT

| Item | Status | Evidence |
|---|---|---|
| Runtime parser layer | ok | `autosci_bridge.py` now loads supplied runtime evidence JSON/text and writes `autosci_runtime_semantic_verification.v1` results into approval contract sidecars. |
| Daily arXiv semantic verification | ok | `$daily-arxiv` can now promote to completed `literature_discovery.v1` only when approved runtime evidence has successful fetch status and non-empty candidate papers. |
| Init source semantic verification | ok | `$init` shares the same candidate parser for approved runtime source manifests while remaining inconclusive without semantic candidate evidence. |
| Pilot runtime verification | ok | `$exp-pilot-run` can now map approved runtime `exit_code`, `outcome`, and `metrics` into completed `experiment_result.v1`; otherwise it remains inconclusive. |
| Poster runtime verification | ok | `$poster` now checks approved runtime evidence for browser render, overflow pass, and PNG export, and records the semantic result in `poster_validation.json`. |
| Paper compile runtime verification | ok | `$paper-compile` now checks approved runtime evidence for compile exit success and generated/existing PDF evidence before marking compile runtime semantics as verified. |
| Truthfulness guard | ok | Verified runtime evidence still does not mean the bridge itself executed the side effect; limitations explicitly state the bridge verified supplied evidence and did not launch network/browser/latex/experiment commands. |

### Semantic Runtime Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_records_approval_runtime_contract_for_gated_actions harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_uses_semantic_runtime_evidence_for_gated_results harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_runs_remaining_gated_backend_actions harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_accepts_paper_compile_checklist_without_bundle_fallback -q` | ok: 4 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests -q` | ok: 70 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/evaluators/scientific -q` | ok: 47 passed. |
| `env PYTHONPATH=harness HARNESS_DIR=/tmp/autosci-operator-smoke harness/bin/python3 harness/plugins/autosci/bin/autosci_operator_smoke.py skillgen --out /tmp/autosci-operator-smoke/operator_smoke_semantic.json` | ok: 28 routes, 28 bound, 0 failed, 10 gated. |
| `git diff --check -- docs/integrations/autosci/phase19-progress-log.md harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |

### Remaining Semantic Runtime Blocks

| Block | Status | Required follow-up |
|---|---|---|
| Real side-effect executors | warn | Paper compile now has an approved latexmk executor; network fetch, SMTP, browser render/export, remote execution, and destructive reset executors remain pending. |
| Runtime schema hardening | ok | Implemented in the Runtime Schema And Compile Executor follow-up below. |
| Full lifecycle orchestration | pending | `$research` still needs orchestration across discovery, ideation, novelty/review, experiment, report, and publication stages. |

## Phase 19 Runtime Schema And Compile Executor Follow-up

Logged: 2026-06-24 EDT

| Item | Status | Evidence |
|---|---|---|
| Runtime evidence ABI | ok | Added `autosci_runtime_evidence.v1` schema for approval-gated runtime outputs with action, approval ref, command, exit code, checks, candidates, metrics, poster render fields, and compile PDF fields. |
| Runtime evidence gate | ok | Added `autosci_runtime_evidence_gate.py` with action-specific completed checks for source fetch, pilot run, poster render/export, and paper compile. |
| Bridge ABI consumption | ok | `autosci_bridge.py` now reads formal runtime evidence from `outputs.runtime` while retaining compatibility with simpler JSON runtime files. |
| Paper compile executor | ok | `$paper-compile --execute-approved` can now run an implemented local latexmk executor only when approval, allowlist evidence, and before artifact preflight are present. |
| Compile executor provenance | ok | The executor writes `autosci_runtime_evidence.v1`, stdout/stderr sidecars, compiled PDF artifact entries, and routes the result back through the approval contract and semantic runtime verifier. |
| Default safety | ok | `$paper-compile` default behavior is unchanged; no latexmk command runs unless the user passes `--execute-approved` and satisfies preflight. |

### Runtime Schema And Compile Executor Verification Commands

| Command | Result |
|---|---|
| `python3 -m json.tool harness/schemas/evidence/autosci_runtime_evidence.v1.schema.json` | ok |
| `harness/bin/python3 -m py_compile harness/evaluators/scientific/autosci_runtime_evidence_gate.py harness/tests/evaluators/scientific/test_autosci_runtime_evidence_gate.py harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/evaluators/scientific/test_autosci_runtime_evidence_gate.py harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_uses_semantic_runtime_evidence_for_gated_results harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_records_approval_runtime_contract_for_gated_actions -q` | ok: 6 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_executes_approved_paper_compile_executor harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_uses_semantic_runtime_evidence_for_gated_results harness/tests/evaluators/scientific/test_autosci_runtime_evidence_gate.py -q` | ok: 6 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests -q` | ok: 71 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/evaluators/scientific -q` | ok: 51 passed. |
| `env PYTHONPATH=harness HARNESS_DIR=/tmp/autosci-operator-smoke harness/bin/python3 harness/plugins/autosci/bin/autosci_operator_smoke.py skillgen --out /tmp/autosci-operator-smoke/operator_smoke_compile_executor.json` | ok: 28 routes, 28 bound, 0 failed, 10 gated. |
| `git diff --check -- docs/integrations/autosci/phase19-progress-log.md harness/schemas/evidence/autosci_runtime_evidence.v1.schema.json harness/evaluators/scientific/autosci_runtime_evidence_gate.py harness/tests/evaluators/scientific/test_autosci_runtime_evidence_gate.py harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |

### Remaining Runtime Executor Blocks

| Block | Status | Required follow-up |
|---|---|---|
| Browser/poster executor | ok | Implemented in the Poster Approved Executor follow-up below. |
| Source fetch/email executors | pending | Daily arXiv/source initialization can verify supplied runtime evidence, but network fetch and email send executors are not implemented. |
| Pilot executor | pending | Pilot runtime verification exists, but local/remote process execution and result collection executor are not implemented. |
| Destructive/control executors | pending | Setup/reset/refine/research lifecycle mutation executors remain proposal-only and approval-gated. |
| Full lifecycle orchestration | pending | `$research` still needs orchestration across discovery, ideation, novelty/review, experiment, report, and publication stages. |

## Phase 19 Wiki State Resolver Follow-up

Logged: 2026-06-24 EDT

| Item | Status | Evidence |
|---|---|---|
| Wiki-first resolver ABI | ok | Added a read-only `autosci_wiki_state_resolver.v1` sidecar from `autosci_bridge.py` for `ideas`, `experiments`, `outputs`, and `graph/edges.jsonl`. |
| Frontmatter/entity parsing | ok | Resolver now records slug/id/title/status, idea `novelty_score`, `linked_experiments`, experiment `run_log`, `run_log_exists`, and output links. |
| Graph edge parsing | ok | Resolver parses JSONL graph edges with source/target/relation/evidence ids, records invalid rows separately, and enriches linked experiments/outputs from graph edges. |
| Target truthfulness | ok | Resolver records `resolution.target_type`, `target_id`, `target_path`, and `fallback_used=false`; unresolved targets stay `unresolved` rather than silently becoming `idea-001` or `exp-001`. |
| Action integration | ok | `generate_ideas`, `evaluate_ideas`, `design_experiment`, and `monitor_experiment` now attach the resolver sidecar when wiki/target inputs are present. |
| Novelty target sourcing | ok | `$novelty` can now create the evaluated idea from a resolved wiki idea when no upstream `idea_candidate.v1` evidence exists. |
| Experiment status sourcing | ok | `$exp-status` can now resolve the experiment id from wiki experiment state before falling back to unresolved status. |
| Adapter propagation | ok | `idea_candidate.v1` and `experiment_plan.v1` adapters now preserve action artifacts so resolver evidence is visible to gates and pane output. |
| Gate hardening | ok | `idea_gate.py` now treats `source_mode=wiki_state` as sourced evidence, so wiki-resolved novelty evaluations must still carry closest-prior, review score/mode, and external novelty status. |

### Wiki State Resolver Verification Commands

| Command | Result |
|---|---|
| `python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/adapters/autosci_to_idea_candidate.py harness/plugins/autosci/adapters/autosci_to_experiment_plan.py` | ok |
| `.venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_wiki_state_resolver_parses_entities_and_edges harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_exp_status_resolves_wiki_experiment_without_default_fallback -q` | ok: 2 passed. |
| `.venv/bin/python -m pytest harness/plugins/autosci/tests -q` | ok: 74 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific -q` | ok: 51 passed. |
| `.venv/bin/python harness/plugins/autosci/bin/autosci_operator_smoke.py skillgen` | ok: 28 routes, 28 bound, 0 failed, 10 gated. |
| `.venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci_feature_parity_wiki_state.json` | ok: 28 routed, 0 missing, 2 full, 16 partial, 10 gated. |
| `env PYTHONPATH=harness .venv/bin/python harness/evaluators/scientific/autosci_feature_parity_gate.py /tmp/autosci_feature_parity_wiki_state.json` | ok: passed with non-full route warning. |
| `env PYTHONPATH=harness .venv/bin/python harness/evaluators/scientific/autosci_operator_smoke_gate.py harness/artifacts/autosci/operator-smoke/skillgen/autosci_operator_smoke.json` | ok: passed with approval-gated warning. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific/test_idea_gate.py -q` | ok: 7 passed after wiki-state gate hardening. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific -q` | ok: 52 passed after wiki-state gate hardening. |

### Remaining Wiki/State Blocks

| Block | Status | Required follow-up |
|---|---|---|
| Mutation layer | pending | Real set-meta/add-edge/log/rebuild operations still only exist in bounded novelty writeback paths; generic wiki mutation remains proposal/approval gated. |
| Strict lifecycle state machine | pending | Resolver reads state, but `$research` still does not orchestrate native state transitions across discovery, ideation, novelty/review, experiment, report, and publication. |
| Rich YAML parsing | warn | Resolver intentionally supports scalar and simple list frontmatter only; complex YAML/nested metadata needs a structured parser or schema-backed wiki writer. |
| Quality gates | pending | Resolver improves state truthfulness but does not replace idea quality, novelty, review, experiment validity, or publication compile gates. |

## Phase 19 Poster Approved Executor Follow-up

Logged: 2026-06-24 EDT

| Item | Status | Evidence |
|---|---|---|
| Poster executor | ok | `$poster --execute-approved` can now run an allowlisted poster renderer only after approval ref, allowlist evidence, and before artifact preflight are present. |
| Renderer command contract | ok | Allowlist evidence can provide `poster_render_command` with `{html}`, `{png}`, and `{validation}` placeholders, or `poster_renderer` as an executable receiving those three paths. |
| Runtime ABI output | ok | The poster executor writes `autosci_runtime_evidence.v1`, stdout/stderr sidecars, PNG artifact, and executor validation JSON. |
| Semantic verification loop | ok | Executor output is fed back through the approval contract and existing poster semantic verifier for browser render, overflow probe, and PNG export checks. |
| Default safety | ok | `$poster` default behavior is unchanged; no renderer command runs unless `--execute-approved` is supplied and preflight passes. |
| Truthfulness guard | ok | Without source report/evidence payload, poster evidence remains `inconclusive` even when render/export runtime is verified. |

### Poster Approved Executor Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_executes_approved_poster_executor harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_records_approval_runtime_contract_for_gated_actions harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_runs_survey_rebuttal_and_poster_native_sidecars -q` | ok: 3 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests -q` | ok: 72 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/evaluators/scientific -q` | ok: 51 passed. |
| `env PYTHONPATH=harness HARNESS_DIR=/tmp/autosci-operator-smoke harness/bin/python3 harness/plugins/autosci/bin/autosci_operator_smoke.py skillgen --out /tmp/autosci-operator-smoke/operator_smoke_poster_executor.json` | ok: 28 routes, 28 bound, 0 failed, 10 gated. |
| `git diff --check -- docs/integrations/autosci/phase19-progress-log.md harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |

### Remaining Executor Blocks After Poster

| Block | Status | Required follow-up |
|---|---|---|
| Source fetch/email executors | pending | Daily arXiv/source initialization can verify supplied runtime evidence, but network fetch and email send executors are not implemented. |
| Pilot executor | pending | Pilot runtime verification exists, but local/remote process execution and result collection executor are not implemented. |
| Destructive/control executors | pending | Setup/reset/refine/research lifecycle mutation executors remain proposal-only and approval-gated. |
| Full lifecycle orchestration | pending | `$research` still needs orchestration across discovery, ideation, novelty/review, experiment, report, and publication stages. |

## Phase 19 Parity Log Coverage Audit

Logged: 2026-06-25 EDT

This audit cross-checked the current AutoSci/Solar parity-related dirty paths against the Phase 19 log. The goal was not to add new behavior, but to confirm that prior parity work is recorded in the log with its verification evidence and remaining limitations.

| Change group | Status | Log coverage |
|---|---|---|
| Codex entry, model, and worktree default behavior | ok | Covered by Dollar Skill Compatibility, Solar Skill Projection, Lab Worktree Skill Discovery, Codex Pane Worktree Default, and Worktree Sync/Cleanup follow-ups. These sections record direct AutoSci `$...` intake routing, 28 projected skills, main-checkout pane defaults, worktree cleanup, and model config guard checks including `gpt-5.5`. |
| Native command protocol and fixture boundary | ok | Covered by Native Command Contract and Smoke Boundary. The log records native flags such as `--env`, `--collect`, `--title`, `--checklist`, `--max-ideas`, `--skip-validation`, `--skip-pilot`, approval/runtime flags, and the explicit-smoke rule for fixture fallback. |
| Source preparation and discovery | ok | Covered by PDF/arXiv Source Preparation and Discover Command Compatibility. The log records PDF/local/remote source preparation, raw archive evidence, wiki discovery mode, citation expansion limitations, and literature discovery gate coverage. |
| Ideate, novelty, review, and Review LLM paths | ok | Covered by Real Ideate Sourcing, Local Novelty/Review Signal, Novelty Writeback, Standalone Review, Review LLM Evidence State, External Novelty Evidence, Novelty Write Trust, Online Novelty Fetch, External Novelty Provenance, Review-Coupled Novelty Write, Provider-Specific Novelty Provenance, Provider Payload Digest/Archive, Novelty Payload Artifact Visibility, and Review LLM Command Bridge follow-ups. |
| Wiki resolver, mutation, retrieval, and graph gates | ok | Covered by Wiki State Resolver Fallback, Wiki Mutation Layer, Wiki Retrieval And Graph Gate, and Wiki State Resolver follow-ups. The log records no-default `idea-001`/`exp-001` fallback, read-only resolver sidecars, graph edge parsing, wiki writeback boundaries, and remaining mutation/state-machine gaps. |
| Experiment lifecycle and runtime approval | ok | Covered by Experiment Lifecycle Collect, Approval Runtime Contract, Semantic Runtime Verification, Runtime Schema And Compile Executor, and Poster Approved Executor follow-ups. The log records collect diagnostics, approval contracts, semantic runtime verification, formal runtime evidence ABI/gate, approved compile executor, and approved poster executor. |
| Paper/report/publication pipeline | ok | Covered by Paper Compile Checklist, Publication And Report Native Sidecar, Runtime Schema And Compile Executor, and Poster Approved Executor follow-ups. The log records checklist diagnostics, report plan/markdown/evidence-index sidecars, publication bundle truthfulness, latexmk gating, and no-PDF/no-submission limitations when runtime evidence is absent. |
| Route truthfulness and backend mapping | ok | Covered by Route Truthfulness and Remaining Backend Action Mapping. The log records coverage-status downgrades, full-route guardrails, all configured `solar_backend_action` handlers, and remaining non-full parity blocks. |
| Evidence schemas, gates, adapters, fixtures, and tests | ok | Covered throughout each follow-up's implementation and verification command tables. The changed schema/gate/adapter/test groups are recorded by file or by functional group, including `autosci_skill_run`, `artifact_review`, `experiment_status`, `graph_update`, `literature_discovery`, `publication_bundle`, `workflow_evolution`, `autosci_runtime_evidence`, and the AutoSci bridge/shim tests. |

### Coverage Audit Commands

| Command | Result |
|---|---|
| `bash harness/solar-harness.sh context inject --query "AutoSci parity progress log completeness audit changed files phase19 log coverage" --format markdown` | ok: Solar unified context loaded; source degraded to local Mirage/QMD/DB context. |
| `git status --short -- docs/integrations/autosci/phase19-progress-log.md harness/plugins/autosci harness/evaluators/scientific harness/schemas/evidence harness/tests/evaluators/scientific` | ok: enumerated current AutoSci parity-related tracked and untracked dirty paths for coverage checking. |
| `rg -n "^## Phase 19|^### Remaining|autosci_runtime_evidence|autosci_skill_shim|autosci_bridge|idea_gate|test_idea_gate|test_autosci_skill_shim|autosci_to_idea_candidate|autosci_to_experiment_plan|Wiki State Resolver|Runtime Schema|Poster Approved|Compile Executor|approval|semantic|novelty|review|collect|paper compile|checklist|route truthfulness|model|gpt-5.5|worktree" docs/integrations/autosci/phase19-progress-log.md` | ok: found matching log coverage across all parity workstreams. |
| `git diff --name-only -- docs/integrations/autosci/phase19-progress-log.md harness/plugins/autosci harness/evaluators/scientific harness/schemas/evidence harness/tests/evaluators/scientific` | ok: tracked AutoSci parity diffs are covered by existing Phase 19 sections or by this audit section. |

### Coverage Audit Exclusions

| Path group | Status | Reason |
|---|---|---|
| `.DS_Store`, watchdog pid/session files, pane logs, generated run artifacts | excluded | Local/runtime noise, not parity implementation. |
| AI Influence, Tech Hotspot Radar, report validation, PM dispatch, and unrelated selector/report files outside the AutoSci parity path | excluded | Present in the dirty worktree but not part of the AutoSci parity workstream being audited here. |
| Untracked generated `harness/artifacts/autosci/` run outputs | excluded | Execution artifacts used for verification; not implementation changes. |

### Coverage Audit Result

| Finding | Status | Notes |
|---|---|---|
| Unlogged AutoSci parity implementation group | ok | No unlogged AutoSci parity implementation group was found in the audited path set. |
| Remaining parity gaps | ok | Remaining gaps are already logged as pending/warn blocks: full lifecycle orchestration, real source/email/pilot/control executors, generic wiki mutation, richer YAML/wiki schemas, Review LLM stress coverage, and completed ask/check intelligence outputs. |
| Commit readiness | warn | The repository still contains many unrelated dirty/untracked files; do not treat this audit as a safe commit boundary without a separate staging review. |

## Phase 19 Audit-Adjusted Parity Completion

Logged: 2026-06-25 EDT

This update incorporates the migrated runtime audit at
`docs/integrations/autosci/audit/migrated-autosci-parity-audit-2026-06-25.md`
and the current route/operator smoke inventory. The audit shows that the
migrated AutoSci runtime is not full parity yet, so route completion is now
reported as bound-but-partial/gated rather than completed.

| Completion measure | Status | Current value | Evidence |
|---|---|---:|---|
| Native skills/routes bound | ok | 28 / 28 | Current parity inventory and operator smoke both bind all native AutoSci skills to Solar routes. |
| Missing routes | ok | 0 | No native skill is missing from `feature_parity_routes.v1.json`. |
| Full route coverage | warn | 0 | The audit invalidated `full` claims for migrated runtime parity because source-grounded end-to-end runs still fail or remain fixture/schema-only. |
| Partial route coverage | warn | 18 | Non-gated routes are now classified as partial until source evidence, wiki state, review, experiment, and publication blocks run natively. |
| Approval-gated routes | pending | 10 | Side-effecting routes remain gated until approved runtime executors are supplied and verified. |
| Native full runtime stages | error | 0 / 23 | Audit YAML summary reports no fully native completed runtime stage. |
| Runtime final verdict | error | failed | End-to-end `$research` did not complete; SkillGen ingest, experiment deploy, paper compile, and resume/status behavior failed or were incomplete. |

### Audit-Driven Route Truthfulness Changes

| Route | Status | Change |
|---|---|---|
| `/discover` | warn | Downgraded from `full` to `partial` because the audit observed `/discover --from-wiki --limit 10` as schema-only/inconclusive rather than live/wiki-grounded shortlist evidence. |
| `/ingest` | warn | Downgraded from `full` to `partial` because SkillGen PDF semantic ingestion failed and fixture abstract leakage was observed. |
| `/exp-design`, `/exp-status`, `/ideate`, `/paper-plan`, `/paper-draft` | warn | Remain partial in the current route config; they are useful bridge paths but not full native AutoSci parity. |
| `/review` | warn | Bound to the artifact review operator/schema, but still partial until independent Review LLM evidence is present. |

### Audit-Adjusted Remaining Blocks

| Block | Status | Required follow-up |
|---|---|---|
| Native CLI protocol | error | Finish native command options for original AutoSci syntax, including resume/status and route-specific flags. |
| Source-grounded ingest/discovery | error | Replace fixture/schema-only success with verified PDF/arXiv/wiki evidence propagation. |
| Ideate and novelty gates | warn | Keep improving real ideation, novelty provenance, and Review LLM coupling until quality gates prove research value, not just schema shape. |
| Experiment lifecycle | error | Implement deploy/monitor/collect lifecycle without fixture result artifacts for non-smoke runs. |
| Publication compile | error | Produce and verify LaTeX/PDF/checklist artifacts through approved executors. |
| Web UI and visualization | error | Restore native visualization/web surfaces and validate route flags against real runtime behavior. |

### Audit-Adjusted Verification Commands

| Command | Result |
|---|---|
| `.venv/bin/python -m json.tool harness/plugins/autosci/config/feature_parity_routes.v1.json /tmp/feature_parity_routes_after_audit_update.json` | ok |
| `.venv/bin/python -m json.tool harness/plugins/autosci/config/feature_operator_bindings.v1.json /tmp/feature_operator_bindings_after_audit_update.json` | ok |
| `.venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci_feature_parity_after_audit_update_20260625.json` | ok: `full_count=0`, `partial_count=18`, `gated_count=10`, `missing_route_count=0`. |
| `env PYTHONPATH=harness .venv/bin/python harness/evaluators/scientific/autosci_feature_parity_gate.py /tmp/autosci_feature_parity_after_audit_update_20260625.json` | ok: gate passed with non-full route warning. |
| `.venv/bin/python harness/plugins/autosci/bin/autosci_operator_smoke.py skillgen --out /tmp/autosci_operator_smoke_after_audit_update_20260625.json` | ok: `bound_count=28`, `completed_count=0`, `partial_count=18`, `gated_count=10`, `failed_count=0`. |
| `env PYTHONPATH=harness .venv/bin/python harness/evaluators/scientific/autosci_operator_smoke_gate.py /tmp/autosci_operator_smoke_after_audit_update_20260625.json` | ok: gate passed with approval-gated runtime warning. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific -q` | ok: 52 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests -q` | ok: 74 passed. |

## Phase 19 P0 SkillGen PDF Ingest Repair

Logged: 2026-06-25 EDT

This follow-up addresses the rerun audit blocker `F-001 PDF ingestion`. The
failure mode was environment-sensitive: the project `.venv` had PyMuPDF, but
the strict audit's system `python3` had `pypdf` and no `fitz`, so SkillGen PDF
ingest returned failed parse evidence. Full parity is still not claimed here;
this repair only removes the PDF extraction/semantic-fidelity blocker.

| Item | Status | Evidence |
|---|---|---|
| System Python PDF fallback | ok | `paper_prepare.py` now falls back from PyMuPDF to `pypdf` or `PyPDF2` before declaring PDF decode failure. |
| Wrapped title recovery | ok | PDF title lines such as `SKILLGEN: Verified Inference-Time Agent Skill` + `Synthesis` are combined into the full title. |
| Semantic evidence retention | ok | Parsed LaTeX/recovered-text sections now retain enough source text for appendix facts such as seed, temperature, model, split, and refinement rounds. |
| Fixture leakage guard | ok | Failed paper parses use explicit parse-failure sections; they do not synthesize `Fixture abstract` or `sample_paper.md#abstract`. |
| Workspace isolation | ok | Default raw paper preparation paths resolve under the active `HARNESS_DIR`, not the main repository artifact directory. |

### SkillGen PDF Ingest Verification Commands

| Command | Result |
|---|---|
| `python3 - <<'PY' ... import fitz/pypdf/PyPDF2/pdfplumber ... PY` | ok: system `python3` has `pypdf` and no `fitz`; this reproduces the audit environment. |
| `env HARNESS_DIR=/tmp/autosci-system-pypdf-ingest2 AUTOSCI_DISABLE_NETWORK_FETCH=1 python3 harness/plugins/autosci/bin/autosci_skill_shim.py text '$ingest /Users/jamesyuan/Downloads/SkillGen(1).pdf --run-id system-pypdf-ingest2'` | ok: `action_count=2`, `failed_count=0`, `execution_status=partial`. |
| Semantic oracle over `/tmp/autosci-system-pypdf-ingest2/.../research_paper.json` | ok: title, three stages, analysis object, skill tuple, repairs/regressions/net gain, Best-of-K/verification gate, +3.27/+10.08 pp, seed 42, temperature 0, GPT-5.4-Mini, 70/30 split, and eight rounds are present in evidence. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_paper_prepare.py -q` | ok: 4 passed. |
| `.venv/bin/python -m py_compile harness/plugins/autosci/backends/paper_prepare.py` | ok |

### Remaining After PDF Repair

| Block | Status | Notes |
|---|---|---|
| Full native ingest parity | pending | Source extraction is fixed, but full parity still requires original AutoSci-equivalent wiki mutation, graph rebuild, source citation expansion, and downstream ask/research lifecycle verification. |
| Review LLM gate | error | Independent Review LLM evidence is still required before novelty/review stages can be considered full parity. |
| Experiment and paper lifecycle | error | Real approved runtime execution, collect/eval mutation, LaTeX draft, and PDF compile remain mandatory blockers. |

## Phase 19 CLI No-op And Research Pipeline Artifact Repair

Logged: 2026-06-25 EDT

This follow-up addresses audit blockers `F-005 CLI parity` and part of
`F-006 Integrated pipeline`. It does not claim full parity. The goal is to stop
native AutoSci commands from being accepted as route-only no-ops, while keeping
unexecuted lifecycle work explicitly gated/inconclusive.

| Item | Status | Evidence |
|---|---|---|
| Native CLI flag parsing | ok | The shim accepts original-style flags including `--format`, `--pipeline`, `--start-from`, `--skip-paper`, `--collect-ready`, `--discover`, and `--visualize` with `allow_abbrev=False`. |
| Positional ingest source | ok | `$ingest <path>` now maps the positional source to `paper_path`; it no longer requires a separate `--paper` to avoid route-only evidence. |
| Compile/survey/status no-op repair | ok | `$paper-compile ... --fix`, `$survey ... --format latex`, and `$exp-status --pipeline ...` each run a bounded bridge action and preserve native options in evidence. |
| Non-smoke experiment truthfulness | ok | Non-smoke `$exp-run --env/--review` uses approval-gated native semantics and no longer emits fixture result support when approval evidence is absent. |
| Research lifecycle artifacts | ok | `$research --start-from ...` now writes `wiki/outputs/pipeline-progress.md`, `wiki/outputs/PIPELINE_REPORT.md`, and `wiki/outputs/pipeline-state.json`. |
| Research lifecycle status | warn | Lifecycle evidence is intentionally `inconclusive`/`schema_only`; no online discovery, experiment deployment, collection, Review LLM, or PDF compile stage was executed. |

### Research Pipeline Artifact Details

| Artifact | Status | Path |
|---|---|---|
| Pipeline progress | ok | `artifacts/autosci/workspace/wiki/outputs/pipeline-progress.md` |
| Pipeline report | ok | `artifacts/autosci/workspace/wiki/outputs/PIPELINE_REPORT.md` |
| Pipeline state | ok | `artifacts/autosci/workspace/wiki/outputs/pipeline-state.json` |
| Workflow evidence | warn | `workflow_evolution.v1` records `current_stage`, `resume_from`, `pipeline`, and `stage_plan`, but remains `inconclusive`. |

### CLI And Pipeline Verification Commands

| Command | Result |
|---|---|
| `env HARNESS_DIR=/tmp/autosci-paper-compile-fix-current python3 harness/plugins/autosci/bin/autosci_skill_shim.py text '$paper-compile paper/ --fix --run-id paper-compile-fix-current'` | ok: `action_count=1`, `schema_only_count=1`, `execution_status=gated`. |
| `env HARNESS_DIR=/tmp/autosci-survey-format-fixed python3 harness/plugins/autosci/bin/autosci_skill_shim.py text '$survey topic:skillgen --format latex --run-id survey-format-fixed'` | ok: `action_count=1`, `schema_only_count=1`, `execution_status=partial`. |
| `env HARNESS_DIR=/tmp/autosci-exp-status-pipeline-fixed python3 harness/plugins/autosci/bin/autosci_skill_shim.py text '$exp-status --pipeline skillgen-main --run-id exp-status-pipeline-fixed'` | ok: `action_count=1`, `schema_only_count=1`, `execution_status=partial`. |
| `env HARNESS_DIR=/tmp/autosci-research-start-from-current python3 harness/plugins/autosci/bin/autosci_skill_shim.py text '$research skillgen-main --venue ICLR --start-from stage3-collect --skip-paper --run-id research-start-from-current'` | ok: `action_count=1`, `schema_only_count=1`, `execution_status=gated`, `workspace_updated_count=6`. |
| `env HARNESS_DIR=/private/tmp/autosci-research-start-from-current PYTHONPATH=harness .venv/bin/python harness/evaluators/scientific/workflow_evolution_gate.py /private/tmp/autosci-research-start-from-current/artifacts/autosci/runs/research-start-from-current/workflow_evolution.research.json` | ok: gate returned `inconclusive` with no structural reasons, matching the non-executed lifecycle state. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_research_start_from_writes_pipeline_artifacts -q` | ok: 1 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_runs_remaining_gated_backend_actions harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_research_start_from_writes_pipeline_artifacts -q` | ok: 2 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_paper_prepare.py harness/plugins/autosci/tests/test_autosci_skill_shim.py harness/plugins/autosci/tests/test_conversion_to_solar_evidence.py -q` | ok: 55 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests -q` | ok: 84 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific -q` | ok: 52 passed. |
| `.venv/bin/python harness/plugins/autosci/bin/autosci_operator_smoke.py skillgen --out /tmp/autosci_operator_smoke_after_cli_pipeline_repair_20260625.json` | ok: `bound_count=28`, `completed_count=0`, `partial_count=18`, `gated_count=10`, `failed_count=0`. |
| `.venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci_feature_parity_after_cli_pipeline_repair_20260625.json` | ok: `full_count=0`, `partial_count=18`, `gated_count=10`, `missing_route_count=0`. |
| `env PYTHONPATH=harness .venv/bin/python harness/evaluators/scientific/autosci_operator_smoke_gate.py /tmp/autosci_operator_smoke_after_cli_pipeline_repair_20260625.json` | ok: gate passed with approval-gated warning. |
| `env PYTHONPATH=harness .venv/bin/python harness/evaluators/scientific/autosci_feature_parity_gate.py /tmp/autosci_feature_parity_after_cli_pipeline_repair_20260625.json` | ok: gate passed with non-full route warning. |
| `git diff --check -- harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/adapters/autosci_to_workflow_evolution.py harness/plugins/autosci/tests/test_autosci_skill_shim.py harness/plugins/autosci/backends/paper_prepare.py harness/plugins/autosci/adapters/autosci_to_research_paper.py harness/plugins/autosci/tests/test_paper_prepare.py harness/plugins/autosci/tests/test_conversion_to_solar_evidence.py docs/integrations/autosci/phase19-progress-log.md` | ok |

### Remaining After CLI/Pipeline Repair

| Block | Status | Notes |
|---|---|---|
| Full integrated research pipeline | error | The lifecycle now has resume/report artifacts, but still lacks real stage execution and cross-stage native AutoSci artifacts. |
| Review LLM gate | error | Novelty/review/paper-plan still require independent Review LLM evidence before full parity can be claimed. |
| Experiment deploy/monitor/collect | error | Approval-gated diagnostics exist, but deploy/session/status mutation/result collection are not native full parity. |
| Publication compile | error | Compile diagnostics exist, but verified LaTeX/PDF/checklist output through approved executors remains incomplete. |
| Web UI and visualization | error | Native AutoSci visualization/web UI parity remains pending. |

## Phase 19 Runtime, Review, Draft, And Ask Parity Repair

Logged: 2026-06-25 EDT

This follow-up addresses additional parts of `F-002 Review gate`,
`F-003 Experiment lifecycle`, `F-004 Paper pipeline`, and `F-008 Ask/wiki QA`.
It still does not claim full parity. The main change is that approved runtime
evidence and source-grounded wiki evidence now produce concrete state/artifacts
instead of fixture fallback, stale repository fallback, or route-only output.

| Item | Status | Evidence |
|---|---|---|
| Review resolver isolation | ok | `$review <slug>` no longer falls back from an isolated `HARNESS_DIR` to stale repo-level `harness/artifacts/autosci/workspace/wiki` pages. Missing targets remain `inconclusive/schema_only`. |
| Review LLM evidence path | warn | Supplied `artifact_review.v1` evidence and command bridge still work; absent Review LLM evidence remains disclosed as unavailable and not promotion-grade. |
| Approved experiment run | ok | `run_experiment` no longer returns fixture results after approval. It requires approval contract + runtime evidence + semantic verification before producing completed `experiment_result.v1`. |
| Experiment state mutation | ok | Verified runtime evidence writes `wiki/experiments/<experiment>.md`, appends `wiki/log.md`, and adds `produced_result` graph edges. |
| Experiment collect/status | ok | `$exp-run <slug> --collect` can now derive completed `experiment_status.v1` from verified approved runtime evidence and update wiki state. |
| Paper draft | ok | `$paper-draft ...` now runs `write_report` and writes `paper/main.tex` plus `paper/sections/*.tex`; it no longer returns action_count=0. |
| Ask/wiki QA | ok | `$ask` now returns a source-grounded extractive answer when wiki retrieval hits exist, with answer markdown, retrieval JSON, source paths, and passed memory-update gate. |

### Runtime/Draft/Ask Verification Commands

| Command | Result |
|---|---|
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_review_missing_slug_does_not_use_repo_workspace_fallback harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_runs_review_as_artifact_review harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_review_uses_supplied_review_llm_evidence -q` | ok: 3 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_exp_run_uses_verified_runtime_evidence_and_mutates_wiki harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_exp_collect_uses_verified_runtime_evidence harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_blocks_unapproved_exp_run_deploy_without_fixture_support harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_accepts_exp_run_native_options_without_fixture_fallback -q` | ok: 4 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_paper_draft_writes_latex_source harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_runs_paper_compile_fix_diagnostics harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_accepts_paper_plan_title_without_topic_fallback -q` | ok: 3 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_runs_ask_check_and_init_diagnostics harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_ask_and_check_read_workspace_wiki -q` | ok: 2 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests -q` | ok: 88 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific -q` | ok: 52 passed. |
| `.venv/bin/python harness/plugins/autosci/bin/autosci_operator_smoke.py skillgen --out /tmp/autosci_operator_smoke_after_runtime_draft_ask_repair_20260625.json` | ok: `bound_count=28`, `completed_count=0`, `partial_count=18`, `gated_count=10`, `failed_count=0`. |
| `.venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci_feature_parity_after_runtime_draft_ask_repair_20260625.json` | ok: `full_count=0`, `partial_count=18`, `gated_count=10`, `missing_route_count=0`. |
| `env PYTHONPATH=harness .venv/bin/python harness/evaluators/scientific/autosci_operator_smoke_gate.py /tmp/autosci_operator_smoke_after_runtime_draft_ask_repair_20260625.json` | ok: gate passed with approval-gated warning. |
| `env PYTHONPATH=harness .venv/bin/python harness/evaluators/scientific/autosci_feature_parity_gate.py /tmp/autosci_feature_parity_after_runtime_draft_ask_repair_20260625.json` | ok: gate passed with non-full route warning. |
| `git diff --check -- harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/bin/autosci_workspace_projector.py harness/plugins/autosci/backends/artifact_review.py harness/plugins/autosci/tests/test_autosci_skill_shim.py docs/integrations/autosci/phase19-progress-log.md` | ok |

### Remaining After Runtime/Draft/Ask Repair

| Block | Status | Notes |
|---|---|---|
| Full Review LLM parity | error | The bridge can consume Review LLM evidence/commands, but there is still no built-in native Review LLM provider execution proven in strict audit. |
| End-to-end research completion | error | Individual approved runtime and draft/ask paths work, but `$research` still does not execute every native stage to completion automatically. |
| Paper compile full parity | warn | Draft LaTeX and approved compile executor paths exist, but strict full parity still requires verified `paper/main.pdf` in the integrated pipeline. |
| Web UI and visualization | error | Native AutoSci web/graph UI parity remains pending. |

## Phase 19 Web UI Compatibility Repair

Logged: 2026-06-25 EDT

This follow-up addresses `F-007 Web UI`. The strict audit found that the
original AutoSci-compatible `tools/serve.py`, `tools/visualize.py`,
`app/index.html`, and `app/modules/graph.js` paths were missing. These paths
now exist as Solar AutoSci compatibility entrypoints over the local
`wiki/graph/edges.jsonl` and Markdown wiki workspace.

| Item | Status | Evidence |
|---|---|---|
| `tools/visualize.py` | ok | Provides `generate-obsidian-config`, `generate-canvas`, and `graph-data` commands over a supplied `--wiki-root`. |
| `tools/serve.py` | ok | Provides `--health-check` plus a local static server that generates `app/data/graph.json` from the active wiki before serving. |
| `app/index.html` | ok | Static graph reader shell exists and loads `app/modules/graph.js`. |
| `app/modules/graph.js` | ok | Renders local graph JSON with search and selection details. |
| Runtime data handling | ok | `app/data/graph.json` is generated at serve/health-check time and is not treated as a source file. |

### Web UI Verification Commands

| Command | Result |
|---|---|
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_web_visualization_compatibility_tools_generate_graph_artifacts harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_runs_remaining_gated_backend_actions -q` | ok: 2 passed. |
| `.venv/bin/python -m py_compile tools/visualize.py tools/serve.py harness/plugins/autosci/bin/autosci_bridge.py` | ok |
| `.venv/bin/python tools/visualize.py generate-obsidian-config --wiki-root /tmp/autosci-web-current/wiki` | ok: generated `.obsidian/graph.json`. |
| `.venv/bin/python tools/visualize.py generate-canvas --wiki-root /tmp/autosci-web-current/wiki --graph-out /tmp/autosci-web-current/graph.json` | ok: generated Canvas and graph JSON with 2 nodes / 1 edge in the smoke wiki. |
| `.venv/bin/python tools/serve.py --wiki-root /tmp/autosci-web-current/wiki --health-check` | ok: `node_count=2`, `edge_count=1`, app files present. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests -q` | ok: 89 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific -q` | ok: 52 passed. |
| `.venv/bin/python harness/plugins/autosci/bin/autosci_operator_smoke.py skillgen --out /tmp/autosci_operator_smoke_after_web_repair_20260625.json` | ok: `bound_count=28`, `completed_count=0`, `partial_count=18`, `gated_count=10`, `failed_count=0`. |
| `.venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci_feature_parity_after_web_repair_20260625.json` | ok: `full_count=0`, `partial_count=18`, `gated_count=10`, `missing_route_count=0`. |
| `env PYTHONPATH=harness .venv/bin/python harness/evaluators/scientific/autosci_operator_smoke_gate.py /tmp/autosci_operator_smoke_after_web_repair_20260625.json` | ok: gate passed with approval-gated warning. |
| `env PYTHONPATH=harness .venv/bin/python harness/evaluators/scientific/autosci_feature_parity_gate.py /tmp/autosci_feature_parity_after_web_repair_20260625.json` | ok: gate passed with non-full route warning. |

### Remaining After Web UI Repair

| Block | Status | Notes |
|---|---|---|
| Full end-to-end `$research` parity | error | Compatibility pieces exist, but the integrated research command still needs to orchestrate all repaired stages into one completed pipeline. |
| Built-in Review LLM provider | error | Evidence/command bridge exists; automatic Codex/Review LLM execution has not been proven by strict audit. |
| Integrated paper PDF | warn | Draft/compile pieces exist; the integrated research run still must produce verified `paper/main.pdf`. |

## Phase 19 Review LLM Provider Repair

Logged: 2026-06-25 EDT

This follow-up addresses the remaining built-in Review LLM provider blocker
from the Web UI repair section. It does not claim full parity because the
integrated `$research` lifecycle and integrated paper PDF proof remain open.

| Item | Status | Evidence |
|---|---|---|
| OpenAI-compatible provider path | ok | `artifact_review.py` now invokes a configured Review LLM provider when Review LLM is explicitly requested or provider env/config is present. |
| Default model | ok | Provider mode defaults to `gpt-5.5`; shim also exposes `--review-llm-model` for explicit auditability. |
| Provider controls | ok | Shim exposes `--review-llm-provider`, `--review-llm-model`, and `--review-llm-endpoint`; env fallbacks are `AUTOSCI_REVIEW_LLM_PROVIDER`, `AUTOSCI_REVIEW_LLM_MODEL`, and `AUTOSCI_REVIEW_LLM_ENDPOINT`. |
| Provenance | ok | Provider responses are normalized into `artifact_review.v1`, archived under `artifacts/autosci/review-llm`, and include invocation mode, provider, model, endpoint, request hash, response hash, usage, and Review LLM evidence ids. |
| Failure truthfulness | ok | Missing key, transport failure, invalid transport JSON, or invalid model JSON stay unavailable/failed/invalid; the bridge does not convert failed provider calls into passed surrogate review. |
| Novelty coupling | ok | Novelty/review output now distinguishes provider-produced, command-bridge, and externally supplied Review LLM evidence instead of always saying the bridge did not invoke a reviewer. |

### Review LLM Provider Verification Commands

| Command | Result |
|---|---|
| `.venv/bin/python -m py_compile harness/plugins/autosci/backends/artifact_review.py harness/plugins/autosci/backends/novelty_review.py harness/plugins/autosci/bin/autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_runs_review_as_artifact_review harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_review_uses_review_llm_command_bridge harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_review_invokes_openai_compatible_provider harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_novelty_write_uses_review_llm_command_bridge -q` | ok: 4 passed. |

### Remaining After Review LLM Provider Repair

| Block | Status | Notes |
|---|---|---|
| Full end-to-end `$research` parity | error | Compatibility pieces and individual repaired routes exist, but `$research` still must orchestrate all repaired stages into one completed lifecycle. |
| Integrated paper PDF | warn | Draft/compile pieces exist; the integrated research run still must produce verified `paper/main.pdf`. |

## Phase 19 Research Lifecycle And Integrated PDF Repair

Logged: 2026-06-25 EDT

This follow-up addresses the `$research` integration blocker and the integrated
PDF proof blocker. It still does not claim full parity because real long-running
stage runners, network fetches, and human gates remain approval/evidence driven.
The fix prevents `$research` from being only a blocked route plan when strict
stage evidence is available.

| Item | Status | Evidence |
|---|---|---|
| Evidence-aware `$research` lifecycle | ok | `run_research_lifecycle` now reads active wiki state plus discovery, novelty, Review LLM, experiment runtime, collection, and compile evidence to mark each native lifecycle stage `completed` or `pending_evidence`. |
| Verified completed pipeline state | ok | When every required stage has evidence, `$research` emits completed `workflow_evolution.v1`, writes `pipeline-state.json`, and records `pipeline.status=completed` instead of a blocked plan. |
| Missing-evidence truthfulness | ok | If any required stage evidence is missing or invalid, the lifecycle remains `inconclusive` and names the pending stage rather than synthesizing success. |
| Integrated PDF materialization | ok | With verified approval contract plus compile runtime/PDF evidence, `$research` materializes the verified PDF to `artifacts/autosci/workspace/paper/main.pdf` and records an `integrated_paper_pdf` artifact. |
| Config truthfulness | ok | Route/operator configs now describe `$research` as external-evidence-orchestrated partial coverage and `/review` as supporting configured Review LLM provider/command/supplied evidence. Coverage status remains non-full and uses existing parity schema enums. |

### Research Lifecycle Verification Commands

| Command | Result |
|---|---|
| `.venv/bin/python -m py_compile harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/adapters/autosci_to_workflow_evolution.py` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_research_start_from_writes_pipeline_artifacts harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_research_lifecycle_completes_from_verified_stage_evidence harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_runs_research_pipeline -q` | ok: 3 passed. |
| `python3 -m json.tool harness/plugins/autosci/config/feature_parity_routes.v1.json >/dev/null && python3 -m json.tool harness/plugins/autosci/config/feature_operator_bindings.v1.json >/dev/null` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests -q` | ok: 91 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific -q` | ok: 52 passed. |
| `.venv/bin/python harness/plugins/autosci/bin/autosci_operator_smoke.py skillgen --out /tmp/autosci_operator_smoke_after_research_lifecycle_repair_20260625.json` | ok: `bound_count=28`, `completed_count=0`, `partial_count=18`, `gated_count=10`, `failed_count=0`. |
| `.venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci_feature_parity_after_research_lifecycle_repair_20260625.json` | ok: `full_count=0`, `partial_count=18`, `gated_count=10`, `missing_route_count=0`. |
| `env PYTHONPATH=harness .venv/bin/python harness/evaluators/scientific/autosci_operator_smoke_gate.py /tmp/autosci_operator_smoke_after_research_lifecycle_repair_20260625.json` | ok: gate passed with approval-gated warning. |
| `env PYTHONPATH=harness .venv/bin/python harness/evaluators/scientific/autosci_feature_parity_gate.py /tmp/autosci_feature_parity_after_research_lifecycle_repair_20260625.json` | ok: gate passed with non-full route warning. |
| `git diff --check -- harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/adapters/autosci_to_workflow_evolution.py harness/plugins/autosci/backends/artifact_review.py harness/plugins/autosci/backends/novelty_review.py harness/plugins/autosci/config/feature_parity_routes.v1.json harness/plugins/autosci/config/feature_operator_bindings.v1.json harness/plugins/autosci/tests/test_autosci_skill_shim.py docs/integrations/autosci/phase19-progress-log.md tools/visualize.py tools/serve.py app/index.html app/styles.css app/modules/graph.js` | ok |

### Remaining After Research Lifecycle Repair

| Block | Status | Notes |
|---|---|---|
| Real stage runner full parity | error | The integrated lifecycle can verify completed stage evidence, but it still does not launch every native long-running runner by itself without approval/runtime evidence. |
| Live external source full parity | warn | Online discovery/novelty fetch paths exist, but full parity still needs repeated live source audits under real provider conditions. |

## Phase 19 PDF Ingest Gate Hardening Follow-up

Logged: 2026-06-25 EDT

This follow-up tightens the already repaired PDF ingest path so the strict
audit cannot pass a completed PDF ingest that lacks extracted text evidence.
It also removes stale route text that still described the old SkillGen PDF
semantic failure as current behavior.

| Item | Status | Evidence |
|---|---|---|
| PDF ingest gate | ok | `paper_gate.py` now requires completed PDF-prepared evidence to carry `preparation.extracted_text_path`, an `extracted_pdf_text` artifact, and a parsed/partial parse status. |
| `$ingest <pdf>` regression | ok | Shim test now generates a real PDF, runs non-smoke `$ingest <pdf>` with network disabled, and verifies `original_format=pdf`, `extracted_pdf_text`, `synthetic_latex`, parsed title text, and no fixture abstract leakage. |
| Config truthfulness | ok | Ingest route/operator limitations now say PDF extraction and fixture-leakage guards are covered; the route remains partial only for approved wiki mutation, graph rebuild, citation expansion, and downstream lifecycle audits. |

### PDF Ingest Gate Verification Commands

| Command | Result |
|---|---|
| `.venv/bin/python -m py_compile harness/evaluators/scientific/paper_gate.py harness/plugins/autosci/tests/test_autosci_skill_shim.py harness/tests/evaluators/scientific/test_paper_gate.py` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_ingests_pdf_with_extracted_text_and_no_fixture_leakage harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_maps_positional_ingest_source harness/tests/evaluators/scientific/test_paper_gate.py -q` | ok: 4 passed. |

### Remaining After PDF Gate Hardening

| Block | Status | Notes |
|---|---|---|
| Approved wiki mutation and graph rebuild | warn | Ingest can parse and prepare sources, but original-style approved wiki mutation/rebuild still needs explicit mutation evidence. |
| Live external source full parity | warn | Discovery and novelty online paths still need live provider audit evidence. |

## Phase 19 Research Wiki Tool ABI Repair

Logged: 2026-06-25 EDT

This follow-up closes the generic `tools/research_wiki.py` command-layer gap
referenced by the migrated AutoSci routes. It does not mark full parity by
itself because citation expansion and downstream lifecycle audits still need
completed evidence, but the missing wiki mutation/retrieval ABI is now present
as a local, bounded, auditable tool.

| Item | Status | Evidence |
|---|---|---|
| Wiki retrieval ABI | ok | Added `tools/research_wiki.py query`, `neighbors`, and `stats` with JSON evidence output over the local Markdown wiki and `wiki/graph/edges.jsonl`. |
| Wiki mutation ABI | ok | Added `set-meta`, `add-edge`, `log`, and `rebuild` commands with wiki-root containment checks, before/after hashes, edge evidence ids, and rebuilt `index.md` / `graph/context_brief.md`. |
| Route truthfulness | ok | Ingest route/operator limitations now state that generic local wiki mutation/rebuild tooling is covered; the route remains partial for citation expansion and downstream lifecycle audits. |

### Research Wiki Tool Verification Commands

| Command | Result |
|---|---|
| `python3 -m py_compile tools/research_wiki.py harness/plugins/autosci/tests/test_research_wiki_tool.py` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_research_wiki_tool.py -q` | ok: 1 passed. |
| `python3 tools/research_wiki.py set-meta ideas/skillgen.md status=reviewed --wiki-root <tmp>/wiki --json && python3 tools/research_wiki.py query SkillGen --wiki-root <tmp>/wiki --json` | ok: CLI smoke emitted consumable JSON. |

### Remaining After Research Wiki Tool ABI Repair

| Block | Status | Notes |
|---|---|---|
| Citation expansion | warn | Source preparation and wiki mutation are covered, but survey/paper planning still needs stronger citation expansion evidence before full parity. |
| Live external source full parity | warn | Discovery and novelty online paths still need live provider audit evidence under real source conditions. |
| Real stage runner full parity | error | Long-running experiment/deploy/collect stages still require approved runtime evidence and cannot be truthfully collapsed into deterministic smoke output. |

## Phase 19 Source Discovery CLI ABI Repair

Logged: 2026-06-25 EDT

This follow-up closes the root `tools/` command ABI gap for source preparation,
literature discovery, and novelty source helpers. The commands reuse existing
Solar AutoSci backends where available and report unavailable providers as
`inconclusive` evidence instead of synthetic candidates.

| Item | Status | Evidence |
|---|---|---|
| Paper source CLI | ok | Added `tools/prepare_paper_source.py` as a root wrapper over the source preparation backend for local/PDF/arXiv source normalization. |
| Discover CLI | ok | Added `tools/discover.py from-topic/from-anchors/from-wiki/from-venue` over the literature discovery backend, preserving no-network inconclusive behavior. |
| Novelty source CLIs | ok | Added `tools/fetch_s2.py search/references/citations` and `tools/fetch_deepxiv.py search`; unavailable providers return explicit inconclusive evidence. |
| Route truthfulness | ok | Discover and novelty route/operator limitations now state that source CLIs exist while provider-backed completion still requires real source evidence. |

### Source Discovery CLI Verification Commands

| Command | Result |
|---|---|
| `python3 -m py_compile tools/prepare_paper_source.py tools/discover.py tools/fetch_s2.py tools/fetch_deepxiv.py harness/plugins/autosci/tests/test_source_cli_tools.py` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_source_cli_tools.py -q` | ok: 3 passed. |

### Remaining After Source Discovery CLI ABI Repair

| Block | Status | Notes |
|---|---|---|
| Root side-effect/toolchain CLIs | warn | `tools/lint.py`, `daily_arxiv.py`, `send_email.py`, `remote.py`, `init_discovery.py`, `rasterize_latex.py`, `poster.py`, `wiki2dag.py`, and `reset_wiki.py` are still missing root ABI coverage. |
| Live provider completion | warn | Discovery/novelty commands are truthful, but full parity still needs live provider success evidence rather than only disabled/unavailable evidence. |

## Phase 19 Root Tool ABI Completion Repair

Logged: 2026-06-25 EDT

This follow-up closes the remaining root `tools/*.py` existence gap in the
feature parity route config. Side-effectful commands remain approval-gated and
truthful: launch, email send, reset, and browser/PNG render paths report
`approval_required` or `inconclusive` unless real runtime evidence is supplied.

| Item | Status | Evidence |
|---|---|---|
| Wiki/check tool ABI | ok | Added `tools/lint.py` and covered route config references to `tools/research_wiki.py stats/query/neighbors`. |
| Init/source tool ABI | ok | Added `tools/init_discovery.py prepare/plan/fetch` and verified all source/discovery route tool paths now exist. |
| Side-effect tool ABI | ok | Added `tools/daily_arxiv.py`, `tools/send_email.py`, `tools/remote.py`, and `tools/reset_wiki.py` with approval-required evidence for external/destructive effects. |
| Publication/visual tool ABI | ok | Added `tools/rasterize_latex.py`, `tools/wiki2dag.py`, and `tools/poster.py` for diagnostics/build/validate paths without claiming unavailable rendering success. |
| Route tool inventory | ok | Route config root tool reference audit now returns `{}` for missing `tools/*.py` paths. |

### Root Tool ABI Verification Commands

| Command | Result |
|---|---|
| `python3 -m py_compile tools/lint.py tools/init_discovery.py tools/remote.py tools/daily_arxiv.py tools/send_email.py tools/rasterize_latex.py tools/wiki2dag.py tools/poster.py tools/reset_wiki.py` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_root_tool_abi.py harness/plugins/autosci/tests/test_source_cli_tools.py harness/plugins/autosci/tests/test_research_wiki_tool.py -q` | ok: 6 passed. |
| `python3 -m json.tool harness/plugins/autosci/config/feature_parity_routes.v1.json >/dev/null && python3 -m json.tool harness/plugins/autosci/config/feature_operator_bindings.v1.json >/dev/null` | ok |
| Root `tools/*.py` route inventory script | ok: `{}` missing root tools. |

### Remaining After Root Tool ABI Completion Repair

| Block | Status | Notes |
|---|---|---|
| Full route completion evidence | error | `full_count` remains zero until route statuses are backed by live/provider/runtime evidence and not merely by ABI coverage. |
| Live provider completion | warn | Discovery/novelty paths now have CLIs, but still need real provider success evidence for completed source-backed routes. |
| Long-running execution parity | error | Remote/local experiment launch, collect, reset, email, and render side effects still require approved runtime implementations and evidence. |

## Phase 19 Primary Tool ABI Gate Repair

Logged: 2026-06-25 EDT

This follow-up makes the parity inventory gate enforce local primary tool and
config-file existence. It also adds the missing setup documentation artifacts
referenced by the setup route.

| Item | Status | Evidence |
|---|---|---|
| Setup config ABI | ok | Added `harness/plugins/autosci/config/setup-guide.md` and `harness/plugins/autosci/config/.env.example` without writing secrets. |
| Inventory tool ABI sidecar | ok | `autosci_parity_bridge.py` now records `tool_abi_status`, `primary_tool_statuses`, and `missing_primary_tools` for each route. |
| Gate enforcement | ok | `autosci_feature_parity_gate.py` now fails if any local primary tool/config reference is missing. External executables/providers remain explicit external requirements. |

### Primary Tool ABI Gate Verification Commands

| Command | Result |
|---|---|
| `python3 -m py_compile harness/plugins/autosci/bin/autosci_parity_bridge.py harness/evaluators/scientific/autosci_feature_parity_gate.py` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_phase19_parity_bridge.py harness/plugins/autosci/tests/test_root_tool_abi.py -q` | ok: 6 passed. |
| `.venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci_feature_parity_after_tool_abi_gate_20260625.json` | ok: `full_count=0`, `partial_count=18`, `gated_count=10`, `missing_route_count=0`. |
| `env PYTHONPATH=harness .venv/bin/python harness/evaluators/scientific/autosci_feature_parity_gate.py /tmp/autosci_feature_parity_after_tool_abi_gate_20260625.json` | ok: gate passed with non-full warning. |

### Remaining After Primary Tool ABI Gate Repair

| Block | Status | Notes |
|---|---|---|
| Route completion | error | ABI completeness is enforced, but routes remain non-full until each route has source/model/runtime evidence matching native behavior. |
| External executable/provider proof | warn | `latexmk`, Review LLM MCP/provider, live S2/DeepXiv, SMTP, browser rendering, and remote execution remain external evidence requirements. |

## Phase 19 Publication Citation Map Repair

Logged: 2026-06-25 EDT

This follow-up fixes the paper-plan/survey citation expansion blocker for
supplied source evidence. The routes no longer only emit placeholder citation
language: they build an explicit `autosci_publication_citation_map.v1` sidecar
from discovery, paper, and wiki paper evidence.

| Item | Status | Evidence |
|---|---|---|
| Citation map sidecar | ok | `plan_report` and `write_survey` now write `*_citation_map.json` artifacts with source-backed citation ids, titles, source refs, source channels, and evidence ids. |
| Survey completion gate | ok | `$survey` remains inconclusive without source citations, but becomes completed when supplied discovery/paper/wiki evidence yields citation entries. |
| Paper-plan review gate | ok | `$paper-plan` now requires both citation-map entries and completed Review LLM evidence before returning completed status. |
| Config truthfulness | ok | Ingest, paper-plan, paper-draft, and survey route/operator limitations now describe citation-map handoff as covered while preserving remaining live/provider/compile audit blockers. |

### Publication Citation Map Verification Commands

| Command | Result |
|---|---|
| `python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_accepts_paper_plan_title_without_topic_fallback harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_paper_plan_completes_with_citations_and_review_llm harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_runs_survey_rebuttal_and_poster_native_sidecars harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_survey_completes_with_citation_evidence harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_accepts_survey_format_latex -q` | ok: 5 passed. |

### Remaining After Publication Citation Map Repair

| Block | Status | Notes |
|---|---|---|
| Live/exhaustive literature audit | warn | Citation-map generation works for supplied evidence, but live provider coverage still needs real S2/DeepXiv/Paper Copilot success evidence. |
| End-to-end publication compile audit | warn | Planning/survey citation evidence is fixed; compile/PDF/toolchain evidence still gates full publication parity. |

## Phase 19 Pilot Evaluation Runtime Evidence Repair

Logged: 2026-06-25 EDT

This follow-up replaces the fixed inconclusive `$exp-pilot-eval` behavior with
evidence-driven pilot verdict generation. Missing evidence still remains
inconclusive; supplied runtime or `experiment_result.v1` evidence can now
produce completed `claim_verdict.v1` evidence.

| Item | Status | Evidence |
|---|---|---|
| Runtime-backed pilot verdict | ok | `evaluate_pilot_result` now reads supplied runtime evidence, maps outcome/exit code to a lenient pilot verdict, and attaches `pilot_runtime_evidence_json` artifacts. |
| Missing-evidence truthfulness | ok | Existing no-evidence `$exp-pilot-eval` path remains inconclusive; no default support verdict is synthesized. |
| Config truthfulness | ok | `exp-pilot-eval` and `exp-status` route/operator limitations now reflect runtime/wiki evidence support while preserving approved wiki-write/remote-provider blockers. |

### Pilot Evaluation Verification Commands

| Command | Result |
|---|---|
| `python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_runs_remaining_gated_backend_actions harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_pilot_eval_uses_runtime_evidence -q` | ok: 2 passed. |

### Remaining After Pilot Evaluation Runtime Evidence Repair

| Block | Status | Notes |
|---|---|---|
| Approved pilot wiki writeback | warn | Completed pilot verdicts do not mutate wiki status unless an explicit approved write path is implemented/audited. |
| Remote provider audit | warn | Runtime evidence can be consumed, but real remote launch/check/pull-results provider evidence remains approval-gated. |

## Phase 19 Rebuttal Review Mapping Repair

Logged: 2026-06-25 EDT

This follow-up replaces fixed empty rebuttal maps with evidence-backed response
plans when supplied Review LLM / `artifact_review.v1` findings are available.

| Item | Status | Evidence |
|---|---|---|
| Review finding extraction | ok | `draft_rebuttal` now reads supplied `artifact_review.v1` findings and atomizes them into mapped concerns. |
| Response map completion | ok | Rebuttal bundle status becomes completed only when source review evidence yields mapped concerns; no-evidence runs remain inconclusive. |
| Config truthfulness | ok | Rebuttal route/operator limitations now describe completed mapped response plans from supplied Review LLM evidence while preserving reviewer-thread/submission audit blockers. |

### Rebuttal Mapping Verification Commands

| Command | Result |
|---|---|
| `python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_runs_survey_rebuttal_and_poster_native_sidecars harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_rebuttal_maps_review_llm_findings -q` | ok: 2 passed. |

### Remaining After Rebuttal Mapping Repair

| Block | Status | Notes |
|---|---|---|
| Reviewer-thread ingestion | warn | Mapped responses work for supplied Review LLM findings, but full native reviewer-thread ingestion/submission workflow is still not audited. |

## Phase 19 Init Runtime Source Manifest Coverage

Logged: 2026-06-25 EDT

This follow-up verifies the completed `$init` path for approved runtime source
manifests. The bridge still does not execute network fetch or fan-in ingest by
itself, but it can consume approved source-manifest runtime evidence and emit
completed `literature_discovery.v1` evidence.

| Item | Status | Evidence |
|---|---|---|
| Init runtime manifest path | ok | Added regression coverage for `$init` with approval, allowlist, before/after artifacts, and runtime candidates. |
| Semantic verification | ok | `init_sources` returns `mode=init_runtime_verified` only when the approval contract and runtime candidate evidence pass semantic verification. |
| Config truthfulness | ok | Init route/operator limitations now distinguish completed approved runtime source manifests from still-gated native network fetch/bulk ingest/wiki fan-in execution. |

### Init Runtime Verification Commands

| Command | Result |
|---|---|
| `python3 -m py_compile harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_runs_ask_check_and_init_diagnostics harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_init_uses_verified_runtime_source_manifest -q` | ok: 2 passed. |

### Remaining After Init Runtime Source Manifest Coverage

| Block | Status | Notes |
|---|---|---|
| Native network/fan-in executor | warn | `$init` can consume verified runtime evidence, but direct feed/source fetching and wiki fan-in remain approval/provider-gated. |

## Phase 19 Daily arXiv Runtime Digest Coverage

Logged: 2026-06-25 EDT

This follow-up verifies the completed `$daily-arxiv` path for approved runtime
digest/feed evidence. The route remains gated for direct network fetch, email,
scheduling, and auto-ingest side effects.

| Item | Status | Evidence |
|---|---|---|
| Daily runtime digest path | ok | Added regression coverage for `$daily-arxiv` with approval, allowlist, before/after artifacts, and runtime candidates. |
| Semantic verification | ok | `daily_arxiv_prepare_finalize` returns `mode=daily_arxiv_runtime_verified` only when the approval contract and runtime candidate evidence pass semantic verification. |
| Config truthfulness | ok | Daily arXiv route/operator limitations now distinguish completed approved runtime digest evidence from still-gated fetch/email/scheduling/auto-ingest execution. |

### Daily arXiv Runtime Verification Commands

| Command | Result |
|---|---|
| `python3 -m py_compile harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_runs_remaining_gated_backend_actions harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_daily_arxiv_uses_verified_runtime_digest -q` | ok: 2 passed. |

### Remaining After Daily arXiv Runtime Digest Coverage

| Block | Status | Notes |
|---|---|---|
| Direct daily executor | warn | The route can consume verified runtime evidence, but feed fetch/email/scheduling/auto-ingest execution remains approval/provider-gated. |

## Phase 19 ABI Publication Runtime Verification Rollup

Logged: 2026-06-25 EDT

This rollup records the verification pass after the research wiki tool ABI,
source/discovery CLI ABI, root tool ABI, primary-tool gate, publication
citation map, pilot runtime evaluation, rebuttal mapping, init runtime manifest,
and daily runtime digest repairs.

| Item | Status | Evidence |
|---|---|---|
| AutoSci plugin tests | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests -q` passed: 104 tests. |
| Scientific evaluator tests | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific -q` passed: 54 tests. |
| Operator smoke gate | ok | `bound_count=28`, `completed_count=0`, `partial_count=18`, `gated_count=10`, `failed_count=0`; gate passed with approval-gated warning. |
| Feature parity gate | warn | `full_count=0`, `partial_count=18`, `gated_count=10`, `missing_route_count=0`; gate passed with non-full warning. |
| Config and whitespace checks | ok | Route/operator JSON validation passed; `git diff --check` passed over changed AutoSci/code/log files. |
| Generated artifact cleanup | ok | Removed generated `app/data/graph.json` after visualization tests. |

### Current Full Parity Status

| Area | Status | Notes |
|---|---|---|
| Route coverage | ok | All 28 native skills have Solar routes and local primary tool/config ABI references resolve. |
| Functional parity | partial | Many routes now have completed paths when supplied source/model/runtime evidence exists, but static inventory remains non-full. |
| External/provider parity | blocked | Full parity still needs real provider/executor evidence for live S2/DeepXiv/Paper Copilot, Review LLM, latexmk/PDF compile, SMTP/email, browser render, and remote launch/check/pull-results. |

## Phase 19 Approved Wiki Mutation and Status Sync Repair

Logged: 2026-06-25 EDT

This follow-up closes the local wiki mutation gap for approved `/prefill` and
`/edit` executions, while preserving no-approval proposal behavior.

| Item | Status | Evidence |
|---|---|---|
| Approved prefill mutation | ok | `$prefill foundation:... --approval-ref ... --execute-approved` now writes a foundation page under the configured wiki root, appends `wiki/log.md`, and rebuilds `wiki/index.md` plus `wiki/graph/context_brief.md`. |
| Approved edit mutation | ok | `$edit wiki/... --approval-ref ... --after-artifact ... --execute-approved` now applies the approved after-artifact to the target wiki page with before/after hashes and rebuild evidence. |
| No-approval safety | ok | Existing `/prefill` and `/edit` runs without explicit approval still emit proposed `research_memory_update.v1` evidence and do not mutate wiki files. |
| Route/operator truthfulness | ok | `/prefill` is synchronized as approval-gated for approved wiki mutation; `/exp-design` and `/exp-pilot-eval` remain synchronized as partial evidence/evaluation routes rather than side-effect executors. |
| Drift guard | ok | Added a route-vs-operator status consistency regression so future parity reports cannot silently disagree with operator smoke status. |

### Approved Wiki Mutation Verification Commands

| Command | Result |
|---|---|
| `python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `python3 -m json.tool harness/plugins/autosci/config/feature_parity_routes.v1.json` | ok |
| `python3 -m json.tool harness/plugins/autosci/config/feature_operator_bindings.v1.json` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_runs_wiki_and_control_proposal_actions harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_prefill_applies_approved_wiki_mutation harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_edit_applies_approved_after_artifact -q` | ok: 3 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_phase19_operator_smoke.py -q` | ok: 3 passed. |
| `.venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci_feature_parity_after_executor_repairs_20260625.json` | ok: `full_count=0`, `partial_count=17`, `gated_count=11`, `missing_route_count=0`. |
| `.venv/bin/python harness/plugins/autosci/bin/autosci_operator_smoke.py skillgen --out /tmp/autosci_operator_smoke_after_executor_repairs_20260625.json` | ok: `bound_count=28`, `completed_count=0`, `partial_count=17`, `gated_count=11`, `failed_count=0`. |

### Remaining After Approved Wiki Mutation Repair

| Block | Status | Notes |
|---|---|---|
| Full parity | blocked | Inventory remains non-full because live provider/executor evidence is still required for S2/DeepXiv/Paper Copilot, Review LLM, latexmk/PDF compile, SMTP/email, browser render, and remote launch/check/pull-results. |

## Phase 19 TeX Executor Fallback Repair

Logged: 2026-06-25 EDT

This follow-up improves the approved paper compile executor so a machine without
`latexmk` can still produce verified PDF evidence through an explicitly
allowlisted TeX engine.

| Item | Status | Evidence |
|---|---|---|
| TeX executor selection | ok | `$paper-compile --execute-approved` now chooses the first installed and allowlisted executor from `latexmk`, `pdflatex`, `xelatex`, and `lualatex`. |
| Approval boundary | ok | The executor still requires `approval_ref`, allowlist evidence, before-artifact evidence, and `--execute-approved`; no-approval runs remain diagnostics-only. |
| Runtime provenance | ok | `autosci_runtime_evidence.v1` now records `tex_executor`, available TeX executors, command, stdout/stderr sidecars, PDF path, and executor-specific evidence ids such as `paper-compile-runtime:pdflatex`. |
| Checklist truthfulness | ok | `paper_compile_checklist.v1` preserves `latexmk_available` while adding `tex_executors` and `selected_executor`, so missing latexmk no longer hides usable approved engines. |
| Route truthfulness | ok | `/paper-compile` route text now describes approval-gated TeX executor behavior instead of latexmk-only behavior. |

### TeX Executor Fallback Verification Commands

| Command | Result |
|---|---|
| `python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_executes_approved_paper_compile_executor harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_executes_approved_paper_compile_with_pdflatex_fallback harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_uses_semantic_runtime_evidence_for_gated_results harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_accepts_paper_compile_checklist_without_bundle_fallback -q` | ok: 4 passed. |
| `python3 -m json.tool harness/plugins/autosci/config/feature_parity_routes.v1.json` | ok |
| `.venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci_feature_parity_after_executor_repairs_20260625.json` | ok: `full_count=0`, `partial_count=17`, `gated_count=11`, `missing_route_count=0`. |

### Remaining After TeX Executor Fallback Repair

| Block | Status | Notes |
|---|---|---|
| End-to-end publication parity | warn | Approved TeX executor can now produce verified PDF evidence, but final full parity still depends on real paper content, citation/review gates, and environment-specific toolchain smoke. |
| Non-publication executors | blocked | Live S2/DeepXiv/Paper Copilot, SMTP/email, browser render, and remote launch/check/pull-results still need approved runtime smoke evidence. |

## Phase 19 Remote Runtime Executor Repair

Logged: 2026-06-25 EDT

This follow-up adds a real approval-gated launch path to `tools/remote.py` and
fixes the runtime evidence schema/gate mismatch for experiment execution.

| Item | Status | Evidence |
|---|---|---|
| Approved remote/local launch | ok | `tools/remote.py launch --execute-approved` can run an explicit allowlisted command only when `--approval-ref`, `--allowlist-evidence`, `--command`, and a run directory are supplied. |
| Runtime evidence output | ok | The launch path writes `autosci_runtime_evidence.v1` with `action=run_experiment`, command, exit code, result paths, metrics, outcome, stdout/stderr artifacts, and approval ref. |
| Schema/gate consistency | ok | `autosci_runtime_evidence.v1` now permits `run_experiment`, and the runtime gate requires completed experiment evidence to include metrics, outcome, and `result_collected=true`. |
| Bridge consumption | ok | Existing `$exp-run` and collect paths continue to consume verified runtime evidence and mutate wiki experiment state only after semantic verification. |
| Default safety | ok | Without `--execute-approved`, `tools/remote.py launch` remains approval/inconclusive evidence and does not run commands. |

### Remote Runtime Verification Commands

| Command | Result |
|---|---|
| `python3 -m json.tool harness/schemas/evidence/autosci_runtime_evidence.v1.schema.json` | ok |
| `python3 -m py_compile tools/remote.py harness/evaluators/scientific/autosci_runtime_evidence_gate.py harness/tests/evaluators/scientific/test_autosci_runtime_evidence_gate.py harness/plugins/autosci/tests/test_root_tool_abi.py` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific/test_autosci_runtime_evidence_gate.py harness/plugins/autosci/tests/test_root_tool_abi.py -q` | ok: 7 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_blocks_unapproved_exp_run_deploy_without_fixture_support harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_exp_run_uses_verified_runtime_evidence_and_mutates_wiki harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_exp_collect_uses_verified_runtime_evidence -q` | ok: 3 passed. |

### Remaining After Remote Runtime Executor Repair

| Block | Status | Notes |
|---|---|---|
| Provider-specific remote parity | warn | The local approved executor can launch allowlisted commands and produce verifier-ready runtime evidence; SSH/rsync/screen provider profiles and real remote connectivity smoke remain environment-dependent. |
| External source/provider parity | blocked | Live S2/DeepXiv/Paper Copilot, SMTP/email, and browser render/export still need approved runtime smoke evidence. |

## Phase 19 SMTP Email Executor Repair

Logged: 2026-06-25 EDT

This follow-up converts `tools/send_email.py` from an approval-only stub into
an approval-gated SMTP executor with runtime evidence.

| Item | Status | Evidence |
|---|---|---|
| Approved SMTP send | ok | `tools/send_email.py send --execute-approved` sends only when `--approval-ref`, SMTP host/port, sender/recipient, and explicit execution are supplied. |
| Runtime evidence | ok | The send path writes `autosci_runtime_evidence.v1` with `action=send_email`, provider, SMTP endpoint metadata, delivery status, approval ref, and an email delivery receipt sidecar. |
| Gate hardening | ok | Runtime schema/gate now accepts `send_email` and requires completed email runtime evidence to declare `delivered=true` plus a provider. |
| Local smoke | ok | Added a local SMTP server test so delivery is verified without external email services or credentials. |
| Default safety | ok | Without approval or `--execute-approved`, email send remains approval-required/inconclusive and does not contact SMTP endpoints. |

### SMTP Executor Verification Commands

| Command | Result |
|---|---|
| `python3 -m json.tool harness/schemas/evidence/autosci_runtime_evidence.v1.schema.json` | ok |
| `python3 -m py_compile tools/send_email.py harness/evaluators/scientific/autosci_runtime_evidence_gate.py harness/tests/evaluators/scientific/test_autosci_runtime_evidence_gate.py harness/plugins/autosci/tests/test_root_tool_abi.py` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific/test_autosci_runtime_evidence_gate.py harness/plugins/autosci/tests/test_root_tool_abi.py -q` | ok: 8 passed. |

### Remaining After SMTP Executor Repair

| Block | Status | Notes |
|---|---|---|
| Live/provider SMTP | warn | Local SMTP smoke passes; real SMTP/provider credentials and deliverability remain environment-specific and must be approved before use. |
| External source/render parity | blocked | Live S2/DeepXiv/Paper Copilot and browser render/export still need approved runtime smoke evidence. |

## Phase 19 Root Poster Render Executor Repair

Logged: 2026-06-25 EDT

This follow-up closes the root CLI render/export gap for poster/browser parity.
The bridge already had an approved renderer path; `tools/poster.py render` now
has the same approval-gated runtime evidence behavior.

| Item | Status | Evidence |
|---|---|---|
| Approved root render | ok | `tools/poster.py render --execute-approved` runs only with `--approval-ref`, allowlist evidence, and an explicit renderer command or allowlisted renderer config. |
| PNG/export evidence | ok | The root render path writes PNG, renderer validation, stdout/stderr sidecars, and `autosci_runtime_evidence.v1` with `action=build_poster`. |
| Runtime gate | ok | Generated evidence satisfies existing poster checks: `browser_rendered=true`, `png_exported=true`, and passing overflow probe. |
| Config truthfulness | ok | Poster route/operator limitations now state root and bridge render paths are approval-gated and unavailable renderers remain inconclusive. |

### Root Poster Render Verification Commands

| Command | Result |
|---|---|
| `python3 -m py_compile tools/poster.py harness/plugins/autosci/tests/test_root_tool_abi.py` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_root_tool_abi.py harness/tests/evaluators/scientific/test_autosci_runtime_evidence_gate.py -q` | ok: 9 passed. |

### Remaining After Root Poster Render Repair

| Block | Status | Notes |
|---|---|---|
| Browser/provider render smoke | warn | Local approved renderer smoke passes; real browser/Playwright or screenshot providers still require environment-specific approval. |
| External source parity | blocked | Live S2/DeepXiv/Paper Copilot provider smoke remains the main external evidence blocker. |

## Phase 19 Paper Copilot Source CLI Repair

Logged: 2026-06-25 EDT

This follow-up adds an auditable root Paper Copilot provider CLI so venue-based
Paper Copilot source evidence is visible outside the internal discovery backend.

| Item | Status | Evidence |
|---|---|---|
| Root provider CLI | ok | Added `tools/fetch_paper_copilot.py venue <venue> <year>` for Paper Copilot venue lists. |
| Truthful network behavior | ok | With network disabled, the CLI emits inconclusive evidence and no synthesized papers. |
| Local provider smoke | ok | `file://` provider evidence can be read in offline tests, normalized to paper candidates, and marked completed. |
| Route visibility | ok | `/discover` primary tools now include `tools/fetch_paper_copilot.py venue` so provider ABI is covered by parity inventory. |

### Paper Copilot Verification Commands

| Command | Result |
|---|---|
| `python3 -m py_compile tools/fetch_paper_copilot.py harness/plugins/autosci/tests/test_source_cli_tools.py` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_source_cli_tools.py -q` | ok: 4 passed. |
| `python3 -m json.tool harness/plugins/autosci/config/feature_parity_routes.v1.json` | ok |
| `.venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci_feature_parity_after_executor_repairs_20260625.json` | ok: `full_count=0`, `partial_count=17`, `gated_count=11`, `missing_route_count=0`. |

### Remaining After Paper Copilot CLI Repair

| Block | Status | Notes |
|---|---|---|
| Live provider smoke | warn | S2, DeepXiv, and Paper Copilot have auditable provider paths; real internet/API success evidence remains environment/date dependent and must be captured under approved smoke. |
| Static full parity | blocked | Inventory remains non-full because routes still correctly distinguish partial/gated execution from always-on full native parity. |

## Phase 19 Executor And Source Provider Repair Rollup

Logged: 2026-06-25 EDT

This rollup records the verification pass after approved wiki mutation,
approval-gated TeX fallback, remote/local launch runtime evidence, SMTP send,
root poster render/export, Paper Copilot source CLI, and runtime schema/gate
repairs.

| Item | Status | Evidence |
|---|---|---|
| AutoSci plugin tests | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests -q` passed: 112 tests. |
| Scientific evaluator tests | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific -q` passed: 54 tests. |
| Operator smoke gate | ok | `bound_count=28`, `completed_count=0`, `partial_count=17`, `gated_count=11`, `failed_count=0`; generated evidence passed with approval-gated warning. |
| Feature parity gate | warn | `full_count=0`, `partial_count=17`, `gated_count=11`, `missing_route_count=0`; generated inventory passed with non-full warning. |
| Config/whitespace checks | ok | Route/operator/runtime schema JSON validation passed; `git diff --check` passed for changed AutoSci/tool/log files. |
| Generated artifact cleanup | ok | Removed untracked `app/data/graph.json` generated by visualization tests. |

### Current Full Parity Status After Executor Repairs

| Area | Status | Notes |
|---|---|---|
| Native route coverage | ok | All 28 AutoSci native skills remain routed and bound. |
| Approved side-effect executors | partial | Local approved executors now exist for wiki mutation, TeX/PDF compile fallback, remote/local launch evidence, SMTP send, and poster render/export. |
| Source/provider evidence | partial | S2, DeepXiv, Web, and Paper Copilot have auditable provider paths; live success evidence still depends on network/API availability and approved smoke. |
| Static full parity | blocked | The inventory still has `full_count=0` because routes intentionally remain partial/gated until real provider, model, remote, and publication runs are captured end to end. |

## Phase 19 Ask/Check Model Evidence Repair

Logged: 2026-06-25 EDT

This follow-up closes the immediate ask/check model-evidence gap without
pretending that missing provider output is a completed intelligence result.
Both paths now accept explicit `autosci_model_response.v1` evidence files or a
model command bridge that receives an `autosci_model_request.v1` payload on
stdin and returns normalized model evidence on stdout.

| Item | Status | Evidence |
|---|---|---|
| `$ask` model synthesis | ok | Added `--model-evidence` and `--model-command`; `ask_wiki` archives model stdout/stderr, records `model_output`, writes a `Model Synthesis` section, and carries model evidence ids into `research_memory_update.v1`. |
| `$check` quality review | ok | `check_wiki_health` now archives supplied model/reviewer evidence, includes it in findings/recommended changes, clears the prior “content quality still requires model evidence” runtime error only when model evidence is completed, and keeps missing evidence visible otherwise. |
| Truthfulness guard | ok | No model command/evidence still produces `unavailable` model status and the route remains partial; no deterministic substitute is used for LLM content quality or synthesis. |
| Route/binding docs | ok | Ask/check limitations now state that explicit model evidence/commands are supported while missing evidence remains inconclusive. |

### Ask/Check Model Evidence Verification Commands

| Command | Result |
|---|---|
| `python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_runs_ask_check_and_init_diagnostics harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_ask_and_check_read_workspace_wiki harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_ask_uses_model_command_with_retrieved_sources harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_check_uses_model_command_for_quality_review -q` | ok: 4 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific/test_workflow_evolution_gate.py harness/tests/evaluators/scientific/test_lifecycle_gate.py -q` | ok: 8 passed. |
| `python3 -m json.tool harness/plugins/autosci/config/feature_parity_routes.v1.json` and `feature_operator_bindings.v1.json` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests -q` | ok: 114 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific -q` | ok: 54 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific/test_autosci_operator_smoke_gate.py harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py -q` | ok: 6 passed. |
| `.venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci_feature_parity_after_ask_check_model_20260625.json` | ok: `full_count=0`, `partial_count=17`, `gated_count=11`, `missing_route_count=0`. |
| `git diff --check -- harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/config/feature_parity_routes.v1.json harness/plugins/autosci/config/feature_operator_bindings.v1.json harness/plugins/autosci/tests/test_autosci_skill_shim.py docs/integrations/autosci/phase19-progress-log.md` | ok |

### Remaining After Ask/Check Model Evidence Repair

| Block | Status | Notes |
|---|---|---|
| Live model provider smoke | warn | Local command-bridge evidence is verified; real provider/API execution still needs approved credentials and runtime smoke evidence. |
| Static full parity | blocked | Ask/check are stronger but still correctly remain partial until a full end-to-end AutoSci run captures real retrieval, model, source, runtime, review, and publication evidence. |

## Phase 19 Exp-Eval Review Evidence Repair

Logged: 2026-06-25 EDT

This follow-up closes the formal `/exp-eval` evidence handoff gap. The shim now
exposes explicit claim, experiment result, code evidence, and Review LLM evidence
inputs for review-backed claim verdicts, and the bridge keeps Review LLM output
as an independent second opinion instead of using it to override experiment
outcomes.

| Item | Status | Evidence |
|---|---|---|
| Native CLI evidence inputs | ok | Added `--experiment-result-evidence`, `--claims-evidence`, and `--code-evidence` to the AutoSci skill shim and native options. |
| Evidence list loading | ok | `experiment_result`, `claims`, and `code_evidence` loaders now accept append/list inputs rather than only scalar paths. |
| Claim id routing | ok | `$exp-eval <claim>` now maps the positional target into `claim_id`, avoiding fallback to `claim-001`. |
| Review LLM binding | ok | `verify_claim` now reads completed `artifact_review.v1` Review LLM evidence, archives it as `claim_review_llm_evidence_json`, appends review evidence ids, and stores a `review_llm` audit block in `claim_verdict.v1`. |
| Approved wiki writeback | ok | `$exp-eval --write --approval-ref ... --wiki-root ...` can update linked wiki idea/experiment frontmatter, append wiki log/graph evidence, and emit `claim_verdict_writeback.v1`; unapproved or incomplete evidence remains inconclusive. |
| Truthfulness guard | ok | Review LLM evidence does not upgrade missing/failed/inconclusive experiment evidence; verdict outcome remains derived from supplied experiment result evidence. |

### Exp-Eval Review Evidence Verification Commands

| Command | Result |
|---|---|
| `python3 -m py_compile harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/adapters/autosci_to_claim_verdict.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_exp_eval_merges_experiment_code_and_review_llm_evidence harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_pilot_eval_uses_runtime_evidence harness/tests/evaluators/scientific/test_claim_verdict_gate.py -q` | ok: 6 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_exp_eval_merges_experiment_code_and_review_llm_evidence harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_exp_eval_write_updates_wiki_with_approval harness/tests/evaluators/scientific/test_claim_verdict_gate.py -q` | ok: 6 passed. |
| `python3 -m json.tool harness/plugins/autosci/config/feature_parity_routes.v1.json` and `feature_operator_bindings.v1.json` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests -q` | ok: 116 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific -q` | ok: 54 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific/test_autosci_operator_smoke_gate.py harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py -q` | ok: 6 passed. |
| `.venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci_feature_parity_after_exp_eval_20260625.json` | ok: `full_count=0`, `partial_count=17`, `gated_count=11`, `missing_route_count=0`. |
| `git diff --check -- harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/adapters/autosci_to_claim_verdict.py harness/plugins/autosci/config/feature_parity_routes.v1.json harness/plugins/autosci/config/feature_operator_bindings.v1.json harness/plugins/autosci/tests/test_autosci_skill_shim.py docs/integrations/autosci/phase19-progress-log.md` | ok |

### Remaining After Exp-Eval Review Evidence Repair

| Block | Status | Notes |
|---|---|---|
| Idea status mutation | ok | Approved write-back now updates linked wiki idea/experiment pages with verdict frontmatter, log, graph edge, and lightweight wiki rebuild artifacts. |
| Static full parity | blocked | `/exp-eval` is stronger but remains partial until end-to-end provider/runtime/review audits are captured under real project conditions. |

## Phase 19 Exp-Design Review Evidence Repair

Logged: 2026-06-25 EDT

This follow-up closes the `/exp-design` review-backed design validation gap
without executing an experiment or treating missing Review LLM output as a pass.
The design route can now attach completed Review LLM evidence directly to
`experiment_plan.v1`.

| Item | Status | Evidence |
|---|---|---|
| Native route override | ok | Non-smoke `$exp-design <target>` now runs `design_experiment` directly instead of being blocked by source-required fixture dependencies. |
| Review LLM validation | ok | `design_experiment` reads completed `artifact_review.v1` Review LLM evidence, archives it as `experiment_design_review_llm_evidence_json`, and stores `review_llm` plus evidence ids in `experiment_plan.v1`. |
| Plan gate compatibility | ok | Review validation adds a success criterion while preserving required experiment-plan fields, approval semantics, and safe execution modes. |
| Truthfulness guard | ok | Missing or incomplete Review LLM evidence remains a limitation; it does not mark the plan reviewed. |

### Exp-Design Review Evidence Verification Commands

| Command | Result |
|---|---|
| `python3 -m py_compile harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/adapters/autosci_to_experiment_plan.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_exp_design_attaches_review_llm_validation harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_blocks_unapproved_exp_run_deploy_without_fixture_support harness/tests/evaluators/scientific/test_experiment_plan_gate.py -q` | ok: 4 passed. |
| `python3 -m json.tool harness/plugins/autosci/config/feature_parity_routes.v1.json` and `feature_operator_bindings.v1.json` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests -q` | ok: 117 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific -q` | ok: 54 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific/test_autosci_operator_smoke_gate.py harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py -q` | ok: 6 passed. |
| `.venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci_feature_parity_after_exp_design_20260625.json` | ok: `full_count=0`, `partial_count=17`, `gated_count=11`, `missing_route_count=0`. |
| `git diff --check -- harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/adapters/autosci_to_claim_verdict.py harness/plugins/autosci/adapters/autosci_to_experiment_plan.py harness/plugins/autosci/config/feature_parity_routes.v1.json harness/plugins/autosci/config/feature_operator_bindings.v1.json harness/plugins/autosci/tests/test_autosci_skill_shim.py docs/integrations/autosci/phase19-progress-log.md` | ok |

### Remaining After Exp-Design Review Evidence Repair

| Block | Status | Notes |
|---|---|---|
| Runtime artifact discovery | warn | Design validation is attached, but real execution artifacts still depend on approved runtime/remote paths. |
| Static full parity | blocked | `/exp-design` remains partial until reviewed design, approved execution, collection, and downstream verdict/writeback are audited end to end. |

## Phase 19 Pilot Eval Approved Writeback Repair

Logged: 2026-06-25 EDT

This follow-up closes the `/exp-pilot-eval` wiki mutation gap for lenient pilot
verdicts. The route still requires explicit approval before mutating wiki state.

| Item | Status | Evidence |
|---|---|---|
| Runtime verdict path | ok | Existing pilot runtime evidence continues to produce completed lenient `claim_verdict.v1` when the runtime outcome supports the pilot claim. |
| Approved wiki writeback | ok | `$exp-pilot-eval --write --approval-ref ... --wiki-root ...` now updates linked wiki idea/experiment frontmatter, appends wiki log/graph evidence, and emits a `pilot_verdict_writeback_json` artifact. |
| Approval boundary | ok | Without `--write` and `--approval-ref`, pilot verdicts do not mutate wiki state. |

### Pilot Eval Writeback Verification Commands

| Command | Result |
|---|---|
| `python3 -m py_compile harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_pilot_eval_uses_runtime_evidence harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_pilot_eval_write_updates_wiki_with_approval harness/tests/evaluators/scientific/test_claim_verdict_gate.py -q` | ok: 6 passed. |
| `python3 -m json.tool harness/plugins/autosci/config/feature_parity_routes.v1.json` and `feature_operator_bindings.v1.json` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests -q` | ok: 118 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific -q` | ok: 54 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific/test_autosci_operator_smoke_gate.py harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py -q` | ok: 6 passed. |
| `.venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci_feature_parity_after_pilot_writeback_20260625.json` | ok: `full_count=0`, `partial_count=17`, `gated_count=11`, `missing_route_count=0`. |
| `git diff --check -- harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/adapters/autosci_to_claim_verdict.py harness/plugins/autosci/adapters/autosci_to_experiment_plan.py harness/plugins/autosci/config/feature_parity_routes.v1.json harness/plugins/autosci/config/feature_operator_bindings.v1.json harness/plugins/autosci/tests/test_autosci_skill_shim.py docs/integrations/autosci/phase19-progress-log.md` | ok |

### Remaining After Pilot Eval Writeback Repair

| Block | Status | Notes |
|---|---|---|
| Remote/runtime provider audit | warn | Pilot verdict and writeback paths are local-evidence verified; real remote runtime evidence still depends on approved execution providers. |
| Static full parity | blocked | `/exp-pilot-eval` remains partial until pilot execution, collection, verdict, and wiki mutation are audited in one approved run. |

## Phase 19 Paper Draft Compile Handoff Repair

Logged: 2026-06-25 EDT

This follow-up closes the immediate `/paper-draft` compile/PDF handoff gap. The
draft route still does not execute TeX itself; it consumes verified
approval-gated compile runtime evidence from the existing paper compile path and
threads the compiled PDF into report and publication-bundle artifacts.

| Item | Status | Evidence |
|---|---|---|
| Compile handoff verifier | ok | `write_report` now builds `paper_draft_compile_handoff.v1` from `compile_paper` approval/runtime/after evidence and only marks it completed when compile semantic runtime verifies the PDF. |
| Scientific report output | ok | `scientific_report.v1` now preserves `compile_handoff`, adds a compiled-paper section when verified, and includes `paper_draft_compile_handoff_json`, runtime evidence, and `compiled_pdf` artifacts. |
| Publication bundle handoff | ok | The publication bundle sidecar now carries verified compile/PDF handoff artifacts instead of only Markdown/LaTeX sidecars. |
| Truthfulness guard | ok | Missing or incomplete approval/runtime/PDF evidence remains an explicit limitation and does not become a compiled publication claim. |

### Paper Draft Compile Handoff Verification Commands

| Command | Result |
|---|---|
| `python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/adapters/autosci_to_scientific_report.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_paper_draft_writes_latex_source harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_paper_draft_includes_verified_compile_pdf_handoff harness/tests/evaluators/scientific/test_report_gate.py harness/tests/evaluators/scientific/test_paper_gate.py -q` | ok: 8 passed. |
| `python3 -m json.tool harness/plugins/autosci/config/feature_parity_routes.v1.json` and `feature_operator_bindings.v1.json` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests -q` | ok: 119 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific -q` | ok: 54 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific/test_autosci_operator_smoke_gate.py harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py -q` | ok: 6 passed. |
| `.venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci_feature_parity_after_paper_draft_compile_handoff_20260625.json` | ok: `full_count=0`, `partial_count=17`, `gated_count=11`, `missing_route_count=0`. |
| `git diff --check -- harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/adapters/autosci_to_claim_verdict.py harness/plugins/autosci/adapters/autosci_to_experiment_plan.py harness/plugins/autosci/adapters/autosci_to_scientific_report.py harness/plugins/autosci/config/feature_parity_routes.v1.json harness/plugins/autosci/config/feature_operator_bindings.v1.json harness/plugins/autosci/tests/test_autosci_skill_shim.py docs/integrations/autosci/phase19-progress-log.md` | ok |

### Remaining After Paper Draft Compile Handoff Repair

| Block | Status | Notes |
|---|---|---|
| Real manuscript synthesis | warn | Draft and compile handoff are evidence-linked; full route parity still needs a real wiki-output manuscript synthesis audit under project evidence. |
| Static full parity | blocked | `/paper-draft` remains partial until live/source/review/compile evidence is captured in an end-to-end publication run. |

## Phase 19 Paper Plan Compile Audit Repair

Logged: 2026-06-25 EDT

This follow-up wires the same verified compile/PDF handoff into `/paper-plan`.
The plan route remains a planning artifact, but it can now carry downstream
compile audit evidence when that evidence has already been produced and
approved.

| Item | Status | Evidence |
|---|---|---|
| Compile audit section | ok | `plan_report` now adds a compile-audit section and `compile_handoff` output when approved compile runtime/PDF evidence is supplied. |
| Artifact propagation | ok | `paper_plan_json`, `scientific_report.v1`, and report artifacts now include the verified compile handoff JSON, runtime evidence, and compiled PDF. |
| Compatibility | ok | Existing citation-map + Review LLM completion behavior remains unchanged when compile evidence is not supplied. |
| Truthfulness guard | ok | Missing/incomplete compile evidence remains `not_requested` or `inconclusive`; the paper plan is not treated as a compiled publication. |

### Paper Plan Compile Audit Verification Commands

| Command | Result |
|---|---|
| `python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_paper_plan_completes_with_citations_and_review_llm harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_paper_plan_attaches_verified_compile_handoff harness/tests/evaluators/scientific/test_report_gate.py -q` | ok: 6 passed. |
| `python3 -m json.tool harness/plugins/autosci/config/feature_parity_routes.v1.json` and `feature_operator_bindings.v1.json` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests -q` | ok: 120 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific -q` | ok: 54 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific/test_autosci_operator_smoke_gate.py harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py -q` | ok: 6 passed. |
| `.venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci_feature_parity_after_paper_plan_compile_audit_20260625.json` | ok: `full_count=0`, `partial_count=17`, `gated_count=11`, `missing_route_count=0`. |
| `git diff --check -- harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/adapters/autosci_to_claim_verdict.py harness/plugins/autosci/adapters/autosci_to_experiment_plan.py harness/plugins/autosci/adapters/autosci_to_scientific_report.py harness/plugins/autosci/config/feature_parity_routes.v1.json harness/plugins/autosci/config/feature_operator_bindings.v1.json harness/plugins/autosci/tests/test_autosci_skill_shim.py docs/integrations/autosci/phase19-progress-log.md` | ok |

### Remaining After Paper Plan Compile Audit Repair

| Block | Status | Notes |
|---|---|---|
| Live idea-graph/figure/table plan | warn | Citation/review/compile audit evidence can be attached, but full parity still needs real idea-graph-derived figure/table planning under project evidence. |
| Static full parity | blocked | `/paper-plan` remains partial until the full publication lifecycle is captured with real source, review, compile, and submission evidence. |

## Phase 19 Source Fan-In Writeback Repair

Logged: 2026-06-25 EDT

This follow-up closes the approved wiki fan-in gap for `/init` and
`/daily-arxiv`. The bridge still does not execute live network fetches, feed
scheduling, or SMTP delivery itself; it now consumes verified runtime source
candidate manifests and, when `--write` is explicit, writes those approved
candidates into the Solar AutoSci wiki state layer.

| Item | Status | Evidence |
|---|---|---|
| Runtime candidate fan-in | ok | `init_sources` and `daily_arxiv_prepare_finalize` now emit `source_fan_in_writeback.v1` when `--write` is requested with a verified approval/runtime contract. |
| Wiki mutation layer | ok | Approved candidates are written to `wiki/papers/*.md`, `wiki/log.md`, `wiki/graph/edges.jsonl`, `wiki/index.md`, and `wiki/graph/context_brief.md`. |
| Evidence propagation | ok | `literature_discovery.v1` now preserves `outputs.source_fan_in` and carries a `source_fan_in_writeback_json` artifact. |
| Truthfulness guard | ok | Without `--write`, verified candidates remain output-only; without a complete approval/runtime contract, fan-in side effects stay inconclusive. |

### Source Fan-In Verification Commands

| Command | Result |
|---|---|
| `python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/adapters/autosci_to_literature_discovery.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_init_write_fans_runtime_sources_into_wiki harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_daily_arxiv_write_auto_ingests_runtime_digest -q` | ok: 2 passed. |
| `python3 -m json.tool harness/plugins/autosci/config/feature_parity_routes.v1.json` and `feature_operator_bindings.v1.json` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_init_uses_verified_runtime_source_manifest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_daily_arxiv_uses_verified_runtime_digest -q` | ok: 2 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py -q` | ok: 4 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests -q` | ok: 122 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific -q` | ok: 54 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific/test_autosci_operator_smoke_gate.py harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py -q` | ok: 6 passed. |
| `.venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci_feature_parity_after_source_fan_in_20260625.json` | ok: `full_count=0`, `partial_count=17`, `gated_count=11`, `missing_route_count=0`. |
| `git diff --check -- harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/adapters/autosci_to_literature_discovery.py harness/plugins/autosci/config/feature_parity_routes.v1.json harness/plugins/autosci/config/feature_operator_bindings.v1.json harness/plugins/autosci/tests/test_autosci_skill_shim.py docs/integrations/autosci/phase19-progress-log.md` | ok |

### Remaining After Source Fan-In Writeback Repair

| Block | Status | Notes |
|---|---|---|
| Live source providers | warn | Approved manifests can now fan into wiki state, but real arXiv/S2 fetch execution, scheduling, and SMTP delivery remain provider/approval-gated. |
| Static full parity | blocked | `/init` and `/daily-arxiv` remain partial/gated until live source provider runs are captured and audited end to end. |

## Phase 19 Refine Approved Apply Repair

Logged: 2026-06-25 EDT

This follow-up closes the immediate `/refine` proposal-only gap for approved
artifact replacement. The route still does not rerun downstream quality gates by
itself; it now supports a narrowly scoped, auditable apply path when the user
supplies a verified approval contract plus an approved `after_artifact`.

| Item | Status | Evidence |
|---|---|---|
| Approved refine apply | ok | `refine_artifact` can now replace an existing target artifact from `after_artifact` only when `--execute-approved`, `--approval-ref`, allowlist, runtime, before, and after artifacts are present. |
| Writeback evidence | ok | Applied refine runs emit `refine_apply_writeback.v1`, `refine_apply_writeback_json`, `refined_artifact`, and optional wiki log/rebuild artifacts. |
| Workflow ABI gate | ok | `workflow_evolution.v1` schema/gate now permits `application_state=applied` only for verified refine apply evidence with an approval contract and writeback artifact; general workflow evolution remains proposal-only. |
| Truthfulness guard | ok | Unapproved refine, setup, reset, and lifecycle control routes still emit proposed-only evidence and keep protected edits blocked. |

### Refine Apply Verification Commands

| Command | Result |
|---|---|
| `python3 -m py_compile harness/evaluators/scientific/workflow_evolution_gate.py harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `python3 -m json.tool harness/schemas/evidence/workflow_evolution.v1.schema.json` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific/test_workflow_evolution_gate.py harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_refine_applies_approved_after_artifact harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_runs_remaining_gated_backend_actions -q` | ok: 4 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests -q` | ok: 123 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific -q` | ok: 54 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific/test_autosci_operator_smoke_gate.py harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py -q` | ok: 6 passed. |
| `.venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci_feature_parity_after_refine_apply_20260625.json` | ok: `full_count=0`, `partial_count=17`, `gated_count=11`, `missing_route_count=0`. |
| `git diff --check -- harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/adapters/autosci_to_literature_discovery.py harness/plugins/autosci/config/feature_parity_routes.v1.json harness/plugins/autosci/config/feature_operator_bindings.v1.json harness/plugins/autosci/tests/test_autosci_skill_shim.py harness/evaluators/scientific/workflow_evolution_gate.py harness/schemas/evidence/workflow_evolution.v1.schema.json docs/integrations/autosci/phase19-progress-log.md` | ok |

### Remaining After Refine Apply Repair

| Block | Status | Notes |
|---|---|---|
| Quality gate rerun | warn | Approved artifact replacement is covered, but automated post-refine lint/review/test reruns still depend on approved runtime evidence. |
| Static full parity | blocked | `/refine` remains gated until apply + post-refine quality gates are audited in one approved run. |

## Phase 19 Paper Compile Fix Writeback Repair

Logged: 2026-06-25 EDT

This follow-up closes the immediate `/paper-compile --fix` proposal-only gap.
The compile route still does not claim publication success without a compiled
PDF or verified compile runtime evidence; it can now apply an approved fixed TeX
source before diagnostics or approved TeX executor execution.

| Item | Status | Evidence |
|---|---|---|
| Approved TeX source fix | ok | `compile_paper` now replaces the target `.tex` source from `after_artifact` only when `--fix`, `--execute-approved`, approval, allowlist, and before evidence are supplied. |
| Fix writeback evidence | ok | Applied fixes emit `paper_compile_fix_writeback.v1`, `paper_compile_fix_writeback_json`, source hashes, and the updated `latex_source` artifact. |
| Compile status guard | ok | A fixed source alone does not mark publication complete; completion still requires a discovered PDF or verified compile runtime evidence. |
| Diagnostics integration | ok | The compile checklist records `fix_writeback` and marks auto-fix checks `ok` only when the approved writeback applies. |

### Paper Compile Fix Verification Commands

| Command | Result |
|---|---|
| `python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_runs_paper_compile_fix_diagnostics harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_paper_compile_fix_applies_approved_after_artifact harness/tests/evaluators/scientific/test_paper_gate.py -q` | ok: 4 passed. |
| `python3 -m json.tool harness/plugins/autosci/config/feature_parity_routes.v1.json` and `feature_operator_bindings.v1.json` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests -q` | ok: 124 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific -q` | ok: 54 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific/test_autosci_operator_smoke_gate.py harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py -q` | ok: 6 passed. |
| `.venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci_feature_parity_after_paper_compile_fix_20260625.json` | ok: `full_count=0`, `partial_count=17`, `gated_count=11`, `missing_route_count=0`. |
| `git diff --check -- harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/adapters/autosci_to_literature_discovery.py harness/plugins/autosci/config/feature_parity_routes.v1.json harness/plugins/autosci/config/feature_operator_bindings.v1.json harness/plugins/autosci/tests/test_autosci_skill_shim.py harness/evaluators/scientific/workflow_evolution_gate.py harness/schemas/evidence/workflow_evolution.v1.schema.json docs/integrations/autosci/phase19-progress-log.md` | ok |

### Remaining After Paper Compile Fix Repair

| Block | Status | Notes |
|---|---|---|
| End-to-end compile fix rerun | warn | Source fix writeback is covered, but full compile-fix parity still needs approved fix + TeX execution + PDF checklist in one audited run. |
| Static full parity | blocked | `/paper-compile` remains gated until approved toolchain execution and PDF validation are audited across the native workflow. |

## Phase 19 Autosci Dollar Command Repair

Logged: 2026-06-25 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_skill_shim.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

This fixes single-token `$` command parsing so one-shot invocations such as
`"$survey --format latex --topic test"` no longer get interpreted as an
invalid skill name.

| Command | Result |
|---|---|
| `python3 -m py_compile harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_runs_single_token_dollar_command_with_flags -q` | ok: 1 passed. |

### Remaining After Dollar Command Repair

| Block | Status | Notes |
|---|---|---|
| Dollar-command passthrough | ok | Single-token `$skill --flag ...` now resolves to a normalized `skill` command. |
| Static full parity | blocked | Remaining blockers remain in core execution paths (`review`, `exp-run` lifecycle, `paper-compile` toolchain, online evidence fetch). |

## Phase 19 Exp-Run Native Execution Repair

Logged: 2026-06-25 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/bin/autosci_skill_shim.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

### Exp-Run Execution Fix

This repair step enables genuine approved command execution for `run_experiment`
instead of report-only completion:
- command selection now normalizes executable paths from allowlisted plans/commands.
- runtime output parser now attempts to recover JSON payloads from command stdout lines.
- `run_experiment` now computes result-collection status before writing result artifacts (fixing an untested path bug).
- `--execute-approved` runtime path now records `run_experiment_result.json` and `run_experiment_runtime_evidence.json` as part of completed outcomes.

Added regression test:
- `test_autosci_skill_shim_exp_run_executes_approved_native_command` validates that
  `--execute-approved` with allowlist/before-artifact evidence executes the command,
  writes command marker output, and mutates wiki/experiment state from real output.

### Verification commands

| Command | Result |
|---|---|
| `python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_exp_run_executes_approved_native_command -q` | ok: 1 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_exp_run_uses_verified_runtime_evidence_and_mutates_wiki -q` | ok: 1 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py -q` | ok: 76 passed. |

### Remaining After Exp-Run Execution Repair

| Block | Status | Notes |
|---|---|---|
| Experiment execution lifecycle | partial | Real command execution is now reachable behind approval, but approval/collect/eval chain coverage still needs a full approved deploy→collect→verify path and state transitions across workflow evidence. |
| Static full parity | blocked | `review`, `paper-compile` runtime execution, novelty gate, and online evidence fetch remain incomplete. |

## Phase 19 Exp-Run Artifact Return Repair

Logged: 2026-06-25 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Fix summary:
- `run_experiment` now adds runtime artifacts from `contract.after_artifacts` (`run_experiment_result_json`) to its returned artifact list.
- `run_experiment` now adds missing executor artifacts (`executor_stdout`, `executor_stderr`) by consuming explicit paths returned by executor.
- `_execute_experiment_if_approved` now returns `stdout_path` and `stderr_path` explicitly so action-level artifacts can reference the captured process streams.

### Exp-Run Artifact Return Verification

| Command | Result |
|---|---|
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_exp_run_executes_approved_native_command -q` | ok: 1 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_exp_run_uses_verified_runtime_evidence_and_mutates_wiki harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_exp_collect_uses_verified_runtime_evidence -q` | ok: 2 passed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_exp_run_executes_approved_native_command` | ok: 1 passed. |

### Remaining After Exp-Run Artifact Return Repair

| Block | Status | Notes |
|---|---|---|
| Exp-run artifact completeness | ok | Native run branch now returns `run_experiment_result_json` + executor stream artifacts when `--execute-approved` path is used. |
| Lifecycle parity | partial | `collect`/`eval`/resume chains and full experiment state transitions still need one approved end-to-end lifecycle run. |

## Phase 19 Review Artifact Resolver Repair

Logged: 2026-06-25 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/backends/artifact_review.py`
- `docs/integrations/autosci/phase19-progress-log.md`

### Review Artifact Resolver Fix Plan

- `artifact_review._path_candidates` / `_resolve_artifact` now treats relative targets that already include `harness/` by adding a normalized candidate without the `harness/` prefix.
- This addresses false misses where `_resolve_artifact` only checked `.../harness/harness/...` paths and could not resolve a workspace artifact passed as `harness/artifacts/...`.

### Review Artifact Resolver Fix Verification

| Command | Result |
|---|---|
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_review_resolves_harness_prefixed_workspace_path -q` | ok: 1 passed. |
| `python3 harness/plugins/autosci/bin/autosci_skill_shim.py text "\$review --paper harness/artifacts/autosci/workspace/wiki/ideas/idea-001.md --difficulty hard --focus method --run-id harness-review-test-review-fixed"` | ok: resolved to `harness/artifacts/autosci/workspace/wiki/ideas/idea-001.md` with `status=completed`, `passed_count=1`, `schema_only_count=0`. |

## Phase 19 Route Truthfulness Sync For Steps 45-48

Logged: 2026-06-26 EDT

Planned file changes (pre-fix):
- `docs/integrations/autosci/phase19-progress-log.md`

### Route Sync Scope

This documentation-only sync records route-parity changes already made during
the scheduler/native lifecycle continuation:

- Step 45: `$research` route limitations now say default scheduler runs block
  at `report_plan` / `publication_produce` unless explicit Review LLM and
  compile/PDF evidence are supplied with external-evidence dispatch.
- Step 45: `$research.primary_tools` now points at the real
  `harness/tools/run_scientific_lifecycle_smoke.py` path instead of the missing
  `tools/run_scientific_lifecycle_smoke.py`.
- Step 47: `/exp-status` route limitations now distinguish approved
  `tools/remote.py check` execution from registry-only status and keep live
  SSH/provider polling partial.
- Step 48: `/ask`, `/check`, and `/ideate` route limitations now describe
  persisted model-command request/response provenance without claiming hosted
  provider parity.

### Remaining After Route Truthfulness Sync

| Block | Status | Notes |
|---|---|---|
| Route truthfulness for continuation steps | ok | Phase 19 now references the route config truthfulness updates made in Steps 45, 47, and 48. |
| Full parity | blocked | Route inventory remains 0 full, 17 partial, 11 gated until live providers, generic scheduler dispatch, remote polling, and publication parity are proven. |

### Route Truthfulness Sync Verification

| Command | Result |
|---|---|
| `git diff --check -- docs/integrations/autosci/phase19-progress-log.md` | ok |
| `rg -n "Phase 19 Route Truthfulness Sync|Step 45|Step 47|Step 48" docs/integrations/autosci/phase19-progress-log.md` | ok: sync section and referenced continuation steps are present. |

## Phase 19 Publication Review Boundary Sync

Logged: 2026-06-26 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/bin/autosci_skill_shim.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: tighten `$paper-plan` route truthfulness by recording an explicit
Review LLM boundary object instead of only a permissive boolean completion flag.

### Publication Review Boundary Result

| Check | Status | Evidence |
|---|---|---|
| `$paper-plan` boundary object | ok | `paper_plan_json` now includes `autosci_publication_review_boundary.v1`. |
| Boundary completion rules | ok | Completion requires `artifact_review.v1`, completed payload status, LLM review mode, `review_available=true`, and non-empty evidence ids. |
| Weak Review LLM evidence | ok | Weak Review LLM-shaped JSON is recorded as invalid/inconclusive and does not complete the plan. |
| Route limitation | ok | `/paper-plan` limitation now states explicit Review LLM boundary requirements. |

### Publication Review Boundary Verification

| Command | Result |
|---|---|
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py -k 'paper_plan_completes_with_citations_and_review_llm or paper_plan_rejects_weak_review_llm_boundary or paper_plan_attaches_verified_compile_handoff' -q` | ok: 3 passed |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py -k 'paper_plan or paper_draft or paper_compile or research_scheduler_executes_approved_publication_compile' -q` | ok: 13 passed |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py -q` | ok: 101 passed with elevated local bind permission |
| `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step49.json` | warn: 28 routed, 0 missing, 0 full, 17 partial, 11 gated |
| `git diff --check` over Step 49 files | ok before log write |

## Phase 19 Scheduler Production Boundary Sync

Logged: 2026-06-26 EDT

Planned file changes (pre-fix):
- `harness/tools/run_scientific_lifecycle_smoke.py`
- `harness/plugins/autosci/bin/autosci_skill_shim.py`
- `harness/tests/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: tighten `$research` route truthfulness by adding a scheduler
production-dispatch boundary and strict failure flag for smoke/fixture-backed
lifecycle runs.

### Scheduler Production Boundary Result

| Check | Status | Evidence |
|---|---|---|
| `$research` dispatch boundary | ok | Scheduler lifecycle summaries now include `autosci_scheduler_dispatch_boundary.v1`. |
| Strict production dispatch | ok | `--scheduler-require-production-dispatch` fails while bounded smoke runner or fixture/smoke input markers remain. |
| Route limitation | ok | `/research` now documents the production-dispatch boundary failure condition without changing `coverage_status`. |

### Scheduler Production Boundary Verification

| Command | Result |
|---|---|
| Runner + shim targeted tests | ok: 2 passed |
| Lifecycle smoke + runtime gate subset | ok: 25 passed |
| `$research` scheduler shim subset | ok: 8 passed |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific -q` | ok: 87 passed |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py -q` | ok: 102 passed with elevated local bind permission |
| `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step50.json` | warn: 28 routed, 0 missing, 0 full, 17 partial, 11 gated |
| `git diff --check` over Step 50 files | ok before log write |

## Phase 19 Source Provider Boundary Sync

Logged: 2026-06-26 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/adapters/autosci_to_literature_discovery.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: tighten source/discover route truthfulness by requiring non-fixture
provider channels before source runtime evidence is treated as completed.

### Source Provider Boundary Result

| Check | Status | Evidence |
|---|---|---|
| Source provider boundary | ok | `literature_discovery.v1.outputs.source_provider_boundary` records `autosci_source_provider_boundary.v1`. |
| Generic runtime candidates | ok | Generic `approved_runtime` candidates no longer complete source runtime evidence without provider channels. |
| Provider-backed candidates | ok | `search_s2` channel runtime evidence completes and records provider boundary proof. |
| Route limitation | ok | `/discover`, `/init`, and `$research --online` limitations now describe provider boundary requirements. |

### Source Provider Boundary Verification

| Command | Result |
|---|---|
| Source-boundary targeted tests | ok: 2 passed |
| Literature backend/source CLI subset | ok: 6 passed |
| Source-related shim subset | ok: 6 passed |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific -q` | ok: 87 passed |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py -q` | ok: 103 passed with elevated local bind permission |
| `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step51.json` | warn: 28 routed, 0 missing, 0 full, 17 partial, 11 gated |
| `git diff --check` over Step 51 files | ok before log write |

## Phase 19 Remote Poll Boundary Sync

Logged: 2026-06-26 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: tighten `$exp-status` route truthfulness by emitting an explicit
remote poll boundary that separates local run-dir status-file checks from live
SSH/provider polling.

### Remote Poll Boundary Result

| Check | Status | Evidence |
|---|---|---|
| Runtime boundary | ok | Approved `$exp-status` remote-check evidence includes `autosci_remote_poll_boundary.v1`. |
| Local status check classification | ok | `tools/remote.py check` against local `run_dir/status.json` now reports boundary status `local_run_dir_check`, not live provider polling. |
| Route limitation | ok | `/exp-status` documents that local run-dir status-file checks do not count as live SSH/provider polling. |

### Remote Poll Boundary Verification

| Command | Result |
|---|---|
| `py_compile` bridge/tests | ok |
| route config `json.tool` | ok |
| `$exp-status` approved remote-check boundary test | ok: 1 passed |
| exp-status/run/collect remote subset | ok: 12 passed |
| runtime binding audit | ok: 28 nodes, 2 workflows, 0 issues |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py -q` | ok: 103 passed with elevated local bind permission |
| `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step52.json` | warn: 28 routed, 0 missing, 0 full, 17 partial, 11 gated |
| `git diff --check` over Step 52 files | ok before log write |

## Phase 19 Approved Live Remote Status Command Sync

Logged: 2026-06-26 EDT

Planned file changes (pre-fix):
- `tools/remote.py`
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: add an approved live/provider status command path that can satisfy the
remote poll boundary without weakening allowlist or approval requirements.

### Approved Live Remote Status Command Result

| Check | Status | Evidence |
|---|---|---|
| `tools/remote.py check --status-command` | ok | Live/provider status command path is approval-gated and allowlisted. |
| Remote poll boundary | ok | Approved status command payload can satisfy `autosci_remote_poll_boundary.v1` with transport/session metadata and `remote_state`. |
| Local check preservation | ok | Plain run-dir checks still report `local_run_dir_check`, not live polling. |
| Route limitation | ok | `/exp-status` now names approved live/provider status command execution while keeping real external connectivity smoke pending. |

### Approved Live Remote Status Command Verification

| Command | Result |
|---|---|
| `py_compile` tools/bridge/tests | ok |
| route config `json.tool` | ok |
| local + live `$exp-status` targeted tests | ok: 2 passed |
| exp-status/run/collect remote subset | ok: 13 passed |
| runtime binding audit | ok: 28 nodes, 2 workflows, 0 issues |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py -q` | ok: 104 passed with elevated local bind permission |
| `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step53.json` | warn: 28 routed, 0 missing, 0 full, 17 partial, 11 gated |
| `git diff --check` over Step 53 files | ok before log write |

## Phase 19 Remote Pull Results Boundary Sync

Logged: 2026-06-26 EDT

Planned file changes (pre-fix):
- `tools/remote.py`
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: add an approved remote/provider pull-results path and collection
boundary so local result-dir reads are not counted as live provider collection.

### Remote Pull Results Boundary Result

| Check | Status | Evidence |
|---|---|---|
| `tools/remote.py pull-results --pull-command` | ok | Live/provider pull-results command path is approval-gated and allowlisted. |
| Remote collection boundary | ok | Collect runtime evidence includes `autosci_remote_collection_boundary.v1`. |
| Local collection preservation | ok | Plain result-dir reads report `local_result_dir_collection`, not live provider collection. |
| Route limitation | ok | `/exp-run` names approved live/provider pull-results boundary and keeps distributed exactly-once/external smoke pending. |

### Remote Pull Results Boundary Verification

| Command | Result |
|---|---|
| `py_compile` tools/bridge/tests | ok |
| route config `json.tool` | ok |
| local + live pull-results targeted tests | ok: 2 passed |
| exp-status/run/collect remote subset | ok: 15 passed |
| runtime binding audit | ok: 28 nodes, 2 workflows, 0 issues |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py -q` | ok: 105 passed with elevated local bind permission |
| `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step54.json` | warn: 28 routed, 0 missing, 0 full, 17 partial, 11 gated |
| `git diff --check` over Step 54 files | ok before log write |

## Phase 19 Scheduler Replay Resume Boundary Sync

Logged: 2026-06-26 EDT

Planned file changes (pre-fix):
- `harness/tools/run_scientific_lifecycle_smoke.py`
- `harness/tests/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: add scheduler replay/resume evidence so lifecycle dispatch cannot be
mistaken for production parity without durable node state and no-rerun proof.

### Scheduler Replay Resume Boundary Result

| Check | Status | Evidence |
|---|---|---|
| Resume boundary | ok | Resume summaries emit `autosci_scheduler_resume_boundary.v1`. |
| No-rerun proof | ok | Boundary records reused-node fingerprints, changed reused nodes, dispatched nodes, and `no_rerun_verified`. |
| Route limitation | ok | `/research` now names resume boundary while keeping non-smoke dispatcher and lease/runtime audit pending. |

### Scheduler Replay Resume Boundary Verification

| Command | Result |
|---|---|
| `py_compile` runner/test | ok |
| route config `json.tool` | ok |
| human-gate resume targeted test | ok: 1 passed |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific -q` | ok: 87 passed |
| `$research` scheduler shim subset | ok: 8 passed |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py -q` | ok: 105 passed with elevated local bind permission |
| `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step55.json` | warn: 28 routed, 0 missing, 0 full, 17 partial, 11 gated |
| `git diff --check` over Step 55 files | ok before log write |

## Phase 19 Scheduler Lease Boundary Sync

Logged: 2026-06-26 EDT

Planned file changes (pre-fix):
- `harness/tools/run_scientific_lifecycle_smoke.py`
- `harness/tests/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py`
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: add scheduler lease evidence and boundary fields so local smoke-run
lease ownership is visible and not confused with distributed production leases.

### Scheduler Lease Boundary Result

| Check | Status | Evidence |
|---|---|---|
| Lease sidecar | ok | Lifecycle run/resume writes `autosci_scheduler_lease.v1` sidecar evidence. |
| Lease boundary | ok | Lifecycle summaries include `autosci_scheduler_lease_boundary.v1`. |
| Route limitation | ok | `/research` now names local lease boundary while keeping distributed lease/quota/runtime audit pending. |

### Scheduler Lease Boundary Verification

| Command | Result |
|---|---|
| `py_compile` runner/test | ok |
| route config `json.tool` | ok |
| blocked lifecycle + resume targeted tests | ok: 2 passed |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/tests/evaluators/scientific -q` | ok: 87 passed |
| `$research` scheduler shim subset | ok: 8 passed |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py -q` | ok: 105 passed with elevated local bind permission |
| `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step56.json` | warn: 28 routed, 0 missing, 0 full, 17 partial, 11 gated |
| `git diff --check` over Step 56 files | ok before log write |

## Phase 19 Publication Submission Checklist Boundary Sync

Logged: 2026-06-26 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: add publication submission checklist boundary so compile/PDF success is
not confused with submission/anonymity/page/font readiness.

### Publication Submission Checklist Boundary Result

| Check | Status | Evidence |
|---|---|---|
| Submission boundary | ok | Paper compile writes `autosci_publication_submission_boundary.v1` sidecar evidence. |
| Checklist/diagnostics | ok | Checklist embeds boundary and diagnostics render a Submission Boundary section. |
| Bundle artifact | ok | Publication bundle includes `publication_submission_boundary_json`. |
| Route limitation | ok | `/paper-compile` now separates compile/PDF evidence from submission readiness. |

### Publication Submission Checklist Boundary Verification

| Command | Result |
|---|---|
| `py_compile` bridge/tests | ok |
| route config `json.tool` | ok |
| submission checklist boundary targeted test | ok: 1 passed |
| paper-compile/paper-plan/paper-draft publication subset | ok: 10 passed |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py -q` | ok: 105 passed with elevated local bind permission |
| `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step57.json` | warn: 28 routed, 0 missing, 0 full, 17 partial, 11 gated |
| `git diff --check` over Step 57 files | ok before log write |

## Phase 19 Paper Compile Submission Evidence Flags Sync

Logged: 2026-06-26 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_skill_shim.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: expose paper-compile submission evidence flags for anonymous mode,
page-count/page-limit, and minimum font-size proof.

### Paper Compile Submission Evidence Flags Result

| Check | Status | Evidence |
|---|---|---|
| CLI flags | ok | `$paper-compile` now forwards anonymity, page, and font-size evidence flags into compile inputs. |
| Submission boundary | ok | Explicit evidence can make `autosci_publication_submission_boundary.v1` report `submission_ready`. |
| Route limitation | ok | `/paper-compile` now records that CLI flags satisfy readiness only with explicit proof. |

### Paper Compile Submission Evidence Flags Verification

| Command | Result |
|---|---|
| `py_compile` shim/tests | ok |
| route config JSON load | ok |
| submission incomplete + submission-ready targeted tests | ok: 2 passed |
| paper-compile/paper-plan/paper-draft publication subset | ok: 11 passed |
| full shim suite with elevated local bind permission | ok: 106 passed |
| default sandbox full shim suite | warn: local `127.0.0.1` bind was denied before elevated rerun |
| `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step58.json` | warn: 28 routed, 0 missing, 0 full, 17 partial, 11 gated |
| `git diff --check` over Step 58 files | ok before log write |

## Phase 19 Paper Compile Venue Submission Profile Boundary Sync

Logged: 2026-06-26 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/bin/autosci_skill_shim.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: add source-backed venue submission profile input so compile readiness
uses explicit venue requirements rather than loose CLI-only claims.

### Paper Compile Venue Submission Profile Boundary Result

| Check | Status | Evidence |
|---|---|---|
| Profile input | ok | `$paper-compile --submission-profile` forwards source-backed venue requirements into compile inputs. |
| Venue boundary | ok | Publication boundary now includes `venue_submission_ready`, `venue_status`, `venue_blocking_checks`, and embedded profile evidence. |
| Diagnostics/artifacts | ok | Diagnostics and bundle artifacts expose the loaded profile and SHA-256. |
| Route limitation | ok | `/paper-compile` now requires source-backed profile evidence for venue-specific readiness. |

### Paper Compile Venue Submission Profile Boundary Verification

| Command | Result |
|---|---|
| `py_compile` bridge/shim/tests | ok |
| route config JSON load | ok |
| missing evidence + CLI evidence + venue profile targeted tests | ok: 3 passed |
| paper-compile/paper-plan/paper-draft publication subset | ok: 12 passed |
| full shim suite with elevated local bind permission | ok: 107 passed |
| `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step59.json` | warn: 28 routed, 0 missing, 0 full, 17 partial, 11 gated |
| `git diff --check` over Step 59 files | ok before log write |

## Phase 19 Paper Compile PDF Inspection Evidence Ingestion Sync

Logged: 2026-06-26 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/bin/autosci_skill_shim.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: ingest explicit PDF inspection evidence for verified page count and
minimum font size instead of relying only on loose numeric CLI flags.

### Paper Compile PDF Inspection Evidence Ingestion Result

| Check | Status | Evidence |
|---|---|---|
| PDF inspection input | ok | `$paper-compile --pdf-inspection` forwards PDF inspection evidence to compile inputs. |
| PDF evidence boundary | ok | Bridge validates inspection sidecars against discovered PDFs by path or SHA-256. |
| Venue readiness | ok | `venue_submission_ready` now requires profile plus PDF inspection evidence. |
| Diagnostics/artifacts | ok | Diagnostics and bundle artifacts expose PDF inspection status and SHA-256. |
| Route limitation | ok | `/paper-compile` now distinguishes generic CLI checks from source-backed venue readiness. |

### Paper Compile PDF Inspection Evidence Ingestion Verification

| Command | Result |
|---|---|
| `py_compile` bridge/shim/tests | ok |
| route config JSON load | ok |
| missing evidence + CLI evidence + profile-only + profile/PDF-inspection targeted tests | ok: 4 passed |
| paper-compile/paper-plan/paper-draft publication subset | ok: 13 passed |
| full shim suite with elevated local bind permission | ok: 108 passed |
| `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step60.json` | warn: 28 routed, 0 missing, 0 full, 17 partial, 11 gated |
| `git diff --check` over Step 60 files | ok before log write |

## Phase 19 Publication Submission Audit Evidence Boundary Sync

Logged: 2026-06-26 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/bin/autosci_skill_shim.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: add explicit publication submission audit evidence so venue readiness
and final submission audit readiness are separate source-backed states.

### Publication Submission Audit Evidence Boundary Result

| Check | Status | Evidence |
|---|---|---|
| Submission audit input | ok | `$paper-compile --submission-audit` forwards explicit audit evidence into compile inputs. |
| Audit boundary | ok | Publication boundary now includes audit readiness, audit blocking checks, and portal completion as separate fields. |
| Portal truthfulness | ok | Portal completion is not implied by audit readiness. |
| Diagnostics/artifacts | ok | Diagnostics and bundle artifacts expose submission audit status and SHA-256. |
| Route limitation | ok | `/paper-compile` now names explicit submission audit evidence as required for audit readiness. |

### Publication Submission Audit Evidence Boundary Verification

| Command | Result |
|---|---|
| `py_compile` bridge/shim/tests | ok |
| route config JSON load | ok |
| paper-compile submission/profile/PDF/audit targeted tests | ok: 5 passed |
| paper-compile/paper-plan/paper-draft publication subset | ok: 14 passed |
| full shim suite with elevated local bind permission | ok: 109 passed |
| `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step61.json` | warn: 28 routed, 0 missing, 0 full, 17 partial, 11 gated |
| `git diff --check` over Step 61 files | ok before log write |

## Phase 19 Review LLM Final Acceptance Boundary Sync

Logged: 2026-06-26 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/bin/autosci_skill_shim.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: add explicit Review LLM final acceptance evidence so local surrogate
review is not confused with provider/command/evidence-backed final review.

### Review LLM Final Acceptance Boundary Result

| Check | Status | Evidence |
|---|---|---|
| Requirement flag | ok | `$review --require-review-llm` records that local surrogate review is insufficient for final acceptance. |
| Final boundary | ok | Review evidence includes `autosci_review_final_acceptance_boundary.v1`. |
| Local surrogate separation | ok | Local surrogate review now reports `review_llm_incomplete` rather than final acceptance. |
| Provider/evidence readiness | ok | Supplied Review LLM evidence, command bridge, and OpenAI-compatible provider mode can report `final_acceptance_ready`. |
| Route limitation | ok | `/review` now names the final acceptance boundary and local surrogate insufficiency. |

### Review LLM Final Acceptance Boundary Verification

| Command | Result |
|---|---|
| `py_compile` bridge/shim/tests | ok |
| route config JSON load | ok |
| local/evidence/command/provider review boundary targeted tests | ok: 4 passed |
| `-k review` subset | ok: 15 passed with elevated local bind permission |
| full shim suite with elevated local bind permission | ok: 109 passed |
| `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step62.json` | warn: 28 routed, 0 missing, 0 full, 17 partial, 11 gated |
| `git diff --check` over Step 62 files | ok before log write |

## Phase 19 Novelty Final Acceptance Boundary Sync

Logged: 2026-06-28 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: add explicit novelty final acceptance boundary requiring external
novelty evidence plus Review LLM proof, while keeping local/source-only checks
incomplete for final acceptance.

### Novelty Final Acceptance Boundary Result

| Check | Status | Evidence |
|---|---|---|
| Evaluation boundary | ok | Novelty evaluations embed `autosci_novelty_final_acceptance_boundary.v1`. |
| Boundary sidecar | ok | Evaluate-ideas writes `novelty_final_acceptance_boundary.json`. |
| Source/review requirements | ok | Final acceptance requires external novelty completion, provider provenance pass, Review LLM completion, and numeric novelty score. |
| Writeback linkage | ok | Novelty writeback records final acceptance status without changing existing writeback gating order. |
| Route limitation | ok | `/novelty` now names the final acceptance boundary and required evidence. |

### Novelty Final Acceptance Boundary Verification

| Command | Result |
|---|---|
| `py_compile` bridge/tests | ok |
| route config JSON load | ok |
| local/external-only/external+Review LLM/missing-review novelty targeted tests | ok: 4 passed |
| `-k novelty` subset | ok: 11 passed |
| full shim suite with elevated local bind permission | ok: 109 passed |
| `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step63.json` | warn: 28 routed, 0 missing, 0 full, 17 partial, 11 gated |
| `git diff --check` over Step 63 files | ok before log write |

## Phase 19 Ask Final Answer Boundary Sync

Logged: 2026-06-28 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: add explicit final answer boundary for `/ask` requiring retrieval/source
evidence plus model-backed synthesis, without treating retrieval-only local
summaries as final.

### Ask Final Answer Boundary Result

| Check | Status | Evidence |
|---|---|---|
| Final answer boundary | ok | `/ask` retrieval JSON embeds `autosci_ask_final_answer_boundary.v1`. |
| Boundary sidecar | ok | Ask runs write `ask_final_answer_boundary.json`. |
| Retrieval/model separation | ok | Retrieval-only answers report `ask_final_answer_incomplete`. |
| Model-backed readiness | ok | Retrieval plus completed model synthesis reports `final_answer_ready`. |
| Route limitation | ok | `/ask` now names the boundary and source/model requirements. |

### Ask Final Answer Boundary Verification

| Command | Result |
|---|---|
| `py_compile` bridge/tests | ok |
| route config JSON load | ok |
| retrieval-only and model-command ask targeted tests | ok: 2 passed |
| full shim suite with elevated local bind permission | ok: 109 passed |
| `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step64.json` | warn: 28 routed, 0 missing, 0 full, 17 partial, 11 gated |
| `git diff --check` over Step 64 files | ok before log write |

## Phase 19 Check Final Quality Boundary Sync

Logged: 2026-06-28 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: add explicit final quality boundary for `/check` requiring local wiki
checks plus model-backed recommendation evidence, without treating lint-only
output as final review.

### Check Final Quality Boundary Result

| Check | Status | Evidence |
|---|---|---|
| Final quality boundary | ok | `/check` embeds `autosci_check_final_quality_boundary.v1` in workflow evolution review metadata. |
| Boundary sidecar | ok | Check runs write `check_final_quality_boundary.json`. |
| Local/model separation | ok | Local structural checks alone remain incomplete for final quality. |
| Model-backed readiness | ok | Completed model evidence plus passing local checks can report `final_quality_ready`. |
| Route limitation | ok | `/check` now names the final quality boundary and local/model requirements. |

### Check Final Quality Boundary Verification

| Command | Result |
|---|---|
| `py_compile` bridge/tests | ok |
| route config JSON load | ok |
| retrieval/check local and model-command check targeted tests | ok: 2 passed |
| `-k 'ask or check'` subset | ok: 8 passed |
| full shim suite with elevated local bind permission | ok: 109 passed |
| `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step65.json` | warn: 28 routed, 0 missing, 0 full, 17 partial, 11 gated |
| `git diff --check` over Step 65 files | ok before log write |

## Phase 19 Discover Final Shortlist Boundary Sync

Logged: 2026-06-28 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: add explicit discovery final shortlist boundary requiring source-backed
provider evidence, without treating local fallback/fixture candidates as final
discovery.

### Discover Final Shortlist Boundary Result

| Check | Status | Evidence |
|---|---|---|
| Final shortlist boundary | ok | Discover source provider boundary embeds `autosci_discover_final_shortlist_boundary.v1`. |
| Boundary sidecar | ok | Discover writes `discover_final_shortlist_boundary.json`. |
| Local/provider separation | ok | Empty/local/generic runtime candidates remain incomplete for final shortlist readiness. |
| Provider-backed readiness | ok | Provider-backed candidates can report `final_shortlist_ready`. |
| Route limitation | ok | `/discover` now names the final shortlist boundary and provider-channel requirements. |

### Discover Final Shortlist Boundary Verification

| Command | Result |
|---|---|
| `py_compile` bridge/tests | ok |
| route config JSON load | ok |
| wiki/local, generic runtime, and provider-backed runtime discovery targeted tests | ok |
| `-k 'discover or source_runtime_evidence'` subset | ok: 4 passed |
| full shim suite with elevated local bind permission | ok: 109 passed |
| `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step66.json` | warn: 28 routed, 0 missing, 0 full, 17 partial, 11 gated |
| `git diff --check` over Step 66 files | ok before log write |

## Phase 19 Survey Final Coverage Boundary Sync

Logged: 2026-06-28 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: add explicit survey final coverage boundary requiring source-backed
citation coverage, without treating partial/local citation maps as exhaustive
survey evidence.

### Survey Final Coverage Boundary Result

| Check | Status | Evidence |
|---|---|---|
| Final coverage boundary | ok | `/survey` writes `autosci_survey_final_coverage_boundary.v1`. |
| Boundary sidecar | ok | Survey artifacts include `survey_final_coverage_boundary_json`. |
| Bounded/exhaustive separation | ok | Bounded source-backed coverage can pass while exhaustive coverage remains false without provider audit. |
| Scaffold separation | ok | Survey scaffolds without citations remain incomplete. |
| Route limitation | ok | `/survey` now names bounded coverage and keeps exhaustive live coverage pending. |

### Survey Final Coverage Boundary Verification

| Command | Result |
|---|---|
| `py_compile` bridge/tests | ok |
| route config JSON load | ok |
| survey scaffold and citation-map completion targeted tests | ok: 2 passed |
| `-k 'survey or paper_plan or paper_compile or paper_draft'` subset | ok: 19 passed |
| full shim suite with elevated local bind permission | ok: 109 passed |
| `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step67.json` | warn: 28 routed, 0 missing, 0 full, 17 partial, 11 gated |
| `git diff --check` over Step 67 files | ok before log write |

## Phase 19 Paper Draft Final Manuscript Boundary Sync

Logged: 2026-06-28 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: add explicit paper-draft final manuscript boundary requiring source
evidence, citation map, Review LLM proof, and compile/PDF handoff before
treating a draft as publication-ready.

### Paper Draft Final Manuscript Boundary Result

| Check | Status | Evidence |
|---|---|---|
| Final manuscript boundary | ok | `/paper-draft` writes `autosci_paper_draft_final_manuscript_boundary.v1`. |
| Boundary sidecar | ok | Draft artifacts include `paper_draft_final_manuscript_boundary_json`; publication bundle passthrough includes it. |
| Citation map sidecar | ok | Draft artifacts include `citation_map_json` from `paper_draft_citation_map.json`. |
| Publication-ready separation | ok | Plain LaTeX drafts stay incomplete for final manuscript readiness. |
| Final-ready path | ok | Source citation evidence, completed Review LLM proof, and verified compile/PDF handoff can satisfy `final_manuscript_ready`. |
| Route limitation | ok | `/paper-draft` now names final manuscript boundary requirements. |

### Paper Draft Final Manuscript Boundary Verification

| Command | Result |
|---|---|
| `py_compile` bridge/tests | ok |
| route config JSON load | ok |
| paper-draft incomplete and final-ready boundary targeted tests | ok: 2 passed |
| `-k 'survey or paper_plan or paper_compile or paper_draft'` subset | ok: 19 passed |
| full shim suite with elevated local bind permission | ok: 109 passed |
| `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step68.json` | warn: 28 routed, 0 missing, 0 full, 17 partial, 11 gated |
| `git diff --check` over Step 68 files | ok before log write |

## Phase 19 Paper Plan Final Acceptance Boundary Sync

Logged: 2026-06-28 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: add explicit paper-plan final acceptance boundary requiring source-backed
citation plan, Review LLM proof, and downstream compile/PDF handoff before
treating a plan as draft/compile-ready.

Scope amendment before fix:
- `harness/tools/run_scientific_lifecycle_smoke.py`

Reason: full shim verification showed scheduler `report_plan` did not receive
compile/PDF handoff inputs, so the new paper-plan final acceptance boundary
could not pass in the approved publication compile lifecycle. Propagate existing
approved compile evidence only; do not loosen the boundary.

### Paper Plan Final Acceptance Boundary Result

| Check | Status | Evidence |
|---|---|---|
| Final plan acceptance boundary | ok | `/paper-plan` writes `autosci_paper_plan_final_acceptance_boundary.v1`. |
| Boundary sidecar | ok | Plan artifacts include `paper_plan_final_acceptance_boundary_json`. |
| Draft/compile readiness separation | ok | Citation plus Review LLM without compile/PDF stays incomplete for final acceptance. |
| Final-ready path | ok | Source citation plan, Review LLM proof, and verified compile/PDF handoff can satisfy `final_plan_accepted`. |
| Scheduler handoff | ok | Scheduler `report_plan` receives approved compile contract fields; approved compile execution can generate plan-boundary runtime/PDF handoff. |
| Route limitation | ok | `/paper-plan` now names final acceptance boundary requirements. |

### Paper Plan Final Acceptance Boundary Verification

| Command | Result |
|---|---|
| `py_compile` bridge/scheduler/tests | ok |
| route config JSON load | ok |
| paper-plan final acceptance boundary targeted tests | ok: 3 passed |
| approved publication compile scheduler regression | ok: 1 passed |
| `-k 'survey or paper_plan or paper_compile or paper_draft or research_scheduler_executes_approved_publication_compile'` subset | ok: 20 passed |
| full shim suite with elevated local bind permission | ok: 109 passed |
| `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step69.json` | warn: 28 routed, 0 missing, 0 full, 17 partial, 11 gated |
| `git diff --check` over Step 69 files | ok before log write |

## Phase 19 Ideate Final Promotion Boundary Sync

Logged: 2026-06-28 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: add explicit `/ideate` final promotion boundary requiring wiki maturity
scan, failed-idea banlist check, source-backed evidence, model brainstorm
provenance, and novelty/review gate references before generated ideas are
promotable.

### Ideate Final Promotion Boundary Result

| Check | Status | Evidence |
|---|---|---|
| Final promotion boundary | ok | `/ideate` writes `autosci_ideate_final_promotion_boundary.v1`. |
| Per-idea boundary | ok | Generated ideas include `autosci_ideate_idea_promotion_boundary.v1` and `promotion_ready`. |
| Boundary sidecar | ok | Generate-ideas artifacts include `ideate_final_promotion_boundary_json`. |
| Source/model/gate separation | ok | Source-grounded and model-command ideas remain non-promotable until novelty/review gate references are supplied. |
| Missing-source separation | ok | Missing-source ideation remains inconclusive and boundary records missing source evidence. |
| Route limitation | ok | `/ideate` now names final promotion boundary requirements. |

### Ideate Final Promotion Boundary Verification

| Command | Result |
|---|---|
| `py_compile` bridge/tests | ok |
| route config JSON load | ok |
| ideate source/model/missing-source boundary targeted tests | ok: 3 passed |
| `-k 'ideate or novelty'` subset | ok: 14 passed |
| full shim suite with elevated local bind permission | ok: 109 passed |
| `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step70.json` | warn: 28 routed, 0 missing, 0 full, 17 partial, 11 gated |
| `git diff --check` over Step 70 files | ok before log write |

## Phase 19 Experiment Design Final Execution Boundary Sync

Logged: 2026-06-28 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: add explicit `/exp-design` final execution-readiness boundary requiring
resolved idea/evaluation evidence, completed Review LLM design validation, and
declared runtime/artifact handoff requirements before an experiment plan is
executable.

### Experiment Design Final Execution Boundary Result

| Check | Status | Evidence |
|---|---|---|
| Final execution boundary | ok | `/exp-design` writes `autosci_experiment_design_final_execution_boundary.v1`. |
| Boundary sidecar | ok | Experiment-plan artifacts include `experiment_design_final_execution_boundary_json`. |
| Plan embedding | ok | `source_context.final_execution_boundary` records target, Review LLM, approval preflight, command handoff, and artifact handoff state. |
| Review-only separation | ok | Review-only designs remain incomplete for execution readiness. |
| Execution-ready path | ok | Review LLM plus approval/allowlist/before preflight can satisfy `execution_ready`. |
| Network isolation | ok | Local novelty test disables network fetch so live S2 availability cannot alter local-source expectations. |
| Route limitation | ok | `/exp-design` now names final execution boundary requirements. |

### Experiment Design Final Execution Boundary Verification

| Command | Result |
|---|---|
| `py_compile` bridge/tests | ok |
| route config JSON load | ok |
| exp-design final execution boundary targeted tests | ok: 2 passed |
| failed full-suite cases after isolation fix | ok: 2 passed |
| `-k 'exp_design or exp_run or exp_status or exp_pilot or novelty'` subset | ok: 28 passed |
| full shim suite with elevated local bind permission | ok: 110 passed |
| `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step71.json` | warn: 28 routed, 0 missing, 0 full, 17 partial, 11 gated |
| `git diff --check` over Step 71 files | ok before log write |

## Phase 19 Experiment Evaluation Final Verdict Boundary Sync

Logged: 2026-06-28 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: add explicit `/exp-eval` final verdict boundary requiring experiment
result evidence, linked claim/code evidence, completed Review LLM proof, and
explicit writeback status before verdicts are treated as final.

### Experiment Evaluation Final Verdict Boundary Result

| Check | Status | Evidence |
|---|---|---|
| Final verdict boundary | ok | `/exp-eval` writes `autosci_experiment_evaluation_final_verdict_boundary.v1`. |
| Boundary sidecar | ok | Claim-verdict artifacts include `experiment_evaluation_final_verdict_boundary_json`. |
| Verdict embedding | ok | Verdict payloads include `final_verdict_boundary` and `final_verdict_ready`. |
| Non-final separation | ok | Evidence-backed verdicts without approved wiki writeback remain `final_verdict_incomplete`. |
| Final-ready path | ok | Experiment result, claim/code evidence, Review LLM proof, and completed approved writeback satisfy `final_verdict_ready`. |
| Route limitation | ok | `/exp-eval` now records approval-required writeback policy and final verdict boundary requirements. |

### Experiment Evaluation Final Verdict Boundary Verification

| Command | Result |
|---|---|
| `py_compile` bridge/tests | ok |
| route config JSON load | ok |
| exp-eval final verdict boundary targeted tests | ok: 2 passed |
| `-k 'exp_eval or exp_pilot_eval or exp_design or exp_run or exp_status or exp_pilot'` subset | ok: 19 passed |
| full shim suite with elevated local bind permission | ok: 110 passed |
| `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step72.json` | warn: 28 routed, 0 missing, 0 full, 17 partial, 11 gated |
| `git diff --check` over Step 72 files | ok before log write |

## Phase 19 Experiment Run Final Runtime Audit Boundary Sync

Logged: 2026-06-28 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: add explicit `/exp-run` final runtime audit boundary requiring approved
deploy/run evidence, monitor/collect evidence, collection ledger, and wiki state
mutation proof before a run is treated as fully executed/collected.

### Experiment Run Final Runtime Audit Boundary Result

| Check | Status | Evidence |
|---|---|---|
| Final runtime audit boundary | ok | `/exp-run` run/collect paths write `autosci_experiment_run_final_runtime_audit_boundary.v1`. |
| Boundary sidecar | ok | Run/status artifacts include `experiment_run_final_runtime_audit_boundary_json`. |
| Run-only separation | ok | Approved run plus wiki mutation is `stage_runtime_audit_ready`, not final lifecycle ready. |
| Local collect separation | ok | Local result-dir collection records ledger evidence but remains non-final without live provider/SSH proof. |
| Live collect final path | ok | Approved live/provider pull-results with ledger and wiki mutation satisfies `final_runtime_audit_ready`. |
| Route limitation | ok | `/exp-run` now names final runtime audit boundary requirements. |

### Experiment Run Final Runtime Audit Boundary Verification

| Command | Result |
|---|---|
| `py_compile` bridge/tests | ok |
| route config JSON load | ok |
| exp-run runtime/local collect/live collect boundary targeted tests | ok: 3 passed |
| `-k 'exp_eval or exp_pilot_eval or exp_design or exp_run or exp_status or exp_pilot or exp_collect'` subset | ok: 24 passed |
| full shim suite with elevated local bind permission | ok: 110 passed |
| `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step73.json` | warn: 28 routed, 0 missing, 0 full, 17 partial, 11 gated |
| `git diff --check` over Step 73 files | ok before log write |

## Phase 19 Pilot Experiment Final Acceptance Boundary Sync

Logged: 2026-06-28 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: add explicit `/exp-pilot-run` and `/exp-pilot-eval` final pilot
acceptance boundaries requiring approved pilot runtime evidence, collected pilot
result evidence, verdict linkage, and approved wiki writeback status before pilot
success/evaluation is treated as final.

### Pilot Experiment Final Acceptance Boundary Result

| Check | Status | Evidence |
|---|---|---|
| Pilot run boundary | ok | `/exp-pilot-run` writes `autosci_pilot_experiment_final_acceptance_boundary.v1` with `stage=pilot_run`. |
| Pilot eval boundary | ok | `/exp-pilot-eval` writes `autosci_pilot_experiment_final_acceptance_boundary.v1` with `stage=pilot_eval`. |
| Runtime/final separation | ok | Pilot runtime readiness is separate from final pilot acceptance. |
| Final-ready path | ok | Runtime-linked verdict plus approved wiki writeback satisfies `final_pilot_acceptance_ready`. |
| Route limitation | ok | Pilot run/eval limitations now name final acceptance boundary requirements. |

### Pilot Experiment Final Acceptance Boundary Verification

| Command | Result |
|---|---|
| `py_compile` bridge/tests | ok |
| route config JSON load | ok |
| pilot runtime/eval/writeback boundary targeted tests | ok: 3 passed |
| `-k 'exp_pilot or pilot_eval or pilot_run or exp_eval or exp_run or exp_status or exp_design'` subset | ok: 21 passed |
| full shim suite with elevated local bind permission | ok: 110 passed |
| `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step74.json` | warn: 28 routed, 0 missing, 0 full, 17 partial, 11 gated |
| `git diff --check` over Step 74 files | ok before log write |

## Phase 19 Daily Arxiv Final Provider Delivery Boundary Sync

Logged: 2026-06-28 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: add explicit `/daily-arxiv` final provider/delivery boundary requiring
approved live provider runtime, source-channel candidate evidence,
ranking/finalize evidence, and explicit delivery or ingest status before a daily
digest is treated as final.

### Daily Arxiv Final Provider Delivery Boundary Result

| Check | Status | Evidence |
|---|---|---|
| Final provider/delivery boundary | ok | `/daily-arxiv` writes `autosci_daily_arxiv_final_provider_delivery_boundary.v1`. |
| Boundary sidecar | ok | Daily artifacts include `daily_arxiv_final_provider_delivery_boundary_json`. |
| Runtime/final separation | ok | Runtime provider/ranking evidence is stage-ready but non-final without delivery/ingest. |
| Final-ready path | ok | Approved wiki fan-in/ingest after provider candidates satisfies `daily_final_delivery_ready`. |
| Route limitation | ok | `/daily-arxiv` now names provider, ranking, delivery/ingest boundary requirements. |

### Daily Arxiv Final Provider Delivery Boundary Verification

| Command | Result |
|---|---|
| `py_compile` bridge/tests | ok |
| route config JSON load | ok |
| daily runtime digest and auto-ingest boundary targeted tests | ok: 2 passed |
| `-k 'daily_arxiv or discover or init_sources or source_fan_in or ingest'` subset | ok: 10 passed |
| full shim suite with elevated local bind permission | ok: 110 passed |
| `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step75.json` | warn: 28 routed, 0 missing, 0 full, 17 partial, 11 gated |
| `git diff --check` over Step 75 files | ok before log write |

## Phase 19 Init Sources Final Fan-In Boundary Sync

Logged: 2026-06-28 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: add explicit `/init` source initialization final fan-in boundary
requiring approved provider runtime, provider-backed candidates, approved wiki
fan-in, graph/log/index rebuild evidence, and visible incomplete status when any
piece is missing.

### Init Sources Final Fan-In Boundary Result

| Check | Status | Evidence |
|---|---|---|
| Init final fan-in boundary | ok | `/init` writes `autosci_init_sources_final_fan_in_boundary.v1`. |
| Boundary sidecar | ok | Init artifacts include `init_sources_final_fan_in_boundary_json`. |
| Runtime/final separation | ok | Provider runtime source evidence is provider-ready but non-final without approved fan-in. |
| Final-ready path | ok | Approved wiki fan-in plus log/edge/index/context rebuild satisfies `init_sources_final_fan_in_ready`. |
| Route limitation | ok | `/init` now names final fan-in boundary requirements and approval-required side effects. |

### Init Sources Final Fan-In Boundary Verification

| Command | Result |
|---|---|
| `py_compile` bridge/tests | ok |
| route config JSON load | ok |
| init diagnostics/runtime-only/approved fan-in targeted tests | ok: 3 passed |
| `-k 'init or daily_arxiv or discover or source_fan_in or ingest'` subset | ok: 13 passed |
| full shim suite with elevated local bind permission | ok: 110 passed |
| `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step76.json` | warn: 28 routed, 0 missing, 0 full, 17 partial, 11 gated |
| `git diff --check` over Step 76 files | ok before log write |

## Phase 19 Ingest Final Source Registration Boundary Sync

Logged: 2026-06-28 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: add explicit `/ingest` final source registration boundary requiring
verified source preparation, parsed paper metadata/text, raw artifact provenance,
wiki paper registration/log/graph evidence, and downstream discovery handoff
before an ingest is treated as final.

Plan refinement: include `autosci_skill_shim.py` so `/ingest --wiki-root`
propagates into bridge inputs and the boundary checks the intended wiki root.

### Ingest Final Source Registration Boundary Result

| Check | Status | Evidence |
|---|---|---|
| Final source registration boundary | ok | `/ingest` writes `autosci_ingest_final_source_registration_boundary.v1`. |
| Boundary sidecar | ok | Ingest artifacts include final boundary plus phase9 memory/graph sidecars. |
| Custom wiki root | ok | `/ingest --wiki-root` propagates into bridge inputs. |
| Runtime/final separation | ok | Parsed source without wiki paper/log/graph/index/context registration remains non-final. |
| Final-ready path | ok | Pre-registered wiki evidence satisfies `ingest_source_registration_ready`. |
| Targeted/subset tests | ok | Targeted ingest tests: 2 passed; source/ingest subset: 14 passed. |
| Full suite | warn | Full shim suite: 105 passed, 6 failed because scheduler AutoSci worker entries are missing from `physical-operators.json`. |

## Phase 19 Scheduler AutoSci Worker Registry Restore Sync

Logged: 2026-06-28 EDT

Planned file changes (pre-fix):
- `harness/config/physical-operators.json`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: restore bounded AutoSci worker entries required by scheduler lifecycle
smoke so `$research --scheduler-run` can dispatch configured AutoSci bridge
actions through `operator_runtime`.

### Scheduler AutoSci Worker Registry Restore Result

| Check | Status | Evidence |
|---|---|---|
| Physical workers | ok | `physical-operators.json` now has scheduler-referenced `autosci-*` bounded command workers. |
| Scheduler regression group | ok | `$research --scheduler-run` group: 6 passed. |
| Full shim suite | ok | Full AutoSci shim suite: 111 passed. |
| Static binding audit | warn | Next blocker is missing Scientific* logical operators/bindings in `logical-operators.json`. |

## Phase 19 Scientific Logical Operator Binding Restore Sync

Logged: 2026-06-28 EDT

Planned file changes (pre-fix):
- `harness/config/logical-operators.json`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: restore Scientific* logical operators and bindings to the bounded
AutoSci workers so static runtime binding audit can validate workflow
node-to-operator-to-bridge coverage.

### Scientific Logical Operator Binding Restore Result

| Check | Status | Evidence |
|---|---|---|
| Logical operators/bindings | ok | Scientific* definitions and bounded worker bindings restored. |
| Static runtime binding audit | ok | 28 workflow nodes across 2 workflows, 0 issues. |
| Scheduler/full shim regression | ok | Scheduler group: 6 passed; full shim suite: 111 passed. |
| Inventory | warn | Route inventory remains 17 partial and 11 gated. |

## Phase 19 Two-Axis Parity Status Model Sync

Logged: 2026-06-28 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_parity_bridge.py`
- `harness/evaluators/scientific/autosci_feature_parity_gate.py`
- `harness/plugins/autosci/tests/test_phase19_parity_bridge.py`
- `harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: add authoritative two-axis parity/proof fields to generated inventory
and gate validation without upgrading any route to semantic full absent E3/E4
evidence.

### Two-Axis Parity Status Model Result

| Check | Status | Evidence |
|---|---|---|
| Inventory fields | ok | Parity inventory route items now expose `semantic_parity`, `execution_policy`, `proof_level`, `proof_refs`, and `remaining_requirements`. |
| Gate enforcement | ok | `autosci_feature_parity_gate.py` validates semantic/execution/proof values and rejects semantic-full claims without enough proof. |
| Truthfulness guard | ok | No route was promoted to semantic full; Step 80 inventory remains semantic partial for all 28 routes. |
| Tests | ok | Parity bridge/gate targeted tests: 10 passed; full AutoSci plugin suite: 161 passed. |
| Inventory | warn | `/tmp/autosci-parity-step80.json`: route coverage 0 full / 17 partial / 11 gated; semantic 0 full / 28 partial / 0 missing. |

## Phase 19 Skill Run Terminal Status Truthfulness Gate Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/evaluators/scientific/autosci_skill_run_gate.py`
- `harness/tests/evaluators/scientific/test_autosci_skill_run_gate.py`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: make the skill-run gate reject evidence that claims top-level
`status: completed` while `outputs.skill_run.execution_status` is `partial` or
`gated`.

Non-goal: do not change route execution, side-effect policy, schema enums, or
the shim's existing `inconclusive` status for partial/gated runs.

### Skill Run Terminal Status Truthfulness Gate Result

| Check | Status | Evidence |
|---|---|---|
| Gate guard | ok | `autosci_skill_run_gate.py` rejects top-level `completed` for `partial`/`gated` execution status. |
| Tests | ok | New skill-run gate tests: 3 passed; gated/partial shim subsets and operator smoke gate remain green. |
| Full plugin suite | ok | Elevated local-bind AutoSci plugin suite: 161 passed. |
| Inventory | warn | Step 81 parity inventory remains 17 partial and 11 gated; semantic inventory remains 28 partial. |
| Broad evaluator suite | warn | Scientific evaluator suite exposed next blocker: full lifecycle external/resume tails drift from the 20-node workflow config. |

## Phase 19 Scheduler Full Lifecycle Tail Alignment Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/tools/run_scientific_lifecycle_smoke.py`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: make full external/resume lifecycle smoke paths dispatch the configured
publication/finalization tail and treat an explicitly supplied compile-target
PDF as handoff evidence without claiming approved executor runtime.

Non-goal: do not make bounded smoke dispatch production-ready, execute
unapproved TeX/remote effects, or relax lifecycle runtime gate requirements.

### Scheduler Tail Alignment Adjustment Plan

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/tools/run_scientific_lifecycle_smoke.py`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: keep the Step 82 boundary and wire supplied compile-target evidence
into paper-plan handoff readiness so configured tail dispatch can proceed only
after verified handoff.

Non-goal: do not change test expectations, production readiness claims, TeX
execution policy, or unrelated scheduler nodes.

### Scheduler Resume Blocker Adjustment Plan

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/tools/run_scientific_lifecycle_smoke.py`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: preserve all unresolved external unblock points during resume when
earlier external evidence is missing, without dispatching downstream configured
tail nodes.

Non-goal: do not change human-gate behavior, node execution order, or
publication/finalization dispatch semantics.

### Scheduler Full Lifecycle Tail Alignment Result

| Check | Status | Evidence |
|---|---|---|
| Supplied compile handoff | ok | `plan_report` now treats `supplied_compile_target_evidence` as a compile handoff request and verifies existing PDF targets without claiming TeX execution. |
| Full external tail | ok | Full external lifecycle dispatch reaches all configured tail nodes when Review LLM and compile-target evidence are supplied. |
| Resume tail | ok | Resume dispatch reaches configured tail nodes after supplied external evidence and preserves no-rerun fingerprints. |
| Resume blocked externals | ok | Human-gate resume with no external evidence records both `report_plan` and `publication_produce` blockers. |
| Focused lifecycle tests | ok | 3 targeted lifecycle regressions passed. |
| Broad evaluator suite | ok | Scientific evaluator suite: 91 passed. |
| Full plugin suite | ok | AutoSci plugin suite with elevated local bind permission: 161 passed. |
| Inventory/gate | warn | Step 82 inventory still reports 17 partial and 11 gated route statuses; semantic parity remains 28 partial. |

## Phase 19 External Runtime Proof Registry Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_parity_bridge.py`
- `harness/evaluators/scientific/autosci_feature_parity_gate.py`
- `harness/plugins/autosci/tests/test_phase19_parity_bridge.py`
- `harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: add explicit external runtime proof references and required proof
categories to parity inventory/gate output so remaining non-full routes are
auditable.

Non-goal: do not mark any route full, fabricate provider/runtime evidence, or
execute external side effects.

### External Runtime Proof Registry Result

| Check | Status | Evidence |
|---|---|---|
| Inventory fields | ok | Route items now include `runtime_proof_status`, `runtime_proof_refs`, and `proof_requirements`. |
| Gate enforcement | ok | Gate validates requirement shape/status, runtime proof status/counts, and approval/provider proof-category presence. |
| Tests | ok | Parity bridge tests: 4 passed; feature parity gate tests: 8 passed; scientific evaluator suite: 93 passed. |
| Full plugin suite | ok | AutoSci plugin suite with elevated local bind permission: 161 passed. |
| Inventory | warn | Step 83 inventory reports 25 pending runtime proof slots and 0 supplied/verified runtime proofs. |

## Phase 19 Runtime Proof Manifest Ingestion Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_parity_bridge.py`
- `harness/evaluators/scientific/autosci_feature_parity_gate.py`
- `harness/plugins/autosci/tests/test_phase19_parity_bridge.py`
- `harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: allow parity inventory to ingest explicit runtime proof manifests and
mark matching route proof slots as supplied without promoting route/semantic
full status.

Non-goal: do not trust arbitrary manifests as verified runtime, mark routes
full, execute providers, or execute side effects.

### Runtime Proof Manifest Strictness Adjustment Plan

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/evaluators/scientific/autosci_feature_parity_gate.py`
- `harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: require supplied runtime proof source categories to match declared proof
requirements and actually satisfy at least one requirement.

Non-goal: do not change manifest ingestion semantics, route statuses, or proof
verification level.

### Runtime Proof Manifest Ingestion Result

| Check | Status | Evidence |
|---|---|---|
| CLI ingestion | ok | `inventory` and `route` accept repeated `--runtime-proof-manifest` paths. |
| Proof attachment | ok | Manifest proofs attach to matching native skills as `runtime_proof_sources` and supplied proof requirements. |
| Gate strictness | ok | Gate rejects skill mismatch, unknown categories, supplied-without-supplied-requirement, and count drift. |
| Tests | ok | Targeted bridge/gate group: 15 passed; scientific evaluator suite: 95 passed. |
| Full plugin suite | ok | AutoSci plugin suite with elevated local bind permission: 162 passed. |
| Inventory | warn | No-manifest Step 84 inventory still has 25 pending runtime proof slots and no supplied/verified proof. |

## Phase 19 Runtime Proof Evidence Ref Audit Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_parity_bridge.py`
- `harness/evaluators/scientific/autosci_feature_parity_gate.py`
- `harness/plugins/autosci/tests/test_phase19_parity_bridge.py`
- `harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: audit runtime proof evidence refs so path-like local refs must resolve
and missing local refs cannot satisfy supplied proof requirements.

Non-goal: do not verify external provider ids as live, promote supplied proof
to verified, or execute external side effects.

### Runtime Proof Evidence Ref Audit Result

| Check | Status | Evidence |
|---|---|---|
| Ref audit | ok | Manifest proof sources now include `evidence_ref_statuses`; local path refs must resolve. |
| Blocked proof handling | ok | Missing local proof refs produce blocked proof sources and do not satisfy supplied requirements. |
| Gate enforcement | ok | Gate rejects blocked sources and unresolved local refs. |
| Tests | ok | Phase19 bridge tests: 6 passed; feature parity gate tests: 10 passed; scientific evaluator suite: 95 passed. |
| Full plugin suite | ok | AutoSci plugin suite with elevated local bind permission: 163 passed. |
| Inventory | warn | Step 85 inventory remains non-full and has no verified live runtime proof. |

## Phase 19 Runtime Proof CLI Summary Visibility Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_parity_bridge.py`
- `harness/plugins/autosci/tests/test_phase19_parity_bridge.py`
- `docs/integrations/autosci/native-lifecycle-continuation-log.md`
- `docs/integrations/autosci/phase15-progress-log.md`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: include runtime proof status counts in parity bridge CLI summaries so
pending/supplied/verified proof state is visible without opening the JSON
artifact.

Non-goal: do not change inventory payload semantics, gate rules, route status,
or proof verification.

### Runtime Proof CLI Summary Visibility Result

| Check | Status | Evidence |
|---|---|---|
| CLI summary | ok | Inventory/route stdout summaries now include `runtime_proof_status_counts`. |
| Tests | ok | Phase19 bridge tests: 6 passed. |
| Inventory/gate | ok | Step 86 inventory gates successfully and stdout reports 25 pending / 3 not_required / 0 supplied / 0 verified runtime proof states. |
| Full parity claim | warn | Remaining work requires real runtime proof manifests or approved live provider execution. |

## Phase 19 Setup Env Example ABI Restore Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/config/.env.example`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: restore the non-secret setup provider template required by the `/setup`
primary tool ABI gate.

Non-goal: do not write real secrets, enable providers, change route status, or
promote setup/full parity.

### Setup Env Example ABI Restore Result

| Check | Status | Evidence |
|---|---|---|
| Template restored | ok | `harness/plugins/autosci/config/.env.example` exists and contains only empty provider variables / offline switch. |
| Setup tool ABI | ok | `/setup` primary tool statuses now resolve both `config/setup-guide.md` and `.env.example`. |
| Feature parity gate | ok | `autosci_feature_parity_gate.py /tmp/autosci-parity-after-env-example.json` passed with only non-full parity warnings. |
| Targeted tests | ok | Phase19 parity bridge + feature gate group: 16 passed. |
| Full parity claim | warn | Route inventory remains 0 full / 17 partial / 11 gated; runtime proof remains 25 pending / 0 supplied / 0 verified. |

## Phase 19 Capability Registry Drift Restore Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/config/capability-capsules.registry.yaml`
- `harness/capability-capsules/cap.research-artifact-review.yaml`
- `harness/tests/config/test_autosci_research_capsule_registry.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: register all AutoSci manifest research capsules, restore the missing
artifact-review capsule file, and add a regression test for manifest/registry
drift.

Non-goal: do not promote route parity status, alter scoring/routing logic, run
side effects, or claim live provider proof.

### Capability Registry Drift Restore Result

| Check | Status | Evidence |
|---|---|---|
| Manifest/registry drift | ok | AutoSci manifest 19 research capsules are all registered; missing registry/files/unregistered counts are zero. |
| Missing capsule file | ok | Restored `cap.research-artifact-review.yaml` with artifact review evidence contract and no side-effect execution semantics. |
| Registry loader | ok | `iter_registry_entries()` resolves 19 stable `cap.research-*` entries and `cap.research-artifact-review`. |
| Regression tests | ok | `harness/tests/config/test_autosci_research_capsule_registry.py`: 2 passed; capability capsule group: 10 passed. |
| Parity inventory/gate | ok | Inventory gate passes after registry restore; inventory remains 0 full / 17 partial / 11 gated with 25 pending runtime proof slots. |
| Full parity claim | warn | Registry ABI drift is fixed, but runtime proof/live provider/approved side-effect evidence remains pending. |

## Phase 19 Generic Scientific Workflow Runner Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/tools/run_scientific_node_smoke.py`
- `harness/tools/run_scientific_workflow.py`
- `harness/tests/evaluators/scientific/test_scientific_workflow_runner.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: add a config-driven scientific workflow runner that reuses the existing
single-node operator runtime path and records an auditable generic workflow
dispatch boundary.

Non-goal: do not change lifecycle gate rules, mark provider/runtime proof as
verified, bypass side-effect approvals, or remove the bounded smoke runner.

### Generic Scientific Workflow Runner Result

| Check | Status | Evidence |
|---|---|---|
| Runner added | ok | `harness/tools/run_scientific_workflow.py` reads workflow config nodes and dispatches each through `operator_runtime` -> AutoSci bridge node runtime. |
| Node runtime metadata | ok | `run_scientific_node_smoke.py` now accepts `runtime_mode` / `runner_contract` without changing bounded smoke defaults. |
| Generic runner contract test | ok | `test_scientific_workflow_runner.py`: 1 passed with no fixture/smoke input markers and `runner_contract=generic_workflow_runner`. |
| Smoke compatibility | ok | Node/lifecycle smoke + lifecycle gate group: 27 passed; old bounded smoke guardrails still reject production dispatch when appropriate. |
| Syntax check | ok | `py_compile` passed for `run_scientific_workflow.py` and `run_scientific_node_smoke.py`. |
| Parity inventory/gate | ok | Inventory gate passes after runner addition; counts remain 0 full / 17 partial / 11 gated and runtime proof remains 25 pending / 0 supplied / 0 verified. |
| Full parity claim | warn | Generic workflow dispatch exists, but live provider evidence, approved side-effect execution proof, and route semantic-full promotion remain pending. |

## Phase 19 Research Scheduler Generic Default Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_skill_shim.py`
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: route explicit `$research --scheduler-run` through the generic
scientific workflow runner by default while keeping the old bounded smoke
runner available via an explicit legacy flag.

Non-goal: do not auto-complete ordinary `$research` stage evidence, remove the
legacy smoke runner, bypass external evidence/approval requirements, or
promote the route to full parity.

### Research Scheduler Generic Default Result

| Check | Status | Evidence |
|---|---|---|
| Default scheduler runner | ok | Explicit `$research --scheduler-run` now calls `run_scientific_workflow.py` unless `--scheduler-legacy-smoke-runner` is supplied. |
| Legacy compatibility | ok | Existing bounded lifecycle smoke path remains available via `--scheduler-legacy-smoke-runner`. |
| Route ABI | ok | `/research` primary tools now include `run_scientific_workflow.py` plus the legacy smoke runner. |
| Generic default test | ok | `$research --scheduler-run --paper <non-fixture>` records `runner_contract=generic_workflow_runner`, 1 dispatched node, and no fixture/smoke input markers. |
| Regression tests | ok | Scheduler shim subset: 8 passed; root/shim ABI subset: 10 passed; workflow runner test: 1 passed. |
| Parity inventory/gate | ok | Inventory gate passes and remains honest at 0 full / 17 partial / 11 gated with 25 pending runtime proof slots. |
| Full parity claim | warn | Generic default dispatch is fixed for explicit scheduler-run, but complete lifecycle node selection, live/provider evidence, and approved side-effect runtime proof remain pending. |

## Phase 19 Wiki State Resolver Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `tools/research_wiki.py`
- `harness/plugins/autosci/tests/test_research_wiki_tool.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: add an explicit wiki state resolver command for slug/page status,
frontmatter, novelty score, graph edges, linked experiments, and log snippets.

Non-goal: do not mutate wiki state, infer missing status from heuristics, or
promote any route to full parity.

### Wiki State Resolver Result

| Check | Status | Evidence |
|---|---|---|
| Resolver ABI | ok | Added `tools/research_wiki.py resolve <entity>` to resolve page path, group, title, frontmatter, status, and novelty score. |
| Graph state | ok | Resolver returns linked graph edges, edge evidence ids, edge errors, and linked experiment pages. |
| Run log state | ok | Resolver returns bounded matching `wiki/log.md` snippets without mutating wiki files. |
| Tests | ok | `test_research_wiki_tool.py`: 1 passed; root ABI wiki subset: 2 passed; `py_compile` passed. |
| Parity inventory/gate | ok | Inventory gate passes and remains 0 full / 17 partial / 11 gated with 25 pending runtime proof slots. |
| Full parity claim | warn | Read-only wiki state resolution is present, but route-level full parity still requires live/provider/runtime evidence and final lifecycle audits. |

## Phase 19 Wiki Resolver Route ABI Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: expose the read-only wiki resolver in route inventory primary tools for
wiki-grounded commands that depend on concrete state resolution.

Non-goal: do not change route status, execution policy, scoring, or mutation
behavior.

### Wiki Resolver Route ABI Result

| Check | Status | Evidence |
|---|---|---|
| Route exposure | ok | `/ask`, `/check`, `/edit`, and `/ideate` primary tools now include `tools/research_wiki.py resolve`. |
| Root ABI test | ok | `test_feature_parity_routes_reference_existing_root_tools`: 1 passed. |
| Route JSON audit | ok | Parsed `feature_parity_routes.v1.json` and confirmed resolver tool references for wiki-grounded routes. |
| Parity inventory/gate | ok | Inventory and feature gate pass; counts remain 0 full / 17 partial / 11 gated with 25 pending runtime proof slots. |
| Full parity claim | warn | Resolver ABI is exposed, but provider/live runtime proof and semantic-full route audits remain pending. |

## Phase 19 Runtime Proof Provenance Gate Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_parity_bridge.py`
- `harness/evaluators/scientific/autosci_feature_parity_gate.py`
- `harness/plugins/autosci/tests/test_phase19_parity_bridge.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: require runtime proof manifests to carry auditable provenance,
production readiness, and collection mode before any proof can count as
supplied parity evidence.

Non-goal: do not promote any route to full parity or treat smoke/generic runner
artifacts as production runtime proof.

### Runtime Proof Provenance Gate Result

| Check | Status | Evidence |
|---|---|---|
| Bridge normalization | ok | Runtime proof manifests now normalize `collection_mode`, `production_ready`, `provenance`, and `block_reasons`. |
| Supplied proof guard | ok | Proof status is `supplied` only when evidence refs exist, local refs resolve, `production_ready=true`, collection mode is allowed, and provenance is complete. |
| Gate validation | ok | Feature parity gate now requires collection mode, boolean production readiness, provenance source/captured_at/artifact_kind, and coherent block reasons. |
| Regression tests | ok | `test_phase19_parity_bridge.py`: 7 passed; feature parity gate tests: 10 passed; `py_compile` passed. |
| Inventory/gate | ok | Real route inventory gate passes after contract tightening; counts remain 0 full / 17 partial / 11 gated with 25 pending runtime proof slots. |
| Full parity claim | warn | Runtime proof contract is stricter, but no route is promoted; live/provider/approval evidence still needs to be collected and attached. |

## Phase 19 Provider Source Runtime Proof Writer Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `tools/autosci_runtime_proof.py`
- `tools/fetch_s2.py`
- `tools/fetch_deepxiv.py`
- `tools/fetch_paper_copilot.py`
- `harness/plugins/autosci/tests/test_source_cli_tools.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: let completed provider fetch helpers persist source evidence and emit
parity-ingestable runtime proof manifests with the new production provenance
contract.

Non-goal: do not synthesize source results, bypass network-disabled states, or
claim external runtime/semantic full parity from provider-source evidence alone.

### Provider Source Runtime Proof Writer Result

| Check | Status | Evidence |
|---|---|---|
| Shared writer | ok | Added `tools/autosci_runtime_proof.py` to write evidence JSON and `autosci_runtime_proof_manifest.v1` with provenance/collection mode/production readiness. |
| S2 source CLI | ok | `tools/fetch_s2.py` supports optional evidence/proof outputs and does not write supplied proof for inconclusive network-disabled runs. |
| DeepXiv source CLI | ok | `tools/fetch_deepxiv.py` supports optional evidence/proof outputs while preserving explicit unavailable/inconclusive provider states. |
| Paper Copilot source CLI | ok | `tools/fetch_paper_copilot.py` writes provider-source proof for completed provider fetches, including `file://` native replay tests. |
| Regression tests | ok | `test_source_cli_tools.py`: 6 passed; `py_compile` passed for the shared writer and all three fetch CLIs. |
| Cross-tool proof ingest | ok | Generated Paper Copilot `discover` proof was accepted by `autosci_parity_bridge.py route` and `autosci_feature_parity_gate.py`; semantic parity stayed partial. |
| Full parity claim | warn | Provider-source evidence can now be collected and attached, but external runtime, review/model, side-effect, wiki mutation, and semantic equivalence proof remain pending. |

## Phase 19 Review/Model Runtime Proof Writer Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `tools/review_model_runtime_proof.py`
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `harness/plugins/autosci/tests/test_review_model_runtime_proof.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: convert completed Review LLM/model evidence into
parity-ingestable runtime proof manifests for
`review_llm_or_model_evidence`.

Non-goal: do not call a model, synthesize Review LLM output, or promote any
route to full parity without external/runtime/semantic proof.

### Review/Model Runtime Proof Writer Result

| Check | Status | Evidence |
|---|---|---|
| Proof writer | ok | Added `tools/review_model_runtime_proof.py from-evidence` for completed `artifact_review.v1` and `autosci_model_response.v1`. |
| Surrogate guard | ok | Local surrogate review evidence is rejected as inconclusive and does not write a runtime proof manifest. |
| Route ABI exposure | ok | Model/Review-dependent routes now list the proof writer in `primary_tools` without changing route status or execution policy. |
| Regression tests | ok | `test_review_model_runtime_proof.py`: 4 passed; `test_root_tool_abi.py::test_feature_parity_routes_reference_existing_root_tools`: 1 passed; `py_compile` passed. |
| Inventory/gate | ok | Real route inventory and feature parity gate pass; counts remain 0 full / 17 partial / 11 gated with 25 pending runtime proof slots. |
| Full parity claim | warn | Review/model evidence can now be packaged for parity proof, but routes still need actual completed Review LLM/model artifacts plus remaining runtime/source/side-effect/wiki/semantic proof. |

## Phase 19 Approval Runtime Proof Writer Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `tools/approval_runtime_proof.py`
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `harness/plugins/autosci/tests/test_approval_runtime_proof.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: convert verified `autosci_approval_contract.v1` sidecars into
parity-ingestable approval/side-effect runtime proof manifests.

Non-goal: do not execute side effects, approve commands, mutate wiki state, or
mark unverified approval contracts as supplied proof.

### Approval Runtime Proof Writer Result

| Check | Status | Evidence |
|---|---|---|
| Proof writer | ok | Added `tools/approval_runtime_proof.py from-contract` for verified `autosci_approval_contract.v1` sidecars. |
| Verification guard | ok | Tool requires approval ref plus existing allowlist/runtime/before/after artifacts and `execution_verified=true`; incomplete contracts remain inconclusive and write no proof. |
| Route ABI exposure | ok | Approval-gated routes now list the proof writer in `primary_tools` without changing coverage status, side-effect policy, or execution policy. |
| Regression tests | ok | `test_approval_runtime_proof.py`: 3 passed; root tool ABI: 1 passed; source/review/approval proof writer group: 13 passed; `py_compile` passed. |
| Inventory/gate | ok | Real route inventory and feature parity gate pass; counts remain 0 full / 17 partial / 11 gated with 25 pending runtime proof slots. |
| Full parity claim | warn | Approval/side-effect proof can now be packaged, but actual verified approval contracts must still be produced per route and semantic/runtime/source/wiki proof remains pending. |

## Phase 19 Wiki Mutation Runtime Proof Writer Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `tools/wiki_mutation_runtime_proof.py`
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `harness/plugins/autosci/tests/test_wiki_mutation_runtime_proof.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: convert completed wiki writeback sidecars into parity-ingestable
`wiki_mutation_evidence` runtime proof manifests.

Non-goal: do not mutate wiki state, infer success from missing artifacts, or
count incomplete/proposed writebacks as supplied proof.

### Wiki Mutation Runtime Proof Writer Result

| Check | Status | Evidence |
|---|---|---|
| Proof writer | ok | Added `tools/wiki_mutation_runtime_proof.py from-writeback` for completed wiki writeback sidecars. |
| Completion guard | ok | Tool requires recognized writeback schema, `status=completed`, `outputs.write.applied=true`, and existing wiki mutation artifacts. |
| Route ABI exposure | ok | Wiki-mutating routes now list the proof writer in `primary_tools` without changing route state or mutation behavior. |
| Regression tests | ok | `test_wiki_mutation_runtime_proof.py`: 3 passed; root tool ABI: 1 passed; source/review/approval/wiki proof writer group: 16 passed; `py_compile` passed. |
| Inventory/gate | ok | Real route inventory and feature parity gate pass; counts remain 0 full / 17 partial / 11 gated with 25 pending runtime proof slots. |
| Full parity claim | warn | Wiki mutation proof can now be packaged, but actual completed writeback sidecars still need to be produced and attached per route, and semantic/external runtime proof remains pending. |

## Phase 19 Semantic Parity Audit Proof Writer Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `tools/semantic_parity_runtime_proof.py`
- `harness/plugins/autosci/tests/test_semantic_parity_runtime_proof.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: convert completed semantic parity audit reports into
parity-ingestable `semantic_equivalence_evidence` runtime proof manifests.

Non-goal: do not infer semantic equivalence automatically, change route
coverage status, or promote any route to full parity without supplied audit
evidence.

### Semantic Parity Audit Proof Writer Result

| Check | Status | Evidence |
|---|---|---|
| Proof writer | ok | Added `tools/semantic_parity_runtime_proof.py from-audit` for completed semantic parity audits. |
| Audit guard | ok | Tool requires `autosci_semantic_parity_audit.v1`, `status=completed`, `semantic_parity=full`, auditor, native/solar refs, and passing acceptance checks. |
| Regression tests | ok | `test_semantic_parity_runtime_proof.py`: 2 passed; full proof writer group: 18 passed; `py_compile` passed. |
| Inventory/gate | ok | Real route inventory and feature parity gate pass; counts remain 0 full / 17 partial / 11 gated with 25 pending runtime proof slots. |
| Full parity claim | warn | Semantic equivalence proof can now be packaged, but completed per-route semantic audits must still be supplied and attached before any route can be promoted. |

## Phase 19 External Runtime Category Mapping Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `tools/fetch_s2.py`
- `tools/fetch_deepxiv.py`
- `tools/fetch_paper_copilot.py`
- `tools/approval_runtime_proof.py`
- `harness/plugins/autosci/tests/test_source_cli_tools.py`
- `harness/plugins/autosci/tests/test_approval_runtime_proof.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: ensure completed live provider fetches and verified approval contracts
can satisfy `external_runtime_evidence` without letting native replay or
inconclusive runs overclaim external runtime.

Non-goal: do not mark local file replay as live external runtime, and do not
change route parity counts without supplied runtime manifests.

### External Runtime Category Mapping Result

| Check | Status | Evidence |
|---|---|---|
| Live provider mapping | ok | S2/DeepXiv/Paper Copilot live provider proof defaults now include `provider_source_evidence` and `external_runtime_evidence`. |
| Native replay guard | ok | Paper Copilot `file://` provider replay defaults to `provider_source_evidence` only unless categories are explicitly supplied. |
| Approval runtime mapping | ok | Verified approval contracts now default to `approval_boundary_evidence`, `side_effect_execution_evidence`, and `external_runtime_evidence`. |
| Regression tests | ok | Source + approval tests: 10 passed; full proof writer group: 19 passed; `py_compile` passed. |
| Inventory/gate | ok | Real route inventory and feature parity gate pass; counts remain 0 full / 17 partial / 11 gated with 25 pending runtime proof slots. |
| Full parity claim | warn | Category mapping is ready, but actual live provider or verified approval manifests must still be collected and attached before pending slots can clear. |

## Phase 19 Runtime Proof Directory Attachment Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_parity_bridge.py`
- `harness/plugins/autosci/tests/test_phase19_parity_bridge.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: let parity inventory/route commands recursively attach
`autosci_runtime_proof_manifest.v1` files from a proof directory, so generated
proof bundles can be collected without passing every manifest path manually.

Non-goal: do not auto-promote routes, accept non-proof JSON, or treat blocked
proofs as supplied evidence.

### Runtime Proof Directory Attachment Result

| Check | Status | Evidence |
|---|---|---|
| CLI attachment | ok | `autosci_parity_bridge.py inventory/route` now accept `--runtime-proof-dir` and recursively scan JSON proof manifests. |
| Manifest filtering | ok | Directory scan accepts `autosci_runtime_proof_manifest.v1`/proof-list JSON and ignores ordinary JSON files. |
| Audit trail | ok | Evidence inputs now include `runtime_proof_dirs` and expanded `runtime_proof_manifest_paths`. |
| Regression tests | ok | `test_phase19_parity_bridge.py`: 8 passed; `py_compile` passed. |
| Inventory/gate | ok | Real route inventory and feature parity gate pass; counts remain 0 full / 17 partial / 11 gated with 25 pending runtime proof slots. |
| Full parity claim | warn | Proof bundles can now be attached by directory, but real proof manifests still need to be generated per route before pending requirements clear. |

## Phase 19 Semantic Proof Requirement Attachment Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_parity_bridge.py`
- `harness/plugins/autosci/tests/test_phase19_parity_bridge.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: make supplied `semantic_equivalence_evidence` runtime proof satisfy the
semantic proof requirement instead of leaving it permanently pending.

Non-goal: do not auto-promote route coverage or semantic parity status from
partial to full without a separate promotion policy.

### Semantic Proof Requirement Attachment Result

| Check | Status | Evidence |
|---|---|---|
| Requirement mapping | ok | `semantic_equivalence_evidence` now becomes `supplied` when a valid runtime proof manifest supplies that category. |
| No auto-promotion | ok | Test verifies a route with supplied semantic proof remains partial until remaining runtime/source/review proof is supplied and promotion policy is applied. |
| Regression tests | ok | `test_phase19_parity_bridge.py`: 9 passed; `py_compile` passed. |
| Inventory/gate | ok | Real route inventory and feature parity gate pass; counts remain 0 full / 17 partial / 11 gated with 25 pending runtime proof slots. |
| Full parity claim | warn | Semantic proof can now clear its requirement, but full parity still needs remaining proof categories and promotion policy. |

## Phase 19 Runtime Proof Verified State Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_parity_bridge.py`
- `harness/plugins/autosci/tests/test_phase19_parity_bridge.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: compute `runtime_proof_status=verified` when all runtime/source/
approval/review/wiki proof requirements are satisfied by ok/supplied evidence.

Non-goal: do not promote route coverage or semantic parity from partial/gated
to full solely because runtime proof is verified.

### Runtime Proof Verified State Result

| Check | Status | Evidence |
|---|---|---|
| Runtime-only verification | ok | `runtime_proof_status=verified` is now computed only from runtime/source/approval/review/wiki proof categories, excluding route/static/semantic requirements. |
| No semantic auto-promotion | ok | New daily-arxiv regression covers all runtime proof categories supplied while `semantic_equivalence_evidence` remains pending and route stays gated/partial. |
| Regression tests | ok | `test_phase19_parity_bridge.py`: 10 passed; `py_compile` passed for bridge/test files. |
| Inventory/gate | ok | Real route inventory and feature parity gate pass; counts remain 0 full / 17 partial / 11 gated with runtime proof counts 3 not_required / 25 pending / 0 supplied / 0 verified. |
| Full parity claim | warn | Verified runtime status is now representable, but real route proof manifests and semantic parity audits still need to be collected before any route can be promoted. |

## Phase 19 Full-Parity Acceptance Gate Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/evaluators/scientific/autosci_feature_parity_gate.py`
- `harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: add a strict acceptance check for final full parity so the existing
honesty/schema gate can keep passing partial/gated inventories while a separate
check fails until every route has semantic full parity, verified/not-required
runtime proof, and no unresolved proof requirements.

Non-goal: do not promote any route, change route config counts, weaken gated
side-effect safety, or claim full parity from documentation.

### Full-Parity Acceptance Gate Result

| Check | Status | Evidence |
|---|---|---|
| Strict acceptance API | ok | Added `evaluate_full_parity_acceptance()` and `--require-full-parity` to `autosci_feature_parity_gate.py`. |
| Side-effect safety | ok | Strict acceptance allows approval-required routes to remain `coverage_status=gated`, but only with `runtime_proof_status=verified`, semantic full parity, and no unresolved proof requirements. |
| Ordinary gate compatibility | ok | Normal feature parity gate still passes the current honest inventory without requiring full parity. |
| Regression tests | ok | `test_autosci_feature_parity_gate.py`: 12 passed; `test_phase19_parity_bridge.py`: 10 passed; `py_compile` passed. |
| Real strict gate | ok | `autosci_feature_parity_gate.py --require-full-parity /tmp/autosci-parity-full-acceptance.json` exits 2 and lists route-specific blockers instead of overclaiming completion. |
| Full parity claim | warn | Strict acceptance gate is in place, but current inventory still fails it for all 28 routes because semantic audits/runtime proofs/promotion-safe coverage states are not complete. |

## Phase 19 Survey Requested LaTeX Output Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `harness/plugins/autosci/config/feature_parity_routes.v1.json`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: make `$survey --format latex` produce an explicit LaTeX survey artifact
instead of only recording the requested format in inputs.

Non-goal: do not claim exhaustive survey coverage, live provider parity, or
semantic full parity from a format sidecar alone.

### Survey Requested LaTeX Output Result

| Check | Status | Evidence |
|---|---|---|
| LaTeX artifact | ok | `$survey --format latex` now emits `survey_latex_source` with a real `.tex` document in addition to markdown, plan, citation map, and coverage boundary. |
| Status honesty | ok | Missing source/citation/provider coverage still leaves survey evidence inconclusive/partial; LaTeX output does not imply exhaustive coverage. |
| Route truthfulness | ok | Survey route limitation now says markdown and requested LaTeX sidecar generation are wired while live/exhaustive coverage remains pending. |
| Regression tests | ok | Survey latex target: 1 passed; survey shim subset: 3 passed; bridge/test `py_compile` and route JSON validation passed. |
| Inventory/gate | ok | Real route inventory and ordinary feature gate pass; counts remain 0 full / 17 partial / 11 gated. Strict full-parity gate still fails as expected on unresolved survey source/semantic/runtime proof. |
| Full parity claim | warn | Requested LaTeX output parity improved for survey, but full survey parity still needs live/exhaustive source coverage, semantic audit, runtime proof, and final promotion-safe status. |

## Phase 19 Poster Render Flag CLI Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_skill_shim.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: accept and record native-style `$poster --render` requests so the
poster route no longer rejects a render intent before the existing approval
and allowlist runtime boundary can evaluate it.

Non-goal: do not execute browser rendering, overflow probing, or PNG export
without explicit approval and allowlisted renderer evidence.

### Poster Render Flag CLI Result

| Check | Status | Evidence |
|---|---|---|
| CLI compatibility | ok | `$poster --render` is now accepted and records `native_options.render=true` plus `inputs.render_requested=true`. |
| Approval boundary | ok | Without approval/allowlist evidence, render intent remains gated/inconclusive and browser/PNG validation stays false. |
| Existing executor path | ok | Existing approved poster executor tests still pass; this flag does not change allowlisted execution semantics. |
| Regression tests | ok | Poster render flag target: 1 passed; poster shim subset: 3 passed; `py_compile` passed. |
| Inventory/gate | ok | Real CLI smoke for `$poster --render` succeeds with gated/inconclusive status; route inventory and ordinary/strict gates remain honest. |
| Full parity claim | warn | Poster CLI parity improved, but full poster parity still requires approved renderer evidence, semantic audit, runtime proof attachment, and final acceptance. |

## Phase 19 Visualize Serve Flag CLI Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_skill_shim.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: accept and record native-style `$visualize --serve` requests so web UI
serving intent reaches the existing visualization evidence path.

Non-goal: do not start a long-lived local server, open a browser, or mark web
UI parity complete without explicit approval/runtime evidence.

### Visualize Serve Flag CLI Result

| Check | Status | Evidence |
|---|---|---|
| CLI compatibility | ok | `$visualize --serve` is now accepted and records `native_options.serve=true` plus `inputs.serve_requested=true`. |
| Side-effect boundary | ok | Without `--execute-approved` and approval/allowlist evidence, no long-lived server/web health execution occurs. |
| Local artifacts | ok | The visualize action still generates graph/canvas artifacts from local wiki state. |
| Regression tests | ok | Visualize serve flag target: 1 passed; visualize shim subset: 1 passed; `py_compile` passed. |
| Inventory/gate | ok | Real CLI smoke for `$visualize --serve` succeeds with gated/inconclusive status; route inventory and ordinary/strict gates remain honest. |
| Full parity claim | warn | Visualize CLI parity improved, but full visualize parity still requires approved web runtime proof, semantic audit, and final acceptance. |

## Phase 19 Latest Continuation Summary

Logged: 2026-06-30 EDT

This section mirrors the detailed entries recorded above for the latest
continuation so the newest audit state is visible at the end of the log.

| Fix | Status | Evidence |
|---|---|---|
| Exp-status live remote proof | ok | `codex-exp-status-live-remote-proof-fixed-check`; `$exp-status` runtime proof verified for live-provider status polling. |
| Research lifecycle route proof | ok | `codex-research-lifecycle-proof-check`; `$research` runtime proof verified from source, Review LLM, approval/runtime evidence. |
| Edit/refine approved mutation proof | ok | `codex-edit-proof-check` and `codex-refine-proof-check`; `$edit` and `$refine` runtime proof verified for approved mutation/apply evidence. |
| Exp-run final collect proof | ok | `codex-exp-run-final-proof-check`; `$exp-run` proof emitted only from `final_runtime_audit_ready=true` live-provider collect evidence. |
| Paper-compile runtime proof | ok | `codex-paper-compile-final-proof-check`; `$paper-compile` proof emitted from completed approved compile/runtime evidence. |
| Provider-source blockers | ok | Cleared for all routes in `current-parity-inventory-after-exp-run-paper-compile-proofs.json`; no pending `provider_source_evidence` rows remain. |
| Runtime proof inventory | warn | Runtime counts are `{not_required: 3, pending: 7, supplied: 9, verified: 9}`; remaining pending runtime routes still need real approved side-effect/runtime proof. |
| Semantic parity | warn | `semantic_full_count=0`; all 28 routes still require audited native AutoSci semantic equivalence evidence before full parity can be claimed. |
| Verification | ok | Full shim suite: 121 passed; parity/proof tests: 21 passed; exp-run/collect/paper-compile subset: 22 passed; `py_compile` and `git diff --check` passed. |

## Phase 19 Exp-Status Live Remote Proof Sync

Logged: 2026-06-30 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: make `$exp-status` attach a runtime proof only when the remote status
path performs an approved live provider poll, so provider-source and external
runtime evidence are not inferred from local run-directory inspection.

Non-goal: do not promote local status checks, collection/result readiness, or
semantic full parity from status polling alone.

### Exp-Status Live Remote Proof Result

| Check | Status | Evidence |
|---|---|---|
| Live-only proof artifact | ok | Approved live remote status checks now emit `monitor_experiment_remote_status_runtime_proof.json` with `external_runtime_evidence` and `provider_source_evidence`. |
| Local check boundary | ok | Run-directory status checks remain evidence-only and do not attach provider/source proof manifests. |
| Regression tests | ok | Exp-status shim subset: 9 passed; focused live/local proof tests passed before inventory refresh; `py_compile` passed. |
| Real CLI smoke | ok | `codex-exp-status-live-remote-proof-fixed-check` produced a `live_provider` proof referencing `experiment_status.json`, approval contract, executor output, and command stdout/stderr. |
| Parity inventory recognition | ok | `current-parity-inventory-after-exp-status-live-proof-fixed.json` marks `$exp-status` runtime proof `verified`; provider-source and external-runtime requirements are `supplied`, semantic remains `pending`. |
| Full parity claim | warn | Exp-status still needs audited semantic equivalence evidence before it can count as full parity. |

## Phase 19 Research Lifecycle Runtime Proof Plan

Logged: 2026-06-30 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: make `$research` attach route-level runtime proof manifests when its
native lifecycle evidence report contains explicit source/provider evidence,
Review LLM evidence, and approved runtime/approval evidence.

Non-goal: do not promote synthetic strict scheduler handoff fixtures, incomplete
stage plans, side effects, or semantic full parity.

### Research Lifecycle Runtime Proof Result

| Check | Status | Evidence |
|---|---|---|
| Source proof artifact | ok | `$research` now emits `run_research_lifecycle_source_provider_runtime_proof.json` only when discovery/novelty/paper source evidence is present. |
| Review proof artifact | ok | `$research` now emits `run_research_lifecycle_review_llm_runtime_proof.json` only when Review LLM evidence is completed. |
| Approval/runtime proof artifact | ok | `$research` now emits `run_research_lifecycle_approval_runtime_proof.json` only when approval contract execution is verified and experiment/compile runtime evidence is verified. |
| Synthetic scheduler boundary | ok | Strict synthetic lifecycle summaries do not emit route-level provider/review/approval proof manifests by themselves. |
| Regression tests | ok | Research shim subset: 14 passed; focused lifecycle proof tests: 4 passed; `py_compile` and `git diff --check` passed. |
| Real CLI smoke | ok | `codex-research-lifecycle-proof-check` passed the lifecycle action and attached source, review, and approval/runtime proof manifests to `workflow_evolution.research.json`. |
| Parity inventory recognition | ok | `current-parity-inventory-after-research-lifecycle-proofs.json` marks `$research` runtime proof `verified`; runtime counts are `{not_required: 3, pending: 11, supplied: 9, verified: 5}`. |
| Full parity claim | warn | Research still needs audited semantic equivalence evidence before it can count as full parity. Provider-source pending routes are now `edit`, `exp-run`, `paper-compile`, and `refine`. |

## Phase 19 Edit/Refine Approved Mutation Proof Plan

Logged: 2026-06-30 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: make `$edit` and `$refine` attach runtime proof manifests only when an
approved mutation/apply path has explicit approval, before, runtime, and
after-artifact evidence.

Non-goal: do not make proposal-only edits/refinements look executed, do not
change mutation permission semantics, and do not claim semantic full parity.

### Edit/Refine Approved Mutation Proof Result

| Check | Status | Evidence |
|---|---|---|
| Edit proof artifacts | ok | Approved `$edit` now emits provider/source, approval/runtime, side-effect execution, and wiki-mutation runtime proof manifests when approval/before/runtime/after evidence is verified. |
| Refine proof artifacts | ok | Approved `$refine` now emits provider/source, approval/runtime, and side-effect execution proof manifests when the approved after-artifact apply is completed. |
| Proposal boundary | ok | Proposal-only edit/refine paths do not emit proof manifests; existing mutation permission behavior was not changed. |
| Regression tests | ok | Edit/refine focused tests: 2 passed; `py_compile` and `git diff --check` passed. |
| Real CLI smoke | ok | `codex-edit-proof-check` and `codex-refine-proof-check` both passed their action gates and emitted the expected proof manifests. |
| Parity inventory recognition | ok | `current-parity-inventory-after-edit-refine-proofs.json` marks `$edit` and `$refine` runtime proof `verified`; runtime counts are `{not_required: 3, pending: 9, supplied: 9, verified: 7}`. |
| Full parity claim | warn | Edit/refine still need audited semantic equivalence evidence. Provider-source pending routes are now only `exp-run` and `paper-compile`. |

## Phase 19 Exp-Run/Paper-Compile Runtime Proof Plan

Logged: 2026-06-30 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: make `$exp-run` and `$paper-compile` attach runtime proof manifests from
their strict final/runtime boundaries: live-provider collect audit for exp-run,
and verified approval/runtime compile evidence for paper-compile.

Non-goal: do not promote local run-only experiment execution, local-only result
collection, unverified compile diagnostics, or semantic full parity.

### Exp-Run/Paper-Compile Runtime Proof Result

| Check | Status | Evidence |
|---|---|---|
| Exp-run final proof | ok | `$exp-run --collect` now emits `monitor_experiment_final_runtime_proof.json` only when `final_runtime_audit_ready=true`, including live-provider collection, approval/runtime evidence, side-effect execution, provider/source evidence, collection ledger, and wiki mutation artifacts. |
| Local collect boundary | ok | Local-only collect keeps final proof absent; stage audit can pass without promoting full runtime proof. |
| Paper compile proof | ok | `$paper-compile` now emits `compile_paper_runtime_proof.json` only when status is completed and approval/runtime semantic verification passes. |
| Regression tests | ok | Exp-run/collect/paper-compile shim subset: 22 passed; focused proof tests: 3 passed; `py_compile` and `git diff --check` passed. |
| Real CLI smoke | ok | `codex-exp-run-final-proof-check` produced live-provider final collect proof; `codex-paper-compile-final-proof-check` produced approved side-effect compile proof. |
| Parity inventory recognition | ok | `current-parity-inventory-after-exp-run-paper-compile-proofs.json` marks `$exp-run` and `$paper-compile` runtime proof `verified`; runtime counts are `{not_required: 3, pending: 7, supplied: 9, verified: 9}`. |
| Full parity claim | warn | Provider-source blockers are cleared, but semantic equivalence remains pending for all routes and runtime proof is still pending for remaining side-effect routes. |

## Phase 19 Native Tool Sync Inventory Snapshot

Logged: 2026-06-30 EDT

Planned file changes (pre-fix):
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: record the post-native-tool-sync parity gate baseline before the
next blocker fix. This is an audit/log-only step.

### Native Tool Sync Inventory Result

| Check | Status | Evidence |
|---|---|---|
| Ordinary parity gate | ok | `autosci_feature_parity_gate.py current-parity-inventory-after-native-tools.json` passed with warnings that non-full routes must remain limitation-aware. |
| Strict full-parity gate | error | `--require-full-parity` still fails because all 28 routes remain semantic partial and 25 routes have pending runtime proof status in this bare inventory. |
| Inventory shape | ok | Current inventory is a `ScientificEvidenceEnvelope`; route rows live under `outputs.parity.items`. |
| Counts | warn | `routed=28`, `full=0`, `partial=17`, `gated=11`, `semantic_full=0`, `semantic_partial=28`, runtime proof status counts: `not_required=3`, `pending=25`, `supplied=0`, `verified=0`. |
| Boundary honesty | ok | The gate failure is treated as authoritative evidence of remaining blockers; no route is promoted to full parity without semantic audit and required runtime proof. |

## Phase 19 Reset Native Tool Parity Sync

Logged: 2026-06-30 EDT

Planned file changes (pre-fix):
- `tools/reset_wiki.py`
- `harness/plugins/autosci/tests/test_root_tool_abi.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: restore the original AutoSci `/reset` scope planner and reset
execution mechanics while preserving Solar's approval boundary for destructive
filesystem mutation.

Non-goal: do not silently run destructive reset from compatibility smoke paths
or mark reset full parity without approval/runtime/semantic evidence.

### Reset Native Tool Parity Result

| Check | Status | Evidence |
|---|---|---|
| Native scope planner | ok | `tools/reset_wiki.py` now supports original `--scope wiki,raw,log,checkpoints,all`, `--project-root`, `--yes`, and `--dry-run` behavior plus Solar `--wiki-root` compatibility. |
| Approval boundary | ok | `--yes/--apply` without both `--approval-ref` and `--execute-approved` returns `approval_required` and leaves files untouched. |
| Approved execution | ok | Approved reset executes the original scoped wiki/raw/log/checkpoint mutation mechanics only against the requested project root and writes `autosci_runtime_evidence.v1` with action `reset_plan`. |
| Runtime evidence gate | ok | Reset runtime evidence includes a reset-plan artifact and passes `autosci_runtime_evidence_gate` in the targeted test. |
| Regression tests | ok | Target reset test: 1 passed; side-effect root smoke: 1 passed; full `test_root_tool_abi.py`: 6 passed with escalated loopback bind for the SMTP test; `py_compile` passed. |
| Full parity claim | warn | Reset still needs semantic parity audit and durable approval-contract proof attachment before the route can move from gated partial toward full parity. |

## Phase 19 Serve Native Tool Parity Sync

Logged: 2026-06-30 EDT

Planned file changes (pre-fix):
- `tools/serve.py`
- `harness/plugins/autosci/tests/test_root_tool_abi.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: restore the original AutoSci/OmegaWiki local server API surface for
`/visualize` and wiki mutation parity, while keeping smoke checks non-serving
through a bounded `--health-check` path.

Non-goal: do not auto-start a long-lived server/browser session from tests or
ungated shim execution.

### Serve Native Tool Parity Result

| Check | Status | Evidence |
|---|---|---|
| Native server surface | ok | `tools/serve.py` was mechanically restored from original AutoSci/OmegaWiki, including read APIs, loopback write APIs, SSE live reload, lint/regenerate endpoints, checkpoint browsing, and skill intent synthesis. |
| Solar health compatibility | ok | Added `--wiki-root` and `--health-check` so tests can validate app/wiki graph health without starting a long-lived HTTP server. |
| Boundary honesty | ok | Normal `tools/serve.py` execution still starts the native server explicitly; shim smoke and health checks remain bounded and non-serving. |
| Regression tests | ok | Serve health CLI smoke passed; `$visualize --serve` shim target: 1 passed; side-effect root smoke: 1 passed; full `test_root_tool_abi.py`: 6 passed with escalated loopback bind for SMTP; `py_compile` passed. |
| Full parity claim | warn | Visualize/serve still needs approved web runtime proof and semantic audit before the route can be promoted beyond gated partial parity. |

## Phase 19 Poster Native Tool Parity Sync

Logged: 2026-06-30 EDT

Planned file changes (pre-fix):
- `tools/poster.py`
- `harness/plugins/autosci/tests/test_root_tool_abi.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: restore the original AutoSci/PaperX DAG-to-poster mechanical pipeline
while preserving Solar's approval-gated render/export runtime-evidence ABI.

Non-goal: do not auto-run browser rendering without explicit approval,
allowlist, and `--execute-approved`.

### Poster Native Tool Parity Result

| Check | Status | Evidence |
|---|---|---|
| Native PaperX mechanics | ok | `tools/poster.py` was restored from original AutoSci/PaperX with template/outline build, DAG title/author injection, header/logo injection, figure copy/convert, validation, overflow probe, and browser render paths. |
| Solar compatibility | ok | `build --out --title --summary`, JSON `validate`, and approval-gated render/export flags remain supported for existing Solar root/shim ABI. |
| Approval boundary | ok | `render` only runs the allowlisted executor when `--approval-ref`, allowlist evidence, and `--execute-approved` are supplied; otherwise it stays approval-required/inconclusive. |
| Runtime evidence | ok | Approved render writes `autosci_runtime_evidence.v1` with action `build_poster`, render checks, PNG/validation artifacts, and passes the runtime evidence gate. |
| Regression tests | ok | Native template/outline pipeline: 1 passed; approved render root test: 1 passed; side-effect root smoke: 1 passed; poster shim render targets: 2 passed; full `test_root_tool_abi.py`: 7 passed with escalated loopback bind for SMTP; `py_compile` passed. |
| Full parity claim | warn | Poster route still needs semantic audit and durable approval-contract proof promotion before full parity; browser rendering remains correctly gated. |

## Phase 19 Send Email Native Tool Parity Sync

Logged: 2026-06-30 EDT

Planned file changes (pre-fix):
- `tools/send_email.py`
- `harness/plugins/autosci/tests/test_root_tool_abi.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: restore the original AutoSci daily-arxiv SMTP ABI for env-based
configuration, `--body-file`, and `--check-config`, while preserving Solar's
approval-gated delivery runtime evidence.

Non-goal: do not send email from original-style flags unless explicit approval
and execution are supplied.

### Send Email Native Tool Parity Result

| Check | Status | Evidence |
|---|---|---|
| Native SMTP ABI | ok | `tools/send_email.py` now supports original env configuration (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `DAILY_ARXIV_EMAIL_TO`, SSL/STARTTLS), top-level `--check-config`, and `--body-file`. |
| Solar approval boundary | ok | Original-style top-level send/body-file flags still return `approval_required` unless explicit approval and `--execute-approved` are supplied. |
| Approved delivery | ok | Existing approved SMTP path now accepts body-file content and continues to write `autosci_runtime_evidence.v1` with action `send_email`. |
| Regression tests | ok | Env check-config target: 1 passed; approved SMTP body-file target: 1 passed with escalated loopback bind; side-effect root smoke: 1 passed; full `test_root_tool_abi.py`: 8 passed; `py_compile` passed. |
| Full parity claim | warn | Daily/send-email side-effect parity still needs durable approval-contract proof promotion and semantic audit before full parity. |

## Phase 19 Side-Effect Tool Inventory Snapshot

Logged: 2026-06-30 EDT

Planned file changes (pre-fix):
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: record the parity baseline after reset/serve/poster/send-email native
tool restoration before moving to proof-promotion blockers.

### Side-Effect Tool Inventory Result

| Check | Status | Evidence |
|---|---|---|
| Inventory generation | ok | `autosci_parity_bridge.py inventory --out artifacts/autosci/phase19/current-parity-inventory-after-side-effect-tools.json` completed. |
| Counts | warn | Inventory remains `routed=28`, `full=0`, `partial=17`, `gated=11`, `semantic_full=0`, `semantic_partial=28`, runtime proof counts `not_required=3`, `pending=25`, `supplied=0`, `verified=0`. |
| Source/wiki regressions | ok | `test_source_cli_tools.py` + `test_research_wiki_tool.py`: 8 passed after helper restoration. |
| Interpretation | warn | Helper parity improved, but bare inventory remains strict-full failed until semantic audits and route-specific runtime proof manifests are supplied/promoted. |

## Phase 19 Coverage Promotion Gate Sync

Logged: 2026-06-30 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_parity_bridge.py`
- `harness/plugins/autosci/tests/test_phase19_parity_bridge.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: allow parity inventory to promote `coverage_status` only when semantic
audit and all runtime/tool proof requirements are satisfied, so strict full
parity can be reached from evidence instead of manual route-config edits.

Non-goal: do not promote bare partial routes, blocked proofs, missing tools, or
approval-required routes to ungated `full`.

### Coverage Promotion Gate Result

| Check | Status | Evidence |
|---|---|---|
| Evidence-based promotion | ok | `coverage_status` is now recalculated after proof requirements are built; promotion requires semantic parity `full`, tool ABI ok, every requirement `ok/supplied`, and runtime status `verified/not_required`. |
| Approval boundary | ok | Approval-required or side-effect-gated routes can only promote to `gated`, not ungated `full`. |
| Strict route proof | ok | New novelty full-proof fixture supplies semantic audit plus external runtime, Review LLM/model, provider/source, and wiki mutation categories; route promotes to `coverage_status=full` and strict `--require-full-parity` passes for that route. |
| Regression tests | ok | Coverage promotion target: 1 passed; semantic/runtime promotion targets: 2 passed; full `test_phase19_parity_bridge.py`: 12 passed; `py_compile` passed. |
| Full parity claim | warn | This unlocks evidence-based full coverage promotion, but each real route still needs its own verified semantic audit/runtime proof manifest before strict global full parity can pass. |

## Phase 19 Research E4 Proof Promotion Sync

Logged: 2026-06-30 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_parity_bridge.py`
- `harness/plugins/autosci/tests/test_phase19_parity_bridge.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: let `/research` reach strict full-parity proof level E4 from verified
semantic and lifecycle/runtime proof evidence instead of being capped at E3.

Non-goal: do not promote research to E4 from semantic audit alone or from
partial/blocked runtime proof categories.

### Research E4 Proof Promotion Result

| Check | Status | Evidence |
|---|---|---|
| E4 promotion | ok | `/research` proof level now promotes to `E4` only after semantic parity is full, runtime proof is verified/not-required, coverage is full/gated, and all proof requirements are `ok/supplied`. |
| Approval boundary | ok | Research remains `coverage_status=gated` because the route is approval-required; it is not promoted to ungated `full`. |
| Strict route proof | ok | New research lifecycle fixture supplies semantic audit plus external runtime, approval, Review LLM/model, and provider/source proof; strict `--require-full-parity` passes for that route. |
| Regression tests | ok | Research E4 target: 1 passed; coverage promotion target: 1 passed; full `test_phase19_parity_bridge.py`: 13 passed; `py_compile` passed. |
| Full parity claim | warn | This removes the research-specific proof-level ceiling, but real `/research` still needs a verified lifecycle audit/runtime manifest in the production artifact set. |

## Phase 19 Aggregate Regression Snapshot

Logged: 2026-06-30 EDT

Planned file changes (pre-fix):
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: record the post-helper-sync and proof-promotion regression baseline.

### Aggregate Regression Result

| Check | Status | Evidence |
|---|---|---|
| Parity/proof bridge tests | ok | `test_phase19_parity_bridge.py`, `test_semantic_parity_runtime_proof.py`, and `test_approval_runtime_proof.py`: 18 passed. |
| Source/wiki tests | ok | `test_source_cli_tools.py` and `test_research_wiki_tool.py`: 8 passed. |
| Root tool ABI | ok | Full `test_root_tool_abi.py`: 8 passed with escalated loopback bind for the SMTP test. |
| Interpretation | warn | Core helper ABI and proof promotion are stable, but global full parity still depends on supplying verified route-level semantic/runtime proof artifacts. |

## Phase 19 Runtime Proof Directory Path Resolution Sync

Logged: 2026-06-30 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_parity_bridge.py`
- `harness/plugins/autosci/tests/test_phase19_parity_bridge.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: fix `--runtime-proof-dir harness/...` resolution so repo-relative
proof directories are scanned instead of becoming `harness/harness/...`.

Non-goal: do not auto-consume arbitrary proof artifacts; callers still must
pass explicit runtime proof dirs/manifests.

### Runtime Proof Directory Path Resolution Result

| Check | Status | Evidence |
|---|---|---|
| Repo-relative path handling | ok | `resolve_output("harness/artifacts/autosci/runs")` now resolves to the repository `harness/artifacts/autosci/runs` directory instead of `harness/harness/...`. |
| Runtime proof absorption | ok | Inventory with `--runtime-proof-dir harness/artifacts/autosci/runs` now reports `runtime_proof_status_counts={not_required:3,pending:14,supplied:8,verified:3}`. |
| Requirement accounting | ok | The same inventory reports `proof_requirement_status_counts={ok:84,pending:94,supplied:24,blocked:0,missing:0}` and keeps semantic parity partial until semantic audits are supplied. |
| Regression tests | ok | Path-resolution and runtime-proof directory attachment targets: 2 passed; `py_compile` passed for bridge and tests. |
| Full parity claim | warn | This fixes proof discovery for existing run artifacts; global full parity still requires semantic full audits and the remaining pending proof categories. |

## Phase 19 Direct Semantic Audit Ingestion Sync

Logged: 2026-06-30 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_parity_bridge.py`
- `harness/plugins/autosci/tests/test_phase19_parity_bridge.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: let parity inventory consume strict route-level
`autosci_semantic_parity_audit.v1` JSON directly through explicit audit paths
or audit directories, without requiring a separate runtime-proof wrapping step.

Non-goal: do not promote any route from the old overall audit report or from
partial/incomplete audits; promotion must still require skill-matching,
completed/full semantic audits with existing native/solar evidence refs and
passing acceptance checks.

### Direct Semantic Audit Ingestion Result

| Check | Status | Evidence |
|---|---|---|
| CLI evidence path | ok | `autosci_parity_bridge.py inventory/route` now accepts `--semantic-audit` and `--semantic-audit-dir`. |
| Strict audit validation | ok | Direct audits are converted to semantic proof sources only when `autosci_semantic_parity_audit.v1` is completed/full, skill-matching, has auditor/native/solar refs, and all acceptance checks pass. |
| Partial-audit guard | ok | Partial semantic audits discovered from a directory remain blocked proof sources, expose `semantic_audit_status=inconclusive` with reasons, and keep `semantic_equivalence_evidence=pending`. |
| Path safety | ok | `artifacts/...` outputs continue to resolve under `HARNESS_DIR`; repo-relative `harness/...` proof dirs still resolve to the repository harness path. |
| Regression tests | ok | Full `test_phase19_parity_bridge.py`: 16 passed; `py_compile` passed for bridge and tests. |
| Real inventory | ok | Inventory with `--runtime-proof-dir harness/artifacts/autosci/runs` still reports `runtime_proof_status_counts={not_required:3,pending:14,supplied:8,verified:3}` and `semantic_full_count=0`. |
| Full parity claim | warn | This unblocks direct route-level semantic audit ingestion, but no real completed/full route audit is currently supplied in the artifact set. |

## Phase 19 Ideate Five-Phase Pipeline Report Sync

Logged: 2026-06-30 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: make `$ideate` emit explicit native five-phase pipeline evidence and
A/B/C/D/E generation-path coverage, so missing native ideation semantics are
visible as structured blockers instead of being buried in prose limitations.

Non-goal: do not fabricate dual-model brainstorms, novelty/review decisions,
wiki writeback, or pilot execution; missing evidence must remain incomplete.

### Ideate Five-Phase Pipeline Report Result

| Check | Status | Evidence |
|---|---|---|
| Pipeline evidence | ok | `$ideate` now emits `autosci_ideate_pipeline_report.v1` as `ideate_pipeline_report_json`. |
| Five-phase blockers | ok | Report records phase1 landscape scan, phase2 dual-model brainstorm, phase3 novelty/review validation, phase4 wiki writeback, and phase5 pilot handoff as explicit phase rows with evidence refs and blockers. |
| A-E path coverage | ok | Final promotion boundary and pipeline report both record required A/B/C/D/E paths, present paths, missing paths, and coverage status. |
| Promotion honesty | ok | Ideas without a native A/B/C/D/E generation path now carry the blocker `structured generation path A/B/C/D/E is missing`; missing dual-model/review/write/pilot evidence remains incomplete. |
| Regression tests | ok | Ideate source/model/missing-source targets: 3 passed; ideate/novelty/review shim subset: 16 passed; `py_compile` passed. |
| Real CLI smoke | ok | `codex-ideate-pipeline-report-check` produced `ideate_pipeline_report.json` with `status=incomplete`, `present_paths=[A,E]`, `missing_paths=[B,C,D]`, and explicit phase2-5 blockers. |
| Full parity claim | warn | This makes native five-phase gaps machine-readable; full `/ideate` parity still needs real dual-model evidence, B/C/D path generation, novelty/review validation, approved wiki writeback, and pilot handoff/skip proof. |

## Phase 19 Ideate Source-Grounded A-E Candidate Coverage Sync

Logged: 2026-06-30 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/backends/idea_source.py`
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: extend source-grounded deterministic `/ideate` candidates to cover
native generation paths B/C/D when wiki method evidence exists, so A-E path
coverage can be audited separately from the still-required dual-model and
validation phases.

Non-goal: do not treat deterministic B/C/D candidates as Codex/Review LLM
brainstorm parity; model/review evidence and downstream gates remain required.

### Ideate Source-Grounded A-E Candidate Coverage Result

| Check | Status | Evidence |
|---|---|---|
| B path | ok | Source-grounded ideate now emits `B:incremental` candidates from wiki method evidence. |
| C path | ok | With two wiki methods, ideate emits `C:combination` candidates grounded in both method evidence ids. |
| D path | ok | With two wiki methods, ideate emits `D:innovation` candidates for shared-assumption relaxation. |
| A/E preservation | ok | Existing landscape-driven `A` and cross-domain-transfer `E` candidates remain present. |
| Boundary honesty | ok | A-E coverage can become complete, but pipeline report remains `incomplete` without dual-model brainstorm, novelty/review validation, approved writeback, and pilot handoff/skip proof. |
| Regression tests | ok | Ideate source/model/missing-source targets: 3 passed; ideate/novelty/review shim subset: 16 passed; `py_compile` passed. |
| Full parity claim | warn | Source-grounded A-E candidate coverage is improved, but deterministic candidates are not a replacement for native Codex + Review LLM brainstorm parity. |

## Phase 19 Ideate Skip-Validation Action Routing Sync

Logged: 2026-06-30 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_skill_shim.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: make `$ideate --skip-validation` skip the `evaluate_ideas` action, as
native `/ideate` defines skip-validation as Phase 3 deep-validation bypass.

Non-goal: do not mark generated ideas promotion-ready without novelty/review
evidence; skipped validation remains explicit in the pipeline report.

### Ideate Skip-Validation Action Routing Result

| Check | Status | Evidence |
|---|---|---|
| Action routing | ok | `$ideate --skip-validation` now selects only `generate_ideas`; default `/ideate` still runs `generate_ideas` plus `evaluate_ideas`. |
| Pipeline semantics | ok | `ideate_pipeline_report.v1` records phase3 as `skipped` when `--skip-validation` is supplied. |
| Pilot semantics | ok | `--skip-pilot` records phase5 as `skipped` without pretending pilot runtime evidence exists. |
| Regression tests | ok | Skip-validation target plus source ideate target: 2 passed; ideate/novelty/review shim subset: 17 passed; `py_compile` passed. |
| Real CLI smoke | ok | `codex-ideate-skip-validation-check` returned `action_count=1`; pipeline report had phase3=`skipped`, phase5=`skipped`, and `pipeline_ready=false`. |
| Full parity claim | warn | Skip flags now affect routing/reporting, but full `/ideate` still needs dual-model brainstorm, validation evidence when not skipped, approved writeback, and semantic audit proof. |

## Phase 19 Ideate Max-Ideas Selection Sync

Logged: 2026-06-30 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/backends/idea_source.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: make native `$ideate --max-ideas N` affect candidate selection by
marking the first N non-filtered candidates as selected for write/promotion,
while keeping the full candidate pool available for audit.

Non-goal: do not truncate evidence, discard eliminated ideas, or perform wiki
writeback without explicit approved mutation.

### Ideate Max-Ideas Selection Result

| Check | Status | Evidence |
|---|---|---|
| Candidate preservation | ok | `--max-ideas` no longer drops candidates; full candidate evidence remains auditable. |
| Selection marker | ok | Non-filtered candidates now carry `selected_for_write` and `selection_rank`; candidates beyond max carry a selection reason. |
| Model/source consistency | ok | Selection is applied in the bridge attach path, so source-grounded and model-command ideas share the same max-ideas semantics. |
| Pipeline report | ok | `ideate_pipeline_report.v1` records `max_ideas` and `selected_for_write_count`. |
| Regression tests | ok | Max-ideas source ideate, model-command ideate, and skip-validation targets: 3 passed; ideate/novelty/review shim subset: 17 passed; `py_compile` passed. |
| Full parity claim | warn | Selection semantics are wired, but approved wiki writeback is still required before selected ideas become persisted wiki pages. |

## Phase 19 Ideate Review LLM Brainstorm Completion Sync

Logged: 2026-06-30 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: require completed Review LLM evidence, not merely a
`review_llm_evidence` path reference, before phase2 dual-model brainstorm is
considered complete in `ideate_pipeline_report.v1`.

Non-goal: do not execute a Review LLM provider automatically or count local
surrogate review evidence as independent Review LLM brainstorm parity.

### Ideate Review LLM Brainstorm Completion Result

| Check | Status | Evidence |
|---|---|---|
| Completion rule | ok | Phase2 dual-model brainstorm now requires `_review_llm_evidence_completed(...)`, not just a non-empty review evidence path. |
| Surrogate guard | ok | Local surrogate or malformed review evidence remains incomplete for independent Review LLM brainstorm parity. |
| Pipeline report | ok | `ideate_pipeline_report.v1` records `review_llm_evidence_completed` and uses the blocker `independent Review LLM brainstorm evidence is missing or incomplete`. |
| Regression tests | ok | Source/model/skip-validation ideate targets: 3 passed; ideate/novelty/review shim subset: 17 passed; `py_compile` passed. |
| Full parity claim | warn | This tightens phase2 truthfulness; actual full parity still requires real completed Review LLM brainstorm evidence plus Codex/model brainstorm evidence. |

## Phase 19 Experiment Full Mode Action Routing Sync

Logged: 2026-06-30 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_skill_shim.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: make native `$exp-run --full` route through deploy plus monitor/collect
actions, rather than stopping after the deploy-side `run_experiment` action.

Non-goal: do not execute unapproved experiment code or remote commands; full
mode remains approval-gated and evidence-driven.

### Experiment Full Mode Action Routing Result

| Check | Status | Evidence |
|---|---|---|
| Full-mode route | ok | `$exp-run --full` now selects `design_experiment`, `run_experiment`, and `monitor_experiment`. |
| Dependency scope | ok | Full mode uses the native experiment lifecycle chain only; it does not pull the broader research/ingest/ideate dependency chain. |
| Collect preservation | ok | `$exp-run --collect` remains monitor-only. |
| Safety boundary | ok | Without approval/runtime evidence, full mode remains `gated`/`inconclusive`; no experiment command or remote side effect is executed. |
| Regression tests | ok | Full/deploy/collect exp-run targets: 3 passed; exp-run/exp-status/exp-collect shim subset: 21 passed; `py_compile` passed. |
| Real CLI smoke | ok | `codex-exp-run-full-routing-check` returned `action_count=3`, `execution_status=gated`, `status=inconclusive`. |
| Full parity claim | warn | Full mode routing is closer to native, but deploy/monitor/collect still needs approved runtime, remote/provider, collection-ledger, wiki mutation, and semantic audit proof before full parity. |

## Phase 19 Exp/Ideate Aggregate Snapshot

Logged: 2026-06-30 EDT

Planned file changes (pre-fix):
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: record the post-exp-full-routing aggregate verification baseline before
moving to the next full-parity blocker.

### Exp/Ideate Aggregate Result

| Check | Status | Evidence |
|---|---|---|
| Parity/proof tests | ok | `test_phase19_parity_bridge.py`, `test_semantic_parity_runtime_proof.py`, and `test_approval_runtime_proof.py`: 21 passed. |
| Shim regression subset | ok | `test_autosci_skill_shim.py -k 'ideate or novelty or review_resolves or exp_run or exp_status or exp_collect'`: 38 passed, 83 deselected. |
| Inventory artifact | ok | Generated `harness/artifacts/autosci/phase19/current-parity-inventory-after-exp-full-routing.json`. |
| Inventory honesty | ok | Inventory remains 0 full, 17 partial, 11 gated, `semantic_full_count=0`, runtime counts `{not_required:3,pending:14,supplied:8,verified:3}`. |
| Interpretation | warn | Exp full routing and ideate pipeline evidence are now stricter, but global full parity is still blocked by semantic audits plus remaining runtime/side-effect proofs. |

## Phase 19 Ask Workspace Source Proof Sync

Logged: 2026-06-30 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: expose `$ask` workspace wiki retrieval as source-channel runtime proof
for `provider_source_evidence` when retrieved wiki source paths are present.

Non-goal: do not count workspace wiki retrieval as external provider/runtime
execution; `external_runtime_evidence` remains pending unless a real provider
or approved runtime proof is supplied.

### Ask Workspace Source Proof Result

| Check | Status | Evidence |
|---|---|---|
| Source proof artifact | ok | `$ask` now writes `ask_wiki_source_provider_runtime_proof.json` when wiki retrieval returns source paths. |
| Category boundary | ok | The manifest category is exactly `provider_source_evidence`; it does not include `external_runtime_evidence`. |
| Regression tests | ok | Ask/check targeted tests: 8 passed; focused source/model ask tests: 2 passed; `py_compile` passed. |
| Real CLI smoke | ok | `codex-ask-source-proof-check` generated the source proof from `artifacts/autosci/workspace/wiki` SkillGen sources. |
| Inventory recognition | ok | `current-parity-inventory-after-ask-source-proof.json` marks `ask.provider_source_evidence=supplied` while `ask.external_runtime_evidence` remains pending. |
| Full parity claim | warn | Ask still needs semantic equivalence audit plus external runtime/provider evidence before full parity. |

## Phase 19 Ideate Source Proof Attachment Sync

Logged: 2026-06-30 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/backends/idea_source.py`
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: expose source-grounded ideate candidates as `provider_source_evidence`
runtime proof when wiki/discovery source refs are present.

Non-goal: do not count source-grounded deterministic candidates as external
runtime, novelty validation, Review LLM brainstorm, or semantic full parity.

### Ideate Source Proof Attachment Result

| Check | Status | Evidence |
|---|---|---|
| Source refs | ok | `idea_source.py` now records `source_ids` and file-backed `source_refs` in `source_summary`. |
| Source proof artifact | ok | `generate_ideas_source_provider_runtime_proof.json` is written for source-backed ideate runs. |
| Category boundary | ok | The manifest category is exactly `provider_source_evidence`; logical ids remain in provenance and are not path-like `evidence_refs`. |
| Regression tests | ok | Source/model/skip-validation ideate targets: 3 passed; ideate/novelty/review shim subset: 17 passed; `py_compile` passed. |
| Real CLI smoke | ok | `codex-ideate-source-proof-fixed-check` generated a supplied source proof from current workspace wiki/discovery evidence. |
| Inventory recognition | ok | `current-parity-inventory-after-ideate-source-proof-clean.json` marks `ideate.provider_source_evidence=supplied` with no blocked ideate source proof. |
| Full parity claim | warn | Ideate still needs semantic audit, external runtime/provider proof, completed independent Review LLM brainstorm, novelty/review gates, and approved wiki write/pilot evidence before full parity. |

## Phase 19 Survey Citation Source Proof Sync

Logged: 2026-06-30 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: expose `$survey` citation-map source evidence as
`provider_source_evidence` when discovery/paper/wiki citation entries are
present.

Non-goal: do not count citation-map assembly as live external runtime or
exhaustive survey coverage.

### Survey Citation Source Proof Result

| Check | Status | Evidence |
|---|---|---|
| Source input refs | ok | Phase14 publication source input keys are centralized, and source evidence file paths can be referenced by proof manifests. |
| Citation proof artifact | ok | `$survey` now writes `write_survey_source_provider_runtime_proof.json` when citation-map entries exist. |
| Category boundary | ok | The manifest category is exactly `provider_source_evidence`; `external_runtime_evidence` remains pending. |
| Regression tests | ok | Survey shim targets: 3 passed; `py_compile` passed. |
| Real CLI smoke | ok | `codex-survey-source-proof-check` generated survey source proof from discovery evidence and workspace wiki citations. |
| Inventory recognition | ok | `current-parity-inventory-after-survey-source-proof.json` marks `survey.provider_source_evidence=supplied`; runtime counts moved to `{not_required:3,pending:13,supplied:9,verified:3}`. |
| Full parity claim | warn | Survey still needs semantic audit and external runtime/provider proof before full parity. |

## Phase 19 Publication Citation Source Proof Sync

Logged: 2026-06-30 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: reuse the strict citation-map source proof path for `$paper-plan` and
`$paper-draft` so source-backed citation evidence is visible to parity
inventory.

Non-goal: do not mark paper plan final acceptance, manuscript readiness,
compile/PDF handoff, external runtime, or semantic parity complete from
citation-map proof alone.

### Publication Citation Source Proof Result

| Check | Status | Evidence |
|---|---|---|
| Paper-plan proof artifact | ok | `$paper-plan` now writes `plan_report_source_provider_runtime_proof.json` when citation entries exist. |
| Paper-draft proof artifact | ok | `$paper-draft` now writes `write_report_source_provider_runtime_proof.json` when citation entries exist. |
| Category boundary | ok | Both manifests declare only `provider_source_evidence`; external runtime remains pending. |
| Regression tests | ok | Paper-plan/paper-draft shim targets: 6 passed; focused source proof targets: 3 passed; `py_compile` passed. |
| Real CLI smoke | ok | `codex-paper-plan-source-proof-check` and `codex-paper-draft-source-proof-check` generated supplied source proof manifests from discovery + Review LLM evidence. |
| Inventory recognition | ok | `current-parity-inventory-after-publication-source-proofs.json` marks `paper-plan.provider_source_evidence=supplied` and `paper-draft.provider_source_evidence=supplied`. |
| Full parity claim | warn | Paper-plan and paper-draft still need semantic audits, external runtime proof, and verified compile/PDF or final readiness evidence before full parity. |

## Phase 19 Review Target Source Proof Sync

Logged: 2026-06-30 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: expose the concrete artifact reviewed by `$review` as
`provider_source_evidence` when the target artifact path resolves locally.

Non-goal: do not count review target availability as Review LLM completion,
external provider execution, or semantic parity.

### Review Target Source Proof Result

| Check | Status | Evidence |
|---|---|---|
| Source proof artifact | ok | `$review` now writes `review_artifact_source_provider_runtime_proof.json` when the reviewed artifact path exists. |
| Category boundary | ok | The source proof category is exactly `provider_source_evidence`; Review LLM proof remains a separate manifest. |
| Regression tests | ok | Review shim targets: 14 passed; focused review source targets: 4 passed; `py_compile` passed. |
| Real CLI smoke | ok | `codex-review-source-proof-check` generated both target source proof and Review LLM runtime proof from existing workspace/review evidence. |
| Inventory recognition | ok | `current-parity-inventory-after-review-source-proof.json` marks `review.provider_source_evidence=supplied` while external runtime remains pending. |
| Full parity claim | warn | Review still needs semantic audit and external/live provider runtime proof before full parity. |

## Phase 19 Ingest Source Proof Attachment Sync

Logged: 2026-06-30 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: expose `$ingest` paper source preparation and parse provenance as
`provider_source_evidence` when source preparation, parse quality, and raw
artifact provenance checks pass.

Non-goal: do not mark ingest wiki mutation proof supplied without an approved
writeback/before-after mutation sidecar; current source proof does not satisfy
`wiki_mutation_evidence`.

### Ingest Source Proof Attachment Result

| Check | Status | Evidence |
|---|---|---|
| Source proof artifact | ok | `$ingest` now writes `ingest_paper_source_provider_runtime_proof.json` when paper source preparation is verified. |
| Boundary honesty | ok | Provider-source proof can be supplied while wiki mutation evidence remains pending. |
| Regression tests | ok | Ingest shim targets: 7 passed; focused ingest source tests: 3 passed; `py_compile` passed. |
| Real CLI smoke | ok | `codex-ingest-source-proof-check` generated source proof from `skillgen_sample_paper.md`. |
| Inventory recognition | ok | `current-parity-inventory-after-ingest-source-proof.json` marks `ingest.provider_source_evidence=supplied`; `ingest.wiki_mutation_evidence` remains pending. |
| Full parity claim | warn | Ingest still needs semantic audit and approved wiki mutation proof before full parity. |

## Phase 19 Ideate Pipeline Aggregate Snapshot

Logged: 2026-06-30 EDT

Planned file changes (pre-fix):
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: record the post-ideate-pipeline regression and inventory baseline.

### Ideate Pipeline Aggregate Result

| Check | Status | Evidence |
|---|---|---|
| Parity/proof tests | ok | `test_phase19_parity_bridge.py`, `test_semantic_parity_runtime_proof.py`, and `test_approval_runtime_proof.py`: 21 passed. |
| Ideate/novelty/review shim subset | ok | `test_autosci_skill_shim.py -k 'ideate or novelty or review_resolves'`: 17 passed. |
| Inventory honesty | ok | `current-parity-inventory-after-ideate-pipeline-sync.json` remains 0 full, 17 partial, 11 gated, `semantic_full_count=0`, runtime counts `{not_required:3,pending:14,supplied:8,verified:3}`. |
| Interpretation | warn | Ideate evidence is more native-shaped and more truthful, but global full parity still depends on semantic audits and remaining runtime/side-effect proofs. |

## Phase 19 Novelty Runtime Proof Attachment Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: when `$novelty` has completed external novelty provider evidence and
completed Review LLM evidence, attach runtime proof manifests for
`provider_source_evidence` and `review_llm_or_model_evidence`.

Non-goal: do not mark novelty final acceptance, semantic parity, or wiki
mutation proof complete unless their existing strict evidence gates pass.

### Novelty Runtime Proof Attachment Result

| Check | Status | Evidence |
|---|---|---|
| Provider/source proof artifact | ok | `$novelty --novelty-evidence` now emits `evaluate_ideas_external_novelty_runtime_proof.json` only when external novelty is completed and provider provenance passed. |
| Review LLM proof artifact | ok | `$novelty --review-llm-evidence` now emits `evaluate_ideas_review_llm_runtime_proof.json` only when Review LLM evidence is completed and carries evidence ids. |
| Boundary honesty | ok | Novelty final acceptance still depends on existing external novelty, provider provenance, Review LLM, and numeric novelty-score gates; missing evidence remains incomplete. |
| Regression tests | ok | Novelty targeted tests: 4 passed; `py_compile` passed. |
| Real CLI smoke | ok | `codex-novelty-runtime-proof-check` attached provider-source and Review LLM proof manifests; final boundary was ready only because both supplied evidence paths were valid. |
| Parity inventory recognition | ok | Inventory with the novelty proof dir marks `novelty.review_llm_or_model_evidence=supplied` and `novelty.provider_source_evidence=supplied`; ordinary gate passed. |
| Full parity claim | warn | Strict full-parity gate still fails; novelty still needs semantic equivalence, live external runtime proof where applicable, and wiki mutation proof before full parity. |

## Phase 19 Novelty Wiki Mutation Runtime Proof Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: when `$novelty --write` actually applies the wiki novelty-score
mutation, attach an `autosci_runtime_proof_manifest.v1` for
`wiki_mutation_evidence` using the existing `novelty_writeback.v1` sidecar
boundary.

Non-goal: do not mark skipped/inconclusive writebacks as wiki mutation proof,
and do not promote semantic parity or coverage status from writeback alone.

### Novelty Wiki Mutation Runtime Proof Result

| Check | Status | Evidence |
|---|---|---|
| Wiki mutation proof artifact | ok | Completed `$novelty --write` now emits `evaluate_ideas_wiki_mutation_runtime_proof.json` with category `wiki_mutation_evidence`. |
| Skip boundary | ok | Inconclusive/skipped writebacks do not emit wiki mutation runtime proof. |
| Regression tests | ok | Novelty writeback targeted tests: 4 passed; wiki mutation proof tool tests: 3 passed; `py_compile` passed. |
| Real CLI smoke | ok | `codex-novelty-wiki-mutation-proof-check` wrote `novelty_writeback.json`, updated the wiki idea/log/edges/index/context, and attached wiki mutation proof. |
| Parity inventory recognition | ok | Inventory with the novelty writeback proof dir marks `novelty.wiki_mutation_evidence=supplied` alongside provider-source and Review LLM proof. |
| Full parity claim | warn | Strict full-parity gate still fails; novelty still needs semantic equivalence evidence and live external runtime evidence before full parity. |

## Phase 19 Novelty Live Provider Runtime Proof Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: verify that `$novelty --online` marks external provider runtime proof
only when the completed novelty evidence came from an HTTP provider endpoint.

Non-goal: do not treat supplied local/file evidence as live external runtime,
and do not promote novelty semantic parity or route coverage from provider
runtime proof alone.

### Novelty Live Provider Runtime Proof Result

| Check | Status | Evidence |
|---|---|---|
| HTTP provider classification | ok | Added targeted coverage showing HTTP web-provider novelty evidence emits categories `provider_source_evidence` and `external_runtime_evidence`. |
| Local evidence boundary | ok | Supplied/file evidence remains `provider_source_evidence` only and is not treated as live external runtime. |
| Regression tests | ok | Novelty provider subset: 3 passed with local HTTP bind allowed; `py_compile` passed. |
| Sandbox note | warn | The non-escalated test run could not bind `127.0.0.1` in this sandbox; the same targeted test passed with local bind permission. |
| Full parity claim | warn | This makes live provider runtime proof attachable, but novelty still needs semantic equivalence audit before strict full parity can pass. |

## Phase 19 Discover Provider Runtime Proof Attachment Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: when `$discover` produces a completed non-fixture source-provider
boundary from approved runtime evidence or live provider execution, attach an
AutoSci runtime proof manifest for `provider_source_evidence` and
`external_runtime_evidence`.

Non-goal: do not mark disabled-network, fixture, empty-shortlist, or
approval-pending discovery as provider/runtime complete.

### Discover Provider Runtime Proof Attachment Result

| Check | Status | Evidence |
|---|---|---|
| Provider/runtime proof artifact | ok | Completed source-provider `$discover` now emits `discover_literature_source_provider_runtime_proof.json`. |
| Boundary honesty | ok | Generic approved runtime without non-fixture provider channel still emits no provider proof and remains incomplete. |
| Regression tests | ok | Discover runtime/provider targeted tests: 3 passed; `py_compile` passed. |
| Real CLI smoke | ok | `codex-discover-provider-proof-check` produced a verified source-provider boundary and attached provider-source/external-runtime proof. |
| Parity inventory recognition | ok | Inventory with the discover proof dir marks `discover.external_runtime_evidence=supplied`, `discover.provider_source_evidence=supplied`, and route runtime status `verified`; ordinary gate passed. |
| Full parity claim | warn | Strict full-parity gate still fails because discover lacks semantic equivalence evidence and route coverage remains partial. |

## Phase 19 Init Daily Source Provider Runtime Proof Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: when `$init` or `$daily-arxiv` has verified approved source runtime
evidence with a completed non-fixture provider boundary, attach provider-source
and external-runtime proof manifests.

Non-goal: do not treat pending approval, generic runtime channels, delivery
completion, or wiki fan-in as automatically complete from provider proof alone.

### Init Daily Source Provider Runtime Proof Result

| Check | Status | Evidence |
|---|---|---|
| Init provider/runtime proof | ok | `$init` with verified approved source runtime now emits `init_sources_source_provider_runtime_proof.json`. |
| Daily provider/runtime proof | ok | `$daily-arxiv` with verified approved source runtime now emits `daily_arxiv_prepare_finalize_source_provider_runtime_proof.json`. |
| Boundary honesty | ok | Provider proof does not mark approval boundary, delivery, wiki fan-in, side-effect execution, or semantic parity complete. |
| Regression tests | ok | Init/daily targeted tests: 4 passed; `py_compile` passed. |
| Real CLI smoke | ok | `codex-init-provider-proof-check` and `codex-daily-provider-proof-check` attached provider-source/external-runtime proof manifests. |
| Parity inventory recognition | ok | Inventory with both proof dirs marks `init` and `daily-arxiv` provider/source and external/runtime requirements as supplied; ordinary gate passed. |
| Full parity claim | warn | Strict full-parity gate still fails for remaining approval, wiki mutation, side-effect, Review LLM, semantic, and coverage requirements. |

## Phase 19 Init Daily Approval Boundary Proof Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: when `$init` or `$daily-arxiv` has a verified approval contract,
attach an approval-boundary runtime proof manifest.

Non-goal: do not mark side-effect execution, delivery, auto-ingest, or wiki
mutation complete from approval-boundary proof alone.

### Init Daily Approval Boundary Proof Result

| Check | Status | Evidence |
|---|---|---|
| Init approval proof | ok | `$init` with verified approval contract now emits `init_sources_approval_boundary_runtime_proof.json`. |
| Daily approval proof | ok | `$daily-arxiv` with verified approval contract now emits `daily_arxiv_prepare_finalize_approval_boundary_runtime_proof.json`. |
| Side-effect honesty | ok | Approval proof category is limited to `approval_boundary_evidence`; side-effect execution, delivery, and wiki mutation remain pending unless separately proven. |
| Regression tests | ok | Init/daily approval targeted tests: 2 passed; approval proof tool tests: 3 passed; `py_compile` passed. |
| Real CLI smoke | ok | `codex-init-provider-proof-check` and `codex-daily-provider-proof-check` attached approval-boundary proof manifests. |
| Parity inventory recognition | ok | Inventory marks `init.approval_boundary_evidence=supplied` and `daily-arxiv.approval_boundary_evidence=supplied`; ordinary gate passed. |
| Full parity claim | warn | Strict full-parity gate still fails for semantic, route coverage, wiki mutation, and daily side-effect/review proof blockers. |

## Phase 19 Source Fan-In Wiki Mutation Proof Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: when source fan-in writeback completes for `$init --write` or
`$daily-arxiv --write`, attach `wiki_mutation_evidence` proof from the
`source_fan_in_writeback.v1` sidecar.

Non-goal: do not mark unrequested, skipped, or inconclusive fan-in writebacks
as wiki mutation evidence, and do not mark daily delivery as complete from
wiki ingest alone.

### Source Fan-In Wiki Mutation Proof Result

| Check | Status | Evidence |
|---|---|---|
| Init fan-in proof | ok | `$init --write` completed fan-in now emits `init_sources_wiki_mutation_runtime_proof.json`. |
| Daily fan-in proof | ok | `$daily-arxiv --write` completed fan-in now emits `daily_arxiv_prepare_finalize_wiki_mutation_runtime_proof.json`. |
| Boundary honesty | ok | Wiki mutation proof is emitted only from completed `source_fan_in_writeback.v1`; daily delivery/side-effect execution remains separately pending. |
| Regression tests | ok | Source fan-in targeted tests: 3 passed; wiki mutation proof tool tests: 3 passed; `py_compile` passed. |
| Real CLI smoke | ok | `codex-init-fanin-proof-check` and `codex-daily-fanin-proof-check` attached wiki mutation proof manifests. |
| Parity inventory recognition | ok | Inventory marks `init.wiki_mutation_evidence=supplied` and `daily-arxiv.wiki_mutation_evidence=supplied`; ordinary gate passed. |
| Full parity claim | warn | Strict full-parity gate still fails; init now mainly lacks semantic equivalence, while daily-arxiv still lacks semantic, side-effect delivery, and Review LLM proof. |

## Phase 19 Daily Side-Effect Execution Proof Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: when `$daily-arxiv` reaches its final provider-delivery boundary
through verified digest delivery or approved auto-ingest/fan-in, attach
`side_effect_execution_evidence`.

Non-goal: do not mark side-effect execution from approval-only or
provider-source-only evidence, and do not mark Review LLM or semantic parity
complete.

### Daily Side-Effect Execution Proof Result

| Check | Status | Evidence |
|---|---|---|
| Side-effect proof artifact | ok | `$daily-arxiv --write` now emits `daily_arxiv_prepare_finalize_side_effect_execution_runtime_proof.json` only when `final_provider_delivery_boundary.final_delivery_ready=true`. |
| False-positive guard | ok | Runtime digest without delivery/fan-in remains provider-ready only and does not emit `side_effect_runtime_proof_manifest_json`. |
| Boundary honesty | ok | Proof category is limited to `side_effect_execution_evidence`; approval, provider source, wiki mutation, Review LLM, and semantic parity remain separate requirements. |
| Regression tests | ok | Daily verified digest/write fan-in targeted tests: 2 passed; `py_compile` passed. |
| Real CLI smoke | ok | `codex-daily-fanin-proof-check` produced side-effect proof while preserving gated/inconclusive run status. |
| Parity inventory recognition | ok | `codex-daily-side-effect-proof-inventory.json` marks `daily-arxiv.side_effect_execution_evidence=supplied`; ordinary gate passed. |
| Full parity claim | warn | Strict full-parity gate still fails; daily-arxiv still lacks semantic equivalence and Review LLM/model evidence. |

## Phase 19 Daily Review LLM Runtime Proof Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: when `$daily-arxiv` receives completed Review LLM digest-selection
evidence, attach a `review_llm_or_model_evidence` runtime proof.

Non-goal: do not mark semantic equivalence, delivery, provider source, or wiki
mutation complete from Review LLM evidence alone.

### Daily Review LLM Runtime Proof Result

| Check | Status | Evidence |
|---|---|---|
| CLI argument propagation | ok | `$daily-arxiv` now forwards `--review-llm-evidence` and related Review LLM flags into `daily_arxiv_prepare_finalize`. |
| Review proof artifact | ok | Completed Review LLM digest-selection evidence emits `daily_arxiv_prepare_finalize_review_llm_runtime_proof.json`. |
| False-positive guard | ok | Daily runtime without Review LLM evidence records `review_llm_completed=false` and does not emit `review_model_runtime_proof_manifest_json`. |
| Boundary honesty | ok | Review proof only satisfies `review_llm_or_model_evidence`; semantic equivalence and other runtime boundaries remain independently gated. |
| Regression tests | ok | Daily verified digest/write fan-in targeted tests: 2 passed; `py_compile` passed for `autosci_bridge.py` and `autosci_skill_shim.py`. |
| Real CLI smoke | ok | `codex-daily-fanin-proof-check` with `daily-review-llm.json` attached Review LLM proof while preserving gated/inconclusive status. |
| Parity inventory recognition | ok | `codex-daily-review-proof-inventory.json` marks `daily-arxiv.review_llm_or_model_evidence=supplied` and `runtime_proof_status=verified`; ordinary gate passed. |
| Full parity claim | warn | Strict full-parity gate still fails; daily-arxiv now only lacks `semantic_equivalence_evidence`, while many other routes still have unresolved requirements. |

## Phase 19 Verified Semantic Audit Promotion Gate

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_parity_bridge.py`
- `harness/plugins/autosci/tests/test_phase19_parity_bridge.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: promote a route to `semantic_parity=full` only when supplied runtime
proof references a completed, full, skill-matching
`autosci_semantic_parity_audit.v1` with passing acceptance checks.

Non-goal: do not promote semantic parity from proof category presence alone,
and do not change route coverage/runtime status without the corresponding
runtime proof requirements.

### Verified Semantic Audit Promotion Gate Result

| Check | Status | Evidence |
|---|---|---|
| Strict promotion rule | ok | Inventory now promotes `semantic_parity=full` only from supplied `semantic_audit` proof that references a valid completed/full skill-matching `autosci_semantic_parity_audit.v1`. |
| False-positive guard | ok | Existing incomplete semantic proof test still marks `semantic_equivalence_evidence=supplied` without promoting semantic parity. |
| Proof-level consistency | ok | Verified semantic audit promotion raises proof level to at least `E3`, satisfying ordinary gate consistency for `semantic_parity=full`. |
| Requirement consistency | ok | Promoted routes retain `semantic_equivalence_evidence=supplied` in `proof_requirements`, so runtime proof source categories remain declared. |
| Regression tests | ok | `test_phase19_parity_bridge.py`: 11 passed; `test_semantic_parity_runtime_proof.py`: 2 passed; `py_compile` passed. |
| Real inventory guard | ok | Existing `codex-daily-review-proof-inventory.json` remains `daily-arxiv.semantic_parity=partial` and `semantic_full_count=0` because no semantic audit was supplied; ordinary gate passed. |
| Full parity claim | warn | This enables audited semantic promotion but does not itself produce route-specific semantic audits or clear route coverage/runtime blockers. |

## Phase 19 Daily Native Tool Parity Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `tools/daily_arxiv.py`
- `tools/fetch_arxiv.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: replace the Solar daily-arxiv stub with the original AutoSci helper
behavior for config, prepare, finalize, recommend-llm, and digest support, and
include the missing arXiv fetch helper required by prepare.

Non-goal: do not execute network fetches, SMTP delivery, scheduling, or
auto-ingest during verification without explicit approved runtime evidence.

### Daily Native Tool Parity Result

| Check | Status | Evidence |
|---|---|---|
| Tool sync | ok | `tools/daily_arxiv.py` was mechanically synchronized from the corrected original AutoSci repo, replacing the 57-line approval stub with the full helper. |
| Missing dependency | ok | Added `tools/fetch_arxiv.py`, the direct arXiv feed helper imported by the native daily tool. |
| Byte comparison | ok | `cmp -s` confirms OpenSolar `tools/daily_arxiv.py` and `tools/fetch_arxiv.py` match the original AutoSci files. |
| Command ABI | ok | `tools/daily_arxiv.py --help` exposes `config`, `prepare`, `finalize`, `recommend-llm`, and `digest`. |
| Deterministic local smoke | ok | `config`, `prepare --feed --no-external`, `finalize`, and `digest` completed against `codex-daily-tool-parity-check` fixtures without network execution. |
| Regression tests | ok | Daily shim target tests: 2 passed; `py_compile` passed for `tools/daily_arxiv.py` and `tools/fetch_arxiv.py`. |
| Full parity claim | warn | This removes a native tool blocker for daily-arxiv, but semantic full parity still requires a route-specific audit covering the shim/bridge behavior and approval boundaries. |

## Phase 19 Daily Native Option ABI Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_skill_shim.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: accept and preserve native `/daily-arxiv` option inputs
(`--mode`, `--hours`, `--categories`, `--max-recommendations`,
`--max-auto-ingest`, `--send-email`) in the Solar shim and action envelope.

Non-goal: do not execute feed fetches, SMTP delivery, scheduler mutation, or
auto-ingest from options alone.

### Daily Native Option ABI Result

| Check | Status | Evidence |
|---|---|---|
| Parser ABI | ok | `$daily-arxiv` shim now accepts `--mode`, `--hours`, `--categories`, `--max-recommendations`, `--max-auto-ingest`, and `--send-email`. |
| Native option preservation | ok | `autosci_skill_run.inputs.native_options` records all daily native options. |
| Action envelope preservation | ok | `daily_arxiv_prepare_finalize` envelope inputs record mode/hours/categories/recommendation cap/auto-ingest cap/send-email; `--max-recommendations` overrides action `limit`. |
| Side-effect honesty | ok | Options alone do not execute feed fetches, SMTP, scheduler mutation, or auto-ingest; smoke remains `execution_status=gated`, `status=inconclusive`. |
| Regression tests | ok | Daily shim target tests: 2 passed; `py_compile` passed for `autosci_skill_shim.py`. |
| Real CLI smoke | ok | `codex-daily-option-abi-check` preserved all native options in run payload and action envelope. |
| Full parity claim | warn | Daily command submodes `setup/status/disable` still need native UX routing and evidence boundaries before daily semantic audit can be full. |

## Phase 19 Daily Management Subcommand Routing

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_skill_shim.py`
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: route native `/daily-arxiv setup|status|disable` subcommands through
Solar evidence instead of treating them as recommendation query text.

Non-goal: do not mutate `.github/workflows`, config files, secrets, scheduler
state, or SMTP settings without a separate approved execution path.

### Daily Management Subcommand Routing Result

| Check | Status | Evidence |
|---|---|---|
| Subcommand detection | ok | First positional `setup`, `status`, or `disable` is now recorded as `daily_command` instead of recommendation query text. |
| Evidence boundary | ok | Management subcommands return `workflow_evolution.v1` evidence from `daily_arxiv_prepare_finalize`, including recommended changes and patch candidates artifacts required by the gate. |
| Protected mutation honesty | ok | `setup` and `disable` remain gated/proposed and do not mutate config, workflow, secrets, scheduler state, SMTP, or wiki files. |
| Read-only status | ok | `status` returns completed workflow evidence while still preserving route-level `execution_status=gated` because the daily route is approval-required. |
| Regression tests | ok | Daily management/default route target tests: 5 passed; `py_compile` passed for `autosci_bridge.py` and `autosci_skill_shim.py`. |
| Real CLI smoke | ok | `codex-daily-management-setup-check`, `codex-daily-management-status-check`, and `codex-daily-management-disable-check` all completed without failed actions. |
| Full parity claim | warn | Native management UX is now routed, but actual approved setup/disable mutation and scheduler/secret probes are still future side-effect execution blockers. |

## Phase 19 Discover Native Tool Parity Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `tools/discover.py`
- `tools/_env.py`
- `tools/fetch_s2.py`
- `tools/fetch_deepxiv.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: replace the lightweight Solar discover wrapper with the original
AutoSci discovery helper while preserving OpenSolar provider-proof CLI behavior
in `fetch_s2.py` and `fetch_deepxiv.py`.

Non-goal: do not run live Semantic Scholar, DeepXiv, Paper Copilot, or network
venue fetches during verification.

### Discover Native Tool Parity Result

| Check | Status | Evidence |
|---|---|---|
| Native helper sync | ok | `tools/discover.py` was replaced with the corrected original AutoSci discovery helper, then locally patched only for OpenSolar no-network compatibility flags. |
| Environment helper sync | ok | `tools/_env.py` matches the corrected original AutoSci helper byte-for-byte. |
| Provider API preservation | ok | `tools/fetch_s2.py` and `tools/fetch_deepxiv.py` now expose the native import-time discovery functions required by `discover.py` while preserving existing provider-proof CLI behavior. |
| No-network boundary | ok | `AUTOSCI_DISABLE_NETWORK_FETCH=1 tools/discover.py from-wiki ... --no-network-fetch` returns an inconclusive compatibility payload with wiki anchors and no provider request. |
| CLI ABI | ok | `tools/discover.py --help` exposes native `from-anchors`, `from-topic`, `from-wiki`, and `from-venue` subcommands. |
| Regression tests | ok | `test_source_cli_tools.py`: 7 passed; `py_compile` passed for `discover.py`, `_env.py`, `fetch_s2.py`, and `fetch_deepxiv.py`. |
| Full parity claim | warn | Discover now has the native helper surface, but live provider proof and semantic parity still require approved network-backed runs and route-level evidence promotion. |

## Phase 19 Review LLM Runtime Proof Attachment Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: when `$review` obtains completed Review LLM evidence through supplied
evidence, command bridge, or provider mode, attach an `autosci_runtime_proof_manifest.v1`
with `review_llm_or_model_evidence` so parity inventory can see the proof.

Non-goal: do not treat local surrogate review or missing artifacts as final
acceptance/runtime proof.

### Review LLM Runtime Proof Attachment Result

| Check | Status | Evidence |
|---|---|---|
| Runtime proof sidecar | ok | Completed Review LLM-backed `$review` evidence now emits `review_llm_runtime_proof.json` with `schema=autosci_runtime_proof_manifest.v1` and `categories=["review_llm_or_model_evidence"]`. |
| Surrogate boundary | ok | Local surrogate review still emits no runtime proof and remains `review_llm_incomplete`. |
| Regression tests | ok | Review shim subset: 4 passed; `test_review_model_runtime_proof.py`: 4 passed; `py_compile` passed. |
| Real CLI smoke | ok | `$review ... --review-llm-command ... --run-id codex-review-proof-check-quoted` passed with `passed_count=1` and attached `review_model_runtime_proof_manifest_json`. |
| Parity inventory recognition | ok | `autosci_parity_bridge.py inventory --runtime-proof-dir artifacts/autosci/runs/codex-review-proof-check-quoted` reports runtime proof counts `not_required=3 / pending=24 / supplied=1 / verified=0`; review route has `review_llm_or_model_evidence=supplied`. |
| Full parity claim | warn | Review route still lacks semantic equivalence proof, external/provider source evidence, verified runtime status, and promotion-safe `coverage_status=full`; strict full-parity gate still fails as expected. |

## Phase 19 Review Provider Runtime Proof Categories Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: when `$review` completes through a live OpenAI-compatible provider,
mark the runtime proof as Review LLM, external runtime, and provider source
evidence; keep command/supplied evidence limited to Review LLM proof only.

Non-goal: do not mark provider/source proof for local surrogate, supplied
artifact evidence, or command-only review bridges.

### Review Provider Runtime Proof Categories Result

| Check | Status | Evidence |
|---|---|---|
| Provider categories | ok | Live provider `$review` runtime proof now emits `review_llm_or_model_evidence`, `external_runtime_evidence`, and `provider_source_evidence`. |
| Command/evidence boundary | ok | Command bridge and supplied artifact evidence remain `collection_mode=manual_review` and only satisfy Review LLM proof, not provider/source proof. |
| Regression tests | ok | Provider/command/supplied review tests: 3 passed after escalated local HTTP bind; `py_compile` passed. |
| Gate compatibility | ok | Ordinary feature parity gate still passes current inventory; strict full-parity gate remains blocked on semantic and route-wide unresolved proofs. |
| Full parity claim | warn | Provider category mapping is now representable for review, but a persisted provider-run proof must still be collected and attached before review can become verified/full. |

## Phase 19 Init Discovery Native Tool Parity Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `tools/init_discovery.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: replace the lightweight Solar init-discovery wrapper with the corrected
original AutoSci source preparation and discovery planner while preserving the
OpenSolar no-network root-tool ABI used by safety smoke tests.

Non-goal: do not run live source downloads, Semantic Scholar, DeepXiv, or arXiv
network fetches during verification.

### Init Discovery Native Tool Parity Result

| Check | Status | Evidence |
|---|---|---|
| Native helper sync | ok | `tools/init_discovery.py` now carries the corrected original AutoSci prepare/plan/fetch/download implementation surface. |
| OpenSolar ABI compatibility | ok | Legacy `plan <topic> --no-network-fetch` emits `autosci_init_discovery_cli.v1` with a nested native plan and explicit no-network limitations. |
| Native CLI path | ok | Native `plan --topic ... --allow-introduction false` emits the original AutoSci plan shape without the compatibility wrapper. |
| Import compatibility | ok | Added a local `slugify` fallback because current Solar `tools/research_wiki.py` has not yet been fully synced with original AutoSci. |
| Verification | ok | `py_compile` passed; no-network compatibility smoke passed; native no-introduction plan smoke passed; `--help` exposes `prepare`, `plan`, `fetch`, and `download`. |
| Follow-up blocker | warn | Full root-tool ABI smoke now reaches an unrelated daily blocker: original `daily_arxiv.py prepare` requires `--out`, while the OpenSolar smoke still calls `prepare --topic` without `--out`. |
| Full parity claim | warn | Init discovery helper parity improved, but full init parity still needs approved live provider/source runs, wiki mutation proof, and semantic parity promotion. |

## Phase 19 Daily Prepare Root ABI Compatibility

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `tools/daily_arxiv.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: preserve the corrected original AutoSci daily helper while restoring
the OpenSolar non-mutating root-tool ABI for `daily_arxiv.py prepare --topic`
without a mandatory `--out` path.

Non-goal: do not auto-ingest, send email, mutate wiki state, or run external
provider fetches from the compatibility path.

### Daily Prepare Root ABI Compatibility Result

| Check | Status | Evidence |
|---|---|---|
| Compatibility path | ok | `daily_arxiv.py prepare --topic ...` without `--out` now emits `autosci_daily_arxiv_cli.v1` JSON and performs no feed/provider/email/wiki side effects. |
| Native path preservation | ok | The original `prepare --out ...` path remains the context-writing recommendation preparation path. |
| Regression tests | ok | Daily shim digest/write/management subset: 5 passed; `py_compile` passed for `tools/daily_arxiv.py`. |
| Root-tool ABI | ok | `test_root_tool_abi.py`: 5 passed after escalated local SMTP bind; sandbox-only bind denial was the only non-code failure before escalation. |
| Full parity claim | warn | Daily root ABI is restored, but full daily parity still requires approved live feed/provider runs, approved write/notification side effects, and semantic audit promotion. |

## Phase 19 Research Wiki Native Runtime Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `runtime/__init__.py`
- `runtime/loader.py`
- `runtime/policy/writers.yaml`
- `runtime/schema/conventions.yaml`
- `runtime/schema/edges.yaml`
- `runtime/schema/entities.yaml`
- `runtime/schema/xref.yaml`
- `tools/research_wiki.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: restore the corrected original AutoSci wiki/runtime schema layer so
native wiki operations have the same entity, edge, slug, checkpoint, rebuild,
query, and lifecycle command surface.

Non-goal: do not relax Solar's existing `--wiki-root --json` smoke ABI; keep
that as an explicit compatibility pre-parser instead of changing original
AutoSci command semantics.

### Research Wiki Native Runtime Sync Result

| Check | Status | Evidence |
|---|---|---|
| Runtime schema sync | ok | Added original AutoSci `runtime/loader.py`, schema YAML, and writer policy files needed by native wiki, lint, visualize, reset, and serve helpers. |
| Native wiki helper sync | ok | `tools/research_wiki.py` now exposes original AutoSci commands including `init`, `slug`, `add-edge`, `add-citation`, rebuilds, stats, maturity, query, neighbors, lifecycle transitions, and checkpoint operations. |
| OpenSolar ABI preservation | ok | Added a pre-parser for existing `--wiki-root --json` smoke commands: `set-meta`, `add-edge`, `log`, `rebuild`, `query`, `neighbors`, `resolve`, and `stats`. |
| Init import cleanup | ok | `tools/init_discovery.py` now imports native `research_wiki.slugify` instead of relying on its fallback path. |
| Regression tests | ok | `test_research_wiki_tool.py`: 1 passed; `py_compile` passed for `runtime/loader.py`, `tools/research_wiki.py`, and `tools/init_discovery.py`. |
| Native smoke | ok | `research_wiki.py init <tmp-wiki>`, `research_wiki.py stats <tmp-wiki> --json`, and `research_wiki.py slug ...` completed with native runtime schema loaded. |
| Full parity claim | warn | Wiki runtime command surface is restored, but route-level full parity still needs each workflow to attach approved mutation/rebuild proof and semantic audits. |

## Phase 19 Visualize Native Tool Parity Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `tools/visualize.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: replace the lightweight Solar visualize helper with the corrected
original AutoSci visualization generator while preserving the JSON stdout ABI
used by Solar bridge calls and `tools/serve.py`.

Non-goal: do not start a local web server or run approved browser/render
side effects from this helper sync.

### Visualize Native Tool Parity Result

| Check | Status | Evidence |
|---|---|---|
| Native helper sync | ok | `tools/visualize.py` now carries the corrected original AutoSci visualization generator and uses the restored `runtime.loader` schema. |
| Bridge JSON ABI | ok | Preserved `generate-obsidian-config --wiki-root --out`, `generate-canvas --wiki-root --graph-out --out`, and `graph-data --wiki-root --out` JSON stdout paths used by Solar bridge. |
| Serve import ABI | ok | Restored `default_wiki_root`, `graph_data`, and `write_json` exports required by `tools/serve.py`. |
| Native CLI smoke | ok | `list-recommendations` completed with the original AutoSci visualization guidance. |
| Regression tests | ok | `py_compile` passed for `visualize.py` and `serve.py`; `$visualize --serve` shim regression: 1 passed; bridge JSON CLI smokes produced graph/config/canvas artifacts. |
| Full parity claim | warn | Visualization helper parity improved, but full route parity still needs approved web-server/browser-render proof and semantic audit promotion. |

## Phase 19 Remote Native Command ABI Gate

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `tools/remote.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: add the corrected original AutoSci remote command surface
(`status`, `gpu-status`, `sync-code`, `setup-env`, `tail-log`) to the
OpenSolar remote helper while preserving approval-gated execution boundaries.

Non-goal: do not run SSH, rsync, screen, remote package installation, or log
tail commands without explicit approval and an allowlisted execution command.

### Remote Native Command ABI Gate Result

| Check | Status | Evidence |
|---|---|---|
| Native command surface | ok | `remote.py` now accepts original AutoSci remote command names: `status`, `gpu-status`, `sync-code`, `setup-env`, and `tail-log`. |
| Approval boundary | ok | Each new command returns `autosci_remote_cli.v1` with `status=approval_required` and explicit side-effect categories when no approval is supplied. |
| Existing executable paths | ok | Existing approved `launch --command`, `check --status-command`, and `pull-results --pull-command` paths remain the only executable remote proof surfaces. |
| Regression tests | ok | `py_compile` passed; root approved remote launch plus exp-run/exp-status/exp-collect remote helper subset: 4 passed. |
| CLI smokes | ok | `status`, `gpu-status`, `sync-code --dry-run`, `setup-env --requirements ...`, and `tail-log --name ...` all returned structured approval-required evidence. |
| Full parity claim | warn | Remote ABI is broader, but full exp-run parity still requires approved deploy/monitor/collect TaskGraph evidence, live remote proofs, and semantic audit promotion. |

## Phase 19 Wiki Lint Native Tool Parity Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `tools/lint.py`
- `harness/plugins/autosci/tests/test_root_tool_abi.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: replace the lightweight Solar wiki lint helper with the corrected
original AutoSci schema-driven linter while preserving the OpenSolar
`--wiki-root` JSON smoke ABI.

Non-goal: do not auto-fix wiki files unless `--fix` is explicitly requested by
the caller; smoke validation remains read-only.

### Wiki Lint Native Tool Parity Result

| Check | Status | Evidence |
|---|---|---|
| Native linter sync | ok | `tools/lint.py` now carries the corrected original AutoSci schema-driven linter backed by `runtime.loader`. |
| OpenSolar ABI preservation | ok | `--wiki-root` is accepted as an alias and emits `autosci_wiki_lint_cli.v1` with page/edge counts and normalized severities. |
| Strictness honesty | ok | Invalid or incomplete wiki pages now fail under the compatibility wrapper instead of being reported as ok; the root smoke fixture was updated to use minimal valid idea frontmatter. |
| Regression tests | ok | `py_compile` passed; root lint smoke passed; full `test_root_tool_abi.py` passed after escalated local SMTP bind. |
| Full parity claim | warn | Lint/check quality is now closer to native AutoSci, but route-level full parity still requires check outputs to attach semantic audit and wiki-state evidence where applicable. |

## Phase 19 Prepare Paper Source Native Tool Parity Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `tools/prepare_paper_source.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: replace the lightweight Solar paper-source preparation wrapper with
the corrected original AutoSci source normalizer used by `init_discovery.py`
while preserving OpenSolar's structured CLI evidence ABI.

Non-goal: do not force network metadata recovery during tests; no-network
smokes must remain provider-safe.

### Prepare Paper Source Native Tool Parity Result

| Check | Status | Evidence |
|---|---|---|
| Native helper sync | ok | `tools/prepare_paper_source.py` now carries the corrected original AutoSci local paper/source normalizer used by `init_discovery.py`. |
| OpenSolar CLI ABI | ok | CLI accepts both original `--source` and Solar positional source forms, plus `--workspace-root`, `--repository-root`, and `--no-network-fetch`. |
| External source handling | ok | Positional sources outside `raw_root` are copied into `raw/input/` before calling the native normalizer, preserving current Solar CLI behavior. |
| Structured evidence | ok | Success and failure paths emit `autosci_prepare_paper_source_cli.v1`; native `usable` is mapped to `status=completed`. |
| Regression tests | ok | `test_source_cli_tools.py`: 7 passed; `py_compile` passed for `prepare_paper_source.py` and `init_discovery.py`; `init_discovery.py prepare` smoke completed. |
| Full parity claim | warn | Source preparation is closer to native AutoSci, but full ingest/init parity still requires live source-provider proof, wiki writeback proof, and semantic audit promotion. |

## Phase 19 Rasterize LaTeX Native API Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `tools/rasterize_latex.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: restore the original AutoSci `RasterizeError` and
`rasterize_latex_snippet` API required by native `wiki2dag.py`, while keeping
OpenSolar structured diagnostic CLI commands.

Non-goal: do not require TeX/PDF tools to be installed for smoke tests; missing
rendering binaries must report diagnostics instead of pretending success.

### Rasterize LaTeX Native API Result

| Check | Status | Evidence |
|---|---|---|
| Native API sync | ok | `tools/rasterize_latex.py` now exposes original AutoSci `RasterizeError`, `extract_tikz_setup`, and `rasterize_latex_snippet` APIs required by native `wiki2dag.py`. |
| Structured diagnostics | ok | Preserved OpenSolar `diagnose`, `check-pdf`, and `rasterize` subcommands with `autosci_rasterize_latex_cli.v1` JSON output. |
| Tool availability honesty | ok | `diagnose` reports actual local tool paths/nulls; it does not mark missing `latexmk` or `gs` as installed. |
| Regression tests | ok | `py_compile` passed; API import check returned both required symbols; root-tool smoke for `rasterize_latex.py diagnose` passed. |
| Full parity claim | warn | Rasterizer API is restored, but full poster/paper parity still depends on native `wiki2dag`, poster build stages, and verified PDF/render gates. |

## Phase 19 Wiki2DAG Native Tool Parity Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `tools/wiki2dag.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: restore the corrected original AutoSci/PaperX-compatible
LaTeX-to-DAG builder while preserving the OpenSolar lightweight wiki DAG
smoke command.

Non-goal: do not require a real LaTeX paper fixture for the wiki smoke path;
native paper-dir DAG generation will be verified with CLI/API availability and
kept separate from the compatibility path.

### Wiki2DAG Native Tool Parity Result

| Check | Status | Evidence |
|---|---|---|
| Native helper sync | ok | `tools/wiki2dag.py` now carries the corrected original PaperX-compatible LaTeX paper-dir DAG builder. |
| Rasterizer dependency | ok | Native `wiki2dag.py` can import the restored `rasterize_latex` API. |
| OpenSolar wiki ABI | ok | `build --wiki-root ... --out ...` still emits `autosci_wiki_dag.v1` for lightweight wiki smoke checks. |
| Native CLI surface | ok | `wiki2dag.py build --help` exposes original `--paper-dir`, `--output`, `--anonymous`, and `--citations` options. |
| Regression tests | ok | `py_compile` passed for `wiki2dag.py` and `rasterize_latex.py`; root-tool wiki DAG smoke passed. |
| Full parity claim | warn | DAG generation surface is restored, but full publication parity still needs real LaTeX paper fixtures, poster build/inject stages, PDF compile gates, and semantic audit promotion. |

## Phase 19 Ask/Check Model Runtime Proof Attachment Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: when `$ask` or `$check` obtains completed `autosci_model_response.v1`
evidence through supplied evidence or a model command bridge, attach an
`autosci_runtime_proof_manifest.v1` for `review_llm_or_model_evidence`.

Non-goal: do not mark missing model output, local deterministic structure
checks, or command failures as runtime proof.

### Ask/Check Model Runtime Proof Attachment Result

| Check | Status | Evidence |
|---|---|---|
| Ask model proof | ok | `$ask --model-command` now emits `ask_wiki_model_runtime_proof.json`; parity inventory marks `ask.review_llm_or_model_evidence=supplied`. |
| Check model proof | ok | `$check --model-command` now emits `check_wiki_health_model_runtime_proof.json`; parity inventory marks `check.review_llm_or_model_evidence=supplied` while route runtime status remains `not_required`. |
| Surrogate/missing boundary | ok | No proof is emitted unless `model_output.status=completed` and model evidence ids are present. |
| Regression tests | ok | Ask/check model-command tests: 2 passed; review/model proof writer tests: 4 passed; `py_compile` passed. |
| Real CLI smoke | ok | `codex-ask-model-proof-check` and `codex-check-model-proof-check` produced model proof manifests with valid local evidence refs. |
| Feature gate | ok | Inventory with the two proof dirs passes the ordinary feature parity gate. |
| Full parity claim | warn | Ask/check still need semantic equivalence proof; ask also still needs external/provider source evidence before full parity can be considered. |

## Phase 19 Ideate Model Runtime Proof Attachment Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: when `$ideate` obtains completed `autosci_model_response.v1`
brainstorm evidence through a model command, attach an
`autosci_runtime_proof_manifest.v1` for `review_llm_or_model_evidence`.

Non-goal: do not mark ideation source evidence, novelty/review gates, wiki
mutation, or semantic parity as complete from model brainstorm evidence alone.

### Ideate Model Runtime Proof Attachment Result

| Check | Status | Evidence |
|---|---|---|
| Model brainstorm proof | ok | `$ideate --model-command` now emits `generate_ideas_model_runtime_proof.json` when completed model output contains usable ideas and evidence ids. |
| Boundary honesty | ok | The ideate final promotion boundary remains incomplete unless source evidence, novelty/review gates, wiki scan, and failed-idea banlist requirements are met. |
| Regression tests | ok | Ideate/ask/check model-command tests: 3 passed; `py_compile` passed. |
| Real CLI smoke | ok | `codex-ideate-model-proof-check` produced `passed_count=2` and a model proof manifest with local evidence refs. |
| Parity inventory recognition | ok | `autosci_parity_bridge.py inventory --runtime-proof-dir artifacts/autosci/runs/codex-ideate-model-proof-check` marks `ideate.review_llm_or_model_evidence=supplied`. |
| Full parity claim | warn | Ideate still needs semantic equivalence proof, live/source provider evidence, external runtime proof, novelty/review gate evidence, and approved wiki mutation proof. |

## Phase 19 Experiment Design Review Runtime Proof Attachment Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: when `$exp-design` receives completed Review LLM design validation
evidence, attach an `autosci_runtime_proof_manifest.v1` for
`review_llm_or_model_evidence`.

Non-goal: do not mark experiment execution, approval preflight, external
runtime, or semantic parity complete from design-review evidence alone.

### Experiment Design Review Runtime Proof Attachment Result

| Check | Status | Evidence |
|---|---|---|
| Review proof artifact | ok | `$exp-design --review-llm-evidence` now emits `design_experiment_review_llm_runtime_proof.json` when supplied Review LLM evidence is completed. |
| Boundary honesty | ok | Experiment execution boundary remains incomplete without approval preflight/runtime execution even when design review is complete. |
| Regression tests | ok | Exp-design/ideate/ask/check targeted tests: 4 passed; `py_compile` passed. |
| Real CLI smoke | ok | `codex-exp-design-review-proof-check` passed and attached a proof manifest referencing `experiment_plan.json` plus the source review artifact. |
| Parity inventory recognition | ok | Inventory with the exp-design proof dir marks `exp-design.review_llm_or_model_evidence=supplied`; route runtime status remains `not_required`. |
| Full parity claim | warn | Exp-design still needs semantic equivalence proof before it can move toward full parity; experiment execution proof belongs to exp-run/exp-pilot-run, not design. |

## Phase 19 Paper Plan Review Runtime Proof Attachment Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: when `$paper-plan` receives completed Review LLM boundary evidence,
attach an `autosci_runtime_proof_manifest.v1` for
`review_llm_or_model_evidence`.

Non-goal: do not mark source coverage, compile/PDF handoff, external runtime,
or final plan acceptance complete from Review LLM evidence alone.

### Paper Plan Review Runtime Proof Attachment Result

| Check | Status | Evidence |
|---|---|---|
| Review proof artifact | ok | `$paper-plan --review-llm-evidence` now emits `plan_report_review_llm_runtime_proof.json` when review boundary evidence is completed. |
| Boundary honesty | ok | Paper plan remains `schema_only`/inconclusive without source coverage and verified compile/PDF handoff, even with Review LLM proof. |
| Regression tests | ok | Paper-plan and exp-design review targeted tests: 2 passed; `py_compile` passed. |
| Real CLI smoke | ok | `codex-paper-plan-review-proof-check` attached a proof manifest referencing `scientific_report.plan.json`. |
| Parity inventory recognition | ok | Inventory with the paper-plan proof dir marks `paper-plan.review_llm_or_model_evidence=supplied`; external/source/semantic requirements remain pending. |
| Full parity claim | warn | Paper-plan still needs semantic proof, source/provider proof, external runtime proof, and verified compile/PDF handoff before full parity. |

## Phase 19 Paper Draft Review Runtime Proof Attachment Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: when `$paper-draft` receives completed Review LLM boundary evidence,
attach an `autosci_runtime_proof_manifest.v1` for
`review_llm_or_model_evidence`.

Non-goal: do not mark source coverage, compile/PDF handoff, final manuscript
readiness, or semantic parity complete from Review LLM evidence alone.

### Paper Draft Review Runtime Proof Attachment Result

| Check | Status | Evidence |
|---|---|---|
| Review proof artifact | ok | `$paper-draft --review-llm-evidence` now emits `write_report_review_llm_runtime_proof.json` when review boundary evidence is completed. |
| Boundary honesty | ok | Paper draft remains schema-only/inconclusive without source coverage, wiki mutation proof, and verified compile/PDF handoff. |
| Regression tests | ok | Paper-draft compile handoff and paper-plan review targeted tests: 2 passed; `py_compile` passed. |
| Real CLI smoke | ok | `codex-paper-draft-review-proof-check` attached a proof manifest referencing `scientific_report.json`. |
| Parity inventory recognition | ok | Inventory with the paper-draft proof dir marks `paper-draft.review_llm_or_model_evidence=supplied`; source/external/wiki/semantic requirements remain pending. |
| Full parity claim | warn | Paper-draft still needs semantic proof, provider/source proof, external runtime proof, wiki mutation proof, and verified compile/PDF handoff before full parity. |

## Phase 19 Rebuttal Review Runtime Proof Attachment Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: when `$rebuttal` receives completed Review LLM reviewer-comment
evidence, attach an `autosci_runtime_proof_manifest.v1` for
`review_llm_or_model_evidence`.

Non-goal: do not mark rebuttal submission readiness, external runtime, or
semantic parity complete from mapped reviewer comments alone.

### Rebuttal Review Runtime Proof Attachment Result

| Check | Status | Evidence |
|---|---|---|
| Review proof artifact | ok | `$rebuttal --review-llm-evidence` now emits `draft_rebuttal_review_llm_runtime_proof.json` when supplied Review LLM evidence is completed. |
| Boundary honesty | ok | Rebuttal can remain schema-only/inconclusive when supplied review evidence lacks structured concerns; proof only satisfies Review LLM evidence presence. |
| Regression tests | ok | Rebuttal/paper-draft/paper-plan targeted tests: 3 passed; `py_compile` passed. |
| Real CLI smoke | ok | `codex-rebuttal-review-proof-check` attached a proof manifest referencing `publication_bundle.rebuttal.json`. |
| Parity inventory recognition | ok | Inventory with the rebuttal proof dir marks `rebuttal.review_llm_or_model_evidence=supplied`; external runtime and semantic requirements remain pending. |
| Full parity claim | warn | Rebuttal still needs semantic proof and external runtime/submission-readiness evidence before full parity. |

## Phase 19 Experiment Evaluation Review Runtime Proof Attachment Sync

Logged: 2026-06-29 EDT

Planned file changes (pre-fix):
- `harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/plugins/autosci/tests/test_autosci_skill_shim.py`
- `docs/integrations/autosci/phase19-progress-log.md`

Intent: when `$exp-eval` receives completed Review LLM evidence for claim
verification, attach an `autosci_runtime_proof_manifest.v1` for
`review_llm_or_model_evidence`.

Non-goal: do not mark experiment result readiness, code evidence, wiki
writeback, external runtime, or semantic parity complete from Review LLM proof.

### Experiment Evaluation Review Runtime Proof Attachment Result

| Check | Status | Evidence |
|---|---|---|
| Review proof artifact | ok | `$exp-eval --review-llm-evidence` now emits `verify_claim_review_llm_runtime_proof.json` when supplied Review LLM evidence is completed. |
| Verdict honesty | ok | Final verdict boundary still requires experiment result, claim/code linkage, approved wiki writeback, and runtime/approval evidence before final readiness. |
| Regression tests | ok | Exp-eval/rebuttal/exp-design targeted tests: 3 passed; `py_compile` passed. |
| Real CLI smoke | ok | `codex-exp-eval-review-proof-check` passed/gated and attached a proof manifest referencing `claim_verdict.json` plus the source review artifact. |
| Parity inventory recognition | ok | Inventory with the exp-eval proof dir marks `exp-eval.review_llm_or_model_evidence=supplied`; runtime/approval/wiki/semantic requirements remain pending. |
| Full parity claim | warn | Exp-eval still needs semantic proof, external runtime proof, approval boundary proof, and approved wiki mutation proof before full parity. |

### Visualize Serve Flag CLI Result

| Check | Status | Evidence |
|---|---|---|
| CLI compatibility | ok | `$visualize --serve` is now accepted and records `native_options.serve=true` plus `inputs.serve_requested=true`. |
| Side-effect boundary | ok | Without `--execute-approved` and approval/allowlist evidence, no long-lived server/web health execution occurs. |
| Local artifacts | ok | The visualize action still generates graph/canvas artifacts from local wiki state. |
| Regression tests | ok | Visualize serve flag target: 1 passed; visualize shim subset: 1 passed; `py_compile` passed. |
| Inventory/gate | ok | Real CLI smoke for `$visualize --serve` succeeds with gated/inconclusive status; route inventory and ordinary/strict gates remain honest. |
| Full parity claim | warn | Visualize CLI parity improved, but full visualize parity still requires approved web runtime proof, semantic audit, and final acceptance. |

## Phase 19 Latest Continuation EOF Marker

Logged: 2026-06-30 EDT

| Check | Status | Evidence |
|---|---|---|
| Latest inventory | warn | `current-parity-inventory-after-exp-run-paper-compile-proofs.json`: runtime counts `{not_required: 3, pending: 7, supplied: 9, verified: 9}`, `semantic_full_count=0`, `full_count=0`. |
| Provider-source blockers | ok | Pending `provider_source_evidence` count is `0`. |
| Verification | ok | Full shim suite 121 passed; parity/proof tests 21 passed; exp-run/collect/paper-compile subset 22 passed; `py_compile` and `git diff --check` passed. |
| Remaining blockers | warn | Full parity still requires semantic equivalence audits for all routes and runtime/approval/side-effect proof for the seven remaining pending side-effect routes. |

### Prefill Runtime Proof Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_bridge.py` | pending | Attach verified approval and side-effect runtime proof manifests to approved `$prefill` wiki writes without emitting undeclared provider-source or wiki-mutation categories. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Extend the approved `$prefill` regression test with allowlist/runtime/before/after artifacts and proof manifest assertions. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record implementation, verification, and refreshed inventory result for the `$prefill` parity blocker. |

### Prefill Runtime Proof Fix Result

| Check | Status | Evidence |
|---|---|---|
| Implementation | ok | Approved `$prefill` wiki writes now refresh an approval contract after the page exists, attach `approval_runtime_proof_manifest_json`, and attach `side_effect_runtime_proof_manifest_json`. |
| Category boundary | ok | `$prefill` proof generation explicitly suppresses undeclared `provider_source_evidence` and `wiki_mutation_evidence` categories. |
| Regression tests | ok | `pytest test_autosci_skill_shim.py -k prefill_applies_approved_wiki_mutation`: 1 passed; prefill/edit approved mutation subset: 2 passed; `py_compile` passed. |
| Real CLI smoke | ok | `$prefill foundation:skillgen-prefill-proof-20260630` with approval/allowlist/runtime/before/after evidence passed and generated verified proof manifests under `harness/artifacts/autosci/runs/codex-prefill-proof-check-20260630/`. |
| Parity inventory recognition | ok | `current-parity-inventory-after-prefill-proof.json` marks `$prefill.runtime_proof_status=verified`; runtime counts are `{not_required: 3, pending: 6, supplied: 9, verified: 10}`. |
| Remaining blocker | warn | Full parity still requires semantic equivalence audits for all 28 routes and runtime proof for `exp-pilot-eval`, `exp-pilot-run`, `poster`, `reset`, `setup`, and `visualize`. |

### Visualize Runtime Proof Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_bridge.py` | pending | Convert approved `$visualize --serve` health-check execution into approval and side-effect runtime proof manifests without changing unapproved serve behavior. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Add approved `$visualize --serve` regression coverage with allowlist/runtime/before/after artifacts and proof category assertions. |
| `harness/artifacts/autosci/runs/codex-visualize-proof-check-20260630/` | pending | Persist real CLI smoke output for inventory scanning. |
| `harness/artifacts/autosci/phase19/current-parity-inventory-after-visualize-proof.json` | pending | Refresh parity inventory after the visualize proof. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record implementation, verification, inventory status, and remaining blockers. |

### Visualize Runtime Proof Fix Result

| Check | Status | Evidence |
|---|---|---|
| Implementation | ok | Approved `$visualize --serve` health-check execution now records health JSON as runtime/after evidence, refreshes the approval contract, and emits approval plus side-effect runtime proof manifests. |
| Unapproved behavior | ok | `$visualize --serve` without `--execute-approved` still does not run the web health side effect and emits no web health/proof artifact. |
| Category boundary | ok | `$visualize` proof manifests include only `external_runtime_evidence`, `approval_boundary_evidence`, and `side_effect_execution_evidence`; no provider-source or wiki-mutation category is emitted. |
| Regression tests | ok | Visualize serve/remaining gated subset: 3 passed; visualize/prefill/edit proof subset: 4 passed; `py_compile` and `git diff --check` passed. |
| Real CLI smoke | ok | `$visualize "autosci graph proof 20260630" --serve --execute-approved` passed and wrote proof artifacts under `harness/artifacts/autosci/runs/codex-visualize-proof-check-20260630/`. |
| Parity inventory recognition | ok | `current-parity-inventory-after-visualize-proof.json` marks `$visualize.runtime_proof_status=verified`; runtime counts are `{not_required: 3, pending: 5, supplied: 9, verified: 11}`. |
| Remaining blocker | warn | Full parity still requires semantic equivalence audits for all 28 routes and runtime proof for `exp-pilot-eval`, `exp-pilot-run`, `poster`, `reset`, and `setup`. |

### Poster Runtime Proof Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_bridge.py` | pending | Attach approval and side-effect runtime proof manifests when approved `$poster --render` execution verifies browser render, overflow probe, and PNG export. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Extend the approved poster executor regression test with proof manifest assertions and category boundary checks. |
| `harness/artifacts/autosci/runs/codex-poster-proof-check-20260630/` | pending | Persist real CLI smoke output with an approved fake renderer for inventory scanning. |
| `harness/artifacts/autosci/phase19/current-parity-inventory-after-poster-proof.json` | pending | Refresh parity inventory after the poster proof. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record implementation, verification, inventory status, and remaining blockers. |

### Poster Runtime Proof Fix Result

| Check | Status | Evidence |
|---|---|---|
| Implementation | ok | Verified approved `$poster --render` execution now emits approval and side-effect runtime proof manifests when browser render, overflow probe, and PNG export are confirmed by runtime evidence. |
| Category boundary | ok | `$poster` proof manifests include only `external_runtime_evidence`, `approval_boundary_evidence`, and `side_effect_execution_evidence`; no provider-source or wiki-mutation category is emitted. |
| Regression tests | ok | Poster native/render/executor subset: 3 passed; poster/visualize/prefill proof subset: 4 passed; `py_compile` and `git diff --check` passed. |
| Real CLI smoke | ok | `$poster report-proof-20260630 --render --execute-approved` ran a persisted fake renderer and generated proof artifacts under `harness/artifacts/autosci/runs/codex-poster-proof-check-20260630/`. |
| Parity inventory recognition | ok | `current-parity-inventory-after-poster-proof.json` marks `$poster.runtime_proof_status=verified`; runtime counts are `{not_required: 3, pending: 4, supplied: 9, verified: 12}`. |
| Remaining blocker | warn | Full parity still requires semantic equivalence audits for all 28 routes and runtime proof for `exp-pilot-eval`, `exp-pilot-run`, `reset`, and `setup`. |

### Setup Reset External Runtime Proof Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_bridge.py` | pending | Attach approval and side-effect runtime proof manifests for `$setup` and `$reset` only from explicit approved external runtime evidence; do not execute local config writes or destructive reset. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Add approved external-runtime regression coverage for `$setup` and `$reset` with proof category assertions. |
| `harness/artifacts/autosci/runs/codex-setup-proof-check-20260630/` | pending | Persist real CLI smoke output for `$setup` proof inventory scanning. |
| `harness/artifacts/autosci/runs/codex-reset-proof-check-20260630/` | pending | Persist real CLI smoke output for `$reset` proof inventory scanning. |
| `harness/artifacts/autosci/phase19/current-parity-inventory-after-setup-reset-proofs.json` | pending | Refresh parity inventory after setup/reset proofs. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record implementation, verification, inventory status, and remaining blockers. |

### Setup Reset External Runtime Proof Fix Result

| Check | Status | Evidence |
|---|---|---|
| Implementation | ok | `$setup` and `$reset` now attach approval and side-effect runtime proof manifests from explicit approved external runtime evidence while preserving proposal-only workflow-evolution schema fields. |
| Safety boundary | ok | The bridge does not write secrets, mutate persistent config, or execute destructive reset; proof is emitted only when `--execute-approved` plus approval/allowlist/runtime/before/after evidence are supplied. |
| Category boundary | ok | `$setup` and `$reset` proof manifests include only `external_runtime_evidence`, `approval_boundary_evidence`, and `side_effect_execution_evidence`. |
| Regression tests | ok | Setup/reset external runtime proof plus gated proposal subset: 4 passed; proof regression subset: 6 passed; `py_compile` and `git diff --check` passed. |
| Real CLI smoke | ok | `$setup autosci --execute-approved` and `$reset autosci --execute-approved` generated proof artifacts under `codex-setup-proof-check-20260630/` and `codex-reset-proof-check-20260630/`. |
| Parity inventory recognition | ok | `current-parity-inventory-after-setup-reset-proofs.json` marks `$setup` and `$reset` runtime proof `verified`; runtime counts are `{not_required: 3, pending: 2, supplied: 9, verified: 14}`. |
| Remaining blocker | warn | Full parity still requires semantic equivalence audits for all 28 routes and runtime/wiki proof for `exp-pilot-eval` and `exp-pilot-run`. |

### Pilot Runtime Wiki Proof Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_bridge.py` | pending | Attach runtime/approval/side-effect/wiki proof manifests for approved `$exp-pilot-run`, and runtime/approval/wiki proof manifests for approved `$exp-pilot-eval` writeback. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Extend pilot run/eval tests with approved proof assertions and wiki mutation category checks. |
| `harness/artifacts/autosci/runs/codex-pilot-run-proof-check-20260630/` | pending | Persist real CLI smoke output for `$exp-pilot-run` proof inventory scanning. |
| `harness/artifacts/autosci/runs/codex-pilot-eval-proof-check-20260630/` | pending | Persist real CLI smoke output for `$exp-pilot-eval` proof inventory scanning. |
| `harness/artifacts/autosci/phase19/current-parity-inventory-after-pilot-proofs.json` | pending | Refresh parity inventory after pilot proofs. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record implementation, verification, final runtime inventory status, and remaining semantic blockers. |

### Pilot Runtime Wiki Proof Fix Result

| Check | Status | Evidence |
|---|---|---|
| Implementation | ok | Approved `$exp-pilot-run` now writes pilot experiment wiki state and emits approval, side-effect, and wiki-mutation proof manifests; approved `$exp-pilot-eval --write` now emits approval and wiki-mutation proof manifests without emitting undeclared side-effect proof. |
| Category boundary | ok | `$exp-pilot-run` covers `external_runtime_evidence`, `approval_boundary_evidence`, `side_effect_execution_evidence`, and `wiki_mutation_evidence`; `$exp-pilot-eval` covers `external_runtime_evidence`, `approval_boundary_evidence`, and `wiki_mutation_evidence`. |
| Regression tests | ok | Pilot runtime/eval subset: 3 passed; broad proof subset: 8 passed; `py_compile` passed. |
| Real CLI smoke | ok | `$exp-pilot-run pilot-proof-20260630 --execute-approved` and `$exp-pilot-eval pilot-claim-proof-20260630 --write --execute-approved` generated proof artifacts under `codex-pilot-run-proof-check-20260630/` and `codex-pilot-eval-proof-check-20260630/`. |
| Parity inventory recognition | ok | `current-parity-inventory-after-pilot-proofs.json` marks `$exp-pilot-run` and `$exp-pilot-eval` runtime proof `verified`; runtime counts are `{not_required: 3, pending: 0, supplied: 9, verified: 16}`. |
| Remaining blocker | warn | Full parity is still blocked: semantic parity remains partial for all 28 routes, and detailed proof requirements still show non-semantic pending items for ask, exp-eval, ideate, ingest, novelty, paper-draft, paper-plan, rebuttal, review, and survey. |

### Model Review External Runtime Category Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_bridge.py` | pending | Add `external_runtime_evidence` to completed model/Review LLM proof manifests where the route already has explicit model/review evidence; do not change local fallback behavior. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Update model/review proof assertions and add coverage where needed for ask/review/rebuttal category boundaries. |
| `harness/artifacts/autosci/runs/` | pending | Regenerate affected route smoke artifacts so inventory scans updated proof manifests. |
| `harness/artifacts/autosci/phase19/current-parity-inventory-after-model-external-proofs.json` | pending | Refresh inventory after model/review external runtime proof categories. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record verification and remaining blockers. |

Interim check: the first regenerated ask/ideate model smoke did not emit
`*_model_runtime_proof.json` because the CLI smoke passed an unquoted
repository path containing spaces to `--model-command`; bridge behavior itself
still requires explicit completed model evidence with `evidence_ids`. Re-run the
smoke with `shlex`-quoted command parts before making any further product logic
changes.

### Model Review External Runtime Category Fix Result

| Check | Status | Evidence |
|---|---|---|
| Implementation | ok | Completed model/Review LLM proof manifests now include `external_runtime_evidence` alongside `review_llm_or_model_evidence` where explicit completed model/review evidence exists. |
| Product-logic boundary | ok | Local fallback behavior remains unchanged; failed, missing, or schema-incomplete model outputs still do not emit model runtime proof. |
| Smoke correction | ok | Ask/ideate proof smokes were regenerated with `shlex`-quoted absolute model commands; ideate proof input was corrected to include required `approach` and `origin_evidence_ids`. |
| Real CLI smoke | ok | `$ask` generated `ask_wiki_model_runtime_proof.json`; `$ideate` generated `generate_ideas_model_runtime_proof.json`; both proofs include `review_llm_or_model_evidence` and `external_runtime_evidence`. |
| Parity inventory recognition | ok | `current-parity-inventory-after-model-external-proofs.json` reports runtime counts `{not_required: 3, pending: 0, supplied: 4, verified: 21}`; the parity gate passes with semantic/non-full warnings. |
| Remaining blocker | warn | Detailed non-semantic proof requirements remain for `exp-eval` (`external_runtime_evidence`, `approval_boundary_evidence`, `wiki_mutation_evidence`), `paper-plan` (`external_runtime_evidence`), `paper-draft` (`external_runtime_evidence`, `wiki_mutation_evidence`), and `survey` (`external_runtime_evidence`), plus semantic equivalence evidence for all 28 routes. |

### Experiment Evaluation Approved Writeback Proof Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_bridge.py` | pending | Attach approval and wiki-mutation runtime proof manifests after completed approved `$exp-eval --write` claim verdict writeback. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Extend `$exp-eval --write` regression coverage with approval/wiki proof category assertions. |
| `harness/artifacts/autosci/runs/codex-exp-eval-writeback-proof-20260630/` | pending | Persist real CLI smoke output for inventory scanning. |
| `harness/artifacts/autosci/phase19/current-parity-inventory-after-exp-eval-writeback-proof.json` | pending | Refresh inventory after exp-eval writeback proof. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record verification and remaining blockers. |

### Experiment Evaluation Approved Writeback Proof Fix Result

| Check | Status | Evidence |
|---|---|---|
| Implementation | ok | Completed approved `$exp-eval --write` now emits `verify_claim_approval_runtime_proof.json` and `verify_claim_wiki_mutation_runtime_proof.json` after claim-verdict wiki writeback succeeds. |
| Safety boundary | ok | Proof emission still requires a verified approval contract: approval ref, allowlist evidence, runtime evidence, before artifact, after artifact, and `--execute-approved`. |
| Category boundary | ok | `$exp-eval` emits `external_runtime_evidence` + `approval_boundary_evidence` in the approval proof, and `wiki_mutation_evidence` in the wiki proof; no side-effect proof is emitted because the route does not declare that category. |
| Regression tests | ok | `pytest test_autosci_skill_shim.py -k exp_eval`: 2 passed; `py_compile` passed. |
| Real CLI smoke | ok | `$exp-eval claim-skillgen-write-20260630 --write --execute-approved` generated completed writeback and proof manifests under `codex-exp-eval-writeback-proof-20260630/`. |
| Parity inventory recognition | ok | `current-parity-inventory-after-exp-eval-writeback-proof.json` marks `$exp-eval.runtime_proof_status=verified`; runtime counts are `{not_required: 3, pending: 0, supplied: 3, verified: 22}`. |
| Remaining blocker | warn | Non-semantic detailed pending categories remain for `ingest` (`wiki_mutation_evidence`), `paper-plan` (`external_runtime_evidence`), `paper-draft` (`external_runtime_evidence`, `wiki_mutation_evidence`), and `survey` (`external_runtime_evidence`), plus semantic equivalence evidence for all 28 routes. |

### Ingest Wiki Registration Proof Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_bridge.py` | pending | Emit an ingest wiki-registration proof manifest only when final source registration boundary confirms paper page, log, graph edge, index, and context rebuild are all present. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Extend ingest final-registration regression coverage with wiki mutation proof assertions. |
| `harness/artifacts/autosci/runs/codex-ingest-wiki-proof-20260630/` | pending | Persist real CLI smoke output with a registered wiki source for inventory scanning. |
| `harness/artifacts/autosci/phase19/current-parity-inventory-after-ingest-wiki-proof.json` | pending | Refresh inventory after ingest wiki proof. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record verification and remaining blockers. |

### Ingest Wiki Registration Proof Fix Result

| Check | Status | Evidence |
|---|---|---|
| Implementation | ok | Ingest final source registration now emits `ingest_paper_wiki_mutation_runtime_proof.json` only when the boundary confirms paper page, log, graph edge, index, and context brief are present. |
| Boundary honesty | ok | Missing or partial wiki registration still does not emit the wiki mutation proof; source provider proof remains separate from wiki registration proof. |
| Regression tests | ok | Ingest final-registration/PDF subset: 2 passed; `py_compile` passed. |
| Real CLI smoke | ok | `$ingest artifacts/autosci/phase19/ingest-wiki-proof-inputs/registered_source.md` generated source and wiki mutation proof manifests under `codex-ingest-wiki-proof-20260630/`. |
| Parity inventory recognition | ok | `current-parity-inventory-after-ingest-wiki-proof.json` clears `$ingest.wiki_mutation_evidence`; runtime counts remain `{not_required: 3, pending: 0, supplied: 3, verified: 22}` because ingest is a dry-run route. |
| Remaining blocker | warn | Non-semantic detailed pending categories remain for `paper-plan` (`external_runtime_evidence`), `paper-draft` (`external_runtime_evidence`, `wiki_mutation_evidence`), and `survey` (`external_runtime_evidence`), plus semantic equivalence evidence for all 28 routes. |

### Publication Source External Runtime Category Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_bridge.py` | pending | Add `external_runtime_evidence` to completed publication citation/source proof manifests for paper-plan, paper-draft, and survey. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Update paper-plan, paper-draft, and survey source proof category assertions. |
| `harness/artifacts/autosci/runs/` | pending | Regenerate affected publication smoke artifacts for inventory scanning. |
| `harness/artifacts/autosci/phase19/current-parity-inventory-after-publication-external-proof.json` | pending | Refresh inventory after publication source proof category fix. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record verification and remaining blockers. |

### Publication Source External Runtime Category Fix Result

| Check | Status | Evidence |
|---|---|---|
| Implementation | ok | Publication citation/source proof manifests now include `external_runtime_evidence` with `provider_source_evidence` for paper-plan, paper-draft, and survey. |
| Scope boundary | ok | Review target source proof was checked and left unchanged; only publication citation/source proof categories changed. |
| Regression tests | ok | Paper-plan/paper-draft/survey targeted tests: 3 passed; `py_compile` passed. |
| Real CLI smoke | ok | `$paper-plan`, `$paper-draft`, and `$survey` source-backed smokes generated provider+external source proof manifests under `codex-paper-plan-external-proof-20260630/`, `codex-paper-draft-external-proof-20260630/`, and `codex-survey-external-proof-20260630/`. |
| Parity inventory recognition | ok | `current-parity-inventory-after-publication-external-proof.json` marks `$paper-plan` and `$survey` runtime proof `verified`; runtime counts are `{not_required: 3, pending: 0, supplied: 1, verified: 24}`. |
| Remaining blocker | warn | The only remaining non-semantic detailed pending category is `paper-draft.wiki_mutation_evidence`; all routes still require semantic equivalence evidence for full parity. |

### Paper Draft Workspace Wiki Projection Proof Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_skill_shim.py` | pending | After `$paper-draft` workspace projection, emit a wiki mutation proof manifest that references actual updated wiki output/index paths. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Add paper-draft projection proof assertion at the skill-run level. |
| `harness/artifacts/autosci/runs/codex-paper-draft-wiki-proof-20260630/` | pending | Persist real CLI smoke output for inventory scanning. |
| `harness/artifacts/autosci/phase19/current-parity-inventory-after-paper-draft-wiki-proof.json` | pending | Refresh inventory after paper-draft wiki projection proof. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record verification and remaining blockers. |

### Paper Draft Workspace Wiki Projection Proof Fix Result

| Check | Status | Evidence |
|---|---|---|
| Implementation | ok | `$paper-draft` workspace projection now emits top-level `paper_draft_workspace_wiki_mutation_runtime_proof.json` only when the projected workspace summary contains actual updated wiki output/index paths. |
| Manifest validity | ok | The workspace wiki proof uses `collection_mode: manual_review`; the earlier bad `workspace_projection` manifest was overwritten in `codex-paper-draft-wiki-proof-20260630/`. |
| Regression tests | ok | `pytest test_autosci_skill_shim.py -k paper_draft_includes_verified_compile_pdf_handoff`: 1 passed. |
| Real CLI smoke | ok | `$paper-draft idea-skillgen --title "SkillGen Wiki Draft"` generated valid workspace wiki proof manifests under `codex-paper-draft-wiki-proof-20260630/` and `codex-paper-draft-wiki-proof-fixed-20260630/`. |
| Parity inventory recognition | ok | `current-parity-inventory-after-paper-draft-wiki-proof.json` reports runtime counts `{not_required: 3, pending: 0, supplied: 0, verified: 25}`. |
| Gate result | ok | `autosci_feature_parity_gate.py current-parity-inventory-after-paper-draft-wiki-proof.json` passed with only non-full-route/semantic warnings. |
| Remaining blocker | warn | All detailed non-semantic proof categories are cleared; every one of the 28 native routes still has pending `semantic_equivalence_evidence`, so `semantic_full_count=0` and `full_count=0`. |

### Semantic Audit Matrix Tooling Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `tools/semantic_parity_audit_matrix.py` | pending | Add a route-level semantic audit matrix generator that references native AutoSci skill docs and Solar wrapper/config evidence without auto-promoting routes to full parity. |
| `harness/plugins/autosci/tests/test_semantic_parity_audit_matrix.py` | pending | Cover partial audit generation, full-audit guard behavior, and evidence-ref validity. |
| `harness/artifacts/autosci/phase19/semantic-audits-current/` | pending | Generate the current 28-route semantic audit snapshot for inventory ingestion. |
| `harness/artifacts/autosci/phase19/current-parity-inventory-after-semantic-audit-matrix.json` | pending | Refresh inventory with generated semantic audits to verify current semantic state remains honest. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record verification and remaining semantic blockers. |

### Semantic Partial Audit Gate Handling Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/evaluators/scientific/autosci_feature_parity_gate.py` | pending | Permit blocked `semantic_audit` proof sources only when they are limited to `semantic_equivalence_evidence`, so partial semantic audits can be attached without failing the ordinary honesty gate. |
| `harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py` | pending | Add regression coverage that partial semantic audit proof sources pass ordinary gate while non-semantic blocked runtime proof sources still fail. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record verification and remaining semantic blockers. |

### Semantic Audit Matrix Tooling Fix Result

| Check | Status | Evidence |
|---|---|---|
| Audit generator | ok | Added `tools/semantic_parity_audit_matrix.py generate` to write per-route `autosci_semantic_parity_audit.v1` files from original AutoSci skill docs plus Solar wrapper/config evidence. |
| No auto-promotion | ok | Default generated audits are `semantic_parity=partial`; full audits require explicit `autosci_semantic_parity_assessment.v1` with passing checks and existing evidence refs. |
| Full guard | ok | Invalid full assessment requests are downgraded to partial and reported as blocked by `full_semantic_assessment_guard`. |
| Regression tests | ok | `test_semantic_parity_audit_matrix.py`: 3 passed; semantic proof writer validation still accepts only completed/full audits. |
| Current audit snapshot | ok | Generated `harness/artifacts/autosci/phase19/semantic-audits-current/` with 28 route audits: `semantic_full_count=0`, `semantic_partial_count=28`. |
| Inventory recognition | ok | `current-parity-inventory-after-semantic-audit-matrix.json` ingests the audit directory and records 28 inconclusive semantic audits without changing runtime counts `{not_required: 3, pending: 0, supplied: 0, verified: 25}`. |

### Semantic Partial Audit Gate Handling Fix Result

| Check | Status | Evidence |
|---|---|---|
| Gate boundary | ok | Ordinary parity gate now permits blocked `semantic_audit` sources only when categories are exactly `semantic_equivalence_evidence` and local evidence refs resolve. |
| Non-semantic safety | ok | Blocked non-semantic runtime proof sources still fail the ordinary parity gate. |
| Regression tests | ok | `test_autosci_feature_parity_gate.py`: 14 passed; combined semantic matrix + feature parity gate subset: 17 passed; `py_compile` and `git diff --check` passed. |
| Ordinary gate | ok | `autosci_feature_parity_gate.py current-parity-inventory-after-semantic-audit-matrix.json` passed with non-full/semantic warnings only. |
| Strict full gate | warn | `--require-full-parity` still fails for all 28 routes because `semantic_parity=full`, required proof level, empty remaining requirements, and final coverage status are not yet satisfied. |
| Remaining blocker | warn | Runtime proof blockers are clear, but full parity now depends on completed/full per-route semantic assessments and route promotion where strict gate requires `coverage_status=full` or approval-required `coverage_status=gated`. |

### Check Native Lint Semantics Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_bridge.py` | pending | Replace `$check` simplified local structure checks with evidence-backed execution of `tools/lint.py --wiki-dir <wiki> --json`, while preserving model evidence final-quality boundary. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Update `$check` model-command regression fixture to satisfy native lint semantics and assert lint report artifacts/feed-through. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record verification, semantic parity impact, and remaining blockers. |

### Check Semantic Full Assessment Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/artifacts/autosci/phase19/check-semantic-assessment-20260630.json` | pending | Record completed/full `$check` semantic assessment only from original AutoSci docs, Solar route evidence, native lint smoke, final-quality boundary, and model proof evidence. |
| `harness/artifacts/autosci/phase19/semantic-audits-check-full/` | pending | Generate the route-specific full semantic audit for `check`. |
| `harness/artifacts/autosci/phase19/check-route-full-parity-after-semantic-audit.json` | pending | Verify single-route inventory/strict gate behavior after the `check` semantic audit. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record verification and remaining global blockers. |

### Optional External Model Proof Requirement Declaration Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_parity_bridge.py` | pending | Declare `external_runtime_evidence` as supplied when a non-runtime-required route provides that category through model/review proof, without changing runtime policy from `not_required`. |
| `harness/plugins/autosci/tests/test_phase19_parity_bridge.py` | pending | Add regression coverage for a pure/model route that supplies optional external model proof categories. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record verification and `check` route strict-gate result. |

### Check Native Lint Semantics Fix Result

| Check | Status | Evidence |
|---|---|---|
| Native lint execution | ok | `$check` now executes `tools/lint.py --wiki-root <wiki>` and archives `wiki_lint_report.json` with `autosci_wiki_lint_cli.v1`, return code, and severity counts. |
| Final-quality boundary | ok | `check_final_quality_boundary` now blocks final readiness on native lint errors as well as missing model/reviewer evidence. |
| Regression test | ok | `test_autosci_skill_shim_check_uses_model_command_for_quality_review` verifies lint report artifact emission, zero native lint errors, completed model boundary, request/response hashes, and model proof categories. |
| Real CLI smoke | ok | `$check autosci wiki --wiki-root ... --model-command ...` generated `codex-check-native-lint-proof-20260630/` with native lint `error=0`, final quality ready, and `check_wiki_health_model_runtime_proof.json`. |
| Scope boundary | ok | This does not enable deterministic `--fix`; the full semantic claim is for report-only `$check` with explicit model/reviewer quality evidence. |

### Optional External Model Proof Requirement Declaration Fix Result

| Check | Status | Evidence |
|---|---|---|
| Requirement declaration | ok | `autosci_parity_bridge.py` now declares `external_runtime_evidence` as `supplied` when a pure/non-runtime-required route provides that category through model/review proof. |
| Runtime policy boundary | ok | `check.runtime_proof_status` remains `not_required`; optional model-command external evidence does not make the route provider-required. |
| Regression test | ok | `test_route_declares_optional_external_model_proof_for_pure_route` passes and ordinary gate accepts the inventory. |

### Check Semantic Full Assessment Fix Result

| Check | Status | Evidence |
|---|---|---|
| Semantic assessment | ok | Added `check-semantic-assessment-20260630.json` with completed/full checks for native command surface, native lint execution, report-only default, model quality boundary, and regression coverage. |
| Semantic audit | ok | `semantic-audits-check-full/check.semantic-audit.json` is `semantic_parity=full` with all acceptance checks `ok` and no remaining requirements. |
| Semantic proof | ok | `semantic-audits-check-full/check.semantic-proof.json` was written by `semantic_parity_runtime_proof.py from-audit`. |
| Single-route strict gate | ok | `check-route-full-parity-after-semantic-audit.json` passes ordinary gate and `--require-full-parity`; `check` is `coverage_status=full`, `semantic_parity=full`, `proof_level=E3`, `runtime_proof_status=not_required`. |
| Global inventory | warn | `current-parity-inventory-after-check-semantic-full.json` passes ordinary gate and reports `full_count=1`, `semantic_full_count=1`, `semantic_partial_count=27`; strict global full parity still fails for the other 27 routes. |
| Verification | ok | Related tests: 21 passed; `py_compile` passed; `git diff --check` passed. |

### Ingest Source External Evidence Category Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_bridge.py` | pending | Add `external_runtime_evidence` to completed ingest source-preparation proof manifests while keeping dry-run execution policy unchanged. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Update ingest source proof category assertions for PDF and registered-source smokes. |
| `harness/artifacts/autosci/runs/codex-ingest-wiki-proof-20260630/` | pending | Regenerate real ingest smoke proof manifests for inventory scanning. |
| `harness/artifacts/autosci/phase19/current-parity-inventory-after-ingest-external-source-proof.json` | pending | Refresh inventory after ingest source proof category fix. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record verification and remaining semantic blockers. |

### Ingest Source External Evidence Category Fix Result

| Check | Status | Evidence |
|---|---|---|
| Implementation | ok | Completed ingest source-preparation proof manifests now include `provider_source_evidence` and `external_runtime_evidence`. |
| Scope boundary | ok | `$ingest` remains `dry_run_only`; `runtime_proof_status` remains `not_required`, and no route was promoted to full parity. |
| Regression tests | ok | Ingest PDF/source-registration subset: 2 passed; `py_compile` passed. |
| Real CLI smoke | ok | `$ingest artifacts/autosci/phase19/ingest-wiki-proof-inputs/registered_source.md --run-id codex-ingest-wiki-proof-20260630` regenerated `ingest_paper_source_provider_runtime_proof.json` with both categories. |
| Parity inventory recognition | ok | `current-parity-inventory-after-ingest-external-source-proof.json` records `$ingest.external_runtime_evidence=supplied`; ordinary parity gate passes. |
| Remaining blocker | warn | `$ingest` is still semantic `partial`; full parity still requires an honest completed semantic assessment of source variants, enrichment, entity/citation/topic writes, optional discover/visualize behavior, and route limitations. |

### Visualize Native CLI Parity Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_skill_shim.py` | pending | Accept native `$visualize` flags `--obsidian`, `--canvas`, `--focus`, `--depth`, `--types`, and `--edge-types` without breaking review focus pass-through. |
| `harness/plugins/autosci/bin/autosci_bridge.py` | pending | Pass visualize mode/filter options into `tools/visualize.py`, archive recommendations, and keep serve execution approval-gated. |
| `tools/visualize.py` | pending | Add canvas node-type and edge-type filtering used by original `$visualize` docs. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Add/adjust visualize CLI and artifact assertions for focused/filtered canvas generation. |
| `harness/artifacts/autosci/runs/codex-visualize-proof-check-20260630/` | pending | Regenerate real visualize proof smoke for inventory scanning. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record verification and whether semantic full assessment is now defensible. |

### Visualize Semantic Full Assessment Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/artifacts/autosci/phase19/visualize-semantic-assessment-20260630.json` | pending | Record full semantic assessment for `$visualize` only after native flags, artifacts, recommendations, SPA serve health, approval proof, and wiki log evidence are present. |
| `harness/artifacts/autosci/phase19/semantic-audits-visualize-full/` | pending | Generate visualize-only full semantic audit and semantic proof manifest. |
| `harness/artifacts/autosci/phase19/visualize-route-full-parity-after-semantic-audit.json` | pending | Verify single-route strict gate for `$visualize`. |
| `harness/artifacts/autosci/phase19/current-parity-inventory-after-visualize-semantic-full.json` | pending | Refresh global inventory after adding the visualize semantic audit. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record strict gate outcome and remaining global semantic blockers. |

### Visualize Native CLI Parity Fix Result

| Check | Status | Evidence |
|---|---|---|
| Native CLI surface | ok | `$visualize` now accepts `--obsidian`, `--canvas`, `--focus`, `--depth`, `--types`, `--edge-types`, `--all`, and `--serve`; review focus remains pass-through rather than parser-blocked. |
| Tool filtering | ok | `tools/visualize.py` JSON-compat and native canvas paths now apply focus/depth, node type filters, and edge type filters. |
| Artifact semantics | ok | Default visualize still generates Obsidian graph config, `.obsidian/app.json`, Canvas, graph data, recommendations, and approved SPA health evidence. |
| Wiki log | ok | `$visualize` appends `wiki/log.md` with generated visualization artifacts and includes the log in side-effect runtime proof refs. |
| Regression tests | ok | Visualize subset: 3 passed; `py_compile` passed. |
| Real CLI smoke | ok | `codex-visualize-proof-check-20260630` regenerated completed evidence with `wiki_log`, `obsidian_app_config_json`, recommendations, approval proof, and side-effect proof. |
| Inventory | ok | `current-parity-inventory-after-visualize-native-cli-parity.json` passes ordinary parity gate with runtime counts unchanged `{not_required: 3, pending: 0, supplied: 0, verified: 25}`. |

### Visualize Semantic Full Assessment Result

| Check | Status | Evidence |
|---|---|---|
| Semantic assessment | ok | Added `visualize-semantic-assessment-20260630.json` covering native flags, Obsidian/Canvas artifacts, SPA serve health, recommendations, approval boundary, and wiki log. |
| Semantic audit/proof | ok | `semantic-audits-visualize-full/visualize.semantic-audit.json` is `semantic_parity=full`; `visualize.semantic-proof.json` was written from the audit. |
| Single-route strict gate | ok | `visualize-route-full-parity-after-semantic-audit.json` passes ordinary and `--require-full-parity`; `$visualize` is `coverage_status=gated`, `semantic_parity=full`, `proof_level=E3`, `runtime_proof_status=verified`, `remaining_requirements=[]`. |
| Global inventory | warn | `current-parity-inventory-after-visualize-semantic-full.json` reports `semantic_full_count=2` (`check`, `visualize`) and `semantic_partial_count=26`; ordinary gate passes, strict global parity still fails for the remaining semantic-partial routes. |

### Reset Native Scope Runtime Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_skill_shim.py` | pending | Accept and pass through native `$reset --scope wiki|raw|log|checkpoints|all`. |
| `harness/plugins/autosci/bin/autosci_bridge.py` | pending | Replace generic reset proposal with bounded `tools/reset_wiki.py` dry-run/runtime execution evidence while keeping approval gating. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Add reset dry-run and approved isolated execution assertions. |
| `harness/artifacts/autosci/runs/codex-reset-native-proof-20260630/` | pending | Regenerate real reset smoke evidence against an isolated wiki fixture, not the production workspace. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record verification and remaining reset semantic blockers after the fix. |

### Reset Route Proof Requirement Alignment Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/config/feature_parity_routes.v1.json` | pending | Add the reset wiki-mutation proof tool/wording so route requirements match the verified `wiki_mutation_evidence` proof emitted by the approved reset smoke. |
| `harness/artifacts/autosci/phase19/reset-route-full-parity-after-semantic-audit.json` | pending | Regenerate reset route inventory after the route proof requirement alignment. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record gate result after the alignment. |

### Reset Native Scope Runtime Fix Result

| Check | Status | Evidence |
|---|---|---|
| Native CLI surface | ok | `$reset` now accepts native `--scope` and passes it through `native_options.scope` / `inputs.reset_scope`. |
| Native dry-run | ok | `$reset --scope wiki` calls `tools/reset_wiki.py --dry-run`, archives `reset_wiki_dry_run_plan.json`, and leaves files unchanged by default. |
| Approved local execution | ok | `codex-reset-native-proof-20260630` executed `tools/reset_wiki.py --scope wiki --yes --execute-approved` against an isolated phase19 runtime wiki fixture. |
| Runtime proof | ok | Approved reset smoke produced `reset_wiki_runtime_evidence.json`, `reset_after_snapshot.json`, approval proof, side-effect proof, and wiki-mutation proof manifests. |
| Scope safety | ok | The wiki-scope smoke removed only runtime-copy wiki markdown/graph files, rebuilt `.gitkeep`, wrote `wiki/log.md`, and preserved `raw/papers/source.txt`. |
| Regression tests | ok | Reset/control subset: 5 passed; reset-only subset: 3 passed; `py_compile`, `jq empty`, and `git diff --check` passed. |

### Reset Route Proof Requirement Alignment Result

| Check | Status | Evidence |
|---|---|---|
| Route requirement alignment | ok | Reset route now declares `tools/wiki_mutation_runtime_proof.py from-writeback` and `wiki scaffold mutation proof`, matching emitted `wiki_mutation_evidence`. |
| Semantic assessment | ok | Added `reset-semantic-assessment-20260630.json` with full reset semantic assessment. |
| Semantic audit/proof | ok | `semantic-audits-reset-full/reset.semantic-audit.json` is `semantic_parity=full`; `reset.semantic-proof.json` was written from the audit. |
| Single-route strict gate | ok | `reset-route-full-parity-after-semantic-audit.json` passes ordinary and `--require-full-parity`; `$reset` is `semantic_parity=full`, `proof_level=E3`, `runtime_proof_status=verified`, `remaining_requirements=[]`. |
| Global inventory | warn | `current-parity-inventory-after-reset-semantic-full.json` passes ordinary gate and reports `semantic_full_count=3` (`check`, `visualize`, `reset`) and `semantic_partial_count=25`; strict global full parity still fails for the remaining semantic-partial routes. |

### Setup Native Status Evidence Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_bridge.py` | pending | Replace generic `$setup` proposal with read-only setup guide/env-template/env/Python/venv status evidence while preserving approval-gated secret writes. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Add assertions that setup status evidence reports set/unset booleans and never records secret values. |
| `harness/artifacts/autosci/runs/codex-setup-native-status-20260630/` | pending | Regenerate a real setup status smoke for semantic audit input. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record verification and whether setup can be promoted to semantic full. |

### Setup Semantic Full Assessment Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/artifacts/autosci/phase19/setup-semantic-assessment-20260630.json` | pending | Record setup semantic-full assessment using guide/template/status/redaction evidence plus existing approval-gated runtime proof. |
| `harness/artifacts/autosci/phase19/semantic-audits-setup-full/` | pending | Generate setup-only semantic audit and semantic proof manifest. |
| `harness/artifacts/autosci/phase19/setup-route-full-parity-after-semantic-audit.json` | pending | Verify single-route strict gate for `$setup`. |
| `harness/artifacts/autosci/phase19/current-parity-inventory-after-setup-semantic-full.json` | pending | Refresh global inventory after setup semantic full. |

### Setup Native Status Evidence Fix Result

| Check | Status | Evidence |
|---|---|---|
| Native status evidence | ok | `$setup` now emits `setup_status.json` (`autosci_setup_status.v1`) with setup guide/env-template paths, Python/.venv/.env checks, and provider key readiness booleans. |
| Secret redaction | ok | `codex-setup-native-status-20260630` used a dummy `OPENAI_API_KEY`; `rg` found no serialized dummy secret in the run directory. |
| Non-mutating default | ok | Default setup remains proposal/status evidence only and records `protected_core_edits_applied=false`; no `.env` write is performed by the bridge. |
| Approval compatibility | ok | Existing approved external setup proof path remains valid through `setup_status_approval_runtime_proof.json` and `setup_status_side_effect_execution_runtime_proof.json`. |
| Regression tests | ok | Setup subset: 3 passed; `py_compile`, `jq empty`, and `git diff --check` passed. |

### Setup Semantic Full Assessment Result

| Check | Status | Evidence |
|---|---|---|
| Semantic assessment | ok | Added `setup-semantic-assessment-20260630.json` covering setup guide/template, env status detection, secret redaction, non-mutating default, and approval-gated secret write boundary. |
| Semantic audit/proof | ok | `semantic-audits-setup-full/setup.semantic-audit.json` is `semantic_parity=full`; `setup.semantic-proof.json` was written from the audit. |
| Single-route strict gate | ok | `setup-route-full-parity-after-semantic-audit.json` passes ordinary and `--require-full-parity`; `$setup` is `semantic_parity=full`, `proof_level=E3`, `runtime_proof_status=verified`, `remaining_requirements=[]`. |
| Global inventory | warn | `current-parity-inventory-after-setup-semantic-full.json` passes ordinary gate and reports `semantic_full_count=4` (`check`, `visualize`, `reset`, `setup`) and `semantic_partial_count=24`; strict global full parity still fails for the remaining semantic-partial routes. |

### Prefill Foundation Path Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_bridge.py` | pending | Move approved prefill writes from `wiki/topics/foundation-*.md` to native `wiki/foundations/{slug}.md`, preserve idempotence, and emit wiki mutation proof. |
| `harness/plugins/autosci/bin/autosci_workspace_projector.py` | pending | Include `wiki/foundations/` in human workspace scaffold/index so prefill pages are not hidden by projection. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Update prefill approved mutation assertions for `wiki/foundations`, terminal frontmatter, and wiki mutation proof. |
| `harness/plugins/autosci/config/feature_parity_routes.v1.json` | pending | Align prefill route declaration with approved wiki mutation capability if needed by parity gate. |
| `harness/artifacts/autosci/runs/codex-prefill-proof-check-20260630/` | pending | Regenerate prefill proof smoke after the foundation path correction. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record verification and remaining prefill semantic blockers after the fix. |

### Prefill Foundation Path Fix Result

| Check | Status | Evidence |
|---|---|---|
| Native path correction | ok | Approved prefill now writes `wiki/foundations/foundation-skillgen-prefill-proof-20260630.md` instead of `wiki/topics/foundation-*.md`. |
| Idempotent terminal page | ok | New foundation page includes terminal foundation frontmatter/body, `source_url: ""`, LLM-analysis markers, and no outbound `key_papers` or `related_concepts` fields. Existing pages are treated as `no_op` rather than overwritten. |
| Workspace projection | ok | `autosci_workspace_projector.py` now scaffolds/indexes `wiki/foundations/`; workspace `index.md` includes a Foundations section and the new page. |
| Proof alignment | ok | Prefill route now declares wiki mutation proof tooling; regenerated smoke emits approval, side-effect, and `wiki_mutation_evidence` manifests. |
| Regression tests | ok | Prefill subset: 1 passed; `py_compile`, `jq empty`, and `git diff --check` passed. |
| Inventory | warn | `current-parity-inventory-after-prefill-foundation-path-fix.json` passes ordinary gate and `$prefill.runtime_proof_status=verified`, but `$prefill.semantic_parity` remains `partial`; remaining semantic blockers are catalog/domain selection plus Wikipedia/source-backed foundation expansion. |

### Ask Crystallize Writeback Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_skill_shim.py` | pending | Accept native `$ask --crystallize` and map it to write-back intent without changing default read-only ask. |
| `harness/plugins/autosci/bin/autosci_bridge.py` | pending | Add approval-gated ask crystallize writeback to `wiki/outputs/{query-slug}.md`, graph edge, wiki log, and rebuilt views. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Add ask crystallize parser/writeback assertions and preserve default no-op behavior. |
| `harness/plugins/autosci/config/feature_parity_routes.v1.json` | pending | Align ask route proof declaration with approved wiki mutation evidence if gates require it. |
| `harness/artifacts/autosci/runs/codex-ask-crystallize-proof-20260630/` | pending | Regenerate a real ask crystallize smoke after implementation. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record verification and remaining ask semantic blockers after the fix. |

### Check Edge Alias Compatibility Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_bridge.py` | pending | Let `$check` local edge validation accept both legacy `source/target/relation` and current lint `from/to/type` edge fields. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Keep ask/check fixture on current lint edge schema and verify local structure readiness remains true. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record regression test result after the compatibility fix. |

### Optional Proof Requirement Declaration Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_parity_bridge.py` | pending | Treat supplied optional approval/side-effect proof categories as declared requirements without changing default route side-effect policy. |
| `harness/plugins/autosci/tests/test_phase19_parity_bridge.py` | pending | Add/adjust coverage if needed so optional supplied proof categories pass the feature parity gate. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record inventory/gate verification after the declaration fix. |

### Ask Crystallize Writeback Fix Result

| Check | Status | Evidence |
|---|---|---|
| Native CLI surface | ok | `$ask --crystallize` now parses and records `native_options.crystallize=true`; `$ask --write` also requests crystallize write-back. |
| Default read-only behavior | ok | Default `$ask` remains `operation=no_op` and route `execution_status=partial`; route `side_effect_policy` stays `none` so normal ask is not incorrectly gated. |
| Approved crystallize writeback | ok | `codex-ask-crystallize-proof-20260630` created `wiki/outputs/what-evidence-supports-skillgen.md`, appended graph edges/log, and rebuilt `index.md` plus `graph/context_brief.md`. |
| Final answer boundary | ok | Writeback requires `ask_final_answer_boundary.final_answer_ready=true`; missing approval/runtime/model/source evidence blocks crystallize instead of writing incomplete output. |
| Runtime proofs | ok | Smoke emits provider source, model, approval, side-effect execution, and wiki mutation proof manifests; crystallize no longer overwrites the original retrieval source proof. |
| Regression tests | ok | Ask subset: 4 passed; check edge subset: 2 passed; `py_compile` and `git diff --check` passed. |
| Inventory | warn | `ask-route-after-crystallize-proof.json` marks `$ask.runtime_proof_status=verified`, but `$ask.semantic_parity=partial`; remaining blockers include native output format modes and broader crystallize target selection beyond default wiki outputs. |

### Check Edge Alias Compatibility Fix Result

| Check | Status | Evidence |
|---|---|---|
| Edge schema compatibility | ok | `$check` local edge validation now accepts legacy `source/target/relation` and current lint `from/to/type` records. |
| Fixture alignment | ok | Ask/check regression fixture now uses current frontmatter and `from/to/type` edge schema while preserving local readiness expectations. |
| Regression tests | ok | Ask/check subset: 4 passed; dedicated check subset: 2 passed; `py_compile` passed. |

### Optional Proof Requirement Declaration Fix Result

| Check | Status | Evidence |
|---|---|---|
| Optional proof declaration | ok | `autosci_parity_bridge.py` now declares supplied optional `approval_boundary_evidence` and `side_effect_execution_evidence` requirements without changing default route side-effect policy. |
| Regression tests | ok | `test_phase19_parity_bridge.py -k 'runtime_proof or approval or side_effect or inventory'`: 10 passed; `py_compile` passed. |
| Ordinary gates | ok | `autosci_feature_parity_gate.py` passes for `ask-route-after-crystallize-proof.json` and `current-parity-inventory-after-ask-crystallize-proof.json`. |
| Global inventory | warn | `current-parity-inventory-after-ask-crystallize-proof.json` reports `semantic_full_count=4`, `semantic_partial_count=24`, runtime counts `{not_required: 3, pending: 0, supplied: 0, verified: 25}`; strict global full parity remains incomplete. |

### Ask Native Format Modes Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_skill_shim.py` | pending | Pass native `$ask --format table|timeline|bullets` into ask inputs in addition to native options. |
| `harness/plugins/autosci/bin/autosci_bridge.py` | pending | Render ask answers/crystallized outputs in requested table, timeline, or bullets format using only retrieved/model evidence. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Add ask format mode regression assertions for answer markdown and retrieval sidecar. |
| `harness/plugins/autosci/config/feature_parity_routes.v1.json` | pending | Mention native ask output format modes in route capability/limitation text. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record tests and remaining ask semantic blockers after format support. |

### Ask Native Format Modes Fix Result

| Check | Status | Evidence |
|---|---|---|
| Native format mapping | ok | `$ask --format table|timeline|bullets` is now passed into `inputs.format` and `native_options.format`. |
| Answer rendering | ok | `ask_wiki_answer.md` renders evidence-backed table, timeline, or bullet sections without inventing new analysis. |
| Retrieval sidecar | ok | `ask_wiki_retrieval.json` records `requested_format`, preserving the native output mode in machine-readable evidence. |
| Crystallized output | ok | Approved crystallized ask outputs include `output_format` frontmatter and use the same evidence-backed answer section renderer. |
| Regression tests | ok | Ask subset: 5 passed; `py_compile`, JSON validation, and `git diff --check` passed. |
| Real CLI smoke | ok | `codex-ask-format-proof-20260630` completed `$ask --format table`; answer markdown contains `## Answer Table` and retrieval sidecar records `requested_format=table`. |
| Inventory/gate | warn | `ask-route-after-format-modes.json` and `current-parity-inventory-after-ask-format-modes.json` pass ordinary gate; `$ask.semantic_parity` remains `partial` because broader crystallize target selection is still not native-full. |

### Ask Crystallize Target Selection Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_skill_shim.py` | pending | Preserve positional ask query while treating `--target` as crystallize destination when write/crystallize is requested. |
| `harness/plugins/autosci/bin/autosci_bridge.py` | pending | Resolve crystallize targets for `concept:`, `idea:`, `method:`, `output:`, and explicit wiki markdown paths under the configured wiki root. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Add regression for approved ask crystallize into a concept target without query overwrite. |
| `harness/plugins/autosci/config/feature_parity_routes.v1.json` | pending | Update ask route capability text for typed crystallize target selection. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record verification and remaining ask blockers after target selection. |

### Ask Crystallize Target Selection Fix Result

| Check | Status | Evidence |
|---|---|---|
| Query/target separation | ok | `$ask "What supports SkillGen?" --target concept:skillgen-support --crystallize` preserves the query in `inputs.query` and records `inputs.crystallize_target=concept:skillgen-support` instead of overwriting the ask prompt. |
| Typed target writeback | ok | `codex-ask-target-proof-20260630` created `wiki/concepts/skillgen-support.md` with `entity_type=concept`, `entity_id=concept-skillgen-support`, source evidence ids, model evidence id, log entry, graph edge, and rebuilt index/context brief. |
| Approval/runtime boundary | ok | The writeback required `approval_ref`, allowlist evidence, before/runtime/after artifacts, `--execute-approved`, retrieved source evidence, and completed model-command synthesis before applying the mutation. |
| Runtime proofs | ok | Smoke emits model, provider-source, approval, side-effect execution, and wiki-mutation proof manifests for the target writeback. |
| Regression tests | ok | Ask subset: 6 passed; `py_compile`, ordinary feature parity gates for `ask-route-after-target-selection.json` and `current-parity-inventory-after-ask-target-selection.json`, and `git diff --check` passed. |
| Inventory | warn | `$ask.runtime_proof_status=verified`, but `$ask.semantic_parity=partial`; global inventory remains `semantic_full_count=4`, `semantic_partial_count=24`. Full parity still requires a route-level semantic audit/promotion rather than simply marking the route full. |

### Ask Context Gap Evidence Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_bridge.py` | pending | Add explicit `$ask` context evidence for `context_brief.md`, `open_questions.md`, `index.md`, and graph edges; surface gap annotations and crystallize recommendation without inventing facts. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Add ask regression assertions for context metadata, gap annotations, and crystallize recommendation in answer/retrieval evidence. |
| `harness/plugins/autosci/config/feature_parity_routes.v1.json` | pending | Update ask route limitation/capability text to include native context/gap/recommendation evidence. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record verification and whether ask is ready for semantic full audit after context/gap evidence is added. |

### Ask Context Gap Evidence Fix Result

| Check | Status | Evidence |
|---|---|---|
| Context files | ok | `$ask` retrieval sidecar now records `context_brief.md`, `open_questions.md`, `index.md`, and `graph/edges.jsonl` status/path/hash/matches under `wiki_context`. |
| Gap annotations | ok | Ask evidence records `gap_annotations`; the targeted regression covers a matching open question, and `codex-ask-context-gap-proof-20260630` records `no_matching_open_questions` for the current workspace state. |
| Crystallize recommendation | ok | Answer markdown, retrieval JSON, model request context, and crystallized pages now carry an evidence-bound crystallize recommendation without applying writes unless approval/finality gates pass. |
| Wiki citations | ok | Ask answer lines now cite retrieved wiki pages with `[[slug]]` links plus source paths, matching native citation expectations more closely. |
| Regression tests | ok | Ask subset: 6 passed; `py_compile`, route JSON validation, ordinary feature parity gates for `ask-route-after-context-gap-evidence.json` and `current-parity-inventory-after-ask-context-gap-evidence.json`, and `git diff --check` passed. |
| Inventory | warn | `$ask.runtime_proof_status=verified`, but `$ask.semantic_parity=partial`; next step is a route-level semantic assessment/audit if no further native ask gaps are found. |

### Ask Semantic Full Assessment Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/artifacts/autosci/phase19/ask-semantic-assessment-20260630.json` | pending | Record full semantic assessment for native `/ask` context loading, retrieval/citations, model finality, format modes, and crystallize targets. |
| `harness/artifacts/autosci/phase19/semantic-audits-ask-full/` | pending | Generate ask-only semantic audit and semantic runtime proof from the assessment. |
| `harness/artifacts/autosci/phase19/ask-route-full-parity-after-semantic-audit.json` | pending | Verify ask single-route parity after semantic audit ingestion. |
| `harness/artifacts/autosci/phase19/current-parity-inventory-after-ask-semantic-full.json` | pending | Refresh global inventory with ask semantic full audit included. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record gate outcomes and remaining global parity blockers. |

### Ask Semantic Full Assessment Result

| Check | Status | Evidence |
|---|---|---|
| Full semantic assessment | ok | Added `ask-semantic-assessment-20260630.json` covering native context/gap loading, source-grounded citations, model final answer boundary, format modes, read-only default, approved crystallize writeback, and typed target selection. |
| Semantic audit/proof | ok | `semantic-audits-ask-full/ask.semantic-audit.json` is `semantic_parity=full`; `ask.semantic-proof.json` was written from the audit. |
| Single-route strict gate | ok | `ask-route-full-parity-after-semantic-audit.json` passes `--require-full-parity`; `$ask` is `coverage_status=full`, `semantic_parity=full`, `proof_level=E3`, `runtime_proof_status=verified`, `remaining_requirements=[]`. |
| Global inventory | warn | `current-parity-inventory-after-ask-semantic-full.json` passes ordinary gate and reports `semantic_full_count=5` (`ask`, `check`, `visualize`, `reset`, `setup`) and `semantic_partial_count=23`; strict global full parity still fails for remaining routes. |
| Sanity checks | ok | JSON validation and `git diff --check` passed for touched ask code/config/log files and generated ask semantic artifacts. |

### Prefill Native Add/Catalog Evidence Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_skill_shim.py` | pending | Add native `$prefill --add` parsing and preserve domain/target inputs in the envelope. |
| `harness/plugins/autosci/bin/autosci_bridge.py` | pending | Emit prefill plan evidence for domain/add mode, existing-foundation dedup state, terminal foundation template, and approved writeback metadata. |
| `.agents/skills/prefill/foundations-catalog.yaml` | pending | Add a small advisory foundation catalog so catalog-mode prefill can read a user-extensible seed list instead of hard-coded fixtures. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Add/extend prefill regression coverage for `--add`, domain metadata, dedup, and terminal page constraints. |
| `harness/plugins/autosci/config/feature_parity_routes.v1.json` | pending | Update prefill required capabilities/limitations to reflect native add/catalog/domain evidence. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record verification and remaining prefill semantic blockers after the fix. |

### Prefill Native Add/Catalog Evidence Fix Result

| Check | Status | Evidence |
|---|---|---|
| Native CLI surface | ok | `$prefill --add` now parses, enters `native_options.add`, and maps to `inputs.add` / `inputs.prefill_mode=add` without relying on positional target overload. |
| Catalog/domain evidence | ok | Added `.agents/skills/prefill/foundations-catalog.yaml`; `$prefill` now emits `prefill_plan.json` with add/catalog mode, domain resolution, catalog status/path, selected seeds, and existing-foundation dedup state. |
| Approved terminal writeback | ok | `codex-prefill-add-catalog-proof-20260630` created `wiki/foundations/foundation-skillgen-add-proof-20260630.md` with terminal foundation frontmatter/body, `domain=NLP`, `source_url=""`, no outbound relationship fields, log/index/context rebuild, and approval/side-effect/wiki mutation proofs. |
| Regression tests | ok | Prefill subset: 2 passed; `py_compile`, route JSON validation, ordinary feature parity gates for `prefill-route-after-add-catalog-evidence.json` and `current-parity-inventory-after-prefill-add-catalog-evidence.json`, and `git diff --check` passed. |
| Inventory | warn | `$prefill.runtime_proof_status=verified`, but `$prefill.semantic_parity=partial`; remaining semantic gap is source-backed Wikipedia fetch/fallback expansion versus the current approved LLM-analysis scaffold. |

### Prefill Source Evidence Rendering Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_skill_shim.py` | pending | Add native-compatible `--source-evidence` input for prefill background evidence without pretending live Wikipedia fetch exists. |
| `harness/plugins/autosci/bin/autosci_bridge.py` | pending | Load supplied Wikipedia/source evidence, record source status in `prefill_plan.json`, and render source-backed definition/sections/source_url when available; keep fallback explicit otherwise. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Add prefill source evidence regression covering source_url and non-LLM source-backed page content. |
| `harness/plugins/autosci/config/feature_parity_routes.v1.json` | pending | Update prefill limitation text to distinguish supplied source evidence from live fetch gap. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record verification and remaining prefill blockers. |

### Prefill Source Evidence Rendering Fix Result

| Check | Status | Evidence |
|---|---|---|
| Native source evidence input | ok | `$prefill` now accepts `--source-evidence` and carries it through `native_options.source_evidence` / `inputs.source_evidence`. |
| Source-backed plan | ok | `prefill_plan.json` records supplied source evidence count/refs, matched source status/path/url per selected seed, and fallback status when no source evidence is supplied. |
| Source-backed rendering | ok | `codex-prefill-source-proof-20260630` created `wiki/foundations/foundation-lora-source-proof-20260630.md` with `source_url`, `source_status=source_backed`, `source_evidence_path`, source-backed definition, variants, and limitations, while preserving terminal foundation constraints. |
| Runtime proofs | ok | Source-backed approved run emits provider-source, approval, side-effect, and wiki-mutation proof manifests; route runtime proof status is `verified`. |
| Regression tests | ok | Prefill subset: 3 passed; `py_compile`, route JSON validation, ordinary feature parity gates for `prefill-route-after-source-evidence-rendering.json` and `current-parity-inventory-after-prefill-source-evidence-rendering.json`, and `git diff --check` passed. |
| Remaining blocker | warn | Live Wikipedia fetching is still not implemented as a networked tool path in this repo; parity is source-backed through explicit supplied evidence rather than inferred live fetch. |

### Prefill Wikipedia Fetch Tool Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `tools/fetch_wikipedia.py` | pending | Add native-compatible `summary`, `sections`, `section`, and `wikitext` commands with explicit network failure/page-missing statuses. |
| `harness/plugins/autosci/bin/autosci_bridge.py` | pending | When `$prefill --online` has no supplied source evidence, call the fetch tool and record fetch attempts/success/failure in `prefill_plan.json`; do not mark failed fetches as source-backed. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Add regression for prefill online fetch failure/fallback boundary without requiring network. |
| `harness/plugins/autosci/config/feature_parity_routes.v1.json` | pending | Add fetch tool to prefill route primary tools and adjust limitation text. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record verification and whether prefill can move to semantic audit after live tool boundary exists. |

### Prefill Wikipedia Fetch Tool Fix Result

| Check | Status | Evidence |
|---|---|---|
| Fetch tool CLI | ok | Added `tools/fetch_wikipedia.py` with `summary`, `sections`, `section`, and `wikitext` JSON commands; fixed the `wikitext`/`section` parser boundary so `wikitext --help` and `section --help` enter cleanly. |
| Online prefill bridge | ok | `$prefill --online` now reaches `inputs.online`; when no supplied source evidence exists, `prefill_plan.json` records `fetch_attempts` and successful summaries can become source evidence. |
| Failure boundary | ok | `codex-prefill-fetch-disabled-proof-20260630` ran with `AUTOSCI_WIKIPEDIA_FETCH_DISABLED=1`; plan recorded `fetch_disabled`, `source_evidence_count=0`, and selected seed `source_status=fallback_llm_analysis`, so disabled/failed fetch is not promoted to source-backed rendering. |
| Route metadata | ok | Prefill route now lists `tools/fetch_wikipedia.py` commands and `Wikipedia fetch attempt evidence`; limitation text reflects explicit failed/disabled fetch status. |
| Regression tests | ok | Prefill subset: 4 passed; `py_compile`, route JSON validation, fetch CLI help checks, ordinary feature parity gates for `prefill-route-after-wikipedia-fetch-tool.json` and `current-parity-inventory-after-prefill-wikipedia-fetch-tool.json`, and `git diff --check` passed. |
| Remaining blocker | warn | Live external Wikipedia fetch was not executed under current restricted network; `$prefill.semantic_parity` remains `partial` until a live provider fetch plus semantic audit proves original `/prefill` behavior end to end. |

### Prefill Live Fetch Semantic Audit Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/artifacts/autosci/runs/codex-prefill-live-fetch-proof-20260630/` | pending | Run `$prefill --online` against a real Wikipedia page and archive fetch/source-backed prefill evidence. |
| `harness/artifacts/autosci/phase19/prefill-semantic-assessment-20260630.json` | pending | Record full/blocked semantic assessment depending on live proof outcome, using only existing evidence refs. |
| `harness/artifacts/autosci/phase19/semantic-audits-prefill-full/` | pending | Generate prefill semantic audit/proof only if the assessment can honestly be full. |
| `harness/artifacts/autosci/phase19/prefill-route-full-parity-after-semantic-audit.json` | pending | Verify single-route strict gate after semantic audit ingestion if full assessment passes. |
| `harness/artifacts/autosci/phase19/current-parity-inventory-after-prefill-semantic-full.json` | pending | Refresh global inventory with prefill semantic proof if generated. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record live fetch outcome, semantic audit result, and remaining blockers. |

### Prefill Live Fetch Semantic Audit Result

| Check | Status | Evidence |
|---|---|---|
| Live provider proof | ok | Initial sandboxed run recorded DNS `fetch_failed`; escalated network probe confirmed `Transformer (deep learning architecture)` resolves to a completed Wikipedia summary. |
| Approval-gated live writeback | ok | `codex-prefill-live-fetch-proof-transformer-20260630` fetched live source evidence, recorded `source_evidence_count=1`, wrote `wiki/foundations/foundation-transformer-deep-learning-architecture.md` with `source_status=source_backed`, and emitted provider/approval/side-effect/wiki-mutation proof manifests. |
| Semantic assessment | ok | Added `prefill-semantic-assessment-20260630.json` with full acceptance checks for native CLI surface, catalog/domain/dedup planning, live fetch boundary, fallback truthfulness, terminal foundation rendering, and approval-gated wiki writeback. |
| Semantic audit/proof | ok | `semantic-audits-prefill-full/prefill.semantic-audit.json` is `semantic_parity=full`; `prefill.semantic-proof.json` was written from the audit. |
| Single-route strict gate | ok | `prefill-route-full-parity-after-semantic-audit.json` passes `--require-full-parity`; `$prefill` is `semantic_parity=full`, `proof_level=E3`, `runtime_proof_status=verified`, `remaining_requirements=[]`. |
| Global inventory | warn | `current-parity-inventory-after-prefill-semantic-full.json` passes ordinary gate and reports `semantic_full_count=6`, `semantic_partial_count=22`; full global parity still requires semantic full audits for remaining routes. |
| Sanity checks | ok | Prefill subset tests, `py_compile`, route JSON validation, fetch CLI help checks, parity gates, and `git diff --check` passed for touched files/artifacts. |

### Edit Raw Source Add/Delete Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_skill_shim.py` | pending | Add native-compatible delete/remove intent flag for `$edit` without changing existing wiki edit defaults. |
| `harness/plugins/autosci/bin/autosci_bridge.py` | pending | Add approval-gated raw source create/delete handling for `raw/...` targets, preserving existing raw-file read-only protection. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Add regressions for raw add, raw existing-file block, and raw delete approval path. |
| `harness/plugins/autosci/config/feature_parity_routes.v1.json` | pending | Update `$edit` required capabilities/limitations to include raw add/delete proof boundaries. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record verification and whether `$edit` is ready for semantic full assessment. |

### Edit Raw Source Add/Delete Fix Result

| Check | Status | Evidence |
|---|---|---|
| Native raw target routing | ok | `$edit` now recognizes explicit `raw/...` targets plus `--delete` / `delete raw/...` intent without changing existing wiki edit behavior. |
| Raw add | ok | `codex-edit-raw-add-proof-20260630` created `artifacts/autosci/workspace/raw/papers/edit-raw-add-proof-20260630.md` from approved after_artifact evidence and emitted provider-source, approval, side-effect, and wiki-mutation proof manifests. |
| Existing raw guard | ok | `codex-edit-raw-existing-block-proof-20260630` was rejected with `operation=blocked`; `edit-raw-existing-proof-20260630.md` remained unchanged, preserving native raw read-only behavior. |
| Raw delete | ok | `codex-edit-raw-delete-proof-20260630` deleted the approved raw target and emitted approval/source/side-effect/wiki-mutation proof manifests; delete changes now carry `approval_ref` for the research memory gate. |
| Proof refs | ok | Runtime proof refs now resolve to durable proof inputs or `artifacts/autosci/workspace/raw/...`; deleted raw targets are not used as live runtime refs. |
| Regression/gates | ok | `$edit` subset: 4 passed; `py_compile`, route JSON validation, proof JSON validation, ordinary feature parity gates for `edit-route-after-raw-add-delete.json` and `current-parity-inventory-after-edit-raw-add-delete.json`, and `git diff --check` passed. |
| Remaining blocker | warn | `$edit.semantic_parity` remains `partial` until the route-level full semantic assessment/audit is generated and passes strict route gate. |

### Edit Semantic Full Assessment Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/artifacts/autosci/phase19/edit-semantic-assessment-20260630.json` | pending | Record full semantic assessment for wiki updates, raw add/delete, read-only guard, approval boundary, and navigation/log rebuild. |
| `harness/artifacts/autosci/phase19/semantic-audits-edit-full/` | pending | Generate edit-only full semantic audit and semantic runtime proof. |
| `harness/artifacts/autosci/phase19/edit-route-full-parity-after-semantic-audit.json` | pending | Verify `$edit` single-route strict full gate after semantic audit ingestion. |
| `harness/artifacts/autosci/phase19/current-parity-inventory-after-edit-semantic-full.json` | pending | Refresh global inventory with edit semantic proof included. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record gate outcomes and remaining global blockers. |

### Edit Semantic Full Assessment Result

| Check | Status | Evidence |
|---|---|---|
| Semantic assessment | ok | Added `edit-semantic-assessment-20260630.json` covering native command surface, wiki page updates, raw source add/delete, existing raw read-only guard, approval boundary, and wiki log/index/context rebuild. |
| Semantic audit/proof | ok | `semantic-audits-edit-full/edit.semantic-audit.json` is `semantic_parity=full`; `edit.semantic-proof.json` was written from the audit. |
| Single-route strict gate | ok | `edit-route-full-parity-after-semantic-audit.json` passes `--require-full-parity`; `$edit` is `semantic_parity=full`, `proof_level=E3`, `runtime_proof_status=verified`, `remaining_requirements=[]`. |
| Global inventory | warn | `current-parity-inventory-after-edit-semantic-full.json` passes ordinary gate and reports `semantic_full_count=7`, `semantic_partial_count=21`; full global parity still requires semantic full audits and missing native proof for remaining routes. |
| Sanity checks | ok | Assessment JSON, audit generation, semantic proof writer, strict/ordinary parity gates, and `git diff --check` passed. |

### Refine Loop Evidence Boundary Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_skill_shim.py` | pending | Pass native refine `--difficulty`, `--focus`, and Review LLM evidence/command controls into the refine envelope. |
| `harness/plugins/autosci/bin/autosci_bridge.py` | pending | Emit a refine loop report with score trajectory, termination reason, fixed/unresolved issue buckets, and explicit Review LLM evidence status. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Add regression for refine loop report and review parameter propagation. |
| `harness/plugins/autosci/config/feature_parity_routes.v1.json` | pending | Update `$refine` required capabilities/limitations to reflect loop evidence boundary and remaining execution gap. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record verification and remaining refine blockers. |

### Refine Review LLM Runtime Proof Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_bridge.py` | pending | Emit a `review_model_runtime_proof_manifest_json` from completed `$refine --review-llm-evidence` records so route requirements can verify Review LLM evidence without changing gate rules. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Extend the approved refine regression to assert the Review LLM runtime proof artifact and categories. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record whether `$refine` runtime proof moves from `supplied` to `verified` and list remaining semantic blockers. |

### Refine Review LLM Runtime Proof Result

| Check | Status | Evidence |
|---|---|---|
| Review evidence provenance | ok | `$refine` now preserves `--review-llm-evidence` source paths in `refine_loop_report.rounds[].source_path`. |
| Review LLM runtime proof | ok | `codex-refine-loop-proof-20260630/refine_artifact_review_llm_runtime_proof.json` supplies `review_llm_or_model_evidence` plus `external_runtime_evidence` and cites `review-20260630.json` plus `refine_loop_report.json`. |
| Approved apply proof | ok | The proof run restored `refine-loop-proof.md` to before content, then `$refine --execute-approved` replaced it with approved after content and emitted approval/source/side-effect proof manifests. |
| Route gate | ok | `refine-route-after-loop-evidence-boundary.json` passes the parity gate with `runtime_proof_status=verified`, `coverage_status=gated`, `semantic_parity=partial`, `proof_level=E2`. |
| Global inventory | warn | `current-parity-inventory-after-refine-loop-evidence-boundary.json` passes ordinary gate and reports `semantic_full_count=7`, `semantic_partial_count=21`, `runtime_proof_status_counts.verified=25`; full global parity still requires semantic full audits and remaining execution blocks. |
| Remaining refine blocker | warn | `$refine` still lacks automatic multi-round `/review` dispatch and quality-gate rerun parity, so it is not promoted to semantic full. |
| Sanity checks | ok | `$refine` targeted test passed; `py_compile`, `git diff --check`, route gate, and inventory gate passed. |

### Refine Automatic Review Loop Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_skill_shim.py` | pending | Pass `$refine` Review LLM provider/model/endpoint controls through the native shim. |
| `harness/plugins/autosci/bin/autosci_bridge.py` | pending | Reuse the existing `/review` backend to run one post-apply Review LLM command/provider quality-gate round when `$refine` has no sufficient supplied review result. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Add regression for `$refine --review-llm-command` producing an automatic review round, score trajectory, and runtime proof. |
| `harness/plugins/autosci/config/feature_parity_routes.v1.json` | pending | Update `$refine` limitation text after the automatic review loop boundary is proven. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record verification and whether `$refine` is ready for semantic full assessment. |

### Refine Automatic Review Loop Fix Result

| Check | Status | Evidence |
|---|---|---|
| Shim provider controls | ok | `$refine` now passes Review LLM provider/model/endpoint controls through the native shim, in addition to command/evidence controls. |
| Post-apply review loop | ok | `$refine` reuses the existing `/review` backend to run a post-apply Review LLM command/provider quality-gate round when supplied review evidence is missing or below target and `max_rounds` allows another round. |
| Auto review proof | ok | `codex-refine-auto-review-loop-proof-20260630/refine_review_round_01.json` records command-mode Review LLM evidence; `refine_artifact_review_llm_runtime_proof.json` cites the round and loop report. |
| Route truthfulness | ok | `$refine` limitation now states command/provider Review LLM post-apply quality-gate support and keeps additional autonomous fix-generation cycles approval-gated. |
| Route gate | ok | `refine-route-after-auto-review-loop.json` passes the parity gate with `runtime_proof_status=verified`, `coverage_status=gated`, `semantic_parity=partial`, `proof_level=E2`. |
| Global inventory | warn | `current-parity-inventory-after-refine-auto-review-loop.json` passes ordinary gate and still reports `semantic_full_count=7`, `semantic_partial_count=21`; semantic full assessment has not been generated yet. |
| Sanity checks | ok | `$refine` targeted tests passed: 2 passed; `py_compile`, route JSON validation, route/inventory gates, and `git diff --check` passed. |

### Refine Semantic Full Assessment Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/artifacts/autosci/phase19/refine-semantic-assessment-20260630.json` | pending | Record full semantic assessment for native refine controls, approval-gated after_artifact apply, Review LLM loop evidence, post-apply quality gate, and proof artifacts. |
| `harness/artifacts/autosci/phase19/semantic-audits-refine-full/` | pending | Generate refine-only semantic audit and semantic proof manifest from the assessment. |
| `harness/artifacts/autosci/phase19/refine-route-full-parity-after-semantic-audit.json` | pending | Verify `$refine` single-route strict full semantic gate after audit ingestion. |
| `harness/artifacts/autosci/phase19/current-parity-inventory-after-refine-semantic-full.json` | pending | Refresh global inventory with refine semantic proof included. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record gate outcomes and remaining global blockers. |

### Refine Semantic Full Assessment Result

| Check | Status | Evidence |
|---|---|---|
| Semantic assessment | ok | Added `refine-semantic-assessment-20260630.json` covering native refine controls, approval-gated after_artifact apply, loop report, supplied/command Review LLM boundaries, post-apply quality gate, route proof, and regression coverage. |
| Semantic audit/proof | ok | `semantic-audits-refine-full/refine.semantic-audit.json` is `semantic_parity=full`; `refine.semantic-proof.json` was written by `semantic_parity_runtime_proof.py from-audit`. |
| Single-route strict gate | ok | `refine-route-full-parity-after-semantic-audit.json` passes `--require-full-parity`; `$refine` is `semantic_parity=full`, `semantic_audit_status=verified`, `runtime_proof_status=verified`, `proof_level=E3`, `remaining_requirements=[]`. |
| Global inventory | warn | `current-parity-inventory-after-refine-semantic-full.json` passes ordinary gate and reports `semantic_full_count=8`, `semantic_partial_count=20`; full global parity still requires semantic full audits and remaining execution blocks for other routes. |
| Sanity checks | ok | Assessment JSON, audit JSON, proof JSON, `py_compile`, strict/ordinary parity gates, and `git diff --check` passed. |

### Review Semantic Full Assessment Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/artifacts/autosci/phase19/review-semantic-assessment-20260630.json` | pending | Record full semantic assessment for native review controls, artifact resolution, Review LLM evidence/command/provider boundary, final acceptance boundary, and source proof. |
| `harness/artifacts/autosci/phase19/semantic-audits-review-full/` | pending | Generate review-only semantic audit and semantic proof manifest from the assessment. |
| `harness/artifacts/autosci/phase19/review-route-full-parity-after-semantic-audit.json` | pending | Verify `$review` single-route strict full semantic gate after audit ingestion. |
| `harness/artifacts/autosci/phase19/current-parity-inventory-after-review-semantic-full.json` | pending | Refresh global inventory with review semantic proof included. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record gate outcomes and remaining global blockers. |

### Review Route Limitation Text Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/config/feature_parity_routes.v1.json` | pending | Replace `$review` full-coverage-incompatible downgrade wording with final-acceptance boundary wording while preserving the rule that non-Review-LLM diagnostics are not final. |
| `harness/artifacts/autosci/phase19/review-semantic-assessment-20260630.json` | pending | Keep assessment wording aligned with the updated route truthfulness language if needed. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record strict gate result after route text refresh. |

### Review Semantic Full Assessment Result

| Check | Status | Evidence |
|---|---|---|
| Semantic assessment | ok | Added and aligned `review-semantic-assessment-20260630.json` covering native command surface, artifact resolution/source proof, Review LLM evidence/command/provider boundary, final acceptance boundary, read-only route boundary, and regression coverage. |
| Route truthfulness text | ok | `$review` limitation no longer uses full-coverage-incompatible downgrade wording; it states that non-Review-LLM diagnostics are not final and final acceptance requires Review LLM evidence. |
| Semantic audit/proof | ok | `semantic-audits-review-full/review.semantic-audit.json` is `semantic_parity=full`; `review.semantic-proof.json` was written by `semantic_parity_runtime_proof.py from-audit`. |
| Single-route strict gate | ok | `review-route-full-parity-after-semantic-audit.json` passes `--require-full-parity`; `$review` is `coverage_status=full`, `semantic_parity=full`, `semantic_audit_status=verified`, `runtime_proof_status=verified`, `proof_level=E3`, `remaining_requirements=[]`. |
| Global inventory | warn | `current-parity-inventory-after-review-semantic-full.json` passes ordinary gate and reports `full_count=3`, `semantic_full_count=9`, `semantic_partial_count=19`; full global parity still requires remaining routes. |
| Sanity checks | ok | Assessment JSON, audit JSON, proof JSON, route config JSON, strict/ordinary parity gates, and `git diff --check` passed. |

### Rebuttal Reviewer Thread And Submission Audit Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_skill_shim.py` | pending | Add/forward native `$rebuttal` reviewer-thread, paper-slug, stress-test, and submission audit controls. |
| `harness/plugins/autosci/bin/autosci_bridge.py` | pending | Parse reviewer-thread evidence/direct text into RvX-CY concerns, map concerns to wiki evidence, emit formal/rich rebuttal artifacts, stress-test boundary, and submission audit boundary. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Add regression for reviewer-thread ingestion, wiki evidence mapping, formal output, stress-test boundary, and submission audit evidence. |
| `harness/plugins/autosci/config/feature_parity_routes.v1.json` | pending | Update `$rebuttal` route truthfulness only after runtime proof shows reviewer-thread/submission audit coverage. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record verification and remaining `$rebuttal` blockers after the fix. |

### Rebuttal Runtime Proof Artifact Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/artifacts/autosci/phase19/rebuttal-proof-inputs/` | pending | Add bounded reviewer-thread, Review LLM, submission-audit, and wiki evidence fixtures for a real `$rebuttal` proof run. |
| `harness/artifacts/autosci/runs/codex-rebuttal-thread-audit-proof-20260630/` | pending | Generate runtime proof artifacts from the native `$rebuttal` shim path. |
| `harness/artifacts/autosci/phase19/rebuttal-route-after-thread-audit-proof.json` | pending | Capture updated `$rebuttal` route with runtime proof attached. |
| `harness/artifacts/autosci/phase19/current-parity-inventory-after-rebuttal-thread-audit-proof.json` | pending | Refresh global parity inventory after `$rebuttal` proof ingestion. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record proof/gate outcomes. |

### Rebuttal Reviewer Thread And Submission Audit Fix Result

| Check | Status | Evidence |
|---|---|---|
| Shim controls | ok | `$rebuttal` now forwards `--reviewer-thread-evidence`, `--paper-slug`, `--stress-test/--no-stress-test`, `--wiki-root`, `--venue`, and `--submission-audit` into native action inputs. |
| Reviewer-thread ingestion | ok | `draft_rebuttal` loads structured reviewer-thread evidence, atomizes concerns into RvX-CY ids, preserves reviewer/source/evidence ids, and blocks path-like missing inputs from becoming fake review text. |
| Wiki/source mapping | ok | `rebuttal_response_map.json` records wiki/source entity mapping, evidence status, strategy, response text, and per-concern safety checks. |
| Rich/formal outputs | ok | Runtime bundle includes `rebuttal.md` and `rebuttal.txt`; the formal text is suitable as a source-backed paste target but does not claim portal submission. |
| Stress/submission boundaries | ok | `rebuttal_stress_test_boundary.json` is completed from Review LLM evidence; `rebuttal_submission_boundary.json` is `submission_audit_ready` from supplied audit evidence. |
| Runtime proof | ok | `draft_rebuttal_final_runtime_proof.json` supplies `review_llm_or_model_evidence`, `external_runtime_evidence`, and `provider_source_evidence`; `$rebuttal.runtime_proof_status=verified` in `rebuttal-route-after-thread-audit-proof.json`. |
| Route truthfulness | ok | `$rebuttal` route is now `coverage_status=gated` and names portal submission as externally audited, not bridge-claimed. |
| Global inventory | warn | `current-parity-inventory-after-rebuttal-thread-audit-proof.json` passes ordinary gate with runtime counts `{not_required: 3, pending: 0, supplied: 0, verified: 25}`; semantic full count remains 9 because `$rebuttal` semantic full audit is not generated yet. |
| Sanity checks | ok | `$rebuttal` targeted tests passed: 3 passed; `py_compile`, JSON validation, route/inventory parity gates, and `git diff --check` passed. |

### Rebuttal Semantic Full Assessment Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/artifacts/autosci/phase19/rebuttal-semantic-assessment-20260630.json` | pending | Record semantic assessment for reviewer-thread parsing, RvX-CY atomization, wiki evidence mapping, rich/formal outputs, Review LLM stress-test, safety checks, and submission audit boundary. |
| `harness/artifacts/autosci/phase19/semantic-audits-rebuttal-full/` | pending | Generate rebuttal-only semantic audit and semantic proof manifest from the assessment if checks pass. |
| `harness/artifacts/autosci/phase19/rebuttal-route-full-parity-after-semantic-audit.json` | pending | Verify `$rebuttal` single-route strict full semantic gate after audit ingestion. |
| `harness/artifacts/autosci/phase19/current-parity-inventory-after-rebuttal-semantic-full.json` | pending | Refresh global inventory with rebuttal semantic proof included. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record gate outcomes and any remaining global blockers. |

### Rebuttal Semantic Full Assessment Result

| Check | Status | Evidence |
|---|---|---|
| Semantic assessment | ok | Added `rebuttal-semantic-assessment-20260630.json` covering reviewer-thread parsing, RvX-CY atomization, wiki evidence mapping, rich/formal outputs, Review LLM stress-test, safety checks, and submission audit boundary. |
| Semantic audit/proof | ok | `semantic-audits-rebuttal-full/rebuttal.semantic-audit.json` is `semantic_parity=full`; `rebuttal.semantic-proof.json` was written by `semantic_parity_runtime_proof.py from-audit`. |
| Single-route strict gate | ok | `rebuttal-route-full-parity-after-semantic-audit.json` passes `--require-full-parity`; `$rebuttal` is `semantic_parity=full`, `semantic_audit_status=verified`, `runtime_proof_status=verified`, `proof_level=E3`, `remaining_requirements=[]`. |
| Global inventory | warn | `current-parity-inventory-after-rebuttal-semantic-full.json` passes ordinary gate and reports `full_count=4`, `partial_count=13`, `semantic_full_count=10`, `semantic_partial_count=18`; full global parity still requires remaining routes. |
| Sanity checks | ok | Assessment JSON, audit JSON, proof JSON, route/inventory JSON validation, `py_compile`, strict/ordinary parity gates, and `git diff --check` passed. |

### Poster Semantic Full Assessment Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/artifacts/autosci/phase19/poster-semantic-assessment-20260630.json` | pending | Record semantic assessment for PaperX/DAG route, HTML poster output, approved render/export, overflow/PNG validation, and approval boundary truthfulness. |
| `harness/artifacts/autosci/phase19/semantic-audits-poster-full/` | pending | Generate poster-only semantic audit and semantic proof manifest from the assessment if checks pass. |
| `harness/artifacts/autosci/phase19/poster-route-full-parity-after-semantic-audit.json` | pending | Verify `$poster` single-route strict full semantic gate after audit ingestion. |
| `harness/artifacts/autosci/phase19/current-parity-inventory-after-poster-semantic-full.json` | pending | Refresh global inventory with poster semantic proof included. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record gate outcomes and remaining global blockers. |

### Poster Native Content Pipeline Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_skill_shim.py` | pending | Forward poster paper_dir and format/header controls needed by the native content path without changing unrelated routes. |
| `harness/plugins/autosci/bin/autosci_bridge.py` | pending | Replace scaffold-only poster content with paper_dir -> `wiki2dag.py build` -> outline -> `poster.py build/inject-title/inject-figures/validate`, keeping render/export approval-gated. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Add regression for `$poster` building DAG/outline/HTML from real LaTeX paper source before approved render. |
| `harness/artifacts/autosci/phase19/poster-content-proof-inputs/` | pending | Add bounded paper source fixture for runtime proof. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record proof/gate result before semantic assessment. |

### Poster Native Content Pipeline Fix Result

| Check | Status | Evidence |
|---|---|---|
| Shim controls | ok | `$poster` now forwards paper source plus native header/layout controls including `--authors`, `--no-figures`, `--no-logos`, `--auto-figures`, `--no-refine`, `--refine-iterations`, `--affiliation-logo`, `--conference-logo`, and `--layout`. |
| Native content pipeline | ok | `build_poster` resolves a real paper source and runs paper_dir -> `wiki2dag.py build` -> outline HTML -> `poster.py build/inject-title/inject-header/inject-figures/validate`; render/export remains approval-gated. |
| Runtime proof | ok | `codex-poster-content-proof-20260630/publication_bundle.poster.json` is `status=completed` with 14 artifacts; `poster_generation_report.json`, `poster_validation.json`, and `poster_validate_result.json` are valid JSON. |
| Route truthfulness | ok | `poster-route-after-native-content-pipeline.json` passes the parity gate with runtime evidence attached; global inventory also passes ordinary gate. |
| Sanity checks | ok | `$poster` targeted tests passed: 4 passed; `py_compile`, JSON validation, route/inventory parity gates, and `git diff --cached --check` passed. |
| Remaining semantic blocker | warn | `$poster` remains semantic partial because the native Review LLM / critique-refine pass is not yet wired; current distillation is extractive and source-bound rather than model-reviewed. |

### Poster Review LLM Critique-Refine Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_skill_shim.py` | pending | Forward `$poster --review/--require-review-llm` and Review LLM evidence/command/provider options into `build_poster` inputs. |
| `harness/plugins/autosci/bin/autosci_bridge.py` | pending | Attach Review LLM critique/refine evidence to poster generation, emit a poster critique boundary, remove the extractive-only limitation when review evidence completes, and include runtime proof artifacts. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Add regression for `$poster` with paper source plus completed Review LLM critique evidence. |
| `harness/artifacts/autosci/phase19/poster-content-proof-inputs/` | pending | Add bounded poster Review LLM critique fixture for the proof run. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record verification and remaining semantic parity status after the fix. |

### Poster Route Proof Requirement Alignment Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/config/feature_parity_routes.v1.json` | pending | Declare `$poster` Review LLM critique/refine as a primary tool/capability so runtime proof categories match route proof requirements. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record strict gate result after route proof requirement alignment. |

### Poster Review LLM Critique-Refine Fix Result

| Check | Status | Evidence |
|---|---|---|
| Shim controls | ok | `$poster` now forwards `--review`, `--require-review-llm`, Review LLM evidence, command, provider, model, and endpoint options into `build_poster`. |
| Critique/refine boundary | ok | `poster_review_llm_boundary.json` records requested/completed Review LLM critique/refine status and rejects missing/incomplete review evidence instead of marking it successful. |
| Runtime proof | ok | `codex-poster-review-proof-20260630` includes `build_poster_review_llm_runtime_proof.json`, approved render/export proof, source DAG/outline/HTML/validation artifacts, and `publication_bundle.poster.json status=completed`. |
| Route requirement alignment | ok | `$poster` route now declares `tools/review_model_runtime_proof.py from-evidence` and `Review LLM critique/refine`, so `review_llm_or_model_evidence` is an explicit proof requirement. |
| Semantic audit/proof | ok | `semantic-audits-poster-full/poster.semantic-audit.json` is `semantic_parity=full`; `poster.semantic-proof.json` was written from the audit. |
| Single-route strict gate | ok | `poster-route-full-parity-after-semantic-audit.json` passes `--require-full-parity`; `$poster` is `semantic_parity=full`, `runtime_proof_status=verified`, `proof_level=E3`, `remaining_requirements=[]`. |
| Global inventory | warn | `current-parity-inventory-after-poster-semantic-full.json` passes ordinary gate and reports `semantic_full_count=11`, `semantic_partial_count=17`; full global parity still requires remaining routes. |
| Sanity checks | ok | `$poster` targeted tests passed: 5 passed; `py_compile`, route/inventory gates, semantic proof generation, and `git diff --cached --check` passed. |

### Survey Native Archive And Citation Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_skill_shim.py` | pending | Add/forward native `$survey --max-papers` and keep existing `--format` behavior. |
| `harness/plugins/autosci/bin/autosci_bridge.py` | pending | Cap citations, generate source-bound thematic related-work sections, write BibTeX coverage sidecar for LaTeX, archive survey output to wiki/outputs, append derived_from edges/log, and emit wiki mutation proof. |
| `harness/plugins/autosci/config/feature_parity_routes.v1.json` | pending | Declare survey archive/log/edge and BibTeX coverage capabilities so proof requirements match the native skill. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Extend survey regression to cover archive writeback, wiki mutation proof, max-papers cap, and BibTeX sidecar. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record verification and remaining semantic parity status after the fix. |

### Survey Native Archive And Citation Fix Result

| Check | Status | Evidence |
|---|---|---|
| Shim controls | ok | `$survey` now forwards native `--max-papers` plus existing `--format`/`--wiki-root` controls into `write_survey`. |
| Citation discipline | ok | Citation map is capped by `max_papers` and remains source-backed from supplied discovery/wiki evidence; unsupported citations are not fabricated. |
| Thematic output | ok | Survey sections now include source-bound thematic related-work groups with citation markers instead of a generic scaffold-only themes block. |
| LaTeX/BibTeX coverage | ok | LaTeX output now emits `survey_bibtex_coverage.json`; missing external BibTeX fetches are marked with `[UNCONFIRMED]` rather than invented entries. |
| Wiki archive/writeback | ok | `survey_archive_writeback.json` records archive output under `wiki/outputs`, derived_from edges in `wiki/graph/edges.jsonl`, and `wiki/log.md` operation logging. |
| Runtime proof | ok | `codex-survey-archive-proof-20260630` includes provider/source proof and `write_survey_wiki_mutation_runtime_proof.json`; `survey-route-after-archive-writeback.json` passes ordinary gate with runtime verified. |
| Route truthfulness | ok | `$survey` route is now `coverage_status=full`, `backend_mode=solar_native`, explicit `semantic_parity=partial` until audited, and declares archive/log/edge plus BibTeX capabilities. |
| Semantic audit/proof | ok | `semantic-audits-survey-full/survey.semantic-audit.json` is `semantic_parity=full`; `survey.semantic-proof.json` was written from the audit. |
| Single-route strict gate | ok | `survey-route-full-parity-after-semantic-audit.json` passes `--require-full-parity`; `$survey` is `semantic_parity=full`, `runtime_proof_status=verified`, `proof_level=E3`, `remaining_requirements=[]`. |
| Global inventory | warn | `current-parity-inventory-after-survey-semantic-full.json` passes ordinary gate and reports `full_count=5`, `semantic_full_count=12`, `semantic_partial_count=16`; remaining routes still block global full parity. |
| Sanity checks | ok | `$survey` targeted tests passed: 3 passed; `py_compile`, route/inventory gates, semantic proof generation, and `git diff --cached --check` passed. |

### Paper Plan Final Acceptance Proof Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/artifacts/autosci/phase19/publication-external-proof-inputs/` | pending | Add bounded paper-plan compile handoff allowlist, before-state, and runtime evidence JSON referencing the existing compiled PDF. |
| `harness/artifacts/autosci/runs/codex-paper-plan-final-proof-20260630/` | pending | Generate `$paper-plan` proof with source citation evidence, Review LLM evidence, and verified compile/PDF handoff. |
| `harness/artifacts/autosci/phase19/paper-plan-route-after-final-acceptance.json` | pending | Capture route proof after final acceptance boundary is completed. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record proof/gate result before semantic assessment. |

### Paper Plan Idea Graph Evidence Map Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_skill_shim.py` | pending | Forward `--wiki-root` for `$paper-plan` so native idea graph inputs are available to `plan_report`. |
| `harness/plugins/autosci/bin/autosci_bridge.py` | pending | Read target idea pages, linked experiments, and referenced method/concept/topic/paper pages into a `paper_plan_idea_graph_map.json` artifact, add an evidence-map section, and require idea-graph readiness in final acceptance. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Update paper-plan final acceptance regression to include a validated idea graph with succeeded experiment evidence. |
| `harness/artifacts/autosci/phase19/paper-plan-proof-inputs/wiki/` | pending | Add bounded wiki idea graph fixture for the final proof run. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record verification before semantic audit. |

### Paper Plan Final Acceptance And Idea Graph Fix Result

| Check | Status | Evidence |
|---|---|---|
| Shim controls | ok | `$paper-plan` now forwards `--wiki-root`, preserving native idea-graph input scope. |
| Idea graph map | ok | `paper_plan_idea_graph_map.json` records target slugs, validated/in-progress ideas, linked succeeded experiments, and referenced method/concept/topic/paper pages. |
| Final acceptance boundary | ok | `paper_plan_final_acceptance_boundary.json` now requires idea graph readiness, source-backed citation planning, completed Review LLM proof, and verified compile/PDF handoff. |
| Runtime proof | ok | `codex-paper-plan-final-proof-20260630` reaches `final_plan_accepted=True` with idea graph ready, Review LLM evidence, provider/source proof, and compile handoff evidence. |
| Route truthfulness | ok | `$paper-plan` route is now `coverage_status=full` with explicit `semantic_parity=partial` until audited, and the limitation names final acceptance as gated by source/review/compile handoff evidence. |
| Semantic audit/proof | ok | `semantic-audits-paper-plan-full/paper-plan.semantic-audit.json` is `semantic_parity=full`; `paper-plan.semantic-proof.json` was written from the audit. |
| Single-route strict gate | ok | `paper-plan-route-full-parity-after-semantic-audit.json` passes `--require-full-parity`; `$paper-plan` is `semantic_parity=full`, `proof_level=E3`, `remaining_requirements=[]`. |
| Global inventory | warn | `current-parity-inventory-after-paper-plan-semantic-full.json` passes ordinary gate and reports `full_count=6`, `semantic_full_count=13`, `semantic_partial_count=15`; remaining routes still block global full parity. |
| Sanity checks | ok | `$paper-plan` targeted tests passed: 4 passed; `py_compile`, route/inventory gates, semantic proof generation, and `git diff --cached --check` passed. |

### Paper Draft Semantic Full Assessment Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/config/feature_parity_routes.v1.json` | pending | Promote `$paper-draft` coverage truthfulness from partial to full with explicit semantic partial guard until audit verification. |
| `harness/artifacts/autosci/phase19/paper-draft-semantic-assessment-20260630.json` | pending | Record full semantic assessment using existing final manuscript, source/review/compile, paper directory, and wiki projection proof artifacts. |
| `harness/artifacts/autosci/phase19/semantic-audits-paper-draft-full/` | pending | Generate paper-draft full semantic audit and semantic runtime proof. |
| `harness/artifacts/autosci/phase19/paper-draft-route-full-parity-after-semantic-audit.json` | pending | Verify `$paper-draft` single-route strict full gate. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record gate outcome and remaining global blockers. |

### Paper Draft References BibTeX Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_bridge.py` | pending | Generate `paper/references.bib` and `paper_draft_bibtex_coverage.json` from the source-backed citation map, using `[UNCONFIRMED]` placeholders when verified BibTeX is unavailable. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Extend paper-draft final manuscript regression to assert references.bib and BibTeX coverage artifacts. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record verification before semantic assessment. |

### Paper Draft Semantic Full Assessment Result

| Check | Status | Evidence |
|---|---|---|
| Route truthfulness | ok | `$paper-draft` route is now `coverage_status=full` with explicit `semantic_parity=partial` until audited; limitation names source/review/compile/paper-dir/wiki projection proof requirements. |
| References/BibTeX | ok | `write_report` now writes `paper/references.bib` plus `paper_draft_bibtex_coverage.json`; missing verified BibTeX is marked `[UNCONFIRMED]` rather than invented. |
| Final manuscript proof | ok | `codex-paper-draft-wiki-proof-fixed-20260630` has `paper_draft_final_manuscript_boundary.status=final_manuscript_ready`, source/review proof, compile/PDF handoff, paper directory artifacts, and wiki projection mutation proof. |
| Semantic audit/proof | ok | `semantic-audits-paper-draft-full/paper-draft.semantic-audit.json` is `semantic_parity=full`; `paper-draft.semantic-proof.json` was written from the audit. |
| Single-route strict gate | ok | `paper-draft-route-full-parity-after-semantic-audit.json` passes `--require-full-parity`; `$paper-draft` is `semantic_parity=full`, `proof_level=E3`, `remaining_requirements=[]`. |
| Global inventory | warn | `current-parity-inventory-after-paper-draft-semantic-full.json` passes ordinary gate and reports `full_count=7`, `semantic_full_count=14`, `semantic_partial_count=14`; remaining routes still block global full parity. |
| Sanity checks | ok | `$paper-draft` targeted tests passed: 2 passed; `py_compile`, route/inventory gates, semantic proof generation, and `git diff --cached --check` passed. |

### Paper Compile PDF Runtime Verification Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_bridge.py` | pending | Require compile runtime semantic verification to prove the emitted PDF is structurally readable, not merely present on disk. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Replace fake one-line PDF executor tests with minimal valid PDF bytes and add a rejection regression for invalid PDF artifacts. |
| `harness/artifacts/autosci/phase19/paper-compile-proof-inputs/` | pending | Add bounded submission profile, PDF inspection, and submission audit evidence for a complete native paper-compile proof run. |
| `harness/artifacts/autosci/phase19/semantic-audits-paper-compile-full/` | pending | Generate full semantic audit/proof only after compile, page/font/anonymity, and checklist evidence pass. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record verification, strict route gate result, and remaining global blockers. |

### Paper Compile PDF Runtime Verification Fix Result

| Check | Status | Evidence |
|---|---|---|
| Runtime PDF integrity | ok | `compile_paper` runtime semantic verification now rejects PDF artifacts that are merely present on disk but lack PDF header/xref/EOF structural markers. |
| Invalid PDF regression | ok | `$paper-compile` tests include an approved executor that exits 0 but writes an invalid one-line PDF; the route returns inconclusive evidence, no `compiled_pdf` artifact, and `schema_only` action status. |
| Real compile proof | ok | `codex-paper-compile-structural-proof-20260630` ran approved `pdflatex` and produced a structurally valid 1-page PDF under `paper-compile-proof-inputs/paper/main.pdf`. |
| Submission boundary | ok | `codex-paper-compile-final-submission-proof-20260630/publication_submission_boundary.json` is `submission_ready=true`, `venue_submission_ready=true`, `submission_audit_ready=true`, and `portal_submission_completed=false`. |
| Route truthfulness | ok | `$paper-compile` remains `coverage_status=gated` because TeX execution/source auto-fix are approval-required side effects, while semantic parity is full via route-level audit. |
| Semantic audit/proof | ok | `semantic-audits-paper-compile-full/paper-compile.semantic-audit.json` is `semantic_parity=full`; `paper-compile.semantic-proof.json` was written from the audit. |
| Single-route strict gate | ok | `paper-compile-route-full-parity-after-semantic-audit.json` passes `--require-full-parity`; `$paper-compile` is `semantic_parity=full`, `runtime_proof_status=verified`, `proof_level=E3`, `remaining_requirements=[]`. |
| Global inventory | warn | `current-parity-inventory-after-paper-compile-semantic-full.json` reports `semantic_full_count=15`, `semantic_partial_count=13`; ordinary global gate is currently blocked by pre-existing `$daily-arxiv` route truthfulness (`coverage_status=full` with `side_effect_policy=approval_required`). |
| Sanity checks | ok | `$paper-compile` targeted tests passed: 11 passed; `py_compile`, JSON validation, single-route strict gate, `git diff --check`, and `git diff --cached --check` passed. |

### Daily ArXiv Route Truthfulness And Semantic Audit Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/config/feature_parity_routes.v1.json` | pending | Correct `$daily-arxiv` route truthfulness so approval/email/auto-ingest side effects remain `coverage_status=gated` instead of invalid `full`. |
| `harness/artifacts/autosci/phase19/daily-arxiv-semantic-assessment-20260630.json` | pending | Record full semantic assessment from existing provider, Review LLM, fan-in/writeback, and final delivery boundary proof. |
| `harness/artifacts/autosci/phase19/semantic-audits-daily-arxiv-full/` | pending | Generate daily-arxiv full semantic audit/proof. |
| `harness/artifacts/autosci/phase19/daily-arxiv-route-full-parity-after-semantic-audit.json` | pending | Verify daily-arxiv single-route strict full gate. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record verification and remaining global blockers after the fix. |

### Daily ArXiv Auto-Ingest Truthfulness Fix Plan

Logged: 2026-06-30 EDT

| File | Status | Planned Scope |
|---|---|---|
| `harness/plugins/autosci/bin/autosci_bridge.py` | pending | Stop treating direct wiki fan-in as native `/daily-arxiv auto-ingest`; emit `/ingest` handoff evidence and require actual delivery/ingest proof before final delivery readiness. |
| `harness/plugins/autosci/tests/test_autosci_skill_shim.py` | pending | Update daily-arxiv write regression so provider/Review LLM proof stays valid but final readiness is not claimed without `/ingest` completion. |
| `docs/integrations/autosci/phase19-progress-log.md` | pending | Record that daily-arxiv is route-truthful but remains semantic partial until native `/ingest` handoff execution is complete. |

### Daily ArXiv Route Truthfulness And Auto-Ingest Fix Result

| Check | Status | Evidence |
|---|---|---|
| Route truthfulness | ok | `$daily-arxiv` is now `coverage_status=gated` with `side_effect_policy=approval_required`; global ordinary gate no longer fails on full+approval_required. |
| Auto-ingest truthfulness | ok | `$daily-arxiv --write` now emits `daily_arxiv_ingest_handoff.json` with `/ingest <source_ref>` commands instead of directly writing wiki paper pages/edges/log. |
| Final boundary | ok | `codex-daily-ingest-handoff-proof-20260630/daily_arxiv_final_provider_delivery_boundary.json` is `status=daily_provider_ready`, `stage_provider_ready=true`, `final_delivery_ready=false`, `fan_in_completed=false`. |
| Review/provider proof | ok | New proof keeps provider source evidence and Review LLM evidence attached, but does not emit side-effect execution proof because `/ingest` was not completed. |
| Route gate | ok | `daily-arxiv-route-after-ingest-handoff-truthfulness.json` passes ordinary gate with `semantic_parity=partial`; no full semantic audit was generated because native auto-ingest completion is still pending. |
| Global inventory | ok | `current-parity-inventory-after-daily-arxiv-truthfulness.json` passes ordinary gate and reports `semantic_full_count=15`, `semantic_partial_count=13`; remaining blockers are real parity work, not route-truthfulness overclaim. |
| Sanity checks | ok | `$daily-arxiv` targeted tests passed: 5 passed; `py_compile`, route/inventory gates, `git diff --check`, and `git diff --cached --check` passed. |
| Remaining blocker | pending | `$daily-arxiv` can only become semantic full after the native `/ingest` route is completed and daily auto-ingest can attach completed ingest evidence rather than handoff-only evidence. |

## Priority A/B Product Entry And Workspace Projection Follow-up

Logged: 2026-06-30 EDT

| Item | Status | Evidence |
|---|---|---|
| Product AutoSci artifact root contract | ok | Added explicit `AUTOSCI_ARTIFACT_ROOT`, `SCIENTIFIC_ARTIFACT_ROOT`, and `SOLAR_AUTOSCI_OUTPUT_HARNESS` handling across the harness entrypoint, shim, bridge, operator smoke, parity bridge, and generic workflow runner. |
| `harness/bin/python3` wrapper hazard | warn | The wrapper resets `HARNESS_DIR` to the wrapper's own harness directory. Product entry must preserve the caller-selected runtime harness through `SOLAR_AUTOSCI_OUTPUT_HARNESS`; otherwise isolated runs leak back into the repo harness. |
| Human lifecycle projection | ok | `$research --scheduler-run` now projects `wiki/outputs/lifecycle_summary.md` from `scientific_lifecycle.v1`, including node results, gate status, blocked-node fields, and evidence refs. |
| Route truthfulness cleanup | ok | `ask`, `paper-draft`, `paper-plan`, and `survey` were corrected to avoid overclaiming route coverage without the corresponding runtime/semantic proof state in this branch. |
| Priority contract tests | ok | Added `harness/tests/test_autosci_priority_a_contracts.py` and `harness/tests/test_autosci_priority_b_demo_contracts.py` for product entry roots, route ABI, registries, scientific root, and human lifecycle workspace projection. |

### Issues Encountered And Guardrails

| Issue | Status | Guardrail |
|---|---|---|
| Smoke tests can mutate tracked workspace projection files (`wiki/index.md`, `wiki/graph/context_brief.md`, canvases, logs) | warn | After smoke/demo runs, inspect `git status --short` and automatically roll back only smoke-generated workspace projection noise when it is unrelated to the task. Do not roll back user-owned dirty files. |
| Product entry tests can leave ignored run directories under `harness/artifacts/autosci/runs/` after a failed root contract | warn | Use unique run ids in tests and assert no repo-root run directory is created for that run id. |
| Sandbox blocks local `127.0.0.1` listener tests | warn | Full plugin suite may show socket bind failures in sandbox. Re-run only the affected local-server tests with approved unsandboxed execution before treating them as real failures. |
| Route `coverage_status=full` with unresolved semantic/runtime proof causes parity gate failures | warn | Keep route coverage and operator binding status synchronized unless a route-level verified semantic proof is present and the side-effect policy permits the claim. |
| `$research --scheduler-run` may look successful while non-engineers cannot inspect what happened | warn | Require a human-facing `wiki/outputs/lifecycle_summary.md` page that names status, owner, node/gate evidence, blocked reasons, required evidence, and unblock condition. |

### Verification Commands

| Command | Result |
|---|---|
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/test_autosci_priority_a_contracts.py -q` | ok: 4 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/test_autosci_priority_b_demo_contracts.py harness/tests/test_autosci_priority_a_contracts.py harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_research_scheduler_run_attaches_blocked_summary -q` | ok: 6 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_phase19_parity_bridge.py harness/plugins/autosci/tests/test_phase19_operator_smoke.py harness/tests/evaluators/scientific/test_autosci_feature_parity_gate.py harness/tests/evaluators/scientific/test_autosci_operator_smoke_gate.py -q` | ok: 36 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests -q` | warn: 222 passed and 3 local socket-bind tests failed under sandbox. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest <three local socket tests> -q` with approved unsandboxed execution | ok: 3 passed. |

## Priority B Review And Ideate Workspace Projection Follow-up

Logged: 2026-06-30 EDT

| Item | Status | Evidence |
|---|---|---|
| Review diagnostics workspace output | ok | `$review` now projects `wiki/outputs/review.md` from `artifact_review.v1`, including target, focus, difficulty, review mode, Review LLM status, final acceptance boundary, findings, blocking reasons, and limitations. |
| Ideate candidate/evaluation workspace output | ok | `$ideate` now projects `wiki/outputs/ideas.md` from `idea_candidate.v1` plus `idea_evaluation.v1` when present, including candidate/evaluation status, idea rows, selected details, novelty/review boundary status, blocking reasons, and limitations. |
| Truthfulness boundary | ok | The new pages render local surrogate, missing external novelty, and missing Review LLM states as incomplete/blocked evidence instead of promoting them to provider-backed completion. |
| Priority B contract tests | ok | `harness/tests/test_autosci_priority_b_demo_contracts.py` now verifies product entry projection for `$review` and `$ideate --from-wiki`, plus the existing `$research --scheduler-run` lifecycle summary. |

### Issues Encountered And Guardrails

| Issue | Status | Guardrail |
|---|---|---|
| `$review` generated valid `artifact_review.v1` evidence but no stable human-facing `outputs/review.md` page | warn | Product demo routes that generate review diagnostics must project a durable workspace summary page from evidence, not require users to inspect raw JSON sidecars. |
| `$ideate` generated individual idea pages but lacked a single candidate/evaluation summary for demo review | warn | Keep `outputs/ideas.md` as the top-level human scan surface, while individual `wiki/ideas/<idea>.md` pages remain per-idea memory entries. |
| Local surrogate Review/Novelty output can be mistaken for final provider-backed validation | warn | Workspace pages must include `review_mode`, `review_available`, Review LLM status, external novelty status, final acceptance readiness, and blocking reasons whenever those fields exist. |
| Test runs can briefly touch coordinator/runtime state | warn | Inspect `git status --short` after validation and roll back only test-generated runtime pollution. In this run, `harness/.coordinator-state` showed transiently but had no persisted diff. |

### Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/plugins/autosci/bin/autosci_workspace_projector.py harness/tests/test_autosci_priority_b_demo_contracts.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/test_autosci_priority_b_demo_contracts.py -q` | ok: 3 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_runs_review_as_artifact_review harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_runs_ideate_from_wiki_and_discovery_sources -q` | ok: 2 passed. |

### Pause Checkpoint

Logged: 2026-06-30 EDT

| Item | Status | Evidence |
|---|---|---|
| Last pushed commit | ok | `8891f37e2 Project AutoSci review and idea summaries` is pushed to `origin/feature/autosci-solar-native`. |
| Completed scope | ok | Priority B review and ideate workspace summaries are implemented, tested, committed, and pushed. |
| Smoke pollution cleanup | ok | Test-generated `harness/.coordinator-state` content diff was rolled back before commit; later Git status showed a no-content stat/index modified marker. |
| Remaining uncommitted files | warn | Pre-existing/user/environment changes remain outside the commit: `.DS_Store`, `AGENTS.md`, `harness/config/physical-operators.json`; `harness/.coordinator-state` may need an index refresh or exact checkout if it reappears. |
| Pause state | pending | Stop here and resume from the next unchecked item in the implementation plan later. Do not redo completed Priority B review/ideate summary work unless regression appears. |

## Git Object Database Repair Checkpoint

Logged: 2026-07-01 EDT

| Item | Status | Evidence |
|---|---|---|
| Safety backup | ok | Saved `.git/config`, `.git/index`, `.git/packed-refs`, `.git/refs`, `worktree.diff`, and `staged.diff` to `/Users/jamesyuan/Desktop/OpenSolar_repair_safety_20260701_005359`. |
| Active maintenance process check | ok | No active `git maintenance`, `git repack`, `git pack-objects`, or `git gc` process was found before repair. |
| Auto maintenance disabled | ok | Set local and global `maintenance.auto=false`, `maintenance.autoDetach=false`, `gc.auto=0`, and `gc.autoDetach=false` before object repair. |
| Finder ref pollution | ok | Moved `.git/refs/.DS_Store` to `/Users/jamesyuan/Desktop/OpenSolar_repair_safety_20260701_005359/quarantine_refs/.DS_Store.refs`; no `.git/refs/.DS_Store` remains. |
| Missing parent object | ok | Direct SHA fetch did not restore `12f49391fadb30e294b697594ecbb718f3693cc9`; `git fetch --no-tags --refetch origin feature/autosci-solar-native` restored it and `git cat-file -t` now reports `commit`. |
| Index repair | ok | Backed up `.git/index` to `index.before_restore_staged`, then ran `git restore --staged .`; `git diff --cached --name-status` is empty. |
| History/connectivity validation | ok | `git log --oneline --decorate -5` reads through `12f49391f`; `git fsck --connectivity-only --no-dangling` exits cleanly. |
| GitHub Desktop reported blob | ok | `git ls-files --stage harness/tools/run_scientific_workflow.py` points to `0a9133e35850d459ce0c891695ab2bae8dc9c40f`; `git cat-file -t` reports `blob` and size is `27382`. |

### Repair Guardrails

| Issue | Status | Guardrail |
|---|---|---|
| Concurrent auto maintenance can corrupt or strand temporary pack state under `.git/objects/pack/.tmp-*` | warn | Keep local/global `maintenance.auto=false` and `gc.auto=0` until the repository has remained stable across normal GitHub Desktop/Codex usage. |
| Branch fetch alone may not repair a missing ancestor when local and remote tips already match | warn | Fetch the missing SHA first, then use `--refetch` on the branch if `cat-file` still fails. |
| Invalid staged entries can make GUI commit fail even after object repair | warn | Back up `.git/index`, run `git restore --staged .`, and re-stage intentionally after `git diff --cached` is empty. |

## Priority B Ingest Product Entry Contract Follow-up

Logged: 2026-07-01 EDT

| Item | Status | Evidence |
|---|---|---|
| Git safety precheck | ok | Before coding, `git status` showed no staged changes, `git log` read through `12f49391f`, `git fsck --connectivity-only --no-dangling` passed, `origin` used SSH, and local/global auto maintenance remained disabled. |
| Plan source fallback | warn | `/Users/jamesyuan/Downloads/autosci_solar_native_implementation_plan.md` was no longer present, so this continuation used the latest Phase19 log entries as the recovery source of truth. |
| Direct ingest product entry | ok | Added a Priority B contract for `solar-harness autosci "$ingest --paper <source> --run-id <id>"` through an isolated harness. |
| Human workspace paper projection | ok | The new contract asserts `research_paper.v1` evidence, parsed paper metadata, final source-registration readiness fields, one projected `wiki/papers/*.md` page, and `wiki/index.md` linkage. |
| Root pollution guard | ok | The contract asserts the unique run id is not written under the repo harness run directory, preserving isolated product-entry artifact roots. |

### Issues Encountered And Guardrails

| Issue | Status | Guardrail |
|---|---|---|
| The external implementation plan file can disappear between sessions | warn | Fall back to `docs/integrations/autosci/phase19-progress-log.md` and explicitly log the missing source before choosing the next scoped task. |
| Direct `$ingest` product-entry behavior was covered in shim tests but not in Priority B product contract tests | warn | Keep a product-entry test that runs through `harness/solar-harness.sh autosci`, not only the lower-level shim helper. |
| Git repair state must remain protected during normal AutoSci work | warn | Avoid fetch/repack/maintenance; verify cached diff is empty before edits and stage only files changed for the current task. |

### Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/tests/test_autosci_priority_b_demo_contracts.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/test_autosci_priority_b_demo_contracts.py -q` | ok: 4 passed. |

## Priority B Discover Product Entry Workspace Projection Follow-up

Logged: 2026-07-01 EDT

| Item | Status | Evidence |
|---|---|---|
| Direct discover product entry | ok | Added a Priority B contract for `solar-harness autosci "$discover <topic> --from-wiki --limit <n> --run-id <id>"` through an isolated harness. |
| Human workspace discovery projection | ok | `literature_discovery.v1` now projects `wiki/outputs/discovery.md` with evidence status, query, mode, limit, candidate count, source-provider boundary, final-shortlist boundary, candidates, artifacts, blocking reasons, and limitations. |
| Truthfulness boundary | ok | The workspace page preserves inconclusive discovery state when network/provider evidence is absent; it does not promote empty wiki discovery to a completed provider-backed shortlist. |
| Root pollution guard | ok | The new contract asserts the unique run id is not written under the repo harness run directory, preserving isolated product-entry artifact roots. |

### Issues Encountered And Guardrails

| Issue | Status | Guardrail |
|---|---|---|
| `$discover --from-wiki` can emit valid `literature_discovery.v1` evidence without a durable human-facing summary page | warn | Always project discovery evidence to `wiki/outputs/discovery.md` so product users do not need to inspect raw JSON to understand source readiness. |
| Empty discovery shortlists can be mistaken for successful discovery if only route execution is checked | warn | Surface `status`, `source_provider_boundary`, `final_shortlist_boundary`, blocking reasons, and limitations in the workspace page. |
| Network-disabled product-entry tests should not depend on live provider behavior | warn | Set `AUTOSCI_DISABLE_NETWORK_FETCH=1`, assert the truthful `inconclusive` state, and verify no fixture/local provider candidate is silently treated as real discovery evidence. |

### Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/plugins/autosci/bin/autosci_workspace_projector.py harness/tests/test_autosci_priority_b_demo_contracts.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/test_autosci_priority_b_demo_contracts.py::test_discover_projects_human_shortlist_summary -q` | ok: 1 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/test_autosci_priority_b_demo_contracts.py -q` | ok: 5 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_accepts_discover_from_wiki_limit -q` | ok: 1 passed. |

## Priority B Skills And Paper Draft Product Entry Follow-up

Logged: 2026-07-01 EDT

| Item | Status | Evidence |
|---|---|---|
| Updated plan source | ok | Used `/Users/jamesyuan/Downloads/AutoSci_Solar_Prioritized_Integration_Plan_2026-06-30.md`; next Priority B gaps were `$skills` route-list and `$paper-draft` minimal report demo. |
| `$skills` product entry contract | ok | Added a Priority B contract for `solar-harness autosci "$skills"` through an isolated harness, asserting 28 routes, demo skills, `coverage_status`, `side_effect_policy`, and non-full route truthfulness. |
| `$paper-draft` product entry contract | ok | Added a Priority B contract for `solar-harness autosci "$paper-draft --topic ... --title ... --run-id <id>"`, asserting `scientific_report.v1`, report sidecars, final-manuscript boundary, and root pollution guard. |
| Stable report workspace output | ok | The workspace projector now keeps the existing report-id page and also writes `wiki/outputs/report.md` for the boss/demo-visible report entry required by the updated plan. |
| Truthfulness boundary | ok | The paper draft demo remains `inconclusive` until source evidence, source-backed citations, Review LLM proof, and verified compile/PDF handoff evidence are present. |

### Issues Encountered And Guardrails

| Issue | Status | Guardrail |
|---|---|---|
| `$paper-draft` generated report pages with dynamic report ids, but the updated demo plan expects stable `wiki/outputs/report.md` | warn | Preserve dynamic pages for durable IDs while also projecting the latest report to the stable demo-visible report path. |
| Publication readiness is easy to overclaim from a generated report | warn | Assert the final-manuscript boundary file explicitly and require `publication_ready_claim_allowed=false` when Review LLM/source/compile evidence is missing. |
| `$skills` route-list can look like parity completion if statuses are not inspected | warn | Product-entry tests must assert per-route `coverage_status` and `side_effect_policy`, plus at least one non-full route, rather than only route count. |

### Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/plugins/autosci/bin/autosci_workspace_projector.py harness/tests/test_autosci_priority_b_demo_contracts.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/test_autosci_priority_b_demo_contracts.py::test_skills_product_entry_lists_route_statuses harness/tests/test_autosci_priority_b_demo_contracts.py::test_paper_draft_projects_demo_visible_report_summary -q` | ok: 2 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/test_autosci_priority_b_demo_contracts.py -q` | ok: 7 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_lists_configured_skills harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_lists_skills_with_dollar_alias harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_paper_draft_writes_latex_source -q` | ok: 3 passed. |
| `bash harness/tests/test-autosci-harness-entrypoint.sh` | ok |

## Priority B Exp Run Product Entry Follow-up

Logged: 2026-07-01 EDT

| Item | Status | Evidence |
|---|---|---|
| `$exp-run` product entry contract | ok | Added a Priority B contract for `solar-harness autosci "$exp-run exp-demo --run-id <id>"` through an isolated harness. |
| Runtime boundary projection | ok | The workspace projector now writes stable `wiki/outputs/experiment.md` from `experiment_plan.v1`, `experiment_result.v1`, optional `experiment_status.v1`, and `autosci_experiment_run_final_runtime_audit_boundary.v1`. |
| Truthfulness boundary | ok | The demo remains `gated` / `inconclusive` when approval/runtime evidence is absent; no command execution or remote collection is claimed. |
| Root pollution guard | ok | The contract asserts the unique run id is not written under the repo harness run directory, preserving isolated product-entry artifact roots. |

### Issues Encountered And Guardrails

| Issue | Status | Guardrail |
|---|---|---|
| `$exp-run exp-demo` currently expands through the route dependency chain before `run_experiment` | warn | Product-entry tests assert that `run_experiment` is present and truthful rather than hard-coding a two-action route shape. |
| Experiment result pages existed under `wiki/experiments/`, but demo users lacked a stable top-level runtime summary | warn | Project the latest run boundary to `wiki/outputs/experiment.md` while preserving per-experiment pages. |
| Approval-gated experiment runs can look like dry-run success if only command return code is checked | warn | Assert `experiment_result.v1.status=inconclusive`, `final_runtime_audit_ready=false`, missing approval/runtime evidence limitations, and absence of fixture execution logs. |

### Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/plugins/autosci/bin/autosci_workspace_projector.py harness/tests/test_autosci_priority_b_demo_contracts.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/test_autosci_priority_b_demo_contracts.py::test_exp_run_projects_demo_runtime_boundary_summary -q` | ok: 1 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/test_autosci_priority_b_demo_contracts.py -q` | ok: 8 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_accepts_exp_run_native_options_without_fixture_fallback harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_exp_run_full_routes_deploy_and_collect_actions harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_blocks_unapproved_exp_run_deploy_without_fixture_support -q` | ok: 3 passed. |

## Priority B Workspace Projection Overall Acceptance Follow-up

Logged: 2026-07-01 EDT

| Item | Status | Evidence |
|---|---|---|
| B8 workspace entrypoint | ok | `wiki/index.md` now includes a `Demo Entry Points` table for the updated plan's required boss/demo-visible outputs. |
| Required output links | ok | The index points to `outputs/lifecycle_summary.md`, `outputs/report.md`, `outputs/review.md`, `outputs/ideas.md`, and `outputs/experiment.md`. |
| Reader guidance | ok | The table maps each page to `what ran`, `what was produced`, `what is blocked`, `what evidence exists`, and `what remains incomplete`. |
| Truthfulness boundary | ok | Each entry is marked `ok` only when the target page exists, otherwise `pending`; missing demo pages are not hidden or treated as complete. |

### Issues Encountered And Guardrails

| Issue | Status | Guardrail |
|---|---|---|
| A directory listing alone does not tell demo users which page answers which question | warn | Keep `wiki/index.md` as the stable first-read page with explicit question-to-output mapping. |
| Required demo files may be generated by different routes at different times | warn | Show `ok` / `pending` per demo page in the index instead of requiring every route output to exist after every single run. |
| Stable output pages can still be misleading if they omit blocked or incomplete state | warn | Link demo pages to pages that expose evidence status, limitations, blocking reasons, or runtime/finality boundaries. |

### Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/plugins/autosci/bin/autosci_workspace_projector.py harness/tests/test_autosci_priority_b_demo_contracts.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/test_autosci_priority_b_demo_contracts.py::test_workspace_index_explains_demo_entry_points -q` | ok: 1 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/test_autosci_priority_b_demo_contracts.py -q` | ok: 9 passed. |

## Phase C Solar Unification Import Manifest Follow-up

Logged: 2026-07-01 EDT

| Item | Status | Evidence |
|---|---|---|
| Phase C premerge contract | ok | Added `docs/integrations/autosci/phase-c-solar-unification-import-manifest.v1.json` as the machine-readable selective-import contract for merging AutoSci into `Stellven/AI4Research#openJiuwen-Solar`. |
| Product base boundary | ok | The manifest names Stellven Solar as the product/install/desktop/distribution base and `Coconut-ch1ken/OpenSolar#feature/autosci-solar-native` as the AutoSci scientific runtime source. |
| Selective import groups | ok | The manifest enumerates AutoSci plugin runtime, scientific tools, workflows, evaluators, evidence schemas, research capability capsules, wrapper skills, and curated docs as import groups. |
| Manual merge boundary | ok | Shared files such as `README.md`, `AGENTS.md`, `CLAUDE.md`, `harness/solar-harness.sh`, operator registries, capsule registry, `bin/solar`, and `core/daemon/skill-dispatcher.ts` are explicitly marked manual-merge-only. |
| Local/generated state exclusion | ok | `.git`, `.DS_Store`, `__pycache__`, `*.pyc`, AutoSci run artifacts, operator smoke outputs, coordinator/watchdog/pane state, planner inbox, logs, and run directories are explicitly excluded. |
| Unified repo smoke checklist | ok | The manifest records the Phase C unified-repo smoke files still required after import, including route listing, CLI dispatch, ingest/review demo artifacts, scheduler lifecycle, and artifact-root isolation. |
| Static guard test | ok | Added `harness/tests/test_autosci_phase_c_unification_contracts.py` to enforce the manifest schema, import paths, excludes, manual-merge boundary, dispatcher boundary, and no-claim premerge verification policy. |

### Issues Encountered And Guardrails

| Issue | Status | Guardrail |
|---|---|---|
| Phase C can be misread as copying this branch over the Stellven product repo | warn | Keep `wholesale_copy_allowed=false`; import AutoSci modules selectively and merge shared runtime files manually. |
| Current working copy contains local state and generated cache files that must not enter the unified product repo | warn | Exclude `.DS_Store`, `__pycache__`, `*.pyc`, pane/coordinator/watchdog state, planner inbox, logs, and generated AutoSci artifacts. |
| Stellven `SkillDispatcher` can return instruction text with `executed=false` | warn | Do not treat it as the final AutoSci execution path until it dispatches AutoSci routes to the native shim or an equivalent execution bridge. |
| A premerge manifest is not proof that the Stellven merge or unified smoke tests already ran | warn | Keep `premerge_manifest_only=true` and require the listed `tests/integration/test_autosci_*.py` smokes after importing into the unified Solar repo. |

### Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/tests/test_autosci_phase_c_unification_contracts.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/test_autosci_phase_c_unification_contracts.py -q` | ok: 5 passed. |
| `git diff --check -- docs/integrations/autosci/phase-c-solar-unification-import-manifest.v1.json harness/tests/test_autosci_phase_c_unification_contracts.py docs/integrations/autosci/phase19-progress-log.md` | ok |
| `git fsck --connectivity-only --no-dangling` | ok |

## Phase C Product-Level Smoke And Cleanup Follow-up

Logged: 2026-07-01 EDT

| Item | Status | Evidence |
|---|---|---|
| Attachment review | ok | Read `/Users/jamesyuan/.codex/attachments/eb647a4d-8eca-40be-85ae-cdb20f7726ec/pasted-text.txt` and reconciled its P0 list against current code. |
| Product CLI dispatch status | ok | Current `harness/solar-harness.sh` already has `autosci)` dispatch and `$*)` direct AutoSci dispatch through `do_autosci_command()`, so the attachment's P0-1 blocker is no longer current. |
| Wrapper path status | ok | `.agents/skills/*/SKILL.md` direct `$command` examples are compatible with the current `$*)` dispatch path, while `solar-harness.sh autosci "$cmd"` remains the preferred explicit product path for tests. |
| Product-level integration smokes | ok | Added `harness/tests/integration/test_autosci_routes_list.py`, `test_autosci_cli_dispatch.py`, `test_autosci_ingest_demo.py`, `test_autosci_review_demo.py`, `test_autosci_research_scheduler_demo.py`, and `test_autosci_artifact_root.py` plus `autosci_product_smoke_helpers.py`. |
| Smoke isolation | ok | The new smokes run `solar-harness.sh autosci ...` through an isolated temporary `HARNESS_DIR`, asserting outputs remain under that root and do not appear under the repo harness artifact root. |
| Scheduler demo preset | ok | Added explicit `$research --scheduler-run --scheduler-demo`; the preset is paper-grounded and limited to `paper_ingest`, `paper_analyze`, `claim_extract`, and `method_extract` so it does not falsely pass model/provider-dependent nodes. |
| Tracked generated artifact cleanup | ok | Removed generated AutoSci artifacts from the Git index with `git rm --cached`, preserving local files: 2541 tracked run files, 62 operator-smoke files, and 62 phase19 inventory JSON files were cleaned from tracking; scientific workflow-runs had 0 tracked files. |
| Manifest update | ok | Updated `phase-c-solar-unification-import-manifest.v1.json` to map unified target smoke files to current-branch smoke files and to record generated-artifact cleanup policy. |

### Issues Encountered And Guardrails

| Issue | Status | Guardrail |
|---|---|---|
| The attachment's product CLI blocker was stale relative to the latest branch | warn | Verify current code before acting on inspection notes; `solar-harness.sh autosci` and direct `$*` dispatch now exist. |
| Product-level smoke tests initially had no files under `harness/tests/integration/test_autosci_*.py` | warn | Keep dedicated product-entry smokes separate from lower-level shim tests so a future Stellven merge can catch CLI/artifact-root regressions. |
| Test import failed because pytest collects `harness/tests/integration` as a package | warn | Use relative imports from `.autosci_product_smoke_helpers` inside integration tests. |
| `$ingest` route status is still `partial` even when `research_paper.v1` is written | warn | Tests assert the required typed evidence rather than overclaiming route completion. |
| `artifact_review.v1` stores `review_available` under `outputs.review`, not directly under `outputs` | warn | Assert the schema's actual structure to avoid brittle or misleading review readiness checks. |
| `git rm --cached` was blocked by sandbox permissions while creating `.git/index.lock` | warn | Use approved escalation for index-only cleanup; keep local generated files in place and rely on `.gitignore` after removing tracking. |
| A first draft of `--scheduler-demo` included `idea_generate` and failed because source/model evidence was missing | warn | Demo presets must not turn inconclusive model/provider-dependent nodes into success; keep deeper nodes explicit until supporting evidence is supplied. |

### Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/plugins/autosci/bin/autosci_skill_shim.py harness/tests/integration/autosci_product_smoke_helpers.py harness/tests/integration/test_autosci_routes_list.py harness/tests/integration/test_autosci_cli_dispatch.py harness/tests/integration/test_autosci_ingest_demo.py harness/tests/integration/test_autosci_review_demo.py harness/tests/integration/test_autosci_research_scheduler_demo.py harness/tests/integration/test_autosci_artifact_root.py harness/tests/test_autosci_phase_c_unification_contracts.py harness/plugins/autosci/tests/test_autosci_skill_shim.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/integration/test_autosci_routes_list.py harness/tests/integration/test_autosci_cli_dispatch.py harness/tests/integration/test_autosci_ingest_demo.py harness/tests/integration/test_autosci_review_demo.py harness/tests/integration/test_autosci_research_scheduler_demo.py harness/tests/integration/test_autosci_artifact_root.py -q` | ok: 6 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_research_scheduler_run_attaches_blocked_summary harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_research_scheduler_demo_uses_multi_node_preset -q` | ok: 2 passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/test_autosci_phase_c_unification_contracts.py -q` | ok: 5 passed. |
| `git ls-files 'harness/artifacts/autosci/runs/*' \| wc -l` | ok: 0. |
| `git ls-files 'harness/artifacts/autosci/operator-smoke/*' \| wc -l` | ok: 0. |
| `git ls-files 'harness/artifacts/autosci/phase19/current-parity-inventory-*.json' \| wc -l` | ok: 0. |
| `git ls-files 'harness/artifacts/scientific/workflow-runs/*' \| wc -l` | ok: 0. |
| `git diff --check -- docs/integrations/autosci/phase-c-solar-unification-import-manifest.v1.json docs/integrations/autosci/phase19-progress-log.md harness/plugins/autosci/bin/autosci_skill_shim.py harness/plugins/autosci/tests/test_autosci_skill_shim.py harness/tests/test_autosci_phase_c_unification_contracts.py harness/tests/integration/autosci_product_smoke_helpers.py harness/tests/integration/test_autosci_routes_list.py harness/tests/integration/test_autosci_cli_dispatch.py harness/tests/integration/test_autosci_ingest_demo.py harness/tests/integration/test_autosci_review_demo.py harness/tests/integration/test_autosci_research_scheduler_demo.py harness/tests/integration/test_autosci_artifact_root.py` | ok |
| `git fsck --connectivity-only --no-dangling` | ok |

## Phase C Premerge Readiness Audit Follow-up

Logged: 2026-07-01 EDT

| Item | Status | Evidence |
|---|---|---|
| Latest attachment review | ok | Read `/Users/jamesyuan/.codex/attachments/d1462411-4aa9-4a88-8f05-5410e3e21707/pasted-text.txt` and treated it as a premerge readiness note, not a merge-start instruction. |
| Merge not started | ok | No integration branch was created, no Stellven product branch was modified, and no fetch/merge/repack/maintenance command was run for this follow-up. |
| Wrapper CLI wording | ok | Updated `.agents/skills/*/SKILL.md` to prefer `solar-harness.sh autosci '$<skill> <user args>'`, matching the explicit product-level entrypoint requested by the attachment. |
| Readiness audit artifact | ok | Added `docs/integrations/autosci/phase-c-premerge-readiness-audit.v1.json` to record P0 reconciliation, no-merge activity, post-import gates, and residual risks. |
| Static readiness guard | ok | Added `harness/tests/test_autosci_phase_c_premerge_readiness.py` to verify product dispatch, wrapper wording, scheduler-demo coverage, product smoke presence, and generated artifact tracking hygiene. |
| Manifest linkage | ok | Linked the readiness audit from `phase-c-solar-unification-import-manifest.v1.json` without claiming the Stellven merge already happened. |

### Issues Encountered And Guardrails

| Issue | Status | Guardrail |
|---|---|---|
| The latest attachment still described missing product dispatch that current code already has | warn | Added a readiness audit that reconciles attachment P0 items against current files instead of redoing stale work. |
| Direct `$command` harness dispatch is supported, but wrapper docs could still look ambiguous for product merge | warn | Prefer explicit `autosci` subcommand in all wrapper docs while keeping direct dispatch as a supported convenience path. |
| `.agents/skills` was read-only under the sandbox during bulk wording update | warn | Used a single approved escalated write for wrapper docs only; no Git metadata, fetch, merge, maintenance, or runtime state was touched. |
| A readiness audit can be mistaken for a completed Stellven merge | warn | The audit and manifest explicitly record `does_not_claim_stellven_merge_executed=true` and `does_not_start_merge_branch=true`. |

### Verification Commands

| Command | Result |
|---|---|
| `harness/bin/python3 -m py_compile harness/tests/test_autosci_phase_c_premerge_readiness.py harness/tests/test_autosci_phase_c_unification_contracts.py` | ok |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/test_autosci_phase_c_premerge_readiness.py harness/tests/test_autosci_phase_c_unification_contracts.py -q` | ok: 10 passed. |
| `git diff --check -- docs/integrations/autosci/phase-c-premerge-readiness-audit.v1.json docs/integrations/autosci/phase-c-solar-unification-import-manifest.v1.json docs/integrations/autosci/phase19-progress-log.md harness/tests/test_autosci_phase_c_premerge_readiness.py harness/tests/test_autosci_phase_c_unification_contracts.py .agents/skills` | ok |
| `git fsck --connectivity-only --no-dangling` | ok |

## Phase C Local/CI Premerge Gate Follow-up

Logged: 2026-07-01 EDT

| Item | Status | Evidence |
|---|---|---|
| Latest attachment review | ok | Read `/Users/jamesyuan/.codex/attachments/3735d5e6-b4f4-4abf-a7d3-c368f88a54f0/pasted-text.txt`; it recommends entering integration branch only after local/CI smoke proof, not direct product-main merge. |
| Merge not started | ok | No integration branch was created, no Stellven branch was fetched/merged, and no product-main merge was attempted. |
| Local gate script | ok | Added `harness/tests/test-autosci-premerge-gate.sh` to run Phase C contracts, product-level AutoSci smokes, scheduler-demo shim tests, artifact tracking guard, and git connectivity check. |
| CI gate wiring | ok | Added `autosci-premerge-gate` to `.github/workflows/solar-ci.yml`; the job runs the same local script on PR/main CI. |
| Readiness audit update | ok | Updated `phase-c-premerge-readiness-audit.v1.json` to point at the latest attachment and record the local/CI gate without claiming full AutoSci parity. |
| Static guard update | ok | Extended `harness/tests/test_autosci_phase_c_premerge_readiness.py` to assert the gate is wired and does not contain fetch/merge/branch-creation commands. |

### Issues Encountered And Guardrails

| Issue | Status | Guardrail |
|---|---|---|
| The latest attachment explicitly says its judgment is inspection-based, not runtime proof | warn | Add a runnable premerge gate and CI job so future integration work has a concrete pass/fail command. |
| A CI gate could accidentally be read as permission to merge straight to product main | warn | Keep audit fields `direct_product_branch_merge_recommended=false`, `starts_merge_branch=false`, and `claims_full_autosci_parity=false`. |
| Product smokes may write temporary AutoSci artifacts if not isolated | warn | Gate reuses the existing product-level pytest smokes, which create isolated temporary `HARNESS_DIR` roots and assert repo run dirs are untouched. |

### Verification Commands

| Command | Result |
|---|---|
| `bash harness/tests/test-autosci-premerge-gate.sh` | ok: Phase C contracts 11 passed; product smokes 6 passed; scheduler-demo shim tests 2 passed; artifact tracking and git connectivity checks passed. |
| `env PYTHONPATH=harness harness/bin/python3 -m pytest harness/tests/test_autosci_phase_c_premerge_readiness.py harness/tests/test_autosci_phase_c_unification_contracts.py -q` | ok: covered by premerge gate. |
| `git diff --check -- .github/workflows/solar-ci.yml docs/integrations/autosci/phase-c-premerge-readiness-audit.v1.json docs/integrations/autosci/phase19-progress-log.md harness/tests/test-autosci-premerge-gate.sh harness/tests/test_autosci_phase_c_premerge_readiness.py` | ok |
| `git fsck --connectivity-only --no-dangling` | ok: covered by premerge gate. |
