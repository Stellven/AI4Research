# Phase 22 L2 execution classification

- Total L2 features: 142
- Implemented and passed: 94
- Implemented but failed: 38
- Not implemented / blocked: 10
- Unique executable probes: 79 (58 passed, 21 failed)

| Sheet | Level 1 | Level 2 | Classification | Probe |
|---|---|---|---|---|
| Workflow Features | Ingestion | Request Capture | Function implemented and test passed | wf_intent_capture |
| Workflow Features | Ingestion | Qualified Channel Signal Intake | Function not implemented and test blocked | BLOCKED |
| Workflow Features | Ingestion | User-Supplied Material Import | Function implemented and test passed | wf_paper_prepare |
| Workflow Features | Ingestion | Intake Context Binding | Function implemented and test passed | wf_intent_bind |
| Workflow Features | Ingestion | Real-Time Intake Deduplication & Cleaning | Function implemented and test passed | wf_intent_consume |
| Workflow Features | Ingestion | Intake Provenance Registration | Function implemented and test passed | wf_intent_capture |
| Workflow Features | Ingestion | Intake Qualification | Function implemented and test passed | wf_intake_qualification |
| Workflow Features | Requirement compilation | Intent Interpretation | Function implemented and test passed | wf_pm_build |
| Workflow Features | Requirement compilation | Context Scoping | Function implemented and test passed | wf_pm_build |
| Workflow Features | Requirement compilation | Ambiguity Resolution | Function implemented and test passed | wf_pm_build |
| Workflow Features | Requirement compilation | Constraint Resolution | Function implemented and test passed | wf_pm_reject |
| Workflow Features | Requirement compilation | Requirement Prioritization | Function implemented and test passed | wf_pm_build |
| Workflow Features | Requirement compilation | Acceptance Definition | Function implemented and test passed | wf_pm_reject |
| Workflow Features | Requirement compilation | Requirement Contract Confirmation | Function implemented and test passed | wf_pm_reject |
| Workflow Features | Search & ideation | Search Strategy Formation | Function implemented and test passed | wf_lit_strategy |
| Workflow Features | Search & ideation | Multi-Source Signal Discovery | Function implemented and test passed | wf_lit_provider |
| Workflow Features | Search & ideation | Source Qualification | Function implemented and test passed | wf_lit_provider |
| Workflow Features | Search & ideation | Technical Signal Extraction | Function implemented and test passed | wf_grounded |
| Workflow Features | Search & ideation | Signal Organization | Function implemented and test passed | wf_grounded |
| Workflow Features | Search & ideation | Trend & Gap Analysis | Function implemented and test passed | wf_grounded |
| Workflow Features | Search & ideation | Idea Generation | Function implemented but test failed | wf_ideate |
| Workflow Features | Search & ideation | Search Coverage Review | Function implemented and test passed | wf_evaluation |
| Workflow Features | Idea identification / screening / opportunity selection | Candidate Consolidation | Function implemented and test passed | wf_ideate_dedup |
| Workflow Features | Idea identification / screening / opportunity selection | Idea Identification | Function implemented but test failed | wf_ideate |
| Workflow Features | Idea identification / screening / opportunity selection | Idea Card Formation | Function implemented but test failed | wf_ideate |
| Workflow Features | Idea identification / screening / opportunity selection | Opportunity Definition | Function implemented but test failed | wf_ideate |
| Workflow Features | Idea identification / screening / opportunity selection | Technical Opportunity Screening | Function implemented and test passed | wf_novelty |
| Workflow Features | Idea identification / screening / opportunity selection | Strategic Opportunity Screening | Function not implemented and test blocked | BLOCKED |
| Workflow Features | Idea identification / screening / opportunity selection | Opportunity Portfolio Prioritization | Function implemented and test passed | wf_ideate_dedup |
| Workflow Features | Generate technical claims & hypothesis | Research Question & Technical Claim Formation | Function implemented and test passed | wf_claim_convert |
| Workflow Features | Generate technical claims & hypothesis | Claim, Evidence, Data & Method Modeling | Function implemented and test passed | wf_phase4_convert |
| Workflow Features | Generate technical claims & hypothesis | Hypothesis Pool & Mechanism Formation | Function not implemented and test blocked | BLOCKED |
| Workflow Features | Generate technical claims & hypothesis | Falsifiability Screening & Hypothesis Contracting | Function implemented and test passed | wf_phase4_convert |
| Workflow Features | Generate technical claims & hypothesis | Verification-Ready POC Design | Function implemented but test failed | wf_exp_design |
| Workflow Features | POC implementation | POC Implementation Environment Preparation | Function implemented and test passed | wf_poc_plan |
| Workflow Features | POC implementation | POC Construction | Function implemented but test failed | wf_exp_run |
| Workflow Features | POC implementation | POC Component Integration & Configuration | Function implemented but test failed | wf_exp_run |
| Workflow Features | POC implementation | POC Functional Readiness Validation | Function implemented but test failed | wf_exp_run |
| Workflow Features | POC implementation | Testable POC Artifact Consolidation & Benchmark Handoff | Function implemented but test failed | wf_exp_run |
| Workflow Features | Benchmarking | Benchmark Framing | Function implemented and test passed | wf_core_benchmark |
| Workflow Features | Benchmarking | Benchmark Protocol & Asset Preparation | Function implemented and test passed | wf_benchmark_registry |
| Workflow Features | Benchmarking | Benchmark Execution | Function implemented but test failed | wf_benchmark_execution |
| Workflow Features | Benchmarking | Metrics & Run Evidence Collection | Function implemented and test passed | wf_core_benchmark |
| Workflow Features | Benchmarking | Comparative Result Analysis & Benchmark Result Packaging | Function implemented and test passed | wf_benchmark_report |
| Workflow Features | Evaluation | Evaluation Scope & Evidence Assembly | Function implemented and test passed | wf_evaluation |
| Workflow Features | Evaluation | Evidence Completeness & Provenance Review | Function implemented and test passed | wf_grounded |
| Workflow Features | Evaluation | Experimental, Reasoning & External Validity Review | Function implemented and test passed | wf_artifact_review |
| Workflow Features | Evaluation | Claim & Acceptance-Criteria Comparison | Function implemented and test passed | wf_claim_gate |
| Workflow Features | Evaluation | Verdict, Blocker & Residual-Risk Classification | Function implemented and test passed | wf_evaluation |
| Workflow Features | Evaluation | Refinement & Follow-Up Recording | Function implemented and test passed | wf_status_next |
| Workflow Features | Delivery | Delivery Planning & Evidence Handoff | Function implemented and test passed | wf_publication |
| Workflow Features | Delivery | User-Facing Deliverable Generation | Function implemented and test passed | wf_paper_draft |
| Workflow Features | Delivery | Deliverable, Reusable Asset & Knowledge Packaging | Function implemented and test passed | wf_publication |
| Workflow Features | Delivery | Authorized Distribution, Knowledge Transfer & Lifecycle Closure | Function implemented and test passed | wf_publication |
| Foundation Features | Capability capsule | Capability Capsule Definition & Assembly | Function implemented and test passed | fn_capsule_def |
| Foundation Features | Capability capsule | Capsule Governance, Certification & Registry Management | Function implemented and test passed | fn_capsule_registry |
| Foundation Features | Capability capsule | Capability Discovery, Scoring & Selection | Function implemented and test passed | fn_capsule_select |
| Foundation Features | Capability capsule | Capsule Invocation & Composition | Function implemented and test passed | fn_capsule_invoke |
| Foundation Features | Capability capsule | Capability Capsule Evolution & Version Promotion | Function implemented but test failed | fn_gepa_promote |
| Foundation Features | Operators | Logical Operator Definition, Assembly & Registration | Function implemented but test failed | fn_logical_schema |
| Foundation Features | Operators | Operator Qualification, Admission & Governance | Function implemented and test passed | fn_verification_gate |
| Foundation Features | Operators | Logical-to-Physical Matching, Selection & Binding | Function implemented but test failed | fn_operator_select |
| Foundation Features | Operators | Physical Operator & Execution Fleet Management | Function implemented but test failed | fn_operator_runtime |
| Foundation Features | Operators | Operator Runtime Evaluation & Capability Profiling | Function implemented and test passed | fn_operator_score |
| Foundation Features | Operators | Evaluator-Driven Operator Evolution | Function implemented but test failed | fn_gepa_promote |
| Foundation Features | Evaluator | Contract, Schema & Artifact Conformance Evaluator | Function implemented and test passed | fn_workflow_schema |
| Foundation Features | Evaluator | Engineering Correctness & Code Quality Evaluator | Function implemented and test passed | fn_verification_gate |
| Foundation Features | Evaluator | Performance, Cost & Benchmark Evaluator | Function implemented and test passed | fn_benchmark_report |
| Foundation Features | Evaluator | Security, Privacy, Compliance & IP Evaluator | Function implemented and test passed | fn_repo_hygiene |
| Foundation Features | Evaluator | Evidence, Factuality & Scientific Validity Evaluator | Function implemented and test passed | fn_evaluator |
| Foundation Features | Evaluator | Lifecycle, Parity & Human Review Evaluator | Function implemented and test passed | fn_human_review |
| Foundation Features | Foundational models | Model Capability Registry | Function implemented and test passed | fn_model_registry |
| Foundation Features | Foundational models | Model Routing & Selection | Function implemented and test passed | fn_model_routing |
| Foundation Features | Foundational models | Model Usage Auditing | Function implemented but test failed | fn_model_audit |
| Foundation Features | RSI | Text-Based Artifacts (GEPA / MIPROv2 / TextGrad) | Function implemented but test failed | fn_gepa_promote |
| Foundation Features | RSI | Runtime and Resource Routing (Bayesian Optimization / Bandits / Cost-Aware RL) | Function implemented and test passed | fn_operator_score |
| Foundation Features | RSI | Capability Capsules and Physical Operators (Trajectory Mining / Code Evolution / CEGIS) | Function implemented but test failed | fn_gepa_promote |
| Foundation Features | RSI | DAG and Agent Organization (AFlow / MCTS / ADAS) | Function implemented and test passed | fn_graph_scheduler |
| Foundation Features | RSI | Evaluator, Reward, Contract, and Governance (Judge Calibration / Reward Modeling / CEGIS) | Function implemented and test passed | fn_verification_gate |
| Foundation Features | RSI | Memory, Retrieval, and Evidence (Memory Learning / Self-RAG / Reranker Training) | Function implemented and test passed | fn_context_store |
| Foundation Features | RSI | Model Policies and Weights (SFT / LoRA / DPO / GRPO / Agent RL) | Function not implemented and test blocked | BLOCKED |
| Foundation Features | RSI | Data, Benchmarks, Curriculum, and Observability (Active Learning / Hard-Case Mining / Credit Assignment) | Function implemented and test passed | fn_benchmark_report |
| Foundation Features | Data foundations | Persistent Memory & Context Retrieval | Function implemented and test passed | fn_context_store |
| Foundation Features | Data foundations | Concept Graph Management | Function implemented but test failed | fn_bun_data |
| Foundation Features | Data foundations | Dataset Graph Management | Function not implemented and test blocked | BLOCKED |
| Foundation Features | Data foundations | Code Graph Management | Function implemented but test failed | fn_bun_data |
| Foundation Features | Data foundations | Policy Graph Management | Function not implemented and test blocked | BLOCKED |
| Foundation Features | Data foundations | Workflow Graph Management | Function implemented and test passed | fn_workflow_instantiate |
| Foundation Features | Data foundations | Trace Graph Management | Function implemented and test passed | fn_evidence_ledger |
| Foundation Features | Data foundations | Memory Graph Management | Function implemented but test failed | fn_bun_data |
| Foundation Features | Data foundations | TaskGraph Persistence & Lifecycle Management | Function implemented and test passed | fn_taskgraph_io |
| Foundation Features | Harness Core | Runtime Control Loop & Run Lifecycle Management | Function implemented and test passed | fn_task_lifecycle |
| Foundation Features | Harness Core | Message Bus & Durable Task Queue | Function implemented and test passed | fn_agent_bus |
| Foundation Features | Harness Core | DAG Scheduler, TaskGraph Readiness & Operator Binding | Function implemented and test passed | fn_graph_scheduler |
| Foundation Features | Harness Core | Execution Admission, Lease & Concurrency Control | Function implemented but test failed | fn_actor_lease |
| Foundation Features | Harness Core | Main Loop Dispatch & Runtime Supervision | Function implemented but test failed | fn_actor_runtime |
| Foundation Features | Harness Core | Failure Recovery & Resumability | Function implemented and test passed | fn_task_lifecycle |
| Foundation Features | Intention compilers | Intent Classification & Compilation Variant Selection | Function implemented and test passed | fn_intent_classify |
| Foundation Features | Intention compilers | Goal, Scope and Context normalization | Function implemented and test passed | wf_intent_capture |
| Foundation Features | Intention compilers | Ambiguity Resolution & Readiness | Function implemented and test passed | wf_pm_build |
| Foundation Features | Intention compilers | Constraint Compilation | Function implemented and test passed | fn_plan_validator |
| Foundation Features | Intention compilers | Task Contract & Acceptance Compilation | Function implemented and test passed | fn_intake_contract |
| Foundation Features | Planner | Task Contract Decomposition | Function implemented but test failed | fn_compiled_planner |
| Foundation Features | Planner | TaskGraph Construction | Function implemented and test passed | fn_workflow_instantiate |
| Foundation Features | Planner | TaskGraph Validation & Feasibility Analysis | Function implemented and test passed | fn_plan_validator |
| Foundation Features | Builder | Build Contract Interpretation | Function implemented and test passed | fn_apo_plan |
| Foundation Features | Builder | Build Preparation | Function implemented but test failed | fn_build_prepare |
| Foundation Features | Builder | Code Construction | Function implemented and test passed | fn_code_construct |
| Foundation Features | Builder | Model Construction | Function not implemented and test blocked | BLOCKED |
| Foundation Features | Builder | Experimental Asset Construction | Function implemented but test failed | wf_exp_design |
| Foundation Features | Builder | Benchmark Asset Construction | Function implemented and test passed | wf_benchmark_registry |
| Foundation Features | Builder | Verification Asset Construction | Function implemented and test passed | fn_verification_gate |
| Foundation Features | Builder | Decision Artifact Construction | Function implemented but test failed | wf_ideate |
| Foundation Features | Builder | Prototype Assembly | Function not implemented and test blocked | BLOCKED |
| Foundation Features | Builder | Product Integration | Function implemented and test passed | fn_plan_validator |
| Foundation Features | Builder | Defect Repair | Function implemented and test passed | fn_code_construct |
| Foundation Features | Builder | Build Evidence Generation | Function implemented and test passed | fn_evidence_ledger |
| Foundation Features | Builder | Report/Paper/Deliverable Construction | Function implemented and test passed | wf_paper_draft |
| Foundation Features | Builder | Runtime Deliverable Construction | Function implemented and test passed | fn_release_contract |
| Vertical Features | Visibility / Statistics | Workflow & Platform Status Visibility | Function implemented and test passed | vt_status_scoping |
| Vertical Features | Visibility / Statistics | Execution Trace Search & Inspection | Function implemented and test passed | vt_status_scoping |
| Vertical Features | Visibility / Statistics | Runtime status visibility | Function implemented and test passed | vt_status_usage |
| Vertical Features | Visibility / Statistics | Resource Usage, Cost & Capacity Management | Function implemented and test passed | vt_status_usage |
| Vertical Features | Installer & CLI & Webapp | Windows App | Function implemented and test passed | vt_windows_app |
| Vertical Features | Installer & CLI & Webapp | MacOS App | Function implemented but test failed | vt_macos_app |
| Vertical Features | Installer & CLI & Webapp | MacOS CLI | Function implemented but test failed | vt_cli |
| Vertical Features | Installer & CLI & Webapp | Linux Cli | Function implemented but test failed | vt_cli |
| Vertical Features | Installer & CLI & Webapp | Web Application & Status Service | Function implemented but test failed | vt_status_dashboard |
| Vertical Features | UI | CLI | Function implemented but test failed | vt_cli |
| Vertical Features | UI | GUI | Function implemented but test failed | vt_gui |
| Vertical Features | UI | TUI | Function implemented but test failed | vt_tui |
| Vertical Features | Account management | Account Registration | Function not implemented and test blocked | BLOCKED |
| Vertical Features | Account management | Authentication & Session Security | Function implemented but test failed | vt_auth |
| Vertical Features | Account management | User Profile Management | Function implemented but test failed | vt_status_dashboard |
| Vertical Features | Account management | Privacy & Personal Data Controls | Function implemented and test passed | vt_privacy |
| Vertical Features | Message Channels | Wechat | Function implemented but test failed | vt_wechat |
| Vertical Features | Message Channels | Discord | Function not implemented and test blocked | BLOCKED |
| Vertical Features | Message Channels | TMUX | Function implemented and test passed | vt_tmux |
| Vertical Features | System Configurations | LLM Config | Function implemented but test failed | vt_status_dashboard |
| Vertical Features | System Configurations | User Settings | Function implemented and test passed | vt_user_settings |
| Vertical Features | System Configurations | Cost/Budget Settings | Function implemented and test passed | vt_cost_budget |
| Vertical Features | System Configurations | Cluster setting | Function implemented and test passed | vt_cluster |
