# AutoSci Native Lifecycle Continuation Log

Logged: 2026-06-25 EDT
Branch: `feature/autosci-solar-native`

## Operating Rule

Before each fix, this log records the intended files in scope. After each fix,
it records verification results. A step is not marked complete unless the named
check ran and the remaining limitation is explicit.

## Step 0 - Baseline And Scope Capture

| Field | Value |
|---|---|
| Planned files | `docs/integrations/autosci/continuation-baseline-2026-06-25.md`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Record baseline and create the dedicated continuation/Phase 15 logs before runtime changes. |
| Out of scope | No Python, JSON config, workflow, gate, or shim behavior changes in this step. |
| Risk | Documentation-only; should not affect runtime behavior. |

### Step 0 Result

| Check | Status | Evidence |
|---|---|---|
| Baseline commands recorded | ok | See `continuation-baseline-2026-06-25.md`. |
| Runtime code changed | ok | None. |
| Full parity claimed | ok | No. |

## Next Planned Step - Lifecycle Gate Split

| Field | Value |
|---|---|
| Planned files | `harness/evaluators/scientific/lifecycle_contract_gate.py`, `harness/evaluators/scientific/lifecycle_runtime_gate.py`, `harness/evaluators/scientific/lifecycle_gate.py`, `tests/harness/evaluators/scientific/test_lifecycle_runtime_gate.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md` |
| Intent | Split graph contract validation from runtime lifecycle acceptance and add negative tests for empty/missing result maps. |
| Out of scope | No route/config/operator mutation until the runtime gate contract is in place. |
| Risk | Gate behavior may expose existing false-positive lifecycle tests; retain compatibility wrapper where needed. |

### Step 1 Result

| Check | Status | Evidence |
|---|---|---|
| Contract/runtime gate split | ok | Added `lifecycle_contract_gate.py`; `lifecycle_gate.py` dispatches runtime summaries to `lifecycle_runtime_gate.py`. |
| Runtime empty-map rejection | ok | `lifecycle_runtime_gate.py tests/harness/evaluators/scientific/fixtures/pass/lifecycle.json` exits nonzero and rejects missing `job_id`, `node_results`, and `gate_results`. |
| Existing contract workflow validation | ok | `lifecycle_contract_gate.py harness/workflows/scientific_research_lifecycle_full_v1.json` passes. |
| Targeted lifecycle tests | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific/test_lifecycle_gate.py tests/harness/evaluators/scientific/test_lifecycle_runtime_gate.py -q`: 15 passed. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 63 passed. |

## Next Planned Step - Registry Binding Audit

| Field | Value |
|---|---|
| Planned files | `harness/tools/audit_scientific_runtime_bindings.py`, `tests/harness/evaluators/scientific/test_scientific_runtime_binding_audit.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md` |
| Intent | Add deterministic audit coverage for workflow node -> logical operator -> binding -> physical operator -> host -> command/action -> schema -> gate. |
| Out of scope | Do not mutate operator registries until the audit reports the actual failure set. |
| Risk | Audit may expose stale `backend_action_pending`, placeholder hosts, or missing manifest capabilities. |

### Step 2 Result

| Check | Status | Evidence |
|---|---|---|
| Audit tool added | ok | Added `harness/tools/audit_scientific_runtime_bindings.py`. |
| Synthetic complete-chain test | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific/test_scientific_runtime_binding_audit.py -q`: 2 passed. |
| Current repository audit | error | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 40 issues, exit 1. |

### Step 2 Current Audit Findings

| Finding | Count/Scope | Next action |
|---|---|---|
| Missing logical bindings | `ScientificLiteratureDiscoverer`, `ScientificPaperAnalyzer`, `ScientificGraphUpdater`, `ScientificMethodExtractor`, `ScientificCodeEvidenceMapper`, `ScientificWorkflowEvolver` | Add bindings to existing AutoSci worker actors. |
| Missing manifest capabilities | `cap.research-literature-discover`, `cap.research-memory-update`, `cap.research-graph-update`, `cap.research-paper-analyze`, `cap.research-idea-evaluate` | Reconcile plugin manifest to all 18 target capabilities. |
| Stale binding condition | `backend_action_pending` on memory and idea bindings | Replace with truthful availability conditions for already registered actions. |
| Missing registered host | AutoSci physical workers point to `solar@example-host` | Add a local command host and point AutoSci workers at it. |

## Next Planned Step - Repair Registry Chain

| Field | Value |
|---|---|
| Planned files | `harness/config/actor-hosts.json`, `harness/config/logical-operators.json`, `harness/config/physical-operators.json`, `harness/plugins/autosci/manifest.yaml`, `docs/integrations/autosci/native-lifecycle-continuation-log.md` |
| Intent | Repair only the failures exposed by the audit: local host registration, missing scientific logical bindings, stale pending conditions, manifest capability omissions, and placeholder AutoSci worker metadata. |
| Out of scope | Do not change bridge action behavior or `$research` execution semantics in this step. |
| Risk | Physical operator metadata changes can affect dispatch selection; keep actor IDs and command strings stable. |

### Step 3 Result

| Check | Status | Evidence |
|---|---|---|
| Local AutoSci host registered | ok | Added `local-autosci-backend` as `local_command_worker` in `actor-hosts.json`. |
| Scientific logical bindings repaired | ok | Added missing bindings and removed `backend_action_pending` from current AutoSci-backed scientific bindings. |
| Manifest reconciled | ok | Added the five missing target capabilities to `plugins/autosci/manifest.yaml`. |
| AutoSci physical metadata repaired | ok | AutoSci workers now point to `local-autosci-backend` and use bounded-local metadata. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 27 nodes, 0 issues. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 65 passed. |
| AutoSci manifest/parity targeted tests | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_manifest_capabilities.py tests/plugins/autosci/test_phase19_parity_bridge.py tests/plugins/autosci/test_phase19_operator_smoke.py -q`: 11 passed. |

## Next Planned Step - Scheduler-Dispatched Bounded Node Proof

| Field | Value |
|---|---|
| Planned files | `harness/tools/run_scientific_node_smoke.py`, `tests/harness/evaluators/scientific/test_scientific_node_runtime_smoke.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Prove one safe `ScientificPaperIngestor` node dispatches through `operator_runtime.submit`, local host/operator metadata, bounded bridge action, evidence artifact, and deterministic gate. |
| Out of scope | Do not claim full `$research` lifecycle execution yet; this is one vertical node slice. |
| Risk | `operator_runtime.submit` may write runtime inbox/lease state under harness runtime directories; generated runtime artifacts must remain under explicit artifact paths. |

### Step 4 Result

| Check | Status | Evidence |
|---|---|---|
| Scheduler node smoke tool added | ok | Added `harness/tools/run_scientific_node_smoke.py`; it submits a `ScientificPaperIngestor` task through `operator_runtime.submit` and waits for `operatord` result artifacts. |
| Isolated dispatch smoke test | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific/test_scientific_node_runtime_smoke.py -q`: 1 passed. |
| End-to-end node chain verified | ok | Test asserts operator result, materialized envelope, bridge result, `research_paper.v1` evidence, output log action, and `paper_gate.py` pass. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 66 passed. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 27 nodes, 0 issues. |
| Full `$research` claimed | ok | No. This proves only one scheduler-dispatched bounded node. |

## Next Planned Step - Scheduler Runtime Lifecycle Summary

| Field | Value |
|---|---|
| Planned files | `harness/config/physical-operators.json`, `harness/tools/run_scientific_node_smoke.py`, `harness/tools/run_scientific_lifecycle_smoke.py`, `tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Compose multiple scheduler-dispatched bounded nodes into a runtime lifecycle summary accepted by `lifecycle_runtime_gate.py`, starting from paper ingest and paper analyze. |
| Out of scope | Do not mark `$research` full parity until the complete graph, waits, gates, and resume semantics are proven. |
| Risk | Multi-node smoke may reveal missing dependency handoff paths or stale fixture assumptions between node artifacts. |

### Step 5 Result

| Check | Status | Evidence |
|---|---|---|
| Node smoke generalized | ok | `run_scientific_node_smoke.py` now keeps paper ingest as default but supports explicit action/operator/node/logical operator/evidence name parameters. |
| Two-node lifecycle smoke added | ok | Added `harness/tools/run_scientific_lifecycle_smoke.py` for scheduler-dispatched `paper_ingest` and `paper_analyze`. |
| Runtime lifecycle summary accepted | ok | `test_scientific_lifecycle_runtime_smoke.py` verifies `lifecycle_runtime_gate.py` accepts the generated `scientific_lifecycle.v1` summary. |
| Targeted runtime tests | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific/test_scientific_node_runtime_smoke.py tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py tests/harness/evaluators/scientific/test_lifecycle_runtime_gate.py -q`: 11 passed. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 67 passed. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 27 nodes, 0 issues. |
| Full `$research` claimed | ok | No. This proves a two-node scheduler runtime summary, not the complete lifecycle graph. |

## Next Planned Step - Generic Scheduler Node Runtime For Core Actions

| Field | Value |
|---|---|
| Planned files | `harness/tools/run_scientific_node_smoke.py`, `harness/tools/run_scientific_lifecycle_smoke.py`, `tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Replace paper-only gate wiring with action/schema/gate metadata so the lifecycle smoke can dispatch more bounded core nodes without bespoke code per node. |
| Out of scope | Do not introduce deterministic substitutes for missing model/evidence intelligence; each node must still surface failed/incomplete states through its real gate. |
| Risk | Some existing bridge actions may still depend on earlier fixture paths; generic dispatch may expose missing source-evidence handoff. |

### Step 6 Result

| Check | Status | Evidence |
|---|---|---|
| Schema-driven node gates | ok | `run_scientific_node_smoke.py` now maps action -> expected schema and schema -> deterministic gate CLI. |
| Upstream evidence handoff inputs | ok | `run_scientific_lifecycle_smoke.py` passes prior node artifact paths into memory, graph, method, code, and idea nodes. |
| Core scheduler chain expanded | ok | Lifecycle smoke now dispatches 9 nodes: paper ingest/analyze, memory, graph, claims, methods, code evidence, idea generation, idea evaluation. |
| Runtime lifecycle summary accepted | ok | `test_scientific_lifecycle_runtime_smoke.py` verifies `lifecycle_runtime_gate.py` accepts all 9 node results and artifact hashes. |
| Targeted runtime tests | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific/test_scientific_node_runtime_smoke.py tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py tests/harness/evaluators/scientific/test_lifecycle_runtime_gate.py -q`: 11 passed. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 67 passed. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 27 nodes, 0 issues. |
| Full `$research` claimed | ok | No. Experiment, verification, report/publication, wait/resume, and final memory/workflow evolution are still not complete. |

## Next Planned Step - Experiment Verification And Report Runtime Nodes

| Field | Value |
|---|---|
| Planned files | `harness/tools/run_scientific_lifecycle_smoke.py`, `tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Extend scheduler lifecycle smoke through experiment design/run/monitor, claim verification, report draft, publication bundle, final memory update, and workflow evolution where current gates allow bounded execution. |
| Out of scope | Do not bypass human approval semantics for real experiment deployment; bounded fixture/local runs must remain labeled as smoke/runtime proof. |
| Risk | Publication and workflow evolution gates may expose missing sidecar output configuration or incomplete source evidence handoff. |

### Step 7 Result

| Check | Status | Evidence |
|---|---|---|
| Experiment and verification nodes added | ok | Lifecycle smoke now dispatches experiment design/run/monitor and claim verification through operator runtime. |
| Report/final memory/workflow nodes added | ok | Lifecycle smoke now dispatches report draft, final memory update, and workflow evolution. |
| Workflow evolution gate fixed by input contract | ok | Synthetic failed-run input now uses `failed` status plus ambiguous manual evidence, so `workflow_evolution_gate.py` passes without weakening the gate. |
| Scheduler runtime coverage | warn | 16 nodes pass; missing nodes are `literature_discover`, `report_plan`, and `publication_produce`. |
| Targeted runtime tests | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific/test_scientific_node_runtime_smoke.py tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py tests/harness/evaluators/scientific/test_lifecycle_runtime_gate.py -q`: 11 passed. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 67 passed. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 27 nodes, 0 issues. |
| Full `$research` claimed | ok | No. Literature discovery, report-plan action binding, publication bundle action binding, durable waits, and resume execution remain open. |

## Next Planned Step - Report And Publication Action Binding Accuracy

| Field | Value |
|---|---|
| Planned files | `harness/tools/audit_scientific_runtime_bindings.py`, `tests/harness/evaluators/scientific/test_scientific_runtime_binding_audit.py`, `harness/config/logical-operators.json`, `harness/config/physical-operators.json`, `harness/tools/run_scientific_node_smoke.py`, `harness/tools/run_scientific_lifecycle_smoke.py`, `tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Make the audit catch logical node/action/schema mismatches and bind report planning to `plan_report` and publication production to `compile_paper` instead of treating `write_report` as all publication stages. |
| Out of scope | Do not claim external LaTeX/PDF parity unless compile evidence and PDFs are actually produced and gated. |
| Risk | Tightening the audit may reveal additional route truthfulness issues that require registry repair. |

### Step 8 Result

| Check | Status | Evidence |
|---|---|---|
| Action mismatch audit added | ok | `audit_scientific_runtime_bindings.py` now checks node id -> expected bridge action. |
| Audit negative test added | ok | `test_scientific_runtime_binding_audit.py` rejects an otherwise registered but wrong bridge action. |
| Report plan binding repaired | ok | `ScientificReportPlanner` now binds to `autosci-report-plan-worker` running `plan_report`. |
| Publication producer binding repaired | ok | `ScientificPublicationProducer` now binds to `autosci-publication-compile-worker` running `compile_paper`. |
| Node smoke metadata updated | ok | `run_scientific_node_smoke.py` knows `plan_report` and `compile_paper` schemas/actions. |
| Targeted tests | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific/test_scientific_runtime_binding_audit.py tests/harness/evaluators/scientific/test_scientific_node_runtime_smoke.py tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py -q`: 5 passed. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 68 passed. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 27 nodes, 0 issues. |
| Full `$research` claimed | ok | No. `report_plan` still needs independent review evidence; `publication_produce` still needs real compile/PDF or approved runtime evidence to pass. |

## Next Planned Step - Review Evidence For Report Planning

| Field | Value |
|---|---|
| Planned files | `harness/tools/run_scientific_node_smoke.py`, `harness/tools/run_scientific_lifecycle_smoke.py`, `tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Add scheduler-dispatched artifact review evidence so `plan_report` can run with an explicit Review LLM-equivalent block instead of remaining inconclusive. |
| Out of scope | Do not fabricate a model review; if the local bounded `review_artifact` action marks review unavailable/incomplete, preserve that state. |
| Risk | The report-plan gate may remain inconclusive until review evidence satisfies the bridge's `artifact_review.v1` contract. |

### Step 9 Scope Correction

| Field | Value |
|---|---|
| Actual additional file | `harness/config/physical-operators.json` |
| Reason | A scheduler-dispatched review block required registering `autosci-artifact-review-worker`; no existing physical operator ran `review_artifact`. |

### Step 9 Result

| Check | Status | Evidence |
|---|---|---|
| Review worker registered | ok | Added `autosci-artifact-review-worker` running bounded `review_artifact`. |
| Node smoke review metadata added | ok | `run_scientific_node_smoke.py` maps `review_artifact` to `artifact_review.v1` and `artifact_review_gate.py`. |
| Lifecycle auxiliary review block added | ok | `run_scientific_lifecycle_smoke.py` reviews the generated report draft as `artifact_review`. |
| Review truthfulness preserved | warn | The passing review block is `local_surrogate`; it does not satisfy `plan_report`'s mandatory completed Review LLM condition. |
| Targeted tests | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific/test_scientific_runtime_binding_audit.py tests/harness/evaluators/scientific/test_scientific_node_runtime_smoke.py tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py -q`: 5 passed. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 68 passed. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 27 nodes, 0 issues. |
| Full `$research` claimed | ok | No. Completed Review LLM evidence, report planning, and publication compile/PDF remain open. |

## Next Planned Step - Literature Discovery Runtime Node

| Field | Value |
|---|---|
| Planned files | `harness/tools/run_scientific_lifecycle_smoke.py`, `tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Add the remaining `literature_discover` workflow node to the scheduler-dispatched lifecycle smoke using the existing bounded discovery action and gate. |
| Out of scope | Do not claim online discovery/full source evidence parity; network fetch remains bounded/off unless explicitly configured. |
| Risk | The discovery gate may expose that current smoke discovery is fixture/local-only. |

### Step 10 Result

| Check | Status | Evidence |
|---|---|---|
| Literature discovery node added | ok | `run_scientific_lifecycle_smoke.py` now dispatches `literature_discover` through `autosci-literature-discover-worker`. |
| Discovery truthfulness preserved | warn | Smoke inputs set `allow_network_fetch=false` and `fixture_fallback=true`; this is scheduler proof, not online evidence parity. |
| Lifecycle smoke accepted | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py -q`: 1 passed. |
| Targeted tests | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific/test_scientific_runtime_binding_audit.py tests/harness/evaluators/scientific/test_scientific_node_runtime_smoke.py tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py -q`: 5 passed. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 68 passed. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 27 nodes, 0 issues. |
| Full `$research` claimed | ok | No. Full workflow still needs `report_plan` with completed Review LLM evidence and `publication_produce` with compile/PDF evidence. |

## Next Planned Step - Durable Blocked States For External Evidence

| Field | Value |
|---|---|
| Planned files | `harness/evaluators/scientific/lifecycle_runtime_gate.py`, `tests/harness/evaluators/scientific/test_lifecycle_runtime_gate.py`, `harness/tools/run_scientific_lifecycle_smoke.py`, `tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Represent `report_plan` and `publication_produce` as explicit blocked/waiting nodes when Review LLM or compile/PDF evidence is unavailable, instead of omitting them or marking them passed. |
| Out of scope | Do not weaken passed lifecycle acceptance; passed nodes must still have valid artifacts, hashes, schemas, and gates. |
| Risk | Runtime gate status semantics must distinguish partial/blocked lifecycle proof from completed lifecycle proof. |

### Step 11 Result

| Check | Status | Evidence |
|---|---|---|
| Runtime gate blocked-node support | ok | `lifecycle_runtime_gate.py` accepts structured `blocked_nodes` only as `inconclusive`, not `passed`. |
| Blocked-node negative tests | ok | `test_lifecycle_runtime_gate.py` rejects blocked nodes without reason, required evidence, and unblock condition. |
| Blocked lifecycle smoke mode | ok | `run_scientific_lifecycle_smoke.py --include-blocked-external` records `report_plan` and `publication_produce` as blocked external-evidence waits. |
| Passed lifecycle strictness preserved | ok | Default lifecycle smoke still requires passed nodes with artifacts, hashes, schemas, and gate results. |
| Targeted tests | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific/test_lifecycle_runtime_gate.py tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py -q`: 13 passed. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 71 passed. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 27 nodes, 0 issues. |
| Full `$research` claimed | ok | No. The blocked nodes now surface the remaining external evidence requirements truthfully. |

## Remaining Full-Parity Blockers After Step 11

| Blocker | Status | Required evidence/path |
|---|---|---|
| `report_plan` | blocked | Completed `artifact_review.v1` with `review_mode=review_llm` or `review_llm.status=completed`. |
| `publication_produce` | blocked | `publication_bundle.v1` from `compile_paper` with existing source/PDF files or approved compile runtime evidence. |
| Online literature/source parity | warn | Current lifecycle smoke uses bounded local discovery with network disabled. |
| Resume/human wait orchestration | pending | Blocked nodes are represented in runtime evidence; scheduler resume CLI/dispatch for unblocking is still not complete. |

## Next Planned Step - Resume Blocked External Evidence Nodes

| Field | Value |
|---|---|
| Planned files | `harness/tools/run_scientific_lifecycle_smoke.py`, `tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Add a resume mode that reads a blocked lifecycle summary and dispatches only `report_plan` and `publication_produce` after Review LLM and compile/PDF evidence are supplied. |
| Out of scope | Do not synthesize Review LLM or PDF evidence inside production runtime; tests may create explicit local fixtures as supplied evidence. |
| Risk | Resume must preserve original job id and artifact hashes so lifecycle runtime gate can verify the resumed summary. |

### Step 12 Result

| Check | Status | Evidence |
|---|---|---|
| Blocked lifecycle resume CLI | ok | `run_scientific_lifecycle_smoke.py --resume-summary ...` now resumes only blocked `report_plan` and `publication_produce`. |
| Review/PDF truthfulness preserved | ok | Production resume requires caller-supplied `--review-llm-evidence` and `--compile-target`; it does not synthesize Review LLM or PDF evidence. |
| Runtime gate closure | ok | Resumed nodes dispatch through `operator_runtime.submit`, write artifacts with hashes, and convert blocked lifecycle summaries to passed only after gates pass. |
| Syntax check | ok | `env PYTHONPATH=harness .venv/bin/python -m py_compile harness/tools/run_scientific_lifecycle_smoke.py tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py` passed. |
| Resume lifecycle smoke test | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py -q`: 3 passed. |
| Targeted runtime tests | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific/test_lifecycle_runtime_gate.py tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py -q`: 14 passed. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 72 passed. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 27 nodes, 2 workflows, 0 issues. |
| Full `$research` claimed | ok | No. Online/multi-source evidence fetching still needs a non-fixture parity path and proof. |

## Next Planned Step - Online Source Evidence Strict Mode

| Field | Value |
|---|---|
| Planned files | `harness/tools/run_scientific_lifecycle_smoke.py`, `harness/evaluators/scientific/literature_discovery_gate.py`, `tests/harness/evaluators/scientific/test_literature_discovery_gate.py`, `tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Add an explicit non-fixture/online discovery mode and gate checks so fixture discovery cannot satisfy full-parity source evidence claims. |
| Out of scope | Do not require network during default smoke; network-restricted runs must surface inconclusive/blocked state instead of fabricating candidates. |
| Risk | Strict online mode may fail in offline CI, so default smoke must remain bounded while full-parity proof requires explicit opt-in. |

### Step 13 Result

| Check | Status | Evidence |
|---|---|---|
| Strict online discovery gate | ok | `literature_discovery_gate.py` now rejects fixture/local candidates when `inputs.require_online_source_evidence=true`. |
| Source fan-in control | ok | Gate enforces `inputs.min_online_source_channels` for online source channel fan-in. |
| Lifecycle strict-mode inputs | ok | `run_scientific_lifecycle_smoke.py` now exposes `--allow-network-fetch`, `--disable-fixture-fallback`, `--require-online-source-evidence`, discovery query/mode/limit, and minimum online source channels. |
| Default smoke preserved | ok | Default lifecycle smoke still uses offline fixture mode unless strict online evidence is explicitly requested. |
| Offline strict-mode truthfulness | ok | Strict online lifecycle test fails without network/online candidates instead of accepting fixture discovery. |
| Syntax check | ok | `env PYTHONPATH=harness .venv/bin/python -m py_compile harness/tools/run_scientific_lifecycle_smoke.py harness/evaluators/scientific/literature_discovery_gate.py tests/harness/evaluators/scientific/test_literature_discovery_gate.py tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py` passed. |
| Related tests | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific/test_literature_discovery_gate.py tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py -q`: 7 passed. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 76 passed. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 27 nodes, 2 workflows, 0 issues. |
| Full `$research` claimed | ok | No. The strict path exists, but a real network-enabled source evidence run still needs to be executed/proven in an environment with online access. |

## Next Planned Step - Approved Runtime Source Evidence For Discovery

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `harness/evaluators/scientific/autosci_runtime_evidence_gate.py`, `harness/tools/run_scientific_lifecycle_smoke.py`, `tests/harness/evaluators/scientific/test_autosci_runtime_evidence_gate.py`, `tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Allow `discover_literature` to consume approval-gated runtime source-fetch evidence so strict online discovery can be proven from supplied external evidence in offline environments. |
| Out of scope | Do not execute network fetches or invent source candidates inside the bridge. |
| Risk | Runtime evidence must be validated as source-fetch evidence before it can satisfy strict discovery gates. |

### Step 14 Scope Correction

| Field | Value |
|---|---|
| Additional file | `harness/schemas/evidence/autosci_runtime_evidence.v1.schema.json` |
| Reason | Adding `discover_literature` as a validated source-fetch runtime action requires the Evidence ABI schema enum to accept that action. |

### Step 14 Result

| Check | Status | Evidence |
|---|---|---|
| Discovery runtime evidence bridge | ok | `discover_literature` now consumes approval-gated `runtime_evidence` and emits `discover_literature_runtime_verified` only when the contract and runtime semantic checks pass. |
| Runtime evidence validation | ok | `autosci_runtime_evidence_gate.py` and `autosci_runtime_evidence.v1.schema.json` now recognize `discover_literature` as a source-fetch runtime action. |
| Lifecycle strict online unblocked by supplied evidence | ok | Strict lifecycle smoke can pass with supplied approved source runtime evidence and no fixture fallback. |
| Network truthfulness preserved | ok | The bridge does not execute network fetches or invent candidates; incomplete runtime contracts remain inconclusive. |
| Schema check | ok | `python3 -m json.tool harness/schemas/evidence/autosci_runtime_evidence.v1.schema.json` passed. |
| Related tests | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific/test_autosci_runtime_evidence_gate.py tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py -q`: 9 passed. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 77 passed. |
| AutoSci shim source runtime tests | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py::test_autosci_skill_shim_init_uses_verified_runtime_source_manifest tests/plugins/autosci/test_autosci_skill_shim.py::test_autosci_skill_shim_daily_arxiv_uses_verified_runtime_digest -q`: 2 passed. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 27 nodes, 2 workflows, 0 issues. |
| Full `$research` claimed | ok | No. The runtime evidence path is now proven, but a full end-to-end parity run still needs combined source runtime, Review LLM, compile/PDF evidence, and no remaining lifecycle warnings. |

## Next Planned Step - Combined Full External Evidence Lifecycle

| Field | Value |
|---|---|
| Planned files | `harness/tools/run_scientific_lifecycle_smoke.py`, `tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Add a single lifecycle run mode that dispatches `report_plan` and `publication_produce` when source runtime, Review LLM, and compile/PDF evidence are supplied. |
| Out of scope | Do not treat missing Review LLM or compile/PDF evidence as passed; missing evidence should remain blocked or failed depending on requested mode. |
| Risk | Full run status must remain strict: required external nodes need artifacts, hashes, schemas, and gates like every other scheduler node. |

### Step 15 Result

| Check | Status | Evidence |
|---|---|---|
| Single-run external dispatch | ok | `run_scientific_lifecycle_smoke.py --dispatch-external-evidence` dispatches `report_plan` and `publication_produce` in the same lifecycle run when required evidence is supplied. |
| Missing evidence strictness | ok | Requested external dispatch records missing Review LLM/compile evidence as error/blocked instead of passing. |
| Combined full evidence proof | ok | Lifecycle smoke test passes with strict source runtime evidence, completed Review LLM evidence, compile/PDF target, and no blocked nodes. |
| Syntax check | ok | `env PYTHONPATH=harness .venv/bin/python -m py_compile harness/tools/run_scientific_lifecycle_smoke.py tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py` passed. |
| Lifecycle smoke tests | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py -q`: 5 passed. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 77 passed. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 27 nodes, 2 workflows, 0 issues. |
| Full `$research` claimed | warn | Bounded lifecycle proof is now single-run complete when evidence is supplied, but route truthfulness/coverage metadata still needs review before claiming full AutoSci parity. |

## Step 16 Route Truthfulness Verification

| Check | Status | Evidence |
|---|---|---|
| Planned files | ok | No code/config change planned; this was an audit-only verification of route coverage metadata. |
| Full overclaim scan | ok | `feature_parity_routes.v1.json` has 0 routes with `coverage_status: full`. |
| Route status distribution | ok | Current route config distribution: 17 partial, 11 gated, 0 full. |
| Feature parity gate | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific/test_autosci_feature_parity_gate.py -q`: 4 passed. |
| Inventory proof | ok | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step16.json`: 28 native skills, 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Full `$research` claimed | ok | No. Route metadata is now truthful; remaining parity work is capability completion, not route overclaim repair. |

## Next Planned Step - Research Route Consumes Scheduler Lifecycle Evidence

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `harness/plugins/autosci/bin/autosci_skill_shim.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Let `/research` accept a passed `scientific_lifecycle.v1` scheduler runtime summary as route evidence, so the skill route can cite scheduler-native lifecycle proof. |
| Out of scope | Do not mark incomplete or blocked lifecycle summaries as completed research lifecycle evidence. |
| Risk | The bridge must require passed lifecycle gate status, no blocked nodes, and the key full-lifecycle node results before treating the summary as complete. |

### Step 17 Result

| Check | Status | Evidence |
|---|---|---|
| `/research` scheduler summary input | ok | `autosci_skill_shim.py` now accepts `--lifecycle-summary` and forwards it into bridge inputs/native options. |
| Scheduler lifecycle completion guard | ok | `autosci_bridge.py` accepts only `scientific_lifecycle.v1` summaries with `lifecycle_status=passed`, `lifecycle_gate_result.ok=true`, no blocked nodes, and passed key full-lifecycle node results. |
| Stage-plan integration | ok | A valid scheduler lifecycle summary marks all `/research` lifecycle stages completed without requiring duplicate route-plan inference. |
| Targeted tests | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py::test_autosci_skill_shim_research_lifecycle_completes_from_scheduler_summary tests/plugins/autosci/test_autosci_skill_shim.py::test_autosci_skill_shim_research_lifecycle_completes_from_verified_stage_evidence -q`: 2 passed. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 77 passed. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 27 nodes, 2 workflows, 0 issues. |
| Feature parity inventory | ok | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step17.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Full `$research` claimed | warn | `/research` can now consume scheduler-native completed lifecycle evidence, but route status remains partial until real operational/provider evidence policy is satisfied. |

## Next Planned Step - Route Primary Tool Action Truthfulness

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `harness/evaluators/scientific/autosci_feature_parity_gate.py`, `tests/harness/evaluators/scientific/test_autosci_feature_parity_gate.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Repair route metadata where `primary_tools` still names old generic bridge actions instead of the configured `solar_backend_action`, and add a gate guard against future drift. |
| Out of scope | Do not upgrade route `coverage_status`; this step only fixes metadata truthfulness. |
| Risk | Some primary tools are non-bridge helper tools; the guard must only enforce action matches when a primary tool explicitly invokes `autosci_bridge.py run --action ...`. |

### Step 18 Result

| Check | Status | Evidence |
|---|---|---|
| Route primary tool metadata repaired | ok | Updated stale bridge action references for exp-eval, exp-pilot-eval, exp-pilot-run, paper-draft, paper-plan, rebuttal, refine, and survey where needed. |
| Drift guard added | ok | `autosci_feature_parity_gate.py` now rejects `primary_tools` bridge action drift when `autosci_bridge.py run --action ...` omits the configured `solar_backend_action`. |
| Negative test added | ok | `test_autosci_feature_parity_gate.py` rejects paper-plan primary tool drift from `plan_report` to `write_report`. |
| JSON validation | ok | `python3 -m json.tool harness/plugins/autosci/config/feature_parity_routes.v1.json` passed. |
| Drift scan | ok | Local scan found no route where bridge primary tool action omits the configured backend action. |
| Feature parity gate tests | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific/test_autosci_feature_parity_gate.py -q`: 5 passed. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 78 passed. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 27 nodes, 2 workflows, 0 issues. |
| Feature parity inventory | ok | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step18.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |

## Step 19 Survey CLI Format Recheck

| Field | Value |
|---|---|
| Planned files | `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Recheck the audit blocker that reported `$survey --format latex` as rejected before making further parser changes. |
| Out of scope | Do not change survey report semantics or upgrade route coverage; this is a parser/route truthfulness verification only. |

### Step 19 Result

| Check | Status | Evidence |
|---|---|---|
| `$survey --format latex` direct text command | ok | `env HARNESS_DIR=/tmp/autosci-step19-survey .venv/bin/python harness/plugins/autosci/bin/autosci_skill_shim.py text '$survey --format latex --topic skillgen --run-id step19-survey-format-latex'`: `ok=true`, `action_count=1`, `skill=survey`, `execution_status=partial`. |
| Native option propagation | ok | Existing shim test confirms `inputs.native_options.format == latex` and bridge evidence `inputs.format == latex`. |
| Targeted test | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py::test_autosci_skill_shim_accepts_survey_format_latex -q`: 1 passed. |
| Code changes | ok | None needed; current parser already accepts the original `--format latex` shape. |
| Remaining parity status | warn | Survey CLI rejection is closed, but `write_survey` remains `partial` until citation-backed survey completeness is proven with real source evidence. |

## Next Planned Step - Wiki-Backed Experiment Status Read

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Let `$exp-status --pipeline` / `monitor_experiment` answer from resolved wiki experiment state when no fresh runtime/result evidence is supplied. |
| Out of scope | Do not execute experiment commands, collect remote results, or mutate wiki state in status-only mode. |
| Risk | A read-only wiki state must not be overstated as runtime collection; limitations and evidence ids need to make the source explicit. |

### Step 20 Result

| Check | Status | Evidence |
|---|---|---|
| Wiki experiment state fields | ok | `autosci_bridge.py` now preserves experiment `pipeline`, `aliases`, `outcome`, `evidence_ids`, and run-log metadata from wiki frontmatter. |
| Pipeline alias resolution | ok | Wiki resolver aliases now include `pipeline` and explicit alias lists, so `$exp-status --pipeline <slug>` can resolve matching experiments. |
| Read-only status output | ok | `monitor_experiment` emits `experiment_status.v1` from resolved wiki experiment state only when no `--collect` or runtime evidence path is active. |
| Targeted tests | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest ...test_autosci_skill_shim_exp_status_pipeline_runs_monitor_action ...test_autosci_skill_shim_exp_status_pipeline_reads_wiki_experiment_state -q`: 2 passed. |

## Step 21 Result - Novelty Review LLM Absence Semantics

| Check | Status | Evidence |
|---|---|---|
| Implicit Review LLM provider disabled for novelty | ok | `autosci_skill_shim.py` now sets `review_llm_requested` for idea/novelty evaluation only when `--review` or explicit Review LLM evidence/command/provider/endpoint inputs are supplied. |
| Missing Review LLM state | ok | Local novelty paths now report Review LLM evidence as `unavailable`, not provider `failed`, when no Review LLM source was supplied. |
| Write-back strictness | ok | Novelty write-back still requires completed external novelty provenance and completed Review LLM evidence before mutating wiki novelty score. |
| Targeted tests | ok | Novelty Review LLM absence/write-back group: 4 previously failing semantic cases now pass as part of the 5-test novelty group. |

## Step 22 Result - Novelty Online Archive Test Assertion

| Check | Status | Evidence |
|---|---|---|
| Test assertion repaired | ok | `test_autosci_skill_shim_novelty_defaults_to_online_fetch_when_available` now checks provider `raw_payload_ref`, `raw_payload_archive_status`, and archive file existence instead of checking a local directory string for `file://`. |
| Novelty targeted group | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest ...novelty... -q`: 5 passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 80 passed when rerun outside the sandbox because one provider test binds `127.0.0.1`. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 78 passed. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 27 nodes, 2 workflows, 0 issues. |
| Feature parity inventory | ok | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step22.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Full parity claim | warn | Still not honest to claim full parity; remaining routes depend on real provider/network/approval-gated execution evidence. |

## Next Planned Step - Ideate Model Brainstorm Evidence Path

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Let `/ideate` consume explicit model evidence or a model-command bridge to produce source-grounded candidate ideas instead of only deterministic local candidates. |
| Out of scope | Do not silently call a provider, invent model output, or mark dual-model parity complete without supplied model evidence. |
| Risk | Invalid model output must not be treated as a passed brainstorm; generated ideas still need origin evidence ids and novelty/review gates. |

### Step 23 Result

| Check | Status | Evidence |
|---|---|---|
| Model response shape | ok | `autosci_model_response.v1` normalization now accepts `outputs.ideas` with required evidence ids, while preserving answer/summary support for ask/check. |
| `/ideate` model-command path | ok | `generate_ideas` uses explicit model evidence/command output when it returns valid ideas; invalid/failed model output is marked inconclusive and does not count as model brainstorm parity. |
| Route metadata | ok | `feature_parity_routes.v1.json` now states explicit model-command/model-evidence brainstorming is wired, without upgrading `coverage_status`. |
| Targeted test | ok | `test_autosci_skill_shim_ideate_uses_model_command_for_brainstorm`: passed. |
| Related tests | ok | Ideate/novelty targeted group: 4 passed; idea gate + feature parity gate: 12 passed. |
| Inventory | ok | `/tmp/autosci-parity-step23.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |

## Next Planned Step - Novelty Write Test Network Isolation

| Field | Value |
|---|---|
| Planned files | `tests/plugins/autosci/test_autosci_skill_shim.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Make the `without external evidence` novelty write-back test deterministic by disabling network fetch for that test. |
| Out of scope | Do not change default online novelty behavior. |
| Risk | The test should still prove write-back blocks when external novelty evidence is unavailable. |

### Step 24 Result

| Check | Status | Evidence |
|---|---|---|
| Test isolation | ok | The missing-external-evidence novelty write-back test now sets `AUTOSCI_DISABLE_NETWORK_FETCH=1`, so it validates the unavailable evidence branch even when live network/provider access exists. |
| Targeted test | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest ...test_autosci_skill_shim_novelty_write_skips_without_external_evidence -q`: 1 passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 81 passed outside sandbox because one provider test binds `127.0.0.1`. |
| Scientific evaluator suite | ok | Latest post-Step 23 run: 78 passed. |
| Full parity claim | warn | Still not honest: explicit model-command ideation improves parity, but audited provider-backed dual-model ideation and provider/runtime execution remain partial/gated. |

## Next Planned Step - Wiki Experiment Status State Mapping

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Map common AutoSci wiki experiment statuses such as `collected`, `collect-ready`, and `ready` into the constrained `experiment_status.v1` state enum. |
| Out of scope | Do not execute collect/deploy or mutate experiment state. |
| Risk | `collect-ready` must not be overstated as completed results; only `collected` should map to completed. |

### Step 25 Result

| Check | Status | Evidence |
|---|---|---|
| Status mapping | ok | `collected` now maps to `completed`; `collect-ready` and `ready` map to `running`; planned/failed/abandoned variants map into valid ABI states. |
| No execution/mutation | ok | Mapping is used only by wiki-backed `monitor_experiment` read mode. |
| Targeted tests | ok | `test_autosci_skill_shim_exp_status_pipeline_reads_wiki_experiment_state`, `test_autosci_skill_shim_exp_status_normalizes_native_wiki_states`, and experiment status gate tests: 6 passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 84 passed outside sandbox because one provider test binds `127.0.0.1`. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 78 passed. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 27 nodes, 2 workflows, 0 issues. |
| Feature parity inventory | ok | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step25.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Full parity claim | warn | Still not honest: this closes a status-read gap, but provider/approval-gated execution evidence is still required for full native parity. |

## Next Planned Step - Research Scheduler Lifecycle Entry

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Add an explicit `$research` scheduler lifecycle run path that dispatches the existing scientific lifecycle smoke through `operator_runtime` and feeds its `scientific_lifecycle.v1` summary back into the research bridge. |
| Out of scope | Do not make fixture-mode scheduler execution implicit, do not claim full parity, and do not bypass approval/provider requirements for external source, experiment, Review LLM, or compile evidence. |
| Risk | The new path must remain opt-in and must preserve failure/blocking state rather than converting a failed scheduler run into a successful pipeline projection. |

### Step 26 Result

| Check | Status | Evidence |
|---|---|---|
| Explicit scheduler entry | ok | `$research --scheduler-run` now invokes `tools/run_scientific_lifecycle_smoke.py` with the active `HARNESS_DIR`, prepares isolated harness resource links when needed, and attaches the generated `scientific_lifecycle.v1` summary to the research bridge as `lifecycle_summary`. |
| Blocked external nodes preserved | ok | `$research --scheduler-run --scheduler-include-blocked-external` records `report_plan` and `publication_produce` as blocked scheduler nodes instead of marking the pipeline complete. |
| Route truthfulness | ok | `feature_parity_routes.v1.json` documents the explicit scheduler-run path while keeping `/research` at `coverage_status: partial`. |
| Targeted tests | ok | `$research` supplied-summary, scheduler-run blocked-summary, and lifecycle blocked-node smoke tests: 3 passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 85 passed outside sandbox because one provider test binds `127.0.0.1`. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 78 passed. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 27 nodes, 2 workflows, 0 issues. |
| Feature parity inventory | ok | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step26.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Full parity claim | warn | Still not honest: this closes an explicit scheduler-entry gap, but full native parity still requires non-fixture provider/source evidence, durable human gates, and approved long-running experiment/publication stage runners. |

## Next Planned Step - Scheduler Durable Human Gates

| Field | Value |
|---|---|
| Planned files | `harness/tools/run_scientific_lifecycle_smoke.py`, `harness/plugins/autosci/bin/autosci_skill_shim.py`, `harness/plugins/autosci/bin/autosci_bridge.py`, `tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Represent AutoSci idea/results human approval pauses as scheduler-visible blocked nodes for explicit lifecycle runs. |
| Out of scope | Do not auto-approve human gates, do not change default lifecycle smoke behavior, and do not mark `/research` full parity. |
| Risk | Missing approvals must stop downstream stages instead of allowing experiment or publication stages to run past an unapproved human gate. |

### Step 27 Result

| Check | Status | Evidence |
|---|---|---|
| Human gate nodes | ok | `run_scientific_lifecycle_smoke.py` now models `idea_acceptance_gate` and `results_acceptance_gate` as scheduler-visible lifecycle nodes. |
| Durable approval evidence | ok | Supplying `--idea-approval-ref` or `--results-approval-ref` writes completed `workflow_evolution.v1` gate evidence with approval refs, artifact hashes, and gate results. |
| Missing approval behavior | ok | With human gates enabled, the lifecycle stops at the missing gate and records a blocked node with required evidence/unblock condition; downstream experiment/publication stages do not run past the gate. |
| `$research` shim passthrough | ok | `$research --scheduler-run --scheduler-include-human-gates` passes human gate options to the scheduler lifecycle runner and records the blocked/passed gate state in the skill payload. |
| Targeted tests | ok | Human gate lifecycle smoke and `$research` shim human-gate regression: 2 passed; broader research scheduler group: 3 passed. |
| Lifecycle smoke suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py -q`: 6 passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 86 passed outside sandbox because one provider test binds `127.0.0.1`. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 79 passed. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 27 nodes, 2 workflows, 0 issues. |
| Feature parity inventory | ok | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step27.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Full parity claim | warn | Still not honest: durable gate state is now represented, but non-fixture source/provider evidence and approved long-running experiment/publication execution are still required. |

## Next Planned Step - Human Gate Resume

| Field | Value |
|---|---|
| Planned files | `harness/tools/run_scientific_lifecycle_smoke.py`, `tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Let scheduler lifecycle resume from blocked idea/results human gates using durable approval refs, without rerunning already passed nodes. |
| Out of scope | Do not add external provider execution or publication compile execution in this step. |
| Risk | Resume must not skip the second human gate or rerun completed upstream nodes. |

### Step 28 Result

| Check | Status | Evidence |
|---|---|---|
| Idea gate resume | ok | `run_scientific_lifecycle_smoke.py --resume-summary ... --idea-approval-ref ...` now records approval evidence, removes the blocked idea gate, and resumes at experiment design without rerunning upstream nodes. |
| Results gate resume | ok | A second resume with `--results-approval-ref ...` records results approval evidence and continues through report draft/artifact review/memory final/workflow evolve before blocking on external report plan/compile evidence. |
| No upstream rerun | ok | Resume regression asserts the original `literature_discover` artifact path is unchanged after both human-gate resumes. |
| Targeted test | ok | `test_scientific_lifecycle_smoke_resumes_human_gate_pauses`: passed. |
| Lifecycle smoke suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py -q`: 7 passed. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 80 passed. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 27 nodes, 2 workflows, 0 issues. |
| Feature parity inventory | ok | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step28.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Full parity claim | warn | Still not honest: human gate resume is now covered, but non-fixture source/provider, real experiment deploy/collect, and full publication execution remain partial/gated. |

## Next Planned Step - Research Scheduler Strict Source Evidence Passthrough

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_skill_shim.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Pass `$research --scheduler-run --online` approval/runtime source evidence from the shim into scheduler strict online source flags. |
| Out of scope | Do not execute live network by default, and do not reuse source runtime evidence as experiment or compile evidence. |
| Risk | Missing or invalid source runtime evidence must fail/blocked strict online mode rather than falling back to fixtures. |

### Step 29 Result

| Check | Status | Evidence |
|---|---|---|
| Strict source passthrough | ok | `$research --scheduler-run --online` now maps shim `--approval-ref`, `--allowlist-evidence`, `--runtime-evidence`, `--before-artifact`, and `--after-artifact` into scheduler `--source-*` evidence flags. |
| No fixture fallback | ok | The regression verifies `literature_discover` emits `discover_literature_runtime_verified` with supplied `search_s2` runtime candidates and no fixture candidate id. |
| Route truthfulness | ok | `/research` route limitations now mention strict scheduler source evidence passthrough without changing `coverage_status`. |
| Targeted test | ok | `test_autosci_skill_shim_research_scheduler_online_uses_source_runtime_evidence`: passed. |
| Research scheduler group | ok | `$research` blocked-summary, human-gate, and strict-source scheduler regressions: 3 passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 87 passed outside sandbox because one provider test binds `127.0.0.1`. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 80 passed. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 27 nodes, 2 workflows, 0 issues. |
| Feature parity inventory | ok | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step29.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Full parity claim | warn | Still not honest: source runtime passthrough is wired, but real provider execution plus experiment/publication stage runners remain gated/partial. |

## Next Planned Step - Scheduler Experiment Runtime Evidence Passthrough

| Field | Value |
|---|---|
| Planned files | `harness/tools/run_scientific_lifecycle_smoke.py`, `harness/plugins/autosci/bin/autosci_skill_shim.py`, `tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Let scheduler lifecycle experiment run/monitor consume explicit approved experiment runtime evidence instead of fixture-only experiment output. |
| Out of scope | Do not execute arbitrary experiment commands by default, and do not claim remote/long-running parity without approved executor evidence. |
| Risk | Source runtime evidence and experiment runtime evidence must remain separate so source-fetch approval cannot satisfy experiment execution. |

### Step 30 Result

| Check | Status | Evidence |
|---|---|---|
| Scheduler experiment runtime contract | ok | `run_scientific_lifecycle_smoke.py` now accepts `--experiment-approval-ref`, `--experiment-runtime-evidence`, `--experiment-allowlist-evidence`, `--experiment-before-artifact`, and `--experiment-after-artifact`. |
| Experiment run/monitor passthrough | ok | When experiment runtime evidence is supplied, scheduler `experiment_run` and `experiment_monitor` use `execution_mode: human_approved` plus experiment-specific approval/runtime artifacts instead of fixture experiment output. |
| `$research` shim passthrough | ok | `$research --scheduler-run` forwards `--experiment-*` arguments to the scheduler lifecycle runner without reusing source `--runtime-evidence` paths. |
| Route truthfulness | ok | `/research` limitations document experiment runtime passthrough while keeping `coverage_status: partial`. |
| Targeted tests | ok | `test_scientific_lifecycle_smoke_uses_experiment_runtime_evidence` and `test_autosci_skill_shim_research_scheduler_uses_experiment_runtime_evidence`: 2 passed. |
| Syntax/config checks | ok | `py_compile` for modified Python files and `json.tool` for `feature_parity_routes.v1.json`: passed. |
| Lifecycle smoke suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py -q`: 8 passed. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 81 passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 88 passed outside sandbox because the provider test binds `127.0.0.1`; the sandboxed run had the same single localhost-bind permission failure. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 27 nodes, 2 workflows, 0 issues. |
| Feature parity inventory | ok | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step30.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Full parity claim | warn | Still not honest: scheduler experiment runtime evidence can now be supplied and verified, but live provider execution, long-running deploy/status/collect runners, and publication execution remain partial/gated. |

## Next Planned Step - Scheduler Approved Experiment Executor

| Field | Value |
|---|---|
| Planned files | `harness/tools/run_scientific_lifecycle_smoke.py`, `harness/plugins/autosci/bin/autosci_skill_shim.py`, `harness/plugins/autosci/bin/autosci_bridge.py`, `tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Let explicit scheduler experiment runs execute an allowlisted approved command and feed generated runtime/result evidence into downstream monitor/claim/report stages. |
| Out of scope | Do not execute by default, do not allow unapproved commands, and do not claim remote/session parity until remote runners are separately audited. |
| Risk | The execute-approved path must require approval, allowlist, before/after evidence, and an explicit scheduler/shim flag. |

### Step 31 Result

| Check | Status | Evidence |
|---|---|---|
| Approved scheduler executor flag | ok | `run_scientific_lifecycle_smoke.py` accepts `--experiment-execute-approved` and `--experiment-executor-timeout-seconds`; default scheduler runs still do not execute experiment commands. |
| Shim passthrough | ok | `$research --scheduler-run` forwards `--experiment-execute-approved` and timeout settings to the scheduler lifecycle runner. |
| Runtime ABI mapping | ok | `autosci_bridge.py` now lifts executor-generated `metrics`, `outcome`, and `logs` into `autosci_runtime_evidence.v1` fields consumed by `_approval_semantic_runtime`. |
| Downstream monitor collection | ok | When the executor generates result evidence, scheduler `experiment_monitor` consumes the generated `experiment_result.v1` and reports completed state. |
| Route truthfulness | ok | `/research` limitations document the approved local executor path while keeping `coverage_status: partial`. |
| Targeted tests | ok | `test_scientific_lifecycle_smoke_executes_approved_experiment_command` and `test_autosci_skill_shim_research_scheduler_executes_approved_experiment_command`: 2 passed after the runtime ABI fix. |
| Syntax/config checks | ok | `py_compile` for modified Python files and `json.tool` for `feature_parity_routes.v1.json`: passed. |
| Lifecycle smoke suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py -q`: 9 passed. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 82 passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 89 passed outside sandbox; sandboxed run still cannot bind the local provider test to `127.0.0.1`. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 27 nodes, 2 workflows, 0 issues. |
| Feature parity inventory | ok | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step31.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Full parity claim | warn | Still not honest: approved local experiment execution is now scheduler-visible, but remote/session runners, live provider evidence, and publication execution remain partial/gated. |

## Next Planned Step - Scheduler Approved Publication Compile

| Field | Value |
|---|---|
| Planned files | `harness/tools/run_scientific_lifecycle_smoke.py`, `harness/plugins/autosci/bin/autosci_skill_shim.py`, `tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Let scheduler `publication_produce` consume compile-specific approval/runtime evidence or execute an approved allowlisted TeX command, producing verified PDF/runtime evidence. |
| Out of scope | Do not execute compile by default, do not reuse source/experiment approval evidence, and do not claim submission/anonymity parity yet. |
| Risk | Compile approval evidence must stay separate from source and experiment evidence. |

### Step 32 Result

| Check | Status | Evidence |
|---|---|---|
| Compile-specific scheduler flags | ok | `run_scientific_lifecycle_smoke.py` accepts `--compile-approval-ref`, `--compile-runtime-evidence`, `--compile-allowlist-evidence`, `--compile-before-artifact`, `--compile-after-artifact`, `--compile-execute-approved`, and timeout flags for `publication_produce`. |
| Shim passthrough | ok | `$research --scheduler-run --scheduler-dispatch-external-evidence` forwards compile-specific evidence/execution flags without reusing source or experiment contracts. |
| Approved compile execution | ok | Scheduler publication compile can run an allowlisted fake `latexmk`, generate `main.pdf`, emit `compile_runtime_evidence_json`, and pass runtime semantic verification. |
| Route truthfulness | ok | `/research` limitations document compile-specific runtime evidence/execution while keeping `coverage_status: partial`. |
| Targeted tests | ok | `test_scientific_lifecycle_smoke_executes_approved_publication_compile` and `test_autosci_skill_shim_research_scheduler_executes_approved_publication_compile`: 2 passed. |
| Syntax/config checks | ok | `py_compile` for modified Python files and `json.tool` for `feature_parity_routes.v1.json`: passed. |
| Lifecycle smoke suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py -q`: 10 passed. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 83 passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 90 passed outside sandbox; sandboxed run still cannot bind the local provider test to `127.0.0.1`. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 27 nodes, 2 workflows, 0 issues. |
| Feature parity inventory | ok | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step32.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Full parity claim | warn | Still not honest: scheduler publication compile can now execute approved local TeX commands, but submission/anonymity checks, live provider evidence, and remote/session experiment runners remain partial/gated. |

## Next Planned Step - Publication Submission Checklist Truthfulness

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Add explicit paper compile checklist rows for anonymity, page limit, font size, and `[UNCONFIRMED]` markers without pretending unavailable checks passed. |
| Out of scope | Do not add PDF font parsing or venue-specific submission rules unless verified evidence is supplied. |
| Risk | Missing page/font evidence must be `warn`/unconfirmed, not a deterministic pass. |

### Step 33 Result

| Check | Status | Evidence |
|---|---|---|
| Submission checklist rows | ok | `paper_compile_checklist.json` now includes `submission_checks` for `unconfirmed_marker_scan`, `anonymity_check`, `page_limit_check`, and `font_size_check`. |
| Truthful unconfirmed handling | ok | Missing page/font evidence is reported as `warn`; `[UNCONFIRMED]` source markers and non-anonymous author blocks are surfaced as warnings rather than silently passing. |
| Diagnostics rendering | ok | `paper_compile_diagnostics.md` renders a dedicated `Submission Checks` section. |
| Targeted test | ok | `test_autosci_skill_shim_paper_compile_checklist_records_submission_checks`: passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 91 passed outside sandbox; sandboxed run cannot bind the local provider test to `127.0.0.1`. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 27 nodes, 2 workflows, 0 issues. |
| Feature parity inventory | ok | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step33.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Full parity claim | warn | Still not honest: checklist truthfulness improved, but live provider evidence and remote/session experiment lifecycle remain partial/gated. |

## Next Planned Step - Remote Helper Runtime Evidence Assimilation

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Let approved experiment commands that invoke `tools/remote.py launch` feed its generated `runtime_evidence_path` into the experiment approval contract. |
| Out of scope | Do not add real SSH/session execution; this only assimilates approved helper evidence produced by an allowlisted command. |
| Risk | Remote helper evidence must be an existing runtime evidence file; stdout alone must not be treated as completed experiment evidence. |

### Step 34 Result

| Check | Status | Evidence |
|---|---|---|
| Remote helper stdout parsing | ok | `autosci_bridge.py` now recognizes `autosci_remote_cli.v1` as a pointer/control payload, not as experiment result evidence. |
| Runtime evidence assimilation | ok | Existing `runtime_evidence_path` files emitted by `tools/remote.py launch` are appended to the approval contract and consumed by `_approval_semantic_runtime`. |
| False-success guard | ok | Remote helper stdout alone leaves the local bridge runtime result uncollected; completion still requires a readable runtime evidence file with collected results/metrics. |
| Targeted tests | ok | `test_autosci_skill_shim_exp_run_assimilates_remote_helper_runtime_evidence` and `test_autosci_skill_shim_exp_run_rejects_remote_helper_stdout_without_runtime_evidence`: 2 passed. |
| Syntax checks | ok | `env PYTHONPATH=harness .venv/bin/python -m py_compile harness/plugins/autosci/bin/autosci_bridge.py tests/plugins/autosci/test_autosci_skill_shim.py`: passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 93 passed outside sandbox; local provider test still requires binding `127.0.0.1`. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 27 nodes, 2 workflows, 0 issues. |
| Feature parity inventory | ok | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step34.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Full parity claim | warn | Still not honest: remote helper evidence is assimilated, but true SSH/session lifecycle, live provider runs, and remaining publication parity proof are still partial/gated. |

## Next Planned Step - Approved Remote Collect Execution

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Let `$exp-run --collect --execute-approved` run an approved `tools/remote.py pull-results` style command, convert collected result files into runtime evidence, and reuse semantic verification/wiki mutation. |
| Out of scope | Do not add SSH/session transport or exactly-once collection ledger in this step. |
| Risk | Collection must require approval, allowlist, before artifact, collected files, and semantic runtime verification; empty stdout or empty result directories must not pass. |

### Step 35 Result

| Check | Status | Evidence |
|---|---|---|
| Approved collect execution | ok | `monitor_experiment` can execute an approved/allowlisted collect command when `$exp-run --collect --execute-approved` is used. |
| Pull-results assimilation | ok | Collected files from `tools/remote.py pull-results` stdout are converted into `autosci_runtime_evidence.v1` and verified by `_approval_semantic_runtime`. |
| Empty collection guard | ok | Empty result directories generate runtime evidence but remain `inconclusive`; they do not pass semantic verification or mutate wiki as completed. |
| Route truthfulness | ok | `exp-run` and `exp-status` limitations now mention approved pull-results collection while keeping remote/session and exactly-once parity as partial. |
| Targeted tests | ok | `test_autosci_skill_shim_exp_collect_uses_verified_runtime_evidence`, `test_autosci_skill_shim_exp_collect_executes_approved_remote_pull_results`, and `test_autosci_skill_shim_exp_collect_rejects_empty_remote_pull_results`: 3 passed. |
| Syntax/config checks | ok | `py_compile` for modified Python files and `json.tool` for `feature_parity_routes.v1.json`: passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 95 passed outside sandbox; local provider test still requires binding `127.0.0.1`. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 27 nodes, 2 workflows, 0 issues. |
| Feature parity inventory | ok | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step35.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Full parity claim | warn | Still not honest: approved local pull-results collection is wired, but true SSH/session status, exactly-once collection ledger, live provider runs, and remaining publication proof are still partial/gated. |

## Next Planned Step - Exactly-Once Collection Ledger

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Add a durable local collection identity/hash ledger so repeated approved collect runs reuse existing accepted evidence instead of duplicating collection state. |
| Out of scope | Do not add distributed locks or remote scheduler resume semantics in this step. |
| Risk | Duplicate collection must still return completed status from existing evidence, but must not append duplicate wiki log/graph mutations. |

### Step 36 Result

| Check | Status | Evidence |
|---|---|---|
| Collection identity ledger | ok | Approved collect runs now write `wiki/collections/collection-ledger.json` with experiment id, collected file hashes, evidence ids, and collection identity. |
| Duplicate collection reuse | ok | Repeated approved collect runs with the same experiment/file hashes return completed status with `collection_duplicate=True` and skip duplicate wiki log/graph mutation. |
| Runtime evidence fields | ok | Collect runtime evidence now includes `collection_identity`, `collection_duplicate`, and `collection_ledger_path`. |
| Route truthfulness | ok | `exp-run`/`exp-status` limitations now distinguish local collection ledger support from distributed remote/session exactly-once parity. |
| Targeted tests | ok | Collect runtime, pull-results execution, empty collection rejection, and exactly-once ledger reuse tests: 4 passed. |
| Syntax/config checks | ok | `py_compile` for modified Python files and `json.tool` for `feature_parity_routes.v1.json`: passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 96 passed outside sandbox; local provider test still requires binding `127.0.0.1`. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 27 nodes, 2 workflows, 0 issues. |
| Feature parity inventory | ok | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step36.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Full parity claim | warn | Still not honest: local exactly-once collection is covered, but true remote/session status polling, live provider runs, scheduler resume, and remaining publication proof are still partial/gated. |

## Next Planned Step - Persistent Experiment Session Registry

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Persist approved launch/session records and let `$exp-status` read them when no completed wiki experiment state exists. |
| Out of scope | Do not implement SSH/screen polling or scheduler resume replay yet. |
| Risk | Registry status must not be overstated as collected results; waiting/running sessions should remain non-completed until runtime/collect evidence verifies results. |

### Step 37 Result

| Check | Status | Evidence |
|---|---|---|
| Session registry write | ok | Approved remote-launch style stdout now records `wiki/experiments/session-registry.json` with experiment id, run dir, runtime evidence path, remote CLI status, and session state. |
| Status read from registry | ok | `$exp-status <experiment>` can report `running` from the session registry when wiki state is only planned/running/non-completed. |
| Truthful non-collection status | ok | Registry status limitations state that no remote process was polled and no results were collected in the status call. |
| Route truthfulness | ok | `exp-status` limitations now distinguish local session registry status from missing live remote process polling. |
| Targeted test | ok | `test_autosci_skill_shim_exp_status_reads_persistent_session_registry`: passed. |
| Syntax/config checks | ok | `py_compile` for modified Python files and `json.tool` for `feature_parity_routes.v1.json`: passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 97 passed outside sandbox; local provider test still requires binding `127.0.0.1`. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 27 nodes, 2 workflows, 0 issues. |
| Feature parity inventory | ok | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step37.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Full parity claim | warn | Still not honest: persistent local session status is covered, but live remote polling, scheduler resume replay, live provider runs, and remaining publication proof are still partial/gated. |

## Next Planned Step - Scheduler Runtime Proof Guardrails

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_skill_shim.py`, `harness/evaluators/scientific/lifecycle_runtime_gate.py`, `tests/harness/evaluators/scientific/test_lifecycle_runtime_gate.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Prevent top-level `autosci_skill_run.status` from overstating partial/gated runs and make lifecycle runtime gate require operator/bridge result paths. |
| Out of scope | Do not replace the hardcoded scheduler smoke runner with a generic workflow runner in this step. |
| Risk | Existing consumers may expect completed top-level status for partial route evidence; tests must be updated to use `execution_status` as the parity signal. |

### Step 38 Planned Files Amendment

| Field | Value |
|---|---|
| Additional planned files | `harness/tools/run_scientific_lifecycle_smoke.py`, `tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py` |
| Intent | Materialize human approval gate operator/bridge sidecars so the stricter lifecycle runtime gate does not accept bare approval refs. |
| Out of scope | Do not loosen lifecycle runtime gate requirements for human gates. |

### Step 38 Result

| Check | Status | Evidence |
|---|---|---|
| Top-level run status truthfulness | ok | `autosci_skill_shim.py` now reports `status: inconclusive` for partial/gated non-failed runs while preserving `execution_status` for completed bridge actions. |
| Lifecycle runtime path guard | ok | `lifecycle_runtime_gate.py` now requires per-node `gate`, `operator_result_path`, and `bridge_result_path` files for unblocked nodes. |
| Human approval sidecars | ok | `run_scientific_lifecycle_smoke.py` now writes approval artifact, bridge result, and operator result sidecars for approved human gates; bare approval refs are no longer enough. |
| Scheduler blocked smoke | ok | `run_scientific_lifecycle_smoke.py --include-blocked-external` returned blocked exit `3` with `lifecycle_gate_result.status=inconclusive`, 18 node results, and blocked `report_plan`/`publication_produce`. |
| Targeted shim status tests | ok | Ingest gate, scheduler-run blocked summary, and setup gated tests: 3 passed. |
| Lifecycle gate tests | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific/test_lifecycle_runtime_gate.py -q`: 13 passed. |
| Lifecycle smoke tests | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py -q`: 10 passed. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 85 passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 97 passed with elevated local bind permission; sandbox-only run reached 96 passed and failed only on `127.0.0.1` bind permission. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 27 nodes, 2 workflows, 0 issues. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step38.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 38 touched files: passed. |
| Full parity claim | warn | Still not honest: scheduler proof guardrails improved, but generic workflow runner parity, live source/provider execution, remote polling/resume, and publication finalization remain partial/gated. |

## Next Planned Step - Generic Scheduler Workflow Resume Proof

| Field | Value |
|---|---|
| Planned files | `harness/tools/run_scientific_lifecycle_smoke.py`, `tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Replace the current smoke-only resume proof with stronger scheduler resume evidence that previously completed nodes are reused and blocked nodes resume without rerunning completed work. |
| Out of scope | Do not claim a generic production scheduler runner until non-smoke workflow config dispatch is implemented. |
| Risk | Resume proof must preserve artifact paths and sidecar paths from the source summary; regenerated evidence for completed nodes would hide a parity gap. |

### Step 39 Result

| Check | Status | Evidence |
|---|---|---|
| Resume audit summary | ok | Resumed lifecycle summaries now include `resume_audit` with source summary path, blocked nodes before resume, reused node fingerprints, newly dispatched nodes, and approved human gates. |
| Reuse preservation gate | ok | Resume adds `resume_reused_nodes_preserved`; it fails the lifecycle if an existing node artifact/operator/bridge fingerprint changes during resume. |
| Human-gate resume proof | ok | Tests assert first resume only dispatches experiment nodes after idea approval, and second resume only dispatches report/review/final/evolve nodes after results approval. |
| Targeted resume test | ok | `test_scientific_lifecycle_smoke_resumes_human_gate_pauses`: passed. |
| Lifecycle smoke tests | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py -q`: 10 passed. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 85 passed. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 27 nodes, 2 workflows, 0 issues. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step39.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 39 files: passed. |
| Full parity claim | warn | Still not honest: resume proof is stronger, but generic scheduler config dispatch, live source/provider execution, remote polling, and publication finalization remain partial/gated. |

## Next Planned Step - Scheduler Workflow Config Dispatch Boundary

| Field | Value |
|---|---|
| Planned files | `harness/tools/run_scientific_lifecycle_smoke.py`, `tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py`, `harness/workflows/scientific_research_lifecycle_full_v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Bind lifecycle smoke execution to the declared workflow config and fail if required configured nodes diverge from runner nodes. |
| Out of scope | Do not build a new production scheduler service in this step. |
| Risk | Config binding must expose drift as `error` rather than silently accepting hardcoded smoke parity. |

### Step 40 Result

| Check | Status | Evidence |
|---|---|---|
| Workflow config source | ok | Corrected the planned source to `harness/workflows/scientific_research_lifecycle_full_v1.json`; no nonexistent `harness/config/scientific_workflows.v1.json` file is used. |
| Alignment drift reporting | ok | Lifecycle summaries now include `workflow_config_alignment` with configured nodes, runner available nodes, required nodes, missing/extra nodes, order drift, and issue codes. |
| Strict drift failure | ok | `--require-workflow-config-alignment` fails when the smoke runner diverges from the declared workflow config. |
| Current detected drift | warn | Default smoke still records drift: `artifact_review` is runner-only, default runs omit configured `report_plan`/`publication_produce`, and blocked-external runs put configured publication nodes after runner-only review/final/evolve nodes. |
| Targeted tests | ok | Config-alignment affected tests and strict drift test: 3 passed. |
| Lifecycle smoke tests | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py -q`: 11 passed. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 86 passed. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 27 nodes, 2 workflows, 0 issues. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step40.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 40 files: passed. |
| Full parity claim | warn | Still not honest: config drift is now visible and enforceable, but the runner is not yet a generic production scheduler and publication/source/provider parity remains partial/gated. |

## Next Planned Step - Scheduler Alignment Surfacing In Shim Output

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_skill_shim.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Surface scheduler workflow-config drift in `$research --scheduler-run` route summaries so route consumers cannot miss that smoke parity diverges from declared workflow config. |
| Out of scope | Do not make strict config alignment default for all scheduler runs until the runner is realigned or a production config dispatcher exists. |
| Risk | The wrapper must keep partial/gated runs truthful without breaking evidence attachment for consumers that inspect the full lifecycle summary. |

### Step 41 Result

| Check | Status | Evidence |
|---|---|---|
| Shim summary surfacing | ok | `$research --scheduler-run` now emits `scheduler_workflow_config_alignment_status`, `scheduler_workflow_config_alignment_ok`, and issue codes in the top-level CLI summary. |
| Payload surfacing | ok | `outputs.skill_run.scheduler_lifecycle` now carries the workflow-config alignment object/status/issues, and drift adds an explicit payload limitation. |
| Strict shim option | ok | Added `--scheduler-require-workflow-config-alignment`; it forwards strict mode to the lifecycle runner without changing default behavior. |
| Targeted tests | ok | Blocked scheduler summary and strict config alignment failure tests: 2 passed. |
| Scheduler shim subset | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -k 'research_scheduler' -q`: 7 passed, 91 deselected. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 98 passed with elevated local bind permission. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 27 nodes, 2 workflows, 0 issues. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step41.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 41 files: passed. |
| Full parity claim | warn | Still not honest: shim consumers now see drift directly, but runner/config drift itself remains unresolved. |

## Next Planned Step - Workflow Config Review Block Alignment

| Field | Value |
|---|---|
| Planned files | `harness/workflows/scientific_research_lifecycle_full_v1.json`, `tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Align the declared full lifecycle config with the explicit Review LLM/artifact-review block already exercised by the runner, while preserving drift reporting for unresolved report-plan/publication ordering. |
| Out of scope | Do not reorder or claim production scheduler parity until report-plan/publication execution semantics are realigned. |
| Risk | Adding a workflow node must keep runtime binding audit green and must not hide remaining order drift. |

### Step 42 Planned Files Amendment

| Field | Value |
|---|---|
| Additional planned files | `harness/config/logical-operators.json`, `harness/plugins/autosci/manifest.yaml` |
| Intent | Declare the `ScientificArtifactReviewer` logical operator and `cap.research-artifact-review` capability required by the new workflow node. |
| Out of scope | Do not change the existing physical worker command or host policy. |

### Step 42 Planned Files Amendment 2

| Field | Value |
|---|---|
| Additional planned files | `harness/tools/audit_scientific_runtime_bindings.py` |
| Intent | Teach the static binding audit that `artifact_review` maps to the existing `review_artifact` bridge action. |
| Out of scope | Do not change audit rules for other workflow nodes. |

### Step 42 Planned Files Amendment 3

| Field | Value |
|---|---|
| Additional planned files | `harness/evaluators/scientific/lifecycle_gate.py` |
| Intent | Update the declared full lifecycle contract gate to include the new `ScientificArtifactReviewer` node. |
| Out of scope | Do not change runtime summary gate semantics. |

### Step 42 Result

| Check | Status | Evidence |
|---|---|---|
| Workflow review node | ok | `scientific_research_lifecycle_full_v1.json` now declares `artifact_review` after `report_draft` with `G_ARTIFACT_REVIEW` and `artifact_review.v1` evidence policy. |
| Publication dependency | ok | `publication_produce` now depends on `artifact_review` and reads both report and artifact-review evidence. |
| Artifact contract | ok | `artifact_contract.node_artifacts` now includes `artifact_review` and `artifact_review.v1`. |
| Logical binding | ok | `ScientificArtifactReviewer` and its `autosci-artifact-review-worker` binding are declared in `logical-operators.json`. |
| Plugin capability | ok | `cap.research-artifact-review` is declared in the AutoSci plugin manifest. |
| Static audit mappings | ok | `audit_scientific_runtime_bindings.py` maps `artifact_review` to `review_artifact` and `artifact_review.v1` to `artifact_review_gate.py`. |
| Contract tests | ok | Full lifecycle contract and config drift affected tests: 4 passed. |
| Lifecycle smoke tests | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py -q`: 11 passed. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 86 passed. |
| Scheduler shim subset | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -k 'research_scheduler' -q`: 7 passed, 91 deselected. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 28 nodes, 2 workflows, 0 issues. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step42.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 42 files: passed. |
| Full parity claim | warn | Still not honest: Review LLM/artifact-review is now declared, but the runner still executes report draft/review/final/evolve before configured report-plan/publication ordering. |

## Next Planned Step - Report Plan Publication Ordering Realignment

| Field | Value |
|---|---|
| Planned files | `harness/tools/run_scientific_lifecycle_smoke.py`, `tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Stop treating report draft/review/final/evolve as a completed scheduler tail when configured report-plan/publication evidence is missing; align blocked/executed tail ordering with the workflow config. |
| Out of scope | Do not invent Review LLM or LaTeX evidence; missing external evidence must remain blocked. |
| Risk | Existing tests that expected scheduler smoke `passed` without configured publication evidence must be updated to `blocked`/`inconclusive`. |

### Step 43 Result

| Check | Status | Evidence |
|---|---|---|
| Default scheduler tail truthfulness | ok | Lifecycle smoke now executes only through `claim_verify` by default, then records `report_plan` and `publication_produce` as blocked when Review LLM/compile evidence is missing. |
| Configured tail order | ok | `--dispatch-external-evidence` now uses configured tail order: `report_plan -> report_draft -> artifact_review -> publication_produce -> memory_update_final -> workflow_evolve`. |
| Resume truthfulness | ok | Resuming past results approval no longer dispatches report draft/review/final/evolve without report-plan/publication evidence. |
| Drift shape | ok | Missing publication evidence is now `configured_nodes_not_required_by_run`, not runner-only or order drift; strict mode still fails until full tail evidence is supplied. |
| Lifecycle smoke tests | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py -q`: 11 passed. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 86 passed. |
| Scheduler shim subset | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -k 'research_scheduler' -q`: 7 passed, 91 deselected. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 98 passed with elevated local bind permission. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 28 nodes, 2 workflows, 0 issues. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step43.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 43 files: passed. |
| Full parity claim | warn | Still not honest: ordering is fixed for the smoke runner, but full parity still needs real provider/source evidence, remote polling, and production scheduler dispatch. |

## Next Planned Step - Strict Full Tail Alignment Proof

| Field | Value |
|---|---|
| Planned files | `tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Add acceptance tests showing that when Review LLM and compile evidence are supplied, strict workflow-config alignment passes through the full configured scheduler tail. |
| Out of scope | Do not replace supplied fixture evidence with live provider evidence in this step. |
| Risk | Tests must verify strict alignment only when explicit evidence exists; they must not weaken blocked behavior for missing evidence. |

### Step 44 Result

| Check | Status | Evidence |
|---|---|---|
| Strict full-tail lifecycle proof | ok | Combined source runtime + Review LLM + compile target lifecycle smoke now runs with `--require-workflow-config-alignment` and asserts `workflow_config_alignment.status=aligned`. |
| Strict full-tail shim proof | ok | `$research --scheduler-run --scheduler-dispatch-external-evidence --scheduler-require-workflow-config-alignment` passes when Review LLM and compile evidence are supplied, and top-level shim summary reports alignment `ok`. |
| Targeted tests | ok | Full-tail lifecycle and shim publication compile strict tests: 2 passed. |
| Lifecycle smoke tests | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py -q`: 11 passed. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 86 passed. |
| Scheduler shim subset | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -k 'research_scheduler' -q`: 7 passed, 91 deselected. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 98 passed with elevated local bind permission. |
| Strict runtime binding audit | ok | `env PYTHONPATH=harness .venv/bin/python harness/tools/audit_scientific_runtime_bindings.py --strict --json`: 28 nodes, 2 workflows, 0 issues. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step44.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 44 files: passed. |
| Full parity claim | warn | Still not honest: strict alignment can pass with supplied evidence, but live provider/source evidence, remote/session polling, and production scheduler dispatch remain incomplete. |

## Next Planned Step - Route Truthfulness For Scheduler Tail

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Update route limitations so `$research --scheduler-run` documentation matches the new truthful behavior: default runs block at report-plan/publication tail unless Review LLM and compile evidence are supplied. |
| Out of scope | Do not mark the route full or change route inventory counts. |
| Risk | Route text must not imply live provider/full scheduler parity from supplied fixture evidence. |

### Step 45 Result

| Check | Status | Evidence |
|---|---|---|
| `$research` limitation truthfulness | ok | Route limitations now state that default `$research --scheduler-run` blocks the configured publication tail at `report_plan`/`publication_produce` unless explicit Review LLM and compile/PDF evidence are supplied with `--scheduler-dispatch-external-evidence`. |
| Strict alignment wording | ok | Route limitations now state that `--scheduler-require-workflow-config-alignment` passes only for the full supplied-evidence tail and otherwise surfaces drift/inconclusive status. |
| Primary tool reference | ok | Corrected `$research.primary_tools` from missing `tools/run_scientific_lifecycle_smoke.py` to existing `harness/tools/run_scientific_lifecycle_smoke.py`. |
| JSON parse | ok | `python3 -c 'import json, pathlib; ...'`: json ok. |
| Route/gate tests | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_phase19_parity_bridge.py tests/harness/evaluators/scientific/test_autosci_feature_parity_gate.py tests/harness/evaluators/scientific/test_autosci_operator_smoke_gate.py tests/plugins/autosci/test_root_tool_abi.py::test_feature_parity_routes_reference_existing_root_tools -q`: 12 passed. |
| Root-tool ABI tests | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_root_tool_abi.py -q`: 5 passed with elevated local bind permission for SMTP fixture. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step45.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 45 files: passed. |
| Full parity claim | warn | Still not honest: route text is truthful, but generic workflow dispatch, live provider/source runs, remote/session polling, and publication parity remain incomplete. |

## Next Planned Step - Acceptance And Resume Gap Selection

| Field | Value |
|---|---|
| Planned files | `harness/tools/run_scientific_lifecycle_smoke.py`, `tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py`, `harness/plugins/autosci/bin/autosci_skill_shim.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Inspect and close the next smallest acceptance/resume gap from the status report without upgrading route coverage or hiding remaining non-parity. |
| Out of scope | Do not replace the smoke runner with a generic production scheduler in this micro-step unless the file inspection shows the change is local and reversible. |
| Risk | Resume/acceptance fixes must not make projection-only `$research` appear scheduler-native. |

### Step 46 Scope Narrowing

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Require handoff `scientific_lifecycle.v1` summaries to pass `lifecycle_runtime_gate` and workflow-config alignment before the bridge treats them as completed scheduler lifecycle proof. |
| Out of scope | Do not alter scheduler-run execution or default `$research` routing in this step. |

### Step 46 Result

| Check | Status | Evidence |
|---|---|---|
| Handoff lifecycle gate reuse | ok | `autosci_bridge.py` now reuses `lifecycle_runtime_gate.evaluate()` for supplied `scientific_lifecycle.v1` summaries before treating them as completed scheduler proof. |
| Workflow alignment requirement | ok | Supplied lifecycle summaries must include `workflow_config_alignment.ok=true` and `status=aligned` before bridge projection marks `scheduler_lifecycle_completed=true`. |
| Weak summary rejection | ok | Added shim test proving a weak hand-written lifecycle summary is retained as input evidence but does not complete the research pipeline. |
| Strict summary acceptance | ok | Added shim test proving a lifecycle summary with node artifacts, sidecar paths, hashes, gate results, and aligned workflow config can complete the pipeline. |
| Compile check | ok | `env PYTHONPATH=harness .venv/bin/python -m py_compile harness/plugins/autosci/bin/autosci_bridge.py tests/plugins/autosci/test_autosci_skill_shim.py` |
| Targeted tests | ok | lifecycle-summary handoff tests: 2 passed. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 86 passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 99 passed with elevated local bind permission. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step46.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 46 files: passed before log write. |
| Full parity claim | warn | Still not honest: handoff acceptance is stricter, but generic workflow dispatch, live provider/source runs, remote/session polling, and live publication parity remain incomplete. |

## Next Planned Step - Remote Session Polling Proof

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Inspect and tighten `$exp-status` remote/session polling so an approved `tools/remote.py check` result can be used as durable status evidence without conflating it with local registry-only state. |
| Out of scope | Do not execute real SSH or remote commands without explicit approval; fixture/local evidence must remain marked partial. |

### Step 47 Result

| Check | Status | Evidence |
|---|---|---|
| Shim CLI | ok | Added narrow `--remote-check-command` and `--remote-run-dir` options for approved `$exp-status` polling. |
| Approved remote check executor | ok | `monitor_experiment` can now run an allowlisted approved status-check command, parse `autosci_remote_cli.v1 command=check`, and write durable `autosci_runtime_evidence.v1` monitor evidence. |
| Registry distinction | ok | Registry-only status still says no remote process was polled; approved remote check status uses a separate `remote_status_runtime_evidence_json` artifact. |
| Route truthfulness | ok | `/exp-status` limitation now says approved `tools/remote.py check` execution is wired, while live SSH/provider polling remains partial. |
| Compile/JSON checks | ok | py_compile for bridge/shim/test passed; route config JSON parsed. |
| Targeted tests | ok | New remote-check test passed; exp-run/status/collect subset passed: 14 passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 100 passed with elevated local bind permission. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step47.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 47 files passed before log write. |
| Full parity claim | warn | Still not honest: approved local remote-check execution is wired, but live SSH/provider polling and distributed remote collection remain partial. |

## Next Planned Step - Live Provider Evidence Boundary

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Inspect source/model provider paths and add the next missing durable evidence boundary without substituting deterministic heuristics for live provider behavior. |
| Out of scope | Do not call external providers or network sources without explicit approval. |

### Step 48 Scope Narrowing

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Persist model-command request JSON and request/response hashes for ask/check/ideate command-backed model evidence. |
| Out of scope | Do not add a live hosted model provider path or call external APIs. |

### Step 48 Result

| Check | Status | Evidence |
|---|---|---|
| Model request provenance | ok | `_model_output()` now persists `*_model_request.json` before invoking a model command. |
| Request/response hashes | ok | Model-command request and stdout response hashes are recorded in artifacts and normalized model output. |
| Route truthfulness | ok | `/ask`, `/check`, and `/ideate` limitations now describe persisted request/response provenance for model-command paths. |
| Targeted tests | ok | ask/check/ideate model-command provenance tests passed: 3 passed. |
| Compile/JSON checks | ok | py_compile for bridge/tests passed; route config JSON parsed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 100 passed with elevated local bind permission. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step48.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 48 files passed before log write. |
| Full parity claim | warn | Still not honest: command-backed model evidence is auditable, but live hosted provider execution and dual-model AutoSci parity remain pending. |

## Next Planned Step - Publication Provider Boundary

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `harness/plugins/autosci/backends/artifact_review.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Inspect paper-plan/publication Review LLM and compile handoff evidence for the next missing full-parity boundary. |
| Out of scope | Do not call external Review LLM providers or TeX executors without explicit approval. |

### Step 49 Scope Narrowing

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Add a `paper-plan` Review LLM boundary object so completion requires explicit Review LLM mode, availability, and evidence ids while preserving invocation/provenance details. |
| Out of scope | Do not alter provider invocation, call external APIs, or promote external fixture review evidence to full hosted-provider parity. |

### Step 49 Result

| Check | Status | Evidence |
|---|---|---|
| Publication Review LLM boundary | ok | `$paper-plan` now writes `autosci_publication_review_boundary.v1` into `paper_plan_json` and review-gates markdown. |
| Weak review rejection | ok | Completed plan status now requires artifact review schema/status, LLM review mode, `review_available=true`, and non-empty evidence ids; weak Review LLM-shaped JSON remains inconclusive. |
| Route truthfulness | ok | `/paper-plan` limitation now names explicit Review LLM boundary evidence instead of a loose boolean Review LLM pass. |
| Targeted tests | ok | `paper_plan_completes_with_citations_and_review_llm`, `paper_plan_rejects_weak_review_llm_boundary`, and `paper_plan_attaches_verified_compile_handoff`: 3 passed. |
| Publication subset | ok | paper-plan/paper-draft/paper-compile/scheduler publication subset: 13 passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 101 passed with elevated local bind permission. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step49.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 49 files passed before log write. |
| Full parity claim | warn | Still not honest: paper-plan review gating is stricter, but live idea graph planning, hosted provider runs, generic scheduler dispatch, and end-to-end compile/submission parity remain incomplete. |

## Next Planned Step - Scheduler Production Dispatch Boundary

| Field | Value |
|---|---|
| Planned files | `harness/tools/run_scientific_lifecycle_smoke.py`, `harness/workflows/scientific_research_lifecycle_full_v1.json`, `harness/plugins/autosci/bin/autosci_skill_shim.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Inspect whether `$research --scheduler-run` can move beyond the bounded smoke runner toward a production workflow dispatch boundary without claiming generic scheduler parity prematurely. |
| Out of scope | Do not replace scheduler behavior with deterministic shortcuts or mark route coverage full without replay/resume/runtime proof. |

### Step 50 Scope Narrowing

| Field | Value |
|---|---|
| Planned files | `harness/tools/run_scientific_lifecycle_smoke.py`, `harness/plugins/autosci/bin/autosci_skill_shim.py`, `tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Add a scheduler production-dispatch boundary and strict flag so smoke/fixture runner inputs cannot be mistaken for production scheduler parity. |
| Out of scope | Do not rename the bounded smoke runner to production, do not remove fixture defaults, and do not claim generic scheduler parity. |

### Step 50 Result

| Check | Status | Evidence |
|---|---|---|
| Dispatch boundary | ok | Lifecycle summaries now include `autosci_scheduler_dispatch_boundary.v1` with workflow config hash, profiled nodes, smoke nodes, fixture nodes, and blocking reasons. |
| Strict production flag | ok | `--require-production-dispatch` / `--scheduler-require-production-dispatch` fails while the bounded smoke runner or fixture/smoke markers remain. |
| Shim summary passthrough | ok | `$research` stdout and evidence payload expose dispatch boundary status, production-ready state, and blocking reasons. |
| Route truthfulness | ok | `/research` limitation now states that strict production dispatch fails for bounded smoke/fixture-backed lifecycle runs. |
| Targeted tests | ok | Runner and shim production-boundary tests: 2 passed. |
| Scheduler/scientific subset | ok | Lifecycle smoke + lifecycle runtime gate subset: 25 passed. |
| Research scheduler shim subset | ok | `$research` scheduler subset: 8 passed. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 87 passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 102 passed with elevated local bind permission. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step50.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 50 files passed before log write. |
| Full parity claim | warn | Still not honest: the boundary prevents overclaiming, but a real non-smoke workflow dispatcher is still pending. |

## Next Planned Step - Live Source Provider Completion Boundary

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `harness/plugins/autosci/bin/autosci_skill_shim.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Inspect source/provider evidence completion so online/source runs expose provider success/failure boundaries without synthetic fallback success. |
| Out of scope | Do not call network providers or replace source evidence with deterministic summaries. |

### Step 51 Scope Narrowing

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `harness/plugins/autosci/adapters/autosci_to_literature_discovery.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Add `autosci_source_provider_boundary.v1` so source runtime completion requires non-fixture provider channels instead of generic `approved_runtime` candidates. |
| Out of scope | Do not call network providers, add deterministic source substitutes, or change approval side-effect policy. |

### Step 51 Result

| Check | Status | Evidence |
|---|---|---|
| Source provider boundary | ok | `autosci_source_provider_boundary.v1` is emitted in `literature_discovery.v1.outputs.source_provider_boundary`. |
| Generic runtime rejection | ok | Approved source runtime candidates with only generic `approved_runtime` channel now remain `inconclusive` instead of completed. |
| Provider-backed runtime acceptance | ok | Source runtime evidence with `source_channels=["search_s2"]` still completes and records provider boundary `provider_channels=["search_s2"]`. |
| Route truthfulness | ok | `/discover`, `/init`, and `/research --online` limitations now mention non-fixture provider channel boundary checks. |
| Targeted tests | ok | Source-boundary targeted tests: 2 passed. |
| Source/discover subset | ok | Literature backend/source CLI tests: 6 passed; source-related shim subset: 6 passed. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 87 passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 103 passed with elevated local bind permission. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step51.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 51 files passed before log write. |
| Full parity claim | warn | Still not honest: provider boundary is stricter, but actual live provider/network runs still require approved execution and external connectivity proof. |

## Next Planned Step - Remote Session External Poll Boundary

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md` |
| Intent | Inspect `$exp-status` remote status evidence so approved local checks cannot be mistaken for live SSH/provider polling. |
| Out of scope | Do not run real SSH/provider commands without explicit approval. |

### Step 52 Scope Narrowing

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Add `autosci_remote_poll_boundary.v1` so `$exp-status` distinguishes local `run_dir` status-file checks from declared live SSH/provider polling. |
| Out of scope | Do not execute real SSH/provider commands, change approval policy, or mark `/exp-status` full. |

### Step 52 Result

| Check | Status | Evidence |
|---|---|---|
| Remote poll boundary | ok | `$exp-status` runtime evidence now includes `autosci_remote_poll_boundary.v1`. |
| Local run-dir classification | ok | Approved `tools/remote.py check` status-file reads keep returning experiment state, but boundary status is `local_run_dir_check` with `live_remote_poll_verified=false`. |
| Status report visibility | ok | `experiment_status.v1.outputs.status_report.observations` includes `remote_poll_boundary_status=local_run_dir_check`, and limitations state that this is not proven live SSH/provider polling. |
| Route truthfulness | ok | `/exp-status` limitation now says local run-dir status-file checks are not counted as live SSH/provider polling. |
| Syntax and config | ok | `py_compile` passed for bridge/tests; `python3 -m json.tool` passed for route config. |
| Targeted test | ok | `$exp-status` approved remote-check boundary test: 1 passed. |
| Experiment route subset | ok | exp-status/run/collect remote subset: 12 passed. |
| Runtime binding audit | ok | `audit_scientific_runtime_bindings.py --strict --json`: 28 nodes, 2 workflows, 0 issues. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 103 passed with elevated local bind permission. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step52.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 52 files passed before log write. |
| Full parity claim | warn | Still not honest: boundary prevents overclaiming, but live SSH/provider status polling has not been executed. |

## Next Planned Step - Approved Live Remote Status Command

| Field | Value |
|---|---|
| Planned files | `tools/remote.py`, `harness/plugins/autosci/bin/autosci_bridge.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Inspect whether `tools/remote.py check` can run an explicitly approved live/provider status command and emit transport/session metadata that satisfies the remote poll boundary. |
| Out of scope | Do not run real SSH/provider commands without approval or weaken the allowlist requirement. |

### Step 53 Result

| Check | Status | Evidence |
|---|---|---|
| Approved live status command | ok | `tools/remote.py check` now accepts `--status-command` with `--approval-ref`, `--allowlist-evidence`, `--execute-approved`, `--transport`, and `--session-id`. |
| Allowlist robustness | ok | `tools/remote.py` command allowlist matching now accepts both raw join and `shlex.join` forms, so paths with spaces do not break approved command matching. |
| Live boundary completion | ok | `$exp-status` can now complete `autosci_remote_poll_boundary.v1` as `live_remote_poll` when the approved status command emits `remote_state` plus recognized transport/session metadata. |
| Local boundary preservation | ok | Plain `tools/remote.py check --run-dir` remains `local_run_dir_check` and does not satisfy live provider polling proof. |
| Route truthfulness | ok | `/exp-status` limitation now lists approved live/provider status command execution but keeps real external connectivity smoke as pending. |
| Syntax and config | ok | `py_compile` passed for `tools/remote.py`, bridge, and shim tests; route config `json.tool` passed. |
| Targeted tests | ok | Local + live `$exp-status` remote-check tests: 2 passed. |
| Experiment route subset | ok | exp-status/run/collect remote subset: 13 passed. |
| Runtime binding audit | ok | `audit_scientific_runtime_bindings.py --strict --json`: 28 nodes, 2 workflows, 0 issues. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 104 passed with elevated local bind permission. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step53.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 53 files passed before log write. |
| Full parity claim | warn | Still not honest: the command path is wired, but no real SSH/provider target was contacted in this verification run. |

## Next Planned Step - Approved Remote Pull Results Command

| Field | Value |
|---|---|
| Planned files | `tools/remote.py`, `harness/plugins/autosci/bin/autosci_bridge.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Inspect remote result collection so `tools/remote.py pull-results` can run an explicitly approved provider pull command and distinguish local result-dir reads from live remote/provider collection. |
| Out of scope | Do not run real SSH/rsync/provider commands without approval or claim distributed exactly-once collection complete. |

### Step 54 Result

| Check | Status | Evidence |
|---|---|---|
| Approved live pull-results command | ok | `tools/remote.py pull-results` now accepts `--pull-command` with `--approval-ref`, `--allowlist-evidence`, `--execute-approved`, `--transport`, and `--session-id`. |
| Remote collection boundary | ok | Collect runtime evidence now includes `autosci_remote_collection_boundary.v1`. |
| Local collection classification | ok | Plain `tools/remote.py pull-results --result-dir` remains completed when files exist, but boundary status is `local_result_dir_collection`. |
| Live collection classification | ok | Approved provider pull command can produce result files and satisfy boundary status `live_remote_collection` with transport/session metadata. |
| Route truthfulness | ok | `/exp-run` limitation now names approved live/provider pull-results boundary and keeps distributed exactly-once/external smoke pending. |
| Syntax and config | ok | `py_compile` passed for `tools/remote.py`, bridge, and shim tests; route config `json.tool` passed. |
| Targeted tests | ok | Local + live pull-results targeted tests: 2 passed. |
| Experiment route subset | ok | exp-status/run/collect remote subset: 15 passed. |
| Runtime binding audit | ok | `audit_scientific_runtime_bindings.py --strict --json`: 28 nodes, 2 workflows, 0 issues. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 105 passed with elevated local bind permission. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step54.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 54 files passed before log write. |
| Full parity claim | warn | Still not honest: approved pull command support is wired, but no real SSH/rsync/provider target was contacted in this verification run. |

## Next Planned Step - Scheduler Replay Resume Boundary

| Field | Value |
|---|---|
| Planned files | `harness/tools/run_scientific_lifecycle_smoke.py`, `tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Inspect scheduler resume/replay evidence so production-dispatch parity cannot be claimed without durable node replay state and no-rerun proof. |
| Out of scope | Do not replace the bounded smoke runner with a fake production scheduler or mark `/research` full. |

### Step 55 Result

| Check | Status | Evidence |
|---|---|---|
| Resume boundary | ok | Resume summaries now include `autosci_scheduler_resume_boundary.v1`. |
| No-rerun proof | ok | Boundary records source summary path, reused node fingerprints, dispatched nodes, changed reused nodes, and `no_rerun_verified`. |
| Resume checks | ok | Resume runs add `scheduler_resume_no_rerun_boundary` to lifecycle checks. |
| Route truthfulness | ok | `/research` limitation now names scheduler resume boundary while keeping non-smoke dispatcher and lease/runtime audit pending. |
| Syntax and config | ok | `py_compile` passed for runner/test; route config `json.tool` passed. |
| Targeted resume test | ok | Human-gate resume targeted test: 1 passed. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 87 passed. |
| Research scheduler shim subset | ok | `$research` scheduler subset: 8 passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 105 passed with elevated local bind permission. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step55.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 55 files passed before log write. |
| Full parity claim | warn | Still not honest: resume proof is structured, but the dispatcher is still the bounded smoke runner and lacks production leases. |

## Next Planned Step - Scheduler Lease Boundary

| Field | Value |
|---|---|
| Planned files | `harness/tools/run_scientific_lifecycle_smoke.py`, `tests/harness/evaluators/scientific/test_scientific_lifecycle_runtime_smoke.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Add explicit scheduler lease evidence so lifecycle dispatch reports local lease ownership and does not imply distributed production lease parity. |
| Out of scope | Do not claim distributed lease/quota parity or add a new scheduler service. |

### Step 56 Result

| Check | Status | Evidence |
|---|---|---|
| Lease sidecar | ok | Lifecycle run and resume now write `scheduler_lease.json` with `autosci_scheduler_lease.v1`. |
| Lease boundary | ok | Lifecycle summaries now include `autosci_scheduler_lease_boundary.v1` with local lease ownership and distributed lease status. |
| Lease check | ok | Lifecycle checks include `scheduler_local_lease_boundary`. |
| Route truthfulness | ok | `/research` limitation now names local lease boundary and keeps distributed lease/quota/runtime audit pending. |
| Syntax and config | ok | `py_compile` passed for runner/test; route config `json.tool` passed. |
| Targeted tests | ok | Blocked lifecycle + resume targeted tests: 2 passed. |
| Scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 87 passed. |
| Research scheduler shim subset | ok | `$research` scheduler subset: 8 passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 105 passed with elevated local bind permission. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step56.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 56 files passed before log write. |
| Full parity claim | warn | Still not honest: lease ownership is local to the smoke runner and does not prove distributed scheduler lease/quota parity. |

## Next Planned Step - Publication Submission Checklist Boundary

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Inspect paper-compile publication evidence so compile/PDF success is separated from submission checklist, anonymity, page/font, and unresolved-marker proof. |
| Out of scope | Do not claim venue submission readiness without verified checklist evidence. |

### Step 57 Result

| Check | Status | Evidence |
|---|---|---|
| Submission boundary | ok | Paper compile writes `publication_submission_boundary.json` with `autosci_publication_submission_boundary.v1`. |
| Checklist integration | ok | `paper_compile_checklist.v1` now embeds `submission_boundary` and includes a `publication_submission_boundary` check row. |
| Diagnostics integration | ok | Paper compile diagnostics render a Submission Boundary section. |
| Bundle artifact | ok | `publication_submission_boundary_json` is included in publication bundle files/artifacts. |
| Route truthfulness | ok | `/paper-compile` limitation now says submission boundary separates compile/PDF evidence from submission/anonymity/page/font readiness. |
| Syntax and config | ok | `py_compile` passed for bridge/tests; route config `json.tool` passed. |
| Targeted test | ok | Submission checklist boundary targeted test: 1 passed. |
| Publication subset | ok | paper-compile/paper-plan/paper-draft publication subset: 10 passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 105 passed with elevated local bind permission. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step57.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 57 files passed before log write. |
| Full parity claim | warn | Still not honest: submission boundary is present, but CLI evidence flags for page/font/anonymity proof are not yet exposed. |

## Next Planned Step - Paper Compile Submission Evidence Flags

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_skill_shim.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Add paper-compile CLI evidence flags for anonymous/double-blind mode, page count/limit, and minimum font-size proof so submission boundary can pass when evidence is supplied. |
| Out of scope | Do not infer page/font/anonymity proof without explicit evidence inputs. |

### Step 58 Result

| Check | Status | Evidence |
|---|---|---|
| CLI evidence flags | ok | `$paper-compile` now accepts `--anonymous`, `--double-blind`, `--submission-mode`, `--page-limit`, `--page-count`, `--verified-page-count`, `--min-font-size`, and `--verified-min-font-size`. |
| Native options | ok | Submission evidence flags are preserved in `native_options` and action inputs instead of being inferred from source text alone. |
| Submission boundary completion | ok | Explicit CLI evidence can make `autosci_publication_submission_boundary.v1` reach `submission_ready` when PDF, anonymity, page, font, and marker checks all pass. |
| Route truthfulness | ok | `/paper-compile` limitation now states CLI evidence flags satisfy the boundary only when explicit proof is supplied. |
| Syntax and config | ok | `py_compile` passed for shim/tests; route config JSON load passed. |
| Targeted tests | ok | Submission incomplete + submission-ready paper-compile targeted tests: 2 passed. |
| Publication subset | ok | paper-compile/paper-plan/paper-draft publication subset: 11 passed. |
| Full shim suite | ok | First sandbox run failed only on local `127.0.0.1` bind permission; elevated rerun passed: 106 passed. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step58.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 58 files passed before log write. |
| Full parity claim | warn | Still not honest: submission evidence can be supplied, but venue-specific submission profiles and external submission audit are not yet modeled. |

## Next Planned Step - Paper Compile Venue Submission Profile Boundary

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `harness/plugins/autosci/bin/autosci_skill_shim.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Add an explicit venue submission profile input so venue/page/font/anonymity requirements are source-backed and separate from generic CLI overrides. |
| Out of scope | Do not infer venue rules from the venue name, scrape external CFPs, or claim actual venue submission completion. |

### Step 59 Result

| Check | Status | Evidence |
|---|---|---|
| Submission profile CLI | ok | `$paper-compile` now accepts `--submission-profile` and forwards the JSON evidence path into compile inputs/native options. |
| Profile parser | ok | Bridge loads `autosci_submission_profile.v1`-style JSON, extracts venue, submission mode, anonymity, page limit, minimum font size, evidence ids, SHA-256, and conflicts. |
| Requirement application | ok | Profile requirements fill missing compile inputs only; explicit CLI/profile conflicts block venue readiness instead of silently overriding. |
| Venue boundary | ok | `autosci_publication_submission_boundary.v1` now reports `venue_status`, `venue_submission_ready`, `venue_blocking_checks`, and embedded `submission_profile`. |
| Diagnostics/artifacts | ok | Diagnostics render venue/profile status and bundles include `venue_submission_profile_json` when a profile is loaded. |
| Route truthfulness | ok | `/paper-compile` now states venue readiness requires source-backed `--submission-profile` rather than inferred venue rules. |
| Syntax and config | ok | `py_compile` passed for bridge/shim/tests; route config JSON load passed. |
| Targeted tests | ok | Missing evidence, CLI evidence, and venue profile targeted tests: 3 passed. |
| Publication subset | ok | paper-compile/paper-plan/paper-draft publication subset: 12 passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 107 passed with elevated local bind permission. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step59.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 59 files passed before log write. |
| Full parity claim | warn | Still not honest: venue profile requirements are modeled, but page/font proof is still supplied as numeric CLI evidence rather than a PDF inspection sidecar. |

## Next Planned Step - Paper Compile PDF Inspection Evidence Ingestion

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `harness/plugins/autosci/bin/autosci_skill_shim.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Add explicit PDF inspection evidence input so verified page count and minimum font size can come from a source artifact instead of loose numeric flags. |
| Out of scope | Do not parse arbitrary PDFs or claim external venue submission completion without a verified inspection artifact. |

### Step 60 Result

| Check | Status | Evidence |
|---|---|---|
| PDF inspection CLI | ok | `$paper-compile` now accepts `--pdf-inspection` and forwards it into compile inputs/native options. |
| Inspection parser | ok | Bridge loads `autosci_pdf_inspection.v1`-style JSON, verifies the referenced PDF by path or SHA-256, and extracts page/font measurements and evidence ids. |
| Measurement application | ok | Verified page count and minimum font size can be applied from the inspection sidecar instead of loose numeric CLI flags. |
| Venue readiness tightening | ok | `venue_submission_ready` now requires generic submission readiness, loaded venue profile, and loaded PDF inspection evidence. |
| Diagnostics/artifacts | ok | Diagnostics render PDF inspection status and bundles include `pdf_inspection_json` when loaded. |
| Route truthfulness | ok | `/paper-compile` now states venue readiness requires both `--submission-profile` and `--pdf-inspection`. |
| Syntax and config | ok | `py_compile` passed for bridge/shim/tests; route config JSON load passed. |
| Targeted tests | ok | Missing evidence, CLI evidence, profile-only, and profile+PDF-inspection tests: 4 passed. |
| Publication subset | ok | paper-compile/paper-plan/paper-draft publication subset: 13 passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 108 passed with elevated local bind permission. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step60.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 60 files passed before log write. |
| Full parity claim | warn | Still not honest: compile/profile/PDF inspection readiness is modeled, but external submission audit evidence is not yet ingested. |

## Next Planned Step - Publication Submission Audit Evidence Boundary

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `harness/plugins/autosci/bin/autosci_skill_shim.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Add explicit publication submission audit evidence so venue readiness and final submission audit readiness are separate, source-backed states. |
| Out of scope | Do not claim a portal upload or conference submission unless the audit evidence explicitly says so. |

### Step 61 Result

| Check | Status | Evidence |
|---|---|---|
| Submission audit CLI | ok | `$paper-compile` now accepts `--submission-audit` and forwards it into compile inputs/native options. |
| Audit parser | ok | Bridge loads `autosci_publication_submission_audit.v1`-style JSON, requires check rows, records evidence ids, SHA-256, blocking checks, and portal completion status. |
| Boundary separation | ok | `autosci_publication_submission_boundary.v1` now reports `submission_audit_ready`, `submission_audit_status`, `submission_audit_blocking_checks`, and `portal_submission_completed` separately. |
| Portal truthfulness | ok | `portal_submission_completed` is never implied by audit readiness; it only reflects explicit audit evidence. |
| Diagnostics/artifacts | ok | Diagnostics render audit status and bundles include `publication_submission_audit_json` when loaded. |
| Route truthfulness | ok | `/paper-compile` now states submission audit readiness requires explicit `--submission-audit` evidence. |
| Syntax and config | ok | `py_compile` passed for bridge/shim/tests; route config JSON load passed. |
| Targeted tests | ok | Paper compile submission/profile/PDF/audit targeted tests: 5 passed. |
| Publication subset | ok | paper-compile/paper-plan/paper-draft publication subset: 14 passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 109 passed with elevated local bind permission. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step61.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 61 files passed before log write. |
| Full parity claim | warn | Still not honest: publication audit readiness is modeled, but Review LLM final acceptance for `/review` remains partial. |

## Next Planned Step - Review LLM Final Acceptance Boundary

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `harness/plugins/autosci/bin/autosci_skill_shim.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Add explicit Review LLM final acceptance evidence so local surrogate review is separated from provider/command/evidence-backed final review. |
| Out of scope | Do not treat heuristic/local review as final acceptance without Review LLM evidence. |

### Step 62 Result

| Check | Status | Evidence |
|---|---|---|
| Review LLM requirement flag | ok | `$review` now accepts `--require-review-llm` and records the requirement in native options/inputs. |
| Final acceptance boundary | ok | Review outputs now include `autosci_review_final_acceptance_boundary.v1` with final readiness, invocation mode, provider/model, hashes, evidence ids, and blocking reasons. |
| Local surrogate separation | ok | Local surrogate review remains available but boundary reports `review_llm_incomplete` rather than final acceptance. |
| Provider/evidence acceptance | ok | Supplied Review LLM evidence, command bridge, and OpenAI-compatible provider paths can produce `final_acceptance_ready`. |
| Diagnostics/artifacts | ok | Review evidence now includes `review_final_acceptance_boundary_json`. |
| Route truthfulness | ok | `/review` limitation now names the final acceptance boundary and records local surrogate insufficiency. |
| Syntax and config | ok | `py_compile` passed for bridge/shim/tests; route config JSON load passed. |
| Targeted tests | ok | Local/evidence/command/provider review boundary tests: 4 passed. |
| Review subset | ok | `-k review`: 15 passed with elevated local bind permission. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 109 passed with elevated local bind permission. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step62.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 62 files passed before log write. |
| Full parity claim | warn | Still not honest: `/review` final acceptance is explicit, but `/novelty` still lacks a consolidated final acceptance boundary across source novelty and Review LLM proof. |

## Next Planned Step - Novelty Final Acceptance Boundary

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Add explicit novelty final acceptance boundary requiring external novelty evidence plus Review LLM proof, without treating local/source-only checks as final acceptance. |
| Out of scope | Do not synthesize novelty acceptance from unavailable providers or local heuristics. |

### Step 63 Result

| Check | Status | Evidence |
|---|---|---|
| Final acceptance boundary | ok | Idea evaluations now embed `autosci_novelty_final_acceptance_boundary.v1`. |
| Boundary sidecar | ok | Evaluate-ideas writes `novelty_final_acceptance_boundary.json` with `autosci_novelty_final_acceptance_boundary_set.v1`. |
| Source/review gating | ok | Boundary requires completed external novelty evidence, passed provider provenance, completed Review LLM evidence, and numeric novelty score. |
| Writeback linkage | ok | Novelty writeback sidecar now records `final_acceptance_status` and `final_acceptance_ready` without changing the original writeback gating order. |
| Route truthfulness | ok | `/novelty` limitation now names the final acceptance boundary and its evidence requirements. |
| Syntax and config | ok | `py_compile` passed for bridge/tests; route config JSON load passed. |
| Targeted tests | ok | Local, external-only, external+Review LLM writeback, and missing-review writeback tests: 4 passed. |
| Novelty subset | ok | `-k novelty`: 11 passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 109 passed with elevated local bind permission. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step63.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 63 files passed before log write. |
| Full parity claim | warn | Still not honest: novelty acceptance is explicit, but `/ask` still lacks a final answer boundary separating retrieval-only/local synthesis from model-backed final answers. |

## Next Planned Step - Ask Final Answer Boundary

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Add explicit final answer boundary for `/ask` requiring retrieval/source evidence plus model-backed synthesis, without treating retrieval-only local summaries as final. |
| Out of scope | Do not synthesize final answers from heuristics when model evidence is missing. |

### Step 64 Result

| Check | Status | Evidence |
|---|---|---|
| Final answer boundary | ok | `/ask` retrieval JSON now embeds `autosci_ask_final_answer_boundary.v1`. |
| Boundary sidecar | ok | Ask runs write `ask_final_answer_boundary.json` and include `ask_final_answer_boundary_json` artifact. |
| Retrieval/model separation | ok | Retrieval-only answers remain completed extractive responses but report `ask_final_answer_incomplete`. |
| Model-backed readiness | ok | Retrieval plus completed model synthesis with answer and evidence ids reports `final_answer_ready`. |
| Route truthfulness | ok | `/ask` limitation now names the final answer boundary and its source/model requirements. |
| Syntax and config | ok | `py_compile` passed for bridge/tests; route config JSON load passed. |
| Targeted tests | ok | Retrieval-only and model-command ask tests: 2 passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 109 passed with elevated local bind permission. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step64.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 64 files passed before log write. |
| Full parity claim | warn | Still not honest: `/ask` final answer readiness is explicit, but `/check` still lacks a final quality boundary separating local checks from model-backed recommendations. |

## Next Planned Step - Check Final Quality Boundary

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Add explicit final quality boundary for `/check` requiring local wiki checks plus model-backed recommendation evidence, without treating lint-only output as final review. |
| Out of scope | Do not invent model/reviewer conclusions when model evidence is missing. |

### Step 65 Result

| Check | Status | Evidence |
|---|---|---|
| Final quality boundary | ok | `/check` now embeds `autosci_check_final_quality_boundary.v1` in `evolution.review.final_quality_boundary`. |
| Boundary sidecar | ok | Check runs write `check_final_quality_boundary.json` and include `check_final_quality_boundary_json` artifact. |
| Local/model separation | ok | Passing local wiki structure without model evidence remains `check_final_quality_incomplete`. |
| Model-backed readiness | ok | Passing local checks plus completed model-backed recommendation evidence reports `final_quality_ready`. |
| Route truthfulness | ok | `/check` limitation now names final quality boundary and its local/model requirements. |
| Syntax and config | ok | `py_compile` passed for bridge/tests; route config JSON load passed. |
| Targeted tests | ok | Retrieval/check local and model-command check tests: 2 passed. |
| Ask/check subset | ok | `-k 'ask or check'`: 8 passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 109 passed with elevated local bind permission. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step65.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 65 files passed before log write. |
| Full parity claim | warn | Still not honest: `/check` final quality readiness is explicit, but `/discover` still lacks a final shortlist boundary separating local fallback from provider-backed discovery. |

## Next Planned Step - Discover Final Shortlist Boundary

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Add explicit discovery final shortlist boundary requiring source-backed provider evidence, without treating local fallback/fixture candidates as final discovery. |
| Out of scope | Do not invent provider evidence when live/API sources are unavailable. |

### Step 66 Result

| Check | Status | Evidence |
|---|---|---|
| Final shortlist boundary | ok | Discover source provider boundary now embeds `autosci_discover_final_shortlist_boundary.v1`. |
| Boundary sidecar | ok | Discover runs write `discover_final_shortlist_boundary.json` and include `discover_final_shortlist_boundary_json` artifact. |
| Local/provider separation | ok | Empty wiki/local fallback and generic runtime channels remain `discover_shortlist_incomplete`. |
| Provider-backed readiness | ok | Non-empty candidates with provider channel such as `search_s2` can report `final_shortlist_ready`. |
| Route truthfulness | ok | `/discover` limitation now names final shortlist boundary and provider-channel requirements. |
| Syntax and config | ok | `py_compile` passed for bridge/tests; route config JSON load passed. |
| Targeted tests | ok | Wiki/local, generic runtime, and provider-backed runtime discovery tests passed. |
| Discover/source subset | ok | `-k 'discover or source_runtime_evidence'`: 4 passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 109 passed with elevated local bind permission. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step66.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 66 files passed before log write. |
| Full parity claim | warn | Still not honest: `/discover` final shortlist readiness is explicit, but `/survey` still lacks a final coverage boundary for citation/source coverage. |

## Next Planned Step - Survey Final Coverage Boundary

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Add explicit survey final coverage boundary requiring source-backed citation coverage, without treating partial/local citation maps as exhaustive survey evidence. |
| Out of scope | Do not claim exhaustive literature coverage without explicit provider/source evidence. |

### Step 67 Result

| Check | Status | Evidence |
|---|---|---|
| Final coverage boundary | ok | `/survey` now writes `autosci_survey_final_coverage_boundary.v1`. |
| Boundary sidecar | ok | Survey runs include `survey_final_coverage_boundary_json`. |
| Bounded/exhaustive separation | ok | Source-backed citation evidence can report bounded `final_coverage_ready`, while `exhaustive_coverage_verified` remains false without provider audit. |
| Scaffold separation | ok | Survey scaffold without source/citation evidence reports `survey_coverage_incomplete`. |
| Route truthfulness | ok | `/survey` limitation now names bounded coverage and keeps exhaustive live coverage pending. |
| Syntax and config | ok | `py_compile` passed for bridge/tests; route config JSON load passed. |
| Targeted tests | ok | Survey scaffold and citation-map completion tests: 2 passed. |
| Publication/survey subset | ok | `-k 'survey or paper_plan or paper_compile or paper_draft'`: 19 passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 109 passed with elevated local bind permission. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step67.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 67 files passed before log write. |
| Full parity claim | warn | Still not honest: survey coverage is bounded and explicit, but `/paper-draft` still lacks a final manuscript readiness boundary. |

## Next Planned Step - Paper Draft Final Manuscript Boundary

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Add explicit paper-draft final manuscript boundary requiring source evidence, citation map, Review LLM proof, and compile/PDF handoff before treating a draft as publication-ready. |
| Out of scope | Do not treat generated LaTeX sidecars as a final manuscript without review/compile evidence. |

### Step 68 Result

| Check | Status | Evidence |
|---|---|---|
| Final manuscript boundary | ok | `/paper-draft` now writes `autosci_paper_draft_final_manuscript_boundary.v1`. |
| Boundary sidecar | ok | Draft report artifacts include `paper_draft_final_manuscript_boundary_json`; publication bundle passthrough preserves it. |
| Citation/source handoff | ok | Draft runs write `paper_draft_citation_map.json` and include `citation_map_json`. |
| Publication-ready separation | ok | Plain LaTeX draft without source/citation/Review LLM/compile evidence is `inconclusive` and `publication_ready_claim_allowed=false`. |
| Final-ready path | ok | Source citation evidence plus completed Review LLM proof plus verified compile/PDF handoff reports `final_manuscript_ready`. |
| Route truthfulness | ok | `/paper-draft` limitation now names the final manuscript boundary and its four required evidence classes. |
| Syntax and config | ok | `py_compile` passed for bridge/tests; route config JSON load passed. |
| Targeted tests | ok | Paper-draft incomplete and final-ready boundary tests: 2 passed. |
| Publication/survey subset | ok | `-k 'survey or paper_plan or paper_compile or paper_draft'`: 19 passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 109 passed with elevated local bind permission. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step68.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 68 files passed before log write. |
| Full parity claim | warn | Still not honest: `/paper-draft` final manuscript readiness is explicit, but `/paper-plan` still lacks a final plan acceptance boundary separating scaffold plans from draft/compile-ready plans. |

## Next Planned Step - Paper Plan Final Acceptance Boundary

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Add explicit paper-plan final acceptance boundary requiring source-backed citation plan, Review LLM proof, and downstream compile/PDF handoff before treating a plan as draft/compile-ready. |
| Out of scope | Do not claim a paper plan is final-ready from outline text alone or from missing compile audit evidence. |

### Step 69 Scope Amendment

| Field | Value |
|---|---|
| Additional file | `harness/tools/run_scientific_lifecycle_smoke.py` |
| Reason | Full shim verification showed scheduler report_plan did not receive compile/PDF handoff inputs, so the new paper-plan final acceptance boundary could not be satisfied in the approved publication compile lifecycle. |
| Constraint | Only propagate existing approved compile evidence into report_plan; do not relax final acceptance boundary checks. |

### Step 69 Result

| Check | Status | Evidence |
|---|---|---|
| Final plan acceptance boundary | ok | `/paper-plan` now writes `autosci_paper_plan_final_acceptance_boundary.v1`. |
| Boundary sidecar | ok | Plan artifacts include `paper_plan_final_acceptance_boundary_json`. |
| Draft/compile readiness separation | ok | Citation plus Review LLM without compile/PDF stays `paper_plan_final_acceptance_incomplete`. |
| Final-ready path | ok | Source-backed citation plan, completed Review LLM proof, and verified compile/PDF handoff reports `final_plan_accepted`. |
| Scheduler compile handoff | ok | `report_plan` scheduler inputs now receive approved compile contract fields; approved compile execution can produce runtime/PDF handoff for the plan boundary. |
| Route truthfulness | ok | `/paper-plan` limitation now names final acceptance boundary requirements. |
| Syntax and config | ok | `py_compile` passed for bridge, scheduler runner, and tests; route config JSON load passed. |
| Targeted tests | ok | Paper-plan boundary tests: 3 passed. |
| Scheduler regression | ok | Approved publication compile lifecycle test: 1 passed. |
| Publication/survey subset | ok | `-k 'survey or paper_plan or paper_compile or paper_draft or research_scheduler_executes_approved_publication_compile'`: 20 passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 109 passed with elevated local bind permission. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step69.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 69 files passed before log write. |
| Full parity claim | warn | Still not honest: publication plan/draft boundaries are explicit, but `/ideate` still lacks a final idea-promotion boundary for wiki maturity, failed-idea banlist, source evidence, model brainstorm, and downstream novelty/review gates. |

## Next Planned Step - Ideate Final Promotion Boundary

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Add explicit `/ideate` final promotion boundary requiring wiki maturity scan, failed-idea banlist check, source-backed evidence, model brainstorm provenance, and novelty/review gate references before generated ideas are promotable. |
| Out of scope | Do not replace missing dual-model/provider brainstorming or novelty review with deterministic keyword heuristics. |

### Step 70 Result

| Check | Status | Evidence |
|---|---|---|
| Final promotion boundary | ok | `/ideate` now writes `autosci_ideate_final_promotion_boundary.v1`. |
| Per-idea boundary | ok | Each generated idea carries `autosci_ideate_idea_promotion_boundary.v1` plus `promotion_ready`. |
| Boundary sidecar | ok | Generate-ideas artifacts include `ideate_final_promotion_boundary_json`. |
| Source/model/gate separation | ok | Source-grounded and model-command ideas remain non-promotable until novelty/review gate references are supplied. |
| Missing-source separation | ok | Missing-source ideation stays `inconclusive` and boundary records missing source-backed evidence. |
| Route truthfulness | ok | `/ideate` limitation now names the final promotion boundary and remaining provider/gate blockers. |
| Syntax and config | ok | `py_compile` passed for bridge/tests; route config JSON load passed. |
| Targeted tests | ok | Ideate source/model/missing-source boundary tests: 3 passed. |
| Ideate/novelty subset | ok | `-k 'ideate or novelty'`: 14 passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 109 passed with elevated local bind permission. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step70.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 70 files passed before log write. |
| Full parity claim | warn | Still not honest: ideate promotion readiness is explicit, but experiment design still lacks a final execution-readiness boundary tying idea/evaluation evidence, Review LLM proof, and runtime handoff requirements together. |

## Next Planned Step - Experiment Design Final Execution Boundary

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Add explicit `/exp-design` final execution-readiness boundary requiring resolved idea/evaluation evidence, completed Review LLM design validation, and declared runtime/artifact handoff requirements before an experiment plan is executable. |
| Out of scope | Do not claim experiment execution readiness from a local plan scaffold or missing runtime approval evidence. |

### Step 71 Result

| Check | Status | Evidence |
|---|---|---|
| Final execution boundary | ok | `/exp-design` now writes `autosci_experiment_design_final_execution_boundary.v1`. |
| Boundary sidecar | ok | Experiment-plan artifacts include `experiment_design_final_execution_boundary_json`. |
| Plan embedding | ok | Plan `source_context.final_execution_boundary` records target resolution, Review LLM status, approval preflight, command handoff, and artifact handoff. |
| Review-only separation | ok | Review LLM validation without approval preflight remains `execution_readiness_incomplete`. |
| Execution-ready path | ok | Review LLM plus approval/allowlist/before preflight reports `execution_ready`. |
| Test isolation | ok | Local novelty test now sets `AUTOSCI_DISABLE_NETWORK_FETCH=1` so it does not depend on live Semantic Scholar availability. |
| Route truthfulness | ok | `/exp-design` limitation now names final execution boundary requirements. |
| Syntax and config | ok | `py_compile` passed for bridge/tests; route config JSON load passed. |
| Targeted tests | ok | Exp-design boundary tests: 2 passed. |
| Experiment/novelty subset | ok | `-k 'exp_design or exp_run or exp_status or exp_pilot or novelty'`: 28 passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 110 passed with elevated local bind permission. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step71.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 71 files passed before log write. |
| Full parity claim | warn | Still not honest: experiment design readiness is explicit, but experiment evaluation still lacks a final verdict boundary tying result, claim/code evidence, Review LLM proof, and writeback status together. |

## Next Planned Step - Experiment Evaluation Final Verdict Boundary

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Add explicit `/exp-eval` final verdict boundary requiring experiment result evidence, linked claim/code evidence, completed Review LLM proof, and explicit writeback status before verdicts are treated as final. |
| Out of scope | Do not promote local verdict scaffolds or unapproved wiki writeback proposals as final evaluation results. |

### Step 72 Result

| Check | Status | Evidence |
|---|---|---|
| Final verdict boundary | ok | `/exp-eval` now writes `autosci_experiment_evaluation_final_verdict_boundary.v1`. |
| Boundary sidecar | ok | Claim-verdict artifacts include `experiment_evaluation_final_verdict_boundary_json`. |
| Verdict embedding | ok | Verdict outputs include `final_verdict_boundary` and `final_verdict_ready`. |
| Evidence/writeback separation | ok | Result, claim, code, and Review LLM evidence without approved writeback remains `final_verdict_incomplete`. |
| Final-ready path | ok | Completed experiment result, linked claim/code evidence, completed Review LLM proof, and completed approved wiki writeback report `final_verdict_ready`. |
| Route truthfulness | ok | `/exp-eval` now records approval-required writeback policy and final verdict boundary requirements. |
| Syntax and config | ok | `py_compile` passed for bridge/tests; route config JSON load passed. |
| Targeted tests | ok | Exp-eval boundary tests: 2 passed. |
| Experiment subset | ok | `-k 'exp_eval or exp_pilot_eval or exp_design or exp_run or exp_status or exp_pilot'`: 19 passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 110 passed with elevated local bind permission. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step72.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 72 files passed before log write. |
| Full parity claim | warn | Still not honest: experiment evaluation finality is explicit, but `/exp-run` still lacks a final runtime audit boundary tying approved deploy, monitor, collect, collection ledger, and wiki mutation evidence together. |

## Next Planned Step - Experiment Run Final Runtime Audit Boundary

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Add explicit `/exp-run` final runtime audit boundary requiring approved deploy/run evidence, monitor/collect evidence, collection ledger, and wiki state mutation proof before a run is treated as fully executed/collected. |
| Out of scope | Do not treat fixture result scaffolds, gated plans, or unapproved remote collection proposals as completed native execution. |

### Step 73 Result

| Check | Status | Evidence |
|---|---|---|
| Final runtime audit boundary | ok | `/exp-run` run/collect paths now write `autosci_experiment_run_final_runtime_audit_boundary.v1`. |
| Boundary sidecar | ok | Run/status artifacts include `experiment_run_final_runtime_audit_boundary_json`. |
| Run-only separation | ok | Approved run evidence plus wiki mutation reports `stage_runtime_audit_ready` but not final lifecycle readiness. |
| Local collect separation | ok | Approved local result-dir collection records ledger evidence but remains non-final without live provider/SSH collection proof. |
| Live collect final path | ok | Approved live/provider pull-results with ledger and wiki mutation reports `final_runtime_audit_ready`. |
| Route truthfulness | ok | `/exp-run` limitation now names final runtime audit boundary requirements. |
| Syntax and config | ok | `py_compile` passed for bridge/tests; route config JSON load passed. |
| Targeted tests | ok | Exp-run runtime/local collect/live collect boundary tests: 3 passed. |
| Experiment subset | ok | `-k 'exp_eval or exp_pilot_eval or exp_design or exp_run or exp_status or exp_pilot or exp_collect'`: 24 passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 110 passed with elevated local bind permission. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step73.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 73 files passed before log write. |
| Full parity claim | warn | Still not honest: `/exp-run` now has explicit final lifecycle boundary, but pilot run/eval routes still lack final pilot runtime/evaluation acceptance boundaries. |

## Next Planned Step - Pilot Experiment Final Acceptance Boundary

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Add explicit `/exp-pilot-run` and `/exp-pilot-eval` final pilot acceptance boundaries requiring approved pilot runtime evidence, collected pilot result evidence, verdict linkage, and approved wiki writeback status before pilot success/evaluation is treated as final. |
| Out of scope | Do not promote diagnostics-only pilot runs or lenient local pilot verdicts to final research evidence. |

### Step 74 Result

| Check | Status | Evidence |
|---|---|---|
| Pilot run boundary | ok | `/exp-pilot-run` now writes `autosci_pilot_experiment_final_acceptance_boundary.v1` with `stage=pilot_run`. |
| Pilot eval boundary | ok | `/exp-pilot-eval` now writes `autosci_pilot_experiment_final_acceptance_boundary.v1` with `stage=pilot_eval`. |
| Runtime/final separation | ok | Pilot runtime readiness remains non-final until pilot eval verdict and approved writeback exist. |
| Final-ready path | ok | Runtime-linked pilot verdict plus approved wiki writeback reports `final_pilot_acceptance_ready`. |
| Route truthfulness | ok | Pilot eval side-effect policy now reflects approval-required writeback; pilot run/eval limitations name final acceptance boundary requirements. |
| Syntax and config | ok | `py_compile` passed for bridge/tests; route config JSON load passed. |
| Targeted tests | ok | Pilot runtime/eval/writeback boundary tests: 3 passed. |
| Pilot/experiment subset | ok | `-k 'exp_pilot or pilot_eval or pilot_run or exp_eval or exp_run or exp_status or exp_design'`: 21 passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 110 passed with elevated local bind permission. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step74.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 74 files passed before log write. |
| Full parity claim | warn | Still not honest: pilot finality is explicit, but `/daily-arxiv` still lacks a final provider/finalize/delivery boundary for live feed, S2 enrichment, ranking, and approved delivery/ingest status. |

## Next Planned Step - Daily Arxiv Final Provider Delivery Boundary

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Add explicit `/daily-arxiv` final provider/delivery boundary requiring approved live provider runtime, source-channel candidate evidence, ranking/finalize evidence, and explicit delivery or ingest status before a daily digest is treated as final. |
| Out of scope | Do not treat local candidate fixtures, missing provider fetches, or unapproved email/ingest side effects as final daily discovery output. |

### Step 75 Result

| Check | Status | Evidence |
|---|---|---|
| Final provider/delivery boundary | ok | `/daily-arxiv` now writes `autosci_daily_arxiv_final_provider_delivery_boundary.v1`. |
| Boundary sidecar | ok | Daily discovery artifacts include `daily_arxiv_final_provider_delivery_boundary_json`. |
| Runtime/final separation | ok | Verified runtime digest with provider/ranking evidence is `daily_provider_ready`, not final delivery ready. |
| Final-ready path | ok | Approved wiki fan-in/ingest after provider candidates reports `daily_final_delivery_ready`. |
| Route truthfulness | ok | `/daily-arxiv` limitation now names provider, ranking, delivery/ingest boundary requirements. |
| Syntax and config | ok | `py_compile` passed for bridge/tests; route config JSON load passed. |
| Targeted tests | ok | Daily runtime digest and auto-ingest boundary tests: 2 passed. |
| Source/discovery subset | ok | `-k 'daily_arxiv or discover or init_sources or source_fan_in or ingest'`: 10 passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 110 passed with elevated local bind permission. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step75.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 75 files passed before log write. |
| Full parity claim | warn | Still not honest: `/daily-arxiv` finality is explicit, but `/init` source initialization still lacks a final provider/fan-in/rebuild boundary. |

## Next Planned Step - Init Sources Final Fan-In Boundary

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Add explicit `/init` source initialization final fan-in boundary requiring approved provider runtime, provider-backed candidates, approved wiki fan-in, graph/log/index rebuild evidence, and visible incomplete status when any piece is missing. |
| Out of scope | Do not treat setup scaffolds, missing source candidates, or unapproved wiki writes as completed source initialization. |

### Step 76 Result

| Check | Status | Evidence |
|---|---|---|
| Init final fan-in boundary | ok | `/init` now writes `autosci_init_sources_final_fan_in_boundary.v1`. |
| Boundary sidecar | ok | Init artifacts include `init_sources_final_fan_in_boundary_json`. |
| Runtime/final separation | ok | Provider-backed runtime source evidence is `init_sources_provider_ready`, not final fan-in ready. |
| Final-ready path | ok | Approved wiki fan-in with log, graph edge, index, and context rebuild evidence reports `init_sources_final_fan_in_ready`. |
| Route truthfulness | ok | `/init` side-effect policy now reflects approval-required provider fetch/wiki fan-in and limitation names final fan-in boundary requirements. |
| Syntax and config | ok | `py_compile` passed for bridge/tests; route config JSON load passed. |
| Targeted tests | ok | Init diagnostics, runtime-only, and approved fan-in boundary tests: 3 passed. |
| Source/init subset | ok | `-k 'init or daily_arxiv or discover or source_fan_in or ingest'`: 13 passed. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 110 passed with elevated local bind permission. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step76.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 76 files passed before log write. |
| Full parity claim | warn | Still not honest: `/init` final fan-in is explicit, but `/ingest` still lacks a final source registration boundary tying source preparation, parse quality, wiki registration, discovery handoff, and raw artifact provenance together. |

## Next Planned Step - Ingest Final Source Registration Boundary

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `tests/plugins/autosci/test_autosci_skill_shim.py`, `harness/plugins/autosci/config/feature_parity_routes.v1.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Add explicit `/ingest` final source registration boundary requiring verified source preparation, parsed paper metadata/text, raw artifact provenance, wiki paper registration/log/graph evidence, and downstream discovery handoff before an ingest is treated as final. |
| Out of scope | Do not treat parsed local files without wiki/provenance/handoff evidence as fully registered AutoSci sources. |

### Step 77 Plan Refinement

| Field | Value |
|---|---|
| Planned files | Add `harness/plugins/autosci/bin/autosci_skill_shim.py` to the Step 77 edit set. |
| Reason | `/ingest --wiki-root` must be propagated into bridge inputs so the final source registration boundary checks the intended wiki instead of only the default workspace path. |

### Step 77 Result

| Check | Status | Evidence |
|---|---|---|
| Ingest final source registration boundary | ok | `/ingest` now writes `autosci_ingest_final_source_registration_boundary.v1` with source prep, parse, raw provenance, sidecar handoff, and wiki registration checks. |
| Boundary sidecar | ok | Ingest artifacts include `ingest_final_source_registration_boundary_json`, `research_memory_update_json`, and `research_graph_update_json`. |
| Wiki-root propagation | ok | `/ingest --wiki-root` is passed into bridge inputs so custom wiki registration checks use the intended root. |
| Runtime/final separation | ok | Parsed PDF/source evidence remains non-final without wiki paper/log/graph/index/context registration. |
| Final-ready path | ok | Pre-registered wiki paper/log/graph/index/context evidence reports `ingest_source_registration_ready`. |
| Route truthfulness | ok | `/ingest` limitation now names the final source registration boundary requirements without upgrading coverage status. |
| Syntax and config | ok | `py_compile` passed for bridge/shim/tests; route config JSON load passed. |
| Targeted tests | ok | Ingest PDF incomplete-boundary and pre-registered final-ready tests: 2 passed. |
| Source/ingest subset | ok | `-k 'ingest or init or daily_arxiv or discover or source_fan_in'`: 14 passed. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step77.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Full shim suite | warn | Full suite is blocked by scheduler worker registry: 105 passed, 6 failed because `autosci-literature-discover-worker` is missing from `physical-operators.json`. |
| Diff hygiene | ok | `git diff --check` over Step 77 files passed before log write. |
| Full parity claim | warn | Still not honest: `/ingest` finality is explicit, but scheduler lifecycle parity is blocked by missing AutoSci worker registry entries. |

## Next Planned Step - Scheduler AutoSci Worker Registry Restore

| Field | Value |
|---|---|
| Planned files | `harness/config/physical-operators.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Restore bounded AutoSci worker entries required by scheduler lifecycle smoke so `$research --scheduler-run` can dispatch configured AutoSci bridge actions through `operator_runtime`. |
| Out of scope | Do not change scheduler semantics, workflow node ordering, provider execution, or production-dispatch readiness. |

### Step 78 Result

| Check | Status | Evidence |
|---|---|---|
| Physical worker registry | ok | Added scheduler-referenced `autosci-*` bounded command workers to `physical-operators.json`, each dispatching the matching `autosci_bridge.py run --action ...` command. |
| JSON/syntax | ok | `physical-operators.json` loads successfully; bridge/shim/scheduler smoke scripts pass `py_compile`. |
| Scheduler regression group | ok | Previously failing `$research --scheduler-run` group now passes: 6 passed, 105 deselected. |
| Full shim suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/plugins/autosci/test_autosci_skill_shim.py -q`: 111 passed with elevated local daemon/provider permission. |
| Feature parity inventory | warn | `env PYTHONPATH=harness .venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-step78.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Static runtime binding audit | warn | `audit_scientific_runtime_bindings.py --strict --json` now reaches the next blocker: `logical-operators.json` lacks Scientific* logical operators/bindings. |
| Diff hygiene | ok | `git diff --check` over Step 78 files passed before log write. |
| Full parity claim | warn | Still not honest: physical workers are restored, but logical operator routing is still incomplete. |

## Next Planned Step - Scientific Logical Operator Binding Restore

| Field | Value |
|---|---|
| Planned files | `harness/config/logical-operators.json`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Restore Scientific* logical operators and bindings to the bounded AutoSci workers so static runtime binding audit can validate workflow node-to-operator-to-bridge coverage. |
| Out of scope | Do not change physical worker commands, workflow topology, scheduler behavior, or coverage_status. |

### Step 79 Result

| Check | Status | Evidence |
|---|---|---|
| Scientific logical operators | ok | Added Scientific* logical operator definitions used by full/resume scientific workflows. |
| Scientific bindings | ok | Added one-to-one bindings from Scientific* logical operators to bounded `autosci-*` physical workers. |
| JSON/config | ok | `logical-operators.json` loads successfully. |
| Static runtime binding audit | ok | `audit_scientific_runtime_bindings.py --strict --json`: 28 nodes, 2 workflows, 0 issues. |
| Scheduler regression group | ok | `$research --scheduler-run` group: 6 passed, 105 deselected. |
| Full shim suite | ok | Full AutoSci shim suite: 111 passed with elevated local daemon/provider permission. |
| Feature parity inventory | warn | `/tmp/autosci-parity-step79.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| Diff hygiene | ok | `git diff --check` over Step 79 files passed before log write. |
| Full parity claim | warn | Still not honest: registry chain is now auditable, but route status still conflates semantic completeness and safety/execution policy. |

## Next Planned Step - Two-Axis Parity Status Model

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_parity_bridge.py`, `harness/evaluators/scientific/autosci_feature_parity_gate.py`, `tests/plugins/autosci/test_phase19_parity_bridge.py`, `tests/harness/evaluators/scientific/test_autosci_feature_parity_gate.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Add authoritative two-axis parity fields (`semantic_parity`, `execution_policy`, `proof_level`, `proof_refs`, `remaining_requirements`) to generated inventory and gate validation so safety-gated routes cannot be confused with missing semantic proof. |
| Out of scope | Do not upgrade any route to semantic full without E3/E4 evidence; do not change route execution behavior or side-effect policy. |

### Step 80 Result

| Check | Status | Evidence |
|---|---|---|
| Two-axis inventory fields | ok | Generated route items now include `semantic_parity`, `execution_policy`, `proof_level`, `proof_refs`, and `remaining_requirements`. |
| Gate validation | ok | Feature parity gate now validates semantic/execution/proof values, proof count consistency, and forbids semantic-full claims without sufficient proof level. |
| No overclaim | ok | No route was upgraded to semantic full; generated Step 80 inventory reports semantic `0 full / 28 partial / 0 missing`. |
| Targeted tests | ok | Parity bridge/gate tests passed: 10 passed. |
| Feature parity inventory | warn | `/tmp/autosci-parity-step80.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated; semantic 0 full, 28 partial. |
| Full AutoSci plugin suite | ok | Full plugin test directory passed with elevated local permission: 161 passed. |
| Diff hygiene | ok | `git diff --check` over Step 80 files passed before log sync. |
| Full parity claim | warn | Still not honest: semantic proof is explicit, but skill-run acceptance still needs a hard guard against top-level `completed` for partial/gated route evidence. |

## Next Planned Step - Skill Run Terminal Status Truthfulness Gate

| Field | Value |
|---|---|
| Planned files | `harness/evaluators/scientific/autosci_skill_run_gate.py`, `tests/harness/evaluators/scientific/test_autosci_skill_run_gate.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Reject `autosci_skill_run.v1` evidence that marks the top-level artifact `completed` while the route execution is only `partial` or `gated`, so compatibility evidence cannot pass as full acceptance. |
| Out of scope | Do not change shim route execution, route coverage, side-effect policy, or schema enums; existing partial/gated shim output should remain `inconclusive`. |

### Step 81 Result

| Check | Status | Evidence |
|---|---|---|
| Terminal status guard | ok | `autosci_skill_run_gate.py` now rejects top-level `completed` when `execution_status` is `partial` or `gated`. |
| Gate regression tests | ok | New `test_autosci_skill_run_gate.py`: 3 passed. |
| Existing partial/gated shim behavior | ok | Ingest partial gate and gated survey/rebuttal/poster/remaining route subsets still pass expected inconclusive/gated behavior. |
| Feature parity inventory | warn | `/tmp/autosci-parity-step81.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated; semantic 0 full, 28 partial. |
| Feature parity gate | ok | Step 81 inventory passes with non-full warnings. |
| Full AutoSci plugin suite | ok | Elevated local-bind run: 161 passed. |
| Broad evaluator suite | warn | `tests/harness/evaluators/scientific`: 89 passed, 2 failed on pre-existing lifecycle full-tail workflow alignment drift. |
| Full parity claim | warn | Still not honest: skill-run terminal truthfulness is enforced, but scheduler full lifecycle external/resume tails do not yet dispatch all configured publication/finalization nodes. |

## Next Planned Step - Scheduler Full Lifecycle Tail Alignment

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `harness/tools/run_scientific_lifecycle_smoke.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Make scheduler full external/resume paths dispatch the configured publication/finalization tail and accept explicitly supplied compile-target PDF handoff evidence without pretending an approved executor ran. |
| Out of scope | Do not mark bounded smoke dispatch as production-ready; do not execute unapproved TeX or remote side effects; do not weaken lifecycle runtime gate evidence requirements. |

### Step 82 Adjustment Plan

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_bridge.py`, `harness/tools/run_scientific_lifecycle_smoke.py`, this log, `phase15-progress-log.md`, `phase19-progress-log.md` |
| Intent | Keep the Step 82 boundary and wire supplied compile-target evidence into paper-plan handoff readiness so configured tail dispatch can proceed only after verified handoff. |
| Out of scope | Do not change test expectations, production readiness claims, TeX execution policy, or unrelated scheduler nodes. |

### Step 82 Resume Blocker Adjustment Plan

| Field | Value |
|---|---|
| Planned files | `harness/tools/run_scientific_lifecycle_smoke.py`, this log, `phase15-progress-log.md`, `phase19-progress-log.md` |
| Intent | Preserve all unresolved external unblock points during resume when earlier external evidence is missing, without dispatching downstream configured tail nodes. |
| Out of scope | Do not change human-gate behavior, node execution order, or publication/finalization dispatch semantics. |

### Step 82 Result

| Check | Status | Evidence |
|---|---|---|
| Supplied compile handoff | ok | `plan_report` now requests `_phase14_compile_handoff` when `supplied_compile_target_evidence` is present; existing supplied PDFs are recorded as verified handoff evidence without claiming a TeX executor ran. |
| Configured tail dispatch | ok | Full external lifecycle path now dispatches `report_plan`, `report_draft`, `artifact_review`, `publication_produce`, `memory_update_final`, and `workflow_evolve` in workflow-config order when required evidence is supplied. |
| Resume tail dispatch | ok | Resume path now continues through configured tail nodes after Review LLM and compile-target evidence are supplied, while preserving no-rerun fingerprints for reused nodes. |
| Resume blocker preservation | ok | Human-gate resume without external evidence records both unresolved external unblock points: `report_plan` and `publication_produce`. |
| Focused lifecycle regressions | ok | `test_scientific_lifecycle_smoke_accepts_combined_full_external_evidence`, `test_scientific_lifecycle_smoke_can_resume_external_blocked_nodes`, and `test_scientific_lifecycle_smoke_resumes_human_gate_pauses` all passed. |
| Broad scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 91 passed. |
| Full AutoSci plugin suite | ok | Elevated local-bind run: `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests -q`: 161 passed. |
| Runtime binding audit | ok | `audit_scientific_runtime_bindings.py --strict --json`: 28 nodes, 2 workflows, 0 issues. |
| Feature parity inventory | warn | `/tmp/autosci-parity-step82.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated; semantic 0 full, 28 partial. |
| Feature parity gate | ok | Step 82 inventory passes with warnings for non-full route and semantic parity status. |
| Diff hygiene | ok | `git diff --check` over Step 82 files passed after verification. |
| Full parity claim | warn | Still not honest: scheduler tail alignment is fixed, but live provider/external runtime proof and semantic-full route evidence are still missing. |

## Next Planned Step - External Runtime Proof Registry

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_parity_bridge.py`, `harness/evaluators/scientific/autosci_feature_parity_gate.py`, `tests/plugins/autosci/test_phase19_parity_bridge.py`, `tests/harness/evaluators/scientific/test_autosci_feature_parity_gate.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Add explicit external runtime proof references to parity inventory/gate output so remaining non-full routes have auditable proof requirements instead of generic partial/gated labels. |
| Out of scope | Do not mark any route full; do not fabricate provider/runtime evidence; do not execute external side effects. |

### Step 83 Result

| Check | Status | Evidence |
|---|---|---|
| Runtime proof slots | ok | Parity inventory items now include `runtime_proof_status`, `runtime_proof_refs`, and structured `proof_requirements`. |
| Requirement categories | ok | Inventory distinguishes route definition, native skill presence, tool ABI, semantic-equivalence, external runtime, approval boundary, side-effect execution, Review LLM/model, provider source, and wiki mutation proof needs where applicable. |
| Gate enforcement | ok | Feature parity gate validates runtime proof status, requirement shape/status, status counts, non-full unresolved proof, approval/provider runtime requirements, and count drift. |
| No overclaim | ok | Step 83 inventory still reports 0 full, 17 partial, 11 gated; semantic parity remains 28 partial. |
| Runtime proof state | warn | `/tmp/autosci-parity-step83.json` reports runtime proof status counts: 25 pending, 3 not_required, 0 supplied, 0 verified. |
| Targeted tests | ok | Parity bridge tests: 4 passed; feature parity gate tests: 8 passed. |
| Broad scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 93 passed. |
| Full AutoSci plugin suite | ok | Elevated local-bind run: `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests -q`: 161 passed. |
| Diff hygiene | ok | `git diff --check` over Step 83 files passed before log write. |
| Full parity claim | warn | Still not honest: proof slots are auditable, but no real external runtime proof has been supplied or verified. |

## Next Planned Step - Runtime Proof Manifest Ingestion

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_parity_bridge.py`, `harness/evaluators/scientific/autosci_feature_parity_gate.py`, `tests/plugins/autosci/test_phase19_parity_bridge.py`, `tests/harness/evaluators/scientific/test_autosci_feature_parity_gate.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Allow parity inventory to ingest explicit runtime proof manifests and mark matching route proof slots as supplied without promoting route/semantic full status. |
| Out of scope | Do not trust arbitrary manifests as verified runtime; do not mark routes full; do not execute providers or side effects. |

### Step 84 Strictness Adjustment Plan

| Field | Value |
|---|---|
| Planned files | `harness/evaluators/scientific/autosci_feature_parity_gate.py`, `tests/harness/evaluators/scientific/test_autosci_feature_parity_gate.py`, this log, `phase15-progress-log.md`, `phase19-progress-log.md` |
| Intent | Require supplied runtime proof source categories to match declared proof requirements and actually satisfy at least one requirement. |
| Out of scope | Do not change manifest ingestion semantics, route statuses, or proof verification level. |

### Step 84 Result

| Check | Status | Evidence |
|---|---|---|
| Manifest ingestion CLI | ok | `autosci_parity_bridge.py inventory/route` now accepts repeated `--runtime-proof-manifest` inputs. |
| Supplied proof attachment | ok | Matching manifest entries populate `runtime_proof_sources`, append `runtime_proof_refs`, and mark matching proof requirements `supplied`. |
| No promotion | ok | Runtime manifests only move slots to `supplied`; they do not mark runtime `verified`, route `full`, semantic `full`, or raise proof level. |
| Gate strictness | ok | Gate rejects runtime proof source skill mismatch, unknown categories, supplied status without supplied requirements, and count drift. |
| Targeted tests | ok | Phase19 bridge + feature gate tests: 15 passed after strictness adjustment. |
| Broad scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 95 passed. |
| Full AutoSci plugin suite | ok | Elevated local-bind run: `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests -q`: 162 passed. |
| Feature parity inventory | warn | `/tmp/autosci-parity-step84.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated; semantic 0 full, 28 partial; no manifest gives 25 pending runtime proof slots. |
| Feature parity gate | ok | Step 84 inventory passes with non-full warnings. |
| Diff hygiene | ok | `git diff --check` over Step 84 files passed before log write. |
| Full parity claim | warn | Still not honest: supplied manifests are accepted, but supplied proof refs are not yet audited for local artifact existence or external evidence resolvability. |

## Next Planned Step - Runtime Proof Evidence Ref Audit

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_parity_bridge.py`, `harness/evaluators/scientific/autosci_feature_parity_gate.py`, `tests/plugins/autosci/test_phase19_parity_bridge.py`, `tests/harness/evaluators/scientific/test_autosci_feature_parity_gate.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Audit runtime proof evidence refs so path-like local refs must resolve and missing local refs cannot satisfy supplied proof requirements. |
| Out of scope | Do not verify external provider ids as live; do not mark supplied proofs verified; do not execute external side effects. |

### Step 85 Result

| Check | Status | Evidence |
|---|---|---|
| Evidence ref audit | ok | Runtime proof manifest entries now include `evidence_ref_statuses`; path-like refs are resolved under `HARNESS_DIR` and must exist. |
| Blocked bad proof | ok | Missing local evidence refs mark the source `blocked`, keep `runtime_proof_status` pending, and do not add proof refs or supplied requirement status. |
| Gate enforcement | ok | Feature parity gate rejects blocked runtime proof sources and supplied sources with unresolved local refs. |
| Valid manifest path | ok | Manifest test creates a local runtime artifact and gates successfully while keeping route/semantic full counts at 0. |
| Invalid manifest path | ok | Missing-local-ref manifest test confirms gate failure with `blocked by unresolved evidence refs`. |
| Targeted tests | ok | Phase19 bridge tests: 6 passed; feature parity gate tests: 10 passed. |
| Broad scientific evaluator suite | ok | `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q`: 95 passed. |
| Full AutoSci plugin suite | ok | Elevated local-bind run: `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests -q`: 163 passed. |
| Feature parity inventory | warn | `/tmp/autosci-parity-step85.json`: 28 routed, 0 missing, 0 full, 17 partial, 11 gated; semantic 0 full, 28 partial. |
| Feature parity gate | ok | Step 85 inventory passes with non-full warnings. |
| Diff hygiene | ok | `git diff --check` over Step 85 files passed before log write. |
| Full parity claim | warn | Still not honest: runtime proof references are audited, but no live provider proof has been run or verified. |

## Next Planned Step - Runtime Proof CLI Summary Visibility

| Field | Value |
|---|---|
| Planned files | `harness/plugins/autosci/bin/autosci_parity_bridge.py`, `tests/plugins/autosci/test_phase19_parity_bridge.py`, `docs/integrations/autosci/native-lifecycle-continuation-log.md`, `docs/integrations/autosci/phase15-progress-log.md`, `docs/integrations/autosci/phase19-progress-log.md` |
| Intent | Include runtime proof status counts in parity bridge CLI summaries so pending/supplied/verified proof state is visible without opening the JSON artifact. |
| Out of scope | Do not change inventory payload semantics, gate rules, route status, or proof verification. |

### Step 86 Result

| Check | Status | Evidence |
|---|---|---|
| CLI visibility | ok | `autosci_parity_bridge.py inventory` and `route` stdout summaries now include `runtime_proof_status_counts`. |
| Targeted tests | ok | Phase19 bridge tests: 6 passed. |
| Inventory summary | ok | `/tmp/autosci-parity-step86.json` CLI output now shows runtime proof counts: 25 pending, 3 not_required, 0 supplied, 0 verified. |
| Feature parity gate | ok | Step 86 inventory passes gate with non-full warnings. |
| Diff hygiene | ok | `git diff --check` over Step 86 files passed before log write. |
| Full parity claim | warn | Still not honest: CLI now exposes pending proof counts, but full parity requires actual supplied/verified runtime evidence. |

## Next Required Blocker - Live Runtime Proof Collection

| Field | Value |
|---|---|
| Required input | Real runtime proof manifests or approved provider/runtime executions for the 25 pending runtime-proof routes. |
| Current hard limit | No route can honestly become full/semantic-full while runtime proof status remains pending and proof level remains E2. |
| Safe next action | Run approved live/provider evidence collection or supply audited `autosci_runtime_proof_manifest.v1` files with existing evidence artifacts. |
| Out of scope for local-only fixes | Do not fabricate provider evidence, mark supplied proofs verified, or promote routes to full based on fixture/smoke results. |
