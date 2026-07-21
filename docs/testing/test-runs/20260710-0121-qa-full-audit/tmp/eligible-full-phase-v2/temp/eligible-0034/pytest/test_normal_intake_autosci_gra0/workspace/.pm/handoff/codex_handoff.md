# Codex Handoff — Official full-runtime AutoSci integration test through normal solar intake. Do n

## Goal

Official full-runtime AutoSci integration test through normal solar intake. Do not call a manual autosci shim. The workflow must ingest papers, extract claims, generate ideas, run exp-design, exp-run, exp-eval, and produce a report.

## Read First

- sprint-20260710-140622-intent-official-full-runtime-autosc-602601d3.requirement_ir.json
- sprint-20260710-140622-intent-official-full-runtime-autosc-602601d3.prd.md
- sprint-20260710-140622-intent-official-full-runtime-autosc-602601d3.Contracts.yaml
- sprint-20260710-140622-intent-official-full-runtime-autosc-602601d3.task_graph.json

## Constraints

- Treat requirement_ir.json and contracts/*.yaml as canonical sources.
- Use requirement_trace/coverage_report as completion evidence, not intuition.
- Do not bypass planner before builder dispatch.

## Acceptance

- Normal Solar intake emits a research.autosci.v1 task graph.
- Scientific* nodes resolve to AutoSci research capsules and autosci-* physical operators.
- Autopilot can dispatch ready graph nodes without a manual AutoSci shim call.
