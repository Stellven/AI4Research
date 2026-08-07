# AutoSci Phase 17 Progress Log

Logged: 2026-06-18 17:39 EDT
Branch: `feature/autosci-solar-native`

## Scope

Phase 17 cleaned Solar-facing naming so the architecture reads as a Solar-native
scientific research runtime using AutoSci only as a backend adapter package.

This phase does not change scheduler behavior, report logic, routing behavior,
fallback behavior, scoring, quota, leases, model selection, or backend execution
commands. The cleanup is limited to names, architecture policy labels, fixtures,
and tests that enforce those boundaries.

## Files Changed

| Artifact group | Operation | Paths |
|---|---|---|
| Capability capsule names | Renamed/restored | `harness/capability-capsules/cap.research-{claim-verify,report-plan,report-draft,publication-produce}.yaml` |
| Capsule references | Updated | `harness/capability-capsules/*.yaml`, capsule registry, logical/physical operator required capabilities |
| Workflow architecture policy | Updated | `harness/workflows/scientific*.json` |
| Lifecycle gate | Updated | `harness/evaluators/scientific/lifecycle_gate.py` |
| Evidence fixtures | Updated | `harness/schemas/evidence/fixtures/sample*.json` |
| Plugin manifest/tests | Updated | `harness/plugins/autosci/manifest.yaml`, `test_manifest_capabilities.py` |
| Naming regression test | Added | `tests/harness/evaluators/scientific/test_phase17_naming_cleanup.py` |
| Persona wording | Updated | `harness/personas/scientific-literature-discoverer.md` |

## Cleanup Results

| Area | Status | Evidence |
|---|---|---|
| Capability IDs | ok | `cap.scientific-*` references replaced with `cap.research-*`. |
| Logical operators | ok | Scientific workflow templates use `Scientific*` or `VerifierLite` operators. |
| Evidence ABI examples | ok | Fixture `sprint.autosci*` and `artifacts/autosci/fixtures` sample paths replaced with scientific names. |
| Workflow templates | ok | Workflow ids remain `scientific_*`; old AutoSci black-box policy labels removed. |
| Gate policy names | ok | Lifecycle gate now enforces `hidden-backend-full-workflow` and `backend-black-box-runner`. |
| Backend implementation package | ok | `plugins/autosci`, `autosci-*` workers, and `AutoSci` vendor metadata remain backend-specific. |

## Human Checklist

| Checklist item | Status | Evidence |
|---|---|---|
| Capabilities are `cap.research-*` | ok | New regression test scans capsules, config, schemas, and workflows. |
| Logical operators are `Scientific*` | ok | Workflow test asserts scientific or verifier operators. |
| Evidence schemas are generic scientific schemas | ok | Schema fixture identifiers and sample paths no longer use AutoSci fixture naming. |
| Workflows are scientific lifecycle workflows | ok | Workflow ids/titles remain Solar scientific runtime names. |
| Plugin package remains backend implementation only | ok | AutoSci naming remains in backend adapter metadata and physical bindings. |

## Checks Run

| Check | Status | Note |
|---|---|---|
| Solar context injection | warn | Repo-local context inject worked; Mirage source returned degraded status. |
| Python syntax | ok | `py_compile` passed for `lifecycle_gate.py`. |
| JSON validation | ok | Config, workflow, and schema sample JSON loaded successfully: 33 files. |
| Naming grep | ok | No `cap.scientific`, `cap.autosci`, old AutoSci black-box policy ids, `sprint.autosci`, or `artifacts/autosci/fixtures` remain in checked Solar-facing paths. |
| Lifecycle gate | ok | Full and resume lifecycle templates passed with no reasons or warnings. |
| Plugin/evaluator tests | ok | `pytest harness/plugins/autosci/tests tests/harness/evaluators/scientific`: 53 passed. |
| Plugin validation | ok | `plugin_loader.py validate --id autosci` passed. |
| Whitespace check | ok | `git diff --check` passed. |

## Warnings / Caveats

- Repo-local Solar context injection worked, but Mirage reported degraded source
  status.
- `python3 -m pytest` failed because system Python has no pytest installed; the
  same checks passed with the project `.venv/bin/pytest`.
- A broad lifecycle gate run against every `scientific*.json` template produced
  expected failures for partial templates that do not declare full lifecycle
  artifact contracts. The correct Phase 17 lifecycle gate check against
  `scientific_research_lifecycle_full_v1.json` and
  `scientific_research_resume_v1.json` passed.
- Existing dirty/untracked files from earlier AutoSci phases remain present.
  Some files touched by Phase 17 were already dirty, so safe commit isolation
  requires explicit grouping or a clean ownership decision.

## Done State

Phase 17 is complete for naming and architecture cleanup. Solar-facing
capabilities, workflows, policy labels, and Evidence ABI examples now read as a
generic scientific research runtime while AutoSci remains visible only as a
backend adapter and provenance binding.
