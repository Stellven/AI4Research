# AutoSci → Solar-Native Migration Status Report  
## Branch reviewed: `Coconut-ch1ken/OpenSolar/tree/ChatGPT-check`

**Audience:** coding agent continuing the AutoSci-core-by-Solar migration.  
**Purpose:** verify actual code status, compare current branch against the native AutoSci target plan, and provide concrete next actions.

---

## 0. Executive verdict

The `ChatGPT-check` branch is a meaningful improvement over the previous snapshot. It adds a new explicit `$research --scheduler-run` path, a `run_scientific_lifecycle_smoke.py` scheduler-lifecycle driver, human-gate flags, scheduler-specific experiment/compile evidence flags, local session/collection ledger logic for experiments, and stricter route limitations describing exactly-once/ledger gaps.

However, **this branch is still not full AutoSci parity** and should not be declared complete.

The best current classification is:

> **Broad AutoSci slash-command compatibility + strong typed-evidence bridge + early scheduler-dispatched lifecycle proof, but not yet a fully native Solar research runtime.**

The biggest shift from the previous branch is that `$research` is no longer purely a lifecycle projection wrapper. It can now invoke a scheduler-lifecycle smoke driver through `--scheduler-run`. But this is still a **smoke harness**, not the final generalized Solar workflow runner promised by the implementation plan.

---

## 1. Ground-truth target from the implementation plan

The implementation plan requires every capability to follow this architecture:

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

Non-negotiable rules from the plan:

1. No black-box `AutoSciRunner`.
2. AutoSci code remains under `harness/plugins/autosci/`.
3. Workflow semantics move into Solar operators, capsules, TaskGraphs, evidence schemas, and gates.
4. Capsules use generic `cap.research-*` names.
5. Every phase leaves a human-testable artifact or command.
6. A node is not complete if it lacks verifiable evidence.

Target full lifecycle shape:

```text
ScientificLiteratureDiscoverer
  -> ScientificPaperIngestor
  -> ScientificPaperAnalyzer
  -> ScientificMemoryUpdater
  -> ScientificGraphUpdater
  -> ScientificClaimExtractor
  -> ScientificMethodExtractor
  -> ScientificCodeEvidenceMapper
  -> ScientificIdeaGenerator
  -> ScientificIdeaEvaluator
  -> ScientificExperimentDesigner
  -> ScientificExperimentRunner
  -> ScientificExperimentMonitor
  -> ScientificClaimVerifier
  -> ScientificReportPlanner
  -> ScientificReportDrafter
  -> ScientificPublicationProducer
  -> ScientificMemoryUpdater
  -> ScientificWorkflowEvolver
```

---

## 2. Current migration progress

### 2.1 Route coverage

`harness/plugins/autosci/config/feature_parity_routes.v1.json` still contains **28 native AutoSci-like routes**, covering the main command surface:

- ask
- check
- daily-arxiv
- discover
- edit
- exp-design
- exp-eval
- exp-pilot-eval
- exp-pilot-run
- exp-run
- exp-status
- ideate
- ingest
- init
- novelty
- paper-compile
- paper-draft
- paper-plan
- poster
- prefill
- rebuttal
- refine
- research
- reset
- review
- setup
- survey
- visualize

Current status by route file:

```text
full:    0
partial: 17
gated:   11
missing: 0
```

This remains honest: the branch does not claim full parity in the route config.

### 2.2 Important new route-config changes versus previous snapshot

The meaningful changes are mostly around `/research`, `/exp-run`, and `/exp-status`.

#### `/research`

The route now lists two primary tools:

```json
[
  "harness/workflows/scientific_research_lifecycle_full_v1.json",
  "tools/run_scientific_lifecycle_smoke.py"
]
```

Its limitation text now says:

- `$research --scheduler-run` can dispatch the existing scientific lifecycle through `operator_runtime`;
- `--scheduler-include-human-gates` records idea/results approval pauses;
- `--online` can carry supplied source approval/runtime evidence into strict scheduler source mode;
- scheduler experiment stages can receive explicit `--experiment-*` evidence;
- `--experiment-execute-approved` can run an allowlisted approved local experiment command;
- scheduler publication compile can use compile-specific approved runtime evidence or `--compile-execute-approved`;
- full parity still requires real provider evidence, audited remote/session stage runners, and submission/anonymity checks.

This is a real architectural step forward.

#### `/exp-run` and `/exp-status`

The limitations now explicitly mention:

- local session registry status,
- approved pull-results collection evidence,
- local collection identity ledger,
- remote/session exactly-once collection still partial.

This matches new code in `autosci_bridge.py` that records session registry state and collection ledger entries.

---

## 3. Actual code status

### 3.1 `$research --scheduler-run` now exists

`autosci_skill_shim.py` adds many scheduler-specific native options:

```text
--lifecycle-summary
--scheduler-run
--scheduler-timeout
--scheduler-include-blocked-external
--scheduler-include-human-gates
--scheduler-dispatch-external-evidence
--idea-approval-ref
--results-approval-ref
--experiment-approval-ref
--experiment-runtime-evidence
--experiment-allowlist-evidence
--experiment-before-artifact
--experiment-after-artifact
--experiment-execute-approved
--compile-target
--compile-approval-ref
--compile-runtime-evidence
--compile-allowlist-evidence
--compile-before-artifact
--compile-after-artifact
--compile-execute-approved
```

The shim has a function:

```python
run_research_scheduler_lifecycle(args, run_id, work_dir)
```

It calls:

```text
harness/tools/run_scientific_lifecycle_smoke.py
```

and writes:

```text
scheduler_run_stdout.json
scheduler_run_stderr.txt
scientific_lifecycle_runtime.json
```

Then it attaches the scheduler summary as `lifecycle_summary` evidence before running the normal `run_research_lifecycle` bridge action.

This means the branch has moved from:

```text
$research -> projection-only evidence aggregator
```

to:

```text
$research --scheduler-run -> scheduler smoke runner -> lifecycle summary -> projection/bridge aggregation
```

That is a real improvement.

### 3.2 But `$research` still defaults to non-scheduler projection mode

The default non-smoke `$research` path still sets:

```python
if skill == "research" and not args.smoke:
    actions = ["run_research_lifecycle"]
```

Then the scheduler path only runs if:

```python
if skill == "research" and args.scheduler_run and not args.smoke:
    scheduler_lifecycle = run_research_scheduler_lifecycle(...)
```

Therefore:

```text
$research ...
```

without `--scheduler-run` is still mostly lifecycle projection / evidence aggregation.

Only:

```text
$research ... --scheduler-run
```

attempts scheduler-dispatched lifecycle execution.

### 3.3 The scheduler runner is a special smoke driver, not the final generalized workflow engine

`run_scientific_lifecycle_smoke.py` is not a generic `solar run-workflow` implementation. It hardcodes a `NODE_SPECS` list:

```text
literature_discover
paper_ingest
paper_analyze
memory_update_initial
graph_update
claim_extract
method_extract
code_evidence_map
idea_generate
idea_evaluate
experiment_design
experiment_run
experiment_monitor
claim_verify
report_draft
artifact_review
memory_update_final
workflow_evolve
```

It separately defines external nodes:

```text
report_plan
publication_produce
```

and human-gate nodes:

```text
idea_acceptance_gate
results_acceptance_gate
```

It then dispatches these node specs through `run_scientific_node_smoke.run(...)`.

This is useful, but it is **not yet the final native Solar workflow runner** because:

1. it is hardcoded to this lifecycle shape;
2. it does not appear to load and execute `harness/workflows/scientific_research_lifecycle_full_v1.json` as the source of truth;
3. it is explicitly named `smoke`;
4. publication nodes are still external/blocked unless additional evidence is supplied;
5. human gates are simulated as workflow-evolution evidence nodes;
6. it still depends on files that need verification locally.

### 3.4 Critical red flag: two imported runtime files appear missing from direct GitHub fetch

`run_scientific_lifecycle_smoke.py` imports:

```python
import run_scientific_node_smoke as node_smoke
```

and `_gate_lifecycle()` calls:

```text
harness/evaluators/scientific/lifecycle_runtime_gate.py
```

In my GitHub file-level verification, these expected files could not be fetched at:

```text
harness/tools/run_scientific_node_smoke.py
harness/evaluators/scientific/lifecycle_runtime_gate.py
```

This is a high-priority local check for the coding agent. If these files are actually absent from the branch, then `--scheduler-run` will fail immediately even though the route config and shim expose the feature.

Run this first:

```bash
cd "$SOLAR_REPO/harness"

test -f tools/run_scientific_node_smoke.py \
  || echo "MISSING: tools/run_scientific_node_smoke.py"

test -f evaluators/scientific/lifecycle_runtime_gate.py \
  || echo "MISSING: evaluators/scientific/lifecycle_runtime_gate.py"

python3 tools/run_scientific_lifecycle_smoke.py --help
```

If either file is missing, do not attempt to declare scheduler-run progress until the missing dependency is restored.

### 3.5 `lifecycle_gate.py` remains mostly a structural gate

`lifecycle_gate.py` still validates:

- expected lifecycle operator sequence,
- node uniqueness,
- parent gate declaration,
- artifact contract,
- resume contract,
- no black-box runner,
- required node fields,
- capability declarations,
- dependency order,
- bounded execution policy for experiment runner/monitor.

But its runtime fallback remains weak:

```python
if any(status in {"failed", "error"} for status in statuses):
    return "failed"
if any(status == "inconclusive" for status in statuses):
    return "inconclusive"
return "passed"
```

This means if no explicit failed/inconclusive result is present, it can pass. It is not sufficient as a strong runtime lifecycle gate.

This branch appears to intend a stronger `lifecycle_runtime_gate.py`, but I could not verify the file. The coding agent must fix or confirm this immediately.

---

## 4. Experiment lifecycle progress

This branch makes a real improvement in experiment identity and collection tracking.

### 4.1 New session registry support

`autosci_bridge.py` now has:

```python
_experiment_session_registry_path()
_record_experiment_session()
_experiment_session_from_registry()
_session_status_raw()
```

This supports local session-state recording for experiment launches and status checks.

### 4.2 New collection ledger support

`autosci_bridge.py` now has:

```python
_record_collection_ledger()
_collection_file_digests()
```

It computes a collection identity from:

```text
experiment_id + collected file digests
```

and stores entries in:

```text
wiki/collections/collection-ledger.json
```

This is the beginning of exactly-once/idempotent collection semantics.

### 4.3 Monitor/collect is stronger but still partial

`_action_monitor_experiment()` can now:

- resolve wiki experiment state,
- resolve local session registry state,
- consume approved runtime evidence,
- execute monitor collection if approved,
- attach stdout/stderr and collected-file artifacts,
- record collection ledger artifacts,
- mutate wiki experiment state,
- avoid duplicate collection mutation using the ledger.

However, the route text still correctly says:

```text
live remote process polling and distributed exactly-once collection remain partial
```

So this is not full AutoSci `/exp-run` + `/exp-status` parity yet.

### 4.4 Real local execution exists behind approval

`_action_run_experiment()` supports:

- fixture mode;
- human-approved mode;
- approved runtime evidence;
- approved executor execution;
- wiki state mutation after verified runtime evidence;
- stdout/stderr/result artifacts;
- runtime log and metrics propagation.

This is a real capability, but it still needs end-to-end lifecycle proof through `$research --scheduler-run`.

---

## 5. Publication lifecycle progress

Publication is still partial/gated.

The route config says scheduler publication compile can use compile-specific approved runtime evidence or `--compile-execute-approved`, but full parity still requires:

- real provider evidence,
- audited remote/session stage runners,
- submission/anonymity checks.

`run_scientific_lifecycle_smoke.py` defines external nodes:

```text
report_plan
publication_produce
```

These can be blocked unless evidence is supplied. That is correct governance, but not yet full AutoSci paper lifecycle parity.

Current publication status:

```text
paper-plan: partial
paper-draft: partial
paper-compile: gated
poster: gated
rebuttal: partial
survey: partial
publication_produce in scheduler lifecycle: external/blocked unless compile evidence supplied
```

---

## 6. Review / novelty / model evidence status

The branch preserves earlier improvements:

- local surrogate review,
- Review LLM evidence ingestion,
- Review LLM command bridge,
- OpenAI-compatible Review LLM provider mode,
- external novelty evidence,
- provenance checking,
- online provider degraded mode,
- writeback gated by external novelty + Review LLM evidence.

These areas are useful and increasingly robust, but final parity still requires live provider smoke and clear distinction between:

```text
local surrogate review
```

and

```text
completed independent Review LLM evidence
```

The coding agent must not allow local surrogate review to satisfy final AutoSci Review LLM gates.

---

## 7. Major differences vs previous report

### Improved since previous snapshot

1. `$research --scheduler-run` now exists.
2. `run_scientific_lifecycle_smoke.py` now attempts scheduler-dispatched lifecycle execution.
3. Scheduler path can attach lifecycle summary evidence back into `$research`.
4. Scheduler-specific human gate options exist.
5. Scheduler-specific experiment runtime/allowlist/before/after evidence options exist.
6. Scheduler-specific compile runtime/allowlist/before/after evidence options exist.
7. Experiment session registry exists.
8. Collection ledger / collection identity exists.
9. `exp-run` and `exp-status` route limitations now honestly mention local ledger/session support and remaining distributed exactly-once gaps.
10. `/research` route limitations are much more precise and operational.

### Still not solved

1. Default `$research` is still not scheduler execution; it requires `--scheduler-run`.
2. Scheduler runner is hardcoded smoke driver, not a general workflow runner.
3. The runner appears to depend on missing files:
   - `tools/run_scientific_node_smoke.py`
   - `evaluators/scientific/lifecycle_runtime_gate.py`
4. `feature_operator_bindings.v1.json` still says it is used by “skillgen operator smoke,” and still marks research partial.
5. `lifecycle_gate.py` still has weak runtime fallback.
6. Route config still has `full = 0`.
7. Publication and remote experiment paths remain gated/partial.
8. Plugin manifest still needs checking against the full capability list.
9. Human gates are represented as workflow-evolution evidence, not yet as a first-class generalized Solar human-gate primitive.
10. No final Acceptance Test F equivalent is proven by code alone.

---

## 8. Current status estimate

Do not treat these as exact percentages; they are practical engineering readiness estimates.

| Area | Current estimate | Notes |
|---|---:|---|
| AutoSci route coverage | 90%+ | 28 routes mapped; no missing command family seen. |
| Typed evidence bridge | 75–85% | Many schemas/actions/gates exist; runtime semantics still uneven. |
| Single-command compatibility | 65–75% | Many commands can run partial/gated evidence paths. |
| Experiment lifecycle | 55–65% | Improved local execution/session/ledger, but remote and full lifecycle are partial. |
| Publication lifecycle | 45–55% | Sidecars/compile evidence exist; full paper parity not proven. |
| Scheduler-native lifecycle | 35–45% | New smoke runner exists, but hardcoded, likely missing dependencies, not general. |
| Full native AutoSci parity | 40–50% | Strong progress, but not complete. |

---

## 9. Highest-priority tasks for the coding agent

### Task 1 — Verify and repair missing scheduler dependencies

Run:

```bash
cd "$SOLAR_REPO/harness"

test -f tools/run_scientific_node_smoke.py
test -f evaluators/scientific/lifecycle_runtime_gate.py

python3 tools/run_scientific_lifecycle_smoke.py --help
```

If missing, implement or restore them.

`run_scientific_node_smoke.py` must provide:

```python
def run(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    ...
```

and should:

1. build an operator envelope;
2. invoke `operator_runtime.submit()` or equivalent real operator dispatch;
3. wait for result;
4. run the correct evaluator gate;
5. return a node summary containing:
   - node_id
   - logical_operator
   - operator_id
   - action
   - status
   - evidence_path
   - operator_result_path
   - bridge_result_path
   - gate_result

`lifecycle_runtime_gate.py` must be stricter than `lifecycle_gate.py` and should fail or mark inconclusive if:

- `node_results` is missing;
- any required unblocked node lacks a result;
- any node lacks artifact path;
- any artifact path does not exist;
- any artifact hash is missing or mismatched;
- any required gate result is missing;
- any node result status is not passed;
- blocked nodes exist but are not marked as permitted blocked state;
- lifecycle claims passed while blocked nodes exist.

### Task 2 — Run the scheduler smoke locally and capture exact failure

After repairing missing files:

```bash
cd "$SOLAR_REPO/harness"

export HARNESS_DIR="$PWD"
python3 tools/run_scientific_lifecycle_smoke.py \
  --harness-dir "$PWD" \
  --job-id autosci-scheduler-smoke-local \
  --timeout-seconds 30 \
  --include-blocked-external \
  --out artifacts/scientific/scheduler-lifecycle-smoke/autosci-scheduler-smoke-local/scientific_lifecycle_runtime.json
```

Then inspect:

```bash
cat artifacts/scientific/scheduler-lifecycle-smoke/autosci-scheduler-smoke-local/scientific_lifecycle_runtime.json | python3 -m json.tool | sed -n '1,260p'
```

Expected acceptable states:

- `passed`: if all required nodes executed and no blocked nodes.
- `blocked`: if publication/external/human nodes are deliberately blocked and represented as blocked.
- `failed`: must be fixed before claiming scheduler-run support.

### Task 3 — Run `$research --scheduler-run`

```bash
cd "$SOLAR_REPO/harness"

export HARNESS_DIR="$PWD"
python3 plugins/autosci/bin/autosci_skill_shim.py text \
  '$research scheduler lifecycle --scheduler-run --scheduler-include-blocked-external --run-id scheduler-branch-check'
```

Expected output must include:

```text
scheduler_lifecycle_status
scheduler_lifecycle_summary_path
scheduler_lifecycle_node_count
scheduler_lifecycle_blocked_node_count
```

Then inspect the generated `autosci_skill_run.json`.

### Task 4 — Fix shim top-level status semantics

Current `autosci_skill_run.v1` still sets:

```python
"status": "failed" if failed_count else "completed"
```

This ignores partial/gated status unless scheduler failure occurs.

Change to one of:

```python
if failed_total:
    payload_status = "failed"
elif execution_status == "completed":
    payload_status = "completed"
else:
    payload_status = "inconclusive"
```

Or keep backward compatibility but add a hard gate that rejects any final parity claim based only on top-level `status`.

### Task 5 — Make `$research --scheduler-run` the required acceptance path

Do not let coding or checking agents treat plain `$research` as full lifecycle proof.

Acceptance must use:

```text
$research ... --scheduler-run
```

and then verify the produced `scientific_lifecycle.v1` summary.

### Task 6 — Move from hardcoded smoke runner to generic workflow runner

The current smoke runner is useful, but the plan requires TaskGraphs to be native scheduleable artifacts.

Build toward:

```bash
python3 tools/run_scientific_workflow.py \
  --workflow workflows/scientific_research_lifecycle_full_v1.json \
  --job-id <id> \
  --mode fixture
```

It should load workflow JSON as source of truth instead of relying on hardcoded `NODE_SPECS`.

### Task 7 — Prove human-gate resume

Use:

```bash
python3 tools/run_scientific_lifecycle_smoke.py \
  --include-human-gates \
  --job-id human-gate-smoke \
  --out artifacts/scientific/scheduler-lifecycle-smoke/human-gate-smoke/blocked.json
```

Then resume with:

```bash
python3 tools/run_scientific_lifecycle_smoke.py \
  --resume-summary artifacts/scientific/scheduler-lifecycle-smoke/human-gate-smoke/blocked.json \
  --idea-approval-ref approval-idea-001 \
  --results-approval-ref approval-results-001 \
  --out artifacts/scientific/scheduler-lifecycle-smoke/human-gate-smoke/resumed.json
```

Acceptance:

- first run blocks at idea/results gate;
- resume records approval evidence;
- completed nodes are not rerun;
- later nodes continue.

### Task 8 — Prove experiment exactly-once collection

Run a deterministic local experiment command twice with the same collected files.

Acceptance:

- first collect writes ledger entry;
- second collect identifies duplicate collection identity;
- second collect does not duplicate wiki mutation;
- ledger records file digests and evidence ids.

### Task 9 — Prove publication external-node resume

Run scheduler with blocked external nodes:

```bash
--include-blocked-external
```

Then resume with:

```text
--review-llm-evidence <artifact_review.v1>
--compile-target <paper-dir>
--compile-approval-ref <ref>
--compile-allowlist-evidence <allowlist>
--compile-before-artifact <before>
--compile-execute-approved
```

Acceptance:

- report_plan unblocks only with Review LLM evidence;
- publication_produce unblocks only with compile evidence/approved execution;
- final lifecycle summary distinguishes blocked vs passed.

---

## 10. Risks and potential issues

### Risk A — Missing files break scheduler-run

The most urgent risk is that `run_scientific_lifecycle_smoke.py` imports/calls files that were not directly fetchable at expected paths. If absent locally, `--scheduler-run` is currently broken despite route support.

### Risk B — Smoke driver may bypass true workflow JSON

The new runner is hardcoded. That is acceptable for a proof, but not for final Phase 15/18 acceptance. The coding agent should treat it as a bridge toward a real workflow runner.

### Risk C — Weak lifecycle gate can overclaim

`lifecycle_gate.py` can pass if no failed/inconclusive statuses are found. A runtime gate must require complete node/gate evidence.

### Risk D — Top-level status still overstates partial/gated runs

`autosci_skill_run.v1.status` may be `completed` even while `execution_status` is `partial` or `gated`. This must be corrected or strictly guarded.

### Risk E — Publication nodes are still external/blocked

`report_plan` and `publication_produce` are not part of the main `NODE_SPECS` default path. They are optional/external nodes requiring supplied evidence. This is correct governance but not full paper lifecycle parity.

### Risk F — Human gates are modeled but not generalized

Human approval gates are implemented as scheduler-visible workflow-evolution artifacts. This may be acceptable short-term, but a reusable Solar human-gate primitive would be cleaner.

### Risk G — Remote experiment lifecycle is not proven

Local approved command and local ledger are not the same as real remote SSH/rsync/screen/pull-results parity.

### Risk H — Plugin manifest may underdeclare actual capabilities

Previous inspection showed plugin manifest capability declarations lagging the full 18 capability registry. Re-check this branch and align it.

---

## 11. Recommended next coding-agent prompt

Copy this directly to the coding agent:

```text
You are continuing the AutoSci → Solar-native migration on branch ChatGPT-check.

Goal: verify and complete the scheduler-native lifecycle proof without overclaiming full parity.

Start by reading:
1. harness/plugins/autosci/bin/autosci_skill_shim.py
2. harness/tools/run_scientific_lifecycle_smoke.py
3. harness/evaluators/scientific/lifecycle_gate.py
4. harness/plugins/autosci/bin/autosci_bridge.py
5. harness/plugins/autosci/config/feature_parity_routes.v1.json
6. harness/workflows/scientific_research_lifecycle_full_v1.json
7. docs/integrations/autosci/*

First task:
- Check whether these files exist:
  - harness/tools/run_scientific_node_smoke.py
  - harness/evaluators/scientific/lifecycle_runtime_gate.py
- If absent, implement them before touching anything else.
- If present, run them and capture evidence.

Do not declare parity from logs or route config.
Do not treat plain `$research` as full lifecycle proof.
Only `$research --scheduler-run` plus a valid scientific_lifecycle.v1 runtime summary can count as lifecycle proof.

Minimum acceptance for this slice:
1. `python3 tools/run_scientific_lifecycle_smoke.py --help` works.
2. `python3 tools/run_scientific_lifecycle_smoke.py --harness-dir "$PWD" --job-id <id> --include-blocked-external --out <summary>` works.
3. Summary has schema `scientific_lifecycle.v1`.
4. Summary has node_results and gate_results for every unblocked required node.
5. Every node_result has artifact_path, artifact_sha256, expected_schema, gate, operator_result_path, and bridge_result_path.
6. All artifact_path files exist.
7. lifecycle_runtime_gate rejects incomplete summaries.
8. `$research ... --scheduler-run` attaches the scheduler summary into autosci_skill_run artifacts.
9. Top-level autosci_skill_run status cannot falsely represent partial/gated execution as full completion.
10. The final route inventory still reports full_count=0 unless a real end-to-end acceptance run proves otherwise.

After that:
- Implement exact-once collection tests for experiment collect.
- Implement human-gate block/resume tests.
- Implement external publication unblock/resume tests.
- Move hardcoded lifecycle smoke toward a generic workflow runner that reads `harness/workflows/scientific_research_lifecycle_full_v1.json` as source of truth.
```

---

## 12. Bottom line

The branch has advanced meaningfully. The main new capability is:

```text
$research --scheduler-run
```

which tries to connect `$research` to a scheduler-dispatched lifecycle smoke runner.

But full native AutoSci parity is not reached yet because:

1. the scheduler runner is still hardcoded and smoke-specific;
2. referenced runtime files appear missing or must be verified locally;
3. default `$research` is still projection mode;
4. route status remains partial/gated;
5. lifecycle runtime gating is not yet proven strong;
6. publication and remote experiment lifecycle remain gated/partial.

Recommended near-term milestone:

```text
Make `$research --scheduler-run` pass a strict lifecycle_runtime_gate with complete node/gate artifacts for all unblocked nodes.
```

Only after that should the team move to full remote experiment parity and full paper/publication parity.
