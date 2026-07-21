# codex_bridge 入口的研究 artifact 必须出现在 compiled package。

## Research Question
codex_bridge 入口的研究 artifact 必须出现在 compiled package。

## Paper Inventory
- 待补充来源

## Claim Extraction
对每篇论文提取核心 claim、方法、benchmark、限制条件。

## Evidence Map
每个 engineering implication 都必须绑定 source + evidence + confidence。

## Relevance to Our System
输出对 Codex / solar-harness / PM pane 的工程含义。

## Design Candidates
基于证据链生成候选设计方案，并明确 pros / cons。

## Experiment Plan
定义 baseline、metric、threshold 和失败退出条件。

## Build Plan
只有通过 eval gate 的研究结论才能进入实现 DAG。

## Adoption Criteria
- paper/source inventory 完整可追溯。
- claim -> evidence -> implication 映射完整。
- 研究结论具备 adoption/rejection criteria。

## Rejection Criteria
- [medium] PRD / contract / DAG 多份产物漂移 -> 用 Requirement IR 做唯一事实源，所有视图从 IR 编译。
- [medium] 原始需求直接派给 Builder 导致执行发散 -> 强制走 product-brief / planner handoff，不允许 raw request 直派 builder。
- [high] 研究结论缺证据链就进入实现 -> Research mode 强制 evidence ledger 和 review gate。

## Research Artifact Inputs

- path: /Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/codex-not-run-phase/codex-nr-0240/pytest/test_research_artifact_round_t0/research-codex_bridge.json
- project_name: 需求研究-2026-05
- conversation_id: conv-frontdoor-codex_bridge
- source_url: https://chatgpt.com/c/conv-frontdoor-codex_bridge
