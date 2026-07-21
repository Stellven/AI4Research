# solar-harness Handoff — codex_bridge 入口的研究 artifact 必须出现在 compiled package。

## Goal

Read compiled PRD / contract / task graph proposal, then produce planner artifacts without skipping governance.

## Read First

- sprint-20260710-185252-intent-codex_bridge-artifact-compil-660277c5.requirement_ir.json
- sprint-20260710-185252-intent-codex_bridge-artifact-compil-660277c5.prd.md
- sprint-20260710-185252-intent-codex_bridge-artifact-compil-660277c5.Contracts.yaml
- sprint-20260710-185252-intent-codex_bridge-artifact-compil-660277c5.task_graph.json
- sprint-20260710-185252-intent-codex_bridge-artifact-compil-660277c5.handoff.md

## Constraints

- IR is source of truth.
- Markdown PRD / contract are compiled views.

## Acceptance

- Planner produces design.md and plan.md.
- Planner may refine task_graph.json but must preserve compiled governance constraints and explicit requirement_ids mapping.
- No direct builder dispatch from raw request.
