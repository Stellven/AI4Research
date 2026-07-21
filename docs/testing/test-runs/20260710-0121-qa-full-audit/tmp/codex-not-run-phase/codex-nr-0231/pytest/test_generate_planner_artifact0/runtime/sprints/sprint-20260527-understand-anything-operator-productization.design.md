# Design: Understand Anything Productization

sprint_id: `sprint-20260527-understand-anything-operator-productization`
status: planning_complete
generated_at: 2026-07-10T18:52:49Z
source_of_truth: compiled PRD / contract / task_graph

## 目标

- 将编译型需求推进为可执行 planner contract。

## 设计原则

- Requirement IR / compiled contract 仍是事实源，planner 产物只做执行视图。
- 不绕过 `task_graph.json` 直接派 builder。
- 每条 requirement / acceptance 都必须能映射到节点和验证门。
- capability capsule 与 logical operator 绑定必须保留，不能在 planner 层丢失。

## 执行面分层

- **Planning layer**: `S1` 锁定实现边界与文件范围。
- **Implementation layer**: `S2` 做受约束实现，严格限制在声明写范围。
- **Verification layer**: `S3` 输出测试与证据。
- **Review layer**: `S4` / `S5` 负责 verifier 决策与 rollout note。

## 逻辑算子 / capsule 绑定

- `S1` / `DeepArchitect` / `planning` / `cap.requirement-compiler-planner`: Lock implementation approach.
- `S2` / `ImplementationWorker` / `implementation` / `cap.requirement-compiler-implementation`: Implement.

## 产物边界

### Write Scope
- `harness/**`

### Read Scope
- `requirement_ir.json`

## requirement 映射

- `REQ-001` -> S1, S2

## 风险

- 当前 sprint 先前只有 PRD / contract / task_graph，没有稳定的 planner 视图，容易导致 workflow_guard 与 acceptance closeout 对状态理解不一致。
- review 失败应优先回退到 planner，而不是误派 builder。
- `task_graph` 中的 capability capsule 必须与 runtime operator surface 保持一致，否则后续 builder 会出现旁路执行。

## 成功标志

- success_metrics:
- PRD、contract、TaskDAG 互相对齐。
