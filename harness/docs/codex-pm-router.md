# Codex PM Router

更新日期: 2026-05-23

## 目的

`codex-pm-router` 是 Codex 侧的 PM intake compiler，也是首批 `Requirement Compiler` 入口。

它的职责不是替代 `solar-harness` planner，而是在进入 `solar-harness` 之前，先把用户需求规范化成三类之一：

- `short_impl`
- `full_spec`
- `research`

然后给出稳定的：

- PRD 变体
- contract 变体
- task graph 变体
- lane / priority / acceptance profile
- Requirement IR
- compiled handoff package

## 组成

```text
~/.codex/skills/codex-pm-router/
  SKILL.md
  templates/
  references/
  scripts/compile.sh

~/Solar/harness/tools/codex_pm_router.py
```

其中：

- skill 负责 Codex 侧可安装入口和模板组织
- `codex_pm_router.py` 负责可测试的分类、IR 组装、contract/DAG/handoff 编译和文件落盘

## 使用方式

```bash
python3 ~/Solar/harness/tools/codex_pm_router.py \
  --text "fix the cache miss bug in allocator" \
  --format json
```

研究型需求：

```bash
python3 ~/Solar/harness/tools/codex_pm_router.py \
  --text "Analyze these papers and improve PM writing" \
  --paper "arXiv:2511.01815" \
  --paper "ICLR 2026 coding agent paper" \
  --format json
```

直接把 `.pm/` 和 sprint package 落盘：

```bash
python3 ~/Solar/harness/tools/codex_pm_router.py \
  --text "Upgrade PM pane into a requirement compiler" \
  --sprint-id sprint-20260523-requirement-compiler \
  --emit-dir ~/Solar \
  --emit-sprint-root ~/.solar/harness/sprints \
  --format json
```

或者通过 `pm-dispatch` 走“编译后派单”：

```bash
solar-harness pm-dispatch compile-request \
  --text "Upgrade PM pane into a requirement compiler" \
  --workspace-root ~/Solar \
  --dispatch-planner
```

## 输出契约

编译器输出：

- `pm_intake`
- `classification`
- `canonical_request_type`
- `prd_variant`
- `contract_variant`
- `dag_variant`
- `lane_hint`
- `priority`
- `acceptance_profile`
- `task_graph_skeleton`
- `requirement_ir`
- `compiled_artifacts`

## 首批 Requirement Compiler 产物

编译器可以直接输出：

```text
.pm/
  intake.json
  requirement_ir.json
  prd.md
  Contracts.yaml
  contracts/
    product.yaml
    interface.yaml
    agent_execution.yaml
    research.yaml
  task_dag.json
  handoff/
    codex_handoff.md
    solar_harness_handoff.md
  evals/
    golden_cases.jsonl
```

如果指定 sprint root，还会编译兼容视图：

- `<sid>.prd.md`
- `<sid>.contract.md`
- `<sid>.task_graph.json`
- `<sid>.product-brief.md`
- `<sid>.handoff.md`
- `<sid>.requirement_ir.json`
- `<sid>.Contracts.yaml`

## Solar 接口

为了接纳 Codex PM Router 输出，当前 schema 已扩展：

- `schemas/product-brief.schema.json`
  - `request_type`
  - `template_variant`
  - `pm_intake`
  - `requirement_ir_ref`
- `schemas/task-graph.schema.json`
  - `dag_variant`
  - `research_mode`
  - `evidence_policy`
  - `logical_operator`
  - `verifier_required`
  - `research_stage`
  - `type / owner / inputs / outputs / validation / risk / uncertainty / parallelizable / approval_gate`
- `schemas/requirement-ir.schema.json`
  - canonical Requirement IR source-of-truth schema

## 边界

- 这是 Codex 外层 intake compiler。
- `solar-harness` planner 仍然是内层 execution compiler。
- `Requirement IR` 是新的 canonical source；Markdown PRD / contract 是 compiled views。
- research 请求默认必须走 evidence-ledger 风格 DAG，不应降级成普通 implementation-first 流程。
