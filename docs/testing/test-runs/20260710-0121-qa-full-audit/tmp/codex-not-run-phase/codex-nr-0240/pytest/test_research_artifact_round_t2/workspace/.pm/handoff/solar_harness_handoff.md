# solar-harness Handoff — antigravity 入口的研究 artifact 必须出现在 compiled package。

## Goal

Read compiled PRD / contract / task graph proposal, then produce planner artifacts without skipping governance.

## Read First

- sprint-20260710-185254-intent-antigravity-artifact-compile-0017d47d.requirement_ir.json
- sprint-20260710-185254-intent-antigravity-artifact-compile-0017d47d.prd.md
- sprint-20260710-185254-intent-antigravity-artifact-compile-0017d47d.Contracts.yaml
- sprint-20260710-185254-intent-antigravity-artifact-compile-0017d47d.task_graph.json
- sprint-20260710-185254-intent-antigravity-artifact-compile-0017d47d.handoff.md

## Constraints

- IR is source of truth.
- Markdown PRD / contract are compiled views.

## Acceptance

- Planner produces design.md and plan.md.
- Planner may refine task_graph.json but must preserve compiled governance constraints and explicit requirement_ids mapping.
- No direct builder dispatch from raw request.
