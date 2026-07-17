# AutoSci-on-Solar Prioritized Integration Plan

**Working branch:** `Coconut-ch1ken/OpenSolar/tree/feature/autosci-solar-native`  
**Target product/runtime base:** `Stellven/AI4Research#openJiuwen-Solar`  
**Native AutoSci reference:** `skyllwt/AutoSci`  
**Purpose:** finish the highest-priority AutoSci migration work first, then merge into the productized Solar runtime while continuing full AutoSci parity work in parallel.

---

## 0. Executive summary

The goal is no longer “finish all native AutoSci parity before merging.” That is too slow for the current deadline.

The new goal is:

```text
1. Implement the parts that are hardest to migrate later.
2. Implement the parts required for a simple but truthful boss demo.
3. Merge the AutoSci module into Stellven's productized Solar runtime.
4. Continue completing full AutoSci parity inside the unified Solar runtime.
```

The final architecture should be:

```text
Stellven/OpenJiuwen Solar product runtime
  + AutoSci scientific runtime module from feature/autosci-solar-native
```

Not:

```text
Stellven Solar
  -> Coconut Solar
     -> AutoSci
```

A two-Solar interface can be used only as a temporary emergency demo bridge. It should not become the permanent architecture.

---

## 1. Current branch assets to preserve

The latest `feature/autosci-solar-native` branch already contains major integration assets. These should be treated as the AutoSci module’s core structure.

### 1.1 AutoSci plugin and route layer

```text
harness/plugins/autosci/manifest.yaml
harness/plugins/autosci/bin/autosci_skill_shim.py
harness/plugins/autosci/bin/autosci_bridge.py
harness/plugins/autosci/config/feature_parity_routes.v1.json
harness/plugins/autosci/config/feature_operator_bindings.v1.json
```

Current function:

```text
- The plugin manifest declares the AutoSci scientific capability family.
- The route config maps native AutoSci commands to Solar capability/operator/action/evidence contracts.
- The skill shim parses AutoSci-style `$...` commands and emits typed Solar evidence.
- The bridge performs bounded backend actions and converts outputs into Solar Evidence ABI.
```

### 1.2 Scientific workflow runtime

```text
harness/tools/run_scientific_workflow.py
harness/tools/run_scientific_node_smoke.py
harness/tools/run_scientific_lifecycle_smoke.py
harness/workflows/scientific_research_lifecycle_full_v1.json
harness/workflows/scientific_research_resume_v1.json
```

Current function:

```text
- `run_scientific_workflow.py` is the important new generic workflow runner.
- It reads workflow nodes from workflow JSON.
- It dispatches selected nodes through operator_runtime -> AutoSci bridge.
- It writes `scientific_lifecycle.v1` and runtime manifest artifacts.
- It is not a black-box AutoSciRunner.
```

### 1.3 Evidence ABI and gates

```text
harness/schemas/evidence/*.schema.json
harness/evaluators/scientific/*.py
```

Current function:

```text
- Typed Evidence ABI for scientific artifacts.
- Deterministic gates for paper, claims, methods, code evidence, ideas, experiments, verdicts, reports, publication bundles, and lifecycle summaries.
```

### 1.4 Operator/capsule layer

```text
harness/config/logical-operators.json
harness/config/physical-operators.json
harness/config/capability-capsules.registry.yaml
harness/capability-capsules/cap.research-*.yaml
```

Current function:

```text
- Scientific logical operators such as ScientificPaperIngestor, ScientificExperimentRunner, ScientificPublicationProducer.
- AutoSci-backed physical workers such as autosci-paper-ingest-worker and autosci-experiment-run-worker.
- Research capability capsules such as cap.research-paper-ingest and cap.research-claim-verify.
```

### 1.5 AutoSci user-facing wrappers

```text
.agents/skills/ask/SKILL.md
.agents/skills/check/SKILL.md
.agents/skills/daily-arxiv/SKILL.md
.agents/skills/discover/SKILL.md
.agents/skills/edit/SKILL.md
.agents/skills/exp-design/SKILL.md
.agents/skills/exp-eval/SKILL.md
.agents/skills/exp-pilot-eval/SKILL.md
.agents/skills/exp-pilot-run/SKILL.md
.agents/skills/exp-run/SKILL.md
.agents/skills/exp-status/SKILL.md
.agents/skills/ideate/SKILL.md
.agents/skills/ingest/SKILL.md
.agents/skills/init/SKILL.md
.agents/skills/novelty/SKILL.md
.agents/skills/paper-compile/SKILL.md
.agents/skills/paper-draft/SKILL.md
.agents/skills/paper-plan/SKILL.md
.agents/skills/poster/SKILL.md
.agents/skills/prefill/SKILL.md
.agents/skills/rebuttal/SKILL.md
.agents/skills/refine/SKILL.md
.agents/skills/research/SKILL.md
.agents/skills/reset/SKILL.md
.agents/skills/review/SKILL.md
.agents/skills/setup/SKILL.md
.agents/skills/survey/SKILL.md
.agents/skills/visualize/SKILL.md
```

These wrappers are useful but must be reconciled with the final product CLI so they do not point to a non-existent or non-wired `solar-harness '$cmd'` path.

---

## 2. Prioritization principle

Do not prioritize all AutoSci features equally.

Use three priority classes:

```text
Priority A: Hard-to-migrate-later foundations
Priority B: Demo-contract functionality
Priority C: Full native AutoSci semantic parity
```

### Priority A — Hard-to-migrate-later foundations

These must be implemented before or during Solar unification because changing them afterward will be expensive:

```text
1. Common command entry point.
2. Common artifact root.
3. Stable AutoSci route config ABI.
4. Stable Evidence ABI and gates.
5. Unified logical/physical/capability registries.
6. Generic workflow runner as the single scientific workflow runner.
7. Product CLI wiring in Stellven Solar.
8. Artifact hygiene and `.gitignore`.
```

### Priority B — Demo-contract functionality

These must be implemented for a simple boss demo. They may be fixture-backed, provider-mocked, approval-gated, or blocked on explicit evidence, as long as they do not falsely claim live/full success:

```text
1. `$skills`
2. `$ingest`
3. `$review`
4. `$ideate`
5. `$research --scheduler-run`
6. `$paper-draft` minimal evidence-linked report
7. `$exp-run` dry-run / approved-local path
8. Human-facing workspace projection
```

### Priority C — Full native AutoSci parity

These continue after the merge into one Solar runtime:

```text
1. Full OmegaWiki parity.
2. Full `/ideate` five-phase pipeline.
3. Full `/exp-run` local/remote deploy/collect/full behavior.
4. Full `/paper-draft` paper tree generation.
5. Full `/paper-compile` TeX/PDF/submission checks.
6. Full `/poster` rendering.
7. Full `/rebuttal`.
8. Live provider and remote-host proofs.
```

---

## 3. Definition of “demo-contract functionality”

“Demo-contract” does not mean fake success.

Allowed:

```text
- fixture-backed output, only when explicitly marked as fixture/smoke;
- provider-mocked output, with provenance that says it is mocked;
- approval-gated output, with approval contract evidence;
- blocked nodes, with reason / required_evidence / unblock_condition;
- inconclusive status, when live provider or runtime evidence is missing.
```

Forbidden:

```text
- claiming real remote execution without runtime evidence;
- claiming Review LLM completion without Review LLM evidence;
- claiming paper submission readiness without submission/anonymity/page/font checks;
- marking a partial/gated route as completed;
- hiding blocked nodes;
- using a black-box AutoSciRunner as the lifecycle owner.
```

---

# Phase A — Hard-to-migrate-later foundations

## A1. Implement one product-level AutoSci command entry

### Goal

In the unified Solar runtime, users must be able to call:

```bash
solar harness autosci '$review path/to/artifact.md --focus method'
solar harness autosci '$ingest path/to/paper.pdf'
solar harness autosci '$research "topic" --scheduler-run'
```

Optional convenience:

```bash
solar harness '$review path/to/artifact.md --focus method'
```

### Why this is first

Without this, AutoSci exists only if users know to call:

```bash
python3 harness/plugins/autosci/bin/autosci_skill_shim.py ...
```

That is not integrated Solar.

### Implementation target

In Stellven Solar’s CLI/harness layer:

```text
If command verb is `autosci`:
    pass remaining command string to autosci_skill_shim.py text
If command starts with `$` and the skill exists in feature_parity_routes.v1.json:
    pass full command string to autosci_skill_shim.py text
Else:
    normal Solar command handling
```

### Shell command to call internally

```bash
python3 "$HARNESS_DIR/plugins/autosci/bin/autosci_skill_shim.py" text "$AUTOSCI_COMMAND"
```

### Acceptance

These must work from the product runtime:

```bash
solar harness autosci '$skills'
solar harness autosci '$review --help'
solar harness autosci '$ingest --help'
solar harness autosci '$research --help'
```

Expected:

```text
- no "unknown command";
- no shell expansion of `$review` into empty string;
- command reaches autosci_skill_shim.py;
- output includes AutoSci skill or route information.
```

---

## A2. Standardize AutoSci artifact roots

### Goal

Use one artifact root inside the shared Solar runtime:

```text
harness/artifacts/autosci/runs/<run-id>/
harness/artifacts/autosci/workspace/wiki/
harness/artifacts/autosci/workspace/wiki/outputs/
harness/artifacts/scientific/workflow-runs/<job-id>/
```

### Required environment behavior

```bash
HARNESS_DIR=<shared product harness>
AUTOSCI_ARTIFACT_ROOT="$HARNESS_DIR/artifacts/autosci"
SCIENTIFIC_ARTIFACT_ROOT="$HARNESS_DIR/artifacts/scientific"
```

### Acceptance

Run:

```bash
solar harness autosci '$review README.md --run-id artifact-root-check'
```

Verify:

```bash
test -d harness/artifacts/autosci/runs/artifact-root-check
test ! -d ../OpenSolar/harness/artifacts/autosci/runs/artifact-root-check
test ! -d ../AutoSci/harness/artifacts/autosci/runs/artifact-root-check
```

All outputs must remain in the unified Solar runtime.

---

## A3. Freeze AutoSci route config ABI

### Canonical file

```text
harness/plugins/autosci/config/feature_parity_routes.v1.json
```

### Required fields per route

```text
native_skill
autosci_command
feature_kind
native_paths
solar_capability
solar_logical_operator
solar_backend_action
coverage_status
backend_mode
side_effect_policy
evidence_schema
primary_tools
required_capabilities
limitations
```

### Acceptance

Run:

```bash
python3 harness/plugins/autosci/bin/autosci_skill_shim.py skills list
```

Expected:

```text
- route count matches the route config;
- every route has native_skill;
- every route has autosci_command;
- every route has solar_backend_action;
- every route has evidence_schema;
- no route has coverage_status=full unless corresponding proof exists.
```

---

## A4. Stabilize Evidence ABI and lifecycle gates

### Must-keep schemas

```text
autosci_skill_run.v1
scientific_lifecycle.v1
scientific_workflow_runtime_manifest.v1
research_paper.v1
literature_discovery.v1
research_memory_update.v1
research_graph_update.v1
research_claims.v1
research_method.v1
code_evidence_map.v1
idea_candidate.v1
idea_evaluation.v1
experiment_plan.v1
experiment_status.v1
experiment_result.v1
claim_verdict.v1
artifact_review.v1
scientific_report.v1
publication_bundle.v1
workflow_evolution.v1
```

### Required lifecycle gate behavior

`lifecycle_runtime_gate.py` must reject:

```text
- missing node_results;
- missing gate_results;
- missing artifact path;
- missing or mismatched artifact_sha256;
- artifact schema mismatch;
- artifact status not completed;
- sprint_id/job_id mismatch;
- node_id mismatch;
- black-box lifecycle action such as run_research_lifecycle as node runtime owner.
```

### Acceptance

Use one weak summary and one strict summary:

```bash
python3 harness/evaluators/scientific/lifecycle_runtime_gate.py weak_summary.json
# must fail

python3 harness/evaluators/scientific/lifecycle_runtime_gate.py strict_summary.json
# must pass or return inconclusive only if blocked nodes are explicit
```

---

## A5. Merge registries into the common Solar runtime

### Files to merge manually

```text
harness/config/logical-operators.json
harness/config/physical-operators.json
harness/config/capability-capsules.registry.yaml
```

### Required logical operators

```text
ScientificLiteratureDiscoverer
ScientificPaperIngestor
ScientificPaperAnalyzer
ScientificMemoryUpdater
ScientificGraphUpdater
ScientificClaimExtractor
ScientificMethodExtractor
ScientificCodeEvidenceMapper
ScientificIdeaGenerator
ScientificIdeaEvaluator
ScientificExperimentDesigner
ScientificExperimentRunner
ScientificExperimentMonitor
ScientificClaimVerifier
ScientificReportPlanner
ScientificReportDrafter
ScientificArtifactReviewer
ScientificPublicationProducer
ScientificWorkflowEvolver
```

### Required physical workers

```text
autosci-literature-discover-worker
autosci-paper-ingest-worker
autosci-paper-analyze-worker
autosci-memory-update-worker
autosci-graph-update-worker
autosci-claim-extract-worker
autosci-method-extract-worker
autosci-code-evidence-map-worker
autosci-idea-worker
autosci-idea-evaluate-worker
autosci-experiment-design-worker
autosci-experiment-run-worker
autosci-experiment-monitor-worker
autosci-claim-verify-worker
autosci-artifact-review-worker
autosci-report-plan-worker
autosci-report-worker
autosci-publication-compile-worker
autosci-workflow-evolve-worker
```

### Required capability capsules

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

### Acceptance commands

```bash
grep -R "ScientificExperimentRunner" harness/config/logical-operators.json
grep -R "autosci-experiment-run-worker" harness/config/physical-operators.json
grep -R "cap.research-experiment-run" harness/config/capability-capsules.registry.yaml
```

Also run JSON/YAML parse checks:

```bash
python3 -m json.tool harness/config/logical-operators.json >/tmp/logical.ok.json
python3 -m json.tool harness/config/physical-operators.json >/tmp/physical.ok.json

python3 - <<'PY'
import yaml
from pathlib import Path
yaml.safe_load(Path("harness/config/capability-capsules.registry.yaml").read_text())
print("capsule registry yaml ok")
PY
```

---

## A6. Make `run_scientific_workflow.py` the single scientific workflow runner

### Goal

The generic runner must be the standard path for `$research --scheduler-run`.

### Current intended behavior

```text
$research --scheduler-run
  -> harness/tools/run_scientific_workflow.py
  -> workflow JSON
  -> selected workflow nodes
  -> operator_runtime -> AutoSci bridge
  -> node evidence
  -> lifecycle_runtime_gate.py
```

### Legacy behavior

Old lifecycle smoke runner should remain available only as:

```text
--scheduler-legacy-smoke-runner
```

### Acceptance

Run:

```bash
solar harness autosci '$research "demo topic" --scheduler-run --run-id runner-check'
```

Verify output includes:

```text
runner_contract=generic_workflow_runner
scientific_lifecycle.v1
scientific_workflow_runtime_manifest.v1
node_results or explicit blocked_nodes
```

---

## A7. Prevent generated artifact pollution

### Add/update `.gitignore`

```gitignore
harness/artifacts/autosci/runs/
harness/artifacts/autosci/phase19/current-parity-inventory-*.json
harness/artifacts/autosci/operator-smoke/
harness/.coordinator*
harness/.watchdog*
harness/.pane-*
harness/PLANNER-INBOX.md
.solar-backups/
.DS_Store
```

### Keep

```text
- small fixtures;
- schema examples;
- deterministic test fixtures;
- curated docs;
- maybe one small golden parity sample if intentionally maintained.
```

### Remove from production branch

```text
- large current-parity-inventory dumps;
- local run outputs;
- PID/state files;
- generated proof-input directories unless used by tests.
```

---

# Phase B — Demo-contract functionality

## B1. `$skills` route-list demo

### Command

```bash
solar harness autosci '$skills'
```

### Expected output

List all AutoSci routes and statuses:

```text
ask
check
daily-arxiv
discover
edit
exp-design
exp-eval
exp-pilot-eval
exp-pilot-run
exp-run
exp-status
ideate
ingest
init
novelty
paper-compile
paper-draft
paper-plan
poster
prefill
rebuttal
refine
research
reset
review
setup
survey
visualize
```

### Acceptance

```text
- route count is correct;
- routes show coverage_status;
- routes show side_effect_policy;
- output does not imply all are full parity.
```

---

## B2. `$ingest` paper demo

### Command

```bash
solar harness autosci '$ingest harness/plugins/autosci/tests/fixtures/sample_paper.md --run-id demo-ingest'
```

### Must produce

```text
harness/artifacts/autosci/runs/demo-ingest/
harness/artifacts/autosci/workspace/wiki/papers/<paper>.md
research_paper.v1
autosci_skill_run.v1
```

### Acceptance

```text
- research_paper.v1 exists;
- paper gate passes or reports concrete reasons;
- human-facing wiki paper exists;
- no hidden native AutoSci repo mutation.
```

---

## B3. `$review` artifact demo

### Command

```bash
solar harness autosci '$review README.md --focus method --run-id demo-review'
```

### Must produce

```text
artifact_review.v1
autosci_skill_run.v1
human-readable review diagnostics
```

### If Review LLM unavailable

Acceptable:

```text
review_mode=local_diagnostic
final_acceptance_ready=false
status=inconclusive or partial
limitations mention missing Review LLM evidence
```

Not acceptable:

```text
claiming Review LLM completed without provider/evidence
```

---

## B4. `$ideate` demo-contract path

### Command

```bash
solar harness autosci '$ideate "agentic scientific workflow" --run-id demo-ideate'
```

### Must produce

```text
idea_candidate.v1
idea_evaluation.v1 if evaluator evidence exists
human-facing idea output
limitations explaining source/model/provider status
```

### Acceptance

```text
- no fabricated provider-backed novelty;
- no fabricated Review LLM second opinion;
- fixture output only when --smoke is explicit;
- missing provider/model evidence yields inconclusive, not completed.
```

---

## B5. `$research --scheduler-run` demo

### Command

```bash
solar harness autosci '$research "agentic scientific workflow" --scheduler-run --run-id demo-research'
```

### Must produce

```text
scientific_lifecycle.v1
scientific_workflow_runtime_manifest.v1
node_results
gate_results
blocked_nodes where needed
human-facing lifecycle report
```

### Acceptable result

```text
lifecycle_status=passed
```

or:

```text
lifecycle_status=blocked
```

if blocked nodes are explicit.

### Required blocked node fields

```text
reason
required_evidence
unblock_condition
```

### Not acceptable

```text
- no node_results;
- no gate_results;
- black-box AutoSciRunner;
- lifecycle owned by run_research_lifecycle projection;
- hidden blocked external provider.
```

---

## B6. `$paper-draft` minimal report demo

### Command

```bash
solar harness autosci '$paper-draft --topic "agentic scientific workflow" --run-id demo-paper-draft'
```

### Must produce

```text
scientific_report.v1
report.md
optional LaTeX sidecar
evidence/citation map if available
limitations
```

### Acceptance

```text
- report sections cite evidence or mark evidence missing;
- unsupported claims are not presented as verified;
- publication-ready claims require compile/PDF handoff evidence.
```

---

## B7. `$exp-run` dry-run or approved-local demo

### Command

Dry run:

```bash
solar harness autosci '$exp-run exp-demo --run-id demo-exp-run'
```

Approved local deterministic command path:

```bash
solar harness autosci '$exp-run exp-demo --experiment-execute-approved --experiment-approval-ref demo-approval --run-id demo-exp-run'
```

### Must produce

```text
experiment_result.v1 or experiment_status.v1
approval contract evidence if execution attempted
runtime evidence or blocked state
collection ledger if collecting
```

### Acceptance

```text
- remote execution is not claimed unless runtime evidence exists;
- collection has file digests or is blocked/inconclusive;
- long-running external execution requires approval;
- local fixture/smoke execution is clearly marked.
```

---

## B8. Human-facing workspace projection

### Goal

Boss/demo users need human-readable outputs.

### Required output locations

```text
harness/artifacts/autosci/workspace/wiki/
harness/artifacts/autosci/workspace/wiki/outputs/
harness/artifacts/scientific/workflow-runs/<job-id>/
```

### Demo-visible files

```text
wiki/index.md
wiki/outputs/lifecycle_summary.md
wiki/outputs/report.md
wiki/outputs/review.md
wiki/outputs/ideas.md
```

### Acceptance

A non-engineer should be able to open the workspace directory and understand:

```text
what ran
what was produced
what is blocked
what evidence exists
what remains incomplete
```

---

# Phase C — Solar unification preparation

## C1. Use Stellven Solar as product base

### Base branch

```text
Stellven/AI4Research#openJiuwen-Solar
```

### Import from your branch

```text
Coconut-ch1ken/OpenSolar#feature/autosci-solar-native
```

### Why

Stellven has product/install/desktop/distribution runtime. Your branch has AutoSci scientific runtime. They are complementary.

---

## C2. Import AutoSci module files selectively

### Bring

```text
harness/plugins/autosci/**
harness/tools/run_scientific_workflow.py
harness/tools/run_scientific_node_smoke.py
harness/tools/run_scientific_lifecycle_smoke.py
harness/workflows/scientific_*.json
harness/evaluators/scientific/**
harness/schemas/evidence/**
harness/capability-capsules/cap.research-*.yaml
.agents/skills/* AutoSci wrappers, after CLI wording review
docs/integrations/autosci/* curated design docs
```

### Do not bring wholesale

```text
harness/artifacts/autosci/runs/*
harness/artifacts/autosci/phase19/current-parity-inventory-*.json
harness/artifacts/autosci/operator-smoke/*
harness/.coordinator*
harness/.watchdog*
harness/.pane-*
harness/PLANNER-INBOX.md
.solar-backups/*
.DS_Store
```

---

## C3. Merge shared runtime files manually

Do not overwrite Stellven’s product files.

Manual merge required:

```text
README.md
AGENTS.md
CLAUDE.md
bin/solar
harness/solar-harness.sh or harness CLI equivalent
core/daemon/skill-dispatcher.ts
harness/config/logical-operators.json
harness/config/physical-operators.json
harness/config/capability-capsules.registry.yaml
```

Important note:

Stellven’s current `SkillDispatcher` resolves and returns instruction text, and `executed` remains false. It must not be used as the final AutoSci execution path unless extended to dispatch AutoSci routes to the shim.

---

## C4. Integration smoke tests

Create tests in the unified Solar repo:

```text
tests/integration/test_autosci_routes_list.py
tests/integration/test_autosci_cli_dispatch.py
tests/integration/test_autosci_ingest_demo.py
tests/integration/test_autosci_review_demo.py
tests/integration/test_autosci_research_scheduler_demo.py
tests/integration/test_autosci_artifact_root.py
```

Minimum assertions:

```text
- `solar harness autosci '$skills'` works.
- `$review --help` reaches shim.
- `$ingest` writes research_paper.v1.
- `$review` writes artifact_review.v1.
- `$research --scheduler-run` writes scientific_lifecycle.v1.
- outputs stay under the unified HARNESS_DIR.
```

---

# Phase D — Parallel post-merge full parity work

Once Priority A and B are done and the module is merged into Stellven Solar, run two workstreams in parallel.

---

## Track 1 — Solar unification stabilization

Focus:

```text
- CLI polish.
- Desktop/status-server surface for AutoSci runs.
- `solar doctor` AutoSci checks.
- backup/restore includes AutoSci workspace and artifacts.
- install/update handles AutoSci plugin files.
- command help pages.
- artifacts not committed.
- cross-platform path handling.
```

Doctor checks should include:

```text
AutoSci plugin manifest exists
route config exists
schemas exist
gates exist
python dependencies available
optional provider credentials detected or absent with warning
TeX toolchain detected or absent with warning
remote experiment config detected or absent with warning
```

---

## Track 2 — Complete native AutoSci parity

Prioritized sequence:

```text
1. OmegaWiki command compatibility.
2. Full /ideate five-phase pipeline.
3. Full /exp-run deploy/collect/full local + remote-gated behavior.
4. Full /paper-draft paper tree.
5. Full /paper-compile TeX/PDF/submission checks.
6. /poster render path.
7. /rebuttal thread/stress-test/submission audit.
8. live provider env-gated tests.
9. parity inventory.
10. route promotion from partial/gated to full only with proof.
```

---

# Phase E — Demo script

This is the boss-facing demo script.

```bash
# 1. Confirm Solar is alive.
solar status

# 2. Show AutoSci command surface inside Solar.
solar harness autosci '$skills'

# 3. Ingest a paper.
solar harness autosci '$ingest harness/plugins/autosci/tests/fixtures/sample_paper.md --run-id demo-ingest'

# 4. Review the ingested paper or a known artifact.
solar harness autosci '$review harness/artifacts/autosci/workspace/wiki/papers/<paper>.md --focus method --run-id demo-review'

# 5. Generate idea candidates.
solar harness autosci '$ideate "agentic scientific workflow" --run-id demo-ideate'

# 6. Run scheduler-visible research lifecycle.
solar harness autosci '$research "agentic scientific workflow" --scheduler-run --run-id demo-research'

# 7. Open human-facing workspace.
ls -R harness/artifacts/autosci/workspace/wiki | sed -n '1,120p'
ls -R harness/artifacts/scientific/workflow-runs/demo-research | sed -n '1,160p'
```

What to show:

```text
- AutoSci routes are recognized by Solar.
- Each command writes Solar evidence.
- The scientific workflow produces node/gate evidence.
- Missing provider/remote steps are explicitly blocked, not hidden.
- Human-facing workspace contains readable outputs.
```

What not to claim:

```text
- Do not claim live remote experiment parity unless actually tested.
- Do not claim Review LLM parity unless provider/evidence is present.
- Do not claim paper submission readiness unless compile/submission checks pass.
- Do not claim 100% native parity until parity inventory and acceptance tests prove it.
```

---

# Phase F — Definition of priority integration complete

Priority integration is complete when:

```text
[ ] Stellven Solar can call AutoSci commands through one CLI path.
[ ] `$skills` works.
[ ] `$ingest` produces research_paper.v1.
[ ] `$review` produces artifact_review.v1.
[ ] `$ideate` produces idea_candidate.v1 or honest inconclusive evidence.
[ ] `$research --scheduler-run` uses run_scientific_workflow.py.
[ ] scientific_lifecycle.v1 is generated.
[ ] lifecycle_runtime_gate passes or returns inconclusive for explicit blocked nodes.
[ ] AutoSci route config is canonical.
[ ] AutoSci artifacts land in one shared artifact root.
[ ] Scientific logical operators are registered.
[ ] autosci-* physical workers are registered.
[ ] cap.research-* capsules are registered.
[ ] Human-facing workspace/report projection exists.
[ ] Generated proof artifacts are not committed into the product branch.
```

At this point, you can say:

```text
Integrated Solar now has AutoSci capabilities enabled.
Full native AutoSci parity is continuing inside the unified Solar runtime.
```

---

# Phase G — Definition of full AutoSci parity

Full parity requires:

```text
[ ] All native AutoSci commands represented.
[ ] All routes backed by executable code, not only config.
[ ] All capabilities registered and capsule-backed.
[ ] All workflow nodes resolve logical -> capability -> physical -> backend action.
[ ] Full /research runs through Solar scheduler, not black-box AutoSciRunner.
[ ] Every unblocked node emits typed Evidence ABI.
[ ] Every unblocked node passes deterministic gate.
[ ] Blocked external/human nodes are explicit and resumable.
[ ] OmegaWiki command surface is native-compatible.
[ ] /ideate has full five-phase semantics.
[ ] /exp-run supports deploy, collect, full, local/remote gated paths.
[ ] /paper-draft produces full paper/ tree.
[ ] /paper-compile produces publication_bundle.v1 and compile diagnostics/PDF when approved.
[ ] /poster and /rebuttal produce native-equivalent artifacts.
[ ] parity_inventory reports full only after acceptance tests pass.
```

---

# Appendix A — Suggested coding-agent prompt

Use this when sending the work to a coding agent:

```text
You are continuing the AutoSci-on-Solar migration on branch feature/autosci-solar-native and preparing it to merge into Stellven/AI4Research#openJiuwen-Solar.

Do not try to finish every native AutoSci feature first. Prioritize:
1. hard-to-migrate-later integration foundations;
2. demo-contract functionality;
3. merge readiness;
4. then full native parity in parallel after unification.

First implement:
- product-level AutoSci CLI entry: `solar harness autosci '$review ...'`;
- one artifact root under the shared HARNESS_DIR;
- route config ABI stability;
- Evidence ABI/gate stability;
- registry merge for Scientific* operators, autosci-* workers, and cap.research-* capsules;
- use `run_scientific_workflow.py` as the default `$research --scheduler-run` runner;
- prevent generated artifacts from being committed.

Then implement demo-contract commands:
- `$skills`;
- `$ingest`;
- `$review`;
- `$ideate`;
- `$research --scheduler-run`;
- `$paper-draft` minimal report;
- `$exp-run` dry-run or approved-local.

Do not claim full parity from route config or logs. Every demo feature must write typed evidence. Missing provider/remote/review/compile evidence must produce blocked or inconclusive status, not fake success.

After this is working, import the AutoSci module into Stellven Solar and continue full AutoSci parity work inside the unified runtime.
```

---

# Appendix B — File import checklist for Stellven merge

## Import from AutoSci branch

```text
harness/plugins/autosci/**
harness/tools/run_scientific_workflow.py
harness/tools/run_scientific_node_smoke.py
harness/tools/run_scientific_lifecycle_smoke.py
harness/workflows/scientific_*.json
harness/evaluators/scientific/**
harness/schemas/evidence/**
harness/capability-capsules/cap.research-*.yaml
.agents/skills/* AutoSci wrappers
docs/integrations/autosci/* curated docs
```

## Manually merge

```text
harness/config/logical-operators.json
harness/config/physical-operators.json
harness/config/capability-capsules.registry.yaml
bin/solar
harness/solar-harness.sh or equivalent harness CLI
core/daemon/skill-dispatcher.ts
README.md
AGENTS.md
CLAUDE.md
```

## Exclude

```text
harness/artifacts/autosci/runs/*
harness/artifacts/autosci/phase19/current-parity-inventory-*.json
harness/artifacts/autosci/operator-smoke/*
harness/.coordinator*
harness/.watchdog*
harness/.pane-*
harness/PLANNER-INBOX.md
.solar-backups/*
.DS_Store
```
