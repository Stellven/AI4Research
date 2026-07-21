# AutoSci Phase 9 Progress Log

Logged: 2026-06-18 10:26:00 EDT
Branch: `feature/autosci-solar-native`

## Scope

Phase 9 implemented fixture-mode knowledge-foundation actions for the AutoSci
backend adapter. The actions emit Solar Evidence ABI artifacts for paper
ingestion, paper analysis, proposed memory updates, explicit graph updates, and
local fixture literature discovery.

This phase does not change scheduler behavior, product logic, report logic,
fallback behavior, scoring, routing, quota, leases, or model selection. Memory
updates are emitted as `operation: propose`; no wiki or memory state is mutated.

## Files Changed

| Artifact group | Operation | Paths |
|---|---|---|
| Bridge actions | Updated | `harness/plugins/autosci/bin/autosci_bridge.py` |
| Phase 9 converters | Added | `harness/plugins/autosci/adapters/autosci_to_{literature_discovery,research_memory_update,research_graph_update}.py` |
| Paper converter | Updated | `harness/plugins/autosci/adapters/autosci_to_research_paper.py` |
| Fixture envelopes | Added/updated | `harness/plugins/autosci/tests/fixtures/envelope.*.json` |
| Plugin tests | Updated | `harness/plugins/autosci/tests/test_*.py` |
| Physical operators | Updated | `harness/config/physical-operators.json` |
| README | Updated | `harness/plugins/autosci/README.md` |
| Evaluator environment shim | Added/updated | `harness/bin/python3`, `harness/evaluators/scientific/common.py` |

## Backend Actions

| Action | Evidence ABI | Note |
|---|---|---|
| `discover_literature` | `literature_discovery.v1` | Local fixture shortlist only; no live search. |
| `ingest_paper` | `research_paper.v1` | Parses local markdown and preserves source ref. |
| `analyze_paper` | `research_paper.v1` | Adds `outputs.paper.analysis` from local sections. |
| `update_memory` | `research_memory_update.v1` | Emits proposed memory changes only. |
| `update_graph` | `research_graph_update.v1` | Emits explicit proposed/confirmed edges. |

`ingest_paper` also writes Phase 9 smoke sidecars for
`research_memory_update.v1` and `research_graph_update.v1` so the plan's
single-command paper-ingestion smoke can validate the knowledge-foundation
artifacts without invoking a hidden AutoSci full workflow.

## Human-Testable Artifact Contract

The canonical graph output is `research_graph_update.json`, not
`graph_edges.jsonl`. The file is a `research_graph_update.v1` Solar Evidence ABI
payload, and the actual graph rows are nested in `outputs.edges`. A separate
`graph_edges.jsonl` export can be added later if a graph importer needs
line-delimited edge rows.

Scientific evaluator gates should be run with the repo `.venv` Python. From
`harness/`, use `bin/python3 evaluators/scientific/paper_gate.py ...`; the
wrapper resolves to `../.venv/bin/python`, where `jsonschema` is installed. The
gates also try the same-version repo `.venv` site-packages path when invoked by
bare Python, and fail closed if no Draft 2020-12 validator is available.

## Issues Encountered During Phase 9 Check

| Issue | Status | Cause | Fix approach | Resolution / disposition |
|---|---|---|---|---|
| Direct PDF ingest failed on `SkillGen.pdf` | scoped out | `ingest_paper` reads `inputs.paper_path` as UTF-8 markdown/text; it does not run a PDF extractor. | Do not add PDF parsing to Phase 9; keep the phase focused on native paper/memory/graph ABI flow. | Treat Phase 9 paper input as markdown fixture input. PDF-native ingestion is a future capability, not a Phase 9 blocker. |
| Temporary PDF-derived paper lived under runtime artifacts | fixed | The first SkillGen check used `artifacts/scientific/.../skillgen_paper.md` as a runnable workaround. | Promote the reusable sample into the AutoSci fixture tree so future tests do not depend on run artifacts. | Added canonical fixture `harness/plugins/autosci/tests/fixtures/skillgen_sample_paper.md`; redo check uses that fixture. |
| Graph artifact naming did not match the human plan | fixed | The human plan expected `graph_edges.jsonl`, but the implemented Solar Evidence ABI is `research_graph_update.v1` JSON with edges in `outputs.edges`. | Prefer the existing Evidence ABI contract over inventing a second graph file format in Phase 9. | Canonical output is now documented as `research_graph_update.json`; optional `graph_edges.jsonl` can be added later as a derived export. |
| `graph_edges.jsonl` could be created with the wrong content if named in an envelope | fixed by contract | The generic evidence writer writes a full Evidence ABI JSON object to `evidence_payload_path` regardless of file extension. | Stop naming the Evidence ABI payload as `.jsonl`; reserve `.jsonl` for future line-delimited exports only. | Envelopes and docs should use `research_graph_update.json` for the graph evidence payload. |
| Bare `python3` did not import `jsonschema` | fixed | Bare `python3` is the mise-managed runtime, while `jsonschema` is installed in OpenSolar `.venv` and as a separate pipx CLI. | Add a project-local Python entrypoint instead of installing Python libraries into the shared mise runtime. | Added `harness/bin/python3` wrapper to run repo `.venv/bin/python`; dependency record updated. |
| Malformed metadata could pass under weak fallback validation | fixed | `paper_gate.py` previously fell back to a shallow structural check when `jsonschema` was unavailable. | Make scientific gates fail closed when the Draft 2020-12 validator is unavailable. | Scientific gates now fail closed if `jsonschema` cannot be loaded; malformed metadata is rejected without warnings. |
| `jsonschema` CLI vs Python import caused confusion | clarified | `pipx` exposes `/Users/jamesyuan/.local/bin/jsonschema` as a CLI, but does not make `import jsonschema` available in mise Python. | Keep CLI and import roles separate: pipx for command-line use, `.venv` for Python imports. | Documented that project checks should use `.venv` via `harness/bin/python3`; global CLI remains only for command-line schema validation. |
| `harness/.venv` exists but lacks Phase 9 dependencies | clarified | `harness/.venv` is an older local venv and is not the current AutoSci Solar-native dependency target. | Use one source of truth for this integration: OpenSolar repo `.venv`, reached through `harness/bin/python3`. | Current dependency source of truth is OpenSolar `.venv` plus `harness/bin/python3`. |
| Physical operators still use placeholder `owner_host` | pre-existing | AutoSci physical operators retain `owner_host: solar@example-host` and no explicit `host_id`. | Do not change scheduler-clean ownership in Phase 9; keep the known Phase 5 issue visible. | Logged as a Phase 5 scheduler-clean warning; not introduced or changed by Phase 9. |
| Literature discovery is fixture-only | accepted limitation | `discover_literature` returns local fixture shortlist; no live search or network path is wired. | Keep discovery bounded and deterministic for this phase; live literature search belongs to a later backend expansion. | Remains in caveats; acceptable for Phase 9 fixture-mode knowledge-foundation validation. |

Redo verification used `artifacts/scientific/skillgen-phase9-redo-check/` and
confirmed `research_paper.v1`, `research_memory_update.v1`, and
`research_graph_update.v1` artifacts through `operator_runtime.submit`, with
`paper_gate`, `memory_update_gate`, graph schema validation, malformed metadata
rejection, strict architecture guard, and related pytest coverage all passing
without warnings.

## Physical Operator Wiring

| Operator | Status | Action |
|---|---|---|
| `autosci-literature-discover-worker` | enabled | `discover_literature` |
| `autosci-paper-ingest-worker` | enabled | `ingest_paper` |
| `autosci-paper-analyze-worker` | enabled | `analyze_paper` |
| `autosci-memory-update-worker` | enabled | `update_memory` |
| `autosci-graph-update-worker` | enabled | `update_graph` |

## Checks Run

| Check | Status | Note |
|---|---|---|
| Solar context injection | warn | Repo-local context inject worked; Mirage source was degraded. |
| Python syntax | ok | `py_compile` passed for bridge and adapters. |
| Plugin tests | ok | `pytest plugins/autosci/tests`: 8 passed. |
| Phase 9 ingest smoke | ok | Wrote `artifacts/scientific/smoke/research_paper.json`, `research_memory_update.json`, and `research_graph_update.json`. |
| Paper gate | ok | `paper_gate.py artifacts/scientific/smoke/research_paper.json` passed. |
| Memory gate | ok | `memory_update_gate.py artifacts/scientific/smoke/research_memory_update.json` passed. |
| Graph schema | ok | `jsonschema research_graph_update.v1` passed. |
| Literature schema | ok | `jsonschema literature_discovery.v1` passed. |
| Harness Python wrapper | ok | `bin/python3` resolves to repo `.venv/bin/python`; `jsonschema` import, graph schema validation, and malformed metadata rejection passed without warnings. |
| Operator runtime submit | ok | `autosci-memory-update-worker` and `autosci-graph-update-worker` completed with exit code 0. |
| Evaluator regression tests | ok | `pytest tests/evaluators/scientific`: 10 passed. |
| Workflow validation | ok | Paper-ingestion and full-lifecycle `graph_scheduler.py validate` passed. |
| Architecture guard | ok | Full lifecycle strict guard passed. |
| Physical operator JSON | ok | `json.tool config/physical-operators.json` passed. |
| Whitespace check | ok | `git diff --check` passed. |

## Caveats

- AutoSci physical operators still use the existing placeholder
  `owner_host: solar@example-host` and do not declare explicit `host_id`; this is
  the pre-existing Phase 5 scheduler-clean warning, not changed here.
- Existing dirty/untracked files outside this Phase 9 scope were left untouched.
- The Phase 9 discovery action is fixture-mode only; it does not perform live
  literature search.

## Done State

Phase 9 is complete when Solar can ingest a fixture paper and produce explicit
research memory and graph Evidence ABI artifacts through native bridge actions
and local command workers, with deterministic gates/schema checks accepting the
outputs.
