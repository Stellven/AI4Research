---
entity_type: "paper"
entity_id: "paper-skillgen-operator-smoke-paper"
title: "SKILLGEN: Verified Inference-Time Agent Skill Synthesis"
run_id: "shim-single-token-dollar-command"
source_evidence: "artifacts/autosci/runs/shim-single-token-dollar-command/research_paper.json"
managed_by: "solar-autosci-workspace-projector"
---
# SKILLGEN: Verified Inference-Time Agent Skill Synthesis

## Source

- Paper id: `paper-skillgen-operator-smoke-paper`
- Source ref: `plugins/autosci/tests/fixtures/skillgen_operator_smoke_paper.md`
- Source type: `markdown`
- Parse status: `parsed`
- Evidence: `artifacts/autosci/runs/shim-single-token-dollar-command/research_paper.json`

## Abstract

The paper introduces SKILLGEN, a multi-agent inference-time framework for synthesizing reusable, auditable agent skills from successful and failed trajectories. It emphasizes contrastive induction, candidate verification, and empirical net-effect checks before deployment.

## Sections

### Abstract

Source anchor: `skillgen_operator_smoke_paper.md#abstract`

The paper introduces SKILLGEN, a multi-agent inference-time framework for synthesizing reusable, auditable agent skills from successful and failed trajectories. It emphasizes contrastive induction, candidate verification, and empirical net-effect checks before deployment.

### Method

Source anchor: `skillgen_operator_smoke_paper.md#method`

The workflow derives candidate skill procedures from trajectory data, compares success patterns and failure modes, and verifies whether the generated skill improves the base agent without introducing unacceptable regressions.

### Evidence Notes

Source anchor: `skillgen_operator_smoke_paper.md#evidence-notes`

This compact markdown fixture is derived from the SkillGen paper for Solar-native AutoSci operator smoke testing.

