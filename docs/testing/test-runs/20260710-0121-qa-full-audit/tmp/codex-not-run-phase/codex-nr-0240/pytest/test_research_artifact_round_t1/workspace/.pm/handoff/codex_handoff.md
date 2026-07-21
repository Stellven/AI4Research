# Codex Handoff — pm_dispatch 入口的研究 artifact 必须出现在 compiled package。

## Goal

pm_dispatch 入口的研究 artifact 必须出现在 compiled package。

## Read First

- sprint-20260710-185253-intent-pm_dispatch-artifact-compile-c008fcce.requirement_ir.json
- sprint-20260710-185253-intent-pm_dispatch-artifact-compile-c008fcce.prd.md
- sprint-20260710-185253-intent-pm_dispatch-artifact-compile-c008fcce.Contracts.yaml
- sprint-20260710-185253-intent-pm_dispatch-artifact-compile-c008fcce.task_graph.json

## Constraints

- Treat requirement_ir.json and contracts/*.yaml as canonical sources.
- Use requirement_trace/coverage_report as completion evidence, not intuition.
- Do not bypass planner before builder dispatch.

## Acceptance

- paper/source inventory 完整可追溯。
- claim -> evidence -> implication 映射完整。
- 研究结论具备 adoption/rejection criteria。
