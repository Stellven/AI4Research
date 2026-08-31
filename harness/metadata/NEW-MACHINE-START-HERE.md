# 新机器接手入口：OpenSolar / AI4Research

核对日期：2026-08-31。最后产品代码：`f463b861bf47bddff46cc2ce3de151dcd8d78992`。
先读 [最后一次 E2E 与迁移状态](migration-handoff-20260831.md)。最后测试在 Planner
模型输出 schema 准入失败，未到 Scheduler；用户要求停止修复并迁移，不能宣称全流程通过。
本说明由当前生产源码与已记录运行证据整理，不将设计示例当作已实现功能。
所有下文代码路径均相对**源码仓库根目录**；安装后 `harness/` 对应已批准的 runtime。

## 1. 项目目的与边界

OpenSolar（界面名称 AI4Research）是本地优先的多智能体任务执行框架。
它把用户目标变成可验证的需求和执行计划，在模型、CLI 和科研算子上运行，
通过结构化 artifact、引用哈希、评估和执行账本交付结果。
软件任务与科研任务共用控制平面；科研任务可以组合检索、论文摄取、方法提取、
论断评估、报告规划与报告撰写，而不是只生成一次聊天回答。

目标设计是：**LLM 解释语义，确定性代码校验结构、维护引用、冻结合同和调度。**
Intent Compiler、默认 Requirement Compiler 和 Elastic Planner 均为 LLM-based。
2026-08-30 的后续修复新增结构化检索合同，离线验证与在线验收状态以问题日志为准。
Requirement 的旧确定性编译器仅供显式 legacy 调用，不是默认 intake 的回退路径。
项目是受控试用系统，不是多租户云服务，也没有通过所有平台/工具的完整验收。

旧机器的唯一 runtime 和 backend 在
[migration-handoff-20260830.md](migration-handoff-20260830.md) 中记录。
新机器必须先由用户确认路径、数据目录、地址和端口，不能把旧 IP 当默认值。
源码迁移不包含模型登录、API 凭据、旧 session 或本地虚拟环境。

## 2. 当前真实 pipeline

`GUI/CLI → Intent Compiler → Requirement Compiler → Elastic Planner
→ 冻结 SchedulerInput → Scheduler → Dispatcher → Operators/Gates → 最终交付`

这是默认 formal intake 路径，不是根 README 中历史 PRD/Contracts/task_graph 路径。
复杂查询不能仅凭 epic 标签绕过前面的编译链。
`SOLAR_INTAKE_COMPAT_MODE=legacy` 仍保留兼容路径；迁移验收不要启用它。

| 步骤 | 职责与实际入口 | 主要输入 → 输出 |
| --- | --- | --- |
| GUI / CLI intake | `harness/lib/symphony/status-server.py`；`harness/solar-harness.sh` | 用户请求、附件引用 → intent request；返回 session/intake 状态 |
| Intent Compiler | `harness/lib/intent_gateway.py` → `intent_compiler.run_pipeline` | 标准化 input → IntentIR、validation、独立 fidelity、acceptance；失败/澄清时禁止继续 |
| Requirement Compiler | `harness/lib/requirement_compiler/semantic.py`，`evaluator.py` | 已接受 IntentIR → 共享合同 v2 的 LLM values + 独立语义审查；结构与语义各一次修复，最多五次调用且总时限有界 |
| Planner 入口 | `harness/lib/intent_consumer.py` → `harness/tools/elastic_planner_adapter.py` | 已接受 RequirementIR → semantic/execution bundle；adapter 本身不写生命周期状态 |
| Elastic Planner | `harness/lib/elastic_planner.py::run_elastic_planning_request` | LLM decision、PlanIR、fidelity 与绑定审查；确定性 validation/acceptance；最多限定次数修复 |
| 执行合同编译 | `elastic_planner.compile_and_freeze_execution_bundle` | accepted semantic plan → capsule/physical/evaluation plans、SchedulerInput、frozen run contract |
| Scheduler | `harness/lib/scheduler_input.py`、`multi_task_runner.py`、`graph_scheduler.py` | 验证冻结 bundle → runtime graph projection + 独立可变 task_graph_state；按依赖持续调度 |
| Dispatcher | `harness/lib/graph_node_dispatcher.py`、`operator_runtime.py` | ready node + 合同/租约 → operator request、提交/接受/结果证据；提交回执不等于执行成功 |
| Operators 与 gates | `harness/plugins/autosci/`、`harness/evaluators/scientific/` | 已声明 artifact routes → 领域 evidence；按绑定 evaluator/test_policy 产生判定 |
| 交付 | 所选 report-plan/report-draft 算子 + Scheduler/Coordinator 收尾 | 科研 evidence → report plan → structured report + report.md；必须检查主题相关性、证据与标题 |

当前 Elastic Planner **内部**完成冻结编译；不要再顺手调用
`static_execution_compiler.compile_bundle` 进行第二次权威编译。
旧的自由文本 Graph Compiler / PRD 路径不能作为 formal 路径的成功证据。

简单查询也应经过 Intent、Requirement、Planner。Planner 可以选择 direct_response，
这时不启动 Scheduler/worker；不要为了简单回答人为构造多节点 DAG。
编译阶段的语义审查与运行节点的 bundled evaluator 是不同边界。

Rapid smoke 通过可信环境 `SOLAR_TEST_MODE=rapid_smoke` 注入冻结 test_policy，
不是通过用户 prompt 或 operator 输出里的关键词来授权跳过校验。
它减少执行语义评估成本，不能用来证明科学质量；已有一次 rapid receipt PASS
没有阻止空 discovery 交接，因此也不能只看 receipt 就宣称所有硬门禁执行成功。

## 3. 每一步合同 / schema 的准确地址

可执行 JSON Schema 目录：
[Intent](../schemas/compiler/)、
[Planner/Scheduler](../schemas/planning/)、
[Scientific Evidence ABI](../schemas/evidence/)。
完整 schema 文件哈希清单见
[migration-closure-20260830.json](migration-closure-20260830.json)。

**并非每一步都有独立 JSON Schema。** 下表明确区分 JSON Schema、模板和代码校验；
不要把名称相似的旧 schema 错当成当前 v2 的合同。

| 边界 / artifact | 权威文件或校验位置（仓库相对路径） | 类型与限制 |
| --- | --- | --- |
| 原始请求 / input.json | `harness/lib/intent_compiler.py::normalize_input`；`harness/metadata/1-input normalizer output/` | 代码规范化 + 设计示例；不是独立 JSON Schema |
| intent_ir.json | `harness/schemas/compiler/intent-ir.v3.schema.json`；模型 body 为 `intent-ir.semantic.v1.schema.json` | JSON Schema + 来源/引用校验 |
| Intent validation/fidelity/acceptance | 同目录 `intent-validation.v1.schema.json`、`intent-fidelity.review.v1.schema.json`、`intent-fidelity.v1.schema.json`、`intent-acceptance.v1.schema.json` | 独立结构、语义和准入合同 |
| requirement_ir.json v2 | `harness/metadata/3-requirements compiler output/requirement_ir/requirement_ir.json`；`harness/schemas/compiler/requirement-semantics.v2.schema.json`；`evaluator.py` | 原 envelope 模板 + semantic_contract；模型 values 新增 selection_authority；原约束 AST 精确保留 |
| 共享模板 / Requirement review | `harness/schemas/compiler/requirement-semantic-contract.v2.json`、`harness/schemas/compiler/requirement-semantic-review.v2.schema.json` | registry/Intent ID 固化为实际调用 schema 枚举；结构化 rule/field/evidence/reason；只读 runtime policy 单独保留。v1 历史合同不覆盖 |
| 检索合同 | `harness/schemas/compiler/retrieval-contract.v1.schema.json` | Planner 用 retrieval_contract_ref 引用；Scheduler 冻结合同；Discovery 不从 objective 猜主题 |
| requirement_format_evaluation.json | `harness/lib/requirement_compiler/evaluator.py` | 代码定义输出；metadata 的 requirement_validation/coverage 不能视为当前全部已执行 |
| planning_context / catalog / decision | `harness/schemas/planning/planning-context.v1.schema.json`、`planning-catalog-snapshot.v1.schema.json`、`planning-decision.v1.schema.json` | 决策模型 body 用 `planning-decision.semantic.v1.schema.json` |
| plan_ir / validation / fidelity / binding / acceptance | 同目录 `plan-ir.v2.schema.json`、`plan-validation.v2.schema.json`、`plan-fidelity.v1.schema.json`、`binding-trace.v2.schema.json`、`plan-acceptance.v1.schema.json` | 模型语义 body 与机械 envelope 分开；见同目录 semantic/review schemas |
| capsule / physical / evaluation plans | 同目录 `capsule-plan.v1.schema.json`、`physical-plan.v2.schema.json`、`evaluation-check-registry.v1.schema.json`、`evaluation-plan.v1.schema.json`、`evaluation-plan-validation.v1.schema.json` | 候选组合、选择、绑定校验另有同目录 schema |
| scheduler_input / frozen contract | 同目录 `scheduler-input.v1.schema.json`、`run-contract-frozen.v2.schema.json` | 不可变执行权威；验证全链哈希后才能投影 |
| runtime projection / task_graph_state | `harness/lib/scheduler_input.py::verify_runtime_projection`；`harness/lib/graph_scheduler.py`；参考定义 `harness/schemas/task-graph-state.schema.json` | 当前实际执行代码校验；未发现该 JSON Schema 被这条路径直接加载，不能宣称其字段约束均已执行 |
| dispatch / lease / generic worker envelope | `harness/lib/graph_node_dispatcher.py`、`harness/lib/operator_runtime.py`、`harness/tools/operatord.py` | 代码协议；metadata 7/8 阶段 envelope 是设计示例，不宣称独立 schema 已全面生效 |
| Discovery → ingestion → methods/claims | `harness/schemas/evidence/literature_discovery.v1.schema.json`、`research_paper.v1.schema.json`、`research_method.v1.schema.json`、`research_claims.v1.schema.json`、`claim_verdict.v1.schema.json` | 当前 Scientific Evidence ABI；其他科研算子同目录按产物名查找 |
| Report plan / report | 同目录 `scientific_report_plan.v1.schema.json`、`scientific_report.v1.schema.json` | 报告规划与最终报告是不同 schema；Markdown 是人类可读交付，不代替结构化 evidence |
| Final delivery / learning | `harness/metadata/10-final delivery output/`，及实际选中 delivery 算子 | 通用 EvidenceIR/promotion 示例不是当前每次研究任务都会生成的产物 |

选中哪些 capability 不是用户必须手写的架构步骤，而是 Planner 的绑定/组合结果。
注册入口为 `harness/config/capability-capsules.registry.yaml`，显式指向具体 capsule；
对应 `harness/config/logical-operators.json` 与 `physical-operators.json`。
本次核对：68 个注册 manifest 都在 Git 内。不要扫描目录后自动激活未注册 capsule。

## 4. 已遇到的问题与解决状态

逐条问题、原因、修复和验证：
[pre-scheduler-stabilization-log-20260829.md](pre-scheduler-stabilization-log-20260829.md)。
记录包含健康请求、sprint ID 返回、typed intake、Planner PV/binding、Scheduler 连续 tick、
dispatch acknowledgement、旧 session 复活、schema 导入兼容、artifact routing、
study_protocol 传递、report-plan schema 身份以及报告标题解析。
按记录中的 commit 与当次测试判断，不要把后来的已修复问题继续当成当前阻塞。

**最新语义修复（最终无干预 E2E 结果见问题日志）：**

- 默认 Requirement Compiler 已改为 LLM，原 constraint 类别/表达式单独保留并核对；
- 删除 Planner 的语义后处理；语义合同路径不再按 reviewer 错误文本过滤缺陷；
- Discovery 使用结构化查询/纳入/排除/时间与覆盖条件；流程和交付要求不参与关键词推断；
- 结构化 Discovery 缺少必要候选或 audit 时在 producer 交接处失败，rapid 不豁免。

设计与兼容边界：[semantic-retrieval-contract.md](semantic-retrieval-contract.md)。

原始 Planner 的 R2/R3 归属不等于后处理修改后的 objective。不要归因成笼统的
“LLM 智能不稳定”，也不要靠补 stopwords 来隐藏问题。
详细函数、证据和原始复测 prompt 已保存在
[migration-handoff-20260830.md](migration-handoff-20260830.md)。

## 5. 新环境要求与验收

主路径：Linux / Windows WSL2，Python 3.11+（当前核验为 3.12.3）、Bash 4+、
Git、tmux、jq、已认证且兼容 schema-bound 调用的模型 CLI。
当前测试平台：Bash 5.2.21、tmux 3.4、jq 1.7。
核心 Python 依赖来自 `requirements/harness.txt`；不要复制带 system-site-packages 的旧 venv。
`requirements/autosci-solar-native-dev.txt` 是较大的开发环境快照，不是全平台锁文件；
其中旧的个人 cache 路径示例不应照抄。

React lockfile 的 Vite 8 要求 Node `^20.19.0 || >=22.12.0`。
当前 Windows Node 22.23.2 可通过 typecheck/prebuild tests，但当前 WSL 默认 PATH
没有 Linux Node，还可能找到 Windows npm 后失败。新机器应在同一 Linux/WSL
环境安装配套 Node/npm，再运行 `npm ci`；不能把混合 PATH 当作依赖已就绪。
前端开发测试需要仓库根 `tests/harness/status_server/react_app/`；
当前 installer 的 runtime payload 不等于完整开发 checkout。

模型/检索网络、认证、外部服务、GPU/训练工具、浏览器依赖和 Mac-only 集成需按选中功能单独检查。
不要求所有 optional integration 都可用，但不得把未测试标记为 PASS。
Windows 原生 Bash/Python harness 不是已支持替代路径；WSL 首次安装仍需新机器实测。

安装前先确认唯一 runtime，审阅 installer dry-run。主组件是 `harness,autosci`，
会带上 kernel；`--claude-dir`、hooks/MCP 注册会影响用户工具配置，必须先确认。
不要自动启动 Electron 内嵌 backend、Vite dev server、示例端口或另建测试 runtime。

启动锁定 backend 时，显式设置一致的 `HARNESS_DIR`、`SOLAR_HARNESS_DIR`、
`HARNESS_SPRINTS_DIR`、`SOLAR_BIND_HOST`，以及相同的
`SOLAR_STATUS_PORT_START` / `SOLAR_STATUS_PORT_END` 来禁止端口 fallback。
这些值只能来自用户确认，不能硬编码旧机器值。启动后核对实际 cwd、环境、
监听端口、URL、Git commit、session 数和 worker 状态。
不要用“sleep 几秒”代替健康检查，也不要用 tmux 前缀误杀相似 session 名。

离线验证、Git tree 完整性检查和精确复测 prompt 见迁移 handoff。
本次全仓静态/环境检查与限制见
[portability-audit-20260830.md](portability-audit-20260830.md)。
**GitHub 搬运代码不等于新机器通过验收**；必须在已批准的目标环境实际安装、
验证 import、前端构建和唯一 backend 身份，最后由用户授权进行 rapid E2E。
