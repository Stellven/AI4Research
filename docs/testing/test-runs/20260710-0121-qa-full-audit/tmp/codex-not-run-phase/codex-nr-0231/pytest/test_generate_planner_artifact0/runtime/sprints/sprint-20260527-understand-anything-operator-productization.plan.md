# Plan: sprint-20260527-understand-anything-operator-productization

gate: `sprint-20260527-understand-anything-operator-productization:passed`
generated_at: 2026-07-10T18:52:49Z

## DAG Waves

- Wave 1: S1
- Wave 2: S2

## 节点清单

- `S1` depends_on=[] acceptance=['Implementation path explicit.'] outputs=['patch.diff']
- `S2` depends_on=['S1'] acceptance=['Patch produced.'] outputs=['test_report.md']

## 路由约束

- `planning_complete` 前不得路由 builder。
- `task_graph` validate 失败不得推进状态。
- 失败评审默认回退给 planner，重新产出 design/plan，而不是直接返工 builder。

## Stop Rules

- stop_conditions:
- 缺少可验证 acceptance 不得标记为完成。
