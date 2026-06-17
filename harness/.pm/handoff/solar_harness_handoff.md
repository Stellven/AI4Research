# solar-harness Handoff — Write a research report on WWDC Apple 2026

## Goal

Read compiled PRD / contract / task graph proposal, then produce planner artifacts without skipping governance.

## Read First

- sprint-20260617-170416-intent-write-a-research-report-on-w-ee1ade67.requirement_ir.json
- sprint-20260617-170416-intent-write-a-research-report-on-w-ee1ade67.prd.md
- sprint-20260617-170416-intent-write-a-research-report-on-w-ee1ade67.Contracts.yaml
- sprint-20260617-170416-intent-write-a-research-report-on-w-ee1ade67.task_graph.json
- sprint-20260617-170416-intent-write-a-research-report-on-w-ee1ade67.handoff.md

## Constraints

- IR is source of truth.
- Markdown PRD / contract are compiled views.

## Acceptance

- Planner produces design.md and plan.md.
- Planner may refine task_graph.json but must preserve compiled governance constraints and explicit requirement_ids mapping.
- No direct builder dispatch from raw request.
