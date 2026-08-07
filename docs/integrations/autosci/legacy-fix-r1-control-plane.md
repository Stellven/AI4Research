# Legacy Fix R1 Control Plane

## Scope

- Branch: `codex/legacy-fix-r1-control-plane`
- Baseline: `6a96d40153b919d97a2018c8267d7796d5e3e1d5`
- Worktree: `C:/Users/j50058254/Desktop/Github repo/.legacy-fix-worktrees/r1-control-plane`
- Legacy IDs addressed: `A02`, `A08`, `A09`, `T06`
- L2 covered: Request Capture, Acceptance Definition, Constraint Resolution, Intent Interpretation, Requirement Contract Confirmation, Ambiguity Resolution, Ambiguity Resolution & Readiness, Goal/Scope/Context Normalization, Constraint Compilation, Intent Classification & Compilation-Variant Selection, Task Contract & Acceptance Compilation, Intake, requirement, evaluation-sidecar adjacency.

## Root Cause

Solar had a research orchestration spine, but the control-plane contract was too thin. Full prompts were preserved in some runtime results, but language, delivery format, URL/PDF/evidence input semantics, user constraints, and readiness decisions were not consistently compiled into machine-checkable task contract fields. URL seeds without report wording could fall back to conservative ambiguity. The workflow taxonomy/config did not declare the currently supported research entry classes, and parity checks did not exercise the production `autosci_bridge.py research` entrypoint with same-input upstream-vs-Solar semantics.

The intake package path also exposed a Windows long-path failure in PM contract emission, which could block AutoSci intake regression before planner-ready graph assertions.

## Changes

- `harness/lib/research_orchestration/runtime.py`
  - Added `compile_research_requirements`.
  - Added machine-checkable `constraints.request_capture`, `constraints.user_constraints`, and `constraints.readiness_gate`.
  - Persisted `contracts/<run-id>.research_task_contract.json` for production research runs.
  - Added clarification/readiness gate returning `awaiting_human` for missing or contradictory core requirements.
  - Tightened Git provenance to require the supplied root itself to be a checkout.
- `harness/lib/research_orchestration/intent.py`
  - URL seeds now route to `research_synthesis` even when the prompt lacks report/survey wording.
- `harness/config/research-workflow-selection.v1.json`
  - Marked active and declared supported input kinds plus semantic entry stages for topic, URL, PDF, Markdown, external evidence, and experiment.
- `harness/config/task-taxonomy.json`
  - Added research task classes for topic synthesis, URL synthesis, paper ingestion, evidence resume, and experiment lifecycle.
- `harness/tools/codex_pm_router.py`
  - Added Windows long-path-safe PM package writes.
- Tests and fixtures:
  - Added production-entrypoint control-plane tests in `harness/tests/research_orchestration/test_research_control_plane_contract.py`.
  - Added captured upstream parity fixture `harness/tests/research_orchestration/fixtures/upstream_research_parity_contracts.json`.
  - Extended intent and workflow selection tests.

## Real Inputs And Artifacts

- URL prompt: `Analyze https://example.org/autosci-control-plane ... FULL_PROMPT_SENTINEL_R1_0123456789`
- Ambiguous prompt: `Research better agent memory`
- Parity fixture cases: topic, URL, PDF, evidence-resume.
- PDF input: `harness/tests/research_orchestration/fixtures/phase5/seed_portability/local_pdf_synthesis_seed.pdf`
- Evidence-resume input created during tests: `.codex-tmp/r1-tests/bt-final/.../prior-evidence.json`
- Production contract artifacts created during tests: `.codex-tmp/r1-tests/bt-final/.../contracts/*.research_task_contract.json`
- Manual debug artifact confirming Markdown lifecycle path-length diagnosis: `.codex-tmp/r1-tests/manual-markdown-debug/`

## Test Results

- `python -m pytest harness\tests\research_orchestration\test_research_control_plane_contract.py harness\tests\research_orchestration\test_research_intent.py harness\tests\research_orchestration\test_research_workflow_selection.py harness\tests\research_orchestration\test_research_production_routing.py harness\tests\research_orchestration\test_research_production_runtime.py --basetemp .codex-tmp\r1-tests\bt-all -o cache_dir=.codex-tmp\r1-tests\cache-all -q`
  - Exit code: `0`
  - Result: `52 passed`
- `python -m pytest tests\journeys\phase22\code\test_j16_tmux_requirements_builder.py --basetemp .codex-tmp\r1-tests\bt-j16 -o cache_dir=.codex-tmp\r1-tests\cache-j16 -q`
  - Exit code: `0`
  - Result: `1 skipped`
  - Reason: serial live/TMUX journey guard was not enabled.
- `python -m pytest harness\tests\test_autosci_intake_contract.py --basetemp .codex-tmp\r1-tests\bt-intake3 -o cache_dir=.codex-tmp\r1-tests\cache-intake3 -q`
  - Exit code: `0`
  - Result: `11 passed`
- Final combined command:
  - `python -m pytest harness\tests\research_orchestration\test_research_control_plane_contract.py harness\tests\research_orchestration\test_research_intent.py harness\tests\research_orchestration\test_research_workflow_selection.py harness\tests\research_orchestration\test_research_production_routing.py harness\tests\research_orchestration\test_research_production_runtime.py harness\tests\test_autosci_intake_contract.py --basetemp .codex-tmp\r1-tests\bt-final -o cache_dir=.codex-tmp\r1-tests\cache-final -q`
  - Exit code: `0`
  - Result: `63 passed`

## Success Conditions

- Full prompt not truncated: satisfied by production-entrypoint test and persisted contract sentinel/hash/length checks.
- URL request not misrouted to software development: satisfied by URL route tests and taxonomy additions.
- Ambiguous request produces clarification: satisfied by production-entrypoint `awaiting_human` readiness gate test.
- Clear request produces enforceable contract: satisfied by URL contract fields for language, format, URL, source count, and claim/evidence separation.
- Topic, URL, PDF, evidence-resume covered: satisfied by same-input parity fixture and production-entrypoint regression.
- Parity tests pass at current HEAD: satisfied by `test_same_input_upstream_fixture_vs_solar_production_entrypoint_parity`.
- Production entrypoint tested: satisfied by subprocess calls to `harness/plugins/autosci/bin/autosci_bridge.py research`.
- No monolithic `real_data_research` backend restored: satisfied; no such backend was added or reintroduced.
- Solar remains orchestrator: satisfied; Codex/model workers are not used for unbounded workflow ownership.

## Remaining Variants

- Live upstream `/research` was not executed. The regression uses a captured upstream semantic contract fixture because live provider/runtime authorization was not available.
- J16 live TMUX journey remains skipped unless `PHASE22_ENABLE_SERIAL_TMUX_JOURNEYS=1` and live journey authorization are explicitly provided.
- External evidence resume is covered through import-evidence contract and entry-stage parity, not a full live provider resume.

## Source Material Gaps

- `docs/integrations/autosci/legacy-issue-closure-ledger.md` was not present in this baseline worktree.
- `.codex-tmp/legacy-issue-audit-20260806/github-issue-map.json` was not present in this baseline worktree.
