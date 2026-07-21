# Architect Investigation #003 — 多 builder pane 并行调度可行性

**架构师**: pane 3 (opus)
**问题**: 当前 4 pane (planner/builder/evaluator/architect) 单 builder 是瓶颈, 调研未来开 2-3 个 builder 并行的可行性
**结论**: **有条件建议** — 短期 (Phase A) 不建议; 中期 (Phase A.3+) 经过 worktree 改造和 dispatch 改造后**可行**, 推荐 2 builder 起步.

---

## 1. 现状分析

### 1.1 物理布局
- tmux session `solar-harness` 4 panes (0/1/2/3), 由 `~/.solar/harness/session.sh` 创建
- 当前角色映射:
  | idx | 角色 | 模型 | 职责 |
  |-----|------|------|------|
  | 0 | planner | opus | 规划, 与监护人对话 |
  | 1 | builder | glm-5.1 | 编码 (单点) |
  | 2 | evaluator | glm-5.1 | 评审 |
  | 3 | second-builder/architect | opus | 现作 architect 拓扑专用 |

### 1.2 代码层硬编码
- `coordinator.sh:62` `choose_builder_pane()` **硬编码** `echo "$PANE_BUILDER"` (即 pane 0.1)
- 注释明确 "pane 3 (architect, opus) 不参与 choose_builder_pane"
- `coordinator-watchdog.sh:194` `PERSONA_PANES=( [0]=planner [1]=builder [2]=evaluator [3]=second-builder )`
- `lib/worktree.sh:22` worktree 路径**写死** `$work_dir/.worktrees/builder` (单一目录, 无 builder index)

### 1.3 dispatch 现状
- 主循环每 iter 派 1 个 sprint (get_latest_sprint_file 单返回)
- 即便 scanner 修了 (sprint-102743), 也是顺序派给同一 builder pane
- sprint-104819 修复后, 同一 pane 不能被 2 sprint 占用 (return 2), 但**不会自动找另一个 builder**

---

## 2. 可行性逐项评估 (5 问答)

### Q1: 2 builder 同时改 git 同一文件?

**风险**: **高** (核心阻塞)
- 当前 worktree 单目录: 2 个 builder 共享 `.worktrees/builder` → 两个 Claude 同时写 `coordinator.sh` 直接互踩
- git 不能保证 mid-write 一致性, 一个 builder 中途 git add 另一个 builder 半成品
**缓解**: 必须 per-builder worktree (`.worktrees/builder-1`, `.worktrees/builder-2`), 各自独立 branch, sprint 终态时 evaluator 决定哪个 branch 合并到 main
**改造量**: `lib/worktree.sh` ~30 行 (加 builder_idx 参数), `pane-launcher.sh` 启动时传递 idx

### Q2: worktree 隔离能否支持 N 并发?

**可行性**: 是, 但需要重构
- git worktree 本身支持 N 并行 (一个 repo, 多个 worktree, 各 checkout 不同 branch)
- 当前实现复用单 worktree (line 25 `if [[ -d "$worktree_dir" ]] && grep -q ...`) → 多 builder 会拿到同一目录
- 改造后: `.worktrees/builder-${idx}` 各自隔离, 主仓库通过 `git fetch <worktree>/<branch>` 合并
**资源代价**: 每个 worktree 完整 checkout, ThunderOMLX 大约 ~500 MB × 3 = 1.5 GB 磁盘 (可接受)
**清理复杂度**: sprint 终态时 cleanup_builder_worktree 要按 idx 清, 不能误清其他 builder

### Q3: watchdog 多 builder respawn 管理?

**风险**: 中
- `PERSONA_PANES` 当前是平面 dict, 加 [4]=builder-2 / [5]=builder-3 即可识别
- respawn 逻辑 (`coordinator-watchdog.sh:277`) 用 `pane-launcher.sh` 的 persona profile, 多 builder 共享 builder profile, 不需要新 profile
- **新坑**: rate-limit 状态 `PANE_RESTART_STATE` 是 per-pane-idx, 多 builder 各自计数即可, 但需要确认 rate-limit 文件不会因为多 idx 同时写出现 race (现有 reverse-tail awk 处理已经 OK)
**改造量**: ~5 行加 dict entry + 文档说明

### Q4: dispatch 负载均衡?

**核心改动**: `choose_builder_pane()` 从硬编码改为调度策略.

**策略 A (round-robin, 简单)**:
```bash
choose_builder_pane() {
  local last_idx_file="$HARNESS_DIR/.last-builder-idx"
  local last_idx=$(cat "$last_idx_file" 2>/dev/null || echo 0)
  local builders=("$PANE_BUILDER" "$PANE_BUILDER2")
  local n=${#builders[@]}
  local next=$(( (last_idx + 1) % n ))
  echo "$next" > "$last_idx_file"
  echo "${builders[$next]}"
}
```

**策略 B (load-aware, 利用 sprint-104819 P0 输出)**:
基于 PANE_CURRENT_SPRINT dict 找空闲 builder, 都忙就返回最早占用的 (LRU)
```bash
choose_builder_pane() {
  local builders=("1" "3")  # 候选 idx
  local oldest_idx="" oldest_ts=999999999999
  for idx in "${builders[@]}"; do
    local sid="${PANE_CURRENT_SPRINT[$idx]:-}"
    [[ -z "$sid" ]] && { echo "$SESSION_NAME:0.$idx"; return; }
    local ts="${PANE_ASSIGN_TS[$idx]:-0}"
    if (( ts < oldest_ts )); then oldest_ts=$ts; oldest_idx=$idx; fi
  done
  echo "$SESSION_NAME:0.$oldest_idx"   # 都忙: 返回最早的, dispatch 仍会 return 2
}
```

**推荐 B**: 与 sprint-104819 协同, 自动避免覆盖 bug. 改造量 ~30 行.

### Q5: 资源成本?

**实测估算 (M4 Max 64GB 参考)**:
- 单 Claude Code 实例: ~600 MB RSS + 几个 node 子进程 (~1 GB total)
- 3 builder + 1 planner + 1 evaluator + 1 architect = 6 实例 ≈ 6 GB
- M4 Max 64GB 可接受, 但 ThunderOMLX 推理时同时占大头 → 实际峰值 50+ GB
- **API quota**: glm-5.1 是 Zhipu 配额, 并行调用直接拉高 RPM. 当前单 builder ~10-30 req/min, 3 builder 同步飙到 90 req/min, 接近 Zhipu Tier-1 限速 (100 RPM)
- **opus quota**: planner + architect 已用 opus. 多 builder 用 glm-5.1 不挤 opus 配额, 安全

**结论**: 内存够, API 配额需要 Tier 升级或 throttling.

---

## 3. 实施路径 (分阶段)

### Phase X.1 — 数据结构改造 (1h)
- 修 `lib/worktree.sh` 加 builder_idx 参数, 路径变 `.worktrees/builder-${idx}`
- 修 `coordinator.sh` PANE_BUILDER 改成数组 `PANE_BUILDERS=(0.1 0.3 0.4)`
- 修 `coordinator-watchdog.sh` PERSONA_PANES 加 [4]/[5] entries

### Phase X.2 — session 物理布局 (45 min)
- `session.sh` split-window 加 2 个 pane (0.4, 0.5)
- 调整 layout 让 6 pane 都可见 (推荐 tiled / main-vertical 布局)
- `pane-launcher.sh` 接受 builder-2/builder-3 persona alias, 复用 builder profile

### Phase X.3 — 调度器 (1.5h)
- 实现策略 B load-aware `choose_builder_pane()`
- 与 sprint-104819 PANE_CURRENT_SPRINT 集成
- 加配置 `~/.solar/harness/.builder-count` 控制 1/2/3 (默认 1, 渐进上线)

### Phase X.4 — git 合并策略 (2h)
- 设计: 每 builder 独立 branch, sprint passed 时 evaluator 触发 merge
- 冲突处理: 自动 merge 失败 → 触发 needs_human_review
- handoff.md 必须含 `branch: harness-builder-${idx}-${ts}` 字段

### Phase X.5 — 端到端测试 (1.5h)
- 同时启 3 个 sprint, 验证 3 builder 各自独立
- 验证 git 历史无冲突 (sprint 间 file 不重叠)
- 故意触发冲突场景 (2 builder 改同一文件) → 验证 evaluator 报告 needs_human

**总预算**: ~6h 30min, 拆 3 个 sprint 推进:
- sprint X.1+X.2: 数据结构 + session 物理 (~2h)
- sprint X.3: 调度器 (~1.5h)
- sprint X.4+X.5: 合并 + 测试 (~3h 30min)

---

## 4. 风险与权衡

| # | 风险 | 严重度 | 缓解 |
|---|------|--------|------|
| R1 | 2 builder 改同一文件 (e.g. coordinator.sh) → git merge 冲突地狱 | **高** | sprint 调度时按 "影响范围" 分组, 同文件 sprint 排队同 builder, 跨文件 sprint 才并行 |
| R2 | API quota 飙升触发 Zhipu 限速 → 全线慢 | 中 | 限并发数 ≤ 2, 加 token bucket per-builder; 监控 ledger.jsonl |
| R3 | tmux 6 pane 视觉拥挤, 监护人盯不过来 | 低 | 默认折叠 builder-2/3, 用 dashboard 提供文字摘要 |
| R4 | watchdog 同时 respawn 多 builder 触发熔断 | 中 | rate-limit 已 per-pane, 多 builder 各自有 N=3/5min 限制 |
| R5 | 对话历史/记忆: 3 builder 各自不知道对方在干什么 | 中 | 每 builder dispatch 时附 "其他 builder 当前任务摘要" 作 context |

---

## 5. 推荐结论

**短期 (Phase A, 当前)**: ❌ **不建议** 立即开多 builder
- 当前 dispatch 覆盖 bug 还没修 (sprint-104819 还没合)
- worktree 单目录改造未完成
- 没有调度器, 只有硬编码

**中期 (Phase A.3+, 1-2 周后)**: ✅ **建议 2 builder 起步**
- 前置: sprint-104819 (dispatch 修) 合入 + sprint-102743 (scanner 修) 合入
- 第一阶段开 2 builder (pane 0.1 + 0.3 复用 architect 闲时), 不开 6 pane
- 用 load-aware 策略 B + 文件影响分组防止冲突

**长期 (Phase B+, 1 个月后)**: 🟡 **审慎扩到 3 builder**
- 需要 git 合并自动化 (X.4) + 配额管理
- 需要监护人确认监控 dashboard 能跟上

---

## 6. 推荐 sprint 拆分

| Sprint | 范围 | 时间 | 依赖 |
|--------|------|------|------|
| **multi-builder-S1** | Phase X.1 + X.2: worktree per-idx + session 6 pane | 2h | sprint-104819 合入 |
| **multi-builder-S2** | Phase X.3: load-aware 调度器 | 1.5h | S1 + sprint-102743 |
| **multi-builder-S3** | Phase X.4: git 合并策略 | 2h | S2 |
| **multi-builder-S4** | Phase X.5: 端到端测试 + 文档 | 1.5h | S3 |

**第一里程碑** (S1+S2 完成) 可解锁: 2 个 sprint 真并行, builder 利用率提升 ~80%.

---

**完成**: 调研 ~190 行 (≤200 ✓). 现状 / 5 问答 / 实施路径 / 风险 / 明确建议结论.
