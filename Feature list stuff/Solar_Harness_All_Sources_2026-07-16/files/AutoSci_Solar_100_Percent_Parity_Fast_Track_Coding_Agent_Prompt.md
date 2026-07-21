# Coding Agent Prompt — Fast-Track AutoSci-on-Solar to 100% Native Parity

You are the coding agent responsible for completing the AutoSci → Solar-native migration as fast as possible, without architectural shortcuts that would be rejected later.

Repository under work:

```bash
export SOLAR_REPO="/path/to/OpenSolar"
cd "$SOLAR_REPO"
git checkout ChatGPT-check
```

Native reference repository:

```bash
export AUTOSCI_REPO="/path/to/AutoSci"
# Native reference: https://github.com/Coconut-ch1ken/AutoSci
```

Your mission:

```text
Reach 100% practical native AutoSci parity inside Solar:
- all native AutoSci command families are supported;
- full /research lifecycle is executable as Solar-native workflow;
- every stage emits typed Evidence ABI;
- every runtime claim is gate-checked;
- no black-box AutoSciRunner owns the lifecycle;
- native AutoSci semantics are preserved using the fastest safe implementation path.
```

## 0. Non-negotiable architecture

Every capability must follow this model:

```text
TaskGraph node
  -> Logical operator
  -> Capability capsule
  -> Physical operator
  -> Implementation package
  -> Command
  -> Evidence ABI
  -> Gate / human-verifiable test
```

Rules:

```text
1. Do not create a black-box AutoSciRunner that owns the whole workflow.
2. Do not move AutoSci-specific implementation into Solar core.
3. AutoSci-specific code belongs under harness/plugins/autosci/ or a clearly bounded compatibility package.
4. Solar owns workflow semantics, TaskGraphs, evidence contracts, gates, resume, and lifecycle acceptance.
5. You may reuse/port native AutoSci code aggressively, but only as bounded backend actions per command/stage.
6. Do not claim full parity from routes, logs, or docs.
7. Full means command + evidence + gate + test + parity inventory all pass.
8. If a live provider is unavailable, implement the real provider integration and a deterministic mocked-provider contract test; mark live proof as env-gated rather than full live proof.
```

## 1. Current status you inherit

The branch already has:

```text
- 28 AutoSci-style skill routes.
- AutoSci plugin manifest declaring scientific research capabilities.
- Scientific logical operators.
- AutoSci physical workers.
- scientific_research_lifecycle_full_v1.json.
- autosci_skill_shim.py with $research --scheduler-run.
- run_scientific_node_smoke.py.
- run_scientific_lifecycle_smoke.py.
- lifecycle_runtime_gate.py.
- typed evidence gates.
- bridge actions for many commands.
- improved status semantics: partial/gated -> inconclusive, not completed.
```

Estimated parity is about 58%. Your job is to close the remaining ~42% quickly.

Biggest known gaps:

```text
P0:
- capability registry drift: plugin manifest declares cap.research-* but main registry may not.
- lifecycle runner is still smoke-specific/hardcoded.
- plain $research is still not scheduler-native by default.

P1:
- OmegaWiki parity incomplete.
- /ideate native 5-phase semantics incomplete.
- /exp-run native deploy/collect/full semantics incomplete.
- /paper-draft and publication parity incomplete.
- physical operators still use stub/local host ownership.
- live provider and remote execution proof incomplete.
```

## 2. Strategy: fastest safe route to 100%

Do not rebuild every native feature from scratch.

Use a two-layer strategy:

### Layer A — Solar-native control plane

Implement or complete:

```text
capability registry
generic workflow runner
strict lifecycle runtime gate
node runtime evidence
human gate resume
external-node blocked/resume
parity inventory
```

### Layer B — AutoSci-native compatibility backends

Port or call native AutoSci functionality as bounded stage-level backends:

```text
plugins/autosci/native_compat/
  native_repo.py
  command_runner.py
  evidence_normalizers.py
  research_wiki_native.py
  ideate_native.py
  exp_run_native.py
  paper_native.py
  research_pipeline_native.py
```

These modules may reuse native AutoSci tools/logic, but they must output Solar evidence and must not own the full lifecycle as one black-box action.

Acceptable:

```text
ScientificExperimentRunner node
  -> autosci-experiment-run-worker
  -> plugins/autosci/native_compat/exp_run_native.py deploy or collect
  -> experiment_result.v1 / experiment_status.v1
  -> gate
```

Not acceptable:

```text
ScientificWorkflowEvolver
  -> AutoSciRunner.run_everything()
  -> final report only
```

## 3. First commands to run

```bash
cd "$SOLAR_REPO"
git status --short
git branch --show-current

cd "$SOLAR_REPO/harness"
export HARNESS_DIR="$PWD"

python3 plugins/autosci/bin/autosci_skill_shim.py skills list | tee /tmp/autosci_routes.json
python3 -m json.tool /tmp/autosci_routes.json | sed -n '1,300p'

test -f tools/run_scientific_node_smoke.py
test -f tools/run_scientific_lifecycle_smoke.py
test -f evaluators/scientific/lifecycle_runtime_gate.py
test -f plugins/autosci/bin/autosci_skill_shim.py
test -f plugins/autosci/bin/autosci_bridge.py

python3 tools/run_scientific_node_smoke.py --help
python3 tools/run_scientific_lifecycle_smoke.py --help
python3 plugins/autosci/bin/autosci_skill_shim.py --help
python3 plugins/autosci/bin/autosci_bridge.py --help
```

Then inspect native AutoSci:

```bash
cd "$AUTOSCI_REPO"
sed -n '1,520p' README.md
sed -n '1,460p' .claude/skills/research/SKILL.md
sed -n '1,460p' .claude/skills/ideate/SKILL.md
sed -n '1,460p' .claude/skills/exp-run/SKILL.md
sed -n '1,360p' .claude/skills/paper-draft/SKILL.md
sed -n '1,360p' tools/research_wiki.py
```

## 4. P0 — Fix capability registry drift

The plugin manifest must match the central registry and existing capsule files.

Run:

```bash
cd "$SOLAR_REPO/harness"

python3 - <<'PY'
from pathlib import Path
import yaml

manifest = yaml.safe_load(Path("plugins/autosci/manifest.yaml").read_text())
registry = yaml.safe_load(Path("config/capability-capsules.registry.yaml").read_text())

manifest_caps = set(manifest["capabilities"])
registry_caps = {
    item.get("capability_capsule_id")
    for item in registry.get("capsules", {}).get("capability", [])
    if isinstance(item, dict)
}
missing = sorted(manifest_caps - registry_caps)

print("manifest caps:", len(manifest_caps))
print("registry caps:", len(registry_caps))
print("missing:", missing)

for cap in sorted(manifest_caps):
    capsule_path = Path("capability-capsules") / f"{cap}.yaml"
    if not capsule_path.exists():
        print("missing capsule file:", capsule_path)

raise SystemExit(1 if missing else 0)
PY
```

If missing entries exist, patch:

```text
harness/config/capability-capsules.registry.yaml
```

Add entries for all manifest capabilities:

```text
cap.research-literature-discover
cap.research-paper-ingest
cap.research-paper-analyze
cap.research-memory-update
cap.research-graph-update
cap.research-claim-extract
cap.research-method-extract
cap.research-code-evidence-map
cap.research-idea-generate
cap.research-idea-evaluate
cap.research-experiment-design
cap.research-experiment-run
cap.research-experiment-monitor
cap.research-claim-verify
cap.research-report-plan
cap.research-report-draft
cap.research-artifact-review
cap.research-publication-produce
cap.research-workflow-evolve
```

Add test:

```text
harness/tests/config/test_autosci_research_capsule_registry.py
```

It must fail if:

```text
- plugin manifest capability is missing from registry;
- route capability is missing from registry;
- registry manifest_path does not exist;
- capability file exists but is not registered.
```

## 5. P0 — Make scheduler-native run the acceptance path

### 5.1 Prove node runtime path

Run:

```bash
cd "$SOLAR_REPO/harness"
export HARNESS_DIR="$PWD"

python3 tools/run_scientific_node_smoke.py \
  --harness-dir "$PWD" \
  --operator-id autosci-paper-ingest-worker \
  --node-id paper_ingest \
  --logical-operator ScientificPaperIngestor \
  --action ingest_paper \
  --expected-schema research_paper.v1 \
  --paper plugins/autosci/tests/fixtures/sample_paper.md \
  --task-id task-autosci-node-paper-ingest \
  --sprint-id sprint-autosci-node-smoke \
  --output-dir artifacts/scientific/node-smoke/paper_ingest \
  --out artifacts/scientific/node-smoke/paper_ingest/summary.json
```

Must pass:

```text
operator_runtime_submit == ok
operatord_result_written == ok
bridge_result_completed == ok
evidence schema correct
gate passed
operator_result_path exists
bridge_result_path exists
evidence_path exists
```

Then make these nodes pass:

```text
paper_ingest
claim_extract
experiment_run
report_draft
publication_produce
workflow_evolve
```

### 5.2 Prove `$research --scheduler-run`

```bash
cd "$SOLAR_REPO/harness"
export HARNESS_DIR="$PWD"

python3 plugins/autosci/bin/autosci_skill_shim.py text \
  '$research scheduler lifecycle --scheduler-run --scheduler-include-blocked-external --run-id scheduler-branch-check'
```

Must produce:

```text
status != failed
scheduler_lifecycle_summary_path
scheduler_lifecycle_node_count > 0
scheduler_workflow_config_alignment_status == aligned
```

Validate:

```bash
SUMMARY="<path-from-output>"
python3 -m json.tool "$SUMMARY" | sed -n '1,360p'
python3 evaluators/scientific/lifecycle_runtime_gate.py "$SUMMARY"
```

Blocked external nodes are acceptable only if:

```text
runtime gate returns inconclusive, not failed;
blocked nodes have reason;
blocked nodes have required_evidence;
blocked nodes have unblock_condition;
all unblocked nodes have node_results + gate_results + artifact hashes.
```

## 6. P0 — Build generic workflow runner

Create:

```text
harness/tools/run_scientific_workflow.py
```

Required command:

```bash
python3 tools/run_scientific_workflow.py \
  --workflow workflows/scientific_research_lifecycle_full_v1.json \
  --job-id <job_id> \
  --mode fixture \
  --include-blocked-external \
  --out artifacts/scientific/<job_id>/scientific_lifecycle_runtime.json
```

Required implementation:

```text
1. Load workflow JSON.
2. Use workflow nodes and depends_on as source of truth.
3. Resolve logical_operator -> physical_operator.
4. Resolve required_capabilities -> registered capsule.
5. Construct one envelope per node.
6. Submit each node via operator_runtime.submit.
7. Run deterministic evidence gate.
8. Write node_results and gate_results.
9. Support blocked external/human nodes.
10. Support --resume-summary.
11. Do not rerun completed nodes.
12. Write strict scientific_lifecycle.v1.
13. Run lifecycle_runtime_gate.py before returning success.
```

Keep:

```text
tools/run_scientific_lifecycle_smoke.py
```

as a compatibility wrapper around the generic runner once stable.

## 7. P1 — Make plain `$research` scheduler-native by default

Currently plain `$research` still uses `run_research_lifecycle` projection. Change behavior:

```text
$research ...                 -> scheduler-native by default
$research ... --projection-only -> old bridge/projection mode
```

Implementation:

```text
- Add --projection-only flag.
- If skill == research and not smoke and not projection_only:
    run scheduler workflow runner.
- Still attach run_research_lifecycle projection after scheduler summary, but do not treat projection as lifecycle owner.
- If scheduler fails, overall run fails.
```

Acceptance:

```bash
python3 plugins/autosci/bin/autosci_skill_shim.py text \
  '$research tiny scheduler test --run-id default-scheduler-check'
```

Expected:

```text
scheduler_lifecycle_summary_path present
scheduler_lifecycle_node_count > 0
not projection-only
```

## 8. P1 — Port OmegaWiki parity

OpenSolar’s current `tools/research_wiki.py` is narrower than native AutoSci. Implement a superset, not a breaking replacement.

Required commands:

```text
init
slug
log
read-meta
set-meta
add-edge
add-citation
batch-edges
dedup-edges
dedup-citations
find
query
neighbors
compile-context
rebuild-context-brief
rebuild-open-questions
rebuild-index
transition
stats
maturity
checkpoint-save
checkpoint-load
checkpoint-clear
checkpoint-set-meta
checkpoint-get-meta
```

Fastest route:

```text
- Port native AutoSci tools/research_wiki.py into plugins/autosci/native_compat/research_wiki_native.py.
- Expose compatible command surface in root tools/research_wiki.py.
- Preserve OpenSolar path confinement and evidence write semantics.
- Add schema-backed edge/citation validation using native runtime loader logic, copied or adapted under plugins/autosci/native_compat/runtime/.
```

Tests:

```text
tests/tools/test_research_wiki_native_compat.py
```

Must cover:

```text
init creates full wiki tree;
add-edge validates endpoints;
add-citation writes citations.jsonl;
dedup removes duplicates;
transition accepts legal transitions and rejects illegal ones;
maturity returns cold/warm/hot;
checkpoint save/load/clear works;
compile-context and rebuild-open-questions produce files.
```

## 9. P1 — Native `/ideate` parity

Implement full native five-phase behavior as bounded Solar evidence.

Required behavior:

```text
1. Check wiki maturity.
2. Load context_brief and open_questions.
3. Load failed idea banlist.
4. Load active ideas for dedup.
5. External discovery evidence: Web/S2/DeepXiv/arXiv.
6. Dual-model brainstorm:
   - model A evidence
   - Review LLM evidence
7. Enforce generation paths A/B/C/D/E.
8. Merge/dedup candidates.
9. First-pass filter.
10. Deep validation via novelty and review.
11. Write accepted ideas.
12. Write eliminated ideas with failure_reason.
13. Add graph edges.
14. Rebuild context/open questions.
15. Optional pilot handoff.
16. Growth report.
```

Fastest route:

```text
- Implement plugins/autosci/native_compat/ideate_native.py.
- Reuse native SKILL.md semantics as the implementation spec.
- Accept explicit model_evidence, review_llm_evidence, discovery_evidence, novelty_evidence.
- If evidence missing, return inconclusive with exact missing fields.
- Do not fabricate ideas unless --smoke.
```

Evidence:

```text
idea_candidate.v1
idea_evaluation.v1
research_memory_update.v1
research_graph_update.v1
ideate_pipeline_report.v1 sidecar
```

Tests:

```text
test_ideate_requires_external_or_model_evidence_without_smoke
test_ideate_writes_accepted_and_eliminated_ideas
test_ideate_generation_paths_A_to_E
test_ideate_failed_banlist_blocks_duplicate
test_ideate_pilot_handoff_gated
```

## 10. P1 — Native `/exp-run` parity

Implement native deploy / collect / full semantics.

Required behavior:

```text
Deploy mode:
- read wiki/experiments/{slug}.md;
- require status planned;
- inspect linked idea and related paper/method context;
- inspect dataset/config;
- generate experiments/code/{slug}/:
  train.py, config.yaml, run.sh, requirements.txt;
- optional Review LLM code review;
- sanity check;
- require manual approval before launch;
- local launch through screen or approved local equivalent;
- remote launch through tools/remote.py equivalent;
- update experiment status to running;
- write DEPLOY_REPORT.

Collect mode:
- require status running;
- check local/remote process;
- if still running: report only, no wiki mutation;
- if completed: pull results if remote;
- parse results/{slug}/seed_*.json;
- compute mean ± std metrics;
- classify succeeded / failed / inconclusive;
- update wiki experiment page;
- write RUN_REPORT;
- update collection ledger;
- avoid duplicate mutation.

Full mode:
- deploy then wait/poll then collect.
```

Fastest route:

```text
- Implement plugins/autosci/native_compat/exp_run_native.py.
- Use approved local command execution already present.
- Add native-style codegen and report artifacts.
- Add remote.py wrapper only if config/server.yaml and approval evidence exist.
```

Evidence:

```text
experiment_plan.v1
experiment_result.v1
experiment_status.v1
research_memory_update.v1
approval_contract.v1 sidecar
collection_ledger.v1 sidecar
deploy_report.md
run_report.md
```

Tests:

```text
test_exp_run_deploy_requires_approval
test_exp_run_deploy_generates_code_dir
test_exp_run_collect_running_does_not_mutate_wiki
test_exp_run_collect_completed_updates_wiki
test_exp_run_collect_duplicate_is_idempotent
test_exp_run_multiseed_mean_std
test_exp_run_remote_requires_config_and_approval
```

## 11. P1 — Native `/paper-draft`, `/paper-compile`, `/poster`, `/rebuttal`

### `/paper-draft`

Must generate:

```text
paper/main.tex
paper/math_commands.tex
paper/references.bib
paper/sections/introduction.tex
paper/sections/related_work.tex
paper/sections/method.tex
paper/sections/experiments.tex
paper/sections/conclusion.tex
paper/figures/
paper/tables/
```

Must implement:

```text
PAPER_PLAN parsing
venue template copy/fallback
figure/table plan execution
section material collection from wiki
citation plan
BibTeX verification
de-AI polish pass
optional section Review LLM
optional full-paper Review LLM
integrity checks for input/includegraphics/cite/ref
```

### `/paper-compile`

Must implement:

```text
latexmk / pdflatex approved execution
auto-fix using after_artifact evidence
page count check
anonymity check
font/checklist diagnostics
publication_bundle.v1
```

### `/poster`

Must implement:

```text
PaperX-style DAG extraction
HTML poster
overflow validation
optional approved browser PNG render
```

### `/rebuttal`

Must implement:

```text
review comment atomization
mapping concerns to wiki/evidence
Review LLM stress-test
rebuttal.md
response map JSON
```

Fastest route:

```text
- Implement plugins/autosci/native_compat/paper_native.py.
- Reuse native paper-draft / paper-compile / poster / rebuttal SKILL.md behavior.
- Make all file writes explicit and evidence-backed.
```

Tests:

```text
test_paper_draft_creates_full_paper_tree
test_paper_draft_bibtex_integrity
test_paper_draft_section_evidence_map
test_paper_compile_requires_approval_for_latex
test_paper_compile_generates_publication_bundle
test_poster_generates_html_and_gated_png
test_rebuttal_maps_review_comments_to_evidence
```

## 12. P1 — Native `/research` parity

Native `/research` must be implemented as Solar workflow, not one bridge action.

Required state machine:

```text
Stage 0: Bootstrap
Stage 1: Idea Discovery
Gate 1: Select Idea
Stage 2: Experiment Design
Stage 3a: Deploy All
Stage 3b: Await
Stage 3c: Collect
Stage 4: Verdict & Iteration
Gate 2: Confirm Paper Ready
Stage 5: Paper Writing
Final: Pipeline report + memory/evolution
```

Required native resume modes:

```text
--start-from stage1
--start-from stage2
--start-from stage3
--start-from stage3-collect
--start-from stage3-check
--start-from stage4
--start-from stage5
```

Required files:

```text
wiki/outputs/pipeline-progress.md
wiki/outputs/PIPELINE_REPORT.md
wiki/log.md
paper/ directory if not --skip-paper
scientific_lifecycle.v1
evidence.jsonl
```

Implementation:

```text
- Use generic run_scientific_workflow.py as runtime engine.
- Model human gates as explicit blocked nodes.
- Model Stage 3b await as blocked/waiting state, not failure.
- Resume must skip completed nodes.
- Do not use run_research_lifecycle as owner; it may project a human report after scheduler evidence.
```

Tests:

```text
test_research_cold_bootstrap
test_research_gate1_block_resume
test_research_stage3_await_block
test_research_stage3_collect_resume
test_research_failed_baseline_terminates
test_research_iteration_refine_once
test_research_skip_paper
test_research_full_fixture_to_publication
```

## 13. P2 — Live provider proof

Implement provider integration and env-gated tests.

Providers:

```text
Semantic Scholar
DeepXiv
arXiv
Paper Copilot
Review LLM OpenAI-compatible endpoint
latexmk / TeX
optional SMTP
optional browser rendering
optional remote experiment host
```

Rules:

```text
- Mock/fixture tests must pass in CI.
- Live tests run only if env vars/config exist.
- Do not claim live provider parity if env missing.
```

Add:

```text
tests/providers/test_autosci_provider_contracts.py
tests/providers/test_autosci_live_providers_env_gated.py
```

## 14. P2 — Parity inventory and route promotion

Create:

```text
harness/tools/autosci_parity_inventory.py
```

It must compute:

```text
route_count
full_count
partial_count
gated_count
missing_route_count
manifest_registry_drift
capsule_registry_missing
workflow_node_count
workflow_runtime_proof_status
node_runtime_proof_status
omega_wiki_parity_status
ideate_parity_status
experiment_parity_status
publication_parity_status
research_lifecycle_parity_status
live_provider_status
native_command_parity_by_command
```

Rules for setting `coverage_status: full`:

```text
A route can be full only when:
1. route exists;
2. capability is registered;
3. capsule file exists;
4. logical operator exists;
5. physical operator exists;
6. backend action exists;
7. evidence schema exists;
8. deterministic gate exists;
9. fixture/native contract test passes;
10. if the route has side effects, approval-gated execution test passes;
11. parity inventory recognizes it as full.
```

Do not manually mark all routes full before acceptance.

## 15. Required acceptance commands before final report

Run:

```bash
cd "$SOLAR_REPO/harness"
export HARNESS_DIR="$PWD"

python3 -m pytest \
  tests/config/test_autosci_research_capsule_registry.py \
  plugins/autosci/tests \
  tests/evaluators/scientific \
  tests/tools/test_research_wiki_native_compat.py \
  tests/scientific

python3 tools/autosci_parity_inventory.py \
  --native-repo "$AUTOSCI_REPO" \
  --out artifacts/autosci/parity_inventory.json

python3 plugins/autosci/bin/autosci_skill_shim.py text \
  '$research full fixture parity --scheduler-run --scheduler-include-human-gates --scheduler-include-blocked-external --run-id final-full-parity-fixture'

python3 evaluators/scientific/lifecycle_runtime_gate.py \
  artifacts/scientific/final-full-parity-fixture/scientific_lifecycle_runtime.json
```

Final report must include:

```text
- exact commands run;
- pass/fail output;
- generated artifacts;
- parity inventory JSON;
- any env-gated provider tests not run;
- routes still not full, if any.
```

## 16. Definition of 100% parity for this migration

You may claim 100% parity only when:

```text
[ ] All native AutoSci commands are represented.
[ ] All routes are backed by real code, not just route config.
[ ] All capabilities are registered and have capsule files.
[ ] All workflow nodes resolve logical -> capability -> physical -> backend action.
[ ] Full /research runs through Solar scheduler, not black-box AutoSciRunner.
[ ] Every unblocked node emits typed Evidence ABI.
[ ] Every unblocked node passes deterministic gate.
[ ] Blocked external/human nodes are explicit and resumable.
[ ] OmegaWiki command surface is native-compatible.
[ ] /ideate has full 5-phase semantics.
[ ] /exp-run supports deploy, collect, full, local/remote gated paths.
[ ] /paper-draft produces full paper/ tree.
[ ] /paper-compile produces publication_bundle.v1 and compile diagnostics/PDF when approved.
[ ] /poster and /rebuttal produce native-equivalent artifacts.
[ ] parity_inventory reports 100% with no silent skipped areas.
```

If live provider credentials are unavailable, report:

```text
Code parity: 100%
Live provider proof: env-gated, not executed
```

Do not call that production parity.

## 17. Final instruction

Work in the fastest safe order:

```text
1. Registry drift.
2. Node runtime proof.
3. Generic workflow runner.
4. $research scheduler-native default.
5. OmegaWiki parity.
6. /ideate parity.
7. /exp-run parity.
8. /paper-draft / compile / poster / rebuttal parity.
9. Provider contracts.
10. Parity inventory and route promotion.
```

Every PR/commit must include a test or executable proof. Do not stop at docs. Do not ask for clarification unless a required secret or remote host is needed; instead implement fixture/mocked-provider parity and clearly mark live proof as env-gated.
