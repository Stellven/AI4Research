---
entity_type: "paper"
entity_id: "paper-sample-paper"
title: "AutoSci Adapter Fixture Paper"
run_id: "shim-exp-run-runtime-verified"
source_evidence: "artifacts/autosci/runs/shim-exp-run-runtime-verified/research_paper.json"
managed_by: "solar-autosci-workspace-projector"
---
# AutoSci Adapter Fixture Paper

## Source

- Paper id: `paper-sample-paper`
- Source ref: `plugins/autosci/tests/fixtures/sample_paper.md`
- Source type: `markdown`
- Parse status: `parsed`
- Evidence: `artifacts/autosci/runs/shim-exp-run-runtime-verified/research_paper.json`

## Abstract

This fixture paper exists only to test Solar-native adapter boundaries.

## Sections

### Abstract

Source anchor: `sample_paper.md#abstract`

This fixture paper exists only to test Solar-native adapter boundaries.

### Method

Source anchor: `sample_paper.md#method`

The fixture method runs a deterministic bridge action and records the generated
Solar Evidence ABI artifact.

### Results

Source anchor: `sample_paper.md#results`

The fixture path should produce a `result.json` file and an `evidence.jsonl`
ledger entry without invoking a monolithic AutoSci workflow owner.

