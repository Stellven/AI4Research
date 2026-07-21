# Foundation L2 Candidate → Canonical Decision Table v2

## 1. 本轮处理规则

1. 表中的 `Candidate` 已经是执行完本轮 Merge / Split 之后的候选，不再重复列出被吸收的旧名称。
2. `Merge → Keep` 表示多个旧候选已经合成当前 Candidate；`Split → Keep` 表示一个旧候选已经拆成当前 Candidate，并分别放进正确的 Foundation L1。
3. 用户点名提出疑问的 Candidate 均暂时保持独立；除非问题本身同时提出了明确的 Split / Merge 建议。
4. “职责”说明该功能必须完成什么；“边界”同时写明它包含什么、不包含什么，以便后续测试和去重。
5. 这是 Candidate → Canonical 的 v2 决策稿，不等同于最终批准版。`Keep（暂定）` 表示边界已经可描述，但是否作为独立 Canonical L2 仍需下一轮判断。

## 2. 争议项的结论与解释

### Operator Performance Learning

它负责从已经结束的 operator 执行中学习稳定的历史先验，例如任务类型下的成功率、质量、延迟、成本、失败模式和校准后的置信度，并更新 operator profile 或后续选择所使用的 ranking prior。

它不是：

- 当前运行中选择 operator；这是 `Operator Eligibility Matching` 和 `Operator Selection`。
- 训练 foundational model。
- 修改整个系统的 workflow、gate 或 schema；这是 RSI。

因此它是“跨运行积累 operator 表现知识”，而不是“单次运行中的动态路由”。

### Capsule Invocation

Capsule invocation 是把一个已经选定的 capsule 变成一次受约束的调用：校验并绑定输入、注入上下文、解析 effect/permission、确定兼容 operator 或 backend、发起调用，并把结果规范化为 capsule contract 定义的输出与 evidence。

它不负责 capsule 的打包、注册、发现或选择，也不等于 capsule 内部真正执行科研任务的实现代码。因此本版将 `Capsule Packaging` 与 `Capsule Invocation` 分开。

### Operator Qualification

本版将它明确限定为“添加、启用或晋级 operator 时的准入资格认证”，例如 contract conformance、最低能力、权限、安全、可靠性和基准门槛。程序运行时针对某个任务判断 operator 是否适用，属于 `Operator Eligibility Matching`；从合格集合中选一个，属于 `Operator Selection`。

### Operator Architecture Boundary Enforcement

它强制 logical operator、physical actor/host、capsule、planner 和 harness 之间的架构边界，例如禁止 logical operator 硬编码某个 provider/host，禁止 operator 绕过统一 dispatch、evidence 或 approval contract，禁止 backend 反向拥有 control-plane 语义。

它检查的是“实现是否跨层或越权”，不是 operator 输出是否正确。因此本版先作为 F2 的独立 Candidate 保留。

### Lifecycle, Parity & Runtime Claim Evaluation

这个名称确实包含三类对象：

- Lifecycle claim：某阶段、节点或整条流程是否真的到达声明的生命周期状态。
- Parity claim：某实现是否真的达到目标功能或参考实现的语义等价/覆盖水平。
- Runtime claim：某次真实执行、外部副作用或 provider 调用是否真的发生。

三者的共同功能是“用 typed evidence 验证系统对自身运行状态和能力所作的声明”。此前建议 Merge，是因为它们最终都会进入 verdict generation / evaluation learning，且这个名称像一个 evaluator bundle，而不像单一原子功能。但它们的证据类型、判定规则和测试对象明显不同，所以本版遵照要求保持原样并标记 `Keep（暂定）`；下一轮应专门判断它是一个统一的 System Claim Evaluator，还是三个 L2。

### Model Continuity 与 Availability / Fallback

二者语义不同：

- `Model Continuity Management` 保持跨调用、跨 session、跨模型切换或恢复后的任务上下文、对话状态、tool state 和 continuation token，使同一项工作可以连续进行。
- `Model Availability & Fallback Management` 监测 endpoint/provider/model 是否可用，并在限流、故障、配额或认证异常时执行 failover/fallback。

此前把 Continuity 重命名为 Availability & Fallback，是把“工作不中断”误等同于“provider 可用性”，边界扩大过头。本版分别保留。

### Model/Provider Runtime Configuration 与 Model Capability Registry

不应 Merge。Capability Registry 保存“模型能做什么”的结构化事实，例如 context window、modality、tool use、cost class 和已验证能力；Runtime Configuration 决定“这一环境下怎样调用它”，例如 endpoint、deployment、timeout、quota、routing defaults 和有效 provider settings。

用户凭证录入、provider 开关和 UI 配置属于 Misc；F4 只保留已经解析并供运行时消费的有效配置。

### Model Performance Monitoring 与 Model Usage Auditing

Performance 不是 token usage。Performance Monitoring 关注延迟、吞吐、错误率、任务成功率、输出质量和退化趋势；Usage Auditing 关注调用记录、token、成本、配额、计费归属和政策审计。因此本版把旧的 `Model Performance & Availability Monitoring` 拆成：

- `Model Performance Monitoring`
- `Model Availability & Fallback Management`（吸收 availability 部分）

并保持 `Model Usage Auditing` 独立。

### RSI 在本 repo 中应是什么

本 repo 的 RSI 应定义为：**基于多次运行证据，对可复用系统资产进行提案、实验、审批、部署和回滚的受控自演进**。可演进对象包括 workflow template、operator prompt/policy、capsule、routing rule、schema、gate、adapter 和 memory policy。

单次流程内的 retry、re-plan、换 operator、修改执行顺序或恢复运行，不是 RSI；它们分别属于 Planner、Harness Core 或 Evaluator。单次流程可以产生 RSI 的 experience，但 RSI 的改动应影响未来运行，并且不能绕过评估、审批和回滚。

### Evidence & Artifact Contract Storage 的 nuance

本版不再把它拆进 ledger/repository：

- Contract Storage 保存“合法证据或产物应该长什么样”的 schema、版本、约束、兼容规则和 contract metadata。
- Evidence Ledger 保存“这次运行产生了哪些证据、由谁产生、支持什么 verdict”的不可抵赖记录与索引。
- Research Asset Repository 保存实际文件、数据、模型、代码、报告等 payload。

contract、ledger entry 和 artifact payload 可以互相引用，但生命周期和访问模式不同，因此保持三个 Candidate 更准确。后续可考虑把名称改成 `Evidence & Artifact Contract Registry`，本轮先保留原名。

### Runtime Bridge & Route Execution

它是 planner/harness 与异构执行后端之间的适配执行层：接收已确定的 route/binding，调用相应 actor host、provider、CLI、API、browser 或 remote wrapper，传输 envelope，并把异构返回转换成统一结果/错误/evidence 格式。

它不负责选择 route、不负责 operator qualification，也不拥有运行状态的 source of truth。本版先不 Merge。

### Runtime State and Status Management

它维护 run、task、operator、actor/host 的规范状态机和当前状态投影，例如 queued、leased、running、blocked、failed、completed、draining、quota_exhausted，并保证状态转换、恢复和查询的一致性。

它不同于 `Execution Recordkeeping`：Recordkeeping 保存 append-only event/audit history；State and Status Management 根据事件和规则给出“当前是什么状态”。本版先不 Merge。

### Execution Envelope Construction

它把已经编译的 task contract、context、chosen binding、timeout/retry policy、criticality、approval reference 和 evidence ledger reference 组装成可被 Harness 派发的标准 envelope。它只构造派发契约，不负责选 actor、入队、获取 lease 或真正执行。本版先保持独立。

### Logical Plan、Runtime Plan 与两类领域计划

按照本轮建议，`Logical Plan Generation` 不再单独保留，而是拆入：

- `Research and Experiment Planning`
- `Report and Delivery Handoff Planning`

这两个功能生成“做什么、以什么语义顺序做”的领域计划。`Runtime Execution Planning` 则把已经形成的领域计划转换为可执行策略，加入环境、资源、并发、恢复、dispatch 和 runtime constraint。它们的抽象层不同，所以 Runtime Planning 不应合进两个领域计划。

### 两类 Deliverable Construction

“Construction”只是共同动词，真正决定边界的是构造对象：

- `Report/Paper/Deliverable Construction` 产出人类消费的内容型交付物，例如论文、报告、幻灯片、poster、rebuttal 和交付包叙事。
- `Runtime Deliverable Construction` 产出机器可运行或可部署的交付物，例如 executable、service、package、container、workflow bundle 或部署配置。

因此本版保持二者独立，不再分别吸收到 Decision Artifact Construction 和 Product Integration。

## 3. 新版 Candidate → Canonical 决策表

### F1 — Capability Capsules

| Candidate（已执行 Merge/Split） | 决策 | 职责 | 边界（Includes / Excludes） |
|---|---|---|---|
| Capability Contract Management | Merge → Keep | 定义、验证、版本化 capsule 的能力意图、输入输出、effects、兼容性与路由约束。 | Includes contract/spec declaration、contract versioning、route hints；Excludes packaging、registry publication、selection、invocation。 |
| Capsule Packaging | Keep | 将 capsule 定义、依赖、资源、metadata 和 entrypoint 组装为可分发、可加载的单元。 | Includes bundle/build、dependency manifest、integrity metadata；Excludes execution、registry lifecycle、capability scoring。 |
| Capability Verification & Certification | Merge → Keep | 依据 schema、签名、测试、政策和质量门槛验证 capsule，并授予、撤销或更新 certification。 | Includes conformance、integrity、trust/quality certification；Excludes task-result evaluation 和 registry CRUD。 |
| Capsule Registry Management | Keep | 管理 capsule 的发布、索引、版本、状态、所有权、弃用和可发现 metadata。 | Includes register/publish/update/deprecate/query metadata；Excludes capsule 内容演进、运行时选择和调用。 |
| Capability Discovery, Scoring & Selection | Merge → Keep | 根据任务能力、effects、质量、成本、兼容性和政策要求发现、过滤、评分并选定 capsule。 | Includes registry search、ranking、selection rationale；Excludes operator/model selection 和 capsule invocation。 |
| Capsule Invocation | Keep | 将已选 capsule 的输入、上下文、权限和 binding 具体化为一次调用，并返回 contract-compliant output/evidence。 | Includes input binding、effect checks、invocation、output normalization；Excludes packaging、discovery、内部科研实现。 |
| Capsule Composition | Keep | 将多个 capsule 的 contract、数据依赖、effects 和失败语义组合为复合能力。 | Includes compatibility check、composition graph、composite contract；Excludes全局 workflow planning 和 runtime scheduling。 |
| Capsule Evolution | Keep | 基于批准的改进提案创建、测试、晋级或回滚 capsule 新版本，并管理兼容迁移。 | Includes version evolution、migration、promotion/rollback；Excludes registry 日常管理和 RSI 的跨系统机会发现。 |

### F2 — Operators

| Candidate（已执行 Merge/Split） | 决策 | 职责 | 边界（Includes / Excludes） |
|---|---|---|---|
| Operator Registration | Keep | 将新的 logical/physical operator 身份、contract 引用、owner 和初始状态登记进系统。 | Includes identity creation、uniqueness、initial metadata；Excludes qualification、performance learning 和 runtime selection。 |
| Operator Profile Management | Keep | 维护 operator 的角色、政策、成本、风险、配额、候选 host 和运维 metadata。 | Includes profile CRUD/versioning；Excludes通过运行结果推断能力和具体任务选择。 |
| Operator Capability Profiling | Keep | 根据声明与验证证据形成 operator 的能力、限制、任务类型适配度和置信度画像。 | Includes capability evidence aggregation；Excludes准入认证、实时 eligibility 和 performance prior 更新。 |
| Operator Qualification | Keep | 在 operator 注册、启用或晋级时验证其 contract、安全、权限、可靠性和最低质量门槛。 | Includes admission/certification-time qualification；Excludes每次任务的 eligibility matching 和 final selection。 |
| Operator Eligibility Matching | Keep | 在某次任务运行前，根据 capability、policy、risk、quota、health 和 host constraints 过滤合法 operator 集合。 | Includes runtime candidate filtering；Excludes ranking/final choice、lease 和 dispatch。 |
| Operator Selection | Keep | 在 eligible operator 集合中按质量、成本、延迟、负载、独立性和 fallback policy 选定执行者。 | Includes ranking、tie-break、selection rationale；Excludes eligibility definition、lease 和 invocation。 |
| Operator Performance Learning | Keep | 从历史执行结果学习 operator 在不同任务上的质量、成功率、延迟、成本和失败先验，更新后续选择依据。 | Includes cross-run performance priors；Excludes model training、当前任务选择和系统级 RSI。 |
| Operator Independence Control | Keep | 管理 builder/evaluator 或多评审者之间的独立性、隔离和冲突约束。 | Includes separation-of-duty、conflict rules、independent evidence path；Excludes architecture layering 和评价方法。 |
| Logical Operator Contract Management | Keep | 定义和版本化稳定的语义工作单元，包括输入、输出、capability needs、effects 和完成条件。 | Includes logical contract lifecycle；Excludes绑定具体 actor/provider/host 和实际执行。 |
| Logical-to-Physical Binding Eligibility | Split → Keep | 定义哪些 logical operator 与 physical actor/host 组合在能力、权限和架构上是合法的。 | Includes binding constraints/compatibility rules；Excludes选择具体 binding、lease、dispatch 和 adapter execution。 |
| Operator Architecture Boundary Enforcement | Keep | 防止 logical operator、capsule、physical host 和 backend 越层耦合或绕过统一控制面。 | Includes dependency/layering checks、provider-neutrality、control-plane guard；Excludes输出正确性和 runtime state tracking。 |

### F3 — Evaluator

| Candidate（已执行 Merge/Split） | 决策 | 职责 | 边界（Includes / Excludes） |
|---|---|---|---|
| Evaluation Contract Management | Keep | 将 acceptance criteria、metrics、evidence requirements、thresholds 和 verdict schema 编译并版本化为评价契约。 | Includes evaluation contract compile/validate/version；Excludes选择执行 evaluator 和实际判定。 |
| Evaluation Method Selection | Keep | 根据 claim、artifact、risk 和 contract 选择静态检查、benchmark、LLM review、human review 等评价方法。 | Includes method fit/rationale；Excludes执行方法、模型路由和 verdict 聚合。 |
| Evaluator Assignment | Keep | 从合格 evaluator 中分配一个或多个执行者，并应用独立性、冲突与职责分离约束。 | Includes evaluator eligibility、assignment、review topology；Excludes operator 普遍选择和评价方法定义。 |
| Reasoning & External Plausibility Verification | Merge → Keep | 检查推理链、claim-support 关系、内部一致性，并用外部知识/基线识别明显不合理结论。 | Includes reasoning consistency、source comparison、sanity checks；Excludes完整 benchmark execution 和最终 verdict。 |
| Evaluation Calibration | Keep | 用 gold cases、历史误差和 reviewer agreement 校准评分、阈值和 evaluator 置信度。 | Includes bias/error calibration、threshold tuning；Excludes业务目标设置和模型训练。 |
| Evidence Admissibility & Sufficiency Gating | Merge → Keep | 判断提交 evidence 是否类型合法、来源可接受、覆盖 acceptance criteria 且数量/质量足以进入判定。 | Includes admissibility、coverage、sufficiency gate；Excludes schema registry、artifact storage 和 verdict 结论。 |
| Human Review Gate Management | Split → Keep | 在需要人工判断时生成 review packet、收集带身份/理由的 decision，并控制 gate 关闭。 | Includes HITL review lifecycle；Excludes approval contract 编译和 runtime admission enforcement。 |
| Evaluation Verdict Generation | Keep | 汇总多种评价结果，按 contract 生成 pass/fail/inconclusive、理由、置信度和整改要求。 | Includes result aggregation、verdict、reason codes；Excludes证据生产和部署决策。 |
| Evaluation Quality Learning | Keep | 追踪 evaluator 的误判、漂移、一致性和反馈，改进后续 evaluator 选择及校准。 | Includes evaluator performance history；Excludes operator execution learning 和 RSI deployment。 |
| Lifecycle, Parity & Runtime Claim Evaluation | Keep（暂定） | 用 typed evidence 验证生命周期完成、功能/语义 parity 和真实 runtime/side-effect 声明。 | Includes三类 system claim verification；Excludes普通科研 claim verdict。是否拆成三个 L2 留待下一轮。 |
| Operator Contract & Boundary Validation | Move → Keep | 对 operator 做 contract conformance、smoke 和 architecture-boundary 验证，证明其可被安全接入。 | Includes operator smoke、I/O/effect/boundary checks；Excludes registration、qualification policy 和 task-result evaluation。 |

### F4 — Foundational Models

| Candidate（已执行 Merge/Split） | 决策 | 职责 | 边界（Includes / Excludes） |
|---|---|---|---|
| Model Capability Registry | Keep | 保存模型已声明/已验证的 modality、context、tool use、structured output、cost class 和任务能力。 | Includes capability metadata/versioning；Excludes endpoint credentials、live health 和 per-task routing。 |
| Model Routing & Selection | Merge → Keep | 根据任务、policy、能力、质量、成本、配额和健康状态匹配并选择模型/route。 | Includes task-model matching、ranking、route choice；Excludes provider 配置和实际 invocation。 |
| Model Context Preparation | Keep | 构造模型调用所需的 prompt/context、压缩、检索注入、格式和 token budget。 | Includes context assembly/trim；Excludes长期 memory ownership、model call 和 response parsing。 |
| Model Invocation | Keep | 通过统一接口发起模型请求，处理 streaming、timeout、retry 和调用级错误。 | Includes request execution；Excludes route selection、provider setup 和 semantic response normalization。 |
| Model Tool-Use Mediation | Keep | 管理模型 tool call 的暴露、参数验证、授权、执行回传和循环控制。 | Includes tool schema/policy mediation；Excludes工具自身实现和一般 Harness dispatch。 |
| Model Response Normalization | Keep | 将不同 provider/model 的文本、结构化输出、tool calls、usage 和错误统一成标准返回格式。 | Includes parsing/mapping/validation；Excludes质量评价和 artifact construction。 |
| Model Continuity Management | Keep | 保持跨调用、session、模型切换或恢复后的任务上下文、continuation state 和 tool state。 | Includes continuation/resume/context handoff；Excludes provider health、fallback decision 和长期知识库。 |
| Model Availability & Fallback Management | Split → Keep | 监测模型/endpoint/provider 可用性，并在限流、故障、配额或认证异常时执行 fallback/failover。 | Includes health/circuit breaker/fallback ladder；Excludes上下文连续性和性能质量趋势。 |
| Model Policy Enforcement | Keep | 执行模型使用的隐私、安全、数据驻留、能力限制、预算和允许/禁止规则。 | Includes pre-call policy gates；Excludes用户配置 UI 和通用 approval workflow。 |
| Model Usage Auditing | Keep | 记录模型调用、token、成本、配额、调用者、route 和政策合规审计信息。 | Includes accounting/audit trail；Excludes latency/quality monitoring 和 route selection。 |
| Model/Provider Runtime Configuration | Keep | 解析并向运行时提供 endpoint、deployment、timeout、quota、defaults 和 provider-specific effective settings。 | Includes effective runtime config；Excludes capability facts；credential/UI/provider setup 属于 Misc。 |
| Model Performance Monitoring | Split → Keep | 监测模型的延迟、吞吐、错误率、任务成功率、输出质量和性能退化趋势。 | Includes performance telemetry/trends/alerts；Excludes token/cost audit、availability failover 和 evaluator calibration。 |

### F5 — RSI

| Candidate（已执行 Merge/Split） | 决策 | 职责 | 边界（Includes / Excludes） |
|---|---|---|---|
| Improvement Experience Capture | Merge → Keep | 跨运行收集失败节点、gate rejection、人工介入、低质量 binding、runtime error 和成功模式等改进证据。 | Includes workflow-evolution evidence capture；Excludes普通业务日志和单次运行即时恢复。 |
| Improvement Pattern Discovery | Merge → Keep | 从多次 experience 中识别重复失败、退化、瓶颈和可泛化成功模式。 | Includes clustering/trend/root pattern；Excludes直接生成或部署修改。 |
| Improvement Opportunity Formation | Merge → Keep | 将已验证模式转化为有范围、目标、预期收益、风险和 evidence links 的改进机会。 | Includes opportunity definition/prioritization input；Excludes具体 patch 或实验执行。 |
| Improvement Candidate Generation | Merge → Keep | 为 workflow template、prompt、capsule、routing、schema、gate、adapter 或 memory policy 生成可比较的修改候选。 | Includes proposal/patch candidates；Excludes自动应用和最终选择。 |
| Improvement Experimentation | Merge → Keep | 在受控环境中对改进候选做离线回放、A/B、canary 或 sandbox experiment。 | Includes experiment design/execution for system changes；Excludes业务 POC 和生产部署。 |
| Improvement Evaluation | Merge → Keep | 比较改进候选对质量、成本、延迟、可靠性和安全的影响，形成采用/拒绝证据。 | Includes candidate verdict；Excludes人工批准和部署执行。 |
| Improvement Deployment Control | Merge → Keep | 对批准的系统改进执行分阶段发布、监控、回滚和版本治理。 | Includes approval-aware promotion/canary/rollback；Excludes未经审批的自修改。 |
| Improvement Policy Calibration | Merge → Keep | 基于长期结果调整 RSI 的触发阈值、风险等级、实验预算、审批和自动化边界。 | Includes meta-policy tuning；Excludes某个 workflow 的普通计划参数。 |

注：旧的 `Evidence-Based Workflow Evolution` 不是一个额外原子 L2，而是以上八项共同构成的端到端能力，因此已经被吸收到这八个功能候选中。

### F6 — Data Foundations

| Candidate（已执行 Merge/Split） | 决策 | 职责 | 边界（Includes / Excludes） |
|---|---|---|---|
| Unified Data Access | Keep | 为结构化、非结构化、图、向量和 artifact 数据提供统一寻址、读取与查询抽象。 | Includes common access API/identity；Excludes connector implementation、retrieval ranking 和治理政策。 |
| Source Connector Management | Keep | 管理文件、网页、论文服务、代码仓等 source connector 的注册、能力、健康和生命周期。 | Includes connector registry/config interface；Excludes用户 provider setup 和采集调度。 |
| Source Acquisition & Structural Normalization | Merge → Keep | 从 connector 获取 source，并转换为保留 provenance 的规范数据/文档结构。 | Includes fetch/import、decode、parse、canonical structure；Excludes语义抽取、质量 verdict 和知识图谱更新。 |
| Data Quality Validation & Remediation | Merge → Keep | 检测并处理缺失、损坏、重复、格式异常、不一致和 normalization failure。 | Includes quality profiling、dedup、repair/quarantine；Excludes schema/ontology ownership 和 claim evaluation。 |
| Data Semantics & Schema Management | Merge → Keep | 管理实体/字段语义、ontology、schema、版本兼容，并验证数据与 typed evidence 的结构符合性。 | Includes semantic/schema registry、schema validation；Excludes provenance chain 和 evaluator sufficiency。 |
| Data Lineage & Provenance Management | Merge → Keep | 捕获并验证数据从 source 到派生产物的来源、变换、版本和责任链。 | Includes provenance graph、derivation links、continuity checks；Excludes evidence verdict 和 payload storage。 |
| Hybrid Retrieval | Keep | 组合 lexical、vector、graph、metadata 和 filter retrieval，返回带来源和分数的上下文候选。 | Includes query fusion/ranking；Excludes source ingestion、model context assembly 和最终回答。 |
| Research Knowledge Graph Management | Keep | 管理论文、概念、方法、claim、实验、人员和引用等科研实体与关系。 | Includes entity/edge lifecycle；Excludes opportunity-specific graph 和通用 artifact blob storage。 |
| Opportunity Graph Management | Keep | 管理问题、需求、gap、opportunity、idea、evidence 和 decision 之间的机会空间关系。 | Includes opportunity lineage/dependency/state；Excludes一般科研引用图和 idea workflow 本身。 |
| Opportunity Metadata Enrichment | Keep | 为 opportunity 补充来源、主题、影响、可行性、风险、证据覆盖和状态等结构化 metadata。 | Includes enrichment/linking；Excludes opportunity selection verdict 和 source ingestion。 |
| Evidence Ledger Management | Keep | 记录每次运行产生的 evidence identity、producer、provenance、claim/criterion links、状态和审计链。 | Includes append/index/query evidence records；Excludes evidence schema definition 和大文件 payload storage。 |
| Research Asset Repository | Keep | 保存、版本化和检索代码、数据、模型、文档、图表、实验输出等实际科研资产。 | Includes artifact payload/version/metadata；Excludes evidence verdict、contract schema 和运行状态。 |
| Failure Knowledge Repository | Keep | 保存失败尝试、反例、根因、无效假设、修复和复发条件，支持防重复与诊断。 | Includes failure memory/retrieval；Excludes live incident handling 和 RSI deployment。 |
| Technical Memory Management | Keep | 管理跨运行的技术事实、决策、约束、摘要和可复用上下文的写入、压缩、检索与过期。 | Includes durable memory lifecycle；Excludes model continuity、research graph 专属结构和 raw event log。 |
| Data Governance | Keep | 执行数据访问、隐私、保留、许可、敏感度、删除、共享和审计政策。 | Includes policy/classification/enforcement；Excludes UI account management 和模型调用政策。 |
| Evidence & Artifact Contract Storage | Keep | 保存 evidence/artifact schema、版本、约束、兼容规则和 contract metadata。 | Includes contract registry/storage；Excludes实际 ledger entries 和 artifact payload。 |

### F7 — Harness Core

| Candidate（已执行 Merge/Split） | 决策 | 职责 | 边界（Includes / Excludes） |
|---|---|---|---|
| Run Initialization | Keep | 创建 run/sprint identity、workspace、初始状态、日志/evidence 路径并加载有效配置。 | Includes bootstrap/idempotent init；Excludes意图编译和任务规划。 |
| Work Readiness & Task Graph Scheduling | Merge → Keep | 根据依赖、gate、write scope、资源和状态判断节点 readiness，并生成可调度批次/顺序。 | Includes DAG readiness/scheduling；Excludes选择具体 operator、lease 和 backend invocation。 |
| Execution Assignment, Queueing & Dispatch | Merge → Keep | 将 ready work 分配给已选执行者，管理队列顺序并提交 dispatch 请求。 | Includes assignment、enqueue、dispatch trigger；Excludes eligibility/selection、lease ownership 和 route adapter execution。 |
| Execution Environment Provisioning | Keep | 准备 worktree、sandbox、process、remote environment、runtime dependency 和隔离边界。 | Includes create/prepare/cleanup execution environment；Excludes installer 和 operator selection。 |
| Execution Admission, Approval, Lease & Concurrency Control | Merge → Keep | 在执行前校验 approval/policy/resource 条件，原子获取 lease，并执行并发、互斥、quota 和 backpressure。 | Includes admission gate、approval enforcement、lease/concurrency；Excludes approval contract 编译和任务优先级规划。 |
| Execution Recordkeeping | Keep | 追加记录 dispatch、start、heartbeat、result、error、retry、approval 和 handoff 事件，形成审计历史。 | Includes append-only events/idempotency；Excludes当前状态投影和科研 evidence 语义。 |
| Experiment Loop Automation | Keep | 自动协调 experiment 的 prepare、run、collect、evaluate 和 iteration 控制。 | Includes loop state/stop conditions/repetition；Excludes experiment scientific design 和 result verdict。 |
| Run Recovery Control | Keep | 从中断、worker failure、stale lease 或 partial result 中安全恢复、重试、补偿或终止 run。 | Includes checkpoint/resume/retry/compensation；Excludes长期 RSI 和普通 plan evolution。 |
| Artifact Routing | Keep | 按 contract 将产生的 artifact/evidence 传递到下游节点、ledger、repository 或 delivery channel。 | Includes artifact identity/path/reference routing；Excludes artifact content construction 和 storage implementation。 |
| Run Closure Assurance | Keep | 确认所有节点、gate、artifact、evidence 和 parent/child 状态闭合后，才允许 run 完成。 | Includes closure invariants/finalization；Excludes最终科研评价内容和 delivery construction。 |
| Runtime Bridge & Route Execution | Keep | 按已确定 route 调用 actor host/provider/CLI/API/browser/remote adapter，并规范化结果、错误与 evidence。 | Includes transport/backend adapters；Excludes route selection、lease、current-state ownership。 |
| Runtime State and Status Management | Keep | 维护 run/task/operator/actor-host 的规范状态机、合法转换和可查询当前状态投影。 | Includes state transition/projection/status query；Excludes append-only event history 和用户 UI。 |
| Actor Host & Physical Host Management | Keep | 管理承载 actor 的 host 类型、实例、健康、兼容映射、生命周期和 carrier metadata。 | Includes actor-host registry/runtime lifecycle/legacy compatibility；Excludes operator capability semantics 和 provider model registry。 |
| Runtime Operator Binding Activation | Split → Keep | 将 planner 选定的 logical-to-physical binding 解析为可用 actor-host 实例，并准备进入 lease/dispatch。 | Includes binding resolution/materialization；Excludes binding legality、binding plan choice、queue 和 backend invocation。 |

### F8 — Intention Compilers

| Candidate（已执行 Merge/Split） | 决策 | 职责 | 边界（Includes / Excludes） |
|---|---|---|---|
| Compiler Profile Selection | Keep | 根据输入类型、领域、任务风险和目标输出选择 intention compiler/profile。 | Includes compiler routing/profile choice；Excludes模型路由和任务规划策略。 |
| Intent Classification & Command Parsing | Merge → Keep | 解析自然语言/命令结构，识别意图类别、action、flags 和候选任务类型。 | Includes syntax/intent classification；Excludes完整目标语义、clarification 和计划生成。 |
| Goal Extraction & Parameter Binding | Merge → Keep | 从输入中提取目标、对象、成功条件和参数，并把 command arguments 绑定到规范字段。 | Includes goal/argument normalization；Excludes约束冲突处理和 task decomposition。 |
| Context Projection | Keep | 从项目、用户输入、memory 和附件中投影当前 intention 所需的最小相关上下文。 | Includes context selection/summary/reference；Excludes长期 memory storage 和 model context formatting。 |
| Ambiguity Detection | Keep | 识别目标、术语、范围、约束、优先级和成功条件中的缺失、冲突或多义性。 | Includes ambiguity report/impact；Excludes向用户提问和自动做高风险假设。 |
| Clarification Generation | Keep | 针对阻塞性 ambiguity 生成最小、可回答、能改变 contract 的澄清问题。 | Includes question formulation/answer binding；Excludes普通对话 UI 和目标执行。 |
| Constraint Compilation | Keep | 将预算、时间、权限、scope、质量、数据、审批和禁止事项编译为机器可执行约束。 | Includes constraint normalization/conflict detection；Excludes runtime policy enforcement。 |
| Task Contract Compilation | Keep | 将目标、context、constraints 和 acceptance criteria 编译为稳定、可追踪的任务契约。 | Includes contract schema/validation/version；Excludes任务图和 physical plan。 |
| Contract Traceability | Keep | 维护 raw input、requirements、goals、constraints、task contract、plan node 和 acceptance evidence 的追踪关系。 | Includes IDs/links/coverage；Excludes数据 provenance 的通用变换链。 |
| Execution Envelope Construction | Keep | 将 task contract、context、chosen binding、timeout/retry、criticality、approval/evidence refs 组装为 dispatch envelope。 | Includes envelope validation/serialization；Excludes actor selection、lease、queue 和 execution。 |
| Approval Contract Compilation | Merge → Keep | 将需要谁在何时基于什么 evidence 批准何种 side effect/transition 编译为审批契约。 | Includes approval subjects/conditions/evidence/expiry；Excludes收集人工 verdict 和 runtime admission enforcement。 |

### F9 — Planner

| Candidate（已执行 Merge/Split） | 决策 | 职责 | 边界（Includes / Excludes） |
|---|---|---|---|
| Task Decomposition | Keep | 将 task contract 分解为有明确输入、输出、完成条件和边界的工作单元。 | Includes node definition/granularity；Excludes dependency ordering 和 operator binding。 |
| Planning Strategy Selection | Keep | 根据任务类型、风险、信息缺口和成本选择 sequential、parallel、iterative、exploratory 等规划策略。 | Includes strategy/rationale；Excludes具体任务节点和 runtime route。 |
| Research and Experiment Planning | Split → Keep | 生成研究、检索、假设、实验、benchmark 和验证活动的领域逻辑计划。 | Includes semantic stages/iterations/decision points；Excludes report delivery plan、physical resources 和 dispatch。 |
| Report and Delivery Handoff Planning | Split → Keep | 生成报告、论文、演示、交付包及其 review、compile、handoff 的领域逻辑计划。 | Includes deliverable stages/consumer handoff；Excludes内容构造和 runtime deployment。 |
| Dependency Graph Formation | Keep | 建立工作单元之间的数据、控制、gate、artifact 和 parent/child 依赖，并验证无效图。 | Includes DAG edges/topology/cycle checks；Excludes runtime readiness scheduling。 |
| Execution Requirement Compilation | Keep | 为每个计划节点定义 capability、environment、tool、data、security、evidence 和 side-effect 要求。 | Includes node execution requirements；Excludes选择具体 operator/model/host。 |
| Resource Planning | Keep | 估算并分配时间、算力、模型预算、并发、存储、设备和人工注意力。 | Includes capacity/budget plan；Excludes live quota enforcement 和 billing audit。 |
| Assurance Planning | Keep | 规划 evaluator、test、benchmark、human gate、evidence 和 rollback，以证明任务完成。 | Includes verification/gate strategy；Excludes实际评价和 gate execution。 |
| Plan Validation | Keep | 检查计划对 task contract 的覆盖、依赖合法性、可执行性、风险和约束符合性。 | Includes plan static validation/coverage；Excludes runtime outcome evaluation。 |
| Physical Plan Selection | Keep | 在多个可执行拓扑/资源策略中选择整体 physical plan，并记录成本、风险和 fallback rationale。 | Includes plan alternative ranking；Excludes单节点具体 actor-host lease 和 dispatch。 |
| Plan Evolution | Keep | 在新证据、需求变化或执行反馈出现时版本化修改尚未完成的计划，并保持 traceability。 | Includes re-plan/change impact/versioning；Excludes系统级跨运行 RSI。 |
| Runtime Execution Planning | Keep | 把领域逻辑计划转换为考虑环境、资源、并发、恢复、dispatch 和 runtime constraints 的执行计划。 | Includes runtime topology/batches/checkpoints/fallback intent；Excludes实际 scheduling、lease 和 backend call。 |
| Physical Operator Binding Planning | Split → Keep | 为计划节点选择具体或有序候选的 physical actor/host binding，并给出 fallback ladder 与理由。 | Includes binding choice using capability/health/cost；Excludes绑定合法性规则、runtime activation、lease 和 dispatch。 |

### F10 — Builder

| Candidate（已执行 Merge/Split） | 决策 | 职责 | 边界（Includes / Excludes） |
|---|---|---|---|
| Build Contract Interpretation | Keep | 将 task/build contract 解释为构建目标、接口、acceptance、write scope 和禁止事项。 | Includes build-facing requirement resolution；Excludes intention compilation 和 plan creation。 |
| Build Preparation | Keep | 准备源码、依赖、模板、数据、workspace、toolchain 和构建前检查。 | Includes scaffold/setup/readiness；Excludes通用 installer 和 execution environment provisioning。 |
| Code Construction | Keep | 创建或修改 deterministic source code、scripts、tests 和配置以实现技术功能。 | Includes implementation/refactor within contract；Excludes模型训练和报告写作。 |
| Model Construction | Keep | 构建、训练、微调或组装算法/统计/ML 模型及其可复现定义。 | Includes model/algorithm artifacts；Excludes调用 foundational model 和 benchmark verdict。 |
| Experimental Asset Construction | Keep | 构造实验代码、数据处理、instrumentation、环境描述和运行脚本。 | Includes executable experiment assets；Excludes实验计划、运行协调和结果评价。 |
| Benchmark Asset Construction | Keep | 构造 benchmark dataset、harness、workload、baseline、metric implementation 和 comparison scripts。 | Includes benchmark implementation；Excludes benchmark execution 和 verdict。 |
| Verification Asset Construction | Keep | 构造 unit/integration/e2e tests、validators、fixtures、checklists 和 verification scripts。 | Includes test/validator assets；Excludes evaluator assignment 和最终 gate decision。 |
| Decision Artifact Construction | Keep | 构造 opportunity card、decision record、trade-off matrix、recommendation packet 等决策型产物。 | Includes decision-facing structured artifacts；Excludes论文/报告正文和 runtime package。 |
| Prototype Assembly | Keep | 将代码、模型、数据和界面/接口组合成可演示、可运行、范围受限的 POC/prototype。 | Includes integration for POC outcome；Excludes production hardening 和 product deployment。 |
| Product Integration | Keep | 将已验证组件接入目标产品、接口、数据流和运维边界，完成 production-oriented integration。 | Includes interface/integration changes；Excludes安装分发 UI 和 runtime deliverable packaging。 |
| Defect Repair | Keep | 根据 failure evidence 定位并修复代码、配置、contract 或集成缺陷，并避免回归。 | Includes diagnosis-to-fix within build scope；Excludes evaluator verdict 和 RSI pattern discovery。 |
| Build Evidence Generation | Keep | 为构建过程和产物生成 provenance、diff、test/compile result、manifest、hash 和 acceptance evidence。 | Includes build proof packaging；Excludes evidence ledger storage 和独立评价。 |
| Report/Paper/Deliverable Construction | Keep | 生成和组装人类消费的报告、论文、slide、poster、rebuttal 和叙事型交付包。 | Includes drafting/layout/compile/bundle；Excludes领域交付计划、decision-only artifacts 和 executable packaging。 |
| Runtime Deliverable Construction | Keep | 构造可运行或可部署的 executable、service、package、container、workflow bundle 与部署配置。 | Includes build/package/release-ready runtime artifact；Excludes实际部署、产品集成和人类报告。 |

## 4. 下一轮检查重点

1. 判断 `Lifecycle, Parity & Runtime Claim Evaluation` 是统一的 system-claim evaluator，还是应拆为三个 L2。
2. 检查 `Execution Envelope Construction` 最终归 F8 还是 F9；保持功能不变，只判断 owner。
3. 检查 F7 中 Assignment、Binding Activation、Runtime Bridge 三层接口是否能分别给出独立输入输出和测试。
4. 检查 F9 的 `Physical Plan Selection` 与 `Physical Operator Binding Planning` 是否保持“整体拓扑 vs 节点 binding”的边界。
5. 决定 `Model/Provider Runtime Configuration` 中哪些是 F4 的有效运行时配置，哪些必须移动到 Misc 的 provider/user configuration。
6. 对每个 L1 做 sibling overlap、parent coverage、cross-L1 ownership 和 end-to-end support trace 检查，再批准 Canonical L2。
