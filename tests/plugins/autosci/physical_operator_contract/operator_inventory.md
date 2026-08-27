# Physical operator inventory for the 25 RequirementIR workloads

Snapshot basis: `ai4research-main` at `285837bbde7a66469544255db3d291e9c1d8a61d` on 2026-08-26.

## Scope and interpretation

The production research resolver composes 33 physical bindings from
`harness.plugins.autosci.operators.scientific_lifecycle.registry:production_bindings`.
Every binding accepts `research_node_request.v1`, returns
`research_node_result.v1`, and is selected by exact `physical_operator.operator_id`.
The resolver has no fallback selection.

The unified registry declares identity, implementation identity, version and
family, but does **not** declare a capability list. Capabilities are supplied
and enforced per request through `physical_operator.capabilities`,
`authorization.approved_capabilities`, read scope and write scope. This is
recorded as `request-bound (registry gap)` below rather than inventing registry
metadata.

Case mappings are minimum direct workload needs inferred from the accepted
RequirementIR objectives, not a proposed PlanIR:

- R01–R10: research and literature review.
- D11–D15: internet data collection and source reconciliation.
- E16–E20: experiment design or execution.
- C21–C25: child-oriented direct answers or creative output.

The five child cases require a generic direct-answer generator, but the unified
research resolver has no such physical binding. Provider-backed generic model
slots in `harness/config/physical-operators.json` require external runtimes or
credentials and were not invoked.

## Research synthesis family (8 bindings)

Common implementation boundary:
`harness.plugins.autosci.operators.research_synthesis.registry:execute_operator`.
Declared capabilities for every row: `request-bound (registry gap)`.

| Physical operator ID | Implementation operator / production entrypoint | Accepted typed input | Expected operator-owned artifacts | External dependency | Local testability | Cases requiring it | Coverage and gap |
|---|---|---|---|---|---|---|---|
| `seed_fetch_operator` | `research-synthesis-seed_fetch`; `research_synthesis.seed_fetch:execute` | task contract plus URL/topic/local file seeds | `seed_snapshot.json` (`research_synthesis.seed_snapshot.v1`) | `fetch_url` for URLs; optional `extract_pdf_text`; local files otherwise | Yes with fake fetcher/local file | R01–R10, D11–D15; conditional for E16–E20 | Existing family tests; not in first direct matrix |
| `source_discovery_operator` | `research-synthesis-source_discovery`; `research_synthesis.source_discovery:execute` | seed snapshot; acquisition mode; supplied candidates or query contract | `source_discovery.json` (`research_synthesis.source_discovery.v1`) | `discover_sources` for live/legacy discovery; none for source pack | Yes with fake provider/source pack | R01–R10, D11–D15; conditional E17/E20 | **Direct matrix PASS**; live provider not tested |
| `source_validation_operator` | `research-synthesis-source_validation`; `research_synthesis.source_validation:execute` | source-discovery artifact or candidate list and task query | `source_validation.json` (`research_synthesis.source_validation.v1`) | None | Yes | R01–R10, D11–D15; conditional E17/E20 | **Direct matrix PASS** |
| `evidence_synthesis_operator` | `research-synthesis-evidence_synthesis`; `research_synthesis.evidence_synthesis:execute` | validated sources, seed snapshot, task contract | `evidence_synthesis.json` (`research_synthesis.evidence_synthesis.v1`) | `model_generate` | Yes with fake model | R01–R10, D11–D15; conditional E17/E20 | **Direct matrix PASS**; real model quality not tested |
| `report_draft_operator` | `research-synthesis-report_draft`; `research_synthesis.report_draft:execute` | evidence synthesis and deliverable contract | `report_draft.json`, `report.md` | `model_generate` | Yes with fake model | R01–R10, D11–D15; conditional E16–E20 | **Direct matrix PASS**; real model quality not tested |
| `independent_review_operator` | `research-synthesis-independent_review`; `research_synthesis.independent_review:execute` | report draft, synthesis and validation lineage | `independent_review.json` (`research_synthesis.independent_review.v1`) | `review_model_generate` | Yes with fake review model | R01–R10, D11–D15; conditional E16–E20 | Existing family tests; not in first direct matrix |
| `report_revision_operator` | `research-synthesis-report_revision`; `research_synthesis.report_revision:execute` | draft, review, validation and synthesis artifacts | `report_revision.json`, revised `report.md` | `model_generate` and optional `review_model_generate` | Yes with fakes | Conditional R01–R10/D11–D15/E16–E20 when review rejects | Existing family tests; not in first direct matrix |
| `final_acceptance_operator` | `research-synthesis-final_acceptance`; `research_synthesis.final_acceptance:execute` | hash-bound draft/review/synthesis/validation artifacts and task contract | `final_acceptance.json` (`research_synthesis.final_acceptance.v1`) | None | Yes | R01–R10, D11–D15; conditional E16–E20 | Existing family tests; not in first direct matrix; does not own `gate_ledger.json` or `evidence_ir.json` |

## Scientific evidence family (12 bindings)

Common production entrypoint:
`harness.plugins.autosci.operators.scientific_lifecycle.evidence.registry:execute_<node_id>`.
Declared capabilities for every row: `request-bound (registry gap)`.

| Physical operator ID | Implementation operator | Accepted typed input | Expected operator-owned artifact | External dependency | Local testability | Cases requiring it | Coverage and gap |
|---|---|---|---|---|---|---|---|
| `evidence_import_worker` | `autosci-evidence-import` | task-contract `supplied_evidence` refs in read scope | `research_evidence_import.v1.json` | Local filesystem | Yes | Conditional R01–R10/D11–D15/E16–E20 when evidence is supplied | Existing positive/missing/idempotence suite; not in first matrix |
| `literature_discover_worker` | `autosci-evidence-literature-discover` | query/topic/anchors/venue/mode | `literature_discovery.v1.json` | injected `discover_literature` or backend; network only when authorized | Yes; offline boundary and explicitly authorized live provider tested | R01–R10; conditional E17/E20 | **Direct live-provider PASS** using the real J05 anchors: five traceable Semantic Scholar candidates, negative-ID exclusion, hash-verified artifact, and no synthetic markers; offline `awaiting_external` behavior also covered. Relevance quality still requires human review |
| `paper_ingest_worker` | `autosci-evidence-paper-ingest` | scoped paper path or URL plus metadata | `research_paper.v1.json` | parser; network fetch only for authorized URL | Yes with local paper | Conditional R01–R10/E17/E20 when paper inputs are selected | **Direct matrix PASS** with checked-in Markdown fixture, content hash, source registration, missing-input failure, and replay |
| `material_ingest_worker` | `autosci-evidence-material-ingest` | scoped material path or URL plus metadata | `research_material.v1.json` carrying `research_paper.v1` | parser; optional authorized network | Yes with local material | Conditional all evidence workloads | **Direct matrix PASS** with checked-in Markdown fixture, parsed sections, source hash, registration boundary, and missing-input failure |
| `paper_analyze_worker` | `autosci-evidence-paper-analyze` | `research_paper.v1` | `research_paper_analysis.v1.json` | None | Yes | Conditional R01–R10/E17/E20 | **Direct matrix PASS** consuming the real `material_ingest_worker` artifact; missing-input failure also covered |
| `content_analyze_worker` | `autosci-evidence-content-analyze` | `research_paper.v1` content view | `research_content_analysis.v1.json` | None | Yes | Conditional R01–R10/D11–D15 | **Direct matrix PASS** consuming the real `material_ingest_worker` artifact with exact source highlights; missing-input failure also covered |
| `memory_update_initial_worker` | `autosci-evidence-memory-update-initial` | paper/analysis/claim/method evidence | `initial_research_memory_update.v1.json` | None | Yes | Not required by the 25 user outcomes; optional memory side effect | Existing evidence suite; not in first matrix |
| `memory_update_final_worker` | `autosci-evidence-memory-update-final` | final lifecycle evidence | `final_research_memory_update.v1.json` | None | Yes | Not required by the 25 user outcomes; optional memory side effect | Existing evidence suite; not in first matrix; grouped implementation with initial update |
| `graph_update_worker` | `autosci-evidence-graph-update` | `research_memory_update.v1` | `research_graph_update.v1.json` | None | Yes | Not required by the 25 user outcomes; optional memory graph side effect | Existing evidence suite; not in first matrix |
| `claim_extract_worker` | `autosci-evidence-claim-extract` | `research_paper.v1` | `research_claims.v1.json` | None | Yes | Conditional R01–R10/E17/E20 | **Direct matrix PASS** consuming the real `material_ingest_worker` artifact; exact source-anchored unverified claim and missing-input failure covered |
| `method_extract_worker` | `autosci-evidence-method-extract` | `research_paper.v1` | `research_method.v1.json` | None | Yes | Conditional R01–R10/E16–E20 when method evidence is required | **Direct matrix PASS** consuming the real `material_ingest_worker` artifact; exact method text, source anchor, extraction basis, and missing-input failure covered |
| `code_evidence_map_worker` | `autosci-evidence-code-evidence-map` | claims plus scoped repository/code path | `code_evidence_map.v1.json` | Local repository scan | Yes | Conditional E16/E18/E19 when code evidence is part of execution | Existing evidence suite; not in first matrix |

## Scientific action and delivery family (13 bindings)

Common implementation boundary:
`harness.plugins.autosci.operators.scientific_lifecycle.action.registry:execute_operator`.
Declared capabilities for every row: `request-bound (registry gap)`; experiment
execution additionally requires explicit `execute_experiment` authorization and
hash-bound approval evidence.

| Physical operator ID | Implementation operator | Accepted typed input | Expected operator-owned artifacts | External dependency | Local testability | Cases requiring it | Coverage and gap |
|---|---|---|---|---|---|---|---|
| `idea_generate_worker` | `autosci-idea-generation-physical` | research context/evidence | `idea_candidate.v1.json` | `idea_generator` | Yes with fake model | Not required; experiment hypotheses are already stated in E16–E20 | Existing action chain; not in first matrix |
| `idea_evaluate_worker` | `autosci-idea-evaluation-physical` | idea candidates | `idea_evaluation.v1.json` | None | Yes | Not required by minimum E16–E20 outcomes | Existing action chain; not in first matrix |
| `experiment_design_worker` | `autosci-experiment-design-physical` | idea candidate/evaluation plus sandbox and metrics | `experiment_plan.v1.json` | None | Yes | E16–E20 | **Direct matrix PASS**, including deterministic replay |
| `experiment_approval_gate_worker` | `autosci-experiment-approval-gate-physical` | experiment plan plus authorization | `experiment_approval.v1.json` | Human approval reference for execution | Structural path locally testable | E16–E20 before execution | Existing approval tests; not in first matrix; worker did not fabricate approval |
| `experiment_run_worker` | `autosci-bounded-experiment-run-physical` | hash-bound plan and approval; exact sandbox/write scope | `experiment_result.v1.json` | injected `experiment_executor` | Yes with deterministic fake executor; real platform external | E16–E20 | **Direct matrix PASS**, including deterministic replay; real experiment platform not tested |
| `experiment_monitor_worker` | `autosci-experiment-monitor-physical` | plan/result evidence | `experiment_status.v1.json` | optional `experiment_status_provider` | Yes with fake provider/local result | Conditional E16–E20 for asynchronous execution | Existing action chain; not in first matrix |
| `claim_verify_worker` | `autosci-claim-verification-physical` | claims plus experiment/code evidence | `claim_verdict.v1.json` | None | Yes | R01–R10 and E16–E20 when claims are published | Existing action chain; not in first matrix |
| `report_plan_worker` | `autosci-report-planning-physical` | verified claims and task contract | `scientific_report_plan.v1.json` | None | Yes | R01–R10/D11–D15/E16–E20 when lifecycle report route is used | Existing action chain; not in first matrix |
| `report_draft_worker` | `autosci-report-drafting-physical` | report plan, claims, methods, results | `scientific_report.v1.json` plus Markdown | None | Yes | R01–R10/D11–D15/E16–E20 when lifecycle report route is used | Existing action chain; not in first matrix; distinct from tested synthesis report adapter |
| `artifact_review_worker` | `autosci-artifact-review-physical` | report/publication artifact | `artifact_review.v1.json` | None (local structural review) | Yes | Conditional R01–R10/D11–D15/E16–E20 | Existing action chain; not in first matrix; local review is not independent peer review |
| `publication_produce_worker` | `autosci-publication-production-physical` | accepted report and review | `publication_bundle.v1.json` plus compiled files | Local compiler/filesystem | Yes | Conditional R01–R10/D11–D15/E16–E20 when publication is requested | Existing action chain; not in first matrix |
| `final_evaluation_worker` | `autosci-final-publication-evaluation-physical` | publication, review, source, method and verdict evidence | `research_final_evaluation.v1.json` | None | Yes | Conditional R01–R10/D11–D15/E16–E20 | Existing action chain; not in first matrix; must not author `evidence_ir.json` or `gate_ledger.json` |
| `workflow_evolve_worker` | `autosci-workflow-evolution-proposal-physical` | reviewed run evidence and proposed change | `workflow_evolution.v1.json` | None | Yes | Not required by the 25 user outcomes | Existing action chain; not in first matrix |

## First-scope result

Direct production-boundary coverage was added for six operators:
`source_discovery_operator`, `source_validation_operator`,
`evidence_synthesis_operator`, `report_draft_operator`,
`experiment_design_worker`, and `experiment_run_worker`.

For all six, the worker-harness matrix covers success, structurally invalid
request, missing required input, timeout, transient failure, permanent failure,
unsupported request, malformed result, artifact identity/hashes, and forbidden
artifact ownership. Provider-specific malformed responses are additionally
exercised for the four provider-backed operators. Deterministic byte replay is
asserted for the two action operators that accept a fixed evidence timestamp.

No live provider, generic model slot, external experiment runtime, credential,
Planner contract, Scheduler adapter, PlanIR fixture, evaluator ledger, or gate
artifact was used or modified.
