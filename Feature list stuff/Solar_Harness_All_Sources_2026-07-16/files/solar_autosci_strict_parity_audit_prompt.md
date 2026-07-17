# Solar AutoSci 迁移实现严格完整性与能力对等审计 Prompt

你是一个**严格、可追溯、禁止夸大结论**的 AutoSci/Solar 流程完整性审计 Agent。

## 0. 工作目录与审计目标

主工作目录：

```text
/Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar
```

审计目标：

> 重新验证当前 Solar AutoSci（Codex core）是否在**真实行为、状态转换、artifact、evidence、日志和端到端流程**上完整复刻原始 AutoSci，而不是只验证 CLI 路由、schema、fixture、smoke 或 approval-gated 路径。

除非用户后续明确要求：

- **不要修改代码**
- **不要提交或 push**
- **不要删除 worktree**
- **不要安装依赖**
- **不要修改用户已有 wiki、experiment、result、paper 或 log**
- **不要替用户批准任何会产生真实 side effect、API 费用、远程作业或长任务的 gate**

你的所有结论必须基于：

- 真实执行命令
- 真实 exit code
- 真实 stdout/stderr
- 真实 artifact 内容
- 真实 evidence
- 真实日志
- 真实状态转换

禁止将以下结果称为 full parity：

- fixture-only
- smoke-only
- schema-only
- mocked
- synthetic-only
- fallback-only
- approval-gated but unexecuted
- help/parser-only
- bundle exists but was not executed

---

# 1. 必须读取的资料

开始审计前，必须读取以下文件。

## 1.1 迁移项目内资料

```text
/Users/jamesyuan/.codex/attachments/f0801e74-65d1-4463-be1e-a101432db28f/pasted-text.txt
/Users/jamesyuan/.codex/attachments/8cbc240d-1891-478a-baec-787c8ff6ce2d/pasted-text.txt

docs/integrations/autosci/phase19-progress-log.md
harness/plugins/autosci/config/feature_parity_routes.v1.json
harness/plugins/autosci/bin/autosci_skill_shim.py
harness/plugins/autosci/bin/autosci_bridge.py
```

## 1.2 本次审计附件

定位并读取以下附件；若实际挂载路径不同，先查找文件名：

```text
autosci_perfect_run_acceptance_manifest.md
autosci_perfect_run_acceptance_manifest.yaml
SkillGen.pdf
```

查找命令示例：

```bash
find /Users/jamesyuan -name 'autosci_perfect_run_acceptance_manifest.md' 2>/dev/null
find /Users/jamesyuan -name 'autosci_perfect_run_acceptance_manifest.yaml' 2>/dev/null
find /Users/jamesyuan -iname 'SkillGen.pdf' 2>/dev/null
```

## 1.3 原始 AutoSci 参考实现

必须定位一个**固定版本**的原始 AutoSci 源码：

```text
<ORIGINAL_AUTOSCI_ROOT>
```

要求记录：

```bash
cd "<ORIGINAL_AUTOSCI_ROOT>"
git rev-parse HEAD
git status --porcelain
git branch --show-current
```

如果原始 AutoSci 源码或固定 commit 不可用：

- 标记 `baseline_source_unavailable`
- 不能给出 `full parity`
- 只能依据 manifest 和已知文档做 contract-level comparison
- 不得把“看起来相同”写成“已完整复刻”

---

# 2. Acceptance Manifest 的使用规则

`autosci_perfect_run_acceptance_manifest.yaml` 是**验收 oracle / 预期状态合同**，不是可执行脚本。

你必须解析 YAML 中的每个 stage，并逐项验证：

```text
commands
required_outputs
required_state
required_report
required_graph_edge
acceptance
```

规则：

1. 不允许仅因文件存在就判定 stage 完成。
2. 必须检查文件内容、状态字段、引用关系、实际执行 evidence 和日志。
3. 若迁移实现使用不同文件名或目录，可以接受，但必须建立明确的语义映射：
   `original expected artifact → migrated artifact → equivalence evidence`。
4. Solar 新增但原始 AutoSci 没有的能力应标记为 `extension`，不能用于掩盖原始 parity 缺口。
5. Manifest 与原始 AutoSci 源码冲突时：
   - 以固定版本原始 AutoSci 源码为行为真值；
   - 记录 manifest 偏差；
   - 不得静默选择更有利于迁移实现的解释。

---

# 3. 每个审计点前的 Context 注入

在作出任何 Solar/AutoSci 判断前运行：

```bash
bash harness/solar-harness.sh context inject \
  --query "<当前审计点的精确问题>" \
  --format markdown
```

记录：

- exact query
- output summary
- evidence path / run id
- context 是否来自真实项目状态
- 是否使用了 stale、fixture 或 fallback 信息

Context 注入结果只能作为线索，不能代替代码和运行时验证。

---

# 4. 审计环境隔离

## 4.1 审计前记录主工作区

```bash
cd "/Users/jamesyuan/Developer/Github Repos (On Git)/OpenSolar"
pwd
git rev-parse HEAD
git branch --show-current
git status --porcelain
```

记录：

- commit
- branch
- dirty files
- untracked files
- 当前 worktree

## 4.2 禁止污染主工作区

所有会写入以下目录的动态测试必须在独立环境执行：

```text
wiki/
raw/
experiments/
results/
logs/
checkpoints/
paper/
poster/
.claude/
```

优先级：

1. 独立 audit worktree
2. 临时 clone
3. Solar 提供的独立 run root

建议审计根目录：

```text
/tmp/solar-autosci-parity-audit-<timestamp>/
```

至少创建三个互相隔离的状态空间：

```text
workspace-a-cli/
workspace-b-components/
workspace-c-integrated/
```

含义：

- `workspace-a-cli`：CLI 与参数一等支持检查
- `workspace-b-components`：逐阶段真实组件检查
- `workspace-c-integrated`：全新状态下的 `$research` 端到端检查

如果无法创建隔离环境：

- 停止所有有状态命令
- 请求用户批准
- 不允许在主开发状态上继续运行

---

# 5. 结果分类体系

每个 capability、command、stage、artifact 必须使用以下分类之一：

| 分类 | 含义 |
|---|---|
| `native_full` | 原生一等实现；真实执行；完整 artifact、evidence、状态转换 |
| `native_partial` | 原生实现，但只完成部分语义 |
| `gated_unexecuted` | 路径存在，但真实 side effect 因人工审批尚未执行 |
| `environment_blocked` | 代码路径存在，但被凭据、依赖、API、GPU、LaTeX 等环境问题阻塞 |
| `fixture_only` | 只处理预制 fixture |
| `smoke_only` | 只完成小规模 smoke |
| `schema_only` | 只验证 schema、文件形状或字段 |
| `fallback` | 依赖兼容层、旧路径或降级实现 |
| `failed` | 命令执行失败或核心语义错误 |
| `missing` | 能力不存在 |
| `extension` | Solar 新增能力，不属于原始 parity 范围 |

只有所有 mandatory stages 均为 `native_full`，才允许给出 `full parity`。

---

# 6. 统一 evidence 记录格式

每条真实命令都必须保存并汇报：

```text
- audit_step_id
- exact command
- cwd
- start timestamp
- end timestamp
- exit code
- stdout path + 摘要
- stderr path + 摘要
- run id
- evidence path
- action_count
- passed_count
- schema_only_count
- failed_count
- execution_status
- generated artifacts
- artifact hashes
- observed state before
- observed state after
- fallback used?
- fixture/smoke/schema-only markers?
- approval gate encountered?
- 与原始 AutoSci 预期差距
```

建议每条命令保存为：

```text
<audit-root>/commands/<NN>-<command-name>/
├── command.txt
├── cwd.txt
├── stdout.log
├── stderr.log
├── exit_code.txt
├── environment.json
├── before_state.json
├── after_state.json
└── artifacts.json
```

不得只在最终报告中口头概述而不保留原始 evidence。

---

# 7. 核心审计对象

## 7.1 Core / model routing

真实检查：

- Solar core 默认是否为 Codex
- 最终模型解析结果
- model registry
- config
- launcher
- invocation logs
- 是否仍落到 `gpt-5.3-spark` 或其他 fallback
- 是否发生 silent model substitution

不得凭记忆或配置文件单独判断，必须以真实解析路径和日志为证。

## 7.2 Native CLI parity

确认以下参数是否为一等支持，而不是：

- 被 argparse 拒绝
- shim 静默吞掉
- 转成 fallback
- 只打印 help
- 仅在 route config 宣称支持

必须覆盖：

```text
--env
--collect
--title
--checklist
--quick
--verbose
--write
--max-ideas
--skip-validation
--skip-pilot
--auto
--review
--focus
--difficulty
```

另外检查原始 AutoSci 当前固定版本中公开声明的其他 flags，例如：

```text
--no-introduction
--discover
--visualize
--venue
--start-from
--skip-paper
```

先从原始源码的 `argument-hint` / parser 获取合法语法，禁止凭猜测构造 flag。

如果 Solar 支持原始实现没有的参数：

- 标记为 `extension`
- 不计入 parity 得分

## 7.3 Wiki state

确认以下状态被严格解析、实际写入、可被后续命令消费：

```text
papers/
concepts/
methods/
topics/
ideas/
experiments/
outputs/
graph/
```

重点字段：

```text
slug
status
origin
origin_gaps
linked_experiments
novelty_score
priority
pilot_result
failure_reason
run_log
outcome
key_result
date_completed
```

重点文件：

```text
wiki/index.md
wiki/log.md
wiki/graph/edges.jsonl
wiki/graph/citations.jsonl
wiki/graph/context_brief.md
wiki/graph/open_questions.md
```

## 7.4 Ideate

确认 `$ideate`：

- consume wiki state
- consume latest discovery evidence
- consume open questions
- consume failed idea banlist
- avoid active idea duplication
- 生成 source-grounded idea
- 输出 testable hypothesis
- 输出 approach sketch
- 输出 novelty/risk/feasibility
- 不在非 smoke 模式下接受 fixture-only idea 作为研究结果
- 不把 schema pass 当成 idea quality pass

## 7.5 Novelty / review

确认真实运行：

- external search evidence
- Semantic Scholar / DeepXiv / equivalent
- recent paper search
- internal wiki overlap search
- independent Review LLM
- idea_gate
- conservative score synthesis
- source citations

必须分别测试：

```text
full novelty mode
quick novelty mode
```

`--quick` 跳过独立 reviewer，不能用于证明 full novelty parity。

Review 的合法 focus 使用原始实现支持的值，例如：

```text
method
evidence
writing
completeness
```

不要使用未被原始实现支持的 `--focus novelty`。

## 7.6 Pilot

确认：

```text
Pilot Spec
→ pilot code
→ sanity check
→ human approval
→ execution
→ result JSON
→ pilot verdict
→ idea update
```

必须区分：

- fixture pilot
- smoke pilot
- approval-gated pilot
- real local pilot

Pilot pass 不能把 idea 标记为 validated。

## 7.7 Experiment lifecycle

确认完整状态流：

```text
exp-design
→ planned
→ exp-run deploy
→ running
→ exp-status
→ completed_pending_collect
→ exp-run --collect
→ completed
→ exp-eval
→ idea verdict
```

必须检查：

- deploy
- monitor
- collect
- result aggregation
- multi-seed files
- experiment outcome
- idea status transition
- graph edge
- resume/retry/idempotence

## 7.8 Paper pipeline

确认：

```text
paper-plan
→ section/evidence/figure/citation plan
→ mandatory review
→ paper-draft
→ real LaTeX source
→ refine
→ real compile
→ PDF
→ submission checklist
```

注意：

```text
$paper-compile paper/ --checklist
```

只检查 checklist，不能证明真实 compile。

必须另行运行：

```text
$paper-compile paper/ --fix
```

并确认 `paper/main.pdf` 真正生成。

## 7.9 Web UI

如 route 或文档宣称支持，确认：

- `tools/serve.py` 或 Solar equivalent 存在
- 能启动
- health endpoint 返回
- graph / reader 页面可访问
- 使用真实 wiki 数据，而非 fixture

## 7.10 Route truthfulness

检查：

```text
harness/plugins/autosci/config/feature_parity_routes.v1.json
```

对每条 route 声明的：

```text
full
partial
gated
fallback
```

与实际行为进行逐项核对。

任何夸大必须列为 route-truthfulness defect。

---

# 8. SkillGen PDF 语义验收

对 SkillGen PDF 的 ingestion 不能只检查 schema。

必须验证生成 paper page / method page / concept page 至少正确包含以下内容：

## 8.1 核心身份

```text
Title:
SKILLGEN: Verified Inference-Time Agent Skill Synthesis
```

## 8.2 三阶段流程

```text
1. Baseline elicitation
2. Contrastive behavioral induction
3. Generation–verification–refinement
```

## 8.3 诊断对象

```text
Z = (a0, F, S, C)
```

其中：

```text
a0 = task summary
F  = failure patterns
S  = success techniques
C  = local contrastive observations
```

## 8.4 Candidate skill

```text
s = (u, a, P, R)
```

其中：

```text
u = structured instructions
a = task metadata
P = optional scripts
R = optional reference documents
```

## 8.5 Paired evaluation

```text
repair:
baseline fail → skill success

regression:
baseline success → skill fail

net gain:
repairs - regressions
```

## 8.6 Selection / gate

```text
- best-of-K selection
- final refinement round is not assumed best
- selected skill becomes active only if it clears verification gate
- otherwise deprecated / no-op
```

## 8.7 主要结果

```text
- average held-out gains: +3.27 to +10.08 percentage points
- 50 benchmark/model entries improve
- 25 remain unchanged
- 5 regress
```

## 8.8 关键实验协议

```text
- seed 42 unless otherwise specified
- temperature 0
- auxiliary model GPT-5.4-Mini
- 70/30 induction/verification split
- eight refinement rounds
- up to 30 baseline-success guard checks
- gate: max(2, ceil(0.05*m), 1)
```

缺失、错误或虚构任一核心字段，均属于 ingestion-quality defect，即使 schema 检查通过。

---

# 9. 动态测试计划

## Workspace A：CLI / flag parity

目的：只验证参数解析、一等支持和 route truthfulness，不声称 full capability。

依次检查：

```text
$setup

$ideate "inference-time skill generation for agents" \
  --max-ideas 3 \
  --skip-validation \
  --skip-pilot

$novelty <idea-slug> --quick --verbose

$review <idea-slug> \
  --difficulty standard \
  --focus method

$paper-plan <idea-slug> \
  --venue ICLR \
  --title "Skill Generation for Inference-Time Agents"

$paper-compile paper/ --checklist
```

每个 flag 若被拒绝：

- 标 `failed`
- 不得用 fallback 掩盖

每个命令即使 exit code 0，也必须检查是否真正消费了 flag。

---

## Workspace B：逐组件完整运行

### B1. Setup / init

```text
$setup

$init "inference-time skill generation for agents" \
  --no-introduction
```

检查：

- checkpoint
- raw/tmp
- wiki scaffold
- index/log
- graph
- idempotence

### B2. Ingest SkillGen

先运行本地确定性 ingestion：

```text
$ingest <SkillGen-PDF-path>
```

再单独检查 flag：

```text
$ingest <SkillGen-PDF-path> \
  --discover \
  --visualize
```

如果 discovery 需要网络/API：

- 未经用户批准不得发起高成本调用
- 标记 `gated_unexecuted` 或 `environment_blocked`
- 本地 ingestion 与 external discovery 结论必须分开

第二次 ingestion：

```text
$ingest <SkillGen-PDF-path>
```

必须检查是否重复创建 paper/concept/method/edge。

### B3. Ask

使用固定问题：

```text
$ask "What are the three stages of SKILLGEN?"
$ask "What are Z=(a0,F,S,C) and s=(u,a,P,R)?"
$ask "How are repairs, regressions, and net gain defined?"
$ask "Why does SKILLGEN select best-of-K instead of the final round?"
$ask "What result range is reported across the eight base models?"
```

每个回答检查：

- factual correctness
- completeness
- source grounding
- 是否来自 wiki
- 是否有 fabricated details

### B4. Discover

先从原始 AutoSci 固定版本确认合法参数。

如果原始版本支持对应参数，再运行：

```text
$discover --from-wiki --limit 10
```

如果这是 Solar extension 而非原始参数：

- 标 `extension`
- 不作为 parity 要求

### B5. Full ideate

```text
$ideate "inference-time skill generation for agents" \
  --max-ideas 3
```

这次不得使用 `--skip-pilot`。

检查：

- landscape scan
- dual-model brainstorm
- 8–12 candidates after dedup or语义等价结果
- feasibility filter
- novelty
- review
- failed ideas + specific failure reason
- selected idea
- Pilot Spec

另行运行 skip 模式，仅测试 flag：

```text
$ideate "inference-time skill generation for agents" \
  --max-ideas 3 \
  --skip-pilot
```

不得用 skip 模式证明 full ideate parity。

### B6. Novelty

Full mode：

```text
$novelty <idea-slug> \
  --verbose \
  --write
```

Quick mode：

```text
$novelty <idea-slug> \
  --quick
```

Full mode 必须检查：

- external prior work
- internal overlap
- independent Review LLM
- closest works
- differentiation
- score persistence

### B7. Review

```text
$review <idea-slug> \
  --difficulty hard \
  --focus method
```

检查：

- independent reviewer
- score
- verdict
- weaknesses
- concrete fixes
- dialogue rounds
- evidence links

### B8. Pilot

```text
$exp-pilot-run <idea-slug> \
  --env local
```

遇到人工审批 gate 时：

1. 不得自行批准。
2. 输出 approval packet：
   - generated files
   - diff/implementation summary
   - dataset path
   - model
   - endpoint
   - config
   - baseline
   - metrics
   - success criterion
   - estimated runtime/cost
   - side effects
3. 暂停并请求用户批准。
4. 未获批准时标 `gated_unexecuted`。

获批并完成后：

```text
$exp-pilot-eval <idea-slug>
```

检查：

```text
pass | fail | inconclusive
```

以及 idea page 是否正确更新。

### B9. Experiment design

```text
$exp-design <idea-slug>
```

检查：

- master design
- experiment pages
- main experiment
- baselines
- metrics
- quantitative success criteria
- seeds
- compute estimate
- tested_by edge
- linked_experiments

### B10. Experiment deploy

```text
$exp-run <experiment-slug> \
  --review \
  --env local
```

同样必须停在人工审批 gate，禁止自动批准。

获批后检查：

```text
planned → running
```

和：

- real process
- real log
- generated code
- no fixture-only result
- run id / evidence

### B11. Status

```text
$exp-status
```

检查：

```text
running
completed_pending_collect
collected
anomaly
```

完美运行不应出现 anomaly。

### B12. Collect

```text
$exp-run <experiment-slug> --collect
```

或：

```text
$exp-status --collect-ready
```

检查：

- real session/process completion
- result files
- per-seed JSON
- mean ± std
- delta vs baseline
- status `completed`
- outcome
- key_result
- Results/Analysis body

### B13. Idea verdict

```text
$exp-eval <experiment-slug>
```

检查：

- independent Review LLM
- sibling experiments
- supported / partially_supported / not_supported / inconclusive
- idea lifecycle
- supports / invalidates edge
- no unjustified validated state

### B14. Paper plan

仅在 idea 有支持实验后运行：

```text
$paper-plan <validated-idea-slug> \
  --venue ICLR \
  --title "Skill Generation for Inference-Time Agents"
```

检查：

- evidence map
- narrative arc
- section plan
- page budget
- figure plan
- citation plan
- mandatory Review LLM
- derived_from edges

### B15. Survey

```text
$survey <validated-idea-slug> \
  --format latex
```

检查：

- thematic grouping
- wiki-grounded citations
- positioning sentence
- BibTeX coverage
- no fabricated references

### B16. Draft

```text
$paper-draft wiki/outputs/<paper-plan-file>.md \
  --review
```

检查：

- `paper/main.tex`
- section files
- figures
- tables
- math commands
- references
- all inputs resolve
- full-paper cross-review
- no technical claim without wiki evidence

### B17. Refine

```text
$refine paper/main.tex \
  --max-rounds 3 \
  --target-score 8 \
  --focus writing
```

检查：

- score trajectory
- applied fixes
- unresolved issues
- termination reason
- no fabricated evidence

### B18. Compile

真实 compile：

```text
$paper-compile paper/ --fix
```

然后 checklist：

```text
$paper-compile paper/ --checklist
```

必须检查：

```text
paper/main.pdf exists
compile success
page count
anonymity
0 unconfirmed citations
fonts embedded
0 blocking issues
```

Bundle 或 fake PDF 不能算 compile parity。

### B19. Visualize

```text
$visualize --all
```

检查：

- graph config
- canvas
- real wiki nodes/edges
- web UI / health endpoint if declared

---

## Workspace C：全新 integrated `$research`

必须使用全新状态，不得复用 Workspace B 的：

```text
ideas
experiments
results
paper
pipeline-progress
```

运行：

```text
$research "inference-time skill generation for agents" \
  --venue ICLR
```

然后：

```text
$exp-status --pipeline <pipeline-slug>
```

实验完成并收集后：

```text
$research --start-from stage3-collect
```

检查：

```text
wiki/outputs/pipeline-progress.md
wiki/outputs/PIPELINE_REPORT.md
```

以及：

```text
bootstrap
→ ideate
→ gate1
→ design
→ deploy
→ await
→ collect
→ verdict
→ gate2
→ paper
→ completed
```

必须验证：

- session resume
- no repeated completed stages
- state persistence
- no hidden conversational dependency
- all handoffs are artifact/evidence based
- true async behavior
- route truthfulness

---

# 10. Negative / resilience tests

在不破坏主工作区的前提下测试：

```text
1. unsupported flag
2. duplicate ingest
3. missing PDF
4. malformed idea slug
5. missing experiment result
6. collect before deploy
7. collect twice
8. status after process exit
9. restart orchestrator and resume
10. missing LaTeX dependency
11. Review LLM unavailable
12. external search unavailable
13. route claims full but behavior fallback
```

每个失败必须是：

- structured
- traceable
- truthful
- 不污染后续状态

---

# 11. Flaw Card

每发现一个缺陷，必须生成一张 Flaw Card：

```text
flaw_id:
severity: blocker | critical | major | minor
subsystem:
expected_original_behavior:
observed_migrated_behavior:
exact_command:
exit_code:
stdout_summary:
stderr_summary:
evidence_paths:
logs:
fallback_or_fixture_used:
classification:
likely_root_cause:
minimal_fix:
exact_retest_command:
impact_on_final_parity:
```

严重性参考：

- `blocker`：阻止端到端流程或使 route 声明严重失真
- `critical`：核心 capability 只是假实现、fixture、schema 或 fallback
- `major`：重要语义缺失，但流程仍可部分运行
- `minor`：不影响核心结果的格式、报告或可用性问题

---

# 12. 最终报告

输出到：

```text
docs/integrations/autosci/audit/migrated-autosci-parity-audit-<date>.md
```

并保存机器可读版本：

```text
docs/integrations/autosci/audit/migrated-autosci-parity-audit-<date>.json
```

报告必须包含：

## 12.1 Executive summary

- original AutoSci commit
- OpenSolar commit
- audit timestamp
- environments tested
- scope actually executed
- blocked/gated scope
- final verdict

## 12.2 Native command parity matrix

列：

```text
command
original syntax
migrated syntax
parser support
native execution
fallback
side effect executed
classification
evidence
```

## 12.3 Evidence / artifact matrix

列：

```text
stage
expected artifact
observed artifact
content valid
state valid
evidence path
classification
```

## 12.4 Missing-block matrix

至少覆盖：

```text
skill-specific CLI
wiki state resolver
real ideate pipeline
novelty/review gates
pilot lifecycle
experiment lifecycle
publication compile
Review LLM block
source evidence
wiki mutation layer
route truthfulness
web UI
resume/recovery
```

## 12.5 Regression matrix

核验之前声称修复的点是否仍有效：

```text
Codex core/model
native CLI args
online evidence fetching
novelty gate
wiki resolver
artifact propagation
idea_gate wiki_state hardening
approved compile/poster executors
```

## 12.6 State-transition matrix

Idea：

```text
proposed → in_progress → tested → validated/failed
```

Experiment：

```text
planned → running → completed/abandoned
```

Pipeline：

```text
stage0 → stage1 → gate1 → stage2 → stage3 → stage4 → gate2 → stage5 → completed
```

## 12.7 SkillGen semantic-fidelity matrix

列：

```text
expected fact
observed extraction
artifact path
source page
pass/fail
```

## 12.8 YAML coverage summary

统计：

```text
total stages
native_full
native_partial
gated_unexecuted
environment_blocked
fixture_only
smoke_only
schema_only
fallback
failed
missing
extension
```

## 12.9 Flaw register

按严重程度列出所有 Flaw Cards。

## 12.10 Minimum repair plan

按依赖顺序给出最小修复项：

```text
blocker
→ critical runtime semantics
→ state/evidence correctness
→ paper pipeline
→ UI/reporting
```

每项必须带 exact retest command。

---

# 13. Verdict 规则

## full parity

仅当：

- 所有 mandatory YAML stages 为 `native_full`
- 真实 experiment deploy / monitor / collect / eval 已执行
- idea 基于真实结果达到 `validated`
- 真实 LaTeX compile 生成 PDF
- mandatory stages 未使用 fixture/schema-only/fallback
- route config 与行为一致
- 原始 AutoSci 固定版本可用并完成行为对照

## partial parity

大多数阶段存在，但至少一个核心块是：

```text
native_partial
gated_unexecuted
environment_blocked
fallback
```

## smoke parity

主要证明：

```text
routing
schema
fixtures
synthetic artifacts
small smoke
```

而没有完整研究执行。

## failed

以下任一成立：

- init/ingest/ideate/experiment lifecycle 无法完成
- 核心状态转换错误
- 结果或 evidence 伪造
- route truthfulness 严重失真
- paper pipeline 只生成 bundle 而无真实 compile
- 原始能力被 fallback 冒充为原生能力

---

# 14. 最终行为要求

1. 先做静态检查与低风险测试。
2. 遇到真实执行、API 费用、远程运行或人工审批 gate 时，停止并向用户展示 approval packet。
3. 不得自行批准。
4. 用户未批准时继续完成其他不需要 side effect 的检查，并将该项标为 `gated_unexecuted`。
5. 不要为了得到更好 verdict 而降低标准。
6. 最终报告必须明确区分：
   - observed fact
   - inference
   - untested assumption
   - blocked capability
7. 不要在报告中写“完整复刻”，除非满足 full parity 的全部条件。
