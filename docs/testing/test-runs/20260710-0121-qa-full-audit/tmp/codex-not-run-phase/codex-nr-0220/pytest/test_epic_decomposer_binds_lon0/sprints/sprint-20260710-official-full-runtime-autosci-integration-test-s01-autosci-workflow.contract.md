# Contract: AutoSci 合同化研究工作流

priority: `P0`
epic_id: `epic-20260710-official-full-runtime-autosci-integration-test`
sprint_id: `sprint-20260710-official-full-runtime-autosci-integration-test-s01-autosci-workflow`
handoff_to: `planner`

## Intent

通过 normal intake 生成 research.autosci.v1 合同绑定的 Scientific* task graph，并交给 graph scheduler 自动派发 AutoSci workers。

## Required Capabilities

- research.autosci.v1
- scientific-research
- graph-dispatch

## Acceptance

- child sprint 的 task_graph 声明 workflow_contract=research.autosci.v1
- 所有 Scientific* 节点绑定 research capability capsule
- status 进入 planning_complete/builder_main，autopilot 可直接派发 ready graph nodes

## Stop Rules

- 缺 `.task_graph.json` 不得派 builder。
- 缺可复现验证不得标记 passed。
- 发现 scope 冲突必须回写父级 traceability。
