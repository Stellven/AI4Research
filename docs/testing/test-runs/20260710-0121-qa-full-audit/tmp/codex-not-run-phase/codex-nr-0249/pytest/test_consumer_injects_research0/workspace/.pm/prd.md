# 通过 Browser Agent 前门研究后再编译 requirement package。

## 背景 / Context
Compiled from RawIntent into Requirement IR, contract artifacts, and a dispatchable task graph.

## 用户问题 / Problem
通过 Browser Agent 前门研究后再编译 requirement package。

## 用户目标 / Goals
- 通过 Browser Agent 前门研究后再编译 requirement package。

## 用户故事 / User Stories
- As the Solar operator, I need the request structured into PM, Planner, Builder, and Evaluator handoffs so execution stays inside the product workflow.

## 功能需求 / Requirements
- PRD、contract、TaskDAG 互相对齐。
- 实施、验证、兼容/发布路径均已显式表达。
- 每条验收标准都能追溯到验证或 gate。

## 验收标准 / Acceptance Criteria
- PRD、contract、TaskDAG 互相对齐。
- 实施、验证、兼容/发布路径均已显式表达。
- 每条验收标准都能追溯到验证或 gate。

## 非目标 / Non-Goals
- 不在首批交付中做完整四区 PM pane 重构。
- 不绕过 planner 直接进入 builder。

## 约束 / Constraints
- Requirement IR remains the source of truth.
- Builder execution must go through task_graph dispatch.
- Evaluator-visible evidence is required before closeout.

## 风险 / Risks
- [medium] PRD / contract / DAG 多份产物漂移 -> 用 Requirement IR 做唯一事实源，所有视图从 IR 编译。
- [medium] 原始需求直接派给 Builder 导致执行发散 -> 强制走 product-brief / planner handoff，不允许 raw request 直派 builder。
- [medium] 验收标准没有映射到验证步骤 -> 编译期做 acceptance coverage 检查，缺失时阻断派单。

## 开放问题 / Open Questions
- 当前请求缺少显式 success metric，需在 PRD 中补齐。

## 架构交接 / Planner Handoff
Planner must use `requirement_ir.json`, `contract.md`, and `task_graph.json` to verify DAG boundaries, write scopes, gates, and evaluator evidence requirements before builder execution.
