# 需求单：APO v2 Lease / Quota / Cost-Aware Agent Plan Optimizer

## 0. 一句话定位

把现有 `apo_plan_compiler.py` 从 `LogicalPlan -> CapsulePlan -> PhysicalPlan` 的静态编译器，升级为可解释、可回放、可受 lease/quota/risk/runtime feedback 约束的 Agent Plan Optimizer。

目标不是再做一个 scheduler，而是让 Solar-harness 能回答：

- 这个用户目标应该被编译成什么 logical DAG？
- 有哪些等价执行计划？
- 当前 operator 池、lease、quota、模型健康、风险约束下，哪个 physical plan 最优？
- 为什么选这个 operator，而不是另一个？
- 执行失败、quota blocked、verifier reject、测试失败后，如何局部重优化？

## 1. 背景与现状

本需求建立在已验收的 `sprint-20260523-agent-plan-optimizer-foundation` 之上。

当前已经存在：

- `harness/lib/apo_plan_compiler.py`
- `build_capsule_plan_ir()`
- `build_physical_plan_for_capsule_node()`
- `compile_execution_plan_for_node()`
- capability capsule / guard / resource / verifier stage
- physical operator registry
- `operator_runtime.acquire_operator_lease()`
- pane lease / operator lease
- quota cooldown / operator flow control
- status-server physical operator observability
- evidence / proof obligations 基础结构

当前缺口：

- physical candidate 排序仍以 registry priority 为主，不是真正 cost/risk/quota-aware。
- APO 输出没有统一 explain plan，无法审查 why selected / why rejected。
- physical plan 没有把 lease requirement、quota health、runtime_state、cooldown_until 纳入候选过滤。
- verifier separation、sandbox/worktree/materialization 等 enforcer 还没有成为 plan-time hard rule。
- runtime failure 之后缺少 Adaptive Replan 记录和局部重优化入口。
- PlanMemo 还没有沉淀历史成功率、耗时、失败类型、operator 表现。

## 2. 目标

### 2.1 P0 目标

实现 APO v2 heuristic optimizer，要求：

1. 基于现有 APO 编译链扩展，不另起第二套 runtime。
2. 物理计划选择必须读取 operator lease / quota / runtime_state。
3. 候选 operator 必须输出 cost breakdown 和 rejected reason。
4. 写代码节点后强制插入或声明 verifier/test obligations。
5. writer 和 verifier 必须分离，至少 operator_id 不同；高风险任务 provider 也应不同。
6. 输出 explain plan artifact，支持 CLI 查看。
7. 支持 runtime feedback record，为后续 adaptive replan 做数据闭环。
8. 所有新逻辑用 deterministic heuristic，不接 learned optimizer。

### 2.2 P1 目标

1. 引入 PlanMemo，保存候选计划、执行结果、历史成功率和失败类型。
2. 实现 `solar-harness apo explain|candidates|why|feedback` CLI。
3. Runtime failure 后能生成 replan suggestion。
4. 在 status page 展示 selected plan、候选 plan、reject reason、lease/quota blockers。

### 2.3 P2 目标

1. Adaptive Replan 自动局部重优化。
2. Learned cost model，仅在累计足够真实样本后启用。
3. 跨 sprint / repo / task type 的 fleet-global PlanMemo。

## 3. 非目标

- 不重写 Requirement Compiler。
- 不替换 `graph_node_dispatcher` / `operatord` / `operator_runtime`。
- 不绕过现有 lease。
- 不把 cost model 外包给 LLM ranking。
- 不在 P0 自动抢占正在运行的 operator。
- 不允许为了低成本跳过 verifier / evidence / security gate。

## 4. 核心概念

### 4.1 Logical Agent Algebra

第一版沿用 APO foundation 的 logical operator 概念，但需要在 schema 中正式支持这些算子：

- `ScanContext`
- `UnderstandGoal`
- `DecomposeTask`
- `DesignSolution`
- `ExploreAlternatives`
- `ImplementPatch`
- `GenerateTests`
- `RunTests`
- `RunBenchmark`
- `DebugRCA`
- `ReviewPatch`
- `VerifyClaim`
- `SynthesizeReport`
- `CompressContext`
- `AskHuman`

要求：

- Logical plan 不允许出现具体 operator_id。
- Logical node 只描述任务语义、输入输出、约束、风险、验收。
- Physical plan 才能绑定 operator、lease、capsule、enforcer。

### 4.2 Physical Operator

Physical operator 包括：

- Claude pane
- Codex pane
- Antigravity managed agent
- local ThunderOMLX / MLX worker
- local shell / benchmark runner
- verifier / reviewer operator

候选 operator 必须携带：

- `operator_id`
- `provider`
- `model`
- `roles`
- `task_classes`
- `capability_fit`
- `runtime_state`
- `lease_status`
- `quota_status`
- `cooldown_until`
- `risk_fit`
- `expected_latency`
- `historical_success`
- `recent_failure_penalty`

### 4.3 Lease

APO 不重新实现 lease，但必须消费并尊重现有 lease。

物理计划中每个 execute stage 必须声明：

```json
{
  "lease_requirement": {
    "required": true,
    "ttl_sec": 2400,
    "renewable": true,
    "preemptible": false,
    "heartbeat_timeout_sec": 90,
    "release_on": ["completed", "failed", "cancelled", "quota_blocked", "crashed"]
  }
}
```

调度前置条件：

- 已有有效 lease 的 operator 不得被选中，除非同一 task/node 正在续租。
- `QUOTA_BLOCKED` / `AUTH_BLOCKED` / `POLICY_BLOCKED` operator 不得进入 selected plan。
- expired lease 应通过现有 cleanup/reap 机制释放后再参与候选。

## 5. 状态机要求

物理 operator 状态应在 APO explain 中统一映射为：

```text
UNREGISTERED
BOOTING
READY
LEASED
RUNNING
FINALIZING
STALE
QUOTA_BLOCKED
AUTH_BLOCKED
POLICY_BLOCKED
HUMAN_REQUIRED
CRASHED
DRAINING
DISABLED
```

兼容要求：

- 现有 idle/running 继续保留为低层 runtime 状态。
- APO explain 使用上述高层状态。
- `READY` 才能进入 selected execute candidate。
- `LEASED/RUNNING` 只能作为 rejected candidate，必须给出 lease_id/task_id/expires_at。

## 6. Cost Model

P0 使用 deterministic weighted score。

```text
score =
    0.28 * capability_fit
  + 0.20 * historical_success
  + 0.14 * quota_health
  + 0.12 * risk_fit
  + 0.10 * latency_fit
  + 0.08 * context_affinity
  + 0.05 * cost_efficiency
  + 0.03 * tool_availability
  - 0.20 * recent_failure_penalty
  - 0.15 * stale_context_penalty
  - 0.25 * verifier_conflict_penalty
```

输出必须包含每个候选的 breakdown：

```json
{
  "operator_id": "op.codex.gpt55.impl.01",
  "score": 0.81,
  "score_breakdown": {
    "capability_fit": 0.92,
    "historical_success": 0.78,
    "quota_health": 0.86,
    "risk_fit": 0.74,
    "latency_fit": 0.68,
    "context_affinity": 0.80,
    "cost_efficiency": 0.71,
    "tool_availability": 1.0,
    "recent_failure_penalty": 0.0,
    "stale_context_penalty": 0.0,
    "verifier_conflict_penalty": 0.0
  },
  "decision": "selected | rejected",
  "rejected_reason": ""
}
```

## 7. Rewrite / Enforcer Rules

P0 必须实现或至少在 plan 中显式 materialize 以下规则：

### 7.1 LocalPreScan

昂贵模型执行前，优先插入本地 scan/compress。

```text
DesignSolution(repo)
=> ScanContext(local) -> CompressContext(local) -> DesignSolution(strong_model)
```

### 7.2 VerifyAfterWrite

任何写代码节点后必须有测试/验证义务。

```text
ImplementPatch
=> ImplementPatch -> RunTests -> ReviewPatch
```

### 7.3 WriterVerifierSeparation

生成 patch 的 operator 不能做最终 verifier。

约束：

- `verifier.operator_id != writer.operator_id`
- high risk 时 `verifier.provider != writer.provider`

### 7.4 QuotaReserve

高级模型 quota 低时，低价值任务不能选用高价值 operator。

### 7.5 Sandbox / Worktree / Secret / Evidence Enforcers

根据 node requirement 自动加入：

- `WorktreeEnforcer`
- `SandboxEnforcer`
- `SecretScrubber`
- `EvidenceMaterializer`
- `VerifierEnforcer`
- `ContextMaterialization`

要求：

- enforcer 是 plan-time hard rule，不是 runtime best-effort。
- high-risk execute stage 缺 verifier/enforcer 时，physical plan 必须 invalid。

## 8. Explain Plan 输出

新增 artifact：

```text
~/.solar/harness/sprints/<sid>.<node_id>-apo-explain.json
~/.solar/harness/sprints/<sid>.<node_id>-apo-explain.md
```

JSON schema 必须包含：

```json
{
  "schema_version": "solar.apo_explain.v2",
  "sprint_id": "string",
  "node_id": "string",
  "mode": "conservative | exploratory | economy",
  "goal": "string",
  "logical_plan": {},
  "capsule_plan": {},
  "physical_plan": {},
  "selected_plan": {
    "operator_id": "string",
    "lease_requirement": {},
    "expected_cost": {},
    "risk_controls": [],
    "enforcers": []
  },
  "candidate_plans": [],
  "rejected_candidates": [
    {
      "operator_id": "string",
      "reason": "quota_blocked | leased | capability_mismatch | verifier_conflict | policy_blocked | disabled | lower_score",
      "details": {}
    }
  ],
  "why_selected": [],
  "why_rejected": [],
  "proof_obligations": [],
  "runtime_feedback_ref": ""
}
```

Markdown explain 必须类似数据库 `EXPLAIN PLAN`：

```text
PLAN selected

Logical:
  ScanContext -> DebugRCA -> ImplementPatch -> RunTests -> ReviewPatch

Physical:
  ScanContext    -> op.local.scan.01
  DebugRCA       -> op.claude.opus.debug.01
  ImplementPatch -> op.codex.gpt55.impl.01
  RunTests       -> op.local.shell.01
  ReviewPatch    -> op.claude.review.01

Why selected:
  - highest quality-adjusted score
  - lease available
  - quota healthy
  - writer/verifier separated

Rejected:
  - op.sonnet.builder.02: leased until ...
  - op.local.thunderomlx.01: capability mismatch for repo_write
```

## 9. CLI / API

新增命令建议：

```bash
solar-harness apo explain <sprint_id> <node_id> [--json]
solar-harness apo candidates <sprint_id> <node_id> [--json]
solar-harness apo why <sprint_id> <node_id>
solar-harness apo feedback <sprint_id> <node_id> --status failed --reason test_failed
```

P0 至少支持：

- `apo explain`
- `apo candidates`

可以先作为 `python3 harness/lib/apo_plan_compiler.py explain ...` 内部入口实现，再接入 `solar-harness`。

## 10. Runtime Feedback

新增 append-only JSONL：

```text
~/.solar/harness/sprints/<sid>.apo-runtime-feedback.jsonl
```

记录：

```json
{
  "ts": "datetime",
  "sprint_id": "string",
  "node_id": "string",
  "plan_id": "string",
  "operator_id": "string",
  "lease_id": "string",
  "event": "started | completed | failed | quota_blocked | verifier_rejected | test_failed | benchmark_regressed | crashed",
  "failure_type": "compile_error | test_failure | design_error | quota | auth | policy | timeout | unknown",
  "artifact_refs": [],
  "suggested_replan": {}
}
```

P0 只要求记录，不要求自动重优化。

## 11. 与现有模块的集成点

必须复用：

- `harness/lib/apo_plan_compiler.py`
- `harness/lib/operator_runtime.py`
- `harness/lib/operator_flow_control.py`
- `harness/config/physical-operators.json`
- `harness/config/concurrency-policy.json`
- `graph_scheduler`
- `graph_node_dispatcher`
- `operatord`
- status-server physical operator summary

禁止：

- 新建第二套 operator registry。
- 新建第二套 lease manager。
- 在 APO 中直接操作 tmux pane。
- 绕过 `operator_runtime.submit_task_to_operator()`。

## 12. 验收标准

### AC1：Lease-aware candidate filtering

构造 3 个 operator：

- A: capability match + READY
- B: capability match + valid lease held by other task
- C: capability match + quota blocked

执行 candidate enumeration：

- A 可 selected。
- B 出现在 rejected，reason=`leased`，包含 `lease_id/expires_at/task_id`。
- C 出现在 rejected，reason=`quota_blocked`，包含 `cooldown_until`。

### AC2：Cost breakdown

每个 candidate 必须有 `score` 和完整 `score_breakdown`。

### AC3：Writer/verifier separation

当 capability stage 和 verifier stage 选择同一 operator 时：

- physical plan invalid 或 verifier candidate 被 reject。
- explain 中出现 `verifier_conflict`。

### AC4：Explain artifact

对任一 graph node 编译后生成：

- `<sid>.<node>-apo-explain.json`
- `<sid>.<node>-apo-explain.md`

JSON 可解析，Markdown 包含：

- Logical Plan
- Physical Plan
- Why selected
- Rejected candidates
- Enforcers

### AC5：Runtime feedback

调用 feedback 入口后：

- append 到 `<sid>.apo-runtime-feedback.jsonl`
- 不覆盖历史
- 含 `plan_id/operator_id/lease_id/event/failure_type`

### AC6：Backward compatibility

现有测试必须继续通过：

```bash
pytest -q harness/tests/test_apo_plan_compiler.py
pytest -q harness/tests/runtime/test_operator_runtime.py
pytest -q harness/tests/test_pm_dispatch.py
```

### AC7：No learned optimizer

P0 不允许引入模型 ranking / learned scoring。所有权重必须在 JSON/config 或 Python 常量中 deterministic 可测试。

### AC8：Shadow mode 主链路有效性验证

APO P0 不能只作为独立 CLI 或旁路报告存在。它必须接入真实主派单链路的 shadow mode：

- `graph_node_dispatcher` / `operatord` 每次真实派单时，保留 baseline 实际选择。
- APO 同步生成 shadow recommendation，但不影响真实派单。
- 记录到 append-only 文件：

```text
~/.solar/harness/run/apo-shadow-decisions.jsonl
```

每条记录必须包含：

```json
{
  "ts": "datetime",
  "sprint_id": "string",
  "node_id": "string",
  "dispatch_id": "string",
  "baseline_operator_id": "string",
  "apo_operator_id": "string",
  "apo_plan_id": "string",
  "decision_diff": "same | different",
  "baseline_reason": "string",
  "apo_why_selected": [],
  "baseline_runtime_state": "string",
  "apo_runtime_state": "string",
  "quota_context": {},
  "lease_context": {},
  "eventual_outcome_ref": ""
}
```

### AC9：Baseline vs APO 效果报告

必须新增日报/CLI 统计，不允许只记录不分析。

输出：

```bash
solar-harness apo effectiveness --since 7d --json
solar-harness apo effectiveness --since 7d
```

最小指标：

- `dispatch_success_rate`
- `task_completion_rate`
- `time_to_first_action`
- `rework_rate`
- `quota_waste_rate`
- `stale_lease_incident_rate`
- `verifier_escape_rate`
- `cost_per_passed_node`
- `stuck_node_rate`
- `human_intervention_count`

报告必须区分：

- baseline 实际选择后的真实 outcome。
- APO shadow recommendation 的反事实判断只能标为 `counterfactual_estimate`，不能伪装成真实收益。
- APO 能真实证明的收益优先来自：避开 blocked/leased/stale operator、插入 verifier/enforcer、减少 quota misdispatch。

### AC10：Promotion gate / Kill switch

APO 不允许一上线就接管派单。必须有三档开关：

```json
{
  "apo_mode": "off | shadow | advisory | gated",
  "promotion_gate": {
    "min_shadow_decisions": 50,
    "min_days": 3,
    "required_improvements": {
      "quota_waste_rate": "-20%",
      "stuck_node_rate": "-15%",
      "verifier_escape_rate": "near_zero"
    }
  },
  "kill_switch": {
    "enabled": true,
    "fallback": "baseline_dispatcher"
  }
}
```

验收要求：

- 默认模式必须是 `shadow` 或 `off`，不能默认 `gated`。
- 未达到 promotion gate，不允许 APO 影响真实 selected operator。
- `SOLAR_APO_MODE=off` 时主链路必须完全回到 baseline dispatcher。
- `SOLAR_APO_MODE=shadow` 时 APO 只记录，不改变派单。
- `SOLAR_APO_MODE=advisory` 时可展示建议，但最终仍由 baseline/人工确认。
- `SOLAR_APO_MODE=gated` 只能在 promotion gate 通过后用于高风险/强模型/拥堵任务。

### AC11：砍掉条件

如果 shadow/advisory 连续 100 个真实 dispatch 后满足任一条件，APO v2 不得进入 gated：

- 无法降低 `quota_waste_rate` 或 `stuck_node_rate`。
- APO recommendation 与 baseline 差异小于 5%，说明没有决策增量。
- APO 增加平均 dispatch latency 超过 1 秒且没有对应质量收益。
- explain artifact 生成失败率超过 2%。
- evaluator 认定 explain 无法支持 why selected / why rejected。

## 13. 推荐实施切片

### S00：Shadow effectiveness harness

- 在主派单路径记录 baseline vs APO shadow decision。
- 新增 `apo-shadow-decisions.jsonl`。
- 新增 `apo effectiveness` 汇总 CLI。
- 默认不影响真实派单。

### S01：APO cost/risk/quota schema

- 定义 `solar.apo_explain.v2`
- 定义 candidate score schema
- 定义 runtime feedback schema
- 定义 `solar.apo_shadow_decision.v1`
- 定义 `solar.apo_effectiveness_report.v1`
- 单元测试 schema required fields

### S02：Lease-aware physical candidate enumeration

- 扩展 `enumerate_physical_candidates()`
- 接入 `operator_runtime.get_operator_lease()`
- 接入 `operator_flow_control.get_operator_status_data()`
- 输出 selected / rejected candidates

### S03：Explain artifacts + CLI

- materialize explain JSON/MD
- 新增 `apo explain/candidates`
- status-server 可选展示

### S04：Verifier / Enforcer hard rules

- writer/verifier separation
- high-risk verifier required
- Worktree/Evidence/Secret enforcer materialization

### S05：Runtime feedback + replan suggestion

- feedback JSONL
- failure classification
- suggested_replan 只输出建议，不自动执行

### S06：Promotion gate + kill switch

- 增加 `apo_mode = off | shadow | advisory | gated` 统一配置。
- 实现 promotion gate 检查。
- 实现 kill switch 回退 baseline dispatcher。
- 未通过 effectiveness gate 时禁止 gated takeover。

## 14. 优先级

Priority: `P0`

Lane: `optimizer-plane`

建议派给：

- Planner/Architect：先锁 schema、状态机、兼容边界。
- Builder：实现 `apo_plan_compiler.py` 和 CLI。
- Evaluator：重点打 lease/quota/verifier conflict 负控。

## 15. 最终判断

这张单的本质是：把 Solar-harness 从“能派发 DAG 节点”升级到“能解释为什么这样派发，以及当前资源/风险下这是不是最佳计划”。

P0 成功标准不是智能程度，也不是 explain 漂亮程度，而是：

- 可解释
- 可测试
- 尊重 lease/quota
- 不跳过 verifier/enforcer
- 能沉淀 runtime feedback
- 能在 shadow mode 中证明减少 stuck/quota waste/verifier escape，或明确被 kill gate 阻止进入 gated
