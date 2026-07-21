# Codex Handoff — 新增 intent consumer，把 RawIntent 自动编译成 PM/Planner sprint package。

## Goal

新增 intent consumer，把 RawIntent 自动编译成 PM/Planner sprint package。

## Read First

- sprint-20260710-185257-intent-intent-consumer-rawintent-pm-0e593383.requirement_ir.json
- sprint-20260710-185257-intent-intent-consumer-rawintent-pm-0e593383.prd.md
- sprint-20260710-185257-intent-intent-consumer-rawintent-pm-0e593383.Contracts.yaml
- sprint-20260710-185257-intent-intent-consumer-rawintent-pm-0e593383.task_graph.json

## Constraints

- Treat requirement_ir.json and contracts/*.yaml as canonical sources.
- Use requirement_trace/coverage_report as completion evidence, not intuition.
- Do not bypass planner before builder dispatch.

## Acceptance

- 目标变更在声明范围内完成。
- 至少一条测试/执行证据被记录。
- 存在独立 verifier 决策。
