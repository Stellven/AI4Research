# AutoSci Unification Status

Date: 2026-07-02
Agent: Agent A

## Branch And Source Anchors

- BetterSolar branch: `integration/autosci-on-openjiuwen-solar`
- BetterSolar base HEAD: `cdc7e90334437796232e019a0dd689d33e53e7f2`
- OpenSolar source snapshot: `feature/autosci-solar-native` at `9d68c5baa9b814c086ae87f9c26f6ad0ae62ecd7`
- Native AutoSci reference: `main` at `71469e89eb1381e557661da0b90c0585c48288d7`
- OpenSolar and AutoSci were treated as read-only sources.

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
