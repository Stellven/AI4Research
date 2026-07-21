# DeepDive Requirement Compiler Isolation

## 目标

DeepDive 需要使用需求编译管道里已经验证过的一部分思想：结构化输入、任务图、证据门、traceability 和 closeout。
但 DeepDive 不能直接复用 `codex_pm_router.py` 的普通需求路由，否则普通需求分析、普通调研和 DeepDive 长程研究容易互相污染。

本设计采用“按需复制 + 改名 + DeepDive 内聚”的方式：

- 普通 PM / PRD 需求继续由 `tools/codex_pm_router.py` 处理。
- 普通 RawIntent 入口可按触发词调用 `GPTRequirementWriter` 做需求展开。
- DeepDive 使用 `lib/research/deepdive_requirement_compiler.py`。
- DeepDive 启动入口先调用 `DeepDiveBriefExpander` 做研究 brief 展开。
- 两条链路不互相 import。
- DeepDive 不写 `raw_intent.json` / `requirement_ir.json`。
- DeepDive 产物使用 `solar.deepdive.requirement_contract.v1`。

## 边界原则

```text
┌────────────────────────────┬────────────────────────────────────────────┐
│ 原则                       │ 决策                                       │
├────────────────────────────┼────────────────────────────────────────────┤
│ 普通需求入口               │ RawIntent + GPTRequirementWriter + PM     │
│ DeepDive 入口              │ DeepDiveBriefExpander + DeepDiveCompiler  │
│ 代码依赖                   │ 不互相 import                             │
│ Schema                     │ 不复用 solar.requirement_ir.v1            │
│ DAG 节点                   │ DeepDive 只使用 D* 节点                   │
│ Logical operator           │ DeepDive 只使用 DeepDive* 名称            │
│ 触发条件                   │ 必须显式 deepdive profile/source/关键词   │
│ 泛词触发                   │ “研究/调研/论文”不能触发 DeepDive         │
└────────────────────────────┴────────────────────────────────────────────┘
```

## 复制 / 改名 / 映射关系

```text
┌────────────────────────────┬──────────────────────────────┬──────────────────────────────┐
│ 需求管道概念               │ DeepDive 名称                │ 处理策略                     │
├────────────────────────────┼──────────────────────────────┼──────────────────────────────┤
│ RawIntent capture           │ DeepDiveBriefCapture         │ 复制概念，不写 raw_intent     │
│ GPTRequirementWriter prompt │ DeepDiveBriefExpander        │ 只复制展开能力，改路由/schema │
│ Requirement IR              │ DeepDiveResearchContract     │ 改 schema，不复用 IR 文件名   │
│ Requirement item mapping    │ DeepDiveQuestionMapping      │ 从 REQ 映射改为 DQ 映射       │
│ Research DAG skeleton       │ DeepDiveEvidenceDAG          │ 改成 deepdive_research DAG    │
│ Coverage report             │ DeepDiveTraceabilityReport   │ 对问题/证据/章节做覆盖检查    │
│ Acceptance verdict          │ DeepDiveCloseoutDecision     │ 只决定 DeepDive closeout      │
└────────────────────────────┴──────────────────────────────┴──────────────────────────────┘
```

## GPTRequirementWriter 与 DeepDiveBriefExpander

```text
┌────────────────────────────┬────────────────────────────┬──────────────────────────────┐
│ 项目                       │ GPTRequirementWriter        │ DeepDiveBriefExpander        │
├────────────────────────────┼────────────────────────────┼──────────────────────────────┤
│ 所属链路                   │ 普通需求管道               │ DeepDive 研究入口            │
│ 入口文件                   │ lib/intent_gateway.py       │ lib/research/cli.py          │
│ 物理脚本                   │ tools/chatgpt_requirement…  │ lib/research/deepdive_brief… │
│ 输出 schema                │ solar.requirement_ir.v1     │ solar.deepdive.*             │
│ 产物                       │ raw_intent/requirement_ir   │ deepdive_*                   │
│ 调度/路由                  │ logical-operators registry  │ DeepDive 内部启动契约        │
│ 共享内容                   │ 需求展开 prompt 思路        │ 需求展开 prompt 思路         │
│ 禁止共享                   │ schema、路由、状态、artifact│ schema、路由、状态、artifact │
└────────────────────────────┴────────────────────────────┴──────────────────────────────┘
```

`DeepDiveBriefExpander` 不是全局 logical operator，也不进入普通 `operator_registry`。它是 DeepDive 启动入口的一步本地 compiler，产物只供 `source/evidence/chapter/chief-editor` 流程使用。

## DeepDive 专属 DAG

```text
D0 DeepDiveBriefExpander
  ↓
D1 DeepDiveBriefCapture
  ↓
D2 DeepDiveSourcePlanner
  ↓
D3 DeepDiveSourceCollector
  ↓
D4 DeepDiveClaimCompiler
  ↓
D5 DeepDiveContradictionScanner
  ↓
D6 DeepDiveChapterPlanner
  ↓
D7 DeepDiveChiefEditor
  ↓
D8 DeepDiveClaimVerifier
  ↓
D9 DeepDiveArtifactPublisher
```

这个 DAG 只属于 DeepDive，不作为普通 `RESEARCH` 或 `FULL_SPEC` 的变体。

## 显式触发规则

允许触发 DeepDive：

- `profile=deepdive`
- `profile=deepdive_research`
- `source_channel=deepdive`
- 用户明确输入 `DeepDive` / `Deep Research` / `深度研究` / `深研`

不允许触发 DeepDive：

- 只出现 `研究`
- 只出现 `调研`
- 只出现 `论文`
- 只出现 `综述`
- 普通 PM intake 的 `request_type=research`

## 一致性维护规则

需求管道和 DeepDive 会长期共享“思想”，但不共享运行时对象。后续改动按下面规则保持一致：

```text
┌────────────────────────────┬────────────────────────────────────────────┐
│ 如果普通需求管道修改       │ DeepDive 同步检查                         │
├────────────────────────────┼────────────────────────────────────────────┤
│ traceability 字段增加      │ 检查 DeepDiveTraceabilityReport 是否需要  │
│ DAG gate 规则调整          │ 检查 DeepDive D* gate 是否需要等价增强    │
│ acceptance/closeout 变严   │ 检查 DeepDiveCloseoutDecision 是否同步    │
│ evidence policy 变更       │ 检查 DeepDive evidence_policy 是否同步    │
│ schema version 升级        │ 只更新 DeepDive schema，不复用 PM schema  │
│ logical operator 改名      │ 只更新映射文档，不把 PM 名称带入运行时    │
└────────────────────────────┴────────────────────────────────────────────┘
```

## 反污染检查

每次修改 DeepDive 编译器后，必须验证：

- DeepDive expansion 产物是 `deepdive_brief_expansion.*`，不是 `gpt_requirement_writer_output.*`。
- DeepDive contract 的 `schema_version` 不是 `solar.requirement_ir.v1`。
- DeepDive contract 不包含顶层 `requirement_ir`。
- DeepDive DAG 的 `dag_variant` 是 `deepdive_research`。
- DeepDive DAG 节点 id 全部以 `D` 开头。
- DeepDive logical operator 全部以 `DeepDive` 开头。
- 普通 `研究/调研/论文` 文本不会通过 `is_explicit_deepdive_request()`。

## 当前实现

- 模块：`lib/research/deepdive_requirement_compiler.py`
- Brief 扩展：`lib/research/deepdive_brief_expander.py`
- 普通需求 GPT 展开：`tools/chatgpt_requirement_writer_operator.py` + `lib/intent_gateway.py`
- 测试：`tests/research_survey/test_deepdive_requirement_compiler.py`
- 文档：`docs/deepdive-requirement-compiler-isolation.md`
