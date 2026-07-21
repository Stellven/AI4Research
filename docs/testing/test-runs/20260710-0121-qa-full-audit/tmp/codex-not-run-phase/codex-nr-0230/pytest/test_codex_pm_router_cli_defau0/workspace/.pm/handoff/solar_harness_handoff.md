# solar-harness Handoff — 把 codex_pm_router 入口接到 RawIntent 主链。

## Goal

Read compiled PRD / contract / task graph proposal, then produce planner artifacts without skipping governance.

## Read First

- sprint-20260710-185248-intent-codex_pm_router-rawintent-247df1a2.requirement_ir.json
- sprint-20260710-185248-intent-codex_pm_router-rawintent-247df1a2.prd.md
- sprint-20260710-185248-intent-codex_pm_router-rawintent-247df1a2.Contracts.yaml
- sprint-20260710-185248-intent-codex_pm_router-rawintent-247df1a2.task_graph.json
- sprint-20260710-185248-intent-codex_pm_router-rawintent-247df1a2.handoff.md

## Constraints

- IR is source of truth.
- Markdown PRD / contract are compiled views.

## Acceptance

- Planner produces design.md and plan.md.
- Planner may refine task_graph.json but must preserve compiled governance constraints and explicit requirement_ids mapping.
- No direct builder dispatch from raw request.
