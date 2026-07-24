"""Build the Phase 22 executable Level-2 feature matrix.

The generated matrix is self-contained: it copies the contract boundary used
for classification and binds every implemented L2 to one feature-relevant
executable probe. Code-absent L2s have no probe and remain explicitly blocked.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ANNOTATION_FILES = (
    "workflow_annotations.json",
    "foundation_annotations.json",
    "vertical_annotations.json",
)

BLOCKED_FEATURES = {
    "Qualified Channel Signal Intake",
    "Strategic Opportunity Screening",
    "Hypothesis Pool & Mechanism Formation",
    "Model Policies and Weights (SFT / LoRA / DPO / GRPO / Agent RL)",
    "Dataset Graph Management",
    "Policy Graph Management",
    "Model Construction",
    "Prototype Assembly",
    "Account Registration",
    "Discord",
}

PROBES = {
    "wf_intent_capture": {
        "runner": "pytest",
        "target": "harness/tests/test_intent_gateway.py::test_capture_writes_raw_rewritten_ir_and_trace",
        "rationale": "Executes request capture and verifies raw, normalized, IR, and trace artifacts.",
    },
    "wf_paper_prepare": {
        "runner": "pytest",
        "target": "harness/plugins/autosci/tests/test_paper_prepare.py::test_prepare_pdf_prefers_arxiv_source_when_recovered",
        "rationale": "Executes current user-supplied paper material preparation.",
    },
    "wf_intent_bind": {
        "runner": "pytest",
        "target": "harness/tests/test_intent_gateway.py::test_bind_copies_intent_artifacts_to_sprint",
        "rationale": "Executes sprint/workspace context binding for intake artifacts.",
    },
    "wf_intent_consume": {
        "runner": "pytest",
        "target": "harness/tests/test_intent_consumer.py::test_consumer_compiles_rawintent_to_sprint_package",
        "rationale": "Executes normalized intake consumption and deterministic package production.",
    },
    "wf_intake_qualification": {
        "runner": "pytest",
        "target": "harness/tests/livework/test_intake_state_machine.py::TestHappyPath::test_full_happy_path",
        "rationale": "Executes qualification state transitions through dispatch-ready intake.",
    },
    "wf_pm_build": {
        "runner": "pytest",
        "target": "harness/tests/test_codex_pm_router.py::test_build_pm_intake_emits_capsule_plan_for_standard_request",
        "rationale": "Executes requirement interpretation, scoping, assumptions, priority, and acceptance compilation.",
    },
    "wf_pm_reject": {
        "runner": "pytest",
        "target": "harness/tests/test_codex_pm_router.py::test_validate_compiled_package_rejects_raw_metadata_pollution",
        "rationale": "Executes compiled-requirement validation and explicit rejection behavior.",
    },
    "wf_lit_strategy": {
        "runner": "pytest",
        "target": "harness/plugins/autosci/tests/test_literature_discover.py::test_from_wiki_uses_recent_arxiv_anchors_and_honors_limit",
        "rationale": "Executes bounded search formation from current wiki and literature anchors.",
    },
    "wf_lit_provider": {
        "runner": "pytest",
        "target": "harness/plugins/autosci/tests/test_literature_discover.py::test_topic_discovery_retries_semantic_scholar_429_then_returns_candidates",
        "rationale": "Executes provider discovery, retry handling, candidate qualification, and deduplication.",
    },
    "wf_grounded": {
        "runner": "pytest",
        "target": "harness/tests/scenarios/test_p7_grounded_synthesis.py::test_fixed_source_packs_compile_to_a_passing_topic_general_report",
        "rationale": "Executes signal extraction, evidence linking, organization, gap analysis, and grounded synthesis.",
    },
    "wf_ideate": {
        "runner": "pytest",
        "target": "harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_runs_ideate_from_wiki_and_discovery_sources",
        "rationale": "Executes current multi-source idea generation and idea evidence production.",
    },
    "wf_ideate_dedup": {
        "runner": "pytest",
        "target": "harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_ideate_active_idea_dedup_filters_duplicate",
        "rationale": "Executes candidate consolidation, duplicate filtering, and bounded selection.",
    },
    "wf_novelty": {
        "runner": "pytest",
        "target": "harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_runs_novelty_target_with_local_sources",
        "rationale": "Executes the current technical novelty/opportunity screening surface.",
    },
    "wf_claim_convert": {
        "runner": "pytest",
        "target": "harness/plugins/autosci/tests/test_conversion_to_solar_evidence.py::test_raw_claims_convert_to_unverified_solar_claims",
        "rationale": "Executes research-claim formation into the current evidence schema.",
    },
    "wf_phase4_convert": {
        "runner": "pytest",
        "target": "harness/plugins/autosci/tests/test_conversion_to_solar_evidence.py::test_core_phase4_converters_emit_expected_schema_names",
        "rationale": "Executes claim/method/experiment-plan modeling and schema boundaries.",
    },
    "wf_exp_design": {
        "runner": "pytest",
        "target": "harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_exp_design_marks_execution_ready_with_approval_preflight",
        "rationale": "Executes verification-ready experiment/POC design and approval preflight.",
    },
    "wf_poc_plan": {
        "runner": "pytest",
        "target": "harness/tests/test_autosci_intake_contract.py::test_autosci_contract_task_graph_selects_autosci_physical_workers",
        "rationale": "Executes POC environment planning and operator preparation.",
    },
    "wf_exp_run": {
        "runner": "pytest",
        "target": "harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_exp_pilot_run_parity_demo_auto_executes_local_command",
        "rationale": "Executes current local POC construction, integration, validation, and evidence handoff path.",
    },
    "wf_core_benchmark": {
        "runner": "node_ts",
        "target": "tests/workflow/benchmarking/test_core_benchmark_behavior.mjs",
        "rationale": "Executes core benchmark metadata framing and measurement summarization.",
    },
    "wf_benchmark_registry": {
        "runner": "pytest",
        "target": "harness/tests/benchmark/test_benchmark_registry.py::test_register_then_get_roundtrip",
        "rationale": "Executes benchmark asset registration and retrieval.",
    },
    "wf_benchmark_execution": {
        "runner": "pytest",
        "target": "harness/tests/benchmark/test_terminal_bench_adapter.py::test_empty_missing_prereqs_allows_dry_run_ok",
        "rationale": "Executes the current Terminal-Bench dry-run path and asserts an executable-ready verdict.",
    },
    "wf_benchmark_report": {
        "runner": "pytest",
        "target": "harness/tests/benchmark/test_benchmark_report_schema.py::test_run_json_contains_all_required_fields",
        "rationale": "Executes benchmark result packaging and validates required run evidence.",
    },
    "wf_evaluation": {
        "runner": "pytest",
        "target": "harness/tests/research_unit/test_evaluator.py::test_evaluate_artifacts_passes_complete_artifact_set",
        "rationale": "Executes evaluation assembly, completeness checks, and final verdict production.",
    },
    "wf_artifact_review": {
        "runner": "pytest",
        "target": "harness/tests/evaluators/scientific/test_artifact_review_gate.py::test_artifact_review_gate_accepts_local_surrogate_with_disclosure",
        "rationale": "Executes scientific/reasoning artifact review with explicit limitations.",
    },
    "wf_claim_gate": {
        "runner": "pytest",
        "target": "harness/tests/evaluators/scientific/test_claim_verdict_gate.py::test_claim_verdict_gate_accepts_evidence_linked_verdict",
        "rationale": "Executes evidence-linked claim and acceptance comparison.",
    },
    "wf_status_next": {
        "runner": "pytest",
        "target": "harness/tests/research_survey/test_status_next.py::test_status_next_done_when_finalize_passed",
        "rationale": "Executes refinement/follow-up state determination after evaluation.",
    },
    "wf_paper_draft": {
        "runner": "pytest",
        "target": "harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_paper_draft_writes_latex_source",
        "rationale": "Executes user-facing deliverable generation.",
    },
    "wf_publication": {
        "runner": "pytest",
        "target": "harness/plugins/autosci/tests/test_autosci_skill_shim.py::test_autosci_skill_shim_runs_survey_rebuttal_and_poster_native_sidecars",
        "rationale": "Executes delivery packaging, reusable sidecars, and lifecycle handoff evidence.",
    },
    "fn_capsule_def": {
        "runner": "pytest",
        "target": "harness/tests/test_capability_capsules.py::test_validate_sample_capability_capsule_manifest_has_no_errors",
        "rationale": "Executes capsule definition normalization and semantic validation.",
    },
    "fn_capsule_registry": {
        "runner": "pytest",
        "target": "harness/tests/test_capability_capsules.py::test_registry_loader_and_query_skip_non_stable_by_default",
        "rationale": "Executes capsule registry governance and stable-only discovery.",
    },
    "fn_capsule_select": {
        "runner": "pytest",
        "target": "harness/tests/test_capability_capsules.py::test_default_capability_plan_for_logical_operator_maps_requirement_nodes",
        "rationale": "Executes capability discovery and logical-task selection.",
    },
    "fn_capsule_invoke": {
        "runner": "pytest",
        "target": "harness/tests/test_capability_capsules.py::test_resolution_gate_attaches_guard_and_resource_capsules",
        "rationale": "Executes capsule composition with guard and resource attachments.",
    },
    "fn_gepa_promote": {
        "runner": "pytest",
        "target": "harness/tests/integrations/gepa_optimizer/test_promote.py::test_promote_writes_target_and_backup",
        "rationale": "Executes current artifact evolution, promotion, and backup behavior.",
    },
    "fn_logical_schema": {
        "runner": "pytest",
        "target": "harness/tests/test_logical_operator_schema.py",
        "rationale": "Executes logical operator definition, binding, and registry schema tests.",
    },
    "fn_verification_gate": {
        "runner": "pytest",
        "target": "harness/tests/runtime/test_verification_gate.py::test_reject_code_task_without_test",
        "rationale": "Executes admission/governance and engineering-correctness rejection.",
    },
    "fn_operator_select": {
        "runner": "pytest",
        "target": "harness/tests/test_physical_operator_logical_selector.py::test_task_type_matching",
        "rationale": "Executes logical-to-physical operator matching and selection.",
    },
    "fn_operator_runtime": {
        "runner": "pytest",
        "target": "harness/tests/runtime/test_operator_runtime.py::test_operator_lease_lifecycle",
        "rationale": "Executes physical operator fleet lease lifecycle management.",
    },
    "fn_operator_score": {
        "runner": "pytest",
        "target": "harness/tests/runtime/test_operator_score.py::test_rank_actors",
        "rationale": "Executes operator capability scoring and ranking.",
    },
    "fn_workflow_schema": {
        "runner": "pytest",
        "target": "harness/tests/workflow_contract/test_contract_schema.py::test_all_shipped_contracts_schema_valid",
        "rationale": "Executes contract/schema conformance across shipped workflow contracts.",
    },
    "fn_benchmark_report": {
        "runner": "pytest",
        "target": "harness/tests/benchmark/test_benchmark_report_schema.py::test_run_json_contains_all_required_fields",
        "rationale": "Executes benchmark/performance result and evidence evaluation.",
    },
    "fn_repo_hygiene": {
        "runner": "bash",
        "target": "./tests/test-repo-hygiene.sh",
        "rationale": "Executes security/privacy/repository hygiene positive and negative controls.",
    },
    "fn_evaluator": {
        "runner": "pytest",
        "target": "harness/tests/research_unit/test_evaluator.py::test_evaluate_artifacts_passes_complete_artifact_set",
        "rationale": "Executes evidence, factuality, and scientific-validity evaluation.",
    },
    "fn_human_review": {
        "runner": "pytest",
        "target": "harness/tests/workflow_contract/test_instantiate.py::test_on_human_review_policy_carried_per_node",
        "rationale": "Executes lifecycle and human-review policy propagation.",
    },
    "fn_model_registry": {
        "runner": "pytest",
        "target": "harness/tests/test_model_registry_codex_aliases.py::test_codex_aliases_expose_provider_and_model_key",
        "rationale": "Executes foundational model registry alias resolution.",
    },
    "fn_model_routing": {
        "runner": "pytest",
        "target": "harness/tests/graph/test_graph_scheduler_model_matching.py::test_sonnet_preferred_matches_anthropic_sonnet_alias_before_glm",
        "rationale": "Executes model matching, preference, and routing selection.",
    },
    "fn_model_audit": {
        "runner": "pytest",
        "target": "harness/tests/runtime/test_model_call_runtime.py",
        "rationale": "Executes model-call event recording and usage audit behavior.",
    },
    "fn_graph_scheduler": {
        "runner": "pytest",
        "target": "harness/tests/graph/test_graph_scheduler_external_deps.py::test_external_depends_on_allows_ready_after_upstream_passed",
        "rationale": "Executes DAG readiness and dependency-aware scheduling.",
    },
    "fn_context_store": {
        "runner": "pytest",
        "target": "harness/tests/test_context_store_runtime.py::test_save_and_load",
        "rationale": "Executes persistent context/memory storage and retrieval.",
    },
    "fn_evidence_ledger": {
        "runner": "pytest",
        "target": "harness/tests/test_evidence_ledger.py::test_write_run_entry",
        "rationale": "Executes trace/evidence graph event persistence.",
    },
    "fn_bun_data": {
        "runner": "bun",
        "target": "tests/foundation/data_foundations/test_bun_data_foundation_behavior.test.ts",
        "rationale": "Executes Bun-backed ontology, semantic-memory, and SMI code-index behavior.",
    },
    "fn_workflow_instantiate": {
        "runner": "pytest",
        "target": "harness/tests/workflow_contract/test_instantiate.py::test_instantiation_byte_identical_twice",
        "rationale": "Executes deterministic workflow graph construction and management.",
    },
    "fn_taskgraph_io": {
        "runner": "pytest",
        "target": "harness/tests/graph/test_task_graph_io.py::test_save_and_load_spec",
        "rationale": "Executes TaskGraph persistence and lifecycle round-trip.",
    },
    "fn_task_lifecycle": {
        "runner": "pytest",
        "target": "harness/tests/runtime/test_task_lifecycle.py::test_exact_durable_result_converges_submitted_status",
        "rationale": "Executes run lifecycle convergence and recovery state handling.",
    },
    "fn_agent_bus": {
        "runner": "node_ts",
        "target": "tests/foundation/harness_core/test_agent_bus_behavior.mjs",
        "rationale": "Executes message bus queueing, validation, and delivery.",
    },
    "fn_actor_lease": {
        "runner": "pytest",
        "target": "harness/tests/runtime/test_actor_lease.py::test_acquire_and_read",
        "rationale": "Executes admission, lease acquisition, and concurrency state.",
    },
    "fn_actor_runtime": {
        "runner": "pytest",
        "target": "harness/tests/runtime/test_actor_runtime.py::test_submit_returns_lease_and_paths",
        "rationale": "Executes main-loop task submission and runtime supervision envelope creation.",
    },
    "fn_intent_classify": {
        "runner": "pytest",
        "target": "harness/tests/test_intent_gateway.py::test_general_user_research_requests_get_research_lane_and_roles",
        "rationale": "Executes intent classification and compilation-variant selection.",
    },
    "fn_plan_validator": {
        "runner": "pytest",
        "target": "harness/tests/workflow_contract/test_plan_validator.py::test_valid_dag_has_no_graph_structure_errors",
        "rationale": "Executes compiled constraints and TaskGraph feasibility validation.",
    },
    "fn_intake_contract": {
        "runner": "pytest",
        "target": "harness/tests/test_autosci_intake_contract.py::test_autosci_contract_task_graph_selects_autosci_physical_workers",
        "rationale": "Executes task contract and acceptance compilation.",
    },
    "fn_compiled_planner": {
        "runner": "pytest",
        "target": "harness/tests/test_compiled_sprint_planner.py::test_generate_planner_artifacts_for_compiled_sprint",
        "rationale": "Executes task contract decomposition into planner artifacts.",
    },
    "fn_apo_plan": {
        "runner": "pytest",
        "target": "harness/tests/test_apo_plan_compiler.py::test_build_capsule_plan_node_inserts_guard_resource_and_verifier",
        "rationale": "Executes plan/build contract interpretation and guard/resource/verifier assembly.",
    },
    "fn_build_prepare": {
        "runner": "pytest",
        "target": "tests/vertical/installer_cli_webapp/test_cli_provider_onboarding_behavior.py::test_cli_doctor_reports_selected_codex_runtime",
        "rationale": "Executes installer/CLI preparation and provider configuration flow in an isolated portable home.",
    },
    "fn_code_construct": {
        "runner": "pytest",
        "target": "harness/tests/runtime/test_codex_operator_contract.py::test_multi_task_operator_envelope_carries_work_dir_and_graph_path",
        "rationale": "Executes the current code/operator construction envelope boundary.",
    },
    "fn_release_contract": {
        "runner": "bash",
        "target": "./tests/test-release-checklist.sh",
        "rationale": "Executes runtime deliverable/release packaging contract checks.",
    },
    "vt_status_scoping": {
        "runner": "pytest",
        "target": "harness/tests/test_status_server_session_scoping.py::test_events_for_request_filters_global_events_for_requested_sprint",
        "rationale": "Executes workflow status and trace scoping for visibility.",
    },
    "vt_status_usage": {
        "runner": "pytest",
        "target": "harness/tests/test_status_server_usage_runtime.py::test_codex_runtime_does_not_project_claude_quota_rows",
        "rationale": "Executes runtime/resource usage projection by active provider runtime.",
    },
    "vt_windows_app": {
        "runner": "node",
        "target": "desktop/src/runtime-detect.test.js",
        "rationale": "Executes Windows/WSL desktop runtime detection.",
    },
    "vt_macos_app": {
        "runner": "node",
        "target": "desktop/bootstrap-contract.test.js",
        "rationale": "Executes desktop bootstrap and macOS packaging contract tests.",
    },
    "vt_cli": {
        "runner": "pytest",
        "target": "tests/vertical/installer_cli_webapp/test_cli_provider_onboarding_behavior.py::test_cli_doctor_reports_selected_codex_runtime",
        "rationale": "Executes the shipped CLI provider/configuration onboarding path in an isolated portable home.",
    },
    "vt_status_dashboard": {
        "runner": "python_script",
        "target": "harness/tests/test-status-server-p0-dashboard.py",
        "rationale": "Executes the legacy self-running web/status dashboard, settings payload, and rendered UI surface.",
    },
    "vt_gui": {
        "runner": "node",
        "target": "desktop/frontend-scenarios.test.js",
        "rationale": "Executes desktop GUI frontend scenarios.",
    },
    "vt_tui": {
        "runner": "pytest",
        "target": "harness/tests/integration/test_tui_pane_e2e.py",
        "rationale": "Executes TUI pane state, recovery, and reinjection scenarios.",
    },
    "vt_auth": {
        "runner": "pytest",
        "target": "harness/tests/supervision/test_run_preflight.py::test_auth_absent_fails_closed",
        "rationale": "Executes authentication/session preflight fail-closed behavior.",
    },
    "vt_user_settings": {
        "runner": "pytest",
        "target": "harness/tests/config/test_spine_registry.py::test_user_config_defaults_are_neutral",
        "rationale": "Executes current user configuration defaults and settings boundary.",
    },
    "vt_privacy": {
        "runner": "bash",
        "target": "./tests/test-repo-hygiene.sh",
        "rationale": "Executes privacy/secret/repository hygiene controls.",
    },
    "vt_wechat": {
        "runner": "bash",
        "target": "./harness/tests/test-apple-notes-ingest.sh",
        "rationale": "Executes the current WeChat-via-Apple-Notes ingestion surface.",
    },
    "vt_tmux": {
        "runner": "pytest",
        "target": "harness/tests/test_tmux_notification_bridge.py::test_notify_tmux_state_emits_tmux_commands",
        "rationale": "Executes TMUX notification/state command emission.",
    },
    "vt_cost_budget": {
        "runner": "pytest",
        "target": "harness/tests/integrations/gepa_optimizer/test_budgets.py::TestBudget::test_valid_budget",
        "rationale": "Executes budget validation for cost/evaluation/wall-time controls.",
    },
    "vt_cluster": {
        "runner": "node_ts",
        "target": "tests/vertical/system_configurations/test_hive_cluster_behavior.mjs",
        "rationale": "Executes Hive node registration, capability discovery, and cluster matching.",
    },
}


PROBE_FEATURES = {
    "wf_intent_capture": ["Request Capture", "Intake Provenance Registration"],
    "wf_paper_prepare": ["User-Supplied Material Import"],
    "wf_intent_bind": ["Intake Context Binding"],
    "wf_intent_consume": ["Real-Time Intake Deduplication & Cleaning"],
    "wf_intake_qualification": ["Intake Qualification"],
    "wf_pm_build": ["Intent Interpretation", "Context Scoping", "Ambiguity Resolution", "Requirement Prioritization"],
    "wf_pm_reject": ["Constraint Resolution", "Acceptance Definition", "Requirement Contract Confirmation"],
    "wf_lit_strategy": ["Search Strategy Formation"],
    "wf_lit_provider": ["Multi-Source Signal Discovery", "Source Qualification"],
    "wf_grounded": ["Technical Signal Extraction", "Signal Organization", "Trend & Gap Analysis", "Evidence Completeness & Provenance Review"],
    "wf_ideate": ["Idea Generation", "Idea Identification", "Idea Card Formation", "Opportunity Definition"],
    "wf_ideate_dedup": ["Candidate Consolidation", "Opportunity Portfolio Prioritization"],
    "wf_novelty": ["Technical Opportunity Screening"],
    "wf_claim_convert": ["Research Question & Technical Claim Formation"],
    "wf_phase4_convert": ["Claim, Evidence, Data & Method Modeling", "Falsifiability Screening & Hypothesis Contracting"],
    "wf_exp_design": ["Verification-Ready POC Design"],
    "wf_poc_plan": ["POC Implementation Environment Preparation"],
    "wf_exp_run": ["POC Construction", "POC Component Integration & Configuration", "POC Functional Readiness Validation", "Testable POC Artifact Consolidation & Benchmark Handoff"],
    "wf_core_benchmark": ["Benchmark Framing", "Metrics & Run Evidence Collection"],
    "wf_benchmark_registry": ["Benchmark Protocol & Asset Preparation"],
    "wf_benchmark_execution": ["Benchmark Execution"],
    "wf_benchmark_report": ["Comparative Result Analysis & Benchmark Result Packaging"],
    "wf_evaluation": ["Search Coverage Review", "Evaluation Scope & Evidence Assembly", "Verdict, Blocker & Residual-Risk Classification"],
    "wf_artifact_review": ["Experimental, Reasoning & External Validity Review"],
    "wf_claim_gate": ["Claim & Acceptance-Criteria Comparison"],
    "wf_status_next": ["Refinement & Follow-Up Recording"],
    "wf_paper_draft": ["User-Facing Deliverable Generation"],
    "wf_publication": ["Delivery Planning & Evidence Handoff", "Deliverable, Reusable Asset & Knowledge Packaging", "Authorized Distribution, Knowledge Transfer & Lifecycle Closure"],
    "fn_capsule_def": ["Capability Capsule Definition & Assembly"],
    "fn_capsule_registry": ["Capsule Governance, Certification & Registry Management"],
    "fn_capsule_select": ["Capability Discovery, Scoring & Selection"],
    "fn_capsule_invoke": ["Capsule Invocation & Composition"],
    "fn_gepa_promote": ["Capability Capsule Evolution & Version Promotion", "Evaluator-Driven Operator Evolution", "Text-Based Artifacts (GEPA / MIPROv2 / TextGrad)", "Capability Capsules and Physical Operators (Trajectory Mining / Code Evolution / CEGIS)"],
    "fn_logical_schema": ["Logical Operator Definition, Assembly & Registration"],
    "fn_verification_gate": ["Operator Qualification, Admission & Governance", "Engineering Correctness & Code Quality Evaluator", "Evaluator, Reward, Contract, and Governance (Judge Calibration / Reward Modeling / CEGIS)"],
    "fn_operator_select": ["Logical-to-Physical Matching, Selection & Binding"],
    "fn_operator_runtime": ["Physical Operator & Execution Fleet Management"],
    "fn_operator_score": ["Operator Runtime Evaluation & Capability Profiling", "Runtime and Resource Routing (Bayesian Optimization / Bandits / Cost-Aware RL)"],
    "fn_workflow_schema": ["Contract, Schema & Artifact Conformance Evaluator"],
    "fn_benchmark_report": ["Performance, Cost & Benchmark Evaluator", "Data, Benchmarks, Curriculum, and Observability (Active Learning / Hard-Case Mining / Credit Assignment)"],
    "fn_repo_hygiene": ["Security, Privacy, Compliance & IP Evaluator"],
    "fn_evaluator": ["Evidence, Factuality & Scientific Validity Evaluator"],
    "fn_human_review": ["Lifecycle, Parity & Human Review Evaluator"],
    "fn_model_registry": ["Model Capability Registry"],
    "fn_model_routing": ["Model Routing & Selection"],
    "fn_model_audit": ["Model Usage Auditing"],
    "fn_graph_scheduler": ["DAG and Agent Organization (AFlow / MCTS / ADAS)", "DAG Scheduler, TaskGraph Readiness & Operator Binding"],
    "fn_context_store": ["Memory, Retrieval, and Evidence (Memory Learning / Self-RAG / Reranker Training)", "Persistent Memory & Context Retrieval"],
    "fn_evidence_ledger": ["Trace Graph Management"],
    "fn_bun_data": ["Concept Graph Management", "Code Graph Management", "Memory Graph Management"],
    "fn_workflow_instantiate": ["Workflow Graph Management", "TaskGraph Construction"],
    "fn_taskgraph_io": ["TaskGraph Persistence & Lifecycle Management"],
    "fn_task_lifecycle": ["Runtime Control Loop & Run Lifecycle Management", "Failure Recovery & Resumability"],
    "fn_agent_bus": ["Message Bus & Durable Task Queue"],
    "fn_actor_lease": ["Execution Admission, Lease & Concurrency Control"],
    "fn_actor_runtime": ["Main Loop Dispatch & Runtime Supervision"],
    "fn_intent_classify": ["Intent Classification & Compilation Variant Selection"],
    "wf_intent_capture": ["Request Capture", "Intake Provenance Registration", "Goal, Scope and Context normalization"],
    "wf_pm_build": ["Intent Interpretation", "Context Scoping", "Ambiguity Resolution", "Requirement Prioritization", "Ambiguity Resolution & Readiness"],
    "fn_plan_validator": ["Constraint Compilation", "TaskGraph Validation & Feasibility Analysis", "Product Integration"],
    "fn_intake_contract": ["Task Contract & Acceptance Compilation"],
    "fn_compiled_planner": ["Task Contract Decomposition"],
    "fn_apo_plan": ["Build Contract Interpretation"],
    "fn_build_prepare": ["Build Preparation"],
    "fn_code_construct": ["Code Construction", "Defect Repair"],
    "wf_exp_design": ["Verification-Ready POC Design", "Experimental Asset Construction"],
    "wf_benchmark_registry": ["Benchmark Protocol & Asset Preparation", "Benchmark Asset Construction"],
    "fn_verification_gate": ["Operator Qualification, Admission & Governance", "Engineering Correctness & Code Quality Evaluator", "Evaluator, Reward, Contract, and Governance (Judge Calibration / Reward Modeling / CEGIS)", "Verification Asset Construction"],
    "wf_ideate": ["Idea Generation", "Idea Identification", "Idea Card Formation", "Opportunity Definition", "Decision Artifact Construction"],
    "fn_evidence_ledger": ["Trace Graph Management", "Build Evidence Generation"],
    "wf_paper_draft": ["User-Facing Deliverable Generation", "Report/Paper/Deliverable Construction"],
    "fn_release_contract": ["Runtime Deliverable Construction"],
    "vt_status_scoping": ["Workflow & Platform Status Visibility", "Execution Trace Search & Inspection"],
    "vt_status_usage": ["Runtime status visibility", "Resource Usage, Cost & Capacity Management"],
    "vt_windows_app": ["Windows App"],
    "vt_macos_app": ["MacOS App"],
    "vt_cli": ["MacOS CLI", "Linux Cli", "CLI"],
    "vt_status_dashboard": ["Web Application & Status Service", "User Profile Management", "LLM Config"],
    "vt_gui": ["GUI"],
    "vt_tui": ["TUI"],
    "vt_auth": ["Authentication & Session Security"],
    "vt_user_settings": ["User Settings"],
    "vt_privacy": ["Privacy & Personal Data Controls"],
    "vt_wechat": ["Wechat"],
    "vt_tmux": ["TMUX"],
    "vt_cost_budget": ["Cost/Budget Settings"],
    "vt_cluster": ["Cluster setting"],
}


def clean_feature(value: object) -> str:
    text = re.sub(r"^\d+\.\s*", "", str(value or "").strip())
    # Some Foundation labels were stored as mojibake prefix + English suffix.
    if " — " in text:
        text = text.rsplit(" — ", 1)[-1].strip()
    return text


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def feature_probe_map() -> dict[str, str]:
    result: dict[str, str] = {}
    for probe_id, features in PROBE_FEATURES.items():
        if probe_id not in PROBES:
            raise ValueError(f"Undefined probe in mapping: {probe_id}")
        for feature in features:
            if feature in result:
                raise ValueError(f"Feature mapped more than once: {feature}")
            result[feature] = probe_id
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contracts-dir", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("l2_execution_matrix.json"),
    )
    args = parser.parse_args()

    contracts: list[dict] = []
    for name in ANNOTATION_FILES:
        contracts.extend(json.loads((args.contracts_dir / name).read_text(encoding="utf-8")))

    mapping = feature_probe_map()
    rows = []
    seen = set()
    for index, contract in enumerate(contracts, start=1):
        feature = clean_feature(contract["level_2_feature"])
        if feature in seen:
            raise ValueError(f"Duplicate L2 feature name requires composite mapping: {feature}")
        seen.add(feature)
        blocked = feature in BLOCKED_FEATURES
        probe_id = None if blocked else mapping.get(feature)
        if not blocked and not probe_id:
            raise ValueError(f"Implemented L2 has no executable probe: {feature}")
        sheet_code = {"Workflow Features": "WF", "Foundation Features": "FN", "Vertical Features": "VT"}[contract["sheet"]]
        rows.append(
            {
                "case_id": f"P22-{sheet_code}-L2-{index:03d}",
                "test_name": f"test_l2_{slug(feature)}",
                "sheet": contract["sheet"],
                "level_1_feature": contract["level_1_feature"],
                "level_2_feature": feature,
                "contract_description": contract["level_2_description"],
                "purpose_user_function": contract["purpose_user_function"],
                "valid_inputs": contract["valid_inputs"],
                "expected_outputs": contract["expected_outputs"],
                "success_evidence": contract["success_evidence"],
                "implementation_entrypoints": contract["implementation_entrypoints"],
                "supported_boundaries_exclusions": contract["supported_boundaries_exclusions"],
                "review_notes": contract["review_notes"],
                "implementation_status": "NOT_IMPLEMENTED" if blocked else "IMPLEMENTED_CURRENT_SUBSET",
                "probe_id": probe_id,
                "blocked_reason": (
                    "No direct core implementation was found; adjacent or partial surfaces do not satisfy this L2 contract."
                    if blocked
                    else ""
                ),
            }
        )

    unused_mappings = set(mapping) - seen
    if unused_mappings:
        raise ValueError(f"Mappings do not match a contract: {sorted(unused_mappings)}")
    if len(rows) != 142 or sum(row["implementation_status"] == "NOT_IMPLEMENTED" for row in rows) != 10:
        raise ValueError("Expected exactly 142 L2 rows with 10 implementation-blocked rows")

    payload = {
        "schema": "phase22.l2_execution_matrix.v1",
        "classification_policy": {
            "implemented_pass": "Direct current implementation exists and its feature-relevant executable probe passed.",
            "implemented_fail": "Direct current implementation exists but its executable probe failed or could not execute on the current machine.",
            "not_implemented_blocked": "No direct core implementation exists; no passing probe may be assigned.",
            "partial_rule": "A partial umbrella L2 is implemented only when a meaningful direct current subset exists; the tested subset and exclusions remain visible.",
        },
        "counts": {"total_l2": 142, "implemented": 132, "not_implemented": 10},
        "probes": PROBES,
        "features": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload["counts"], sort_keys=True))


if __name__ == "__main__":
    main()
