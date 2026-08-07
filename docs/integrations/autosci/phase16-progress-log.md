# AutoSci Phase 16 Progress Log

Logged: 2026-06-18 17:35 EDT
Branch: `feature/autosci-solar-native`

## Scope

Phase 16 implemented fixture-mode workflow evolution feedback as Solar-native
`workflow_evolution.v1` evidence. The new `evolve_workflow` bridge action reads
an intentionally failed workflow run, collects concrete failure signals, writes
`recommended_changes.md`, and emits reviewable proposed changes without editing
capsules, schemas, gates, routing, or workflow templates.

This phase does not change scheduler behavior, product logic, report logic,
fallback behavior, scoring, routing, quota, leases, model selection, or workflow
ownership. Evolution output remains proposed-only until a human accepts or
rejects each change.

## Files Changed

| Artifact group | Operation | Paths |
|---|---|---|
| Bridge action | Updated | `harness/plugins/autosci/bin/autosci_bridge.py` |
| Workflow evolution adapter | Added | `harness/plugins/autosci/adapters/autosci_to_workflow_evolution.py` |
| Evaluator gate | Updated | `harness/evaluators/scientific/workflow_evolution_gate.py` |
| Evidence schema docs | Updated | `harness/schemas/evidence/workflow_evolution.v1.schema.json`, sample fixture |
| Fixture envelope | Added | `tests/plugins/autosci/fixtures/envelope.evolve_workflow.failed_run.json` |
| Gate fixtures/tests | Added/updated | `tests/harness/evaluators/scientific/test_workflow_evolution_gate.py`, workflow evolution fixtures |
| Plugin metadata/tests | Updated | `harness/plugins/autosci/manifest.yaml`, README, plugin tests |
| Capability capsule | Updated | `harness/capability-capsules/cap.research-workflow-evolve.yaml` |

## Added / Updated / Used Classification

| Item | Phase 16 classification | Note |
|---|---|---|
| `ScientificWorkflowEvolver` | used | Existing logical operator; no hidden AutoSci runner introduced. |
| `cap.research-workflow-evolve` | used/updated | Capsule now documents recommended changes and review-only output. |
| `workflow_evolution.v1` | used/extended | Schema documents `collected`, `proposed_changes`, `review`, and `recommended_changes_path`; gate enforces Phase 16 semantics. |
| `evolve_workflow` bridge action | added | Reads failed-run evidence and emits proposed-only workflow evolution artifacts. |
| `workflow_evolution_gate.py` | updated | Requires failed nodes, gate/runtime reasons, category-separated proposals, review controls, and recommended changes artifact. |

## Human-Testable Artifact Contract

| Artifact | Schema/type | Path |
|---|---|---|
| Workflow evolution evidence | `workflow_evolution.v1` | `harness/artifacts/scientific/smoke/workflow_evolution.json` |
| Recommended changes | `markdown` | `harness/artifacts/scientific/smoke/recommended_changes.md` |
| Patch candidates | `directory` | `harness/artifacts/scientific/smoke/patch_candidates/` |
| Bridge result wrapper | `json` | `harness/artifacts/scientific/smoke/evolve_workflow.result.json` |

## Manual Checklist

| Checklist item | Status | Evidence |
|---|---|---|
| Evolution report cites concrete failed nodes | ok | `experiment_run` is cited with `G_EXPERIMENT_RUN`. |
| It proposes bounded changes | ok | Proposed changes are `proposed_only` and `review_required`. |
| It separates manual changes from schema/gate changes | ok | Proposal categories include `manual`, `gate`, `schema`, `workflow_template`, and `routing`. |
| It does not silently edit protected core runtime | ok | Review block has `protected_core_edits_applied: false`; bridge only writes artifacts. |
| Human can accept/reject each proposed change | ok | `recommended_changes.md` states proposed-only review controls; evidence has per-change ids. |

## Checks Run

| Check | Status | Note |
|---|---|---|
| Solar context injection | warn | Repo-local context inject worked; Mirage source was degraded. |
| Phase 16 bridge smoke | ok | `evolve_workflow` generated `workflow_evolution.json`, `recommended_changes.md`, and `patch_candidates/`. |
| Workflow evolution gate | ok | `workflow_evolution_gate.py artifacts/scientific/smoke/workflow_evolution.json` passed with no warnings. |
| Python syntax | ok | `py_compile` passed for bridge, adapter, and gate. |
| Plugin/evaluator tests | ok | `pytest harness/plugins/autosci/tests tests/harness/evaluators/scientific`: 50 passed. |
| Plugin validation | ok | `plugin_loader.py validate --id autosci` passed. |
| Schema validation | ok | Workflow evolution sample, pass fixture, and smoke artifact validate against `workflow_evolution.v1`. |
| Whitespace check | ok | `git diff --check` passed for Phase 16 touched files. |

## Warnings / Caveats

- Repo-local Solar context injection worked, but Mirage reported degraded source
  status.
- Phase 16 uses fixture-mode failed-run evidence. It does not run live external
  scientific validation, paid API calls, or autonomous workflow mutation.
- Existing dirty/untracked files outside this Phase 16 scope were left
  untouched. Some files touched by Phase 16 were already dirty before this
  phase, so commit isolation needs care.

## Done State

Phase 16 is complete for the fixture-mode Solar-native workflow evolution scope:
failed workflow evidence is converted into `workflow_evolution.v1`,
`recommended_changes.md` and `patch_candidates/` are produced, deterministic
gates enforce governance, and plugin/evaluator tests pass.

## Checker Fix Pass — Patch Candidates Output

Logged: 2026-06-18 17:42 EDT

| Item | Status | Note |
|---|---|---|
| Missing expected output | fixed | `evolve_workflow` now creates `artifacts/scientific/smoke/patch_candidates/`. |
| Evidence artifact registry | fixed | `workflow_evolution.v1` now includes a `patch_candidates_directory` artifact and `patch_candidates_path`. |
| Gate coverage | fixed | `workflow_evolution_gate.py` now rejects evidence missing the `patch_candidates_directory` artifact. |
| Review-only behavior | ok | The directory is created empty for human review; no patch is applied automatically. |
| Fixture/test coverage | ok | Phase 16 bridge smoke and workflow evolution fixtures now assert the directory output. |
