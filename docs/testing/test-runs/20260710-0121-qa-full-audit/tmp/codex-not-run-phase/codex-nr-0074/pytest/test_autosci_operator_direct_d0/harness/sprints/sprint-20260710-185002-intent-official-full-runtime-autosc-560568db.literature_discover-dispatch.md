<solar-runtime-context>
规则: 这是从 append-only session log + unified KB recall 生成的运行时投影；它是当前模型工作集，不是事实源。
pane: operator:autosci-literature-discover-worker | dispatch_id: graph-test-autosci-direct-submit | session_id: sprint-20260710-185002-intent-official-full-runtime-autosc-560568db

# Context Projection: sprint-20260710-185002-intent-official-full-runtime-autosc-560568db
Policy: dispatch-default | Tokens: ~0/1800 | Built: 2026-07-10T18:50:04Z

## Knowledge Base Hits
- [default] QMD solar-wiki
- [default] Solar DB
- [default] Solar Obsidian Vault
- [degraded] mirage:nonzero

## Provenance
This context is a projection over session events.
It does not modify or replace the source event log.
Total events in session: see SessionLog.replay()
</solar-runtime-context>

<!-- SOLAR_STATE_READ_PREFLIGHT -->
## 必须先读状态 (防写入 hook 卡死)

在任何 Write/Edit/handoff/eval/status 更新之前，必须先用 Claude/Codex 的 **Read 工具**读取：

`~/.solar/STATE.md`

不要用 `cat` 替代这一步；本地 `state-read-enforcer.sh` hook 只认 Read 工具标记。

如果 Write/Edit hook 仍阻断，立刻 Read 上面的 STATE 文件后重试原写入一次，不要停在“已读”等待。

---

## DEFINITION OF DONE · 强制完成约束

任务没有完成，除非同时满足以下 7 条。交付不是输出代码；交付是用证据证明功能真的工作。

1. 真实调用链接入 — 所有新增/修改功能已接入真实调用链，不允许只写孤立模块。
2. 禁止硬编码 — 不允许硬编码业务数据、测试数据、路径、token、feature flag。
3. 测试必须运行 — 必须运行相关测试；如果不能运行，必须明确说明原因。
4. 执行证据齐全 — 必须给出实际执行过的命令和结果摘要，不接受“应该可以工作”。
5. Diff 自审 — 必须检查 diff，列出每个改动文件的目的。
6. 禁用乐观词 — 如果存在未完成项，禁止使用 “done / complete / implemented”。
7. 结构化收尾 — 最终回答必须分为：已完成 · 已验证 · 未验证 · 风险 · 后续待办。

硬性判定：没有证据，不许报喜；存在未验证项时只能标 `未验证` 或 `风险`，不能标完成。

---


# DAG Node Dispatch — sprint-20260710-185002-intent-official-full-runtime-autosc-560568db / literature_discover

Sprint: `sprint-20260710-185002-intent-official-full-runtime-autosc-560568db`
Node: `literature_discover`
Pane: `operator:autosci-literature-discover-worker`
Dispatch ID: `graph-test-autosci-direct-submit`
Graph: `/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/codex-not-run-phase/codex-nr-0074/pytest/test_autosci_operator_direct_d0/harness/sprints/sprint-20260710-185002-intent-official-full-runtime-autosc-560568db.task_graph.json`

## Execution Plan

- Logical Operator: `ScientificLiteratureDiscoverer`
- Capability Capsule: `cap.research-literature-discover`
- Selected Physical Operator: `N/A`

## Capsule Stages

- N/A

## Plan Artifacts

- `/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/codex-not-run-phase/codex-nr-0074/pytest/test_autosci_operator_direct_d0/harness/sprints/sprint-20260710-185002-intent-official-full-runtime-autosc-560568db.literature_discover-capsule-plan.json`
- `/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/codex-not-run-phase/codex-nr-0074/pytest/test_autosci_operator_direct_d0/harness/sprints/sprint-20260710-185002-intent-official-full-runtime-autosc-560568db.literature_discover-physical-plan.json`

## Goal

Discover candidate literature and produce bounded shortlist evidence.

## Required Skills

- N/A

## Required Capabilities

- `cap.research-literature-discover`
- `research_synthesis`
- `data_extraction`
- `harness.context_preflight`
- `harness.intent`
- `harness.dispatch_visibility`
- `harness.contracts`
- `harness.dag`
- `harness.status`
- `harness.model_routing`
- `intent.match`
- `intent.audit`
- `dispatch.intent_telemetry`
- `dag.validate`
- `dag.ready_nodes`
- `dag.join_gate`
- `autopilot.monitor`
- `autopilot.safe_apply`
- `pane.deadlock_detection`
- `skill.methodology`
- `workflow.planning`
- `debug.systematic`
- `test.tdd`
- `repair.pr-cot`
- `failure.structured_repair`
- `routing.complexity_budget`
- `document.convert`
- `document.markdown_extract`
- `mcp.markitdown`
- `research.empirical_pipeline`
- `research.literature_review`
- `analysis.causal_inference`

## Read Scope

- `dispatch/envelope.json`
- `artifacts/scientific/sprint-20260710-185002-intent-official-full-runtime-autosc-560568db/lifecycle_summary.json`
- `artifacts/scientific/sprint-20260710-185002-intent-official-full-runtime-autosc-560568db/evidence.jsonl`

## Write Scope

- `artifacts/scientific/sprint-20260710-185002-intent-official-full-runtime-autosc-560568db/01_paper/literature_discovery.v1.json`

## Canonical Output Paths

- No sprint artifact outputs declared. For source-code files, use the current repository/worktree path.

## Write Scope Preflight

- No pre-existing stale write-scope artifacts detected.

## Architecture Guard

- 默认原则: 新能力必须做成可插拔 package / plugin / skill / connector，不改主架构和主循环。
- 允许例外: 仅限 P0 bugfix，并且 node.architecture_policy.core_patch_allowed=true 且写明 rollback。
- Online Exploration: 涉及探索/尝试时必须列出 >=2 个候选方向和 kill_criteria，快速淘汰弱方案。
- package_boundary: `plugins/autosci`
- core_hits: ``
- guard_warnings: `none`
- guard_errors: `none`



## Acceptance

- [ ] Emits or validates literature_discovery.v1 evidence for ScientificLiteratureDiscoverer.
- [ ] Records failed or inconclusive status instead of inventing missing evidence.
- [ ] Does not call a hidden backend full workflow runner.

## Rules

- 只做本节点，不接手其他 DAG node。
- 只允许修改 `Write Scope` 里的文件/目录；需要扩大范围时写入 handoff 的 `Scope Change Request`，不要直接扩大。
- 如果 `Write Scope` / `outputs` 包含 `harness/sprints/...` 或 `sprints/...`，必须写入上方 `Canonical Output Paths` 中的绝对路径；不要把 sprint artifact 只写到当前 builder worktree 的相对路径。
- 不要把 parent sprint 标成 passed。
- 不要等待用户确认；遇到阻塞先写清楚证据和最小修复建议。
- 不要停在“继续/要不要继续/等待 review”提示；只要本节点 acceptance 未完成，就自主继续执行。
- 完成后必须写 handoff 并把本节点标记为 `reviewing`；这是释放下游和 evaluator 的唯一闭环。

## Work Steps

1. 读取 graph 和合约：
   ```bash
   cat "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/codex-not-run-phase/codex-nr-0074/pytest/test_autosci_operator_direct_d0/harness/sprints/sprint-20260710-185002-intent-official-full-runtime-autosc-560568db.task_graph.json"
   cat "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/codex-not-run-phase/codex-nr-0074/pytest/test_autosci_operator_direct_d0/harness/sprints/sprint-20260710-185002-intent-official-full-runtime-autosc-560568db.contract.md"
   ```

2. 按本节点 goal/acceptance 实现。

3. 运行本节点相关验证；把命令和结果写入 handoff。

4. 写节点 handoff：
   ```bash
   cat > "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/codex-not-run-phase/codex-nr-0074/pytest/test_autosci_operator_direct_d0/harness/sprints/sprint-20260710-185002-intent-official-full-runtime-autosc-560568db.literature_discover-handoff.md" <<'EOF'
   # Handoff — sprint-20260710-185002-intent-official-full-runtime-autosc-560568db / literature_discover

   ## Summary

   ## Changed Files

   ## Verification Evidence

   ## Capability / KB Usage Evidence

   - 写明实际使用了 dispatch 中哪些 Solar capability / skill / KB context。
   - 如果未使用，写明原因；不要把“被注入”当成“已使用”。

   ## Scope Compliance

   ## Known Risks

   ## Not Done
   EOF
   ```

5. 将节点状态置为 reviewing，等待 evaluator：
   ```bash
   /Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/codex-not-run-phase/codex-nr-0074/pytest/test_autosci_operator_direct_d0/harness/solar-harness.sh graph-scheduler mark --graph "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/codex-not-run-phase/codex-nr-0074/pytest/test_autosci_operator_direct_d0/harness/sprints/sprint-20260710-185002-intent-official-full-runtime-autosc-560568db.task_graph.json" --node "literature_discover" --status reviewing --in-place
   ```

<solar-skills-context>
<!-- auto-generated by solar_skills.py at 2026-07-10T18:50:03Z -->
Solar has 0 general skills and 0 solar-native skills.

Solar-native skills: 
</solar-skills-context>

<solar-intent-context>
<!-- auto-generated by solar_skills.py at 2026-07-10T18:50:03Z -->
## Solar Intent Adapter

- intent solar-harness execute confidence=0.9
  Action: 用户希望执行上一个提议；立即开始执行，无需再次确认。
- hint superpowers test-driven-development confidence=0.85
  Action: 建议使用 Superpowers test-driven-development。

## Intent Rules

- 这是旧 Solar intent-engine-hook.sh 的 Harness 适配层；用于 dispatch 前决策提示。
- direct intent 可以改变执行纪律；skill hint 只作为能力注入建议，不覆盖 sprint 合约。
- 命中 learned-db 规则时，优先按学习规则解释用户意图，但必须保留证据。
</solar-intent-context>

<solar-capability-context>
<!-- auto-generated by solar_skills.py at 2026-07-10T18:50:03Z -->
## Auto-selected Solar Capabilities

- ATLAS (repair.pr-cot, failure.structured_repair, routing.complexity_budget)
  Readiness: injectable_only (no executable/effective scorecard yet)
  Why: 任务涉及失败修复、hook/tool 异常、阻塞恢复或复杂度预算。
  Use: 进入 repair 模式：定位失败点，写明证据链，优先做局部修复；不要静默停住或等待人工拍板。
- Everything Claude Code (agent.inventory, command.catalog, rules.catalog, mcp.catalog)
  Readiness: injectable_only (no executable/effective scorecard yet)
  Why: 任务涉及 Claude Code 生态能力盘点、命令/规则/MCP/agent inventory。
  Use: 只读使用 vendor inventory；不要盲装 hooks 或覆盖现有 Solar 规则。
- MarkItDown (document.convert, document.markdown_extract, mcp.markitdown)
  Readiness: injectable_only (no executable/effective scorecard yet)
  Why: 任务涉及 PDF/Office/HTML/图片等文档转 Markdown。
  Use: 优先把原件转成 Markdown，再交给 Obsidian/QMD/Mirage 入库；保留源文件路径和转换日志。
- Solar-Harness Runtime (harness.context_preflight, harness.intent, harness.dispatch_visibility, harness.contracts, harness.dag, harness.status, harness.model_routing)
  Readiness: injectable_only (no executable/effective scorecard yet)
  Why: 任务涉及 Solar-Harness 自身、pane、dispatch、intent engine、DAG、coordinator、status、模型路由或能力可视化。
  Use: 调用 solar-harness-runtime skill：先 context inject + intent match，再用 skills inject / intent summarize / audit / activation-proof 留证据；模型切换只用 solar-harness models 命令。
- Superpowers (skill.methodology, workflow.planning, debug.systematic, test.tdd)
  Readiness: injectable_only (no executable/effective scorecard yet)
  Why: 任务需要系统化规划、TDD、根因分析或调试纪律。
  Use: 先拆解目标和验收，再做最小实现；调试时记录假设、证据、验证命令和回归测试。
- solar-autopilot-monitor (autopilot.monitor, autopilot.safe_apply, pane.deadlock_detection)
  Readiness: injectable_only (no executable/effective scorecard yet)
  Why: 任务涉及自动盯梢、pane 死等、queue/lease 阻塞、自动推进或协调器断头。
  Use: 先运行 solar-autopilot-monitor.py --json；只对安全项 --apply，派发前检查 pane lease。
- solar-graph-scheduler (dag.validate, dag.ready_nodes, dag.join_gate)
  Readiness: injectable_only (no executable/effective scorecard yet)
  Why: 任务涉及 task_graph、DAG、ready node、join gate、write_scope 或父 sprint readiness。
  Use: 必须验证 task_graph.json；无 write_scope 节点不得并行；父 sprint 通过前必须 parent-ready-check。
- solar-intent-engine (intent.match, intent.audit, dispatch.intent_telemetry)
  Readiness: injectable_only (no executable/effective scorecard yet)
  Why: 任务涉及意图识别、learned intent、dispatch 前能力命中或 intent telemetry。
  Use: 先运行 solar-harness intent match，再用 skills inject 生成 .intent.json；只把 audit 证据写成 worker_used。

## Dispatch Rules

- 这些 capability 是自动选择的执行辅助，不替换 Solar coordinator / planner / evaluator。
- Autoresearch 只能作为 pane-level optimizer/advisor；没有用户授权、--execute、清洁/隔离工作树和 bounded max-iterations 时不得自动运行。
- 若 capability 缺失或不可用，必须 fail-open：继续完成主任务，并在 handoff 写明降级证据。
- 遇到失败、超时、hook/tool 异常时，优先触发 ATLAS structured repair，不要停在等待人工决策。
</solar-capability-context>

<solar-knowledge-context>
<solar-unified-context>
来源: Mirage + QMD solar-wiki + Obsidian Vault + Solar DB + CocoIndex + Understanding + RAGFlow(optional)
规则: 开始开发/设计/分析前，优先参考这些命中；如不足，再主动搜索 vault/qmd。
排序: synthesis/concepts/references/code/understanding 分层融合；raw 只作为证据层靠后。
- [default:other] QMD solar-wiki (qmd://solar-wiki): MinerU Document Explorer 负责 PDF/Markdown/文档索引和语义检索；后台 `solar-harness wiki qmd-embed status` 处理 embedding backlog。
- [default:other] Solar DB (/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/codex-not-run-phase/codex-nr-0074/home/.solar/solar.db): Solar DB 保存 sprint、cortex、accepted artifacts、obsidian_vault_index 和 FTS 索引。设计/开发前先查已有资产，避免重复造轮子。
- [default:other] Solar Obsidian Vault (/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/codex-not-run-phase/codex-nr-0074/home/Knowledge): 本机默认知识库。优先用 `solar-harness wiki qmd-search "<query>" --json` 或 `solar-harness mirage search "<query>" --json` 检索。
降级源: mirage:nonzero
</solar-unified-context>
</solar-knowledge-context>
