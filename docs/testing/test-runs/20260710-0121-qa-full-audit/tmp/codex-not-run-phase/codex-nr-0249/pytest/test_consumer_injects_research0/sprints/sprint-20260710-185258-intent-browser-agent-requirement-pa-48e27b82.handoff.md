# solar-harness Handoff — 通过 Browser Agent 前门研究后再编译 requirement package。

## Goal

Read compiled PRD / contract / task graph proposal, then produce planner artifacts without skipping governance.

## Read First

- sprint-20260710-185258-intent-browser-agent-requirement-pa-48e27b82.requirement_ir.json
- sprint-20260710-185258-intent-browser-agent-requirement-pa-48e27b82.prd.md
- sprint-20260710-185258-intent-browser-agent-requirement-pa-48e27b82.Contracts.yaml
- sprint-20260710-185258-intent-browser-agent-requirement-pa-48e27b82.task_graph.json
- sprint-20260710-185258-intent-browser-agent-requirement-pa-48e27b82.handoff.md

## Constraints

- IR is source of truth.
- Markdown PRD / contract are compiled views.

## Acceptance

- Planner produces design.md and plan.md.
- Planner may refine task_graph.json but must preserve compiled governance constraints and explicit requirement_ids mapping.
- No direct builder dispatch from raw request.
