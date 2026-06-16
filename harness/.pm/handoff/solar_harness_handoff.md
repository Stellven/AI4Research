# solar-harness Handoff — kllmk

## Goal

Read compiled PRD / contract / task graph proposal, then produce planner artifacts without skipping governance.

## Read First

- sprint-20260616-194507-intent-kllmk-b01a0a0b.requirement_ir.json
- sprint-20260616-194507-intent-kllmk-b01a0a0b.prd.md
- sprint-20260616-194507-intent-kllmk-b01a0a0b.Contracts.yaml
- sprint-20260616-194507-intent-kllmk-b01a0a0b.task_graph.json
- sprint-20260616-194507-intent-kllmk-b01a0a0b.handoff.md

## Constraints

- IR is source of truth.
- Markdown PRD / contract are compiled views.

## Acceptance

- Planner produces design.md and plan.md.
- Planner may refine task_graph.json but must preserve compiled governance constraints and explicit requirement_ids mapping.
- No direct builder dispatch from raw request.
