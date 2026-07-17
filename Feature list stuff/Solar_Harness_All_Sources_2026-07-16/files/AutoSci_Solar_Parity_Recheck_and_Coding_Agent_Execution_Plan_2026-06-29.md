# AutoSci-on-Solar Parity Recheck and Coding-Agent Execution Plan

Branch reviewed: `Coconut-ch1ken/OpenSolar/tree/ChatGPT-check`  
Native target used for comparison: `Coconut-ch1ken/AutoSci`  
Date: 2026-06-29  
Audience: coding agent continuing the Solar-native AutoSci migration.

---

## 1. Executive verdict

Current parity against native AutoSci is approximately:

```text
Overall native AutoSci parity:        ~58%
Credible range:                       55%–62%

Command-surface routing parity:       ~90%+
Evidence/schema/gate parity:          ~70%–78%
Single-command functional parity:     ~55%–65%
Scheduler-native lifecycle parity:    ~45%–55%
Full end-to-end /research parity:      ~40%–45%
Production/live-provider parity:       ~25%–35%
```

This branch is now an **advanced Solar-native AutoSci runtime prototype**, not merely a wrapper. It has 28 AutoSci-style skill routes, Solar scientific TaskGraph definitions, `Scientific*` logical operators, AutoSci-backed physical operators, a plugin manifest declaring the full research capability surface, typed Evidence ABI outputs, deterministic gates, a strict lifecycle runtime gate, a node-level scheduler smoke tool, `$research --scheduler-run` integration, and experiment runtime/session/collection-ledger support.

But it is not yet full native AutoSci parity because the full lifecycle runner is still smoke-oriented and partly hardcoded; `$research --scheduler-run` is optional; the main capability registry appears to omit the `cap.research-*` family despite manifest and capsule files existing; native OmegaWiki, `/ideate`, `/exp-run`, `/research`, and `/paper-draft` are substantially richer than the current migrated implementation; and live providers, remote experiment execution, full publication readiness, and production recovery are not proven.

---

## 2. Reference target: native AutoSci

Native AutoSci is a memory-centric full research lifecycle system with the following command surface:

```text
/setup /reset /prefill /init /ingest /discover /edit /ask /check
/daily-arxiv /ideate /exp-pilot-run /exp-pilot-eval /novelty /review
/exp-design /exp-run /exp-status /exp-eval /refine
/survey /paper-plan /paper-draft /paper-compile /research /rebuttal /poster /visualize
```

Key native behaviors to match:

### `/research`

Native `/research` provides Stage 0 bootstrap, 5 main stages, 2 human gates, session-resumable state, cold wiki auto-bootstrap, non-blocking experiment deployment, scheduled monitoring in auto mode, explicit `--start-from` resume modes, `pipeline-progress.md`, `PIPELINE_REPORT.md`, and a `paper/` directory if not skipped.

### `/ideate`

Native `/ideate` provides wiki maturity detection, landscape scan, WebSearch + Semantic Scholar + DeepXiv + arXiv, failed idea banlist, active idea dedup, structured paths A-E, dual-model brainstorming, first-pass filter, deep novelty validation, Review LLM review, writing validated and eliminated ideas to wiki, pilot experiment invocation, context/open-question rebuild, and growth report.

### `/exp-run`

Native `/exp-run` provides experiment code generation, dataset/config inspection, manual user inspection gate, Review LLM code review, sanity check and one auto-fix, local screen launch, remote SSH/rsync/screen launch, GPU checks, status polling, log tailing, collect mode, remote results pull, multi-seed mean ± std metrics, wiki experiment mutation, and RUN_REPORT.

### `/paper-draft`

Native `/paper-draft` provides `paper/main.tex`, `paper/math_commands.tex`, `paper/references.bib`, `paper/sections/*.tex`, `paper/figures/*`, `paper/tables/*`, venue template handling, BibTeX verification, figure/table generation, section-level evidence collection, de-AI polish, per-section Review LLM review, and full-paper Review LLM review.

### `tools/research_wiki.py` / OmegaWiki

Native OmegaWiki provides `init`, `slug`, `log`, `read-meta`, `set-meta`, `add-edge`, `add-citation`, `batch-edges`, `dedup-edges`, `dedup-citations`, `find`, `query`, `neighbors`, `compile-context`, `rebuild-context-brief`, `rebuild-open-questions`, `rebuild-index`, `transition`, `stats`, `maturity`, checkpoint save/load/clear/meta commands, schema-backed edge validation, and lifecycle transition validation.

---

## 3. Current OpenSolar branch progress

### 3.1 Route coverage

The branch has 28 configured AutoSci-style routes. Current route status remains:

```text
full:    0
partial: 17
gated:   11
missing: 0
```

This is honest and should be preserved until full acceptance evidence exists.

### 3.2 Manifest

`harness/plugins/autosci/manifest.yaml` now declares the full research capability surface:

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

This fixes the previous manifest-undercoverage issue.

### 3.3 Capability registry issue

The main capability registry currently appears to omit the `cap.research-*` capability family. This is a major issue because research capsule files exist, the plugin manifest declares them, and workflow nodes require them, but `harness/config/capability-capsules.registry.yaml` does not register them in the fetched branch. This can break capability admission, routing, validation, and scheduler consistency.

### 3.4 Logical and physical operators

`harness/config/logical-operators.json` now includes the scientific logical operators: `ScientificLiteratureDiscoverer`, `ScientificPaperIngestor`, `ScientificPaperAnalyzer`, `ScientificMemoryUpdater`, `ScientificGraphUpdater`, `ScientificClaimExtractor`, `ScientificMethodExtractor`, `ScientificCodeEvidenceMapper`, `ScientificIdeaGenerator`, `ScientificIdeaEvaluator`, `ScientificExperimentDesigner`, `ScientificExperimentRunner`, `ScientificExperimentMonitor`, `ScientificClaimVerifier`, `ScientificReportPlanner`, `ScientificReportDrafter`, `ScientificArtifactReviewer`, `ScientificPublicationProducer`, and `ScientificWorkflowEvolver`.

`harness/config/physical-operators.json` contains AutoSci physical workers for the major scientific actions: literature discovery, ingest, analysis, memory/graph update, claim/method/code extraction, idea generation/evaluation, experiment design/run/monitor, claim verification, artifact review, report plan/draft, publication compile, and workflow evolution.

Remaining issue: they still use `owner_host: stub_docker_sandbox` and `compat_maps_to: local_command_worker`. This is adequate for local proof, but not clean host-owned scheduler deployment.

### 3.5 Workflow

`harness/workflows/scientific_research_lifecycle_full_v1.json` exists and now includes a rich Solar-native lifecycle: literature discovery, paper ingest/analyze, memory/graph update, claim/method/code extraction, idea generation/evaluation, experiment design/run/monitor, claim verification, report plan/draft, artifact review, publication production, final memory update, and workflow evolution.

### 3.6 Runtime proof tooling

`harness/tools/run_scientific_node_smoke.py` now exists. It proves one node goes through `operator_runtime.submit -> operatord -> AutoSci bridge -> evidence file -> deterministic gate`.

`harness/evaluators/scientific/lifecycle_runtime_gate.py` now exists and is meaningfully strict. It checks `scientific_lifecycle.v1` runtime summaries, requires job IDs, required nodes, node results, gate results, artifact paths, hashes, schemas, sprint/node matching, and valid blocked-node semantics. It also rejects black-box `AutoSciRunner`/`BackendFullWorkflowRunner` and bridge-owned lifecycle projection actions.

### 3.7 `$research --scheduler-run`

`autosci_skill_shim.py` now has scheduler-run support. It can call `tools/run_scientific_lifecycle_smoke.py` and attach `scientific_lifecycle_runtime.json`, scheduler stdout/stderr, node count, blocked-node count, and workflow config alignment status.

However, plain `$research` still uses `run_research_lifecycle` unless `--scheduler-run` is supplied.

### 3.8 Status semantics fixed

The old overclaiming bug is fixed. The shim now makes partial/gated runs top-level `inconclusive` instead of `completed`:

```python
payload_status = (
    "failed"
    if failed_total
    else ("completed" if execution_status == "completed" else "inconclusive")
)
```

---

## 4. Percentage parity by subsystem

| Subsystem | Parity | Reason |
|---|---:|---|
| Command route coverage | 90–95% | 28 commands are routed, but all are still partial/gated. |
| Solar architecture skeleton | 70–75% | Workflows, logical operators, physical operators, manifest, gates exist. Registry issue blocks clean admission. |
| Evidence ABI / gates | 70–78% | Many deterministic gates exist; strict lifecycle runtime gate is good. Need more end-to-end artifact proof. |
| Single-command behavior | 55–65% | Many commands produce useful evidence. Native semantics are still richer. |
| Knowledge / OmegaWiki | 35–45% | OpenSolar wiki ABI is useful but much narrower than native OmegaWiki. |
| Ideation / novelty / review | 50–60% | External evidence and review hooks exist; dual-model full ideation pipeline not complete. |
| Experiment lifecycle | 50–60% | Runtime evidence, local execution, session registry, collection ledger exist; full codegen/remote/multiseed parity missing. |
| Publication lifecycle | 40–50% | Report/compile sidecars exist; full paper-draft/compile/poster parity incomplete. |
| Full `/research` orchestration | 40–45% | Scheduler-run exists, but smoke-specific and optional. |
| Production/live providers | 25–35% | Live S2/DeepXiv/arXiv/Review LLM/remote/GPU/SMTP/browser paths not fully proven. |

Overall weighted parity: **~58%**.

---

## 5. Issues remaining

### P0 — Capability registry drift

The plugin manifest and workflow require `cap.research-*`, but the main registry does not register them.

### P0 — Scheduler runner is still smoke-specific

`run_scientific_lifecycle_smoke.py` is valuable but hardcoded. It should become or wrap a generic workflow runner that reads `harness/workflows/scientific_research_lifecycle_full_v1.json` as the source of truth.

### P0 — `$research --scheduler-run` is optional

Plain `$research` still performs bridge lifecycle projection. For parity claims, require `$research ... --scheduler-run`.

### P1 — Host ownership is still stub/local

Physical operators are executable locally but not yet cleanly hosted under explicit Solar host IDs.

### P1 — OmegaWiki parity gap

Need typed entity lifecycle, citations, context compilation, maturity, checkpointing, transition validation.

### P1 — Native `/ideate` parity gap

Need full 5-phase ideation: maturity-aware search, dual-model brainstorm, A-E generation paths, banlist/active-dedup, novelty/review validation, accepted/eliminated idea writeback, pilot handoff, and growth report.

### P1 — Native `/exp-run` parity gap

Need experiment code generation, dataset/config inspection, manual approval gate, sanity check, local/remote deploy, screen/session handling, remote pull-results, multi-seed mean±std, DEPLOY_REPORT, and RUN_REPORT.

### P1 — Native publication gap

Need full `paper/` directory generation, BibTeX verification, figures/tables, section evidence mapping, Review LLM review, compile/anonymity/page/font checks.

### P2 — Live provider proof

Need approved live smoke for Semantic Scholar, DeepXiv, arXiv, Paper Copilot, Review LLM provider, latexmk/TeX, optional SMTP, optional browser rendering, and remote experiment server.

---

## 6. Immediate execution plan for coding agent

### Phase A — Verify branch and route inventory

```bash
export SOLAR_REPO="/path/to/OpenSolar"
cd "$SOLAR_REPO"
git checkout ChatGPT-check
git pull --ff-only || true
git status --short

cd "$SOLAR_REPO/harness"
export HARNESS_DIR="$PWD"

python3 plugins/autosci/bin/autosci_skill_shim.py skills list > /tmp/autosci_routes.json
python3 -m json.tool /tmp/autosci_routes.json | sed -n '1,260p'
```

Acceptance:

```text
count == 28
all major routes listed
no route status "full"
```

Run file checks:

```bash
test -f tools/run_scientific_node_smoke.py
test -f tools/run_scientific_lifecycle_smoke.py
test -f evaluators/scientific/lifecycle_runtime_gate.py
test -f evaluators/scientific/autosci_skill_run_gate.py
test -f plugins/autosci/bin/autosci_skill_shim.py
test -f plugins/autosci/bin/autosci_bridge.py
```

Run help/import checks:

```bash
python3 tools/run_scientific_node_smoke.py --help
python3 tools/run_scientific_lifecycle_smoke.py --help
python3 evaluators/scientific/lifecycle_runtime_gate.py --help || true
python3 plugins/autosci/bin/autosci_skill_shim.py --help
python3 plugins/autosci/bin/autosci_bridge.py --help
```

### Phase B — Fix capability registry drift

Add all manifest-declared research capabilities to `harness/config/capability-capsules.registry.yaml`.

Verification script:

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
print("manifest_caps:", len(manifest_caps))
print("registry_caps:", len(registry_caps))
print("missing_from_registry:", missing)

for cap in sorted(manifest_caps):
    path = Path("capability-capsules") / f"{cap}.yaml"
    if not path.exists():
        print("missing capsule file:", path)

raise SystemExit(1 if missing else 0)
PY
```

Add `harness/tests/config/test_autosci_research_capsule_registry.py` that fails if plugin manifest capability lacks registry entry, registry entry path does not exist, route capability lacks registry entry, or a capability file exists but is not registered.

### Phase C — Prove node-level runtime path

Run paper ingest node:

```bash
cd "$SOLAR_REPO/harness"
export HARNESS_DIR="$PWD"

python3 tools/run_scientific_node_smoke.py   --harness-dir "$PWD"   --operator-id autosci-paper-ingest-worker   --node-id paper_ingest   --logical-operator ScientificPaperIngestor   --action ingest_paper   --expected-schema research_paper.v1   --paper plugins/autosci/tests/fixtures/sample_paper.md   --task-id task-autosci-node-paper-ingest   --sprint-id sprint-autosci-node-smoke   --output-dir artifacts/scientific/node-smoke/paper_ingest   --out artifacts/scientific/node-smoke/paper_ingest/summary.json
```

Acceptance:

```text
summary.status == passed
operator_runtime_submit == ok
operatord_result_written == ok
bridge_result_completed == ok
evidence_schema_research_paper.v1 == ok
evidence_gate_passed == ok
artifact path exists
operator_result_path exists
bridge_result_path exists
```

Then run additional nodes in dependency order.

### Phase D — Prove `$research --scheduler-run`

Run:

```bash
cd "$SOLAR_REPO/harness"
export HARNESS_DIR="$PWD"

python3 plugins/autosci/bin/autosci_skill_shim.py text   '$research scheduler lifecycle --scheduler-run --scheduler-include-blocked-external --run-id scheduler-branch-check'
```

Acceptance:

```text
status != failed
execution_status == gated or partial
scheduler_lifecycle_status == blocked or passed
scheduler_lifecycle_summary_path is non-empty
scheduler_lifecycle_node_count > 0
scheduler_workflow_config_alignment_status == aligned
```

Inspect summary:

```bash
SUMMARY="<path-from-output>"
python3 -m json.tool "$SUMMARY" | sed -n '1,360p'
python3 evaluators/scientific/lifecycle_runtime_gate.py "$SUMMARY"
```

Blocked-state acceptance:

```text
lifecycle_runtime_gate returns inconclusive, not failed
blocked nodes have reason
blocked nodes have required_evidence
blocked nodes have unblock_condition
all unblocked required nodes have node_results/gate_results/artifacts
```

### Phase E — Build generic workflow runner

Create `harness/tools/run_scientific_workflow.py`.

Required command:

```bash
python3 tools/run_scientific_workflow.py   --workflow workflows/scientific_research_lifecycle_full_v1.json   --job-id <job_id>   --mode fixture   --include-blocked-external   --out artifacts/scientific/<job_id>/scientific_lifecycle_runtime.json
```

Implementation requirements:

1. Load workflow JSON.
2. Use workflow nodes and dependencies as source of truth.
3. Resolve logical operator → physical operator.
4. Resolve required capability → registered capsule.
5. Build one envelope per node.
6. Submit via `operator_runtime.submit`.
7. Run deterministic evidence gate.
8. Record node_result and gate_result.
9. Write strict `scientific_lifecycle.v1`.
10. Run `lifecycle_runtime_gate.py`.
11. Support `--resume-summary`.
12. Support blocked nodes without failing whole lifecycle.

Keep `run_scientific_lifecycle_smoke.py` as a compatibility wrapper until the generic runner is stable.

### Phase F — Human gate block/resume test

Create `harness/tests/scientific/test_autosci_research_human_gate_resume.py`.

First run:

```bash
python3 tools/run_scientific_workflow.py   --workflow workflows/scientific_research_lifecycle_full_v1.json   --job-id human-gate-smoke   --include-human-gates   --out artifacts/scientific/human-gate-smoke/blocked.json
```

Resume:

```bash
python3 tools/run_scientific_workflow.py   --resume-summary artifacts/scientific/human-gate-smoke/blocked.json   --idea-approval-ref approval-idea-001   --results-approval-ref approval-results-001   --out artifacts/scientific/human-gate-smoke/resumed.json
```

Acceptance: completed nodes are not rerun, approval node artifacts exist, resume continues after gate, strict runtime gate passes or blocks only on next external node.

### Phase G — Experiment exactly-once collection

Create `harness/tests/scientific/test_autosci_experiment_collection_ledger.py`.

Acceptance: first collect creates `collection-ledger.json`, ledger entry contains `collection_identity` and file digests, second collect with same files detects duplicate, second collect does not append duplicate wiki mutation, and runtime evidence IDs are preserved.

### Phase H — Publication external unblock/resume

Create `harness/tests/scientific/test_autosci_publication_resume.py`.

First run with blocked external nodes. Then resume with:

```text
--review-llm-evidence <artifact_review.v1>
--compile-target <paper-dir>
--compile-approval-ref <approval-ref>
--compile-allowlist-evidence <allowlist.json>
--compile-before-artifact <before.json>
--compile-execute-approved
```

Acceptance: `report_plan` only unblocks with completed Review LLM evidence; `publication_produce` only unblocks with compile target + approval or runtime evidence; `publication_bundle.v1` exists; compiled PDF exists or is clearly inconclusive with diagnostics; runtime gate passes only when artifacts exist and hash matches.

### Phase I — OmegaWiki parity slice

Add missing native-compatible commands to OpenSolar `tools/research_wiki.py`: `init`, `add-citation`, `batch-edges`, `dedup-edges`, `dedup-citations`, `compile-context`, `rebuild-context-brief`, `rebuild-open-questions`, `transition`, `maturity`, checkpoint commands, and tests for typed edge validation, citation dedup, legal/illegal transitions, checkpoint resume, maturity, context brief, and open questions.

### Phase J — Native `/ideate` parity slice

Implement maturity-aware behavior, failed idea banlist, active idea dedup, generation paths A-E, dual-model independent brainstorming, deep validation through `/novelty` and `/review`, accepted/eliminated idea writeback, pilot handoff, and growth report.

### Phase K — Native `/exp-run` parity slice

Implement experiment code directory generation, dataset/config inspection, manual approval artifact, local screen launch or approved local equivalent, remote.py status/gpu/sync/setup/launch/check/tail-log/pull-results support, multi-seed result aggregation, mean ± std metrics, wiki experiment status mutation, DEPLOY_REPORT, and RUN_REPORT.

### Phase L — Native `/paper-draft` and `/paper-compile` parity slice

Implement `paper/main.tex`, `paper/math_commands.tex`, `paper/references.bib`, sections, figures, tables, citation map, BibTeX verification, figure/table generation, section-level evidence mapping, de-AI polish, Review LLM section/full paper review, latexmk/pdflatex compile, page count, anonymity, font, and checklist.

### Phase M — Final parity inventory

Create `harness/tools/autosci_parity_inventory.py` reporting route count, full/partial/gated counts, capsule registry gaps, manifest/registry drift, workflow node count, workflow runtime proof status, native command parity by command, live provider proof, remote experiment proof, and publication proof. The script must not allow manual edits to claim `full`.

---

## 7. M4 acceptance definition

Declare **M4 scheduler-native runtime prototype** complete only when:

```text
[ ] cap.research-* and cap.research-artifact-review are registered.
[ ] run_scientific_node_smoke.py passes paper_ingest, claim_extract, experiment_run, report_draft.
[ ] lifecycle_runtime_gate.py rejects weak/incomplete summaries.
[ ] $research --scheduler-run produces scientific_lifecycle.v1.
[ ] scientific_lifecycle.v1 has node_results and gate_results for every unblocked node.
[ ] all node artifacts exist and hashes match.
[ ] blocked nodes are explicit, inspectable, and resumable.
[ ] top-level skill status does not overclaim partial/gated runs.
[ ] human-gate resume test passes.
[ ] publication external unblock/resume test passes.
[ ] parity inventory reports correct non-full status unless all full acceptance tests pass.
```

---

## 8. Anti-overclaiming rules

The agent must not claim full parity from route config alone, docs/integrations logs, feature operator bindings smoke config, plain `$research` without `--scheduler-run`, workflow JSON contract alone, fixture-only runs, local surrogate Review LLM, pre-created runtime evidence without verifying artifact hashes, or lifecycle summary without strict runtime gate proof.

---

## 9. Copy-paste coding-agent prompt

```text
You are continuing the AutoSci-on-Solar migration on branch ChatGPT-check.

Your goal is not to add new surface routes. The 28 routes already exist. Your goal is to convert the current broad compatibility bridge into a strict scheduler-native Solar research runtime.

Read first:
- harness/plugins/autosci/config/feature_parity_routes.v1.json
- harness/plugins/autosci/bin/autosci_skill_shim.py
- harness/tools/run_scientific_node_smoke.py
- harness/tools/run_scientific_lifecycle_smoke.py
- harness/evaluators/scientific/lifecycle_runtime_gate.py
- harness/evaluators/scientific/lifecycle_gate.py
- harness/plugins/autosci/bin/autosci_bridge.py
- harness/config/capability-capsules.registry.yaml
- harness/plugins/autosci/manifest.yaml
- harness/config/logical-operators.json
- harness/config/physical-operators.json
- harness/workflows/scientific_research_lifecycle_full_v1.json
- native AutoSci reference if available: .claude/skills/research/SKILL.md, exp-run/SKILL.md, ideate/SKILL.md, paper-draft/SKILL.md, tools/research_wiki.py

Immediate tasks:
1. Fix capability registry drift. The plugin manifest declares research capabilities, but the main capability registry must also register them and point to existing capsule files.
2. Run and repair tools/run_scientific_node_smoke.py for paper_ingest, claim_extract, experiment_run, and report_draft.
3. Run and repair tools/run_scientific_lifecycle_smoke.py through $research --scheduler-run.
4. Ensure lifecycle_runtime_gate.py rejects weak summaries and accepts only complete runtime summaries.
5. Convert hardcoded lifecycle smoke toward a generic workflow runner that reads workflows/scientific_research_lifecycle_full_v1.json.
6. Add tests for human-gate resume, experiment exactly-once collection, and publication external unblock/resume.
7. Do not claim full parity unless route, capsule, workflow, runtime evidence, gates, and acceptance tests all pass.

Required proof artifacts:
- command transcript
- generated scientific_lifecycle.v1
- lifecycle_runtime_gate output
- node result summaries
- gate results
- artifact hashes
- parity inventory JSON

Do not use logs as acceptance evidence unless they are paired with executable code paths and generated artifacts.
```
