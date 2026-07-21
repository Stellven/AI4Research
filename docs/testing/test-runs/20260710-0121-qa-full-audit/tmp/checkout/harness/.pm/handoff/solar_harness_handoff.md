# solar-harness Handoff — 修复一个按钮文案 typo。

## Goal

Read compiled PRD / contract / task graph proposal, then produce planner artifacts without skipping governance.

## Read First

- sprint-20260710-062937-intent-typo-a0370f32.requirement_ir.json
- sprint-20260710-062937-intent-typo-a0370f32.prd.md
- sprint-20260710-062937-intent-typo-a0370f32.Contracts.yaml
- sprint-20260710-062937-intent-typo-a0370f32.task_graph.json
- sprint-20260710-062937-intent-typo-a0370f32.handoff.md

## Constraints

- IR is source of truth.
- Markdown PRD / contract are compiled views.

## Acceptance

- Planner produces design.md and plan.md.
- Planner may refine task_graph.json but must preserve compiled governance constraints and explicit requirement_ids mapping.
- No direct builder dispatch from raw request.
