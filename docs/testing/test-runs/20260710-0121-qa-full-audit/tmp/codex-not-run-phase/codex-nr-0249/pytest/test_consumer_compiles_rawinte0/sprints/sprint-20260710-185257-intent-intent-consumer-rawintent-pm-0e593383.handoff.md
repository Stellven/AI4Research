# solar-harness Handoff — 新增 intent consumer，把 RawIntent 自动编译成 PM/Planner sprint package。

## Goal

Read compiled PRD / contract / task graph proposal, then produce planner artifacts without skipping governance.

## Read First

- sprint-20260710-185257-intent-intent-consumer-rawintent-pm-0e593383.requirement_ir.json
- sprint-20260710-185257-intent-intent-consumer-rawintent-pm-0e593383.prd.md
- sprint-20260710-185257-intent-intent-consumer-rawintent-pm-0e593383.Contracts.yaml
- sprint-20260710-185257-intent-intent-consumer-rawintent-pm-0e593383.task_graph.json
- sprint-20260710-185257-intent-intent-consumer-rawintent-pm-0e593383.handoff.md

## Constraints

- IR is source of truth.
- Markdown PRD / contract are compiled views.

## Acceptance

- Planner produces design.md and plan.md.
- Planner may refine task_graph.json but must preserve compiled governance constraints and explicit requirement_ids mapping.
- No direct builder dispatch from raw request.
