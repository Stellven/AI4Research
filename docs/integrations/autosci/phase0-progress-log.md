# AutoSci Phase 0 Progress Log

Logged: 2026-06-16 15:52:53 EDT
Updated: 2026-06-17 14:53:26 EDT
Branch: `feature/autosci-solar-native`

| Path or artifact | Operation | Operation time | Note |
|---|---|---|---|
| `docs/integrations/autosci/autosci-workflow-map.md` | Added | 2026-06-16T15:36:26-04:00 | Phase 0 workflow inventory, Solar-native boundary, support utilities, SciDAG/SciEvolve notes. |
| `docs/integrations/autosci/autosci-to-solar-capability-map.yaml` | Added | 2026-06-16T15:36:26-04:00 | AutoSci command-to-Solar logical operator, capsule, Evidence ABI, support, and excluded utility mapping. |
| `docs/integrations/autosci/autosci-artifact-map.yaml` | Added | 2026-06-16T15:36:26-04:00 | AutoSci artifact-to-Solar Evidence ABI coverage, including `/ask`, `/reset`, and SciEvolve artifacts. |
| `.test-home/python-userbase/` | Local dependency install, ignored | 2026-06-16 15:52:53 EDT | Installed `pytest` for the active OpenSolar `python3` with dependencies stored inside the repo-local ignored `.test-home/` tree. |
| `.venv/` | Local dependency install, ignored | 2026-06-16 16:30:24 EDT | Rebuilt OpenSolar-local venv from mise Python 3.14.2 and installed pytest plus required third-party packages inside the project directory. |
| `docs/integrations/autosci/dependency-installation.md` | Added/modified | 2026-06-16 to 2026-06-17 EDT | Tracks rebuildable OpenSolar and AutoSci dependency environments, approved uv cache usage, and the global `jsonschema` CLI install. |
| `docs/integrations/autosci/phase0-progress-log.md` | Added | 2026-06-16 15:52:53 EDT | Brief progress log for Phase 0 files, notes, dependency install, and checks. |

## Checks

| Check | Status | Note |
|---|---|---|
| Solar context injection | ok with warning | Used repo-local `HARNESS_DIR=<OpenSolar>/harness bash solar-harness.sh context inject`; Mirage source was degraded. |
| AutoSci dependency smoke | ok | AutoSci `.venv` imports and tool `--help` checks passed. |
| YAML parse | ok | Phase 0 YAML files parsed with Ruby YAML. |
| Whitespace check | ok | `git diff --check -- docs/integrations/autosci` passed. |
| Dependency install record | ok | OpenSolar `.venv`, AutoSci `.venv`, approved uv cache, and global `jsonschema==4.26.0` CLI state are recorded in `dependency-installation.md`. |
| OpenSolar pytest startup | warn | `pytest` and third-party imports are installed in `.venv`; full harness collection still fails on 51 unrelated first-party import/path/API issues listed below. |

## Harness-Wide Pytest Collection Notes

Logged: 2026-06-16 16:30:24 EDT

This is not a Phase 0 completeness gate. The command below collects the whole `harness/` test tree, including unrelated Solar capabilities, legacy research units, GitHub intelligence, YouTube intelligence, Gemini Deep Research, and duplicate test-module basenames.

Command:

```bash
cd "$SOLAR_REPO/harness"
"$SOLAR_REPO/.venv/bin/python" -m pytest -p no:cacheprovider --collect-only -q
```

Result: `3738 tests collected, 51 errors during collection`.

Blocked collection modules:

| Test module | Blocking category | Phase 0 relationship |
|---|---|---|
| `integrations/gemini_deep_research/evidence/test_completion_evidence.py` | First-party import path | Unrelated harness capability |
| `integrations/gemini_deep_research/orchestration/test_auto_activation.py` | First-party import path | Unrelated harness capability |
| `lib/capabilities/gemini_deep_research/tests/test_core.py` | First-party import path | Unrelated harness capability |
| `tests/benchmark/test_benchmark_registry.py` | First-party import/API | Unrelated benchmark surface |
| `tests/benchmark/test_benchmark_report_schema.py` | First-party import/API | Unrelated benchmark surface |
| `tests/benchmark/test_solar_solver.py` | First-party import/API | Unrelated benchmark surface |
| `tests/benchmark/test_terminal_bench_adapter.py` | First-party import/API | Unrelated benchmark surface |
| `tests/gemini_deep_research/control/test_negative_and_activation.py` | First-party import path | Unrelated harness capability |
| `tests/gemini_deep_research/e2e/test_o1_o6_flow.py` | First-party import path | Unrelated harness capability |
| `tests/graph/test_multi_task_runner_status_surface.py` | Stale first-party symbol import | Unrelated graph status surface |
| `tests/influence/test_models.py` | Duplicate module/import mismatch | Unrelated influence surface |
| `tests/integration/test_youtube_e2e.py` | Missing first-party migration module | Unrelated YouTube surface |
| `tests/livework/test_schemas.py` | Duplicate module/import mismatch | Unrelated livework surface |
| `tests/research/integration/test_deepresearch_s6_integration.py` | Duplicate module/import mismatch | Unrelated research surface |
| `tests/research/integration/test_local_command_fixture.py` | Duplicate module/import mismatch | Unrelated research surface |
| `tests/research/integration/test_pipeline.py` | Duplicate module/import mismatch | Unrelated research surface |
| `tests/research/integration/test_real_vs_estimated_switch.py` | Duplicate module/import mismatch | Unrelated research surface |
| `tests/research/negative/test_negative_control.py` | Duplicate module/import mismatch | Unrelated research surface |
| `tests/research/survey/activation_proof/test_status_epic_activation.py` | First-party import path | Unrelated research survey surface |
| `tests/research/survey/cli/test_argument_density_view.py` | Duplicate module/import mismatch | Unrelated research survey surface |
| `tests/research/survey/cli/test_contradiction_matrix_view.py` | Duplicate module/import mismatch | Unrelated research survey surface |
| `tests/research/survey/cli/test_exploration_view.py` | Duplicate module/import mismatch | Unrelated research survey surface |
| `tests/research/survey/cli/test_gate_report_view.py` | Duplicate module/import mismatch | Unrelated research survey surface |
| `tests/research/survey/cli/test_source_quality_view.py` | Duplicate module/import mismatch | Unrelated research survey surface |
| `tests/research/survey/test_schemas.py` | Duplicate module/import mismatch | Unrelated research survey surface |
| `tests/research_survey/test_schemas.py` | Duplicate module/import mismatch | Unrelated research survey surface |
| `tests/research_unit/test_cli.py` | Duplicate module/import mismatch | Unrelated research unit surface |
| `tests/research_unit/test_evaluator.py` | Duplicate module/import mismatch | Unrelated research unit surface |
| `tests/research_unit/test_schemas.py` | Duplicate module/import mismatch | Unrelated research unit surface |
| `tests/test_briefs.py` | Stale first-party symbol import | Unrelated GitHub intelligence surface |
| `tests/test_cards.py` | Stale first-party symbol import | Unrelated GitHub intelligence surface |
| `tests/test_detectors.py` | Stale first-party symbol import | Unrelated GitHub intelligence surface |
| `tests/test_evidence_compression.py` | Stale first-party symbol import | Unrelated GitHub intelligence surface |
| `tests/test_evidence_ledger.py` | Duplicate module/import mismatch | Unrelated evidence ledger surface |
| `tests/test_hf_paper_insight_collection.py` | Ambiguous `schema` import path | Unrelated HF paper insight surface |
| `tests/test_hf_paper_insight_runtime.py` | Ambiguous `schema` import path | Unrelated HF paper insight surface |
| `tests/test_hf_paper_insight_schema.py` | Ambiguous `schema` import path | Unrelated HF paper insight surface |
| `tests/test_hf_paper_insight_scoring.py` | Ambiguous `schema` import path | Unrelated HF paper insight surface |
| `tests/test_operator_router.py` | Duplicate module/import mismatch | Unrelated operator router surface |
| `tests/test_pipeline.py` | Duplicate module/import mismatch | Unrelated pipeline surface |
| `tests/test_prerequisite_resolver.py` | Duplicate module/import mismatch | Unrelated graph prerequisite surface |
| `tests/test_schemas.py` | Duplicate module/import mismatch | Unrelated schema surface |
| `tests/test_youtube_cli.py` | Missing first-party migration module | Unrelated YouTube surface |
| `tests/test_youtube_dashboard.py` | Missing first-party migration module | Unrelated YouTube surface |
| `tests/test_youtube_job_scheduler.py` | Missing first-party migration module | Unrelated YouTube surface |
| `tests/test_youtube_migration.py` | Missing first-party migration module | Unrelated YouTube surface |
| `tests/test_youtube_pollution_repair.py` | Missing first-party migration module | Unrelated YouTube surface |
| `tests/test_youtube_premium_escape.py` | Missing first-party migration module | Unrelated YouTube surface |
| `tests/test_youtube_quality_gate.py` | Missing first-party migration module | Unrelated YouTube surface |
| `tests/test_youtube_transcript_storage.py` | Missing first-party migration module | Unrelated YouTube surface |
| `tools/research/test_figure_grounding.py` | Duplicate module/import mismatch | Unrelated research tooling surface |

## Commit History

| Commit | Time | Summary |
|---|---|---|
| `5473c019` | 2026-06-16T15:36:26-04:00 | Document AutoSci Solar-native phase 0 mapping. |
| `1397285c` | 2026-06-16T15:52:53-04:00 | Add Phase 0 progress log. |
| `06e0d72e` | 2026-06-16T16:30:24-04:00 | Document harness-wide pytest collection blockers for Phase 0 validation context. |
| `07d620e6` | 2026-06-16 | Track AutoSci validation dependencies. |
| `e0c78c40` | 2026-06-17 | Align dependency installs with updated install-dependencies skill guidance. |
| `275a8b63` | 2026-06-17 | Document global `jsonschema` CLI install. |
