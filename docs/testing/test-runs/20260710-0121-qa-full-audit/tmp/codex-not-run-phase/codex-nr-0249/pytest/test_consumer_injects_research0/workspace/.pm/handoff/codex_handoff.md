# Codex Handoff — 通过 Browser Agent 前门研究后再编译 requirement package。

## Goal

通过 Browser Agent 前门研究后再编译 requirement package。

## Read First

- sprint-20260710-185258-intent-browser-agent-requirement-pa-48e27b82.requirement_ir.json
- sprint-20260710-185258-intent-browser-agent-requirement-pa-48e27b82.prd.md
- sprint-20260710-185258-intent-browser-agent-requirement-pa-48e27b82.Contracts.yaml
- sprint-20260710-185258-intent-browser-agent-requirement-pa-48e27b82.task_graph.json

## Constraints

- Treat requirement_ir.json and contracts/*.yaml as canonical sources.
- Use requirement_trace/coverage_report as completion evidence, not intuition.
- Do not bypass planner before builder dispatch.

## Acceptance

- PRD、contract、TaskDAG 互相对齐。
- 实施、验证、兼容/发布路径均已显式表达。
- 每条验收标准都能追溯到验证或 gate。
