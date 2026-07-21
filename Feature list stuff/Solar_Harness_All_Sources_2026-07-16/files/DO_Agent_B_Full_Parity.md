# DO — Agent B: AutoSci Full-Parity Continuation

## Work folder and push target

Prefer to work in a BetterSolar-based parity worktree, because BetterSolar is becoming the unified Solar runtime:

```bash
/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar-autosci-parity
```

Create it from:

```bash
/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar
```

Use this branch:

```bash
feature/autosci-full-parity-continuation
```

Push to:

```bash
origin/feature/autosci-full-parity-continuation
```

Read native AutoSci as reference only:

```bash
/Users/jamesyuan/Developer/Github Repos (On Git)/AutoSci
```

Do not edit Agent A’s unification branch unless explicitly instructed.

---

## Your mission

Continue implementing full native AutoSci semantic parity inside the AutoSci module, while preserving the product-level integration contract.

Your job is **not** product unification. Agent A owns that.

Your job is to reduce the remaining AutoSci parity gap:

```text
Current AutoSci route inventory:
- 28 routes
- 17 partial
- 11 gated
- 0 full
```

You should improve high-value parity areas with typed evidence, deterministic gates, and tests. Do not promote any route to `full` unless evidence and tests prove it.

---

## Background

Native AutoSci is the reference. It is a memory-centric agentic system for the full research lifecycle, from paper ingestion to rebuttal. It has 30+ slash commands across:

```text
setup/reset
knowledge base
daily arXiv/discovery/ingest
ask/check/edit/prefill/init
ideation and novelty
experiment design/run/status/eval
review/refine
paper plan/draft/compile
research orchestrator
poster/rebuttal/visualize
```

The current Solar-native integration already has:

```text
harness/plugins/autosci
harness/plugins/autosci/config/feature_parity_routes.v1.json
harness/tools/run_scientific_workflow.py
harness/workflows/scientific_research_lifecycle_full_v1.json
harness/evaluators/scientific
harness/schemas/evidence
cap.research-* capsules
Scientific* logical operators
autosci-* physical workers
product-level AutoSci smoke tests
```

But many routes remain `partial` or `gated`.

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
2. Native AutoSci repo is read-only reference.
3. Do not mutate native AutoSci repo.
4. Do not modify BetterSolar product runtime files unless absolutely necessary and documented.
5. Preserve product dispatch:
   solar-harness.sh autosci '$cmd'
6. Preserve artifact roots:
   HARNESS_DIR
   SOLAR_AUTOSCI_OUTPUT_HARNESS
   AUTOSCI_ARTIFACT_ROOT
   SCIENTIFIC_ARTIFACT_ROOT
7. Missing live provider / remote / Review LLM / compile evidence must result in blocked or inconclusive, not fake success.
8. Do not promote routes to `full` without proof.
```

---

## Step 0 — Create worktree and branch

```bash
export BETTER_SOLAR_REPO="/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar"
export PARITY_WORKTREE="/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar-autosci-parity"
export NATIVE_AUTOSCI_REPO="/Users/jamesyuan/Developer/Github Repos (On Git)/AutoSci"

cd "$BETTER_SOLAR_REPO"
git status --short
git fetch origin
git checkout openJiuwen-Solar
git pull --ff-only || true

# Create worktree if it does not already exist.
git worktree add "$PARITY_WORKTREE" openJiuwen-Solar || true

cd "$PARITY_WORKTREE"
git checkout -b feature/autosci-full-parity-continuation || git checkout feature/autosci-full-parity-continuation
git status --short
```

If BetterSolar does not contain `harness/plugins/autosci/manifest.yaml`, stop and report. Do not duplicate Agent A’s import work.

---

## Step 1 — Baseline tests

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

Do not change code until baseline is known.

---

## Step 2 — Create/update parity inventory

Create or update:

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

Run:

```bash
cd "$PARITY_WORKTREE/harness"

python3 tools/autosci_parity_inventory.py \
  --native-repo "$NATIVE_AUTOSCI_REPO" \
  --out artifacts/autosci/parity_inventory_current.json
```

If this writes under `artifacts/`, do not commit the generated artifact unless it is intentionally small and treated as a fixture. Prefer committing the tool and tests, not runtime outputs.

---

## Step 3 — Update native parity gap matrix

Create or update:

```text
docs/integrations/autosci/native-parity-gap-matrix.md
```

Map each native AutoSci command to:

```text
native behavior
current Solar route
coverage_status
implemented evidence schemas
implemented gates
remaining missing behavior
tests
next required evidence
```

Read native reference files:

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

---

## Step 4 — Choose the first high-value parity slice

Prioritize in this order:

```text
1. OmegaWiki / research_wiki native compatibility
2. /ideate full five-phase path
3. /exp-run and /exp-status deploy/collect/full behavior
4. /paper-draft full paper tree
5. /paper-compile TeX/PDF/submission checks
6. /poster
7. /rebuttal
8. live provider env-gated tests
```

For the first work slice, I recommend:

```text
OmegaWiki / research_wiki native compatibility
```

Reason:

```text
It supports /ask, /check, /ideate, /research, /paper-plan, /paper-draft, and memory update.
```

If you choose another slice, document why.

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

Implement or improve native-compatible commands:

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

Tests to add:

```text
test_research_wiki_init_creates_tree
test_research_wiki_add_citation_and_dedup
test_research_wiki_legal_transition
test_research_wiki_illegal_transition
test_research_wiki_checkpoint_save_load_clear
test_research_wiki_compile_context
test_research_wiki_rebuild_open_questions
```

Rules:

```text
- invalid transitions fail;
- citation dedup works;
- context compilation produces files;
- checkpoint load restores state or explicitly reports missing checkpoint;
- all writes stay under supplied wiki root;
- no native AutoSci repo mutation.
```

---

## Step 6 — If not OmegaWiki, use this slice policy

For `/ideate`:

```text
Implement maturity scan, context/open questions, failed idea banlist,
active idea dedup, A/B/C/D/E generation path recording, supplied model evidence,
novelty/review gate boundaries, accepted/eliminated writeback.
```

For `/exp-run`:

```text
Implement approved local execution, session registry, collection ledger,
duplicate collection prevention, multiseed metrics, remote config-gated path.
```

For `/paper-draft`:

```text
Implement paper/main.tex, math_commands.tex, references.bib,
sections, figures/tables directories, section evidence map, citation integrity.
```

For `/paper-compile`:

```text
Implement pdflatex/xelatex/lualatex fallback, approval gating,
PDF diagnostics, page/anonymity checks, publication_bundle.v1.
```

Always add tests.

---

## Step 7 — Product-level tests must remain green

After changes:

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

If product-level tests break, fix before continuing.

---

## Step 8 — Route status promotion policy

Do not set `coverage_status: full` unless all are true:

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
11. provider/remote/side-effect requirements are live-proven or explicitly not part of claimed full status;
12. parity inventory confirms the route as full.
```

If unsure, keep route:

```text
partial
```

or:

```text
gated
```

Update `limitations` with exact remaining evidence requirements.

---

## Step 9 — Handoff to Agent A

If you change shared-contract files, document it.

Shared-contract files include:

```text
harness/plugins/autosci/config/feature_parity_routes.v1.json
harness/schemas/evidence/*.schema.json
harness/evaluators/scientific/*.py
harness/workflows/scientific_*.json
harness/capability-capsules/cap.research-*.yaml
harness/config/logical-operators.json
harness/config/physical-operators.json
harness/config/capability-capsules.registry.yaml
```

Create or update:

```text
docs/integrations/autosci/parity-to-unification-handoff.md
```

Include:

```text
changed files
new tests
schemas changed
routes changed
gates changed
whether Agent A must re-import or re-run tests
```

---

## Step 10 — Commit and push

After baseline tests and your new tests pass, commit and push:

```bash
cd "$PARITY_WORKTREE"
git status --short

git add \
  harness/plugins/autosci \
  harness/tools \
  harness/evaluators/scientific \
  harness/schemas/evidence \
  harness/workflows \
  harness/capability-capsules \
  harness/plugins/autosci/config/feature_parity_routes.v1.json \
  harness/plugins/autosci/tests \
  harness/tests/evaluators/scientific \
  harness/tests/integration \
  docs/integrations/autosci

git commit -m "feat(autosci): advance native parity slice"

git push -u origin feature/autosci-full-parity-continuation
```

Do not add generated runtime artifacts unless they are intentionally small fixtures.

---

## Final response required from Agent B

Report:

```text
- working folder
- branch
- push target
- HEAD commit
- native files inspected
- parity slice chosen
- files changed
- tests added
- tests run and results
- routes improved
- routes still partial/gated and why
- whether any shared-contract handoff is needed
- final git status
```

---

## Agent B definition of done

```text
[ ] Branch feature/autosci-full-parity-continuation exists.
[ ] Branch is pushed to origin.
[ ] Baseline tests were recorded.
[ ] Parity inventory or gap matrix exists/updated.
[ ] At least one high-value parity slice is improved with tests.
[ ] Product-level AutoSci tests still pass.
[ ] No product runtime files are modified.
[ ] No route is falsely promoted to full.
[ ] Handoff note exists if shared contracts changed.
```
