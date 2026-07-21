# Epic: Official full-runtime AutoSci integration test

epic_id: `epic-20260710-official-full-runtime-autosci-integration-test`
priority: `P0`
status: `active`
workflow_contract: `research.autosci.v1`

## 目标

Normal intake 命中 AutoSci 研究工作流合同，生成 graph-ready child sprint，
由 graph scheduler 派发 Scientific* DAG nodes。

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

## 子任务图

| Node | Sprint | Slice | Depends |
| --- | --- | --- | --- |
| S01_autosci_workflow | `sprint-20260710-official-full-runtime-autosci-integration-test-s01-autosci-workflow` | AutoSci 合同化研究工作流 | - |
