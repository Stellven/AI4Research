# solar-harness Handoff — asdad

## Goal

Read compiled PRD / contract / task graph proposal, then produce planner artifacts without skipping governance.

## Read First

- sprint-20260617-165134-intent-asdad-3abfab76.requirement_ir.json
- sprint-20260617-165134-intent-asdad-3abfab76.prd.md
- sprint-20260617-165134-intent-asdad-3abfab76.Contracts.yaml
- sprint-20260617-165134-intent-asdad-3abfab76.task_graph.json
- sprint-20260617-165134-intent-asdad-3abfab76.handoff.md

## Constraints

- IR is source of truth.
- Markdown PRD / contract are compiled views.

## Acceptance

- Planner produces design.md and plan.md.
- Planner may refine task_graph.json but must preserve compiled governance constraints and explicit requirement_ids mapping.
- No direct builder dispatch from raw request.
