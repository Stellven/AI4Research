# PRD: AutoSci 合同化研究工作流

epic_id: `epic-20260710-official-full-runtime-autosci-integration-test`
sprint_id: `sprint-20260710-official-full-runtime-autosci-integration-test-s01-autosci-workflow`
slice: `autosci-workflow`

## 用户原始需求

Official full-runtime AutoSci integration test through normal solar intake. Do not call a manual autosci shim. The workflow must ingest papers, extract claims, generate ideas, run exp-design, exp-run, exp-eval, and produce a report so we can verify whether AutoSci autonomously participates in the runtime.
- requirement 0: keep AutoSci autonomous and evidence-backed.
- requirement 1: keep AutoSci autonomous and evidence-backed.
- requirement 2: keep AutoSci autonomous and evidence-backed.
- requirement 3: keep AutoSci autonomous and evidence-backed.
- requirement 4: keep AutoSci autonomous and evidence-backed.
- requirement 5: keep AutoSci autonomous and evidence-backed.
- requirement 6: keep AutoSci autonomous and evidence-backed.
- requirement 7: keep AutoSci autonomous and evidence-backed.

## 本切片目标

通过 normal intake 生成 research.autosci.v1 合同绑定的 Scientific* task graph，并交给 graph scheduler 自动派发 AutoSci workers。

## 范围

- 只交付本切片，不允许声称父 Epic 已完成。
- 必须读取 `epic-20260710-official-full-runtime-autosci-integration-test.epic.md`、`epic-20260710-official-full-runtime-autosci-integration-test.traceability.json` 和父级 task_graph。
- 必须在 handoff 中写明上游依赖、下游影响和未闭环项。

## 验收标准

- child sprint 的 task_graph 声明 workflow_contract=research.autosci.v1
- 所有 Scientific* 节点绑定 research capability capsule
- status 进入 planning_complete/builder_main，autopilot 可直接派发 ready graph nodes

## 非目标

- 不直接绕过 planner 派 builder。
- 不用单个大 PRD 覆盖所有实现细节。
- 不用“已完成”替代可复现证据。

## 交付物

- `sprint-20260710-official-full-runtime-autosci-integration-test-s01-autosci-workflow.design.md`
- `sprint-20260710-official-full-runtime-autosci-integration-test-s01-autosci-workflow.plan.md`
- `sprint-20260710-official-full-runtime-autosci-integration-test-s01-autosci-workflow.task_graph.json`
- `sprint-20260710-official-full-runtime-autosci-integration-test-s01-autosci-workflow.handoff.md`
- `sprint-20260710-official-full-runtime-autosci-integration-test-s01-autosci-workflow.eval.md` 或 `sprint-20260710-official-full-runtime-autosci-integration-test-s01-autosci-workflow.eval.json`
