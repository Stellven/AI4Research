# Phase 22 Repair Issue Packets

Generated for baseline: `c331eec8b905007b785fa494041af1efc2139a89`

Scope: every L2 currently recorded as `FAIL`, `ENVIRONMENT_BLOCKED`, or `PASS_WITH_KNOWN_LIMITATIONS`. CI and `NOT_AVAILABLE` rows are excluded by user instruction.

> A recorded status is a hypothesis until its selector is rerun at the stated baseline. `pytest PASS` from a diagnostic journey does not by itself mean the product behavior passed.

## Counts

| Priority | Count |
|---|---:|
| `P0_BLOCKER` | 15 |
| `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | 72 |
| `P2_EVIDENCE_RECONCILIATION` | 2 |
| `P2_MILD_FAILURE` | 2 |

## Investigation queue

| ID | Category | L2 feature | Recorded status | Priority | Freshness | Confidence | Selector count |
|---|---|---|---|---|---|---|---:|
| P22-REPAIR-001 | Workflow | Request Capture | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-003 | Workflow | User-Supplied Material Import | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-004 | Workflow | Intake Context Binding | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-005 | Workflow | Real-Time Intake Deduplication & Cleaning | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-006 | Workflow | Intake Provenance Registration | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-007 | Workflow | Intake Qualification | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-008 | Workflow | Intent Interpretation | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-010 | Workflow | Ambiguity Resolution | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-011 | Workflow | Constraint Resolution | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-013 | Workflow | Acceptance Definition | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-014 | Workflow | Requirement Contract Confirmation | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-015 | Workflow | Search Strategy Formation | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-016 | Workflow | Multi-Source Signal Discovery | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-017 | Workflow | Source Qualification | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-018 | Workflow | Technical Signal Extraction | `FAIL` | `P0_BLOCKER` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_EXECUTABLE_DIAGNOSTIC` | 1 |
| P22-REPAIR-019 | Workflow | Signal Organization | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-020 | Workflow | Trend & Gap Analysis | `FAIL` | `P0_BLOCKER` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_EXECUTABLE_DIAGNOSTIC` | 1 |
| P22-REPAIR-021 | Workflow | Idea Generation | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-022 | Workflow | Search Coverage Review | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-023 | Workflow | Candidate Consolidation | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-024 | Workflow | Idea Identification | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-025 | Workflow | Idea Card Formation | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-029 | Workflow | Opportunity Portfolio Prioritization | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-030 | Workflow | Research Question & Technical Claim Formation | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-031 | Workflow | Claim, Evidence, Data & Method Modeling | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-033 | Workflow | Falsifiability Screening & Hypothesis Contracting | `FAIL` | `P0_BLOCKER` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_EXECUTABLE_DIAGNOSTIC` | 1 |
| P22-REPAIR-034 | Workflow | Verification-Ready POC Design | `FAIL` | `P0_BLOCKER` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_EXECUTABLE_DIAGNOSTIC` | 2 |
| P22-REPAIR-036 | Workflow | POC Construction | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 2 |
| P22-REPAIR-037 | Workflow | POC Component Integration & Configuration | `FAIL` | `P0_BLOCKER` | `LIKELY_STALE_J21_SOURCE_NOW_RECOMMENDS_PASS_OR_LIMITED` | `LOW_UNTIL_RERUN` | 1 |
| P22-REPAIR-038 | Workflow | POC Functional Readiness Validation | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 2 |
| P22-REPAIR-039 | Workflow | Testable POC Artifact Consolidation & Benchmark Handoff | `FAIL` | `P0_BLOCKER` | `LIKELY_STALE_J21_SOURCE_NOW_RECOMMENDS_PASS_OR_LIMITED` | `LOW_UNTIL_RERUN` | 1 |
| P22-REPAIR-040 | Workflow | Benchmark Framing | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-041 | Workflow | Benchmark Protocol & Asset Preparation | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-043 | Workflow | Metrics & Run Evidence Collection | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-044 | Workflow | Comparative Result Analysis & Benchmark Result Packaging | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-045 | Workflow | Evaluation Scope & Evidence Assembly | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 2 |
| P22-REPAIR-047 | Workflow | Experimental, Reasoning & External Validity Review | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 2 |
| P22-REPAIR-048 | Workflow | Claim & Acceptance-Criteria Comparison | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 2 |
| P22-REPAIR-049 | Workflow | Verdict, Blocker & Residual-Risk Classification | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 2 |
| P22-REPAIR-051 | Workflow | Delivery Planning & Evidence Handoff | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-052 | Workflow | User-Facing Deliverable Generation | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-053 | Workflow | Deliverable, Reusable Asset & Knowledge Packaging | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-054 | Workflow | Authorized Distribution, Knowledge Transfer & Lifecycle Closure | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-055 | Foundation | Capability Capsule Definition & Assembly | `FAIL` | `P0_BLOCKER` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_EXECUTABLE_DIAGNOSTIC` | 1 |
| P22-REPAIR-057 | Foundation | Capability Discovery, Scoring & Selection | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-066 | Foundation | Contract, Schema & Artifact Conformance Evaluator | `FAIL` | `P0_BLOCKER` | `LIKELY_STALE_J21_SOURCE_NOW_RECOMMENDS_PASS_OR_LIMITED` | `LOW_UNTIL_RERUN` | 1 |
| P22-REPAIR-067 | Foundation | Engineering Correctness & Code Quality Evaluator | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-068 | Foundation | Performance, Cost & Benchmark Evaluator | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-069 | Foundation | Security, Privacy, Compliance & IP Evaluator | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 2 |
| P22-REPAIR-070 | Foundation | Evidence, Factuality & Scientific Validity Evaluator | `FAIL` | `P0_BLOCKER` | `POSSIBLY_STALE_INFERRED_MAPPING` | `LOW_UNTIL_RERUN` | 1 |
| P22-REPAIR-071 | Foundation | Lifecycle, Parity & Human Review Evaluator | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-076 | Foundation | Runtime and Resource Routing (Bayesian Optimization / Bandits / Cost-Aware RL) | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-080 | Foundation | Memory, Retrieval, and Evidence (Memory Learning / Self-RAG / Reranker Training) | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-082 | Foundation | Data, Benchmarks, Curriculum, and Observability (Active Learning / Hard-Case Mining / Credit Assignment) | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-083 | Foundation | Persistent Memory & Context Retrieval | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-084 | Foundation | Concept Graph Management | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-086 | Foundation | Code Graph Management | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-089 | Foundation | Trace Graph Management | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-090 | Foundation | Memory Graph Management | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-091 | Foundation | TaskGraph Persistence & Lifecycle Management | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-092 | Foundation | Runtime Control Loop & Run Lifecycle Management | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-094 | Foundation | DAG Scheduler, TaskGraph Readiness & Operator Binding | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-095 | Foundation | Execution Admission, Lease & Concurrency Control | `FAIL` | `P0_BLOCKER` | `LIKELY_STALE_J21_SOURCE_NOW_RECOMMENDS_PASS_OR_LIMITED` | `LOW_UNTIL_RERUN` | 1 |
| P22-REPAIR-096 | Foundation | Main Loop Dispatch & Runtime Supervision | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-100 | Foundation | Ambiguity Resolution & Readiness | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-102 | Foundation | Task Contract & Acceptance Compilation | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-103 | Foundation | Task Contract Decomposition | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-104 | Foundation | TaskGraph Construction | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-105 | Foundation | TaskGraph Validation & Feasibility Analysis | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-108 | Foundation | Code Construction | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-110 | Foundation | Experimental Asset Construction | `FAIL` | `P0_BLOCKER` | `LIKELY_STALE_J21_SOURCE_NOW_RECOMMENDS_PASS_OR_LIMITED` | `LOW_UNTIL_RERUN` | 1 |
| P22-REPAIR-111 | Foundation | Benchmark Asset Construction | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-112 | Foundation | Verification Asset Construction | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-113 | Foundation | Decision Artifact Construction | `FAIL` | `P0_BLOCKER` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_EXECUTABLE_DIAGNOSTIC` | 1 |
| P22-REPAIR-115 | Foundation | Product Integration | `FAIL` | `P0_BLOCKER` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_EXECUTABLE_DIAGNOSTIC` | 1 |
| P22-REPAIR-116 | Foundation | Defect Repair | `FAIL` | `P0_BLOCKER` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_EXECUTABLE_DIAGNOSTIC` | 1 |
| P22-REPAIR-117 | Foundation | Build Evidence Generation | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-118 | Foundation | Report/Paper/Deliverable Construction | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-119 | Foundation | Runtime Deliverable Construction | `FAIL` | `P0_BLOCKER` | `LIKELY_STALE_J21_SOURCE_NOW_RECOMMENDS_PASS_OR_LIMITED` | `LOW_UNTIL_RERUN` | 1 |
| P22-REPAIR-120 | Vertical | Workflow & Platform Status Visibility | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 2 |
| P22-REPAIR-121 | Vertical | Execution Trace Search & Inspection | `FAIL` | `P2_MILD_FAILURE` | `DETECTION_TEST_ENCODES_KNOWN_FAILURE` | `MEDIUM_EXECUTABLE_DIAGNOSTIC` | 1 |
| P22-REPAIR-125 | Vertical | MacOS App | `ENVIRONMENT_BLOCKED` | `P2_EVIDENCE_RECONCILIATION` | `POSSIBLY_STALE_MAC_EVIDENCE_NOT_RECONCILED` | `MEDIUM_EXECUTABLE_DIAGNOSTIC` | 1 |
| P22-REPAIR-126 | Vertical | MacOS CLI | `ENVIRONMENT_BLOCKED` | `P2_EVIDENCE_RECONCILIATION` | `POSSIBLY_STALE_MAC_EVIDENCE_NOT_RECONCILED` | `MEDIUM_EXECUTABLE_DIAGNOSTIC` | 1 |
| P22-REPAIR-127 | Vertical | Linux Cli | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 2 |
| P22-REPAIR-128 | Vertical | Web Application & Status Service | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 4 |
| P22-REPAIR-129 | Vertical | CLI | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 2 |
| P22-REPAIR-130 | Vertical | GUI | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 2 |
| P22-REPAIR-131 | Vertical | TUI | `FAIL` | `P2_MILD_FAILURE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_EXECUTABLE_DIAGNOSTIC` | 3 |
| P22-REPAIR-135 | Vertical | Privacy & Personal Data Controls | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 1 |
| P22-REPAIR-138 | Vertical | TMUX | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 2 |
| P22-REPAIR-139 | Vertical | LLM Config | `PASS_WITH_KNOWN_LIMITATIONS` | `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE` | `NEEDS_CURRENT_BASELINE_RERUN` | `MEDIUM_BROAD_JOURNEY_LIMITATION` | 2 |

## Full packets

### P22-REPAIR-001 — Workflow :: Request Capture

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J02
- Expected behavior: Receives the user’s question, instruction, desired outcome, and requested deliverable as an intake candidate without prematurely treating it as a formal requirement.
- Expected output: A raw intake record, rewritten intent, Requirement IR, manifest, bound sprint artifacts, and optionally a dispatched planner handoff.
- Recorded observation: The main workflow passed, but the older eval.md evidence file was not created; command logs and saved status are available instead.
- Production entrypoints: harness/solar-harness.sh::intake_request, write_intake_raw_record; harness/lib/intent_gateway.py::capture, deterministic_rewrite, build_requirement_ir; harness/lib/intent_consumer.py::consume_one
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['5a4583e790b568dc62eac78c46cbba30cb751008']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j02_live_coding_task.py::test_p22_j02_live_coding_task`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/phase22-j02-live-windows-008/result.json` — exists=true, recorded_head=`5a4583e790b568dc62eac78c46cbba30cb751008`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/solar-harness.sh::intake_request` returns success and `harness/lib/intent_gateway.py::capture` produces raw, rewritten, Requirement IR, and manifest artifacts.

### P22-REPAIR-003 — Workflow :: User-Supplied Material Import

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J04
- Expected behavior: Imports documents, uploads, pasted content, datasets, and explicit file, repository, or URL references supplied by the user; related-source discovery belongs to Search & Ideation.
- Expected output: Canonical ingest path, prepared source artifacts, extracted sections/text, parse status, provenance, and limitations.
- Recorded observation: The PDF was imported, but registration into the wiki was not completed.
- Production entrypoints: harness/plugins/autosci/backends/paper_prepare.py::prepare_paper_source, read_paper_source; harness/plugins/autosci/bin/autosci_bridge.py::_read_sample_paper, _native_prepare_paper_source
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['0265f6416e197cf613d69b4705b52730621cf3c9']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j04_paper_ingestion.py::test_p22_j04_paper_ingestion`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/overnight-phase22/result.json` — exists=true, recorded_head=`0265f6416e197cf613d69b4705b52730621cf3c9`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/plugins/autosci/backends/paper_prepare.py::prepare_paper_source, read_paper_source` returns canonical content/sections and `harness/plugins/autosci/bin/autosci_bridge.py::_action_ingest_paper` emits evidence.

### P22-REPAIR-004 — Workflow :: Intake Context Binding

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J02
- Expected behavior: Binds the candidate to the authorized user, session, workspace, project, originating signal, and explicitly selected prior artifacts needed for interpretation.
- Expected output: A bound intent/sprint record with workspace identity and captured context that downstream planning can consume.
- Recorded observation: The main workflow passed, but the older eval.md evidence file was not created; command logs and saved status are available instead.
- Production entrypoints: harness/lib/workspace_binding.py::bind_active_workspace, sprint_workspace_root; harness/lib/intent_gateway.py::capture, bind_intent_artifacts; harness/lib/intent_consumer.py::consume_one
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['5a4583e790b568dc62eac78c46cbba30cb751008']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j02_live_coding_task.py::test_p22_j02_live_coding_task`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/phase22-j02-live-windows-008/result.json` — exists=true, recorded_head=`5a4583e790b568dc62eac78c46cbba30cb751008`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/lib/workspace_binding.py::bind_active_workspace, sprint_workspace_root` and `harness/lib/intent_gateway.py::bind_intent_artifacts` agree on the active workspace and publish bound artifacts.

### P22-REPAIR-005 — Workflow :: Real-Time Intake Deduplication & Cleaning

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J04
- Expected behavior: Canonicalizes incoming candidates, filters malformed or noisy content, and merges replays, exact duplicates, and near-duplicates while preserving meaningful revisions and independent corroboration.
- Expected output: Whitespace-normalized text and idempotent same-intent consumption; no verified merged candidate or corroboration/revision record exists across separately captured intents.
- Recorded observation: The PDF was imported, but registration into the wiki was not completed.
- Production entrypoints: harness/lib/intent_consumer.py::consume_one; harness/tools/codex_pm_router.py::_normalized_text; harness/lib/intent_gateway.py::capture
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['0265f6416e197cf613d69b4705b52730621cf3c9']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j04_paper_ingestion.py::test_p22_j04_paper_ingestion`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/overnight-phase22/result.json` — exists=true, recorded_head=`0265f6416e197cf613d69b4705b52730621cf3c9`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Partial only: `harness/lib/intent_consumer.py::consume_one` avoids re-consuming an existing intent ID and `harness/tools/codex_pm_router.py::_normalized_text` normalizes whitespace.

### P22-REPAIR-006 — Workflow :: Intake Provenance Registration

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J02
- Expected behavior: Records origin, identity, version, timestamp, access path, acquisition mode, and transformations for every accepted intake input.
- Expected output: Raw intake record, source metadata, receive timestamp, intent ID/digest, rewritten request, Requirement IR, and manifest references.
- Recorded observation: The main workflow passed, but the older eval.md evidence file was not created; command logs and saved status are available instead.
- Production entrypoints: harness/lib/intent_gateway.py::capture, build_requirement_ir, bind_intent_artifacts; harness/solar-harness.sh::write_intake_raw_record
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['5a4583e790b568dc62eac78c46cbba30cb751008']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j02_live_coding_task.py::test_p22_j02_live_coding_task`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/phase22-j02-live-windows-008/result.json` — exists=true, recorded_head=`5a4583e790b568dc62eac78c46cbba30cb751008`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/lib/intent_gateway.py::capture` records source/channel, actor, device, repo, received_at and writes raw/rewritten/IR/manifest; `harness/solar-harness.sh::write_intake_raw_record` records request/result/runtime rule.

### P22-REPAIR-007 — Workflow :: Intake Qualification

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J04
- Expected behavior: Checks accessibility, authorization, readability, and minimum completeness, then emits a qualified intake package or an explicit rejection or quarantine reason.
- Expected output: A validated/qualified intake and sprint/planner handoff, or a state-machine rejection with reason.
- Recorded observation: The PDF was imported, but registration into the wiki was not completed.
- Production entrypoints: harness/lib/livework/intake_state_machine.py::intake_requirement, IntakeFSM; harness/lib/livework/schemas.py::RequirementIntakePayload, RequirementIntake; harness/tools/codex_pm_router.py::validate_compiled_package
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['0265f6416e197cf613d69b4705b52730621cf3c9']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j04_paper_ingestion.py::test_p22_j04_paper_ingestion`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/overnight-phase22/result.json` — exists=true, recorded_head=`0265f6416e197cf613d69b4705b52730621cf3c9`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/lib/livework/intake_state_machine.py::intake_requirement, IntakeFSM` reaches dispatched only after validation/PM/planner stages; failures carry explicit reasons.

### P22-REPAIR-008 — Workflow :: Intent Interpretation

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J02
- Expected behavior: Determines the user’s actual problem, desired change, audience, decision, and deliverable without selecting an opportunity or solution.
- Expected output: Normalized goal, problem statement, user intent, requirements, assumptions, open questions, risks, and PM intake artifacts.
- Recorded observation: The main workflow passed, but the older eval.md evidence file was not created; command logs and saved status are available instead.
- Production entrypoints: harness/tools/codex_pm_router.py::build_pm_intake, _build_requirement_items; harness/lib/intent_gateway.py::deterministic_rewrite, build_requirement_ir
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['5a4583e790b568dc62eac78c46cbba30cb751008']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j02_live_coding_task.py::test_p22_j02_live_coding_task`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/phase22-j02-live-windows-008/result.json` — exists=true, recorded_head=`5a4583e790b568dc62eac78c46cbba30cb751008`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/tools/codex_pm_router.py::build_pm_intake` populates normalized goal/problem/user intent and `validate_compiled_package` accepts the package.

### P22-REPAIR-010 — Workflow :: Ambiguity Resolution

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J16
- Expected behavior: Finds missing information, conflicting instructions, undefined terms, and consequential assumptions and resolves them through focused questions or explicit defaults.
- Expected output: Assumptions and open-question lists embedded in PM intake/Requirement IR, with blocked or conditional planning where needed.
- Recorded observation: The requirements flow worked, but the product did not generate a clarification question itself.
- Production entrypoints: harness/tools/codex_pm_router.py::_derive_assumptions, _derive_open_questions, build_pm_intake, validate_compiled_package
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j16_tmux_requirements_builder.py::test_p22_j16_tmux_requirements_builder_real_user_defect_repair`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/T1-tmux-prep-001/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/tools/codex_pm_router.py::_derive_assumptions, _derive_open_questions` populate the compiled package and `validate_compiled_package` enforces its shape.

### P22-REPAIR-011 — Workflow :: Constraint Resolution

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J02
- Expected behavior: Identifies and reconciles authorization, scope, time, cost, data, safety, policy, tool, environment, and output-format constraints with the user’s intended outcome.
- Expected output: Requirements/contracts/DAG nodes with constraints, write scopes, gates, resource rules, stop rules, and explicit limitations.
- Recorded observation: The main workflow passed, but the older eval.md evidence file was not created; command logs and saved status are available instead.
- Production entrypoints: harness/tools/codex_pm_router.py::_build_contracts, _default_stop_rules, _node_enrichment; harness/lib/plan_validator.py::compile_and_stamp; harness/lib/policy/action_policy.py
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['5a4583e790b568dc62eac78c46cbba30cb751008']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j02_live_coding_task.py::test_p22_j02_live_coding_task`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/phase22-j02-live-windows-008/result.json` — exists=true, recorded_head=`5a4583e790b568dc62eac78c46cbba30cb751008`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/lib/plan_validator.py::compile_and_stamp` validates graph, write scope and gate allowlists; `harness/lib/policy/action_policy.py` classifies approval-sensitive actions.

### P22-REPAIR-013 — Workflow :: Acceptance Definition

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J02
- Expected behavior: Defines observable success criteria, proof obligations, decision thresholds, failure conditions, and stopping rules.
- Expected output: Acceptance criteria/verdict inputs, contracts with proof obligations, coverage/trace artifacts, gate commands, and stopping rules.
- Recorded observation: The main workflow passed, but the older eval.md evidence file was not created; command logs and saved status are available instead.
- Production entrypoints: harness/tools/codex_pm_router.py::_default_acceptance, _default_stop_rules, _build_contracts; harness/lib/plan_validator.py; harness/schemas/acceptance-verdict.schema.json
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['5a4583e790b568dc62eac78c46cbba30cb751008']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j02_live_coding_task.py::test_p22_j02_live_coding_task`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/phase22-j02-live-windows-008/result.json` — exists=true, recorded_head=`5a4583e790b568dc62eac78c46cbba30cb751008`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/tools/codex_pm_router.py::_default_acceptance, _default_stop_rules, _build_contracts` plus `harness/lib/plan_validator.py` yield accepted gates and `harness/schemas/acceptance-verdict.schema.json` validates results.

### P22-REPAIR-014 — Workflow :: Requirement Contract Confirmation

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J02
- Expected behavior: Assembles a versioned contract with executable task semantics, presents consequential interpretations, and records user confirmation or authorized assumptions.
- Expected output: Validated PM intake, PRD, contracts, task DAG, trace/coverage/acceptance artifacts, and a stamped plan certificate/handoff.
- Recorded observation: The main workflow passed, but the older eval.md evidence file was not created; command logs and saved status are available instead.
- Production entrypoints: harness/tools/codex_pm_router.py::build_pm_intake, validate_compiled_package; harness/lib/plan_validator.py::compile_and_stamp; harness/lib/workflow_intake.py::create_contract_sprint
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['5a4583e790b568dc62eac78c46cbba30cb751008']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j02_live_coding_task.py::test_p22_j02_live_coding_task`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/phase22-j02-live-windows-008/result.json` — exists=true, recorded_head=`5a4583e790b568dc62eac78c46cbba30cb751008`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/tools/codex_pm_router.py::validate_compiled_package` succeeds and `harness/lib/plan_validator.py::compile_and_stamp` emits a valid plan certificate/gate ledger.

### P22-REPAIR-015 — Workflow :: Search Strategy Formation

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J05
- Expected behavior: Turns the requirement contract into technical themes, source families, queries, time horizons, counter-signals, diversity goals, and coverage targets.
- Expected output: A discovery request/strategy and ranked candidate set with channel, score, rationale, dedup and fetch status.
- Recorded observation: Validated one topic and two anchors against Semantic Scholar.
- Production entrypoints: harness/plugins/autosci/backends/literature_discover.py::discover_literature, _score_candidate, _finalize_candidates; harness/lib/research/evaluator.py::source_requirements_for_profile
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['bce2b978008a14d337ff6040a2fabc71ce3e7ae5']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j05_literature_discovery.py::test_p22_j05_literature_discovery`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/J05-live-provider-001/result.json` — exists=true, recorded_head=`bce2b978008a14d337ff6040a2fabc71ce3e7ae5`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/plugins/autosci/backends/literature_discover.py::discover_literature` accepts supported modes and emits candidates conforming to `harness/schemas/evidence/literature_discovery.v1.schema.json`.

### P22-REPAIR-016 — Workflow :: Multi-Source Signal Discovery

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J05
- Expected behavior: Uses parallel research agents to search open-source projects, papers, patents, standards, experts, think tanks, industry reports, big-tech dynamics, technical communities, the open web, and authorized internal history.
- Expected output: Deduplicated literature candidates with identifiers, titles, source channels, ranking rationales, and fetch status.
- Recorded observation: Only Semantic Scholar search and reference channels were exercised.
- Production entrypoints: harness/plugins/autosci/backends/literature_discover.py::discover_literature; harness/plugins/autosci/adapters/autosci_to_literature_discovery.py::convert
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['bce2b978008a14d337ff6040a2fabc71ce3e7ae5']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j05_literature_discovery.py::test_p22_j05_literature_discovery`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/J05-live-provider-001/result.json` — exists=true, recorded_head=`bce2b978008a14d337ff6040a2fabc71ce3e7ae5`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/plugins/autosci/backends/literature_discover.py::discover_literature` exercises supported source channels and `harness/plugins/autosci/adapters/autosci_to_literature_discovery.py::convert` emits the evidence envelope.

### P22-REPAIR-017 — Workflow :: Source Qualification

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J05
- Expected behavior: Screens discovered material for intent relevance, authority, recency, independence, incentives, duplication, access limits, and potential bias.
- Expected output: Qualified/ranked sources, authority/diversity/type metrics, dedup decisions, limitations, and pass/repairable/hard-fail closeout.
- Recorded observation: Qualification was limited to identity, title, year, channel, uniqueness, and negative-ID checks.
- Production entrypoints: harness/plugins/autosci/backends/literature_discover.py::_score_candidate, _dedupe_candidates; harness/lib/research/evaluator.py::evaluate_retrieval_closeout
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['bce2b978008a14d337ff6040a2fabc71ce3e7ae5']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j05_literature_discovery.py::test_p22_j05_literature_discovery`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/J05-live-provider-001/result.json` — exists=true, recorded_head=`bce2b978008a14d337ff6040a2fabc71ce3e7ae5`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/lib/research/evaluator.py::_source_authority_metrics, _source_diversity_metrics, _source_type_validation_metrics, evaluate_retrieval_closeout` produces qualifying metrics and verdicts.

### P22-REPAIR-018 — Workflow :: Technical Signal Extraction

- Recorded status: `FAIL`
- Priority: `P0_BLOCKER`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_EXECUTABLE_DIAGNOSTIC`
- Evidence basis: NT-literature
- Expected behavior: Extracts claims, data, methods, mechanisms, results, benchmarks, limitations, failures, dependencies, adoption signals, and unresolved questions.
- Expected output: Research claims, methods, evidence links, supporting/contradicting relationships, limitations, and evidence gaps.
- Recorded observation: Real sources were found, but the pipeline did not extract source-linked technical signals. The richer research route failed in the Windows planner with access denied.
- Production entrypoints: harness/lib/research/grounded_synthesis.py; harness/lib/research/claim_compiler.py; harness/plugins/autosci/bin/autosci_bridge.py::_paper_claims_raw, _paper_methods_raw
- Freshness warnings:
  - Evidence was recorded against another commit: ['62568bfeef0729f42c0eb9367bc358afe90b1660']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_p22_nt_literature_analysis.py::test_phase22_not_tested_literature_signal_and_trend_validation`
- Evidence paths:
  - `.codex-tmp/phase22-worker-results/NT-literature/result.json` — exists=true, recorded_head=`62568bfeef0729f42c0eb9367bc358afe90b1660`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/lib/research/grounded_synthesis.py::_validated_evidence_links, _validated_evidence_gaps` and `harness/plugins/autosci/bin/autosci_bridge.py::_paper_claims_raw, _paper_methods_raw` emit traceable signals.

### P22-REPAIR-019 — Workflow :: Signal Organization

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J05
- Expected behavior: Normalizes signals, binds provenance, clusters related findings, and maps convergence, divergence, dependencies, and opposing viewpoints.
- Expected output: Merged source/evidence packs, normalized IDs, evidence links, claim-evidence alignments, gaps, and controversy/literature maps.
- Recorded observation: Validated deduplication and provenance for two literature lists only.
- Production entrypoints: harness/lib/research/grounded_synthesis.py::_merge_source_packs, _validated_evidence_links, compile_grounded_report; harness/lib/research/claim_compiler.py
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['bce2b978008a14d337ff6040a2fabc71ce3e7ae5']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j05_literature_discovery.py::test_p22_j05_literature_discovery`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/J05-live-provider-001/result.json` — exists=true, recorded_head=`bce2b978008a14d337ff6040a2fabc71ce3e7ae5`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/lib/research/grounded_synthesis.py::_merge_source_packs, _validated_evidence_links` and `harness/lib/research/claim_compiler.py::ClaimEvidenceAlignment` create organized relationships.

### P22-REPAIR-020 — Workflow :: Trend & Gap Analysis

- Recorded status: `FAIL`
- Priority: `P0_BLOCKER`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_EXECUTABLE_DIAGNOSTIC`
- Evidence basis: NT-literature
- Expected behavior: Detects momentum, decay, contradictions, bottlenecks, missing capabilities, abandoned directions, and technical white spaces.
- Expected output: Evidence-gap lists, controversy review, literature/trend summaries, bottleneck-like limitations, and follow-up search needs.
- Recorded observation: The source search worked, but the report contained no cross-source trend. The richer research route failed before analysis.
- Production entrypoints: harness/lib/research/grounded_synthesis.py::_validated_evidence_gaps; harness/lib/research/survey/quality.py::_build_literature_map, _build_controversy_review; harness/lib/research/survey/evidence_pack.py::build_evidence_packs
- Freshness warnings:
  - Evidence was recorded against another commit: ['62568bfeef0729f42c0eb9367bc358afe90b1660']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_p22_nt_literature_analysis.py::test_phase22_not_tested_literature_signal_and_trend_validation`
- Evidence paths:
  - `.codex-tmp/phase22-worker-results/NT-literature/result.json` — exists=true, recorded_head=`62568bfeef0729f42c0eb9367bc358afe90b1660`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/lib/research/grounded_synthesis.py::_validated_evidence_gaps` and `harness/lib/research/survey/quality.py::_build_literature_map, _build_controversy_review` emit gap/trend-related diagnostics.

### P22-REPAIR-021 — Workflow :: Idea Generation

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J06
- Expected behavior: Expands a diverse candidate set from signal clusters, gaps, adjacencies, cross-domain transfers, and contrarian combinations while retaining initial supporting and opposing evidence.
- Expected output: Idea candidates with title, hypothesis, approach, origin evidence IDs, novelty hypothesis, status, and selection rationale.
- Recorded observation: Basic idea generation worked with local evidence, but live literature search and novelty services were not tested.
- Production entrypoints: harness/plugins/autosci/backends/idea_source.py::collect_idea_sources, build_idea_candidates, _candidate_status, _apply_max_ideas_selection
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j06_idea_generation.py::test_p22_j06_idea_generation`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/journey-fail-repair/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/plugins/autosci/backends/idea_source.py::collect_idea_sources, build_idea_candidates` emits schema-valid candidates with source evidence.

### P22-REPAIR-022 — Workflow :: Search Coverage Review

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J05
- Expected behavior: Tests source-family, technical, geographic, temporal, viewpoint, and counter-evidence coverage before the candidate space is allowed to narrow.
- Expected output: Coverage metrics, source/claim/contradiction diagnostics, pass/fail or repair recommendations, and explicit missing-source/evidence items.
- Recorded observation: Coverage review was limited to two Semantic Scholar modes.
- Production entrypoints: harness/lib/research/survey/evaluator.py::evaluate_survey; harness/lib/research/survey/quality.py::_build_source_coverage; harness/lib/research/evaluator.py::evaluate_artifacts
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['bce2b978008a14d337ff6040a2fabc71ce3e7ae5']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j05_literature_discovery.py::test_p22_j05_literature_discovery`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/J05-live-provider-001/result.json` — exists=true, recorded_head=`bce2b978008a14d337ff6040a2fabc71ce3e7ae5`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/lib/research/survey/evaluator.py::evaluate_survey` and `harness/lib/research/evaluator.py::evaluate_artifacts` emit coverage and verdict metrics.

### P22-REPAIR-023 — Workflow :: Candidate Consolidation

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J06
- Expected behavior: Combines parallel search outputs, resolves semantic duplicates, and preserves variants whose assumptions, evidence, or opportunity boundaries materially differ.
- Expected output: Candidates marked available/duplicate/failed-memory with deterministic bounded selection and reasons.
- Recorded observation: Ideas were generated, but none included a complete risk, falsifiability, validation, and smallest-experiment plan.
- Production entrypoints: harness/plugins/autosci/backends/idea_source.py::_overlaps_known, _candidate_status, _apply_max_ideas_selection, build_idea_candidates
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j06_idea_generation.py::test_p22_j06_idea_generation`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/journey-fail-repair/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/plugins/autosci/backends/idea_source.py::_overlaps_known, _candidate_status, _apply_max_ideas_selection` produces deterministic consolidation statuses.

### P22-REPAIR-024 — Workflow :: Idea Identification

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J06
- Expected behavior: Converts meaningful signal combinations and gaps into discrete candidate ideas with a recognizable technical or user value proposition.
- Expected output: Discrete IdeaCandidate records with title, hypothesis, approach, origin evidence, novelty hypothesis, and status.
- Recorded observation: Ideas were generated, but none included a complete risk, falsifiability, validation, and smallest-experiment plan.
- Production entrypoints: harness/plugins/autosci/backends/idea_source.py::build_idea_candidates; harness/plugins/autosci/adapters/autosci_to_idea_candidate.py::convert
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j06_idea_generation.py::test_p22_j06_idea_generation`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/journey-fail-repair/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/plugins/autosci/backends/idea_source.py::build_idea_candidates` and `harness/plugins/autosci/adapters/autosci_to_idea_candidate.py::convert` emit schema-valid candidates.

### P22-REPAIR-025 — Workflow :: Idea Card Formation

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J06
- Expected behavior: Forms the governing Idea Card with the candidate’s opportunity, relevance, linked evidence, assumptions, novelty, uncertainty, risks, and open questions; evidence formation is part of this card.
- Expected output: Combined candidate/evaluation artifacts with novelty, feasibility, recommendation, risks, evidence IDs, and limitations.
- Recorded observation: Ideas were generated, but none included a complete risk, falsifiability, validation, and smallest-experiment plan.
- Production entrypoints: harness/plugins/autosci/adapters/autosci_to_idea_candidate.py::convert; harness/plugins/autosci/adapters/autosci_to_idea_evaluation.py::convert; harness/plugins/autosci/backends/novelty_review.py::evaluate_novelty_and_review
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j06_idea_generation.py::test_p22_j06_idea_generation`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/journey-fail-repair/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/schemas/evidence/idea_candidate.v1.schema.json` plus `idea_evaluation.v1.schema.json` validate artifacts produced by their AutoSci adapters.

### P22-REPAIR-029 — Workflow :: Opportunity Portfolio Prioritization

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J06
- Expected behavior: Ranks and selects a bounded, diverse opportunity portfolio using transparent criteria and records why other directions were deferred or rejected.
- Expected output: A bounded selected-candidate list with deterministic selection status; no rich portfolio scorecard or diversity objective is found.
- Recorded observation: Ideas were generated, but none included a complete risk, falsifiability, validation, and smallest-experiment plan.
- Production entrypoints: harness/plugins/autosci/backends/idea_source.py::_apply_max_ideas_selection; harness/plugins/autosci/backends/novelty_review.py::evaluate_novelty_and_review
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j06_idea_generation.py::test_p22_j06_idea_generation`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/journey-fail-repair/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Partial: `harness/plugins/autosci/backends/idea_source.py::_apply_max_ideas_selection` bounds selection; novelty review provides advance/revise/reject/inconclusive recommendations.

### P22-REPAIR-030 — Workflow :: Research Question & Technical Claim Formation

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J06
- Expected behavior: turn passed opportunity to specific research questions and testable technical claims, clarify research object, expected effects and applicable situations.
- Expected output: ResearchClaims evidence containing claims, source references, extraction limitations, and heuristic testability status.
- Recorded observation: Ideas were generated, but none included a complete risk, falsifiability, validation, and smallest-experiment plan.
- Production entrypoints: harness/plugins/autosci/bin/autosci_bridge.py::_paper_claims_raw, _claim_testability; harness/plugins/autosci/adapters/autosci_to_research_claims.py::convert
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j06_idea_generation.py::test_p22_j06_idea_generation`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/journey-fail-repair/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/plugins/autosci/bin/autosci_bridge.py::_paper_claims_raw, _claim_testability` and `harness/plugins/autosci/adapters/autosci_to_research_claims.py::convert` emit schema-valid claims.

### P22-REPAIR-031 — Workflow :: Claim, Evidence, Data & Method Modeling

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J06
- Expected behavior: Set up claim, data, means of measuring, approaches, and the relationship between baseline and missing evidence
- Expected output: ResearchClaims, ResearchMethod, and ExperimentPlan artifacts with traceable evidence and measurement/procedure definitions.
- Recorded observation: Ideas were generated, but none included a complete risk, falsifiability, validation, and smallest-experiment plan.
- Production entrypoints: harness/plugins/autosci/adapters/autosci_to_research_claims.py::convert; harness/plugins/autosci/adapters/autosci_to_research_method.py::convert; harness/plugins/autosci/adapters/autosci_to_experiment_plan.py::convert
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j06_idea_generation.py::test_p22_j06_idea_generation`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/journey-fail-repair/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/schemas/evidence/experiment_plan.v1.schema.json` validates objective/hypothesis/variables/metrics/procedure/expected artifacts and AutoSci claim/method adapters validate their evidence.

### P22-REPAIR-033 — Workflow :: Falsifiability Screening & Hypothesis Contracting

- Recorded status: `FAIL`
- Priority: `P0_BLOCKER`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_EXECUTABLE_DIAGNOSTIC`
- Evidence basis: P22-J06
- Expected behavior: Determine if the hypothesis can be overthrowed by obtained data, or methods for the experiment. Also form the contract for testing the hypothesis
- Expected output: Testability classification plus ExperimentPlan contract that defines how evidence could support, refute, or leave the hypothesis inconclusive.
- Recorded observation: The real task ran, but generated candidates lacked complete falsifiability fields.
- Production entrypoints: harness/plugins/autosci/bin/autosci_bridge.py::_claim_testability; harness/plugins/autosci/adapters/autosci_to_experiment_plan.py::convert; harness/schemas/evidence/experiment_plan.v1.schema.json
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j06_idea_generation.py::test_p22_j06_idea_generation`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/journey-fail-repair/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/plugins/autosci/bin/autosci_bridge.py::_claim_testability` classifies claims and `harness/plugins/autosci/adapters/autosci_to_experiment_plan.py::convert` emits the governed plan.

### P22-REPAIR-034 — Workflow :: Verification-Ready POC Design

- Recorded status: `FAIL`
- Priority: `P0_BLOCKER`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_EXECUTABLE_DIAGNOSTIC`
- Evidence basis: P22-J06; P22-J07
- Expected behavior: Design the minimum viable verification plan. Define input, output, evidence requirements, index requirement for success, success/fail criteria, resource needed, restraints and verification steps.
- Expected output: Schema-valid ExperimentPlan suitable for governed implementation/execution and later ExperimentResult/ClaimVerdict comparison.
- Recorded observation: J07 provides partial downstream experiment evidence, but the upstream J06 design contract still fails.
- Production entrypoints: harness/plugins/autosci/adapters/autosci_to_experiment_plan.py::convert; harness/schemas/evidence/experiment_plan.v1.schema.json
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j06_idea_generation.py::test_p22_j06_idea_generation`
  - `tests/journeys/phase22/code/test_j07_experiment_lifecycle.py::test_p22_j07_experiment_lifecycle`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/journey-fail-repair/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/schemas/evidence/experiment_plan.v1.schema.json` validates required objective/hypothesis/variables/metrics/procedure/approval/expected artifacts and the adapter adds baseline/allowlist/resource limits.

### P22-REPAIR-036 — Workflow :: POC Construction

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J02; P22-J07
- Expected behavior: Construct the code, model, prompt, etc. for validating the POC.
- Expected output: Implementation artifacts/patches plus logs, manifests, and evidence required by downstream tests and verification.
- Recorded observation: The experiment ran but ended without a clear final state; the earlier workflow also did not create the older eval.md evidence file.
- Production entrypoints: harness/tools/codex_pm_router.py::_short_task_graph, _standard_task_graph, _node_enrichment; harness/lib/graph_node_dispatcher.py
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['5a4583e790b568dc62eac78c46cbba30cb751008']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j02_live_coding_task.py::test_p22_j02_live_coding_task`
  - `tests/journeys/phase22/code/test_j07_experiment_lifecycle.py::test_p22_j07_experiment_lifecycle`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/phase22-j02-live-windows-008/result.json` — exists=true, recorded_head=`5a4583e790b568dc62eac78c46cbba30cb751008`
  - `.codex-tmp/phase22-worker-results/journey-fail-repair/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/tools/codex_pm_router.py::_short_task_graph, _standard_task_graph` creates ImplementationWorker nodes and `harness/lib/graph_node_dispatcher.py` publishes their artifacts.

### P22-REPAIR-037 — Workflow :: POC Component Integration & Configuration

- Recorded status: `FAIL`
- Priority: `P0_BLOCKER`
- Freshness: `LIKELY_STALE_J21_SOURCE_NOW_RECOMMENDS_PASS_OR_LIMITED`
- Confidence: `LOW_UNTIL_RERUN`
- Evidence basis: P22-J21
- Expected behavior: Connect each part into a POC workable E2E, and prepare for the smoke test.
- Expected output: Integrated workspace artifacts plus task-node outputs and an evaluation-ready handoff.
- Recorded observation: J21 reported a completed run, but it did not prove that the approved command actually executed. The minimum integration condition was not met.
- Production entrypoints: harness/tools/codex_pm_router.py::_standard_task_graph, _node_enrichment; harness/lib/plan_validator.py; harness/lib/graph_node_dispatcher.py
- Freshness warnings:
  - Current J21 source recommends PASS or PASS_WITH_KNOWN_LIMITATIONS for this row, while the register retains an older FAIL.
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['bce2b978008a14d337ff6040a2fabc71ce3e7ae5']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j21_experiment_build_handoff.py::test_p22_j21_real_experiment_build_and_handoff`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/J21-experiment-build-001/result.json` — exists=true, recorded_head=`bce2b978008a14d337ff6040a2fabc71ce3e7ae5`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/tools/codex_pm_router.py::_standard_task_graph` orders ImplementationWorker→TestRunner→Verifier and `harness/lib/plan_validator.py` validates graph legality.

### P22-REPAIR-038 — Workflow :: POC Functional Readiness Validation

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J02; P22-J07
- Expected behavior: Perform smoke test run, make sure POC runs, outputs are in the right format, and faliures can be observed.
- Expected output: Test report, session log, patch diff where relevant, artifact manifest, verifier result, and pass/fail/inconclusive evidence.
- Recorded observation: The experiment ran but ended without a clear final state; the earlier workflow also did not create the older eval.md evidence file.
- Production entrypoints: harness/lib/graph_node_dispatcher.py::_node_evaluation_plan and artifact publication; harness/lib/plan_validator.py gate validation
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['5a4583e790b568dc62eac78c46cbba30cb751008']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j02_live_coding_task.py::test_p22_j02_live_coding_task`
  - `tests/journeys/phase22/code/test_j07_experiment_lifecycle.py::test_p22_j07_experiment_lifecycle`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/phase22-j02-live-windows-008/result.json` — exists=true, recorded_head=`5a4583e790b568dc62eac78c46cbba30cb751008`
  - `.codex-tmp/phase22-worker-results/journey-fail-repair/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/lib/graph_node_dispatcher.py` requires `handoff_md`, `session_log`, and for code/test tasks `patch_diff`/`test_report`, then publishes an artifact manifest.

### P22-REPAIR-039 — Workflow :: Testable POC Artifact Consolidation & Benchmark Handoff

- Recorded status: `FAIL`
- Priority: `P0_BLOCKER`
- Freshness: `LIKELY_STALE_J21_SOURCE_NOW_RECOMMENDS_PASS_OR_LIMITED`
- Confidence: `LOW_UNTIL_RERUN`
- Evidence basis: P22-J21
- Expected behavior: Organize final POC, config, dependencies, runtime, known constraints and necessary explanations, form an artifact that is benchmark-ready.
- Expected output: Artifact manifest and handoff/evaluation plan linking the runnable implementation to evidence and planned benchmark inputs.
- Recorded observation: J21 produced handoff text, but the downstream checker received no valid product package and failed. The handoff was not usable.
- Production entrypoints: harness/lib/graph_node_dispatcher.py::_node_evaluation_plan and manifest publication; harness/tools/codex_pm_router.py::_node_enrichment
- Freshness warnings:
  - Current J21 source recommends PASS or PASS_WITH_KNOWN_LIMITATIONS for this row, while the register retains an older FAIL.
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['bce2b978008a14d337ff6040a2fabc71ce3e7ae5']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j21_experiment_build_handoff.py::test_p22_j21_real_experiment_build_and_handoff`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/J21-experiment-build-001/result.json` — exists=true, recorded_head=`bce2b978008a14d337ff6040a2fabc71ce3e7ae5`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/lib/graph_node_dispatcher.py` publishes artifact manifests and requires handoff/test evidence; planner nodes declare expected inputs/outputs.

### P22-REPAIR-040 — Workflow :: Benchmark Framing

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J03
- Expected behavior: Define the claims to be compared, the runtime for the benchmark, baseline used, reference system, and version history.
- Expected output: BenchmarkResult/Report metadata and a comparison frame linking current versus baseline/reference.
- Recorded observation: J03 recorded the benchmark scope, threshold, weights, and scenarios. Baseline and version-history variants were not tested.
- Production entrypoints: core/benchmark/schema.ts; core/benchmark/reporter.ts::collectMetadata, createBenchmarkResult; core/benchmark/trend.ts::getBaseline, setBaseline
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j03_platform_benchmark.py::test_p22_j03_platform_benchmark`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/journey-fail-repair/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `core/benchmark/reporter.ts::collectMetadata, createBenchmarkResult` and `core/benchmark/trend.ts::getBaseline, setBaseline` produce a framed benchmark.

### P22-REPAIR-041 — Workflow :: Benchmark Protocol & Asset Preparation

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J03
- Expected behavior: define workload, dataset, figures, repetitions, resource limits, methods for data collection, comparision rules, and reletive assets.
- Expected output: Executable caller protocol plus validated benchmark configuration and prepared assets/sample collection inputs.
- Recorded observation: J03 used an isolated harness and produced JSON, Markdown, and evidence files. Repetition and resource-limit variants were not tested.
- Production entrypoints: skills/benchmark/SKILL.md; core/benchmark/schema.ts::BenchmarkConfig, BENCHMARK_PRESETS
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j03_platform_benchmark.py::test_p22_j03_platform_benchmark`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/journey-fail-repair/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `skills/benchmark/SKILL.md` defines protocol guidance and `core/benchmark/schema.ts::BenchmarkConfig, BENCHMARK_PRESETS` represents supported statistics settings.

### P22-REPAIR-043 — Workflow :: Metrics & Run Evidence Collection

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J03
- Expected behavior: Collect benchmark results (index, log, run condition, status, faliure lgos, resource used, and provenance, to make sure result is trackable)
- Expected output: BenchmarkResult with raw data/statistics/metadata and JSON, Markdown, CSV, or raw-data exports.
- Recorded observation: J03 saved scenario scores, failed checks, command logs, and evidence files. Detailed resource consumption was not measured.
- Production entrypoints: core/benchmark/reporter.ts::collectMetadata, createBenchmarkResult, exportJSON, exportMarkdown, exportCSV, exportRawData; core/benchmark/statistics.ts::computeStatistics
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j03_platform_benchmark.py::test_p22_j03_platform_benchmark`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/journey-fail-repair/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `core/benchmark/reporter.ts::collectMetadata, createBenchmarkResult, exportJSON, exportMarkdown, exportCSV, exportRawData` emits traceable benchmark artifacts.

### P22-REPAIR-044 — Workflow :: Comparative Result Analysis & Benchmark Result Packaging

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J03
- Expected behavior: Compare POC and baseline, organize info and form benchmark result.
- Expected output: ComparisonResult, BenchmarkReport, statistical significance/effect/speedup, regression flags, trend data, and JSON/Markdown/CSV exports.
- Recorded observation: J03 correctly packaged the score and explained every failed check. Broader POC-to-baseline comparisons were not tested.
- Production entrypoints: core/benchmark/reporter.ts::compareBenchmarks, generateReport, exportJSON, exportMarkdown, exportCSV; core/benchmark/statistics.ts; core/benchmark/trend.ts
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j03_platform_benchmark.py::test_p22_j03_platform_benchmark`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/journey-fail-repair/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `core/benchmark/reporter.ts::compareBenchmarks, generateReport` and `core/benchmark/trend.ts::buildTrendData, detectRegressions` create packaged comparative evidence.

### P22-REPAIR-045 — Workflow :: Evaluation Scope & Evidence Assembly

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J08/P22-J22 final integration
- Expected behavior: Clarify the strategy and standard used for this evaluation, collect benchmark results, claims, and reletive evidence
- Expected output: An evaluation input set plus coverage/source/claim metrics and a review or closeout verdict.
- Recorded observation: Current reviewer/evidence journeys completed through production review/refine entrypoints, but full evidence-boundary variants and provider-independence remain limited.
- Production entrypoints: harness/lib/research/evaluator.py::evaluate_artifacts, evaluate_final_closeout; harness/plugins/autosci adapters
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['bce2b978008a14d337ff6040a2fabc71ce3e7ae5']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j08_claim_verification.py::test_p22_j08_claim_verification`
  - `tests/journeys/phase22/code/test_j22_evidence_review_followup.py::test_p22_j22_real_evidence_review_and_followup`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/journey-fail-repair/result.json` — exists=true, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/J22-evidence-review-001/result.json` — exists=true, recorded_head=`bce2b978008a14d337ff6040a2fabc71ce3e7ae5`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/lib/research/evaluator.py::evaluate_artifacts` accepts artifacts and calculates evidence/claim/citation/coverage/source metrics.

### P22-REPAIR-047 — Workflow :: Experimental, Reasoning & External Validity Review

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J08/P22-J22 final integration
- Expected behavior: Check experiment design, and if the result make sense in external world
- Expected output: ArtifactReview findings/score/recommendation plus claim/evidence validity diagnostics and explicit limitations.
- Recorded observation: The repaired reviewer path now exercises supported and overreach cases through production entrypoints. Same-provider independence and broader external-validity variants remain limitations.
- Production entrypoints: harness/lib/research/evaluator.py; harness/schemas/evidence/artifact_review.v1.schema.json; harness/plugins/autosci artifact-review adapter/backend
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['bce2b978008a14d337ff6040a2fabc71ce3e7ae5']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j08_claim_verification.py::test_p22_j08_claim_verification`
  - `tests/journeys/phase22/code/test_j22_evidence_review_followup.py::test_p22_j22_real_evidence_review_and_followup`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/journey-fail-repair/result.json` — exists=true, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/J22-evidence-review-001/result.json` — exists=true, recorded_head=`bce2b978008a14d337ff6040a2fabc71ce3e7ae5`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/schemas/evidence/artifact_review.v1.schema.json` represents findings/recommendations and `harness/lib/research/evaluator.py` provides deterministic validity metrics.

### P22-REPAIR-048 — Workflow :: Claim & Acceptance-Criteria Comparison

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J08/P22-J22 final integration
- Expected behavior: Compare the benchmakr with technical claims, hypothesis and the original accept criteria
- Expected output: ClaimVerdict and/or acceptance verdict indicating support level, confidence, basis, evidence, and limitations.
- Recorded observation: The final journey suite passed after evidence bundle repair and reviewer integration. The accepted proof covers the current supported/overreach case, not every claim family.
- Production entrypoints: harness/plugins/autosci/adapters/autosci_to_claim_verdict.py::convert; harness/schemas/evidence/claim_verdict.v1.schema.json; harness/schemas/evidence/experiment_result.v1.schema.json
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['bce2b978008a14d337ff6040a2fabc71ce3e7ae5']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j08_claim_verification.py::test_p22_j08_claim_verification`
  - `tests/journeys/phase22/code/test_j22_evidence_review_followup.py::test_p22_j22_real_evidence_review_and_followup`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/journey-fail-repair/result.json` — exists=true, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/J22-evidence-review-001/result.json` — exists=true, recorded_head=`bce2b978008a14d337ff6040a2fabc71ce3e7ae5`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/schemas/evidence/experiment_result.v1.schema.json` and `claim_verdict.v1.schema.json` validate outcomes; `harness/plugins/autosci/adapters/autosci_to_claim_verdict.py::convert` packages the comparison.

### P22-REPAIR-049 — Workflow :: Verdict, Blocker & Residual-Risk Classification

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J08/P22-J22 final integration
- Expected behavior: Tag the hypothesis as pass/fail/inconclusive/conditionally acceptable/etc.
- Expected output: Final/closeout classification, recommendation, findings/blockers, confidence/basis, limitations, and residual-risk notes.
- Recorded observation: Current evidence-review/refine coverage records overreach follow-up through production CLI paths. Residual-risk taxonomy breadth remains limited.
- Production entrypoints: harness/lib/research/evaluator.py::evaluate_final_closeout; harness/schemas/evidence/claim_verdict.v1.schema.json; harness/schemas/evidence/artifact_review.v1.schema.json
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['bce2b978008a14d337ff6040a2fabc71ce3e7ae5']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j08_claim_verification.py::test_p22_j08_claim_verification`
  - `tests/journeys/phase22/code/test_j22_evidence_review_followup.py::test_p22_j22_real_evidence_review_and_followup`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/journey-fail-repair/result.json` — exists=true, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/J22-evidence-review-001/result.json` — exists=true, recorded_head=`bce2b978008a14d337ff6040a2fabc71ce3e7ae5`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/lib/research/evaluator.py::evaluate_final_closeout` emits pass/repairable_fail/hard_fail and claim/artifact schemas carry supported/revise/inconclusive outcomes and risks.

### P22-REPAIR-051 — Workflow :: Delivery Planning & Evidence Handoff

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J09 final integration
- Expected behavior: Define the target audience, delivery format, delivery content, evidence index, permission, and a handoff checklist
- Expected output: Report/publication plan and bundle metadata linking files to source report/evidence with approval requirements and limitations.
- Recorded observation: J09 passed in the final journey suite after using a hash/span-consistent local proof bundle through production AutoSci paper/report commands. Live review, HITL final approval, and provider-backed compile remain limitations.
- Production entrypoints: harness/plugins/autosci/bin/autosci_bridge.py::_action_plan_report, _approval_contract, _write_phase14_publication_sidecars; harness/plugins/autosci/adapters/autosci_to_publication_bundle.py::convert
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j09_report_delivery.py::test_p22_j09_report_delivery`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/journey-fail-repair/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/plugins/autosci/bin/autosci_bridge.py::_action_plan_report, _approval_contract` and publication sidecar generation produce delivery planning evidence.

### P22-REPAIR-052 — Workflow :: User-Facing Deliverable Generation

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J09
- Expected behavior: generate the report the user needs, including proposal, technical roadmap, investment recommendation, paper, poster, rebuttal or visualization, etc.
- Expected output: ScientificReport and PublicationBundle files such as paper drafts/compiled paper, poster, rebuttal, survey/report, plus provenance/limitations.
- Recorded observation: A readable report was created, but LLM review, final approval, and the final compile path were unavailable or incomplete.
- Production entrypoints: harness/plugins/autosci/bin/autosci_bridge.py::_action_write_report, _action_build_poster, _action_draft_rebuttal; harness/plugins/autosci/adapters/autosci_to_scientific_report.py::convert
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j09_report_delivery.py::test_p22_j09_report_delivery`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/journey-fail-repair/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/plugins/autosci/bin/autosci_bridge.py::_action_write_report, _action_build_poster, _action_draft_rebuttal` and report/publication adapters emit schema-valid artifacts.

### P22-REPAIR-053 — Workflow :: Deliverable, Reusable Asset & Knowledge Packaging

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J09 final integration
- Expected behavior: Organize all the deliverables.
- Expected output: PublicationBundle plus scientific report and sidecars/manifests linking deliverables to reusable evidence/assets.
- Recorded observation: The final J09 path produced report and proof-bundle artifacts through production entrypoints. Reusable packaging, live reviewer, and final compile variants remain limited.
- Production entrypoints: harness/plugins/autosci/adapters/autosci_to_publication_bundle.py::convert; harness/plugins/autosci/bin/autosci_bridge.py::_write_phase14_publication_sidecars
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j09_report_delivery.py::test_p22_j09_report_delivery`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/journey-fail-repair/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: `harness/schemas/evidence/publication_bundle.v1.schema.json` validates publication type/files/source report/evidence IDs and `scientific_report.v1.schema.json` preserves sections/provenance/limitations.

### P22-REPAIR-054 — Workflow :: Authorized Distribution, Knowledge Transfer & Lifecycle Closure

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J09 final integration
- Expected behavior: Send the deliverable to the user, confirme acceptance, complete artifact transferring, save success/faliure experience, and close the current workflow lifecycle.
- Expected output: Authorized submission/delivery result with evidence and retained artifacts; a general acceptance/knowledge-transfer/experience-closeout record is not fully implemented.
- Recorded observation: The handoff/report path completed for local artifacts in the final journey suite. External distribution, explicit HITL approval, and long-term lifecycle closure remain untested.
- Production entrypoints: harness/plugins/autosci/bin/autosci_bridge.py::_approval_contract, _publication_submission_boundary, _daily_arxiv_final_provider_delivery_boundary; harness/lib/policy/action_policy.py
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j09_report_delivery.py::test_p22_j09_report_delivery`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/journey-fail-repair/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Partial: `harness/plugins/autosci/bin/autosci_bridge.py::_approval_contract, _publication_submission_boundary, _daily_arxiv_final_provider_delivery_boundary` enforce specific authorized delivery paths.

### P22-REPAIR-055 — Foundation :: Capability Capsule Definition & Assembly

- Recorded status: `FAIL`
- Priority: `P0_BLOCKER`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_EXECUTABLE_DIAGNOSTIC`
- Evidence basis: No journey: atomic diagnostic only
- Expected behavior: Define the capsule’s contract, metadata, dependencies, resources, and executable entry points.
- Expected output: Normalized capsule dictionary plus semantic/schema validation errors or a RegistryEntry.
- Recorded observation: One detailed executable test failed, so this feature cannot be marked as passed.
- Production entrypoints: harness/lib/capability_capsules.py: normalize_capability_capsule(), load_capability_capsule_manifest(), validate_capability_capsule_semantics(), validate_capability_capsule()
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/foundation/capability_capsules/test_capability_capsule_definition_atomic.py::test_atomic_capability_capsule_definition_assembly__duplicate_identity_version`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `tests/platform/phase22/atomic_feature_matrix.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Validated normalized manifest matches harness/schemas/draft/capability-capsule.v1.draft.json and tests/harness/test_capability_capsules.py passes representative valid/invalid manifests.

### P22-REPAIR-057 — Foundation :: Capability Discovery, Scoring & Selection

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J06
- Expected behavior: Find and rank eligible capsules by compatibility, policy, quality, cost, and performance.
- Expected output: Candidate capsule list/plan with scores or a resolved capsule containing bindings, effects, guards, resources, and rationale.
- Recorded observation: Ideas were generated, but none included a complete risk, falsifiability, validation, and smallest-experiment plan.
- Production entrypoints: harness/lib/capability_capsules.py: classify_task_goal(), query_capability_capsules(), default_capability_plan_for_logical_operator(), resolve_capability_capsule_for_task()
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j06_idea_generation.py::test_p22_j06_idea_generation`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/journey-fail-repair/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Resolved plan identifies a registered capsule, explains rejected candidates, preserves effects/bindings, and passes tests/harness/test_capability_capsules.py and test_apo_plan_compiler.py.

### P22-REPAIR-066 — Foundation :: Contract, Schema & Artifact Conformance Evaluator

- Recorded status: `FAIL`
- Priority: `P0_BLOCKER`
- Freshness: `LIKELY_STALE_J21_SOURCE_NOW_RECOMMENDS_PASS_OR_LIMITED`
- Confidence: `LOW_UNTIL_RERUN`
- Evidence basis: P22-J21
- Expected behavior: Verifies input/output contracts, schemas, scopes, required artifacts, proof obligations, structural completeness, and admissibility of submitted evidence.
- Expected output: Structured gate result or acceptance verdict with status, reasons, warnings, and evidence references.
- Recorded observation: J21 did not reject the blocked run or prove semantic and unsupported-claim checks. Its three minimum conformance assertions failed.
- Production entrypoints: harness/lib/contract_gate_executor.py: execute_gate(); harness/lib/verification_gate.py: VerificationGate; harness/lib/workflow_contract.py: compile_checks()
- Freshness warnings:
  - Current J21 source recommends PASS or PASS_WITH_KNOWN_LIMITATIONS for this row, while the register retains an older FAIL.
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['bce2b978008a14d337ff6040a2fabc71ce3e7ae5']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j21_experiment_build_handoff.py::test_p22_j21_real_experiment_build_and_handoff`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/J21-experiment-build-001/result.json` — exists=true, recorded_head=`bce2b978008a14d337ff6040a2fabc71ce3e7ae5`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Verdict conforms to acceptance-verdict schema, cites artifacts, and negative fixtures fail in tests/qa_audit/.../test_evidence_schema_contracts.py and harness scientific evaluator tests.

### P22-REPAIR-067 — Foundation :: Engineering Correctness & Code Quality Evaluator

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J02
- Expected behavior: Combines automated unit, integration, regression, smoke, and end-to-end testing with static analysis, type checking, linting, maintainability checks, and architecture-boundary validation.
- Expected output: Per-check results plus pass/fail/blocked/inconclusive aggregate and artifact/log references.
- Recorded observation: The main workflow passed, but the older eval.md evidence file was not created; command logs and saved status are available instead.
- Production entrypoints: harness/lib/eval_runner.py: run_pack(); harness/lib/contract_gate_executor.py: execute_gate(); tests/ and tests/harness/ suites
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['5a4583e790b568dc62eac78c46cbba30cb751008']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j02_live_coding_task.py::test_p22_j02_live_coding_task`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/phase22-j02-live-windows-008/result.json` — exists=true, recorded_head=`5a4583e790b568dc62eac78c46cbba30cb751008`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Commands, exit codes, stdout/stderr tails, and verdict are captured; a pass requires all configured mandatory checks.

### P22-REPAIR-068 — Foundation :: Performance, Cost & Benchmark Evaluator

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J03
- Expected behavior: Measures quality, latency, throughput, resource usage, scalability, and cost, and compares results against defined baselines and regression thresholds.
- Expected output: BenchmarkRunResult, report, manifest/hashes, metrics, comparison, and verdict.
- Recorded observation: J03 calculated scenario and overall quality results correctly. Cost, throughput, and scalability measurements were not tested.
- Production entrypoints: harness/lib/benchmark/runner.py: _cmd_plan(), _cmd_run(), _cmd_report(); harness/lib/benchmark/reports.py: write_run_artifacts()
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j03_platform_benchmark.py::test_p22_j03_platform_benchmark`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/journey-fail-repair/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Report and manifest include measured metrics and hashes; tests/harness/benchmark/test_benchmark_report_schema.py and terminal-bench adapter tests validate artifacts.

### P22-REPAIR-069 — Foundation :: Security, Privacy, Compliance & IP Evaluator

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J09/P22-J24 final integration
- Expected behavior: Checks vulnerabilities, secrets, permissions, unsafe effects, sensitive-data exposure, regulatory and organizational policies, licenses, copyright, attribution, and permitted data use.
- Expected output: Security/privacy/policy findings, allowed/denied decision, warnings, and remediation evidence.
- Recorded observation: The final report/privacy journeys exercised local proof-bundle and privacy lifecycle surfaces. Hosted account/provider revocation, external channels, and legal/IP policy variants remain untested.
- Production entrypoints: core/security/checks/*.sh; core/config/privacy.ts; harness/lib/verification_gate.py; tests/repository/release/test_release_public_tree.sh and tests/qa_audit/.../test_misc_side_effect_gate_contracts.py
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['bce2b978008a14d337ff6040a2fabc71ce3e7ae5']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j09_report_delivery.py::test_p22_j09_report_delivery`
  - `tests/journeys/phase22/code/test_j24_privacy_lifecycle.py::test_p22_j24_real_privacy_lifecycle`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/journey-fail-repair/result.json` — exists=true, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/J24-privacy-lifecycle-001/result.json` — exists=true, recorded_head=`bce2b978008a14d337ff6040a2fabc71ce3e7ae5`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Deterministic finding names source/path/rule and denied cases cannot transition to pass; privacy scan and release-tree tests provide current evidence.

### P22-REPAIR-070 — Foundation :: Evidence, Factuality & Scientific Validity Evaluator

- Recorded status: `FAIL`
- Priority: `P0_BLOCKER`
- Freshness: `POSSIBLY_STALE_INFERRED_MAPPING`
- Confidence: `LOW_UNTIL_RERUN`
- Evidence basis: INFERRED — P22-J08 product failure
- Expected behavior: Evaluates claim-to-evidence support, citation and source quality, reasoning consistency, reproducibility, experimental validity, uncertainty, and external plausibility.
- Expected output: Claim/evaluation verdict with reasons, supported/unsupported claims, warnings, uncertainty, and evidence links.
- Recorded observation: Inferred fail: J08 treated an unsupported worldwide claim as supported. This suggests the scientific-validity evaluator misses a material evidence problem.
- Production entrypoints: harness/lib/research/evaluator.py; harness/lib/research/evidence/ledger.py; harness/tools/review_model_runtime_proof.py; harness/schemas/evidence/*.schema.json
- Freshness warnings:
  - The report status was inferred from another journey rather than directly bound to this L2.
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j08_claim_verification.py::test_p22_j08_claim_verification`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/journey-fail-repair/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Every accepted claim traces to admissible source/artifact spans; negative scientific fixtures fail and positive fixtures pass.

### P22-REPAIR-071 — Foundation :: Lifecycle, Parity & Human Review Evaluator

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J21
- Expected behavior: Verifies real execution, workflow completion, required gates, side effects, and feature or semantic parity; aggregates results and invokes attributable HITL review for high-risk, ambiguous, or policy-required decisions.
- Expected output: Lifecycle/parity verdict, human-review pending/approved/rejected state, reasons, warnings, and resumed/blocked transition.
- Recorded observation: J21 recorded lifecycle state and the need for review, but no attributable human approval occurred.
- Production entrypoints: harness/lib/graph_scheduler.py: enter_node_human_review(), validate_human_review_resume(), commit_human_review_resume(), _sprint_status_terminal(); tools/semantic_parity_runtime_proof.py
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['bce2b978008a14d337ff6040a2fabc71ce3e7ae5']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j21_experiment_build_handoff.py::test_p22_j21_real_experiment_build_and_handoff`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/J21-experiment-build-001/result.json` — exists=true, recorded_head=`bce2b978008a14d337ff6040a2fabc71ce3e7ae5`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Closure occurs only after required nodes/gates; human decision is attributable and generation-valid; parity/runtime evidence is typed and linked.

### P22-REPAIR-076 — Foundation :: Runtime and Resource Routing (Bayesian Optimization / Bandits / Cost-Aware RL)

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: NT-optimization-routing
- Expected behavior: Optimizes model, tool, budget, retry, and concurrency decisions. Validate with traces, load tests, and cost–latency metrics.
- Expected output: Recommendation/scorecard and approved routing/config change, with before/after cost-latency evidence.
- Recorded observation: Generic metric-based routing works. Bayesian, bandit, and cost-aware RL routing were not available.
- Production entrypoints: harness/lib/evolution_engine.py; harness/lib/graph_scheduler.py resource/model matching; named Bayesian/bandit/RL optimizer: Not found in current codebase
- Freshness warnings:
  - Evidence was recorded against another commit: ['62568bfeef0729f42c0eb9367bc358afe90b1660']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_p22_nt_optimization_routing.py::test_phase22_not_tested_optimization_and_routing_validation`
- Evidence paths:
  - `.codex-tmp/phase22-worker-results/NT-optimization-routing/result.json` — exists=true, recorded_head=`62568bfeef0729f42c0eb9367bc358afe90b1660`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Before/after traces and guardrails support the recommendation; approved change passes eval/regression and can be reverted.

### P22-REPAIR-080 — Foundation :: Memory, Retrieval, and Evidence (Memory Learning / Self-RAG / Reranker Training)

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: NT-memory-retrieval
- Expected behavior: Improves storage, retrieval, citation, and evidence binding. Validate with recall, precision, citation accuracy, and provenance checks.
- Expected output: Candidate memory/retrieval configuration or model, recall/precision/citation/provenance metrics, and gated recommendation.
- Recorded observation: Basic persistent retrieval works. Memory learning and Self-RAG are partial, and reranker training is unavailable.
- Production entrypoints: core/smi/indexer.ts and query.ts; core/memory/auto-semantic.ts; harness/lib/evidence_ledger.py; Self-RAG/reranker training: Not found in current codebase
- Freshness warnings:
  - Evidence was recorded against another commit: ['62568bfeef0729f42c0eb9367bc358afe90b1660']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_p22_nt_memory_retrieval.py::test_nt_memory_retrieval_cross_run_journey`
- Evidence paths:
  - `.codex-tmp/phase22-worker-results/NT-memory-retrieval/result.json` — exists=true, recorded_head=`62568bfeef0729f42c0eb9367bc358afe90b1660`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Holdout retrieval metrics improve while every returned item retains valid provenance/citation references.

### P22-REPAIR-082 — Foundation :: Data, Benchmarks, Curriculum, and Observability (Active Learning / Hard-Case Mining / Credit Assignment)

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: NT-model-training
- Expected behavior: Improves task coverage, difficulty, data quality, and change attribution. Validate with coverage, contamination, trace, and ablation tests.
- Expected output: Coverage/quality/contamination report, prioritized cases, candidate dataset/curriculum, ablation/attribution evidence, and recommendation.
- Recorded observation: Hard-case mining and observability work. Full active-learning, curriculum repair, and credit-assignment training remain incomplete.
- Production entrypoints: harness/lib/benchmark/runner.py and reports.py; harness/lib/model_call_runtime.py; harness/lib/evolution_engine.py; unified active-learning engine: Not found in current codebase
- Freshness warnings:
  - Evidence was recorded against another commit: ['62568bfeef0729f42c0eb9367bc358afe90b1660']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_p22_nt_model_training.py::test_p22_nt_model_training_and_data_loop_validation`
- Evidence paths:
  - `.codex-tmp/phase22-worker-results/NT-model-training/result.json` — exists=true, recorded_head=`62568bfeef0729f42c0eb9367bc358afe90b1660`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Coverage and ablation reports use traceable data, exclude contamination, and demonstrate attributable improvement under guardrails.

### P22-REPAIR-083 — Foundation :: Persistent Memory & Context Retrieval

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J04
- Expected behavior: Store accepted facts, decisions, summaries, failures, lessons, and reusable context in durable memory; support indexing, retrieval, compression, expiration, and context assembly.
- Expected output: Stored memory record or ranked context/search results with metadata and provenance.
- Recorded observation: The PDF was imported, but registration into the wiki was not completed.
- Production entrypoints: core/memory/auto-semantic.ts: processMessage(), extractKnowledge(), saveToSemanticMemory(); core/smi/indexer.ts and query.ts; harness/lib/experience/memory_functions.py
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['0265f6416e197cf613d69b4705b52730621cf3c9']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j04_paper_ingestion.py::test_p22_j04_paper_ingestion`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/overnight-phase22/result.json` — exists=true, recorded_head=`0265f6416e197cf613d69b4705b52730621cf3c9`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Persisted item is retrievable by stable identity/query with source metadata; isolation and no-match behavior are explicit.

### P22-REPAIR-084 — Foundation :: Concept Graph Management

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J04
- Expected behavior: Define and connect business concepts, entities, terminology, attributes, and semantic relationships.
- Expected output: Persisted ontology objects/relationships or query/timeline results.
- Recorded observation: The PDF was imported, but registration into the wiki was not completed.
- Production entrypoints: core/ontology/manager.ts: OntologyManager; core/ontology/schema-v2.sql; core/ontology/types.ts
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['0265f6416e197cf613d69b4705b52730621cf3c9']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j04_paper_ingestion.py::test_p22_j04_paper_ingestion`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/overnight-phase22/result.json` — exists=true, recorded_head=`0265f6416e197cf613d69b4705b52730621cf3c9`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Entity/relation persists, can be queried, and timeline/version provenance is retained.

### P22-REPAIR-086 — Foundation :: Code Graph Management

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J17
- Expected behavior: Model repositories, modules, APIs, functions, tests, configurations, dependencies, and their relationships to concepts, datasets, and runtime behavior.
- Expected output: Indexed file metadata and search results; richer code-relationship graph is not currently guaranteed.
- Recorded observation: The workflow used code-graph references, but it did not create a standalone CodeGraph file.
- Production entrypoints: core/smi/indexer.ts: FileIndexer; core/smi/query.ts: SMIQuery, quickSearch(); full code graph: Not found in current codebase
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j17_tmux_capsule_operator_core.py::test_p22_j17_tmux_capsule_operator_core_real_user_entrypoint`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/T2-tmux-prep-001/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Indexed files are discoverable with current metadata; full-feature success would additionally require parsed symbols and relationship edges, which lack current proof.

### P22-REPAIR-089 — Foundation :: Trace Graph Management

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: NT-dag-trace
- Expected behavior: Connect requests, plans, executions, operator decisions, tool calls, artifacts, evidence, evaluations, and state transitions into an auditable execution history.
- Expected output: Append-only ledger/event records and correlated state/evidence views.
- Recorded observation: Trace persistence works, but Windows v2 session logging depends on Unix fcntl and no unified trace-query API exists.
- Production entrypoints: harness/lib/evidence_ledger.py: EvidenceLedger, build_scheduler_decision(); harness/lib/node_runstate.py: record(); harness/lib/task_graph_state_io.py: record_event()
- Freshness warnings:
  - Evidence was recorded against another commit: ['62568bfeef0729f42c0eb9367bc358afe90b1660']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_p22_nt_dag_trace.py::test_p22_nt_dag_trace`
- Evidence paths:
  - `.codex-tmp/phase22-worker-results/NT-dag-trace/result.json` — exists=true, recorded_head=`62568bfeef0729f42c0eb9367bc358afe90b1660`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: A run can be reconstructed by stable IDs from intake through terminal verdict without unsupported gaps.

### P22-REPAIR-090 — Foundation :: Memory Graph Management

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J04
- Expected behavior: Represent relationships among remembered facts, decisions, experiences, failures, lessons, entities, workflows, and their originating evidence.
- Expected output: Memory/ontology relations and timeline/query results with provenance.
- Recorded observation: The PDF was imported, but registration into the wiki was not completed.
- Production entrypoints: core/ontology/schema-v2.sql: ont_memory_timeline; core/ontology/manager.ts: OntologyManager; core/memory/auto-semantic.ts
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['0265f6416e197cf613d69b4705b52730621cf3c9']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j04_paper_ingestion.py::test_p22_j04_paper_ingestion`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/overnight-phase22/result.json` — exists=true, recorded_head=`0265f6416e197cf613d69b4705b52730621cf3c9`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Relations persist with evidence/version metadata and are queryable without crossing isolation boundaries.

### P22-REPAIR-091 — Foundation :: TaskGraph Persistence & Lifecycle Management

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J02
- Expected behavior: Store and version executable TaskGraph specifications and their runtime state, including nodes, dependencies, scopes, gates, checkpoints, results, and closure records.
- Expected output: Persisted spec/state/closure paths, merged graph view, node/gate results, and closure completeness status.
- Recorded observation: The main workflow passed, but the older eval.md evidence file was not created; command logs and saved status are available instead.
- Production entrypoints: harness/lib/task_graph_io.py: save_spec(), save_state(), patch_state(), set_node_result_in_state(), save_closure(), closure_complete(); harness/lib/task_graph_state_io.py
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['5a4583e790b568dc62eac78c46cbba30cb751008']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j02_live_coding_task.py::test_p22_j02_live_coding_task`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/phase22-j02-live-windows-008/result.json` — exists=true, recorded_head=`5a4583e790b568dc62eac78c46cbba30cb751008`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Round-trip preserves graph/state, atomic writes avoid partial files, and closure_complete() is false until required evidence/gates are present.

### P22-REPAIR-092 — Foundation :: Runtime Control Loop & Run Lifecycle Management

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J07
- Expected behavior: Initialize run/sprint identity and configuration; drive the main control loop; maintain durable run/node state and status projections; close the run only when required nodes and gates are satisfied.
- Expected output: Initialized spec/state, scheduling/status projections, events, terminal run status, and closure record.
- Recorded observation: The experiment ran, but the system did not record a clear final lifecycle state.
- Production entrypoints: harness/lib/graph_scheduler.py runtime-plane/status/terminal functions; harness/lib/task_graph_state_io.py; harness/lib/task_lifecycle.py
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j07_experiment_lifecycle.py::test_p22_j07_experiment_lifecycle`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/journey-fail-repair/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Run identity/state is created, transitions are legal and persisted, and closure is emitted only after terminal evidence and required gates.

### P22-REPAIR-094 — Foundation :: DAG Scheduler, TaskGraph Readiness & Operator Binding

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J02
- Expected behavior: Validate the DAG, determine readiness from dependencies, gates and external waits, and form safe parallel batches using scope, effect, resource, and capacity constraints.
- Expected output: Validation report, topological layers/critical path, ready nodes, conflict-free batches, assignments, and rejection reasons.
- Recorded observation: The main workflow passed, but the older eval.md evidence file was not created; command logs and saved status are available instead.
- Production entrypoints: harness/lib/graph_scheduler.py: validate_graph(), topo_layers(), ready_nodes(), make_batches(), assign_workers(), assign_ready()
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['5a4583e790b568dc62eac78c46cbba30cb751008']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j02_live_coding_task.py::test_p22_j02_live_coding_task`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/phase22-j02-live-windows-008/result.json` — exists=true, recorded_head=`5a4583e790b568dc62eac78c46cbba30cb751008`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Only dependency/gate-ready nodes are assigned; batches have no forbidden conflicts; tests/control_plane/test-graph-scheduler.sh and graph unit tests pass.

### P22-REPAIR-095 — Foundation :: Execution Admission, Lease & Concurrency Control

- Recorded status: `FAIL`
- Priority: `P0_BLOCKER`
- Freshness: `LIKELY_STALE_J21_SOURCE_NOW_RECOMMENDS_PASS_OR_LIMITED`
- Confidence: `LOW_UNTIL_RERUN`
- Evidence basis: P22-J21
- Expected behavior: Enforce approval, policy and availability checks; acquire/release/reap leases; prevent duplicate dispatch; and enforce concurrency, quota, exclusion, and capacity limits.
- Expected output: Admission decision, lease state/token, rejection reason, release/reap result, and audit record.
- Recorded observation: J21 admitted a run but did not prove duplicate-run rejection, lease behavior, or release.
- Production entrypoints: harness/lib/operator_runtime.py: acquire_operator_lease(), release_operator_lease(); harness/lib/actor_lease.py: LeaseBroker; harness/config/concurrency-policy.json
- Freshness warnings:
  - Current J21 source recommends PASS or PASS_WITH_KNOWN_LIMITATIONS for this row, while the register retains an older FAIL.
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['bce2b978008a14d337ff6040a2fabc71ce3e7ae5']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j21_experiment_build_handoff.py::test_p22_j21_real_experiment_build_and_handoff`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/J21-experiment-build-001/result.json` — exists=true, recorded_head=`bce2b978008a14d337ff6040a2fabc71ce3e7ae5`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: At most one active conflicting lease exists, denied work is not dispatched, and stale leases can be safely recovered with audit evidence.

### P22-REPAIR-096 — Foundation :: Main Loop Dispatch & Runtime Supervision

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J02
- Expected behavior: Consume an already-resolved operator binding, create the execution envelope/instruction, dispatch it to the runtime or host, monitor heartbeat/progress, and collect normalized results, handoffs, artifacts, and evidence references.
- Expected output: Submission receipt, heartbeat/progress state, normalized result/error, handoff, artifacts, and evidence references.
- Recorded observation: The main workflow passed, but the older eval.md evidence file was not created; command logs and saved status are available instead.
- Production entrypoints: harness/lib/operator_runtime.py: submit(), write_heartbeat(), write_result(); harness/lib/actor_runtime.py: ActorRuntime; harness/lib/worker_runtime.py: WorkerRuntime
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['5a4583e790b568dc62eac78c46cbba30cb751008']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j02_live_coding_task.py::test_p22_j02_live_coding_task`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/phase22-j02-live-windows-008/result.json` — exists=true, recorded_head=`5a4583e790b568dc62eac78c46cbba30cb751008`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Submission correlates to one lease/task, heartbeat updates liveness, and terminal result is normalized and linked to artifacts/evidence.

### P22-REPAIR-100 — Foundation :: Ambiguity Resolution & Readiness

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J16 final integration
- Expected behavior: Detect missing, conflicting or unclear requirements; generate the minimum necessary clarification questions; determine whether the intent is ready for planning.
- Expected output: Ready/not-ready signal plus unresolved ambiguity/missing-field list and clarification prompts or fallback route.
- Recorded observation: The workflow reached a usable ready state from saved product artifacts instead of an interactive confirmation. Interactive readiness confirmation remains a limitation.
- Production entrypoints: Partial: harness/lib/intent_gateway.py deterministic_rewrite()/build_requirement_ir(); dedicated minimum-question generator: Not found in current codebase
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j16_tmux_requirements_builder.py::test_p22_j16_tmux_requirements_builder_real_user_defect_repair`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/T1-tmux-prep-001/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Future proof should show blocking ambiguity prevents planning and generated questions are minimal and answerable; current direct proof is absent.

### P22-REPAIR-102 — Foundation :: Task Contract & Acceptance Compilation

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J02
- Expected behavior: Produce a stable, versioned task contract containing normalized inputs and outputs, objectives, constraints, acceptance criteria and required evidence.
- Expected output: Versioned requirement/task contract artifacts and bindings to sprint/plan IDs.
- Recorded observation: The main workflow passed, but the older eval.md evidence file was not created; command logs and saved status are available instead.
- Production entrypoints: harness/lib/intent_gateway.py: build_requirement_ir(), capture(), bind_intent_artifacts(); harness/lib/autosci_intake_contract.py: build_autosci_product_brief()
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['5a4583e790b568dc62eac78c46cbba30cb751008']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j02_live_coding_task.py::test_p22_j02_live_coding_task`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/phase22-j02-live-windows-008/result.json` — exists=true, recorded_head=`5a4583e790b568dc62eac78c46cbba30cb751008`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Contract validates, preserves raw-input trace, has stable identity/version, and is consumed by planner without hidden fields.

### P22-REPAIR-103 — Foundation :: Task Contract Decomposition

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J02
- Expected behavior: Interpret the validated task contract, select an appropriate planning pattern, and split the goal into bounded work units with explicit objectives, inputs, outputs and completion conditions. Also generate the planning plan text artifact for RSI.
- Expected output: Plan text/design/trace artifacts and bounded logical work units or a blocked planning result.
- Recorded observation: The main workflow passed, but the older eval.md evidence file was not created; command logs and saved status are available instead.
- Production entrypoints: harness/lib/compiled_sprint_planner.py: build_design_markdown(), build_plan_markdown(), generate_planner_artifacts(); harness/lib/autosci_intake_contract.py: build_autosci_task_graph()
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['5a4583e790b568dc62eac78c46cbba30cb751008']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j02_live_coding_task.py::test_p22_j02_live_coding_task`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/phase22-j02-live-windows-008/result.json` — exists=true, recorded_head=`5a4583e790b568dc62eac78c46cbba30cb751008`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Every work unit traces to contract requirements and has explicit inputs, outputs, completion evidence, and bounded scope.

### P22-REPAIR-104 — Foundation :: TaskGraph Construction

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J02
- Expected behavior: Compile the work units into a logical Plan IR/TaskGraph, defining dependencies, parent-child relationships, ordering, parallelizable branches and critical paths.
- Expected output: Schema-valid Plan IR/TaskGraph and optional physical/capsule plan artifacts.
- Recorded observation: The main workflow passed, but the older eval.md evidence file was not created; command logs and saved status are available instead.
- Production entrypoints: harness/lib/workflow_contract.py: instantiate(); harness/lib/apo_plan_compiler.py: build_capsule_plan_ir(), build_capsule_plan_node(); harness/lib/compiled_sprint_planner.py
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['5a4583e790b568dc62eac78c46cbba30cb751008']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j02_live_coding_task.py::test_p22_j02_live_coding_task`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/phase22-j02-live-windows-008/result.json` — exists=true, recorded_head=`5a4583e790b568dc62eac78c46cbba30cb751008`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Graph validates against task-graph schema, is acyclic, preserves dependencies/scopes/gates, and has stable contract hash.

### P22-REPAIR-105 — Foundation :: TaskGraph Validation & Feasibility Analysis

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J02
- Expected behavior: Validate schema completeness, missing dependencies, cycles, requirement coverage, scope conflicts, capability feasibility, risk, policy compliance and useful parallelism. Invalid or infeasible plans must be blocked or returned for clarification/replanning.
- Expected output: Validation findings, plan certificate/hash, dispatchable decision, remediation, or bounded replan/clarification status.
- Recorded observation: The main workflow passed, but the older eval.md evidence file was not created; command logs and saved status are available instead.
- Production entrypoints: harness/lib/plan_validator.py: validate_plan(), stamp_plan_certificate(), check_plan_certificate(), compile_planner_graph(); harness/lib/graph_scheduler.py: validate_graph()
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['5a4583e790b568dc62eac78c46cbba30cb751008']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j02_live_coding_task.py::test_p22_j02_live_coding_task`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/phase22-j02-live-windows-008/result.json` — exists=true, recorded_head=`5a4583e790b568dc62eac78c46cbba30cb751008`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Invalid plans cannot reach dispatch; valid plan has reproducible certificate and all required roles/capsules resolve.

### P22-REPAIR-108 — Foundation :: Code Construction

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J02
- Expected behavior: Create or modify deterministic source code, scripts, tests, and configuration to implement the required technical function.
- Expected output: Source/config/test changes plus result, diff, logs, and evidence.
- Recorded observation: The main workflow passed, but the older eval.md evidence file was not created; command logs and saved status are available instead.
- Production entrypoints: harness/lib/operator_runtime.py and harness/tools/codex_operator.py; agents/coder.md; no generic deterministic code-generation function
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['5a4583e790b568dc62eac78c46cbba30cb751008']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j02_live_coding_task.py::test_p22_j02_live_coding_task`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/phase22-j02-live-windows-008/result.json` — exists=true, recorded_head=`5a4583e790b568dc62eac78c46cbba30cb751008`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Diff stays in scope, requested interface works, mandatory checks pass, and build evidence links to exact changes.

### P22-REPAIR-110 — Foundation :: Experimental Asset Construction

- Recorded status: `FAIL`
- Priority: `P0_BLOCKER`
- Freshness: `LIKELY_STALE_J21_SOURCE_NOW_RECOMMENDS_PASS_OR_LIMITED`
- Confidence: `LOW_UNTIL_RERUN`
- Evidence basis: P22-J21
- Expected behavior: Build experiment code, data processing, instrumentation, environment descriptions, and run scripts.
- Expected output: Experiment assets, run contract/scripts, instrumentation, environment manifest, and typed plan/result evidence.
- Recorded observation: The runner executed, but J21 used a supplied script instead of having the product build the experimental asset.
- Production entrypoints: .agents/skills/exp-design/SKILL.md, exp-run/SKILL.md, exp-pilot-run/SKILL.md; harness/workflows/scientific_experiment_lifecycle_v1.json
- Freshness warnings:
  - Current J21 source recommends PASS or PASS_WITH_KNOWN_LIMITATIONS for this row, while the register retains an older FAIL.
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['bce2b978008a14d337ff6040a2fabc71ce3e7ae5']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j21_experiment_build_handoff.py::test_p22_j21_real_experiment_build_and_handoff`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/J21-experiment-build-001/result.json` — exists=true, recorded_head=`bce2b978008a14d337ff6040a2fabc71ce3e7ae5`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Assets are runnable/reproducible, plan/result schemas validate, and side effects occur only with approval/runtime evidence.

### P22-REPAIR-111 — Foundation :: Benchmark Asset Construction

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J03
- Expected behavior: Build benchmark datasets, harnesses, workloads, baselines, metric implementations, and comparison scripts.
- Expected output: Registered benchmark assets and a doctor/plan/run-capable harness definition.
- Recorded observation: J03 demonstrated executable benchmark configuration and durable result files. Creating new benchmark datasets and baselines was not tested.
- Production entrypoints: harness/lib/benchmark/registry.py, schemas.py, terminal_bench.py, runner.py; tests/harness/benchmark/
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j03_platform_benchmark.py::test_p22_j03_platform_benchmark`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/journey-fail-repair/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Doctor/list/plan/run accepts the assets, result schema validates, and baseline/metric behavior is independently checked.

### P22-REPAIR-112 — Foundation :: Verification Asset Construction

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J02
- Expected behavior: Build unit, integration, and end-to-end tests, validators, fixtures, checklists, and verification scripts.
- Expected output: Executable test files/fixtures/validators with stable assertions and documented prerequisites.
- Recorded observation: The main workflow passed, but the older eval.md evidence file was not created; command logs and saved status are available instead.
- Production entrypoints: skills/test/SKILL.md; tests/README.md; tests/** and tests/harness/**
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['5a4583e790b568dc62eac78c46cbba30cb751008']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j02_live_coding_task.py::test_p22_j02_live_coding_task`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/phase22-j02-live-windows-008/result.json` — exists=true, recorded_head=`5a4583e790b568dc62eac78c46cbba30cb751008`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Tests collect/run on declared runner, fail against broken behavior, pass against current behavior, and emit reproducible evidence.

### P22-REPAIR-113 — Foundation :: Decision Artifact Construction

- Recorded status: `FAIL`
- Priority: `P0_BLOCKER`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_EXECUTABLE_DIAGNOSTIC`
- Evidence basis: P22-J09
- Expected behavior: Create opportunity cards, decision records, trade-off matrices, and recommendation packets for decision-making.
- Expected output: Structured decision/opportunity artifact with alternatives, rationale, evidence links, risks, and next action.
- Recorded observation: The report artifacts were created, but final review, approval, or compilation did not complete, so the required handoff was not finished.
- Production entrypoints: .agents/skills/ideate/SKILL.md, novelty/SKILL.md, review/SKILL.md; harness/schemas/evidence/idea_candidate.v1.schema.json and idea_evaluation.v1.schema.json
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j09_report_delivery.py::test_p22_j09_report_delivery`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/journey-fail-repair/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Recommendation traces to explicit criteria/evidence and records limitations and unresolved review items.

### P22-REPAIR-115 — Foundation :: Product Integration

- Recorded status: `FAIL`
- Priority: `P0_BLOCKER`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_EXECUTABLE_DIAGNOSTIC`
- Evidence basis: P22-J16
- Expected behavior: Integrate verified components into target product interfaces, data flows, and production-oriented operational boundaries.
- Expected output: Integrated product change plus migration/config, compatibility evidence, and rollback plan.
- Recorded observation: The live task ran, but the harness startup failed and the repair was not verified through a complete passing test path.
- Production entrypoints: harness/lib/plan_validator.py and operator dispatch; task-specific integrations under integrations/ and harness/integrations/
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j16_tmux_requirements_builder.py::test_p22_j16_tmux_requirements_builder_real_user_defect_repair`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/T1-tmux-prep-001/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Target interface/data flow works end to end, regressions pass, and rollback/migration evidence is recorded.

### P22-REPAIR-116 — Foundation :: Defect Repair

- Recorded status: `FAIL`
- Priority: `P0_BLOCKER`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_EXECUTABLE_DIAGNOSTIC`
- Evidence basis: P22-J16
- Expected behavior: Use failure evidence to identify and repair code, configuration, contract, or integration defects and prevent regression.
- Expected output: Scoped patch/config change, root-cause note, regression test, and verification evidence.
- Recorded observation: The live task ran, but the harness startup failed and the repair was not verified through a complete passing test path.
- Production entrypoints: harness/lib/operator_runtime.py; agents/coder.md; docs/WORKFLOW_DESIGN.md §Bug fix scenario
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j16_tmux_requirements_builder.py::test_p22_j16_tmux_requirements_builder_real_user_defect_repair`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/T1-tmux-prep-001/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Original failure reproduces before fix, passes after scoped fix, regression test is added, and unrelated checks remain green.

### P22-REPAIR-117 — Foundation :: Build Evidence Generation

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J03
- Expected behavior: Generate diffs, manifests, hashes, compile and test results, provenance, and acceptance evidence for the build.
- Expected output: Evidence pack/ledger entries, manifests/hashes, result/handoff artifacts, and acceptance verdict references.
- Recorded observation: J03 retained benchmark commands, hashes, and result files. Build diffs and compile evidence were not part of this run.
- Production entrypoints: harness/lib/evidence_ledger.py; harness/lib/benchmark/reports.py: write_run_artifacts(); harness/lib/operator_runtime.py: write_result()
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j03_platform_benchmark.py::test_p22_j03_platform_benchmark`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/journey-fail-repair/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Every claimed output has stable path/hash/provenance and mandatory checks; tampering or missing artifacts invalidate pass.

### P22-REPAIR-118 — Foundation :: Report/Paper/Deliverable Construction

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J09 final integration
- Expected behavior: Create and assemble human-facing reports, papers, slides, posters, rebuttals, and narrative delivery packages.
- Expected output: Draft/compiled deliverable bundle with citations, provenance, review status, and publication artifacts.
- Recorded observation: The final J09 path produced a readable report from a consistent local proof bundle through production commands. Live LLM review, final approval, and publication compile remain limited.
- Production entrypoints: .agents/skills/paper-plan/SKILL.md, paper-draft/SKILL.md, paper-compile/SKILL.md, poster/SKILL.md, rebuttal/SKILL.md, survey/SKILL.md
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j09_report_delivery.py::test_p22_j09_report_delivery`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/journey-fail-repair/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Deliverable compiles/renders, claims trace to evidence/citations, required review passes, and publication side effects are separately approved.

### P22-REPAIR-119 — Foundation :: Runtime Deliverable Construction

- Recorded status: `FAIL`
- Priority: `P0_BLOCKER`
- Freshness: `LIKELY_STALE_J21_SOURCE_NOW_RECOMMENDS_PASS_OR_LIMITED`
- Confidence: `LOW_UNTIL_RERUN`
- Evidence basis: P22-J21
- Expected behavior: Build executable or deployable services, packages, containers, workflow bundles, and deployment configuration.
- Expected output: Package/service/container/workflow bundle, install/deploy config, manifest/hashes, smoke/health evidence, and rollback instructions.
- Recorded observation: J21 produced output, but it did not prove that the runtime command actually executed. The minimum deliverable condition was not met.
- Production entrypoints: install.sh/install.ps1; distribution/pipx/; harness/docker/Dockerfile; deploy/; harness/workflows/
- Freshness warnings:
  - Current J21 source recommends PASS or PASS_WITH_KNOWN_LIMITATIONS for this row, while the register retains an older FAIL.
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['bce2b978008a14d337ff6040a2fabc71ce3e7ae5']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j21_experiment_build_handoff.py::test_p22_j21_real_experiment_build_and_handoff`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/J21-experiment-build-001/result.json` — exists=true, recorded_head=`bce2b978008a14d337ff6040a2fabc71ce3e7ae5`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: Artifact installs/starts in clean sandbox, health/smoke passes, manifest excludes secrets, and uninstall/rollback is documented and verified.

### P22-REPAIR-120 — Vertical :: Workflow & Platform Status Visibility

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J18
- Expected behavior: Show workflow progress, blockers, gates, budgets, and the health of hosts, providers, queues, data sources, and other platform components without changing authoritative runtime state.
- Expected output: JSON status and orchestration projections, HTML dashboard views, and SSE updates containing current sprint, node/gate status, blockers, panes, recent events, KPIs, capability health, and evidence links.
- Recorded observation: The feature worked in local SolarUbuntu/WSL2, but other Linux setups and multi-session use were not tested.
- Production entrypoints: harness/lib/symphony/status-server.py: _current_sprint, _main_screen, _physical_operator_summary, _capability_health_summary, _orchestration_projection_payload, StatusHandler; core/dashboard/server.ts: getHealthSummary and Bun.serve routes.
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j18_real_linux_status_lifecycle.py::test_p22_j18_real_linux_status_lifecycle`
  - `tests/journeys/phase22/code/test_j18_tmux_cli_status_config.py::test_p22_j18_tmux_cli_status_config`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/T3-tmux-prep-001/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: harness/lib/symphony/status-server.py: StatusHandler GET /status, /orchestration/dashboard, /orchestration/projection and _status_payload/_orchestration_projection_payload; tests/harness/test_status_server_p0_dashboard.py; tests/harness/test_status_server_idle_projection.py.

### P22-REPAIR-121 — Vertical :: Execution Trace Search & Inspection

- Recorded status: `FAIL`
- Priority: `P2_MILD_FAILURE`
- Freshness: `DETECTION_TEST_ENCODES_KNOWN_FAILURE`
- Confidence: `MEDIUM_EXECUTABLE_DIAGNOSTIC`
- Evidence basis: NT-dag-trace
- Expected behavior: Search and inspect time-ordered requests, transitions, tool calls, approvals, failures, artifacts, decisions, and outcomes using filters for project, run, actor, and time range.
- Expected output: Reverse-chronological orchestration-event JSON from SQLite, recent session/sprint event JSON, dashboard event tables, or an SSE event stream.
- Recorded observation: Basic run search works, but project, actor, and time-range filters do not work.
- Production entrypoints: core/daemon/message-executor.ts: recordOrchestrationEvent and getOrchestrationEvents; harness/lib/runtime_bridge.py: record_legacy_event/adopt_sprint; harness/lib/symphony/status-server.py: _runtime_events_path, _events_for_request and _send_sse_events.
- Freshness warnings:
  - The current diagnostic test asserts that project/actor/time filters remain unenforced; it must be converted to a positive regression after reproduction.
  - Evidence was recorded against another commit: ['62568bfeef0729f42c0eb9367bc358afe90b1660']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_p22_nt_dag_trace.py::test_p22_nt_dag_trace`
- Evidence paths:
  - `.codex-tmp/phase22-worker-results/NT-dag-trace/result.json` — exists=true, recorded_head=`62568bfeef0729f42c0eb9367bc358afe90b1660`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: core/daemon/message-executor.ts: getOrchestrationEvents SQL filters and ordering; core/daemon/server.ts: GET /orchestrator/events; harness/lib/symphony/status-server.py: _events_for_request and GET /events.

### P22-REPAIR-125 — Vertical :: MacOS App

- Recorded status: `ENVIRONMENT_BLOCKED`
- Priority: `P2_EVIDENCE_RECONCILIATION`
- Freshness: `POSSIBLY_STALE_MAC_EVIDENCE_NOT_RECONCILED`
- Confidence: `MEDIUM_EXECUTABLE_DIAGNOSTIC`
- Evidence basis: Final integration platform review
- Expected behavior: Package, install, launch, update, repair, and uninstall the macOS desktop application; guide first-run permissions, runtime and provider setup, preserve user data, and verify application and backend readiness.
- Expected output: DMG/application bundle, installed or synchronized runtime, launchd agent, local dashboard window, install logs, health/self-test verdict, and uninstallable service artifacts.
- Recorded observation: The final integration host is Windows/WSL and no macOS runner was available in this pass. Prior macOS evidence remains historical, not current final validation proof.
- Production entrypoints: desktop/src/main.js: runUnixBootstrap, installMacLaunchAgent, syncBundledHarnessLocal, classifyRuntimeState and createWindow; desktop/prepackage-check.js; desktop/verify-macos-package.sh.
- Freshness warnings:
  - Historical macOS evidence exists, but the current register did not accept it as final evidence.
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j15_cross_platform_install_matrix.py::test_p22_j15_cross_platform_install_matrix`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `C:/Users/j50058254/Downloads/phase22-macos-j15-evidence-p22j15-20260729T150935Z-76209.zip` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: desktop/package.json: build:mac and mac target; desktop/verify-macos-package.sh; tests/desktop/src/selftest-verdict.test.cjs; desktop/runtime/install-macos-agent.sh and uninstall-macos-agent.sh.

### P22-REPAIR-126 — Vertical :: MacOS CLI

- Recorded status: `ENVIRONMENT_BLOCKED`
- Priority: `P2_EVIDENCE_RECONCILIATION`
- Freshness: `POSSIBLY_STALE_MAC_EVIDENCE_NOT_RECONCILED`
- Confidence: `MEDIUM_EXECUTABLE_DIAGNOSTIC`
- Evidence basis: Final integration platform review
- Expected behavior: Install and operate the Solar CLI on macOS, including dependency checks, PATH and configuration initialization, provider-authentication readiness, status and doctor checks, backup and restore, update and repair, and uninstall.
- Expected output: ~/.solar layout, solar launcher, component receipt, configuration/secrets files, optional launchd service, doctor/status output, backup archive, restored data, and clean uninstall evidence.
- Recorded observation: The final integration host is Windows/WSL and no macOS runner was available in this pass. Prior macOS CLI evidence remains historical, not current final validation proof.
- Production entrypoints: lib/installer/main.sh: main; lib/installer/common.sh: detect_os/detect_python; lib/installer/components.sh: install_components; bin/solar: doctor/do_backup/do_restore/do_repair/do_update/uninstall.
- Freshness warnings:
  - Historical macOS evidence exists, but the current register did not accept it as final evidence.
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j15_cross_platform_install_matrix.py::test_p22_j15_cross_platform_install_matrix`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `C:/Users/j50058254/Downloads/phase22-macos-j15-evidence-p22j15-20260729T150935Z-76209.zip` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: lib/installer/common.sh: detect_os/detect_python; lib/installer/system-deps.sh; bin/solar: doctor, backup, restore, update, repair and uninstall; tests/harness/installer/test_s1_installer.sh.

### P22-REPAIR-127 — Vertical :: Linux Cli

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J18
- Expected behavior: Install and operate the Solar CLI on supported Linux distributions, including dependency and package-manager checks, runtime and configuration initialization, service startup, status and doctor checks, backup and restore, update and repair, and uninstall.
- Expected output: ~/.solar installation, CLI launcher, receipt and config, optional systemd user unit, status/doctor evidence, backup/restore artifacts, and uninstall result.
- Recorded observation: The feature worked in local SolarUbuntu/WSL2, but other Linux setups and multi-session use were not tested.
- Production entrypoints: lib/installer/main.sh and common.sh; lib/installer/system-deps.sh; bin/solar doctor/update/repair/backup/restore/uninstall; desktop/runtime/install-linux-service.sh.
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j18_real_linux_status_lifecycle.py::test_p22_j18_real_linux_status_lifecycle`
  - `tests/journeys/phase22/code/test_j18_tmux_cli_status_config.py::test_p22_j18_tmux_cli_status_config`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/T3-tmux-prep-001/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: lib/installer/common.sh: Linux detection and apt Python bootstrap; lib/installer/system-deps.sh: apt-get path; desktop/runtime/install-linux-service.sh; tests/harness/installer/test_s1_installer.sh. The obsolete QA-audit contract file is quarantined and is not accepted evidence.

### P22-REPAIR-128 — Vertical :: Web Application & Status Service

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J18; P22-J19
- Expected behavior: Build, serve, configure, and health-check the browser-based application and status API; connect it to authentication, configuration, workflow state, runtime visibility, and artifact views across development and packaged deployments.
- Expected output: HTML/JS application, JSON APIs, SSE projection/event streams, healthz/runtime-info responses, artifact views/downloads, and explicit HTTP errors.
- Recorded observation: J18 started and checked the status service, and J19 used the real dashboard in Chrome. Packaged desktop, broader routes, long-running stability, and concurrent use remain untested.
- Production entrypoints: harness/lib/symphony/status-server.py: StatusHandler, _p0_dashboard_html and main server startup; core/dashboard/server.ts: Bun.serve; desktop/src/main.js: probeHealth, startBackend and loadDashboard.
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j18_real_linux_status_lifecycle.py::test_p22_j18_real_linux_status_lifecycle`
  - `tests/journeys/phase22/code/test_j18_tmux_cli_status_config.py::test_p22_j18_tmux_cli_status_config`
  - `tests/journeys/phase22/code/test_j19_real_gui_dashboard.py::test_p22_j19_real_gui_dashboard`
  - `tests/journeys/phase22/code/test_j19_tmux_ui_account_channels.py::test_p22_j19_tmux_ui_account_channels`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/T3-tmux-prep-001/result.json` — exists=true, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/T4-tmux-prep-001/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: harness/lib/symphony/status-server.py: StatusHandler and /healthz; tests/harness/test_status_server_p0_dashboard.py; tests/desktop/frontend-scenarios.test.cjs; tests/desktop/functional.test.cjs; scripts/verify-webapp-session.sh.

### P22-REPAIR-129 — Vertical :: CLI

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J18
- Expected behavior: Provide a scriptable command-response interface for submitting work, inspecting status, managing lifecycle and configuration, and retrieving logs, artifacts, and evidence, with stable exit codes and human-readable or structured JSON output.
- Expected output: Human-readable stdout/stderr, selected JSON reports, generated artifacts/archives, and exit codes that distinguish success, bad usage, health failure, refusal, or unavailable dependency.
- Recorded observation: Basic Solar CLI help commands worked, but some secondary help commands still failed on Windows.
- Production entrypoints: bin/solar command dispatcher and doctor/do_backup/do_restore/do_ui/uninstall; harness/control-plane.sh; harness/lib/runtime_bridge.py; harness/plugins/autosci/bin/autosci_skill_shim.py.
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j18_real_linux_status_lifecycle.py::test_p22_j18_real_linux_status_lifecycle`
  - `tests/journeys/phase22/code/test_j18_tmux_cli_status_config.py::test_p22_j18_tmux_cli_status_config`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/T3-tmux-prep-001/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: bin/solar: usage and command dispatch; tests/harness/installer/test_s1_installer.sh; tests/harness/integration/test_autosci_cli_dispatch.py; tests/harness/remote/test_remote_dispatch_cli.py.

### P22-REPAIR-130 — Vertical :: GUI

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J19
- Expected behavior: Provide a graphical desktop or web interface for task intake, setup and configuration, workflow and gate monitoring, approval, artifact and evidence inspection, and deliverable access, including loading, empty, error, and accessibility states.
- Expected output: Electron/browser views with loading, installing, healthy, empty, error/recovery and dashboard states; JSON-backed workflow cards, events, artifacts, evidence and deliverable links.
- Recorded observation: The web dashboard worked in local headless Chrome, but packaged desktop windows, accessibility, and multi-monitor use were not tested.
- Production entrypoints: desktop/src/main.js: createWindow, classifyRuntimeState, runAction and loadDashboard; harness/lib/symphony/status-server.py: _p0_dashboard_html and StatusHandler; desktop/src/preload.js.
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j19_real_gui_dashboard.py::test_p22_j19_real_gui_dashboard`
  - `tests/journeys/phase22/code/test_j19_tmux_ui_account_channels.py::test_p22_j19_tmux_ui_account_channels`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/T4-tmux-prep-001/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: tests/desktop/frontend-scenarios.test.cjs; tests/desktop/screens.test.cjs; tests/desktop/functional.test.cjs; tests/desktop/src/selftest-verdict.test.cjs; tests/desktop/overhaul-visual.test.cjs; tests/harness/test_status_server_p0_dashboard.py.

### P22-REPAIR-131 — Vertical :: TUI

- Recorded status: `FAIL`
- Priority: `P2_MILD_FAILURE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_EXECUTABLE_DIAGNOSTIC`
- Evidence basis: P22-J13; P22-J18
- Expected behavior: Provide an interactive terminal interface for monitoring runs, TaskGraph nodes, agents or panes, queues, gates, logs, and resource state, and for issuing explicit authorized control actions through keyboard-driven views.
- Expected output: ANSI/plain terminal dashboard with dependency, runtime, pane, blocker, queue and evidence summaries; TypeScript dashboard widgets and keyboard-driven panel rendering.
- Recorded observation: The interactive terminal interface did not open on Windows because it uses an unsupported signal.
- Production entrypoints: harness/lib/cli/solar_ui_lite.py: main, collect_state, collect_runtime and render; core/ui/dashboard.ts: SolarDashboard; core/ui/v2/runtime.ts: UIRuntime.
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['0265f6416e197cf613d69b4705b52730621cf3c9']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j13_local_interaction_interface.py::test_p22_j13_local_interaction_interface`
  - `tests/journeys/phase22/code/test_j18_real_linux_status_lifecycle.py::test_p22_j18_real_linux_status_lifecycle`
  - `tests/journeys/phase22/code/test_j18_tmux_cli_status_config.py::test_p22_j18_tmux_cli_status_config`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/overnight-phase22/result.json` — exists=true, recorded_head=`0265f6416e197cf613d69b4705b52730621cf3c9`
  - `.codex-tmp/phase22-worker-results/T3-tmux-prep-001/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: harness/lib/cli/solar_ui_lite.py: collect_state/render/build_parser/main; bin/solar: do_ui; core/ui/dashboard.ts: SolarDashboard; tests/core/ui-engine.test.ts.

### P22-REPAIR-135 — Vertical :: Privacy & Personal Data Controls

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J24 final integration
- Expected behavior: Let users inspect, export, retain, or delete personal settings and supplied data and manage consent for message-derived information.
- Expected output: Backup archive, restored local data, retained or removed Solar data, redacted ingestion artifacts, neutral privacy/config values, and privacy-scan pass/fail evidence.
- Recorded observation: The final journey suite passed the privacy lifecycle path after the proof-bundle and migration fixes. Hosted account deletion, provider revocation, Discord/Wechat channels, and live-platform variants remain untested or unavailable.
- Production entrypoints: bin/solar do_backup/do_restore/uninstall; core/config/privacy.ts getters; harness/lib/apple_notes_ingest.py redact; scripts/check-privacy.sh.
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
  - Evidence was recorded against another commit: ['bce2b978008a14d337ff6040a2fabc71ce3e7ae5']; current baseline is c331eec8b905007b785fa494041af1efc2139a89.
- Exact selectors:
  - `tests/journeys/phase22/code/test_j24_privacy_lifecycle.py::test_p22_j24_real_privacy_lifecycle`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/J24-privacy-lifecycle-001/result.json` — exists=true, recorded_head=`bce2b978008a14d337ff6040a2fabc71ce3e7ae5`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: bin/solar: do_backup, do_restore and uninstall; docs/UNINSTALL.md: Keep your data/Back up before removing; core/config/privacy.ts; scripts/check-privacy.sh; harness/lib/apple_notes_ingest.py: redact.

### P22-REPAIR-138 — Vertical :: TMUX

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J18
- Expected behavior: Register and operate tmux sessions and panes as controlled terminal and runtime surfaces, including ownership, attach and detach, pane-state and log inspection, notifications, recovery, and isolation between runs.
- Expected output: Created or reused isolated tmux sessions/panes, assignments and titles, dispatched commands, captured logs/state, runtime/blocker classification, notifications, recovery results, and status artifacts.
- Recorded observation: The feature worked in local SolarUbuntu/WSL2, but other Linux setups and multi-session use were not tested.
- Production entrypoints: harness/coordinator.sh dispatch and pane helpers; harness/coordinator-watchdog.sh recovery; harness/lib/symphony/status-server.py _run_tmux/_pane_snapshot/_main_screen; harness/lib/cli/solar_ui_lite.py collect_runtime.
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j18_real_linux_status_lifecycle.py::test_p22_j18_real_linux_status_lifecycle`
  - `tests/journeys/phase22/code/test_j18_tmux_cli_status_config.py::test_p22_j18_tmux_cli_status_config`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/T3-tmux-prep-001/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: harness/coordinator.sh: tmux dispatch/capture and runtime_status_transition; harness/lib/symphony/status-server.py: _pane_snapshot/_main_screen; tests/harness/test_no_direct_tmux_send_keys.py; tests/harness/test_tmux_notification_bridge.py. The former d5 real-home probe is quarantined and is not accepted evidence.

### P22-REPAIR-139 — Vertical :: LLM Config

- Recorded status: `PASS_WITH_KNOWN_LIMITATIONS`
- Priority: `P1_LIMITATION_REQUIRES_SEVERITY_TRIAGE`
- Freshness: `NEEDS_CURRENT_BASELINE_RERUN`
- Confidence: `MEDIUM_BROAD_JOURNEY_LIMITATION`
- Evidence basis: P22-J18
- Expected behavior: Configure provider endpoints and credential references, register available models and aliases, assign role-specific model defaults, and validate the effective model-routing configuration without exposing raw secrets.
- Expected output: Sanitized effective settings, resolved canonical model IDs/flags/provider routes, updated user config, model-doctor/readiness output, or explicit invalid/disabled/auth-missing errors.
- Recorded observation: Settings were saved and read without exposing secrets, but the expected model name was not fully preserved.
- Production entrypoints: harness/lib/symphony/status-server.py: _model_id_to_alias, _alias_to_model_id, _write_user_config_models, _write_user_config_runtime, _write_provider_keys and _settings_write_payload; harness/model_registry.py.
- Freshness warnings:
  - Recorded or candidate evidence is missing on this machine: ['.codex-tmp/known-issue-repairs/final-integration/result.json']
- Exact selectors:
  - `tests/journeys/phase22/code/test_j18_real_linux_status_lifecycle.py::test_p22_j18_real_linux_status_lifecycle`
  - `tests/journeys/phase22/code/test_j18_tmux_cli_status_config.py::test_p22_j18_tmux_cli_status_config`
- Evidence paths:
  - `.codex-tmp/known-issue-repairs/final-integration/result.json` — exists=false, recorded_head=`unknown`
  - `.codex-tmp/phase22-worker-results/T3-tmux-prep-001/result.json` — exists=true, recorded_head=`unknown`
- Required first decision: `CONFIRMED_REPRODUCIBLE`, `STALE_ALREADY_FIXED`, `MAPPING_ERROR`, `NOT_REPRODUCIBLE`, `ENVIRONMENT_BLOCKED`, or `INSUFFICIENT_EVIDENCE`.
- Repair success evidence: harness/config/model-registry.json; harness/config/model-scenario-routing.json; harness/lib/symphony/status-server.py: model alias/settings helpers; tests/harness/test_model_registry_codex_aliases.py. The older real-home shell guards are quarantined and are not accepted evidence.
