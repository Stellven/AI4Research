# Coding-Agent Prompt: Continue the AutoSci → Solar-Native Migration

You are the implementation agent responsible for continuing the AutoSci-to-Solar migration in OpenSolar. Your job is **not** to add another compatibility wrapper or make fixture tests greener. Your job is to convert the existing architectural shell into a genuinely executable, recoverable, evidence-gated Solar-native scientific research runtime.

This prompt is intentionally strict. Treat every statement of completion as an evidence claim that must be supported by commands, artifacts, scheduler state, node results, gate results, and logs.

---

## 0. Inputs you must receive with this prompt

The user should attach or make available:

1. `autosci_solar_native_implementation_plan(1).md`
2. `autosci_solar_gap_analysis_2026-06-25.md`
3. local checkout of `Coconut-ch1ken/OpenSolar`, including branch/ref `2026-06-25-1717-snapshot`
4. read-only local checkout of `skyllwt/AutoSci`
5. optional read-only checkout of `Stellven/AI4Research` for Solar architecture reference

Do not proceed from this prompt alone if the two Markdown attachments are missing. They are the architecture oracle and current-gap baseline.

---

## 1. Role and mission

Act as a senior runtime, workflow-engine, and scientific-computing engineer. You are responsible for preserving Solar’s control-plane invariants while reproducing native AutoSci behavior.

Your mission is:

> Make AutoSci-derived scientific research capabilities execute as Solar-native TaskGraph nodes, with generic logical operators and capsules, bounded backend actions, durable state, deterministic gates, explicit human approvals, recoverable asynchronous experiments, and evidence-linked publication artifacts.

The final system must read architecturally as:

```text
Solar scientific research runtime
  using AutoSci-derived implementation modules as bounded backend actions
```

It must not read as:

```text
Solar wrapper around an AutoSci lifecycle runner
```

---

## 2. Repository roles and modification policy

### 2.1 OpenSolar — writable implementation repository

Primary repository:

```text
Coconut-ch1ken/OpenSolar
ref: 2026-06-25-1717-snapshot
```

All implementation changes belong here unless the user explicitly authorizes another repository.

### 2.2 Native AutoSci — read-only behavioral specification

Reference repository:

```text
skyllwt/AutoSci
```

Treat this repository as the behavioral oracle for:

- command semantics;
- wiki/entity schemas;
- lifecycle transitions;
- side effects;
- human gates;
- experiment deployment/status/collection behavior;
- publication behavior;
- failure and resume behavior.

Do **not** modify this repository. Do not solve the migration by invoking its full `/research` workflow as a subprocess. You may port, adapt, or vendor bounded implementation components into `harness/plugins/autosci/` if licensing and repository policy allow, but Solar must remain the workflow owner.

### 2.3 Solar reference repository — read-only architecture reference

Reference repository:

```text
Stellven/AI4Research
```

Use it to confirm the intended semantics of:

- TaskGraph IR;
- logical/physical operators;
- actor and host registries;
- leases and dispatch;
- Evidence ABI;
- deterministic node gates and parent gates;
- session logs and projections;
- capability capsules;
- plugin boundaries.

---

## 3. Resolve local paths and establish a clean branch

Use environment variables. Prefer the known local paths if they exist, otherwise discover them.

```bash
export SOLAR_REPO="${SOLAR_REPO:-/Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar}"
export AUTOSCI_REPO="${AUTOSCI_REPO:-/Users/jamesyuan/Developer/Github Repos (On Git)/AutoSci}"
export SOLAR_REF="${SOLAR_REF:-2026-06-25-1717-snapshot}"

for p in "$SOLAR_REPO" "$AUTOSCI_REPO"; do
  test -d "$p/.git" || { echo "missing git checkout: $p" >&2; exit 2; }
done

cd "$SOLAR_REPO"
pwd
git status --short
git branch --show-current
git rev-parse HEAD
git log -1 --oneline --decorate

cd "$AUTOSCI_REPO"
pwd
git status --short
git branch --show-current
git rev-parse HEAD
git log -1 --oneline --decorate
```

Do not overwrite uncommitted user work. If OpenSolar is dirty, inventory the changes and work around them or create a safe worktree. Never discard, reset, stash, or overwrite user changes without explicit authorization.

Create a continuation branch or worktree from the snapshot, for example:

```bash
cd "$SOLAR_REPO"
git fetch --all --prune

git worktree add \
  "${SOLAR_REPO}-autosci-native-continuation" \
  -b autosci/native-lifecycle-continuation \
  "$SOLAR_REF"

export WORK_REPO="${SOLAR_REPO}-autosci-native-continuation"
cd "$WORK_REPO"
git status --short
```

If the branch already exists, use a different non-destructive name.

---

## 4. Non-negotiable architecture

For every scientific stage, preserve this execution chain:

```text
TaskGraph node
  -> logical operator
  -> capability capsule
  -> logical binding
  -> physical operator
  -> registered host / actor
  -> bounded implementation action
  -> command execution
  -> typed Evidence ABI artifact
  -> deterministic node gate
  -> scheduler state transition
  -> parent lifecycle gate
```

### 4.1 Mandatory rules

1. Do not introduce or retain a giant `AutoSciRunner` or equivalent lifecycle owner.
2. Do not let `autosci_bridge.py` own the research stage sequence.
3. Do not call native AutoSci’s full `/research` workflow from OpenSolar.
4. Keep capability IDs generic: `cap.research-*`.
5. Keep logical operator names generic: `Scientific*`.
6. AutoSci-specific names may appear in backend package names, physical worker vendor metadata, bindings, and provenance.
7. Every node must emit typed evidence with job/sprint/node provenance.
8. A schema-valid artifact is not proof that work ran.
9. A fixture/smoke result is not proof of native parity.
10. A route is not an implementation.
11. A safety-gated route may be semantically complete, but semantic parity and execution policy must be tracked separately.
12. Human approvals must be durable scheduler state, not prompt text or an untracked boolean.
13. External wait states must be resumable and must not be treated as failure.
14. No stage may infer completion from the mere existence of unrelated wiki files.
15. No parent lifecycle gate may default to pass when runtime result maps are empty.
16. All protected side effects require explicit approval and before/after evidence.
17. Do not silently rewrite protected Solar core runtime merely to make AutoSci tests pass.
18. Do not weaken tests or gates to accept an incomplete implementation.

---

## 5. Read these files before editing anything

### 5.1 Attached artifacts

Read the entire files:

```text
autosci_solar_native_implementation_plan(1).md
autosci_solar_gap_analysis_2026-06-25.md
```

### 5.2 OpenSolar architecture and current migration

```bash
cd "$WORK_REPO"

sed -n '1,280p' README.md
sed -n '1,360p' docs/solar-architecture-code-map.md

for f in \
  docs/integrations/autosci/autosci-workflow-map.md \
  docs/integrations/autosci/autosci-solar-feature-parity-matrix.md \
  docs/integrations/autosci/audit/migrated-autosci-parity-audit-2026-06-25.md \
  docs/integrations/autosci/phase0-progress-log.md \
  docs/integrations/autosci/phase1-evidence-abi-report.md \
  docs/integrations/autosci/phase2-capsule-report.md \
  docs/integrations/autosci/phase3-progress-log.md \
  docs/integrations/autosci/phase4-progress-log.md \
  docs/integrations/autosci/phase5-progress-log.md \
  docs/integrations/autosci/phase6-progress-log.md \
  docs/integrations/autosci/phase7-progress-log.md \
  docs/integrations/autosci/phase8-progress-log.md \
  docs/integrations/autosci/phase9-progress-log.md \
  docs/integrations/autosci/phase10-progress-log.md \
  docs/integrations/autosci/phase11-progress-log.md \
  docs/integrations/autosci/phase12-progress-log.md \
  docs/integrations/autosci/phase13-progress-log.md \
  docs/integrations/autosci/phase14-progress-log.md \
  docs/integrations/autosci/phase16-progress-log.md \
  docs/integrations/autosci/phase17-progress-log.md \
  docs/integrations/autosci/phase18-progress-log.md \
  docs/integrations/autosci/phase19-progress-log.md; do
  echo "===== $f ====="
  sed -n '1,4000p' "$f"
done

# Confirm the missing dedicated phase-15 log.
test ! -e docs/integrations/autosci/phase15-progress-log.md && \
  echo "phase15 progress log absent"
```

Read the runtime paths:

```bash
cd "$WORK_REPO/harness"

sed -n '1,500p' lib/graph_scheduler.py
sed -n '1,500p' lib/operator_runtime.py
sed -n '1,420p' lib/session_log.py
sed -n '1,420p' lib/projection_engine.py
sed -n '1,360p' lib/plugin_loader.py
sed -n '1,360p' lib/capability_capsules.py
sed -n '1,320p' lib/architecture_guard.py
sed -n '1,320p' lib/workflow_guard.py

python3 -m json.tool config/logical-operators.json >/tmp/logical-operators.json
python3 -m json.tool config/physical-operators.json >/tmp/physical-operators.json
python3 -m json.tool config/actor-hosts.json >/tmp/actor-hosts.json

sed -n '1,260p' config/capability-capsules.registry.yaml
sed -n '1,260p' schemas/plugin.schema.json
sed -n '1,260p' plugins/autosci/manifest.yaml
sed -n '1,320p' plugins/autosci/README.md
```

Read every scientific workflow, capsule, gate, and relevant test:

```bash
find workflows -maxdepth 1 -type f -name 'scientific*.json' -print -exec sed -n '1,1200p' {} \;
find capability-capsules -maxdepth 1 -type f -name 'cap.research-*.yaml' -print -exec sed -n '1,500p' {} \;
find schemas/evidence -maxdepth 1 -type f -name '*.json' -print | sort
find evaluators/scientific -maxdepth 1 -type f -print | sort

sed -n '1,900p' evaluators/scientific/lifecycle_gate.py
sed -n '1,400p' evaluators/scientific/autosci_skill_run_gate.py
sed -n '1,500p' evaluators/scientific/autosci_feature_parity_gate.py
sed -n '1,360p' tests/evaluators/scientific/test_lifecycle_gate.py
```

Read the AutoSci adapter paths in full. Do not skim only the CLI surface:

```bash
cd "$WORK_REPO/harness"

sed -n '1,1200p' plugins/autosci/config/feature_parity_routes.v1.json
sed -n '1,1200p' plugins/autosci/config/feature_operator_bindings.v1.json
sed -n '1,1000p' plugins/autosci/bin/autosci_skill_shim.py
sed -n '1,10000p' plugins/autosci/bin/autosci_bridge.py
sed -n '1,1200p' plugins/autosci/bin/autosci_parity_bridge.py

find plugins/autosci/adapters -maxdepth 2 -type f -print -exec sed -n '1,700p' {} \;
find plugins/autosci/backends -maxdepth 2 -type f -print -exec sed -n '1,900p' {} \;
find plugins/autosci/tests -maxdepth 2 -type f -print | sort
sed -n '1,5000p' plugins/autosci/tests/test_autosci_skill_shim.py

sed -n '1,900p' ../tools/research_wiki.py
```

Read generated wrappers, but do not count them as implementations:

```bash
cd "$WORK_REPO"
find .agents/skills -mindepth 2 -maxdepth 2 -name SKILL.md -print | sort
sed -n '1,240p' .agents/skills/research/SKILL.md
```

### 5.3 Native AutoSci behavioral specification

Read the complete native architecture and schema:

```bash
cd "$AUTOSCI_REPO"

sed -n '1,700p' README.md
sed -n '1,700p' CLAUDE.md
sed -n '1,700p' runtime/CLAUDE.md
find runtime/schema -maxdepth 2 -type f -print -exec sed -n '1,900p' {} \;
sed -n '1,1600p' tools/research_wiki.py
```

Read every native skill protocol:

```bash
cd "$AUTOSCI_REPO"
find .claude/skills -mindepth 2 -maxdepth 2 -name SKILL.md -print | sort

for f in $(find .claude/skills -mindepth 2 -maxdepth 2 -name SKILL.md | sort); do
  echo "===== $f ====="
  sed -n '1,1200p' "$f"
done
```

If the repository uses `i18n/en/skills/` as the current canonical path, compare it with `.claude/skills/` and record any divergence.

Read the native tools used by the critical workflows:

```bash
cd "$AUTOSCI_REPO"
find tools -maxdepth 2 -type f | sort | grep -E \
  '(research_wiki|init_discovery|prepare_paper_source|discover|daily_arxiv|send_email|remote|poster|wiki2dag|visualize|serve|lint|reset)' \
  | while read -r f; do echo "===== $f ====="; sed -n '1,1600p' "$f"; done
```

---

## 6. Establish the baseline before changing code

Run the current tests using the repository’s documented environment. Record exact commands, exit codes, duration, and failures.

```bash
cd "$WORK_REPO"

# Rebuild only if needed and only from the committed dependency manifest.
test -x .venv/bin/python || {
  MISE_PYTHON="${MISE_PYTHON:-$HOME/.local/share/mise/installs/python/3.14.2/bin/python3}"
  "$MISE_PYTHON" -m venv .venv
  UV_CACHE_DIR="${UV_CACHE_DIR:-$HOME/Library/Caches/uv}" \
    uv pip sync --python .venv/bin/python requirements/autosci-solar-native-dev.txt
}

export PYTHONPATH="$WORK_REPO/harness"

.venv/bin/python -m pytest harness/plugins/autosci/tests -q
.venv/bin/python -m pytest harness/tests/evaluators/scientific -q

.venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py \
  inventory --out /tmp/autosci-parity-baseline.json
python3 -m json.tool /tmp/autosci-parity-baseline.json >/tmp/autosci-parity-baseline.pretty.json
```

Also run static consistency probes:

```bash
cd "$WORK_REPO/harness"

python3 -m json.tool config/logical-operators.json >/dev/null
python3 -m json.tool config/physical-operators.json >/dev/null
python3 -m json.tool config/actor-hosts.json >/dev/null
python3 -m json.tool plugins/autosci/config/feature_parity_routes.v1.json >/dev/null
python3 -m json.tool plugins/autosci/config/feature_operator_bindings.v1.json >/dev/null

python3 lib/architecture_guard.py validate \
  --graph workflows/scientific_research_lifecycle_full_v1.json --strict
python3 lib/architecture_guard.py validate \
  --graph workflows/scientific_research_resume_v1.json --strict
```

Create a baseline report before edits:

```text
docs/integrations/autosci/continuation-baseline-2026-06-25.md
```

It must include:

- exact OpenSolar and AutoSci SHAs;
- working tree state;
- test commands/results;
- current 28-route status counts;
- current registry-chain failures;
- current `$research` execution trace;
- current lifecycle-gate false-positive probe;
- current committed-versus-regenerated parity inventory diff;
- known external dependencies unavailable in the environment.

---

## 7. First priority: repair truth and auditability

Do this before implementing new behavior.

### 7.1 Replace the one-dimensional route status model

Current `coverage_status` conflates completeness and safety. Add explicit fields to the route and generated parity schemas:

```json
{
  "semantic_parity": "full | partial | missing",
  "execution_policy": "pure | bounded_local | approval_required | provider_required",
  "proof_level": "E0 | E1 | E2 | E3 | E4 | E5",
  "proof_refs": [],
  "remaining_requirements": []
}
```

Preserve backward compatibility temporarily if needed, but make the new fields authoritative.

Definitions:

```text
E0 declared route/config only
E1 schema/capsule/graph/gate validates
E2 fixture/smoke action passes
E3 one real bounded stage executes with audited evidence
E4 recoverable multi-stage lifecycle executes through Solar
E5 representative end-to-end workflow reaches final accepted artifacts
```

A safety-gated route may be `semantic_parity=full` only if the approved execution path has at least E3 evidence, and lifecycle commands require E4/E5.

### 7.2 Eliminate stale parity artifacts

The committed Phase 19 inventory is inconsistent with later route status. Implement one of:

- regenerate and commit the current inventory deterministically; or
- stop committing generated run inventories and generate them in CI/release artifacts.

Add a test that fails when:

```text
route config counts != generated inventory counts
route item fields != inventory item fields
native skill set != routed skill set
committed artifact provenance ref != current config ref
```

Never permit a completed inventory with stale full claims.

### 7.3 Split contract gates from runtime acceptance gates

Rename or separate current lifecycle validation:

```text
lifecycle_contract_gate.py
lifecycle_runtime_gate.py
```

The contract gate validates only graph structure.

The runtime gate must require:

- expected job ID;
- complete node-result map for every required executed node;
- node gate-result map;
- artifact paths that exist;
- schema validation;
- artifact hashes;
- provenance matching job/sprint/node;
- dependency evidence linkage;
- approval evidence for gated effects;
- no failed or inconclusive required node;
- correct final state;
- final parent-gate evidence.

It must return inconclusive or failed—not passed—when result maps are absent.

Add negative tests for every missing field and cross-job artifact reuse.

### 7.4 Add a full-parity acceptance gate

The existing parity gate may continue validating inventory shape, but add an acceptance gate that rejects any command claimed full without the minimum proof level.

For `$research`, require E5.

---

## 8. Second priority: repair the complete scheduler binding chain

Create a deterministic registry audit tool, for example:

```text
harness/tools/audit_scientific_runtime_bindings.py
```

It must traverse every scientific workflow and verify:

```text
node.logical_operator exists
node.required_capabilities resolve to registered capsules
logical operator has a binding
binding candidate actor/physical operator exists
candidate condition is currently meaningful, not stale placeholder text
physical operator command exists
physical operator host_id exists in actor-hosts.json
host type is supported by operator runtime
plugin manifest declares capability
bridge action exists
expected Evidence ABI exists
node gate exists
```

Exit nonzero on any failure and emit JSON plus human-readable output.

### 8.1 Register a real local AutoSci backend host

Use the host type that `operator_runtime.py` actually supports for local commands. Do not invent an unsupported type merely to satisfy JSON.

Replace placeholder ownership such as:

```text
owner_host: solar@example-host
```

with a valid host reference. Include health and lifecycle fields consistent with the existing registry model.

### 8.2 Complete logical bindings

Ensure every operator in the full and resume graphs has at least one executable candidate, including:

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
ScientificPublicationProducer
ScientificWorkflowEvolver
```

Remove stale conditions such as `backend_action_pending` once the action is available. Do not replace them with `always` unless the operator is genuinely available and policy-compatible.

### 8.3 Correct physical operator metadata and policies

Do not label live-capable workers `autosci-adapter-fixture`.

Separate workers when policies differ. Examples:

```text
autosci-paper-local-worker            network denied/optional
scientific-discovery-provider-worker  network provider-limited
autosci-model-review-worker           explicit model-command/provider policy
autosci-experiment-local-worker       approval + allowlist + sandbox
autosci-experiment-remote-worker      approval + SSH/rsync host policy
autosci-tex-compile-worker            approval + tool allowlist
autosci-poster-render-worker          approval + browser/render policy
autosci-email-worker                  approval + secret/SMTP policy
```

The user-facing shim must not bypass these policy distinctions by directly calling unrestricted bridge code.

### 8.4 Reconcile the plugin manifest

Declare all eighteen target capabilities:

```text
cap.research-paper-ingest
cap.research-literature-discover
cap.research-memory-update
cap.research-graph-update
cap.research-paper-analyze
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
cap.research-publication-produce
cap.research-workflow-evolve
```

Declare actual optional dependencies, read/write scopes, external tools, and rollback/disable behavior.

---

## 9. Third priority: make `$research` submit and run a TaskGraph

This is the primary implementation objective.

### 9.1 Remove bridge-level lifecycle ownership

`run_research_lifecycle` may remain temporarily as a migration diagnostic/projection command, but it must not be the execution backend for `$research`.

Rename it to something truthful if retained, such as:

```text
project_research_lifecycle_state
```

It may summarize scheduler state. It may not decide that stages ran from generic wiki counts.

### 9.2 Introduce a typed workflow request

Create a schema such as:

```text
harness/schemas/workflows/scientific_research_request.v1.schema.json
```

Required fields should include:

```text
job_id
objective/topic/target
input papers or discovery seed
venue optional
start_from optional
skip_paper optional
max_iterations
execution_mode
provider policy
human gate policy
budget/time/resource constraints
artifact root
approval references if pre-authorized
```

### 9.3 Compile a job-specific TaskGraph

Implement a compiler that:

- loads the canonical workflow template;
- creates a unique job-scoped artifact root;
- resolves conditional nodes;
- adds explicit human-gate nodes;
- adds external-wait and collection nodes;
- assigns job/sprint/node IDs;
- binds inputs and predecessor artifacts;
- validates scopes and architecture;
- writes the instantiated graph under the job directory;
- submits it to the existing scheduler.

The compiler must not execute scientific work.

A suitable path might be:

```text
harness/lib/research/scientific_workflow_compiler.py
```

### 9.4 Use the existing scheduler and operator runtime

The execution path must use the repository’s real scheduler state and physical operator dispatch. Do not implement a parallel ad hoc loop unless you are extending the existing scheduler in a general way.

Every node dispatch must record:

```text
job_id
sprint_id
node_id
attempt_id
logical_operator
selected physical operator
host/actor
capsule IDs
input evidence IDs and hashes
read/write scopes
approval state
command/action
start/end timestamps
exit/result state
output evidence IDs and hashes
gate verdict
```

### 9.5 Model the native lifecycle, not a flat linear chain

The instantiated graph must represent at least:

```text
Stage 0: bootstrap / inspect / optional init / optional ingest
Stage 1: ideation + novelty + independent review
Human Gate 1: accept/reject idea
Stage 2: experiment design + design review + code/setup inspection
Stage 3a: deploy
Stage 3b: wait/status
Stage 3c: collect
Stage 4: evaluate
Decision: validate | fail | iterate
Human Gate 2: accept result / request iteration / stop
Stage 5a: paper plan
Stage 5b: draft
Stage 5c: review/refine loop
Stage 5d: compile and submission checks
Final memory/graph/log update
Optional workflow-evolution proposal
```

Do not hide this inside one operator.

### 9.6 Explicit human gates

Represent approvals as durable task states and evidence artifacts, for example:

```text
human_decision.v1
```

Required fields:

```text
job_id
node_id
decision_type
decision
accepted/rejected artifact IDs
scope
constraints
actor/user reference
timestamp
signature/hash or immutable reference
```

A CLI or file-backed approval command may be used, but the scheduler must observe it and transition state.

### 9.7 External wait and resume

Deployment may yield:

```text
waiting_for_external
```

The scheduler must persist:

- remote/local process identity;
- host/session;
- launch command hash;
- output locations;
- polling policy;
- next eligible poll;
- timeout/cancellation policy.

A later process must be able to resume by job ID. Do not infer resume state from global wiki counts.

### 9.8 `--start-from` semantics

Support native-compatible `--start-from` only when predecessor evidence is supplied and accepted for the same job or explicitly imported with provenance.

Do not mark skipped predecessor stages complete from page existence alone. Record them as:

```text
imported_accepted
```

with source evidence and hashes, or reject the request.

### 9.9 `--skip-paper` semantics

Skipping publication must create an explicit conditional skip verdict. It must not leave publication nodes missing without explanation.

---

## 10. Fourth priority: implement native OmegaWiki invariants

The current simplified wiki helper is not sufficient for native AutoSci semantics.

### 10.1 Preferred implementation approach

Choose one of these, document the decision, and preserve licensing:

1. port the relevant native `runtime/loader.py`, schemas, and `tools/research_wiki.py` logic into `harness/plugins/autosci/omegawiki/`; or
2. implement equivalent generic Solar knowledge-state modules under the plugin and prove behavior against native golden fixtures.

Do not put AutoSci-specific schema mechanics into unrelated Solar control-plane core.

### 10.2 Required entity support

Support and validate at least:

```text
papers
concepts
topics
people
methods
ideas
experiments
Summary
foundations
```

### 10.3 Required lifecycle transitions

Enforce:

```text
idea:
  proposed -> in_progress
  in_progress -> tested
  tested -> validated | failed

experiment:
  planned -> running
  running -> completed | abandoned
```

Reject illegal transitions. Require `failure_reason` when an idea fails. Record before/after hashes and transition evidence.

Do not permit generic `set-meta status=...` to bypass the transition command.

### 10.4 Required graph and citation support

Implement:

- validated edge types;
- endpoint topology checks;
- confidence/evidence fields where required;
- symmetric-edge canonicalization;
- deduplication;
- citation graph separate from semantic graph;
- batch writes with transactional evidence;
- reference existence warnings/errors;
- provenance.

### 10.5 Required query and derived-state support

Implement:

- entity find by typed fields;
- rich query modes used by native skills;
- multi-hop neighbors with direction/type filters;
- semantic duplicate candidate search;
- purpose-driven context compilation;
- index rebuild;
- open-question rebuild;
- maturity/statistics;
- checkpoints for batch and resume;
- append-only log.

### 10.6 Workspace and ownership

Keep the human-facing workspace under a Solar-governed root such as:

```text
harness/artifacts/autosci/workspace/wiki/
```

Preserve source ownership boundaries and explicit mutation policies. Solar execution evidence stays under run/job artifact directories and must not pollute the human wiki.

### 10.7 Golden behavior tests

Create a small native-compatible fixture wiki and run equivalent operations against native AutoSci and OpenSolar implementation. Compare normalized outputs for:

- init;
- add edge/citation;
- duplicate detection;
- legal/illegal transitions;
- context compilation;
- open questions;
- checkpoints;
- query/neighbors;
- dedup.

Document intentional differences.

---

## 11. Fifth priority: complete ideation and Gate 1

### 11.1 Independent generation

Native ideation uses independent perspectives. Implement two separately evidenced generation calls or workers:

```text
idea_generator_primary
idea_generator_independent
```

They must not share generated outputs before completion. Record model/provider, prompt hash, input context hash, and output artifact.

### 11.2 Merge, dedup, and anti-memory

A synthesis node must:

- merge candidates;
- detect duplicates;
- compare against existing ideas;
- compare against failed/rejected ideas;
- preserve rejected candidates and reasons;
- prevent silent regeneration of known failed ideas.

### 11.3 Novelty stack

Require explicit evidence for configured layers, for example:

- wiki comparison;
- live web/provider search;
- Semantic Scholar/DeepXiv or equivalent;
- independent reviewer opinion.

Unavailable providers must produce inconclusive layer evidence. Never replace them with fixture candidates in a real run.

### 11.4 Idea evaluation

Emit:

- novelty rationale;
- feasibility;
- expected contribution;
- resource estimate;
- risks;
- falsifiable hypothesis;
- evidence IDs;
- recommendation.

### 11.5 Gate 1

Present accepted candidates to the human gate. Persist the decision. Transition the selected idea to `in_progress`. Preserve rejected/failed candidates appropriately.

### 11.6 Pilot branch

When configured, instantiate:

```text
pilot design -> pilot run -> pilot evaluation
```

Pilot behavior must not be reduced to ordinary full experiment output with renamed fields.

---

## 12. Sixth priority: complete the experiment lifecycle

### 12.1 Design

The design node must produce:

- hypothesis and claim linkage;
- baseline and justified absence rules;
- variables/controls;
- datasets/model/hardware/framework;
- metrics and success criteria;
- run matrix;
- artifact plan;
- expected duration/resource budget;
- code/setup plan;
- failure and stop conditions;
- independent design review evidence.

Create or update a typed experiment entity with `planned` status through the wiki API.

### 12.2 Code/setup preparation and inspection

Separate code generation/modification from execution. Before run approval, require evidence for:

- files changed/generated;
- static inspection;
- command allowlist;
- dependency/environment lock;
- data access boundaries;
- expected output paths;
- cleanup/rollback.

### 12.3 Approved deployment

Support at least one fully audited bounded local executor before expanding remote execution.

The approval contract must bind:

- exact command or command digest;
- working directory;
- environment allowlist;
- input hashes;
- output paths;
- time/memory limits;
- network policy;
- approval reference.

Record stdout, stderr, exit code, process ID, and start time.

### 12.4 Asynchronous state

Long-running deployment must return a durable process/session record and set:

```text
experiment status: running
node state: waiting_for_external
job state: waiting_for_external
```

It must not fabricate a result or mark the node complete.

### 12.5 Status

`$exp-status` and `$research --resume` must inspect the durable deployment record. The status operator must distinguish:

```text
queued
running
completed-awaiting-collection
failed
lost
cancelled
unknown
```

### 12.6 Exactly-once collection

Collection must be idempotent. Use a collection identity and artifact hashes. Repeated collection should return the existing accepted evidence rather than duplicate or overwrite it silently.

### 12.7 Independent evaluation

Evaluation must consume collected artifacts, not backend self-report alone. Require:

- metrics;
- baseline comparison;
- logs;
- limitations;
- independent model/reviewer evidence where configured;
- four-path verdict: supported, partially supported, not supported, inconclusive.

### 12.8 State transitions and iteration

On accepted evaluation:

- transition experiment `running -> completed` or `abandoned`;
- transition idea `in_progress -> tested`;
- after final human/result decision, transition idea `tested -> validated | failed`;
- if inconclusive and iteration is approved, create a new bounded experiment attempt linked to the idea;
- enforce `max_iterations`.

### 12.9 Resume test

Terminate the orchestrator after deployment, restart it, poll, collect, evaluate, and finish. Prove completed earlier nodes were not rerun.

---

## 13. Seventh priority: complete publication and Gate 2

### 13.1 Result Gate 2

After experiment evaluation, require durable human selection:

```text
publish
iterate
stop_as_failed
stop_as_inconclusive
```

The decision must bind the accepted verdict and experiment evidence.

### 13.2 Paper plan

Build the plan from accepted idea/experiment/wiki graph state. Include:

- contribution claims;
- evidence map;
- section outline;
- related-work/citation plan;
- figure plan;
- table plan;
- limitations;
- venue constraints;
- independent review evidence.

### 13.3 Paper draft

Produce a real manuscript project, not only a generic report:

```text
paper/
  main.tex
  sections/
  figures/
  tables/
  references.bib
  build/
  evidence-index.json
```

Every empirical claim must reference accepted evidence. Unsupported claims must be absent or explicitly qualified.

### 13.4 Figures and tables

Generate figures/tables from experiment artifacts or document justified absence. Record source data and rendering commands.

### 13.5 Bibliography

Verify citation identifiers and BibTeX records. Reject unresolved or fabricated citations.

### 13.6 Review/refine loop

Use independent review evidence. Classify findings and apply bounded revisions. Rerun relevant gates after changes. Preserve before/after hashes and iteration history.

### 13.7 Compile

Use an allowlisted compiler in a bounded environment. Require:

- successful exit;
- actual PDF path;
- nonzero file size;
- positive page count;
- no unresolved references/citations;
- no fatal compile errors;
- submission checklist.

A supplied PDF is not accepted merely because it exists; it must be produced or explicitly imported and accepted with provenance.

### 13.8 Rebuttal and poster

After the core paper path is complete, close native behavior for:

- reviewer-comment atomization;
- evidence mapping;
- independent stress test;
- rich and formal rebuttal outputs;
- PaperX DAG;
- HTML poster;
- figure extraction;
- overflow validation;
- PNG rendering.

These may remain approval/provider gated but must have real approved execution tests before semantic parity is full.

---

## 14. Decompose the backend bridge safely

Do not perform an unreviewable big-bang rewrite. Extract one bounded domain at a time while retaining CLI compatibility.

Recommended structure:

```text
harness/plugins/autosci/
  bin/
    autosci_bridge.py          # CLI parser and dispatch only
    autosci_skill_shim.py      # UX parser/router only
  actions/
    knowledge.py
    analysis.py
    ideation.py
    experiments.py
    publication.py
    admin.py
  runtime/
    approvals.py
    evidence.py
    executors.py
    providers.py
    workspace.py
  omegawiki/
    loader.py
    schemas/
    graph.py
    lifecycle.py
    checkpoints.py
    context.py
  adapters/
  backends/
  tests/
```

Rules:

- action functions perform one bounded action;
- action functions do not invoke the next lifecycle action;
- scheduler state lives outside the plugin action implementation;
- provider/tool adapters return explicit evidence;
- all writes remain scope-checked;
- shared evidence and approval helpers are unit-tested;
- compatibility aliases are documented and temporary.

---

## 15. Update the declarative workflows

Revise `scientific_research_lifecycle_full_v1.json` and resume handling so they represent executable semantics.

Do not create a separate static resume workflow that merely omits nodes unless it is generated from state. Prefer one canonical workflow plus persisted per-node status and conditional scheduling.

At minimum add or represent:

```text
bootstrap_inspect
optional_init
optional_ingest
ideate_primary
ideate_independent
idea_merge
novelty_check
idea_review
human_gate_idea
experiment_design
experiment_design_review
experiment_prepare
experiment_deploy
external_wait
experiment_status
experiment_collect
experiment_evaluate
human_gate_result
iteration_decision
paper_plan
paper_draft
paper_review
paper_refine
paper_compile
publication_gate
memory_graph_finalize
workflow_evolution_proposal
```

Use branches/conditions, not an unconditional linear sequence.

Every node must have:

```text
id
logical_operator
required_capabilities
read_scope
write_scope
input artifact bindings
expected Evidence ABI
gate
acceptance conditions
depends_on / conditional dependencies
retry policy
resume policy
architecture policy
approval/external-wait policy where relevant
```

---

## 16. Tests you must add

### 16.1 Static consistency

- all 18 target capabilities in manifest/registry;
- all workflow operators have bindings;
- all physical candidates and hosts exist;
- all actions and gates exist;
- no stale pending conditions;
- no AutoSci semantic names in generic layers except allowed provenance/backend fields.

### 16.2 Lifecycle gate negatives

Test that runtime acceptance rejects:

- empty node results;
- missing gate results;
- wrong job ID;
- wrong node ID;
- missing artifact;
- invalid schema;
- hash mismatch;
- reused artifact from another job;
- unapproved side effect;
- inconclusive required node;
- bridge-owned full workflow.

### 16.3 Scheduler dispatch integration

Use the actual graph scheduler and operator runtime. Assert:

- node readiness;
- binding;
- host resolution;
- lease acquisition;
- envelope write;
- action execution;
- result recording;
- node gate;
- downstream readiness;
- parent gate.

Mock only external services, not the scheduler path itself.

### 16.4 Suspend/resume

Use a test executor that launches a bounded process and deliberately waits. Restart the orchestration process and resume from durable state.

### 16.5 OmegaWiki golden tests

Compare normalized behavior with native AutoSci for legal transitions, illegal transitions, graph writes, citations, dedup, checkpoints, context, and queries.

### 16.6 Real bounded local lifecycle

Create a tiny scientific task and repository where an experiment command can run quickly and safely. It must not be a precomputed result fixture. The command must generate metrics from actual execution.

### 16.7 Actual publication

Compile a minimal but real LaTeX manuscript using generated evidence and validate the PDF.

### 16.8 Failure and inconclusive cases

Prove:

- provider unavailable -> inconclusive, not synthetic success;
- experiment command failure -> failed with logs;
- result missing -> inconclusive;
- novelty evidence missing -> cannot pass idea gate;
- compile failure -> no publication success;
- rejected human gate -> downstream nodes do not run;
- illegal lifecycle transition -> rejected.

---

## 17. Required end-to-end acceptance scenarios

### Scenario A — Clean bounded local research lifecycle

Starting from an empty job-scoped workspace:

1. ingest one real local paper or structured source;
2. populate typed wiki entities/edges/citations;
3. generate and evaluate ideas with two independently evidenced generators;
4. obtain Gate 1 approval;
5. design a bounded experiment;
6. execute a real local command;
7. collect actual metrics;
8. evaluate and transition states;
9. obtain Gate 2 approval;
10. create plan and draft;
11. compile an actual PDF;
12. pass parent lifecycle gate;
13. update memory/graph/log;
14. emit a final job report.

### Scenario B — Suspend and resume

1. run through deployment;
2. enter `waiting_for_external`;
3. terminate orchestration process;
4. restart;
5. resume by job ID;
6. prove passed nodes were not rerun;
7. collect exactly once;
8. finish the lifecycle.

### Scenario C — Negative/inconclusive lifecycle

Run a case where the experiment evidence is insufficient. The lifecycle must produce an inconclusive verdict or bounded iteration request, not a supported claim or publication success.

### Scenario D — Gated utility operations

Run approved, audited examples of:

- edit;
- refine apply;
- reset dry-run and optionally approved reset in a disposable workspace;
- paper compile;
- poster render if renderer available;
- daily-arxiv provider/SMTP only if credentials and explicit approval are provided.

Do not block the core local lifecycle on unavailable external credentials. Record those routes as provider-gated with honest proof levels.

---

## 18. Expected command surface after implementation

Adapt to existing CLI conventions, but provide equivalent usable commands. Example target:

```bash
# Compile and start a new lifecycle.
./harness/solar-harness.sh '$research' \
  --topic "<topic>" \
  --paper "<path>" \
  --job-id "<job-id>" \
  --execution-mode bounded-local \
  --max-iterations 2

# Inspect durable state.
./harness/solar-harness.sh '$exp-status' --pipeline "<job-id>"

# Record a human idea decision.
python3 harness/tools/scientific_workflow.py approve \
  --job-id "<job-id>" \
  --gate idea \
  --accept "<idea-id>" \
  --approval-ref "<ref>"

# Resume after approval or external completion.
python3 harness/tools/scientific_workflow.py resume --job-id "<job-id>"

# Validate runtime acceptance.
python3 harness/evaluators/scientific/lifecycle_runtime_gate.py \
  "harness/artifacts/scientific/<job-id>/lifecycle_summary.json"

# Audit registry and parity truth.
python3 harness/tools/audit_scientific_runtime_bindings.py --strict
python3 harness/plugins/autosci/bin/autosci_parity_bridge.py \
  inventory --out /tmp/autosci-parity-current.json
```

Do not invent commands without implementing and testing them.

---

## 19. Documentation and phase logs

Create a dedicated continuation log and a real Phase 15 log:

```text
docs/integrations/autosci/phase15-progress-log.md
docs/integrations/autosci/native-lifecycle-continuation-log.md
```

Every implementation step must record:

- objective;
- files changed;
- architecture decision;
- commands run;
- exit codes;
- test counts;
- artifact paths;
- hashes where relevant;
- current semantic parity/execution policy/proof level;
- remaining blockers;
- whether results are fixture, mocked-provider, bounded real stage, recoverable lifecycle, or full end-to-end.

Never write “complete” without naming the acceptance scenario that passed.

Update:

- workflow map;
- parity matrix;
- plugin README;
- manifest;
- route config;
- operator binding config;
- generated inventory;
- generated skill wrappers only if route metadata changes.

---

## 20. Repository hygiene

Do not commit local runtime state unless it is an intentional test fixture.

Inspect and clean or ignore as appropriate:

```text
.DS_Store
*.pid
coordinator/watchdog state
local inbox/outbox state
generated run directories
local provider outputs
temporary PDFs/TeX builds
local caches
backups
```

Preserve small, deterministic fixtures under explicit test directories. Do not delete historical evidence the user may need without recording and obtaining approval.

---

## 21. Required incremental PR slicing

Do not combine all work into one opaque patch. Prefer:

```text
PR 1: truth model, parity regeneration, contract/runtime gate split
PR 2: registry/host/binding/manifest repair
PR 3: workflow request/compiler and scheduler-native $research skeleton
PR 4: durable lifecycle state, human gates, wait/resume
PR 5: OmegaWiki schema/lifecycle/graph/checkpoint parity
PR 6: independent ideation, novelty, Gate 1, pilot path
PR 7: experiment deploy/status/collect/eval/iteration
PR 8: publication plan/draft/review/compile and Gate 2
PR 9: remaining utility/admin command parity
PR 10: full acceptance scenarios, inventory, docs, cleanup
```

Each PR must leave a human-verifiable artifact, deterministic test, or real bounded runtime result.

---

## 22. Prohibited shortcuts

Do not do any of the following:

- mark routes full because all 28 have wrappers;
- mark routes full because a schema validates;
- use fixture data in a non-smoke run;
- silently fall back to fixture data when a provider fails;
- pre-create wiki files and call that a completed stage;
- accept supplied evidence without job/provenance/hash validation;
- infer stage completion from global page counts;
- make the lifecycle gate pass by setting `lifecycle_status: passed` alone;
- change tests to expect the current false-positive behavior;
- call native AutoSci `/research` as a black box;
- move AutoSci workflow semantics into Solar core without a reusable abstraction;
- add one giant `ScientificResearchRunner` physical operator;
- let `ScientificWorkflowEvolver` act as the research workflow executor;
- bypass physical operator/host policies through the shim;
- execute unapproved shell, remote, SMTP, browser, destructive, or secret-writing actions;
- claim a PDF was compiled because a file named `.pdf` was supplied;
- claim an experiment ran because a result JSON was supplied;
- silently apply workflow-evolution proposals;
- overwrite user changes or native AutoSci source;
- hide failures or unresolved dependencies in logs.

---

## 23. Completion criteria

Do not declare the migration complete until every item below is proven:

```text
[ ] Current route inventory and committed artifact agree.
[ ] Semantic parity, execution policy, and proof level are separate.
[ ] All 18 target capabilities are in capsules, registry, and plugin manifest.
[ ] Every full/resume workflow logical operator has an executable binding.
[ ] Every candidate physical operator has a valid registered host.
[ ] $research submits a TaskGraph to graph_scheduler.
[ ] autosci_bridge owns no end-to-end stage sequence.
[ ] Every node dispatch goes through operator_runtime and records a lease/result.
[ ] Lifecycle runtime gate rejects empty/missing result maps.
[ ] All accepted artifacts are job/node scoped and hash-bound.
[ ] Human Gate 1 and Gate 2 are durable.
[ ] External wait/resume survives process restart.
[ ] Native idea and experiment lifecycle transitions are enforced.
[ ] Typed graph and citation invariants are enforced.
[ ] Checkpoints and context compilation exist.
[ ] Independent ideation/review evidence exists.
[ ] Failed-idea anti-memory is preserved.
[ ] A real bounded local experiment executes and is collected/evaluated.
[ ] Collection is idempotent.
[ ] Iteration is bounded and stateful.
[ ] A real manuscript is drafted and an actual PDF is compiled/validated.
[ ] A clean full lifecycle reaches the parent gate without fixture fallback.
[ ] A suspend/resume lifecycle completes without rerunning passed nodes.
[ ] A negative lifecycle remains failed/inconclusive and does not overclaim.
[ ] Final parity inventory contains no unsupported full status.
[ ] Intermediate artifacts are human-inspectable.
[ ] AutoSci remains a bounded backend implementation, not workflow owner.
```

---

## 24. Required response format after each implementation slice

Return exactly these sections:

### A. Baseline and scope

- OpenSolar SHA/branch
- AutoSci SHA/branch
- slice objective
- files intentionally in scope
- files intentionally out of scope

### B. Findings before change

- concrete defects
- source paths and line/function references
- why each defect violates Solar or native AutoSci semantics

### C. Changes made

For each file:

```text
path
purpose
behavioral change
architecture impact
compatibility impact
```

### D. Commands and results

Provide exact commands, exit codes, and concise outputs. Distinguish:

```text
static validation
unit test
fixture/smoke
mocked provider
real bounded stage
scheduler integration
suspend/resume
end-to-end
```

### E. Artifacts and evidence

List:

- artifact path;
- schema;
- job/node IDs;
- hash;
- gate verdict;
- whether it is fixture or real.

### F. Parity status changes

Use:

```text
skill
previous semantic parity
new semantic parity
execution policy
proof level
proof refs
remaining requirements
```

### G. Known limitations and next slice

Be explicit. Never imply that future work is already complete.

---

## 25. Immediate first implementation slice

Begin with the following bounded slice; do not jump directly to publication or more wrappers.

### Slice objective

Create a trustworthy baseline and make the declarative scientific graph schedulable without executing the full external lifecycle yet.

### Required deliverables

1. `continuation-baseline-2026-06-25.md`
2. regenerated current parity inventory or removal policy
3. three-axis parity schema/config fields
4. contract/runtime lifecycle gate split
5. negative runtime-gate tests
6. scientific registry audit tool
7. valid local backend host registration
8. complete logical bindings for all nodes in the current full graph
9. corrected physical operator metadata/policies sufficient for bounded local actions
10. reconciled plugin manifest with all eighteen capabilities
11. one actual scheduler-dispatched bounded node, not a direct bridge call
12. a progress log with exact evidence

### First-slice acceptance

Run a small `ScientificPaperIngestor` or other safe local node through:

```text
instantiated TaskGraph
-> graph scheduler
-> logical binding
-> physical operator
-> registered local host
-> operator runtime
-> bounded bridge action
-> Evidence ABI
-> deterministic node gate
-> scheduler result
```

The acceptance artifact must include the selected operator/host and a recorded lease/result. A direct invocation of `autosci_bridge.py` does not satisfy this slice.

After this slice passes, proceed to the scheduler-native `$research` lifecycle skeleton and durable wait/resume state.

