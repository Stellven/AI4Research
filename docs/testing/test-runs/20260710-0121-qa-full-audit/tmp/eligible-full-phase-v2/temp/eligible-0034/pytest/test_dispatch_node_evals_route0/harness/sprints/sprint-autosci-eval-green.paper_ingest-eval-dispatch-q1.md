<solar-runtime-context>
规则: 这是从 append-only session log + unified KB recall 生成的运行时投影；它是当前模型工作集，不是事实源。
pane: operator:autosci-evaluator-worker | dispatch_id: graph-eval-sprint-autosci-eval-green-paper_ingest-20260710T140621Z-q1 | session_id: sprint-autosci-eval-green

# Context Projection: sprint-autosci-eval-green
Policy: dispatch-default | Tokens: ~0/1800 | Built: 2026-07-10T14:06:22Z

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


# DAG Node Evaluation Dispatch — sprint-autosci-eval-green / paper_ingest

Sprint: `sprint-autosci-eval-green`
Node: `paper_ingest`
Pane: `operator:autosci-evaluator-worker`
Dispatch ID: `graph-eval-sprint-autosci-eval-green-paper_ingest-20260710T140621Z-q1`
Evaluator Role: `primary`
Evaluator Index: `1/1`
Graph: `/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0034/pytest/test_dispatch_node_evals_route0/harness/sprints/sprint-autosci-eval-green.task_graph.json`
Handoff: `/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0034/pytest/test_dispatch_node_evals_route0/harness/sprints/sprint-autosci-eval-green.paper_ingest-handoff.md`

## Handoff Candidates

- `/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0034/pytest/test_dispatch_node_evals_route0/harness/sprints/sprint-autosci-eval-green.paper_ingest-handoff.md`

## Evaluation Scope

- 只评审本 DAG node：`paper_ingest`。
- 不要评审 parent sprint。
- 不要把 parent sprint 标成 passed。
- 只根据 node goal / acceptance / write_scope / handoff evidence 给 verdict。
- - 当前只有一个 evaluator；直接完成 canonical verdict。

## Node Goal

Ingest supplied paper sources into Solar research paper evidence.

## Acceptance

- [ ] Emits or validates research_paper.v1 evidence.

## Required Capabilities

- N/A

## Evaluation Plan

- Review Mode: `single`
- Required Evaluators: `1`
- Risk Tier: `medium`
- Evaluator Classes: `autosci-evidence-gate`
- Cross Provider Required: `false`
- Parallelizable: `false`
- Evidence Requirements: `handoff_md`, `session_log`, `scope_compliance`
- Independence: writer_same_operator=`denied`, writer_same_provider=`allowed`
- Escalation On Fail: `Verifier`

## Proof Obligations

- `N/A`

## Proof Support Artifacts

- `N/A`

## Write Scope

- `/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0034/pytest/test_dispatch_node_evals_route0/harness/artifacts/green/research_paper.v1.json`

## Architecture Guard

- 默认原则: 新能力必须做成可插拔 package / plugin / skill / connector，不改主架构和主循环。
- 允许例外: 仅限 P0 bugfix，并且 node.architecture_policy.core_patch_allowed=true 且写明 rollback。
- Online Exploration: 涉及探索/尝试时必须列出 >=2 个候选方向和 kill_criteria，快速淘汰弱方案。
- package_boundary: `N/A`
- core_hits: ``
- guard_warnings: `paper_ingest feature/integration node missing package_boundary/plugin boundary`
- guard_errors: `none`

## Required Reads

```bash
cat "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0034/pytest/test_dispatch_node_evals_route0/harness/sprints/sprint-autosci-eval-green.task_graph.json"
cat "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0034/pytest/test_dispatch_node_evals_route0/harness/sprints/sprint-autosci-eval-green.contract.md"
cat "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0034/pytest/test_dispatch_node_evals_route0/harness/sprints/sprint-autosci-eval-green.paper_ingest-dispatch.md"
test -f "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0034/pytest/test_dispatch_node_evals_route0/harness/sprints/sprint-autosci-eval-green.paper_ingest-handoff.md" && cat "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0034/pytest/test_dispatch_node_evals_route0/harness/sprints/sprint-autosci-eval-green.paper_ingest-handoff.md"
solar-harness session evaluate "sprint-autosci-eval-green" --json
```

## Log-Native Evaluation Requirement

- 评审必须消费 append-only session log，不得只看最终 handoff 文件。
- 在 eval.md 的 `Evidence Checked` 中写入 `Session Log: solar-harness session evaluate used`。
- 如果 `session evaluate` 返回 errors/warnings，必须逐项解释是否阻塞本 node verdict。
- 必须检查 `Architecture Guard`：新能力是否为 package/plugin/skill/connector；如触碰 protected core，必须有 `core_patch_allowed=true`、rollback 和 P0 bugfix 证据，否则 FAIL。
- 涉及 online exploration 的 node 必须验证 >=2 个候选方向和 kill_criteria；否则 FAIL。
- 必须把 proof obligations 逐项回填到 eval artifact：
  - `proof_obligations`: 原样记录本 node 的 obligation 列表
  - `proof_checks`: 对 `self_check` 逐项填 `true/false`
  - `verification_results`: 记录 `checked_artifacts / missing_artifacts / proof_gate`
- DeepResearch deterministic artifact gate is **not required** for this node. Do not run `solar-harness research eval-artifacts`, and do not fail this node only because `research_eval.json`, `report_ast.json`, bibliography, source/evidence/claim counts, or citation-accuracy artifacts are absent.
  Local audit reports, packaging-readiness reports, documentation synthesis, and generic `report.compile` outputs are judged by this node's acceptance criteria, proof obligations, session log, write scope, and handoff evidence unless `research_quality_gate_required=true` or explicit `research.*` artifacts/capabilities are present. Leave `research_quality_gate` empty or mark it `{"required": false}`.

## Required Outputs

1. 写 Markdown 评审：
   ```bash
   cat > "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0034/pytest/test_dispatch_node_evals_route0/harness/sprints/sprint-autosci-eval-green.paper_ingest-eval.md" <<'EOF'
   # Node Evaluation — sprint-autosci-eval-green / paper_ingest

   ## Verdict

   PASS 或 FAIL

   ## Evidence Checked

   ## Capability / KB Usage Evidence Checked

   - 检查 handoff 是否说明实际使用了哪些 capability / KB context。
   - 如果 eval PASS，必须说明这些能力证据是否支撑验收。

   ## Acceptance Result

   ## Proof Obligations

   - 逐项说明哪些 obligation 已满足，哪些未满足。

   ## Scope Compliance

   ## Architecture Guard Compliance

   ## Risks

   ## Required Fixes
   EOF
   ```

2. 写机器可读 JSON：
   ```bash
   cat > "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0034/pytest/test_dispatch_node_evals_route0/harness/sprints/sprint-autosci-eval-green.paper_ingest-eval.json" <<'EOF'
   {
     "node_id": "paper_ingest",
     "verdict": "PASS",
     "summary": "",
     "evaluation_plan": {
  "planning_source": "workflow_contract_research_autosci_v1",
  "task_type": "N/A",
  "risk_tier": "medium",
  "review_mode": "single",
  "required_evaluators": 1,
  "evaluator_classes": [
    "autosci-evidence-gate"
  ],
  "parallelizable": false,
  "cross_provider_required": false,
  "independence_policy": {
    "writer_same_operator": "denied",
    "writer_same_provider": "allowed",
    "mechanism": "runtime_autosci_evaluator_adapter"
  },
  "evidence_requirements": [
    "handoff_md",
    "session_log",
    "scope_compliance"
  ],
  "escalation_on_fail": [
    "Verifier"
  ],
  "capacity": {
    "total_evaluators": 1,
    "available_evaluators": 1,
    "busy_evaluators": 0,
    "available_panes": [
      "operator:autosci-evaluator-worker"
    ],
    "required_evaluators": 1,
    "selected_panes": [
      "operator:autosci-evaluator-worker"
    ],
    "capacity_satisfied": true,
    "quorum_dispatch_supported": true,
    "review_mode": "single",
    "dispatchable_now": true,
    "autosci_evaluator": true
  }
},
     "proof_obligations": [],
     "proof_checks": {},
     "verification_results": {
       "proof_gate": "PENDING",
       "checked_artifacts": [],
       "missing_artifacts": []
     },
     "research_quality_gate": {},
     "checked_at": "2026-07-10T14:06:21Z",
     "eval_md_path": "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0034/pytest/test_dispatch_node_evals_route0/harness/sprints/sprint-autosci-eval-green.paper_ingest-eval.md"
    }
    EOF
   ```

## Peer Evaluator Sidecars

- `N/A`

## Canonical Eval Outputs

- Markdown: `/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0034/pytest/test_dispatch_node_evals_route0/harness/sprints/sprint-autosci-eval-green.paper_ingest-eval.md`
- JSON: `/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0034/pytest/test_dispatch_node_evals_route0/harness/sprints/sprint-autosci-eval-green.paper_ingest-eval.json`

3. 提交节点 verdict。通过时会自动释放下游 ready node；失败时只阻塞依赖它的下游：
   ```bash
   /Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0034/pytest/test_dispatch_node_evals_route0/harness/solar-harness.sh graph-dispatch node-verdict --graph "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0034/pytest/test_dispatch_node_evals_route0/harness/sprints/sprint-autosci-eval-green.task_graph.json" --node "paper_ingest" --verdict pass --eval-json "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0034/pytest/test_dispatch_node_evals_route0/harness/sprints/sprint-autosci-eval-green.paper_ingest-eval.json"
   ```

   如果失败，改用：
   ```bash
   /Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0034/pytest/test_dispatch_node_evals_route0/harness/solar-harness.sh graph-dispatch node-verdict --graph "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0034/pytest/test_dispatch_node_evals_route0/harness/sprints/sprint-autosci-eval-green.task_graph.json" --node "paper_ingest" --verdict fail --eval-json "/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/eligible-full-phase-v2/temp/eligible-0034/pytest/test_dispatch_node_evals_route0/harness/sprints/sprint-autosci-eval-green.paper_ingest-eval.json" --reason "写清楚失败原因"
   ```

<solar-skills-context>
<!-- auto-generated by solar_skills.py at 2026-07-10T14:06:21Z -->
Solar has 0 general skills and 0 solar-native skills.

Solar-native skills: 
</solar-skills-context>

<solar-intent-context>
<!-- auto-generated by solar_skills.py at 2026-07-10T14:06:21Z -->
## Solar Intent Adapter

- intent solar-harness execute confidence=0.9
  Action: 用户希望执行上一个提议；立即开始执行，无需再次确认。
- hint agent-rules-books release-it confidence=0.86
  Action: 建议使用 agent-rules-books: release-it.mini。

## Intent Rules

- 这是旧 Solar intent-engine-hook.sh 的 Harness 适配层；用于 dispatch 前决策提示。
- direct intent 可以改变执行纪律；skill hint 只作为能力注入建议，不覆盖 sprint 合约。
- 命中 learned-db 规则时，优先按学习规则解释用户意图，但必须保留证据。
</solar-intent-context>

<solar-capability-context>
<!-- auto-generated by solar_skills.py at 2026-07-10T14:06:21Z -->
## Auto-selected Solar Capabilities

- Superpowers (skill.methodology, workflow.planning, debug.systematic, test.tdd)
  Score: 4.11 level=closed_loop runtime=N/A backend=N/A
  Readiness: effective
  Why: 任务需要系统化规划、TDD、根因分析或调试纪律。
  Use: 先拆解目标和验收，再做最小实现；调试时记录假设、证据、验证命令和回归测试。
- ATLAS (repair.pr-cot, failure.structured_repair, routing.complexity_budget)
  Score: 2.96 level=default_usable runtime=N/A backend=N/A
  Readiness: executable
  Why: 任务涉及失败修复、hook/tool 异常、阻塞恢复或复杂度预算。
  Use: 进入 repair 模式：定位失败点，写明证据链，优先做局部修复；不要静默停住或等待人工拍板。
- Everything Claude Code (agent.inventory, command.catalog, rules.catalog, mcp.catalog)
  Score: 1.96 level=basic_usable runtime=N/A backend=N/A
  Readiness: injectable
  Why: 任务涉及 Claude Code 生态能力盘点、命令/规则/MCP/agent inventory。
  Use: 只读使用 vendor inventory；不要盲装 hooks 或覆盖现有 Solar 规则。
- DeepResearch Report Compilation (report.compile, research.long_report_compiler, research.report_ast)
  Readiness: injectable_only (no executable/effective scorecard yet)
  Why: 任务涉及报告编译、章节组装、ReportAST 生成、结构化长报告。
  Use: 从 report_ast.json 按章节顺序编译报告；R9 节点只拼接不生成新内容；最终报告由 R11 组装。
- Solar-Harness Runtime (harness.context_preflight, harness.intent, harness.dispatch_visibility, harness.contracts, harness.dag, harness.status, harness.model_routing)
  Readiness: injectable_only (no executable/effective scorecard yet)
  Why: 任务涉及 Solar-Harness 自身、pane、dispatch、intent engine、DAG、coordinator、status、模型路由或能力可视化。
  Use: 调用 solar-harness-runtime skill：先 context inject + intent match，再用 skills inject / intent summarize / audit / activation-proof 留证据；模型切换只用 solar-harness models 命令。
- solar-graph-scheduler (dag.validate, dag.ready_nodes, dag.join_gate)
  Readiness: injectable_only (no executable/effective scorecard yet)
  Why: 任务涉及 task_graph、DAG、ready node、join gate、write_scope 或父 sprint readiness。
  Use: 必须验证 task_graph.json；无 write_scope 节点不得并行；父 sprint 通过前必须 parent-ready-check。

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
- [default:other] Solar DB (/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/final-home/.solar/solar.db): Solar DB 保存 sprint、cortex、accepted artifacts、obsidian_vault_index 和 FTS 索引。设计/开发前先查已有资产，避免重复造轮子。
- [default:other] Solar Obsidian Vault (/Users/jamesyuan/Developer/Github Repos (On Git)/BetterSolar/docs/testing/test-runs/20260710-0121-qa-full-audit/tmp/final-home/Knowledge): 本机默认知识库。优先用 `solar-harness wiki qmd-search "<query>" --json` 或 `solar-harness mirage search "<query>" --json` 检索。
降级源: mirage:nonzero
</solar-unified-context>
</solar-knowledge-context>
