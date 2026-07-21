# Codex Handoff — Official full-runtime AutoSci integration test through normal solar intake. Do n

## Goal

Official full-runtime AutoSci integration test through normal solar intake. Do not call a manual autosci shim. The workflow must ingest papers, extract claims, generate ideas, run exp-design, exp-run, exp-eval, and produce a report so we can verify whether AutoSci autonomously participates in the runtime.

## Read First

- sprint-20260710-185231-intent-official-full-runtime-autosc-23cc6196.requirement_ir.json
- sprint-20260710-185231-intent-official-full-runtime-autosc-23cc6196.prd.md
- sprint-20260710-185231-intent-official-full-runtime-autosc-23cc6196.Contracts.yaml
- sprint-20260710-185231-intent-official-full-runtime-autosc-23cc6196.task_graph.json

## Constraints

- Treat requirement_ir.json and contracts/*.yaml as canonical sources.
- Use requirement_trace/coverage_report as completion evidence, not intuition.
- Do not bypass planner before builder dispatch.

## Acceptance

- Normal Solar intake emits a research.autosci.v1 task graph.
- Scientific* nodes resolve to AutoSci research capsules and autosci-* physical operators.
- Autopilot can dispatch ready graph nodes without a manual AutoSci shim call.
