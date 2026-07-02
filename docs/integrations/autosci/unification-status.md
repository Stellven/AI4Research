# AutoSci Unification Status

Date: 2026-07-02
Agent: Agent A

## Branch And Source Anchors

- BetterSolar branch: `openJiuwen-Solar`
- BetterSolar base HEAD before 2026-07-02 parity sync: `c5ac70d394260b7e2cad591e68bcb63136daf374`
- OpenSolar source snapshot for 2026-07-02 parity sync: `feature/autosci-solar-native` at `0f4ee9fa4`
- Earlier OpenSolar source snapshot for initial import: `feature/autosci-solar-native` at `9d68c5baa9b814c086ae87f9c26f6ad0ae62ecd7`
- Native AutoSci reference: `main` at `71469e89eb1381e557661da0b90c0585c48288d7`
- OpenSolar and AutoSci were treated as read-only sources.

## OpenSolar Parity Sync - 2026-07-02

Compared BetterSolar against OpenSolar `0f4ee9fa4`.

Already content-identical before this sync:

- Active AutoSci route config: 28 routes, 17 `partial`, 11 `gated`, 0 `full`.
- AutoSci-specific logical operators and bindings in `harness/config/logical-operators.json`.
- AutoSci-specific physical workers in `harness/config/physical-operators.json`.
- `harness/plugins/autosci/` runtime/plugin code, except for local timestamp metadata.
- Existing scientific workflow runner files and workflow JSON content.

Imported missing OpenSolar parity assets:

- `harness/tools/audit_scientific_runtime_bindings.py`
- `harness/schemas/evidence/fixtures/`
- `harness/tests/config/test_autosci_research_capsule_registry.py`
- `harness/tests/evaluators/scientific/`, excluding bytecode caches
- `harness/tests/test_autosci_phase_c_premerge_readiness.py`
- `harness/tests/test_autosci_phase_c_unification_contracts.py`
- `harness/tests/test_autosci_priority_a_contracts.py`
- `harness/tests/test_autosci_priority_b_demo_contracts.py`
- `harness/tests/test-autosci-harness-entrypoint.sh`
- `harness/tests/test-autosci-premerge-gate.sh`

Merged BetterSolar-specific CI wiring:

- Added `.github/workflows/solar-ci.yml` job `autosci-premerge-gate`.
- Kept BetterSolar's existing workflow structure and `actions/checkout@v5`.
- Added `openJiuwen-Solar` to push triggers for this active branch.

BetterSolar adaptation after import:

- `docs/integrations/autosci/phase-c-solar-unification-import-manifest.v1.json` now reflects BetterSolar path facts for `bin/solar`, `core/daemon/skill-dispatcher.ts`, and `scripts/solar-codex-intake.sh`.
- `harness/plugins/autosci/bin/autosci_bridge.py` now lets `paper-plan` derive a ready idea graph from supplied `ideas_evidence`, `idea_evaluation_evidence`, and `experiment_result(_evidence)` inputs, not only prewritten wiki idea pages.
- Imported lifecycle tests now use structurally valid minimal PDF fixtures where they expect publication compile evidence to pass the existing PDF integrity gate.

Current active route status after sync:

- `route_count=28`
- `coverage={'partial': 17, 'gated': 11}`
- `full=[]`
- `gated=['/daily-arxiv', '/edit', '/exp-pilot-run', '/exp-run', '/paper-compile', '/poster', '/prefill', '/refine', '/reset', '/setup', '/visualize']`

No route was promoted to `full`.

Verification added in this sync:

- `harness/bin/python3 -m py_compile harness/plugins/autosci/bin/autosci_bridge.py`
- `harness/bin/python3 -m py_compile harness/tools/audit_scientific_runtime_bindings.py`
- `pytest -q harness/tests/test_autosci_phase_c_premerge_readiness.py harness/tests/test_autosci_phase_c_unification_contracts.py harness/tests/test_autosci_priority_a_contracts.py harness/tests/test_autosci_priority_b_demo_contracts.py`: `24 passed`
- `pytest -q harness/tests/evaluators/scientific harness/tests/config/test_autosci_research_capsule_registry.py`: `102 passed`
- `bash harness/tests/test-autosci-premerge-gate.sh`: passed
- `bash harness/tests/test-autosci-harness-entrypoint.sh`: passed

Local hygiene note: the first premerge gate run was blocked only by local Finder metadata at `.git/refs/.DS_Store`; that invalid local ref file was removed and the gate then passed.

## Imported Surfaces

Imported from the OpenSolar AutoSci source snapshot into BetterSolar:

- `.agents/skills/`
- `docs/integrations/autosci/`, excluding generated run/operator-smoke/current-parity-inventory artifacts
- `harness/plugins/autosci/`
- `harness/tools/run_scientific_workflow.py`
- `harness/tools/run_scientific_node_smoke.py`
- `harness/tools/run_scientific_lifecycle_smoke.py`
- `harness/workflows/scientific_*.json`
- `harness/evaluators/scientific/`
- `harness/schemas/evidence/*.schema.json`
- `harness/capability-capsules/cap.research-*.yaml`
- `harness/tests/integration/autosci_product_smoke_helpers.py`
- `harness/tests/integration/test_autosci_*.py`
- `harness/personas/scientific-*.md`
- `requirements/autosci-solar-native-dev.txt`
- `harness/bin/python3`

## Merged Shared Config

Manually merged AutoSci entries into BetterSolar rather than replacing existing registries:

- `harness/config/logical-operators.json`: added 19 `Scientific*` logical operators and their bindings.
- `harness/config/physical-operators.json`: added 19 `autosci-*` command workers.
- `harness/config/capability-capsules.registry.yaml`: added 19 `cap.research-*` capability capsule registry entries.

Preservation check: `mini-codex-gpt55-medium-evaluator-1` remains present in `physical-operators.json`.

## Product Dispatch

Added BetterSolar harness dispatch for AutoSci:

- `solar harness autosci ...` routes to `harness/plugins/autosci/bin/autosci_skill_shim.py`.
- Direct AutoSci-style commands such as `solar harness '$skills'` route through the same shim.
- `bin/solar` already forwarded `solar harness ...` to `harness/solar-harness.sh`, so no `bin/solar` edit was required.

## Ignore Rules

Updated `.gitignore` for generated local artifacts:

- `harness/artifacts/autosci/runs/`
- `harness/artifacts/autosci/operator-smoke/`
- `harness/artifacts/autosci/phase19/current-parity-inventory-*.json`
- `harness/artifacts/scientific/workflow-runs/`
- harness coordinator/watchdog/pane runtime files
- `.solar-backups/`

Tracking check returned no tracked files for generated AutoSci/scientific artifact paths, `.DS_Store`, or `.solar-backups`.

## Verification

Passed:

- `bash -n harness/solar-harness.sh`
- `python3 -m json.tool harness/config/logical-operators.json`
- `python3 -m json.tool harness/config/physical-operators.json`
- `ruby -ryaml -e 'YAML.load_file("harness/config/capability-capsules.registry.yaml")'`
- Presence checks for all 19 logical operators, logical bindings, physical operators, and capability registry entries.
- Product route checks:
  - `bin/solar harness autosci '$skills'` returned `ok=true`, `count=28`.
  - `bin/solar harness '$skills'` returned `ok=true`, `count=28`.
  - `bash harness/solar-harness.sh autosci '$review --help'` reached the AutoSci shim help.
- Imported pytest smokes, using BetterSolar's project-local `.venv`:
  - `tests/integration/test_autosci_routes_list.py`
  - `tests/integration/test_autosci_cli_dispatch.py`
  - `tests/integration/test_autosci_ingest_demo.py`
  - `tests/integration/test_autosci_research_scheduler_demo.py`
  - `tests/integration/test_autosci_review_demo.py`
  - `tests/integration/test_autosci_artifact_root.py`
  - Result: `6 passed in 5.24s`

Dependency note: BetterSolar now has a reproducible project-local `.venv`, built with `uv pip sync` from `requirements/autosci-solar-native-dev.txt`. The harness wrapper at `harness/bin/python3` points AutoSci subprocesses at that environment.

## Current Parity Status

Current status is integration-ready for review, not full AutoSci parity.

What works now:

- BetterSolar contains the AutoSci plugin, skills, schemas, workflows, evaluators, scientific personas, capability capsules, and product smoke tests from the current OpenSolar source snapshot.
- BetterSolar registries can resolve the imported scientific logical/physical/capability surfaces.
- Product-level dispatch reaches the AutoSci shim through both explicit `autosci` and direct dollar-command routes.
- Deterministic dry-run/product smokes pass with BetterSolar's local `.venv`.

What is still not claimed:

- No route was promoted to `full`.
- Full provider parity is not proven.
- Approval-gated side effects remain gated and were not executed.
- Real online evidence, Review LLM evidence, experiment runtime evidence, collection evidence, paper compile evidence, distributed lease/quota/runtime audit, and final submission/anonymity checks remain outside this initial unification pass.

## Handoff Notes

- Agent A did not import unreviewed Agent B changes beyond the stated OpenSolar source snapshot.
- If Agent B later changes shared interface files, import those intentionally after reviewing `docs/integrations/autosci/parity-to-unification-handoff.md`.
- Keep BetterSolar-only integration work on this branch until reviewed.

## Hardening Verification - 2026-07-02

Branch under test: `integration/autosci-unification-hardening`

Verified base HEAD before hardening commit: `aebe4ffeb8aa39f724a92c08d264790636023836`

AutoSci module presence:

- `harness/plugins/autosci/manifest.yaml`: present
- `harness/plugins/autosci/bin/autosci_skill_shim.py`: present
- `harness/plugins/autosci/bin/autosci_bridge.py`: present
- `harness/tools/run_scientific_workflow.py`: present
- `harness/workflows/scientific_research_lifecycle_full_v1.json`: present
- `harness/tests/integration/test_autosci_routes_list.py`: present

Registry/config checks:

- `harness/config/logical-operators.json`: valid JSON
- `harness/config/physical-operators.json`: valid JSON
- `harness/config/capability-capsules.registry.yaml`: valid YAML
- Required logical keys found: `ScientificExperimentRunner`, `ScientificPublicationProducer`
- Required physical keys found: `autosci-experiment-run-worker`, `autosci-publication-compile-worker`
- Required capability keys found: `cap.research-experiment-run`, `cap.research-publication-produce`

Commands tested:

- `bash solar-harness.sh autosci '$skills'`
- `bash solar-harness.sh autosci '$review --help'`
- `bash solar-harness.sh autosci '$ingest --help'`
- `bash solar-harness.sh autosci '$research --help'`
- `bash solar-harness.sh '$review --help'`
- `SOLAR_HOME="$PWD" HARNESS_DIR="$PWD/harness" bin/solar harness autosci '$skills'`
- `SOLAR_HOME="$PWD" HARNESS_DIR="$PWD/harness" bin/solar harness autosci '$review --help'`

Product test result:

- `env PATH="$PWD/bin:$PATH" python3 -m pytest -q tests/integration/test_autosci_routes_list.py tests/integration/test_autosci_cli_dispatch.py tests/integration/test_autosci_ingest_demo.py tests/integration/test_autosci_review_demo.py tests/integration/test_autosci_research_scheduler_demo.py tests/integration/test_autosci_artifact_root.py`
- Result: `6 passed in 5.27s`

Manual isolated smoke result:

- Script: `harness/scripts/autosci-demo-smoke.sh`
- Result: passed
- Smoke root: `/tmp/bettersolar_autosci_smoke_20260702T150947Z`
- `$skills` returned 28 routes.
- `$review --help` reached the AutoSci shim.
- `$ingest` wrote `research_paper.v1` evidence.
- `$research --scheduler-run` wrote `scientific_lifecycle.v1` evidence.
- Outputs remained under the active smoke `HARNESS_DIR`.

Artifact-root behavior:

- Generated smoke artifacts were written under `/tmp/bettersolar_autosci_smoke_20260702T150947Z/artifacts`.
- Tracked generated artifact checks returned empty output for AutoSci run artifacts, operator smoke artifacts, scientific workflow run artifacts, `.DS_Store`, and `.solar-backups`.

Known limitations:

- Integrated Solar now has product-level AutoSci capabilities enabled.
- Full native AutoSci parity continues in parallel and is not complete.
- No route was promoted to `full`.
- Approval-gated side effects remain gated.
- Real online evidence, Review LLM evidence, experiment runtime evidence, collection evidence, paper compile evidence, distributed runtime audit, and submission/anonymity checks remain outside this hardening pass.
