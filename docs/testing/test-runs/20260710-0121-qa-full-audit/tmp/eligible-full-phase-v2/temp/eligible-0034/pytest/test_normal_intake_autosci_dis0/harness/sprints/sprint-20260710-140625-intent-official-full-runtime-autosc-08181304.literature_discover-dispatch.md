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


# DAG Node Dispatch — sprint-20260710-140625-intent-official-full-runtime-autosc-08181304 / literature_discover

Sprint: `sprint-20260710-140625-intent-official-full-runtime-autosc-08181304`
Node: `literature_discover`
Pane: `operator:autosci-literature-discover-worker`
Dispatch ID: `graph-sprint-20260710-140625-intent-official-full-runtime-autosc-08181304-literature_discover-20260710T140626Z`
Graph: `/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0034/pytest/test_normal_intake_autosci_dis0/harness/sprints/sprint-20260710-140625-intent-official-full-runtime-autosc-08181304.task_graph.json`

## Execution Plan

- Logical Operator: `ScientificLiteratureDiscoverer`
- Capability Capsule: `cap.research-literature-discover`
- Selected Physical Operator: `N/A`

## Capsule Stages

- N/A

## Plan Artifacts

- `/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0034/pytest/test_normal_intake_autosci_dis0/harness/sprints/sprint-20260710-140625-intent-official-full-runtime-autosc-08181304.literature_discover-capsule-plan.json`
- `/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0034/pytest/test_normal_intake_autosci_dis0/harness/sprints/sprint-20260710-140625-intent-official-full-runtime-autosc-08181304.literature_discover-physical-plan.json`

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
- `artifacts/scientific/sprint-20260710-140625-intent-official-full-runtime-autosc-08181304/lifecycle_summary.json`
- `artifacts/scientific/sprint-20260710-140625-intent-official-full-runtime-autosc-08181304/evidence.jsonl`

## Write Scope

- `artifacts/scientific/sprint-20260710-140625-intent-official-full-runtime-autosc-08181304/01_paper/literature_discovery.v1.json`

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
   cat "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0034/pytest/test_normal_intake_autosci_dis0/harness/sprints/sprint-20260710-140625-intent-official-full-runtime-autosc-08181304.task_graph.json"
   cat "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0034/pytest/test_normal_intake_autosci_dis0/harness/sprints/sprint-20260710-140625-intent-official-full-runtime-autosc-08181304.contract.md"
   ```

2. 按本节点 goal/acceptance 实现。

3. 运行本节点相关验证；把命令和结果写入 handoff。

4. 写节点 handoff：
   ```bash
   cat > "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0034/pytest/test_normal_intake_autosci_dis0/harness/sprints/sprint-20260710-140625-intent-official-full-runtime-autosc-08181304.literature_discover-handoff.md" <<'EOF'
   # Handoff — sprint-20260710-140625-intent-official-full-runtime-autosc-08181304 / literature_discover

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
   /Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0034/pytest/test_normal_intake_autosci_dis0/harness/solar-harness.sh graph-scheduler mark --graph "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0034/pytest/test_normal_intake_autosci_dis0/harness/sprints/sprint-20260710-140625-intent-official-full-runtime-autosc-08181304.task_graph.json" --node "literature_discover" --status reviewing --in-place
   ```
