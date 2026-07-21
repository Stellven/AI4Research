# Codex Handoff — codex_bridge 入口的研究 artifact 必须出现在 compiled package。

## Goal

codex_bridge 入口的研究 artifact 必须出现在 compiled package。

## Read First

- sprint-20260710-185252-intent-codex_bridge-artifact-compil-660277c5.requirement_ir.json
- sprint-20260710-185252-intent-codex_bridge-artifact-compil-660277c5.prd.md
- sprint-20260710-185252-intent-codex_bridge-artifact-compil-660277c5.Contracts.yaml
- sprint-20260710-185252-intent-codex_bridge-artifact-compil-660277c5.task_graph.json

## Constraints

- Treat requirement_ir.json and contracts/*.yaml as canonical sources.
- Use requirement_trace/coverage_report as completion evidence, not intuition.
- Do not bypass planner before builder dispatch.

## Acceptance

- paper/source inventory 完整可追溯。
- claim -> evidence -> implication 映射完整。
- 研究结论具备 adoption/rejection criteria。
