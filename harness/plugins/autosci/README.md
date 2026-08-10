# AutoSci Backend Adapter

This package is a Solar backend implementation package for AutoSci-derived
research actions. It must not own the research workflow.

Solar-native ownership stays in:

- TaskGraph templates
- `Scientific*` logical operators
- `cap.research-*` capability capsules
- Evidence ABI schemas under `schemas/evidence/`
- deterministic evaluator gates

The adapter converts bounded fixture or backend outputs into Solar Evidence ABI
documents and writes them under declared plugin artifact scopes.

## Commands

```bash
bin/python3 plugins/autosci/bin/autosci_bridge.py --help
bin/python3 plugins/autosci/bin/autosci_bridge.py smoke
bin/python3 plugins/autosci/bin/autosci_bridge.py validate --result artifacts/autosci/smoke/result.json
bin/python3 plugins/autosci/bin/autosci_bridge.py run --action prepare_paper_source --envelope plugins/autosci/tests/fixtures/envelope.ingest_paper.json
bin/python3 plugins/autosci/bin/autosci_bridge.py run --action ingest_paper --envelope plugins/autosci/tests/fixtures/envelope.ingest_paper.json
```

Supported fixture-mode actions verified through Phase 16:

- `discover_literature`
- `prepare_paper_source`
- `ingest_paper`
- `analyze_paper`
- `update_memory`
- `update_graph`
- `extract_claims`
- `extract_methods`
- `map_code_evidence`
- `generate_ideas`
- `evaluate_ideas`
- `design_experiment`
- `run_experiment`
- `monitor_experiment`
- `verify_claim`
- `write_report`
- `evolve_workflow`

Phase 9 paper-ingestion smoke writes the canonical foundation artifacts:

```bash
bin/python3 plugins/autosci/bin/autosci_bridge.py run \
  --action ingest_paper \
  --envelope plugins/autosci/tests/fixtures/envelope.ingest_paper.json

bin/python3 evaluators/scientific/paper_gate.py artifacts/scientific/smoke/research_paper.json
bin/python3 evaluators/scientific/memory_update_gate.py artifacts/scientific/smoke/research_memory_update.json
```

PDF and arXiv source preparation is now handled inside the Solar-native
AutoSci backend before `ingest_paper` parses the source. The preparation path
accepts local `.pdf`, local `.tex`, prepared source directories, archives, and
arXiv URLs. For PDFs it extracts text with PyMuPDF, recovers arXiv IDs from the
explicit input, URL/path/filename, PDF text, or title-based Semantic Scholar
lookup, then tries the arXiv `e-print` source endpoint before falling back to a
synthetic `.tex` under `artifacts/autosci/workspace/raw/tmp/papers/`.
Preparation metadata is preserved in `outputs.paper.preparation`, and generated
source/text sidecars are listed as Evidence ABI artifacts. Set
`inputs.allow_network_fetch=false` or `AUTOSCI_DISABLE_NETWORK_FETCH=1` to force
offline synthetic fallback.

The canonical graph update artifact is
`artifacts/scientific/smoke/research_graph_update.json`. It is a
`research_graph_update.v1` Evidence ABI payload whose graph rows live under
`outputs.edges`; it is not a standalone `graph_edges.jsonl` file.

Literature discovery now preserves the native AutoSci `/discover` seed modes
inside the Solar shim:

```bash
bin/python3 plugins/autosci/bin/autosci_skill_shim.py '$discover' --from-wiki --limit 10
bin/python3 plugins/autosci/bin/autosci_skill_shim.py '$discover' --topic "agent skill learning" --limit 10
bin/python3 plugins/autosci/bin/autosci_skill_shim.py '$discover' --anchor 2106.09685 --negative 1810.04805
bin/python3 plugins/autosci/bin/autosci_skill_shim.py '$discover' --venue neurips --year 2024 --limit 10
```

The backend writes `literature_discovery.v1` with `outputs.mode`,
`outputs.limit`, seed metadata, and candidates from live discovery sources.
If Semantic Scholar or Paper Copilot access is unavailable, the evidence is
`inconclusive` with explicit limitations; it does not fall back to local fixture
candidates for real discovery modes.

Phase 10 claim/method/code mapping smoke:

```bash
bin/python3 plugins/autosci/bin/autosci_bridge.py run \
  --action extract_claims \
  --envelope plugins/autosci/tests/fixtures/envelope.extract_claims.json
bin/python3 plugins/autosci/bin/autosci_bridge.py run \
  --action extract_methods \
  --envelope plugins/autosci/tests/fixtures/envelope.extract_methods.json
bin/python3 plugins/autosci/bin/autosci_bridge.py run \
  --action map_code_evidence \
  --envelope plugins/autosci/tests/fixtures/envelope.map_code_evidence.json

bin/python3 evaluators/scientific/claims_gate.py artifacts/scientific/smoke/research_claims.json
bin/python3 evaluators/scientific/method_gate.py artifacts/scientific/smoke/research_method.json
bin/python3 evaluators/scientific/code_evidence_gate.py artifacts/scientific/smoke/code_evidence_map.json
```

Phase 11 idea generation/evaluation smoke:

```bash
bin/python3 plugins/autosci/bin/autosci_bridge.py run \
  --action generate_ideas \
  --envelope plugins/autosci/tests/fixtures/envelope.generate_ideas.json
bin/python3 plugins/autosci/bin/autosci_bridge.py run \
  --action evaluate_ideas \
  --envelope plugins/autosci/tests/fixtures/envelope.evaluate_ideas.json

bin/python3 evaluators/scientific/idea_gate.py artifacts/scientific/smoke/idea_evaluation.json
bin/python3 evaluators/scientific/memory_update_gate.py artifacts/scientific/smoke/research_memory_update.ideas.json
```

Phase 12 experiment lifecycle smoke:

```bash
bin/python3 plugins/autosci/bin/autosci_bridge.py run \
  --action design_experiment \
  --envelope plugins/autosci/tests/fixtures/envelope.design_experiment.json
bin/python3 plugins/autosci/bin/autosci_bridge.py run \
  --action run_experiment \
  --envelope plugins/autosci/tests/fixtures/envelope.run_experiment.fixture.json
bin/python3 plugins/autosci/bin/autosci_bridge.py run \
  --action monitor_experiment \
  --envelope plugins/autosci/tests/fixtures/envelope.monitor_experiment.json

bin/python3 evaluators/scientific/experiment_plan_gate.py artifacts/scientific/smoke/experiment_plan.json
bin/python3 evaluators/scientific/experiment_result_gate.py artifacts/scientific/smoke/experiment_result.json
bin/python3 evaluators/scientific/experiment_status_gate.py artifacts/scientific/smoke/experiment_status.json
```

Phase 13 claim verification smoke:

```bash
bin/python3 plugins/autosci/bin/autosci_bridge.py run \
  --action verify_claim \
  --envelope plugins/autosci/tests/fixtures/envelope.verify_claim.supported.json

bin/python3 evaluators/scientific/claim_verdict_gate.py artifacts/scientific/smoke/claim_verdict.json
```

Phase 13 also keeps outcome-specific fixtures for
`supported`, `partially_supported`, `not_supported`, and `inconclusive`
experiment evidence. `verify_claim` maps those evidence outcomes to
`claim_verdict.v1` without treating an AutoSci/backend self-report as final
acceptance.

Phase 14 report and publication bundle smoke:

```bash
bin/python3 plugins/autosci/bin/autosci_bridge.py run \
  --action write_report \
  --envelope plugins/autosci/tests/fixtures/envelope.write_report.json

bin/python3 evaluators/scientific/report_gate.py artifacts/scientific/smoke/scientific_report.json
bin/python3 evaluators/scientific/publication_gate.py artifacts/scientific/smoke/publication_bundle.json
```

The report smoke writes `scientific_report.v1`, `publication_bundle.v1`,
`report_plan.json`, `report.md`, `report_evidence_index.json`,
`optional_poster.html`, and `optional_rebuttal.md`. The generated publication bundle is local fixture output only and
requires human approval before external handoff.

Phase 16 workflow evolution smoke:

```bash
bin/python3 plugins/autosci/bin/autosci_bridge.py run \
  --action evolve_workflow \
  --envelope plugins/autosci/tests/fixtures/envelope.evolve_workflow.failed_run.json

bin/python3 evaluators/scientific/workflow_evolution_gate.py artifacts/scientific/smoke/workflow_evolution.json
```

The workflow evolution smoke writes `workflow_evolution.v1`,
`recommended_changes.md`, and a review-only `patch_candidates/` directory from
an intentionally failed workflow run. It proposes bounded
manual/schema/gate/workflow changes and keeps every change in
`proposed_only` state until a human accepts or rejects it.

Additional adapter modules are present for method, code evidence, idea, and
experiment status conversion so later phases can bind native nodes without
introducing a monolithic AutoSci runner.
