# AutoSci Phase 12 Progress Log

Logged: 2026-06-18 16:33:00 EDT
Branch: `feature/autosci-solar-native`

## Scope

Phase 12 implemented fixture-mode experiment design, run, monitor, and result
collection through Solar-native Evidence ABI artifacts. Experiment plans now
record execution mode, baseline, success criteria, command allowlist, and
resource limits. Experiment results record command, logs, metrics, exit code,
artifacts, and evidence ids. Experiment monitor emits `experiment_status.v1`
status evidence derived from local result evidence.

This phase does not change scheduler behavior, product logic, report logic,
fallback behavior, scoring, routing, quota, leases, or model selection.
Non-fixture external execution remains blocked unless the envelope carries
explicit approval.

## Files Changed

| Artifact group | Operation | Paths |
|---|---|---|
| Bridge actions | Updated | `harness/plugins/autosci/bin/autosci_bridge.py` |
| Experiment adapters | Added/updated | `harness/plugins/autosci/adapters/autosci_to_experiment_{plan,result,status}.py` |
| Evaluator gates | Added/updated | `harness/evaluators/scientific/experiment_{plan,result,status}_gate.py` |
| Fixture envelopes | Added/updated | `tests/plugins/autosci/fixtures/envelope.{design_experiment,run_experiment,run_experiment.fixture,monitor_experiment}.json` |
| Plugin/evaluator tests | Added/updated | `tests/plugins/autosci/test_*.py`, `tests/harness/evaluators/scientific/test_experiment_status_gate.py` |
| Physical/logical operators | Updated | `harness/config/{physical,logical}-operators.json` |
| README | Updated | `harness/plugins/autosci/README.md` |

## Added / Updated / Used Classification

Phase 12 uses earlier logical-operator work. It should not be described as
adding `ScientificExperimentDesigner`, `ScientificExperimentRunner`, or
`ScientificExperimentMonitor`.

| Item | Phase 12 classification | Originally introduced | Phase 12 note |
|---|---|---|---|
| `ScientificExperimentDesigner` | used | Phase 3 | Existing logical operator; no Phase 12 logical-operator addition. |
| `ScientificExperimentRunner` | used | Phase 3 | Existing logical operator; no Phase 12 logical-operator addition. |
| `ScientificExperimentMonitor` | used | Phase 3 | Existing logical operator; Phase 12 adds physical binding. |
| `design_experiment` bridge action | updated | Phase 4/5 path | Now emits bounded `experiment_plan.v1` with baseline, success criteria, execution mode, and command allowlist. |
| `run_experiment` bridge action | updated | Phase 4/5 path | Now enforces safe execution mode, records command/logs/metrics, and fails unapproved external runs. |
| `monitor_experiment` bridge action | added | Phase 12 | New action for `experiment_status.v1`. |
| `autosci-experiment-design-worker` | used | Phase 5 | Existing worker; Phase 12 validated runtime submit. |
| `autosci-experiment-run-worker` | used/updated | Phase 5 | Existing worker; now uses stronger run action output. |
| `autosci-experiment-monitor-worker` | added | Phase 12 | New physical worker bound to `ScientificExperimentMonitor`. |
| `experiment_status_gate.py` | added | Phase 12 | Deterministic gate for monitor status evidence. |
| `autosci_to_experiment_status.py` | added | Phase 12 | Converts monitor output to `experiment_status.v1`. |

## Backend Actions

| Action | Phase 12 classification | Evidence ABI | Note |
|---|---|---|---|
| `design_experiment` | updated | `experiment_plan.v1` | Emits a bounded fixture experiment plan. |
| `run_experiment` | updated | `experiment_result.v1` | Emits metrics, command, logs, and run artifact; blocks unapproved external execution as failed evidence. |
| `monitor_experiment` | added | `experiment_status.v1` | Emits completed/failed/unknown status from local result evidence. |

## Physical Operator Wiring

| Operator | Phase 12 classification | Status | Action |
|---|---|---|---|
| `autosci-experiment-design-worker` | used | enabled | `design_experiment` |
| `autosci-experiment-run-worker` | used/updated | enabled | `run_experiment` |
| `autosci-experiment-monitor-worker` | added | enabled | `monitor_experiment` |

## Human-Testable Artifact Contract

The canonical Phase 12 smoke outputs are:

| Artifact | Schema | Path |
|---|---|---|
| Experiment plan | `experiment_plan.v1` | `harness/artifacts/scientific/smoke/experiment_plan.json` |
| Experiment result | `experiment_result.v1` | `harness/artifacts/scientific/smoke/experiment_result.json` |
| Experiment status | `experiment_status.v1` | `harness/artifacts/scientific/smoke/experiment_status.json` |
| Run log | text | `harness/artifacts/scientific/smoke/exp-001.log` |

## Checks Run

| Check | Status | Note |
|---|---|---|
| Solar context injection | warn | Repo-local context inject worked; Mirage source was degraded. |
| Physical operator JSON | ok | `json.tool config/physical-operators.json` passed. |
| Logical operator JSON | ok | `json.tool config/logical-operators.json` passed. |
| Python syntax | ok | `py_compile` passed for bridge, adapters, and experiment gates. |
| Phase 12 bridge smoke | ok | Wrote `experiment_plan.json`, `experiment_result.json`, `experiment_status.json`, and `exp-001.log`. |
| Experiment plan gate | ok | `experiment_plan_gate.py artifacts/scientific/smoke/experiment_plan.json` passed. |
| Experiment result gate | ok | `experiment_result_gate.py artifacts/scientific/smoke/experiment_result.json` passed. |
| Experiment status gate | ok | `experiment_status_gate.py artifacts/scientific/smoke/experiment_status.json` passed. |
| Plugin/evaluator tests | ok | `pytest plugins/autosci/tests tests/evaluators/scientific`: 30 passed. |
| Operator runtime submit | ok | Design, run, and monitor workers completed with exit code 0. |
| Runtime experiment gates | ok | Runtime plan/result/status artifacts passed gates. |
| Plugin validation | ok | `plugin_loader.py validate --id autosci` passed. |
| Workflow validation | ok | Scientific experiment and full research lifecycle graphs passed `graph_scheduler.py validate`. |
| Architecture guard | ok | Full lifecycle strict guard passed. |
| Whitespace check | ok | `git diff --check` passed. |

## Warnings / Caveats

- AutoSci physical operators still use the existing placeholder
  `owner_host: solar@example-host` and do not declare explicit `host_id`; this is
  the pre-existing scheduler-clean warning, not changed here.
- Repo-local Solar context injection worked, but Mirage reported degraded source
  status.
- Several `.venv` invocations printed `RuntimeWarning` about `sys.prefix` /
  `sys.exec_prefix` when called as `../.venv/bin/python` from `harness/`; all
  affected commands exited successfully.
- Phase 12 fixture execution does not perform real benchmark, network, paid, or
  external command execution. Unapproved external modes are failed evidence.
- Existing dirty/untracked files outside this Phase 12 scope were left
  untouched.

## Done State

Phase 12 is complete for the fixture-mode Solar-native adapter scope: experiment
plan, result collection, monitor status, safe execution gating, physical worker
submit, evaluator gates, plugin tests, workflow validation, architecture guard,
and whitespace checks all pass.

## Checker Fix Pass — Monitor Capability Manifest

Follow-up checker found that the Phase 12 monitor worker and workflows referenced
`cap.research-experiment-monitor`, but the AutoSci plugin manifest only declared
experiment design and run capabilities. Operations performed:

| Operation | Status | Note |
|---|---|---|
| Manifest capability fix | ok | Added `cap.research-experiment-monitor` to `harness/plugins/autosci/manifest.yaml`. |
| Regression coverage | ok | Added manifest capability assertion for design/run/monitor lifecycle capabilities. |
| Product/runtime logic | ok | No experiment execution, scheduler, routing, scoring, or evidence conversion logic changed. |

Rerun checker after the manifest fix:

| Check | Status | Evidence |
|---|---|---|
| Phase 12 smoke actions | ok | `design_experiment`, `run_experiment`, and `monitor_experiment` exited 0 and rewrote smoke evidence. |
| Experiment gates | ok | `experiment_plan_gate.py`, `experiment_result_gate.py`, and `experiment_status_gate.py` passed against smoke artifacts. |
| Plugin/evaluator tests | ok | `bin/python3 -m pytest -q plugins/autosci/tests tests/evaluators/scientific`: 31 passed. |
| Plugin validation | ok | `bin/python3 lib/plugin_loader.py validate --id autosci --json`: `valid: true`. |
| Capability discovery | ok | `bin/python3 lib/plugin_loader.py list --json` now reports `cap.research-experiment-monitor` for `autosci`. |
| Workflow validation | ok | `scientific_experiment_lifecycle_v1` and `scientific_research_lifecycle_full_v1` passed `graph_scheduler.py validate`. |
| Architecture guard | ok | Experiment lifecycle and full lifecycle graphs passed strict guard. |
| Schema validation | ok | Smoke `experiment_plan.v1`, `experiment_result.v1`, and `experiment_status.v1` validated against JSON schemas. |
| Whitespace check | ok | `git diff --check` passed for the manifest, test, and Phase 12 log files touched in this fix. |
