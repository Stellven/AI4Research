# Solar Harness 待办 (2026-04-17 会话结束时)

> 下次会话启动后，规划者按优先级派发 Sprint

## 当前状态修订 (2026-05-21)

- `coordinator.sh → TypeScript/Bun 重写` 已从 P0 降级为 P1 架构债。
- 降级原因：当前没有新的 `.coordinator-state` 写坏为 `:` 的复现证据；已有 `sprint-20260521-coordinator-ts-rewrite/` 也只有 PRD / dispatch 草案，没有当前 gate 要求的 `task_graph.json`。
- 硬门槛：除非重新复现 `:` 状态损坏，并补齐正式 Planner 产物 `design.md + plan.md + task_graph.json`，否则扫描器不得把该事项标为当前 P0 或直接派发 Builder。

## P0 — 必须修 (影响稳定性)

### 1. Whisper 实际注入验证
- **现象**: 手动测试 whisper hook 有输出 (33ms, 3 条教训)，但实际对话中没看到 [Subconscious] 标签
- **可能原因**: Claude Code 的 UserPromptSubmit hook stdout 注入方式跟预期不同，或需要新会话加载 settings.json
- **验证方法**: 新会话启动后，看第一个 prompt 有没有 `<system-reminder>[Subconscious]`
- **如果不生效**: 改 whisper 从 UserPromptSubmit 改为 SessionStart hook (一次性注入所有教训)

## P1 — 应该修 (影响体验)

### 2. 协调器 save_state `:` 复现监控与最小修复
- **现象**: .coordinator-state 文件偶尔被写为 `:`，导致每轮误触发派发
- **已做**: save_state 防空值 + PID 互斥 + log >&2 + 初始化替代 rm -f
- **降级状态**: 已从 P0 降级到 P1；先做复现监控和最小修复，不直接重写 coordinator
- **未做**: 根因仍未完全定位；只有重新复现后才允许升级为 P0
- **最小修复**: 在主循环里加 `if [[ "$(cat $COORD_STATE)" == ":" ]]; then save_state "$current_state"; fi`

### 3. CACHE_BOUNDARY 真实注入
- **现象**: coordinator.sh 的 generate_dispatch 有 CACHE_BOUNDARY 但旧 handle_* 没全切过去
- **验收**: `grep -l CACHE_BOUNDARY sprints/*.dispatch.md | wc -l` >= 1

### 4. 协调器 TypeScript 重写（已降级为架构债）
- **理由**: bash 脚本 patch 7 层修不动 (save_state/多进程/log 污染/竞态)
- **范围**: coordinator.sh → coordinator.ts (bun)，进程内状态，事件驱动
- **保留**: session.sh / archive.sh / token-tracker.sh (这些 bash 脚本工作正常)
- **不得直接执行**: 需要先证明当前仍有状态损坏复现，并补齐 `task_graph.json`

### 5. 审判官 /verify-all 集成
- **Sprint 191955 做了 D1-D6** (evaluator.md + dispatch 推荐)，但实际审判官还是手写 bash
- **需要验证**: 新会话中审判官 pane 是否真的会调用 Skill(verify-all)

## P2 — 锦上添花

### 6. Subconscious V2 — 教训聚合去重
- lessons.jsonl 会越来越长，需要定期聚合（相似教训合并）
- whisper 从最近 3 条改为"最相关 3 条"（需要语义搜索，可用 MemPalace）

### 7. 论文方案落地 (arxiv 2603.16856)
- Online Experiential Learning 的 Sprint 经验蒸馏循环
- 已分析完差距，方案在规划者脑中（MEMORY.md 记录）
- 依赖 P0/P1 稳定后再做

### 8. 浏览器工具链清理
- browser-use 修了代码但 MCP 需要新 Claude 会话重连
- 新会话验证 browser-use 是否真的能用
- 如果不能用，考虑彻底删除 browser-use 只保留 playwright

## 今日战报 (2026-04-14 ~ 04-17)

```
Sprint 总数:    ~18
Passed:         12
Failed:         3
Cancelled:      1
Merged:         1
Superseded:     1

关键产出:
  ✅ session.sh (事件流 API)
  ✅ archive.sh (自动归档)
  ✅ wake 命令 (崩溃恢复)
  ✅ token-tracker.sh (自动 token 报告)
  ✅ test-deadhead.sh (断头测试)
  ✅ eval.json (结构化反馈)
  ✅ planner-inbox.md (静默通知)
  ✅ subconscious learn/whisper (经验闭环)
  ✅ PID 互斥 + log >&2 + stat mtime
  ✅ CLAUDE.md 浏览器改 playwright 默认
  ✅ empirical-pipeline (7 阶段实证流水线)
  ✅ Trace2Skill iterate/seed/ReAct/guardrails

发现的 bug:
  🔴 save_state `:` (未根治)
  🔴 多 coordinator 竞争 (PID 互斥已加但未完全验证)
  🟡 CACHE_BOUNDARY 断头
  🟡 @next hook 失败 (Claude Code 不传 env var)
  🟡 whisper 注入可见性未验证
```
