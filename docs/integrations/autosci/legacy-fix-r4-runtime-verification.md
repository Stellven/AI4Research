# Legacy Fix R4 Runtime Verification

Date: 2026-08-07
Branch: `codex/legacy-fix-r4-runtime-verification`
Baseline: `6a96d40153b919d97a2018c8267d7796d5e3e1d5`

## Scope

Repaired runtime and scientific verification paths for TaskGraph persistence, scheduler admission, claim verdict classification, report final evaluation, and benchmark process reporting.

## Changes

- TaskGraph spec saves now strip node runtime fields; durable runtime state remains in the task DAG state plane.
- `enqueue_ready` now re-checks node admission immediately before queueing and records admission evidence in the dispatch payload.
- Dry-run enqueue no longer imports queue/runtime dependencies before admission rejects stale assignments.
- Claim verdict ABI and gates now support explicit `insufficient` verdicts.
- AutoSci claim verification now rejects over-broad claims as `insufficient` when local/bounded evidence cannot support universal scope.
- Final publication evaluation now records blockers, residual risks, and follow-up while preserving content, structure, source, and user-requirement checks.
- Platform and Terminal-Bench benchmark outputs now separate benchmark execution status from target quality verdict.
- Journey harness fallback copies now ignore generated caches and plugin tests on Windows when symlink creation is unavailable.

## Regression Coverage

- TaskGraph runtime plane regression: saved spec no longer persists `status`, `assigned_to`, or `dispatch_id`; reload uses state plane.
- Scheduler admission regression: a stale assignment for a dependency-blocked node is rejected before queueing.
- Claim verdict regressions: supported, unsupported, and insufficient evidence fixtures produce distinct verdicts; supported overclaim risk is rejected.
- Report acceptance regression: final evaluation reaches accepted-with-limitations and exposes blockers/residual risks/follow-up.
- Benchmark regression: low target score still records benchmark execution `PASS` and target quality `FAIL`.

## Verification

Environment: local isolated venv at `.codex-tmp/r4-pytest-venv` with `pytest`, `jsonschema`, and `PyYAML`.

- `pytest tests/harness/graph/test_task_graph_runtime_planes.py tests/harness/graph/test_graph_scheduler_external_deps.py tests/harness/evaluators/scientific/test_claim_verdict_gate.py tests/plugins/autosci/scientific_lifecycle_action_operators/test_action_delivery_operators.py::test_full_action_delivery_chain_produces_traceable_usable_artifacts tests/plugins/autosci/scientific_lifecycle_action_operators/test_action_delivery_operators.py::test_claim_verification_never_promotes_incomplete_evidence tests/plugins/autosci/scientific_lifecycle_action_operators/test_action_delivery_operators.py::test_overbroad_supported_claim_is_classified_as_insufficient tests/harness/benchmark/test_benchmark_report_schema.py tests/harness/benchmark/test_terminal_bench_adapter.py::test_low_quality_harbor_result_keeps_benchmark_process_pass tests/harness/benchmark/test_platform_workflow_benchmark.py -q`
  - Result: `30 passed, 2 warnings`
- `pytest tests/journeys/phase22/code/test_j03_platform_benchmark.py tests/journeys/phase22/code/test_j09_report_delivery.py -q`
  - Result: `2 passed`
- `pytest tests/journeys/phase22/code/test_j08_claim_verification.py tests/journeys/phase22/code/test_j22_evidence_review_followup.py -q`
  - Result: `2 passed`

Local raw journey evidence was written under `outputs/phase22-real-journeys/` and was not staged.

## Notes

- A first J08/J03 run using a long Windows basetemp failed before product logic because fallback copying hit generated cache/deep plugin test paths. The journey runner now ignores those generated/non-runtime paths, and J08 passed with a short independent basetemp.
- A first J22 run failed because the isolated venv lacked `PyYAML`, so native wiki lint could not import `yaml`; after installing `PyYAML` in the isolated venv, J22 passed.
