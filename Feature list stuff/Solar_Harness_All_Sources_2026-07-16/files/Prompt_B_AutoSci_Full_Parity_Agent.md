# Agent B Prompt — AutoSci Full-Parity Continuation

## Working folder

You must work in the AutoSci integration repo, not in BetterSolar:

```bash
/Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar
```

Recommended to avoid interfering with Agent A: create a dedicated worktree or branch.

Preferred new worktree:

```bash
/Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar-autosci-parity
```

Native AutoSci reference is read-only:

```bash
/Users/jamesyuan/Developer/Github Repos (On Git)/AutoSci
```

Do not edit the Stellven/BetterSolar integration branch. Agent A owns that.

---

## Mission

Continue improving AutoSci full native parity inside the AutoSci module while preserving the integration contract that Agent A is porting into BetterSolar.

Your goal is to move route statuses from `partial` / `gated` toward real `full` only when evidence, gates, and tests prove it.

Current route inventory:

```text
route_count = 28
partial = 17
gated = 11
full = 0
```

Do not promote any route to `full` unless all acceptance requirements are satisfied.

---

## Background

Current integration branch:

```text
repo: /Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar
branch: feature/autosci-solar-native
HEAD: 9d68c5baa
```

Native AutoSci reference:

```text
repo: /Users/jamesyuan/Developer/Github Repos (On Git)/AutoSci
branch: main
HEAD: 71469e8
```

AutoSci parity is incomplete in these high-risk areas:

```text
- /ideate full five-phase/provider-backed novelty path
- /exp-run deploy/collect/full local + remote gated execution
- /paper-draft full paper tree and evidence-linked citations
- /paper-compile TeX/PDF/submission checks
- /poster and /rebuttal
- Review LLM proof
- live provider proof
- remote-host proof
```

Provider readiness from the information report:

```text
SEMANTIC_SCHOLAR_API_KEY: absent
DEEPXIV_TOKEN: absent
LLM_API_KEY: absent
LLM_BASE_URL: absent
LLM_MODEL: absent
OPENAI_API_KEY: present
ANTHROPIC_API_KEY: absent
ANTHROPIC_AUTH_TOKEN: absent

TeX tools:
  pdflatex present
  xelatex present
  lualatex present
  latexmk apparently not found in captured command output

Remote tools:
  rsync present
  ssh present
  screen present

Remote configs:
  harness/config/remote.yaml absent
  harness/config/server.yaml absent
```

Therefore, provider/remote parity must be implemented as:

```text
- env-gated live path where credentials/config exist;
- deterministic mock/fixture contract tests for CI;
- explicit blocked/inconclusive status when evidence is missing.
```

---

## Non-negotiable architecture

Preserve this architecture:

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
1. No black-box AutoSciRunner.
2. Native AutoSci repo remains reference-only.
3. Do not write into native AutoSci repo.
4. Do not write into BetterSolar.
5. Do not change product-level CLI behavior unless explicitly coordinated with Agent A.
6. Preserve artifact root variables:
   - HARNESS_DIR
   - SOLAR_AUTOSCI_OUTPUT_HARNESS
   - AUTOSCI_ARTIFACT_ROOT
   - SCIENTIFIC_ARTIFACT_ROOT
7. Evidence ABI changes must be additive or backward-compatible unless absolutely necessary.
8. Every completed claim must have typed evidence and a deterministic gate.
9. Missing provider/runtime evidence must produce blocked or inconclusive, not fake success.
```

---

## Safety constraints

Do not:

```text
- push without user approval;
- touch BetterSolar;
- change bin/solar;
- refactor product installer/desktop/distribution;
- delete user files;
- run real remote experiments without explicit approval;
- send emails;
- write or print secrets;
- fabricate live provider success;
- mark routes full from route config alone.
```

Allowed:

```text
- edit harness/plugins/autosci/**
- edit harness/tools/research_wiki.py and AutoSci-related tools
- edit harness/evaluators/scientific/**
- edit harness/schemas/evidence/**
- edit harness/workflows/scientific_*.json
- edit harness/capability-capsules/cap.research-*.yaml
- edit harness/plugins/autosci/config/feature_parity_routes.v1.json cautiously
- add tests under harness/plugins/autosci/tests
- add tests under harness/tests/evaluators/scientific
- add AutoSci-specific integration tests if needed
```

Avoid editing these unless explicitly required and documented:

```text
harness/solar-harness.sh
bin/solar
core/daemon/skill-dispatcher.ts
desktop/**
distribution/**
components.d/**
```

---

## Step 0 — Create a safe parity work branch/worktree

If the OpenSolar repo is dirty, do not clean it. Create a worktree from the current branch.

```bash
export OPEN_SOLAR_REPO="/Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar"
export PARITY_WORKTREE="/Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar-autosci-parity"
export NATIVE_AUTOSCI_REPO="/Users/jamesyuan/Developer/Github Repos (On Git)/AutoSci"

cd "$OPEN_SOLAR_REPO"
git status --short

# Preferred if worktree does not exist:
git worktree add "$PARITY_WORKTREE" feature/autosci-solar-native

cd "$PARITY_WORKTREE"
git checkout -b feature/autosci-full-parity-continuation
git status --short
```

If worktree creation fails because branch is already checked out, create a new branch in the existing OpenSolar checkout only after verifying the user accepts working there.

---

## Step 1 — Establish current test baseline

```bash
cd "$PARITY_WORKTREE/harness"
export HARNESS_DIR="$PWD"

python3 -m pytest -q \
  tests/integration/test_autosci_routes_list.py \
  tests/integration/test_autosci_cli_dispatch.py \
  tests/integration/test_autosci_ingest_demo.py \
  tests/integration/test_autosci_review_demo.py \
  tests/integration/test_autosci_research_scheduler_demo.py \
  tests/integration/test_autosci_artifact_root.py

python3 -m pytest --collect-only \
  plugins/autosci/tests \
  tests/evaluators/scientific \
  tests/integration/test_autosci_*.py
```

Record results.

Do not start changing code until baseline is known.

---

## Step 2 — Generate a deterministic parity inventory

If no up-to-date parity inventory tool exists, create:

```text
harness/tools/autosci_parity_inventory.py
```

It must report:

```text
route_count
full_count
partial_count
gated_count
missing_route_count
manifest_registry_drift
route_capabilities_missing_from_registry
route_logical_operators_missing
route_physical_operator_binding_missing
route_evidence_schemas_missing
route_backend_actions_missing
route_gate_missing
native_command_parity_by_command
provider_live_proof_status
remote_experiment_proof_status
paper_compile_proof_status
review_llm_proof_status
```

Rules:

```text
- Full cannot be manually asserted.
- Full requires route + capability + operator + physical worker + backend action + schema + gate + product/module test.
- Provider/live features can be env-gated, but env-gated absence cannot count as live proof.
```

Run:

```bash
python3 tools/autosci_parity_inventory.py \
  --native-repo "$NATIVE_AUTOSCI_REPO" \
  --out artifacts/autosci/parity_inventory_current.json
```

If this file writes under `artifacts/`, ensure it is ignored or not committed unless it is an intentionally small fixture.

---

## Step 3 — Prioritize parity by integration value

Do not randomly implement all AutoSci commands. Prioritize this order:

```text
P1. OmegaWiki / research_wiki native compatibility
P2. /ideate full five-phase pipeline
P3. /exp-run deploy/collect/full local + remote-gated behavior
P4. /paper-draft full paper tree
P5. /paper-compile TeX/PDF/submission checks
P6. /poster render path
P7. /rebuttal reviewer-thread/stress-test/submission audit
P8. live provider env-gated tests
```

Reason:

```text
- OmegaWiki supports many commands.
- /ideate, /exp-run, /paper-draft, /paper-compile are the biggest semantic gaps.
- /research depends on all of them.
```

---

## Step 4 — Native AutoSci reference inspection

Read native reference before implementing each area.

```bash
cd "$NATIVE_AUTOSCI_REPO"

sed -n '1,520p' tools/research_wiki.py
sed -n '1,520p' .claude/skills/ideate/SKILL.md
sed -n '1,520p' .claude/skills/exp-run/SKILL.md
sed -n '1,520p' .claude/skills/exp-status/SKILL.md
sed -n '1,520p' .claude/skills/exp-eval/SKILL.md
sed -n '1,520p' .claude/skills/paper-draft/SKILL.md
sed -n '1,520p' .claude/skills/paper-compile/SKILL.md
sed -n '1,520p' .claude/skills/research/SKILL.md
sed -n '1,420p' .claude/skills/review/SKILL.md
sed -n '1,420p' .claude/skills/novelty/SKILL.md
sed -n '1,420p' .claude/skills/rebuttal/SKILL.md
sed -n '1,420p' .claude/skills/poster/SKILL.md
```

Create or update:

```text
docs/integrations/autosci/native-parity-gap-matrix.md
```

This must map each native behavior to:

```text
implemented
partial
gated
missing
test path
evidence schema
gate
```

---

## Step 5 — OmegaWiki parity slice

Target files:

```text
harness/tools/research_wiki.py
harness/plugins/autosci/bin/autosci_bridge.py
harness/plugins/autosci/tests/
harness/schemas/evidence/research_memory_update.v1.schema.json
harness/schemas/evidence/research_graph_update.v1.schema.json
harness/evaluators/scientific/memory_update_gate.py
```

Implement native-compatible commands if missing:

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

Acceptance tests:

```text
test_research_wiki_init_creates_tree
test_research_wiki_add_citation_and_dedup
test_research_wiki_legal_transition
test_research_wiki_illegal_transition
test_research_wiki_checkpoint_save_load_clear
test_research_wiki_compile_context
test_research_wiki_rebuild_open_questions
```

Required behavior:

```text
- invalid transitions fail;
- citation dedup works;
- context compilation produces files;
- checkpoint load restores state or explicitly reports missing checkpoint;
- all writes are under supplied wiki root;
- no native AutoSci repo mutation.
```

---

## Step 6 — `/ideate` full semantic path

Target files:

```text
harness/plugins/autosci/bin/autosci_bridge.py
harness/plugins/autosci/config/feature_parity_routes.v1.json
harness/schemas/evidence/idea_candidate.v1.schema.json
harness/schemas/evidence/idea_evaluation.v1.schema.json
harness/evaluators/scientific/idea_gate.py
harness/plugins/autosci/tests/
```

Native features to implement or gate explicitly:

```text
wiki maturity scan
context_brief and open_questions loading
failed idea banlist
active idea dedup
source evidence / external discovery evidence
generation paths A/B/C/D/E
dual-model brainstorming evidence
first-pass filter
deep novelty validation
Review LLM review
accepted ideas writeback
eliminated ideas writeback
pilot handoff boundary
growth report
```

Rules:

```text
- Without model/provider evidence, do not claim final novelty.
- Fixture output requires explicit --smoke.
- Provider absent means inconclusive or blocked, not completed.
- Accepted idea promotion requires novelty + review evidence.
```

Tests:

```text
test_ideate_requires_model_or_smoke
test_ideate_generation_paths_A_to_E
test_ideate_failed_idea_banlist
test_ideate_active_idea_dedup
test_ideate_with_supplied_model_and_review_evidence_promotes
test_ideate_without_review_evidence_inconclusive
```

---

## Step 7 — `/exp-run` and `/exp-status` parity

Target files:

```text
harness/plugins/autosci/bin/autosci_bridge.py
harness/tools/remote.py
harness/schemas/evidence/experiment_plan.v1.schema.json
harness/schemas/evidence/experiment_status.v1.schema.json
harness/schemas/evidence/experiment_result.v1.schema.json
harness/evaluators/scientific/experiment_plan_gate.py
harness/evaluators/scientific/experiment_result_gate.py
harness/plugins/autosci/tests/
```

Implement or gate:

```text
experiment code directory generation
dataset/config inspection report
manual approval artifact
sanity check
approved local command execution
screen/session launch if safe
remote.py status/gpu/sync/setup/launch/check/tail/pull-results wrappers
runtime evidence
result collection
collection ledger
duplicate collection detection
multi-seed mean ± std metrics
wiki experiment status mutation
DEPLOY_REPORT
RUN_REPORT
```

Rules:

```text
- Remote mode requires config and approval.
- Local execution requires approval or fixture mode.
- If still running, status reports only; do not mutate final result.
- Missing result files => inconclusive.
- Crash/OOM/NaN logs => failed or inconclusive with reason.
- Duplicate collection must not duplicate wiki mutation.
```

Tests:

```text
test_exp_run_deploy_requires_approval
test_exp_run_generates_code_dir
test_exp_run_approved_local_command_writes_runtime_evidence
test_exp_status_running_does_not_mutate_wiki
test_exp_collect_completed_updates_wiki
test_exp_collect_duplicate_is_idempotent
test_exp_multiseed_mean_std
test_exp_remote_requires_config_and_approval
```

---

## Step 8 — `/paper-draft` full paper tree

Target files:

```text
harness/plugins/autosci/bin/autosci_bridge.py
harness/schemas/evidence/scientific_report.v1.schema.json
harness/evaluators/scientific/report_gate.py
harness/plugins/autosci/tests/
```

Implement:

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
venue template fallback
citation plan
BibTeX verification
figure/table plan
section evidence map
Review LLM section evidence if supplied
full-paper review evidence if supplied
de-AI polish boundary
```

Rules:

```text
- unsupported claims must be marked.
- citations must be backed by evidence or marked UNCONFIRMED.
- no final manuscript readiness without compile/PDF handoff.
```

Tests:

```text
test_paper_draft_creates_full_paper_tree
test_paper_draft_references_bib_exists
test_paper_draft_section_evidence_map
test_paper_draft_unconfirmed_citations_marked
test_paper_draft_review_llm_boundary
```

---

## Step 9 — `/paper-compile` parity

Target files:

```text
harness/plugins/autosci/bin/autosci_bridge.py
harness/schemas/evidence/publication_bundle.v1.schema.json
harness/evaluators/scientific/publication_gate.py or report_gate.py
harness/plugins/autosci/tests/
```

Implement:

```text
latexmk/pdflatex/xelatex/lualatex approved execution
compile command allowlist
before/after artifacts
runtime evidence
PDF structural checks
page count
font size check if possible
anonymous/double-blind check
submission profile
submission audit evidence
auto-fix proposal, but not automatic unsafe mutation
publication_bundle.v1
```

Rules:

```text
- TeX execution is side-effect gated.
- If latexmk unavailable but pdflatex exists, use fallback if explicitly approved.
- Missing TeX tool => inconclusive, not complete.
- Portal upload is never claimed without external submission audit evidence.
```

Tests:

```text
test_paper_compile_requires_approval
test_paper_compile_pdflatex_fallback
test_paper_compile_writes_publication_bundle
test_paper_compile_page_anonymity_checks
test_paper_compile_missing_tool_inconclusive
```

---

## Step 10 — `/poster` and `/rebuttal`

Poster:

```text
wiki2dag extraction
HTML poster generation
overflow validation
optional browser PNG render, approval-gated
publication_bundle.v1
```

Rebuttal:

```text
reviewer thread evidence ingestion
comment atomization
evidence mapping
response drafting
Review LLM stress-test if supplied
formal rebuttal export
submission audit boundary
```

Tests:

```text
test_poster_generates_html
test_poster_render_requires_approval
test_rebuttal_atomizes_reviewer_comments
test_rebuttal_maps_comments_to_evidence
test_rebuttal_submission_audit_boundary
```

---

## Step 11 — Keep product-level integration tests passing

After every meaningful change, run:

```bash
cd "$PARITY_WORKTREE/harness"

python3 -m pytest -q \
  tests/integration/test_autosci_routes_list.py \
  tests/integration/test_autosci_cli_dispatch.py \
  tests/integration/test_autosci_ingest_demo.py \
  tests/integration/test_autosci_review_demo.py \
  tests/integration/test_autosci_research_scheduler_demo.py \
  tests/integration/test_autosci_artifact_root.py
```

Also run relevant module tests:

```bash
python3 -m pytest -q plugins/autosci/tests tests/evaluators/scientific
```

If a change breaks product-level dispatch or artifact-root isolation, fix before continuing.

---

## Step 12 — Route status promotion policy

Do not set `coverage_status: full` unless:

```text
1. route exists;
2. capability registered;
3. capsule file exists;
4. logical operator exists;
5. physical operator exists;
6. backend action exists;
7. evidence schema exists;
8. deterministic gate exists;
9. native semantic behavior implemented or explicitly out of route scope;
10. product/module tests pass;
11. provider/remote/side-effect requirements are live-proven or explicitly gated and not part of claimed full status;
12. parity inventory reports full.
```

If unsure, leave route as:

```text
partial
```

or:

```text
gated
```

Update `limitations` with exact remaining evidence requirements.

---

## Step 13 — Final output expected from Agent B

Produce a report:

```text
docs/integrations/autosci/full-parity-progress-report.md
```

Include:

```text
1. branch/worktree used;
2. native AutoSci files inspected;
3. routes improved;
4. files changed;
5. tests added;
6. tests run and results;
7. routes still partial/gated and why;
8. provider/live paths still env-gated;
9. any integration-contract changes that Agent A must know.
```

Final response should include:

```text
- working folder used;
- branch name;
- summary of completed parity improvements;
- exact tests run;
- remaining blockers;
- git status.
```

Do not push unless explicitly told.

---

## Agent B definition of done for this slice

This slice is complete when:

```text
[ ] A clean parity branch/worktree exists.
[ ] Baseline tests are recorded.
[ ] Native AutoSci gap matrix is updated.
[ ] At least one high-value parity slice is materially improved with tests.
[ ] Product-level AutoSci tests still pass.
[ ] No product runtime files are modified without explicit justification.
[ ] No route is falsely promoted to full.
[ ] Final parity progress report exists.
```
