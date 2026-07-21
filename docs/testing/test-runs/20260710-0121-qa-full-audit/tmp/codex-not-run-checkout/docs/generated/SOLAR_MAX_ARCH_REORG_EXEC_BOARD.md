# Solar-MAX Architecture Reorg Execution Board

Last updated: 2026-03-07

## Scope

以“开发 / 研究 / 办公”三大核心能力为目标，执行一次可回滚、可验收的架构重整。

## Phase A - Baseline (Done)

- [x] 生成系统基线：`docs/generated/solar-max-arch-reorg-baseline.json`
- [x] 生成人类可读报告：`docs/generated/solar-max-arch-reorg-baseline.md`
- [x] 输出 agent 优化矩阵：`docs/generated/SOLAR_MAX_AGENT_OPTIMIZATION_MATRIX.md`

验收命令：

```bash
bun run scripts/architecture-reorg-baseline.ts
```

## Phase B - Structure Unification

- [x] 新建 `core/orchestrator/agent-catalog.ts` 作为 agent 单一事实源
- [x] 定义统一 `AgentSpec`（phase/council/persona/modelPolicy/capabilities）
- [x] 将 phase 默认角色从 SQL seed 转为 catalog + 同步器（`bun run sync:phase-agents`）
- [x] 建立 `phase-role-mapping`（phase 与 council 双向映射，`bun run check:phase-role-mapping`）
- [x] 输出变更报告：catalog 与 DB 差异（`bun run check:agent-catalog`）

验收标准：

- catalog 可生成当前 13 个 agent，不丢失 metadata
- phase/council 映射可从同一源导出

## Phase C - Debate + Synthesis Kernel

- [x] 实装标准辩论协议（开场/反驳/交叉质询/裁决）
- [x] 每阶段支持 GPT-5 参赛或裁判两种模式（phaseProfiles + intentPhaseMap 驱动）
- [x] 集成 challenger 模型（Gemini/GLM/DeepSeek）到统一接口（execution hint + challenger lane）
- [x] secretary 升级为结构化综合器（objective/assumptions/evidence/risks/decision/artifacts）
- [x] policy 配置化辩论轮次、参与角色、停机条件（core-policy debate 配置扩展）

验收标准：

- 同任务可产出双模型观点 + 裁决理由
- 所有结论带 evidence/risk/decision 字段

## Phase D - Capability Pipelines

- [x] 开发流水线：plan->code->test->review->release 门禁打通（pipeline gate）
- [x] 研究流水线：question->hypothesis->evidence->synthesis->prototype 门禁打通（pipeline gate）
- [x] 办公流水线：brief->outline->artifact(word/ppt)->quality check 门禁打通（pipeline gate）
- [x] 三条流水线统一 artifact contract（`core/orchestrator/artifact-contract.ts`）

验收标准：

- 三条流水线均可独立 smoke（`smoke:pipeline:dev|research|office`）
- 失败可重试，结果可追踪

## Phase E - Evals & Regression

- [x] 建立核心 eval 套件（开发/研究/办公各 >= 10 用例，当前各 10）
- [x] 指标落库：success/retry/cost/cycle/debate-yield（`bl_orchestrator_eval_runs`）
- [x] 生成每次重整前后对比报告（`docs/generated/solar-max-eval-report.md`）
- [x] 接入 smoke/eval 命令到 `package.json`

验收标准：

- 至少一版 “重整前 vs 重整后” 指标对比
- 核心能力无明显回退

## Risks & Controls

| Risk | Impact | Control |
|---|---|---|
| 角色定义重复导致行为漂移 | 高 | 强制 catalog 作为唯一入口 |
| 多模型接入后成本暴涨 | 高 | rolePolicy + budget gate + max rounds |
| 研究结论不可追溯 | 中 | evidence schema 强校验 |
| 办公产物风格不一致 | 中 | secretary 统一模板与质检 |

## Rollback

- 版本策略：每个 phase 完成后打小版本 tag（如 `v3.1.x-phaseB`）
- 回滚策略：代码 tag 回滚 + policy 快照回放

## Next Action

执行下一项：把阶段性成果固化为一次小版本 tag，并准备回滚说明。

## Progress Notes

- 2026-03-07: 成本维度已从固定估算切到“执行链按模型 token 动态计费”（读取 DB 定价表并注入 orchestrator）。
- 2026-03-07: `smoke:core-policy` 已做服务自恢复（自动执行 `ensure-background-services` + API 就绪等待），`eval:orchestrator` 回归通过 `7/7`，避免端口未就绪导致假失败。
