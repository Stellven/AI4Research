# PM -> Planner -> Headless Pool DAG Flow Final Contract Summary

更新日期: 2026-05-23

## 目的

这份文档是当前 `solar-harness` 已生效规则的稳定入口。

它压缩并收敛了以下三张已经完成的 sprint：

- `sprint-20260523-pane-as-physical-operator-architecture`
- `sprint-20260523-physical-operator-taxonomy-truthification`
- `sprint-20260523-operator-class-compatibility-cutover`

目标不是复述全过程，而是只保留现在应该被视为正式真值的控制面、调度面和执行面契约。

## Canonical Flow

```text
PM
  -> 写 PRD / contract / PM order
  -> 正式派给 solar-harness
  -> Planner 物化 design / plan / task_graph
  -> graph dispatcher 从 headless operator pool 派发 ready nodes
  -> builder / verifier / evaluator 完成节点闭环
  -> sprint passed / finalized / done
```

## 1. 派单契约

### 1.1 PM 默认派单目标

- PM 默认正式派单目标是 `solar-harness`。
- PM 不直接挑具体 headless pane 做正式 sprint 派发。
- adhoc probe 可以存在，但不属于正式 sprint 主路径。

### 1.2 Planner 真值

- `design.md`
- `plan.md`
- `task_graph.json`

以上三者由 Planner 正式物化并作为执行前置真值。

没有 planner artifacts 时，builder / evaluator 不应进入正式执行。

## 2. DAG 契约

### 2.1 DAG 写逻辑需求，不写死模型

节点应优先表达：

- `task_type`
- `required_capabilities`
- `required_skills`
- `constraints`
- `preferred_operator_classes`
- `verifier_required`

长期真值不应依赖写死的 `provider/model` 字符串。

### 2.2 Scheduler 解析顺序

```text
task intent
  -> operator class
  -> capability / skill fit
  -> runtime / lease / quota / policy
  -> concrete operator_id
```

模型或 provider 调整，应该优先通过 registry/runtime 变更完成，而不是重写 DAG。

## 3. Physical Operator 契约

### 3.1 调度单位

- 调度单位是 `physical operator`
- tmux pane 是 operator 的物理宿主，不是最终调度真值

### 3.2 operator 含义

一个 physical operator 应被理解为：

- pane / physical host
- provider binding
- model binding
- auth / access binding
- quota clock
- capability profile
- runtime state
- permission policy
- evidence / logs

### 3.3 No Drift Rule

正式链路不允许在任务执行中偷偷切模型、改登录态或变更关键绑定。

如果需要切换绑定，应通过：

- 新 operator
- registry 更新
- operator 重启 / rebind

而不是通过任务内部隐式漂移完成。

## 4. Runtime 与 `operatord`

正式目标架构是：

```text
operatord run <operator_id>
```

`operatord` 负责：

1. 读取 registry
2. 解析 `secret_ref`
3. 注入环境变量
4. 启动底层 CLI / SDK / local runtime
5. 打心跳
6. 接收 Task Envelope
7. 写 execution log
8. 抓 stdout/stderr
9. 识别 quota/auth/error
10. 上报 task result

## 5. Task Envelope / Result 契约

正式 operator 输入应是结构化 envelope，而不是自由文本直接塞 pane。

最小有效字段包括：

- `task_id`
- `task_type`
- repo / worktree
- objective
- constraints
- inputs / artifacts
- output_contract
- verifier requirements

结果面应至少有：

- task/operator identity
- status
- artifacts
- metrics
- warnings / failures

## 6. Taxonomy 契约

当前 taxonomy 主轴按执行角色而不是 provider/vendor 来定义。

代表性分类包括：

- Deep Architect
- Root-Cause Debug
- Implementation
- Fast Subagent
- Parallel Exploration
- Verifier
- Research Synthesis
- Browser / Computer-use
- Google-stack
- Local Privacy

## 7. Compatibility Cutover 契约

legacy role 桶与 canonical operator class 需要平滑共存。

系统应支持：

- canonical mapping
- legacy alias
- dual visibility
- staged cutover

并保证：

- 不强制重启全部 pane
- 不打断 `LEASED / RUNNING / DRAINING`
- 不破坏正在运行的旧链路

## 8. Scheduler 契约

调度不应只看“哪个模型最强”，而应综合：

- capability fit
- quality / success history
- quota
- latency
- cost tier
- availability / lease
- context affinity
- risk / policy match
- recent error penalty
- verifier conflict penalty

另外，runtime 已兼容 dotted skill 与 coarse worker skill 的匹配，避免假性 `no_matching_worker`。

## 9. 生命周期契约

Canonical lifecycle：

```text
CREATED -> WARMING -> IDLE -> LEASED -> RUNNING -> DRAINING -> IDLE
```

异常状态包括：

- `ERROR`
- `QUOTA_EXHAUSTED`
- `AUTH_EXPIRED`
- `COOLDOWN`
- `DISABLED`
- `STALE_CONTEXT`
- `NEEDS_HUMAN_REVIEW`

调度必须尊重 runtime state 与 lease 安全。

## 10. Review / Evaluator 契约

- writer 与 verifier 必须分离
- review 是 graph verdict 变更的一部分，不能随意越权
- evaluator 扩容不能靠“多开几个 pane”粗暴处理
- 更合理的下一阶段是 `evaluation_plan / evaluator capacity planning`

## 11. 可观测性契约

主状态面是：

- `http://127.0.0.1:8765/`

当前已纳入主状态页的关键视图：

- PM Dispatch
- Physical Operators
- operator alerts / recent results
- sprint phase / node progress

## 12. 禁止行为

当前正式契约明确拒绝：

- PM 默认直派 headless worker
- 没有 planner artifacts 就进入 builder
- DAG 长期写死 provider/model
- 正式任务中的隐式模型漂移
- 绕过 verifier / evaluator gate
- cutover 时破坏 in-flight leased work

## 13. 当前正式角色分工

```text
PM = formal demand + dispatch entry
Planner = architecture + plan + DAG truth owner
solar-harness = sole formal dispatcher
headless panes = operator physical hosts
DAG = logical execution graph
registry/runtime = operator binding truth
8765 = main observability surface
```

## Source Of Truth

如果需要完整细节或中间设计演进，请回看：

- `~/.solar/harness/sprints/sprint-20260523-pane-as-physical-operator-architecture.*`
- `~/.solar/harness/sprints/sprint-20260523-physical-operator-taxonomy-truthification.*`
- `~/.solar/harness/sprints/sprint-20260523-operator-class-compatibility-cutover.*`

运行时压缩版摘要工件：

- `~/.solar/harness/sprints/sprint-20260523-pane-as-physical-operator-final-contract-summary.md`
