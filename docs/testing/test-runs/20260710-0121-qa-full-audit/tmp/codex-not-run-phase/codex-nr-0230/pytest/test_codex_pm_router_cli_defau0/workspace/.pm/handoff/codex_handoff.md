# Codex Handoff — 把 codex_pm_router 入口接到 RawIntent 主链。

## Goal

把 codex_pm_router 入口接到 RawIntent 主链。

## Read First

- sprint-20260710-185248-intent-codex_pm_router-rawintent-247df1a2.requirement_ir.json
- sprint-20260710-185248-intent-codex_pm_router-rawintent-247df1a2.prd.md
- sprint-20260710-185248-intent-codex_pm_router-rawintent-247df1a2.Contracts.yaml
- sprint-20260710-185248-intent-codex_pm_router-rawintent-247df1a2.task_graph.json

## Constraints

- Treat requirement_ir.json and contracts/*.yaml as canonical sources.
- Use requirement_trace/coverage_report as completion evidence, not intuition.
- Do not bypass planner before builder dispatch.

## Acceptance

- 目标变更在声明范围内完成。
- 至少一条测试/执行证据被记录。
- 存在独立 verifier 决策。
