# AutoSci Phase 14 Progress Log

Logged: 2026-06-18 17:01:03 EDT
Branch: `feature/autosci-solar-native`

## Scope

Phase 14 implemented fixture-mode evidence-linked report and publication bundle
generation through Solar-native `scientific_report.v1` and
`publication_bundle.v1` artifacts. The existing `write_report` backend action now
assembles a report from supplied claim, verdict, experiment, and code evidence,
then writes local publication sidecars: `report.md`, `optional_poster.html`,
`optional_rebuttal.md`, `report_evidence_index.json`, and `report_plan.json`.

This phase does not change scheduler behavior, product logic, report product
logic, fallback behavior, scoring, routing, quota, leases, model selection, or
workflow ownership. Generated publication files are local fixture artifacts and
require human approval before any external handoff.

## Files Changed

| Artifact group | Operation | Paths |
|---|---|---|
| Bridge action | Updated | `harness/plugins/autosci/bin/autosci_bridge.py` |
| Report adapter | Updated | `harness/plugins/autosci/adapters/autosci_to_scientific_report.py` |
| Publication adapter | Added | `harness/plugins/autosci/adapters/autosci_to_publication_bundle.py` |
| Report gate | Updated | `harness/evaluators/scientific/report_gate.py` |
| Publication gate | Added | `harness/evaluators/scientific/publication_gate.py` |
| Fixture envelopes | Added/updated | `tests/plugins/autosci/fixtures/envelope.write_report*.json` |
| Plugin manifest | Updated | `harness/plugins/autosci/manifest.yaml` |
| Plugin/evaluator tests | Updated | `tests/plugins/autosci/test_bridge_smoke.py`, `tests/plugins/autosci/test_manifest_capabilities.py`, `tests/harness/evaluators/scientific/test_report_gate.py` |
| Test fixtures | Added/updated | `tests/harness/evaluators/scientific/fixtures/{pass,fail}/publication_bundle.json`, publication file artifacts, pass report fixture |
| README | Updated | `harness/plugins/autosci/README.md` |
| Progress log | Added | `docs/integrations/autosci/phase14-progress-log.md` |

## Added / Updated / Used Classification

Phase 14 uses earlier logical operator and worker wiring. It should not be
described as adding `ScientificReportPlanner`, `ScientificReportDrafter`,
`ScientificPublicationProducer`, or `autosci-report-worker`.

| Item | Phase 14 classification | Originally introduced | Phase 14 note |
|---|---|---|---|
| `ScientificReportPlanner` | used | Phase 3 | Existing logical operator; no Phase 14 logical-operator addition. |
| `ScientificReportDrafter` | used | Phase 3 | Existing logical operator; no Phase 14 logical-operator addition. |
| `ScientificPublicationProducer` | used | Phase 3 | Existing logical operator; no Phase 14 logical-operator addition. |
| `cap.scientific-report-plan` | used/declared in manifest | Phase 2 | Existing capsule; manifest declaration was added for AutoSci capability discovery. |
| `cap.scientific-report-draft` | used | Phase 2 | Already declared in manifest before Phase 14. |
| `cap.scientific-publication-produce` | used/declared in manifest | Phase 2 | Existing capsule; manifest declaration was added for AutoSci capability discovery. |
| `scientific_report.v1` | used | Phase 1 | Existing Evidence ABI schema; no schema change in Phase 14. |
| `publication_bundle.v1` | used | Phase 1 | Existing Evidence ABI schema; no schema change in Phase 14. |
| `write_report` bridge action | updated | Phase 4/5 path | Now emits evidence-linked report output and publication sidecars instead of a static report stub. |
| `autosci-report-worker` | used | Phase 5 | Existing physical worker; Phase 14 validated runtime submit. |
| `report_gate.py` | updated | Phase 8 | Now requires limitations section, artifact existence, and figure/table artifact linkage. |
| `publication_gate.py` | added | Phase 14 | Deterministic gate for `publication_bundle.v1` generated files and source report linkage. |
| `autosci_to_publication_bundle.py` | added | Phase 14 | Converts publication bundle data to `publication_bundle.v1`. |

## Backend Action Behavior

| Action | Phase 14 classification | Evidence ABI | Sidecars |
|---|---|---|---|
| `write_report` | updated | `scientific_report.v1` | `report.md`, `optional_poster.html`, `optional_rebuttal.md`, `report_evidence_index.json`, `report_plan.json`, `publication_bundle.json` |

The report includes summary, findings, evidence map, and limitations sections.
Unsupported or inconclusive claims are placed in an explicit unsupported-claims
section instead of being presented as successful.

## Human-Testable Artifact Contract

The canonical Phase 14 smoke outputs are:

| Artifact | Schema/type | Path |
|---|---|---|
| Scientific report evidence | `scientific_report.v1` | `harness/artifacts/scientific/smoke/scientific_report.json` |
| Publication bundle evidence | `publication_bundle.v1` | `harness/artifacts/scientific/smoke/publication_bundle.json` |
| Markdown report | `markdown_report` | `harness/artifacts/scientific/smoke/report.md` |
| Poster HTML | `optional_poster_html` | `harness/artifacts/scientific/smoke/optional_poster.html` |
| Rebuttal draft | `optional_rebuttal_markdown` | `harness/artifacts/scientific/smoke/optional_rebuttal.md` |
| Report plan sidecar | `report_plan_json` | `harness/artifacts/scientific/smoke/report_plan.json` |
| Evidence index sidecar | `report_evidence_index_json` | `harness/artifacts/scientific/smoke/report_evidence_index.json` |

## Manual Checklist

| Checklist item | Status | Evidence |
|---|---|---|
| Report sections map to evidence artifacts | ok | Report sections all carry evidence ids; report artifacts include generated file paths. |
| Unsupported claims are not presented as successful | ok | Report action lists unsupported/inconclusive claims separately; supported smoke has no unsupported claims. |
| Figures/tables link to artifacts | ok | `fig.optional-poster` and `table.evidence-map` link to top-level generated artifacts. |
| Report has limitations section | ok | Report action emits a `limitations` section and top-level limitations. |
| Publication bundle lists generated files | ok | Bundle files list `report_plan.json`, `report.md`, `report_evidence_index.json`, `optional_poster.html`, and `optional_rebuttal.md`. |
| Gate rejects report sections with no evidence references | ok | Existing report gate fail fixture still fails evidence-free sections. |

## Checks Run

| Check | Status | Note |
|---|---|---|
| Solar context injection | warn | Repo-local context inject worked; Mirage source was degraded. |
| Phase 14 bridge smoke | ok | `write_report` generated report, bundle, and local publication files. |
| Report gate | ok | `report_gate.py artifacts/scientific/smoke/scientific_report.json` passed. |
| Publication gate | ok | `publication_gate.py artifacts/scientific/smoke/publication_bundle.json` passed. |
| Python syntax | ok | `py_compile` passed for bridge, report/publication adapters, and report/publication gates. |
| Plugin/evaluator tests | ok | `pytest plugins/autosci/tests tests/evaluators/scientific`: 38 passed. |
| Operator runtime submit | ok | `autosci-report-worker` completed Phase 14 runtime envelope with exit code 0. |
| Physical operator JSON | ok | `json.tool config/physical-operators.json` passed. |
| Logical operator JSON | ok | `json.tool config/logical-operators.json` passed. |
| Plugin validation | ok | `plugin_loader.py validate --id autosci` passed. |
| Workflow validation | ok | `scientific_publication_lifecycle_v1` and full research lifecycle graphs passed `graph_scheduler.py validate`. |
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
- Phase 14 report and publication files are fixture-mode local artifacts only.
  They are not external scientific validation, real peer review, venue
  submission, paid API output, or live publication.
- Existing dirty/untracked files outside this Phase 14 scope were left
  untouched.

## Done State

Phase 14 is complete for the fixture-mode Solar-native adapter scope:
`write_report` produces evidence-linked `scientific_report.v1` and
`publication_bundle.v1` outputs, local publication files are listed and gated,
report/publication gates pass, the report worker runtime submit succeeds, and
plugin tests, workflow validation, architecture guard, and whitespace checks
pass.

## Checker Fix Pass — Expected Capsule And Artifact Names

Follow-up checker required Phase 14 capsule ids and generated artifact names to
match the expected naming contract. Operations performed:

| Operation | Status | Note |
|---|---|---|
| Capsule rename | ok | Renamed report/publication capsules and updated registry, operator configs, workflows, plugin manifest, and tests to `cap.scientific-report-plan`, `cap.scientific-report-draft`, and `cap.scientific-publication-produce`. |
| Artifact rename | ok | Updated `write_report` to generate `report_plan.json`, `report.md`, `report_evidence_index.json`, `publication_bundle.json`, `optional_poster.html`, and `optional_rebuttal.md`. |
| Publication bundle | ok | Bundle files now list the generated plan, markdown report, evidence index, optional poster, and optional rebuttal artifacts. |
| Runtime behavior | ok | No report scoring, unsupported-claim handling, or publication-routing product logic changed. |

Rerun checker after this fix:

| Check | Status | Evidence |
|---|---|---|
| Expected artifacts | ok | All expected Phase 14 artifact names exist under `artifacts/scientific/smoke/`. |
| ReportGate / PublicationGate | ok | `scientific_report.json` and `publication_bundle.json` passed deterministic gates. |
| Schema validation | ok | Phase 13/14 smoke evidence validated against `claim_verdict.v1`, `scientific_report.v1`, and `publication_bundle.v1` schemas. |
| Tests | ok | `bin/python3 -m pytest -q plugins/autosci/tests tests/evaluators/scientific`: 45 passed. |
| Workflow / architecture | ok | Claim verification, publication, full lifecycle, and resume graphs validated and passed strict guard. |
| Old capsule id check | ok | No old Phase 13/14 research-prefixed capsule ids remain in harness configs, workflows, capsules, manifest, or Phase 13/14 logs. |
