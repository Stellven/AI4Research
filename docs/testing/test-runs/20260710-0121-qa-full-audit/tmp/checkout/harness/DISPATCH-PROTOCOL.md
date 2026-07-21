# Dispatch Protocol — Bug 根因与修复方案

Sprint: sprint-20260417-213037
日期: 2026-04-17

## Bug 1: send-keys 吞键

### 根因
`dispatch_to_pane()` 使用 `tmux send-keys "$cmd" Enter` 一口气发送文本和回车。Claude Code CLI 内部有输入缓冲区，连发 text+Enter 超过缓冲处理速度时，Enter 被吞掉，导致指令停留在输入框未提交。

### 复现
```bash
tmux send-keys -t solar-harness:0.1 "读取并执行 /path/to/dispatch.md" Enter
# Claude Code CLI 输入框显示文本但未执行
```

### 修复
```bash
tmux send-keys -t "$pane" "$short_cmd" 2>/dev/null
sleep 0.8  # 等待 CLI 就绪
tmux send-keys -t "$pane" Enter 2>/dev/null
```
- 覆盖: 所有 handle_* 统一走 `dispatch_to_pane()` 入口
- 验证: `grep -c 'D1: send-keys' coordinator.sh`

## Bug 2: mtime 目录级检测漏检

### 根因
macOS APFS 文件系统行为: 修改文件**内容** (echo/python写status.json) **不更新父目录的 mtime**。只有创建/删除文件才会更新目录 mtime。协调器依赖 `stat -f %m "$SPRINTS_DIR"` 检测变化，导致内容修改被漏检。

### 复现
```bash
stat -f %m ~/.solar/harness/sprints/  # 记录值 X
python3 -c "d=json.load(open('sprint.json')); d['status']='active'; json.dump(d,open('sprint.json','w'))"
stat -f %m ~/.solar/harness/sprints/  # 值仍为 X, 未变!
```

### 修复
```bash
# 扫描所有 sprint-*.status.json 取 max(mtime)
local max_file_mtime=0
for f in "$SPRINTS_DIR"/sprint-*.status.json; do
  [[ -f "$f" ]] || continue
  local fmtime=$(stat -f %m "$f" 2>/dev/null || echo 0)
  (( fmtime > max_file_mtime )) && max_file_mtime=$fmtime
done
```
- 性能: 24 文件 ~24ms/轮, 可接受
- 验证: 修改任意 status.json 后观察协调器日志 "文件级 mtime 变化"

## Bug 3: pane 忙时吞键

### 根因
目标 pane 仍在 Claude Code CLI 思考/生成中时 (显示 `✳ Cogitated for...` / `✶ Cooked for...`), tmux send-keys 发送的文本被 CLI 吞掉，不进入输入缓冲区。

### 复现
```bash
# pane 0.1 显示 "✶ Cogitated for 15s..." 时
tmux send-keys -t solar-harness:0.1 "test" Enter
# 指令丢失, pane 继续 cogitate
```

### 修复
```bash
# 派发前 capture-pane 检查忙碌标记
local busy_patterns='✳|✶|⏺|Cogitated|Cooked|Propagating|Worked for'
local wait_count=0 max_waits=12  # 120s
while (( wait_count < max_waits )); do
  pane_output=$(tmux capture-pane -t "$pane" -p | tail -3)
  if echo "$pane_output" | grep -qE "$busy_patterns"; then
    sleep 10; ((wait_count++))
  else break; fi
done
```
- 超时处理: 记录 `DISPATCH_DEFERRED` 事件, 返回失败
- 验证: 手动在 pane 触发长时间操作后派发

## 测试

```bash
bash ~/.solar/harness/test-dispatch.sh [--skip-tmux-check]
```

---

## Codex Bridge 协同章节

Sprint: sprint-20260419-223020 | 日期: 2026-04-19

### 架构图

```
┌─────────────────────────────────────────────────────────┐
│                    tmux session                          │
│                                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │
│  │  pane 0  │  │  pane 1  │  │  pane 2  │  │ pane 3  │ │
│  │  规划者  │  │  建设者  │  │  审判官  │  │  codex  │ │
│  │ planner  │  │ builder  │  │evaluator │  │ bridge  │ │
│  └──────────┘  └──────────┘  └──────────┘  └─────────┘ │
│       │             │             │            │         │
│       └─────────────┴──────┬──────┘            │         │
│                            │                    │         │
│                    coordinator.sh              │         │
│                     call_codex()               │         │
│                            │                    │         │
│                            ▼                    │         │
│                  codex-bridge/inbox/*.req.md    │         │
│                            │                    │         │
│                            ▼                    ▼         │
│                    codex-bridge.sh (守护进程)             │
│                            │                              │
│                            ▼                              │
│                     codex exec -s read-only               │
│                            │                              │
│                            ▼                              │
│                  codex-bridge/outbox/*.res.md             │
└─────────────────────────────────────────────────────────┘
```

### 时序图: req → dispatch → res → forward

```
coordinator.sh          codex-bridge.sh         codex CLI
     │                        │                      │
     │  call_codex(S, prompt) │                      │
     │──► check budget        │                      │
     │──► check tier          │                      │
     │──► write inbox/*.req.md│                      │
     │                        │                      │
     │                        │◄── poll inbox        │
     │                        │    parse frontmatter │
     │                        │    check tier        │
     │                        │    check budget      │
     │                        │                      │
     │                        │──► codex exec ──────►│
     │                        │    (sandbox read-only│
     │                        │     non-interactive) │
     │                        │                      │
     │                        │◄── response ─────────│
     │                        │                      │
     │                        │──► write outbox/res  │
     │                        │──► append ledger     │
     │                        │──► consume budget    │
     │                        │──► mv req → processed│
     │                        │                      │
     │◄── poll outbox         │                      │
     │    read & rm res.md    │                      │
     │                        │                      │
     │  return result         │                      │
     │  (or BUDGET_EXCEEDED/  │                      │
     │   CIRCUIT_BREAKER_OPEN)│                      │
```

### 三级调用策略

| 级别 | 额度 | 触发 | 禁调 |
|------|------|------|------|
| S | 4000 tokens | 连续FAIL≥2根因/架构A vs B/复杂算法 | 代码风格/函数拆分/简单bug |
| A | 2000 tokens | 跨模块逻辑/疑难bug/合约sanity check | API用法/测试写法/配置项 |
| B | N/A | — | CRUD/格式化/命令执行/单测/简单脚本 |

### 预算熔断

```json
{
  "daily_call_limit": 30,
  "daily_token_limit": 20000,
  "hard_stop": true
}
```

超限 → `BUDGET_EXCEEDED` + macOS 通知 (Purr)

### 回退

```bash
solar-harness monitor   # 在独立 tmux window 打开旧 monitor
Ctrl-b n               # 切回 harness 主窗口
```

---

## 协调器启动三连锁修复

Sprint: sprint-20260420-082442
日期: 2026-04-20

### Bug 1: 僵尸 pidfile 阻止启动

**根因**: 协调器异常退出后 `.coordinator.pid` 残留，下次启动读到死 PID 直接退出，需手动删除。

**修复**: `run_coordinator()` 启动时 `kill -0` 验活，死 PID 自动清理并继续。

```bash
# coordinator.sh run_coordinator() 开头
if kill -0 "$old_pid" 2>/dev/null; then
  exit 1  # 真的在运行
fi
log "stale pidfile detected (PID=${old_pid} dead), removed"
rm -f "$pidfile"
```

### Bug 2: last_state 吞首派发

**根因**: `run_coordinator()` 启动时将当前 sprint 状态写入 `COORD_STATE`，导致主循环首次比较 `last_state == current_state`，跳过派发。

**修复**: 启动时 `rm -f "$COORD_STATE"`，不再写入中间态。首次循环检测到空→当前状态变化，正常触发派发。

### Bug 3: pidfile 所有权散乱

**根因**: monitor.sh、solar-harness.sh 各自预写 pidfile，coordinator 自己也写，三方竞争。

**修复**: pidfile 写入权统一归 coordinator.sh (`echo $$ > "$pidfile"`)，外部脚本只读取/删除。

### Bug 4: update-contract local 作用域错误

**根因**: `update-contract` case 分支内使用 `local` 关键字，但 case 不是函数，`local` 在顶层执行报错。

**修复**: 提取 `do_update_contract()` 函数，case 分支调用函数。

### coord-status 子命令

```bash
solar-harness coord-status
# 返回: {"running": true, "pid": 12345, "uptime_s": 3600, "stale_lock": false}
```

---

## 收官守护与幂等 handle_passed

Sprint: sprint-20260420-090726
日期: 2026-04-20

### Bug: get_latest_sprint_file 跳终态导致 handle_passed 永远不触发

**根因**: `get_latest_sprint_file()` 跳过 `passed/done/failed/eval_pass` 状态，导致 reviewing→passed 后 sprint 被踢出视野。主循环检测不到 passed 状态变化，handle_passed 永远不触发。

**修复**: 移除"跳过终态"逻辑，改为纯 mtime 排序 + id 非空过滤。防重复派发靠主循环 `last_state != current_state`。

### .finalized 幂等机制

```
handle_passed() 开头:
  if [[ -f "$SPRINTS_DIR/${sid}.finalized" ]]; then
    log "already finalized, skip: $sid"
    return 0
  fi
  # ... 执行收官逻辑 ...
  touch "$SPRINTS_DIR/${sid}.finalized"
  emit_event "$sid" "handle_passed_completed" ...
```

### 启动自愈流程

```
coordinator 启动
    │
    ▼
扫 sprint-*.status.json
    │
    ▼
找 status=passed 但无 .finalized 的 sprint
    │
    ├─ 有 → 补跑 handle_passed → 创建 .finalized → 发通知
    │
    └─ 无 → 正常启动
    │
    ▼
主循环开始
```

### clean-corrupted 僵尸清理

```bash
solar-harness clean-corrupted          # dry-run 列表
solar-harness clean-corrupted --apply  # 移到 .quarantine/ (不删)
```

隔离文件记录在 `sprints/.quarantine/MANIFEST.md`。

---

## 中间状态卡死与自愈

Sprint: sprint-20260420-113026
日期: 2026-04-20

### Bug A: plan-review 卡死

**根因**: builder 写 plan → status=planning → coordinator 派发给 evaluator 审批。evaluator REJECT 后 dispatch 指令让它用 `python3 -c` 手动改 status=active，但 evaluator 只追加了 `plan_reviewed` 事件到 history，**漏改 status**。coordinator 看 status 仍为 planning，认为无变化，不再派发 → 卡死。

**代码位置**: coordinator.sh handle_planning() — APPROVE/REJECT dispatch 用 python3 subshell

**修复**: 
1. 新增 `solar-harness plan-verdict <sid> approve|reject [reason]` 原子命令 — status + history + emit_event 三者同步更新 (tempfile+rename)
2. handle_planning dispatch 改用 `bash solar-harness.sh plan-verdict` 替代 python3 subshell
3. handle_planning 开头加自愈: 扫 plan.md 末尾 `APPROVE|REJECT` 标记，如 status 仍为 planning 则自动 plan-verdict 补偿

### Bug B: handle_passed 漏触发

**根因**: coordinator 只在启动时扫 passed 但无 .finalized 的 sprint 补跑 handle_passed。运行期间如果 coordinator 因 mtime 竞态漏检 reviewing→passed 变化，passed sprint 永远不会被 handle_passed 处理。

**修复**: 主循环每 30 次迭代 (~5min) 扫所有 status=passed 但无 .finalized 的 sprint，自动补跑 handle_passed。

### Bug C: last_state 只记单个 sprint

**根因**: `last_state="${sid}:${st}"` 只记录最新一个 sprint 的状态。如果 A sprint 在 reviewing, B sprint 同时变 active → last_state 被覆盖为 B:active → A 的 reviewing→passed 被漏掉。

**修复**: save_state/load_last_state 改为 per-sprint dict 格式 `"sid:st|sid:st|..."`。新增 `check_state_changed(sid, st)` 函数从 dict 中提取对应 sid 的旧状态比较。

### 通用 detect_stuck_state()

扫 events.jsonl 最近 100 行，检测 plan_reviewed/eval_completed 事件超过 60 秒但 status 未推进，自动补偿:
- planning + plan_reviewed >60s → 触发 handle_planning (含自愈逻辑)
- reviewing + eval_completed >60s → 触发 handle_reviewing

### 新增子命令

| 命令 | 用途 | 原子性 |
|------|------|--------|
| `solar-harness plan-verdict <sid> approve\|reject [reason]` | 替代 python3 subshell 审批计划 | tempfile+rename |
| `solar-harness eval-verdict <sid> pass\|fail [reason]` | 替代 python3 subshell 评审判定 | tempfile+rename |
| `solar-harness verify-events <sid>` | 事件一致性对账 | — |

### 可推广模式

此修复模式可推广到其他中间状态:
1. **原子命令替代 subshell** — 任何涉及 status+history+event 三者的更新都应走原子命令
2. **自愈检测** — handle_* 开头检查外部标记 (plan.md 末尾审批标记、events.jsonl 事件)
3. **运行时补偿** — 主循环周期性扫漏处理的终态 sprint
4. **per-sprint 状态追踪** — 多 sprint 并发时不丢任何一方的状态变化

### Round 2+ handoff 史料残缺

Sprint: sprint-20260420-191039 | 日期: 2026-04-20

**根因**: handle_approved/handle_failed_review 的 dispatch 指令让建设者用 python3 subshell 手动改 status=reviewing, 建设者只改了 status 但没追加 history `implementation_completed` 事件也没 emit_event `handoff_submitted`, 导致 events.jsonl 和 history 残缺。sprint-20260420-113026 的 round 2 就是案例 — history 跳过了 round 2 的 implementation_completed。

**与 plan-verdict/eval-verdict 同构**: 三命令现在成套 — 都替代 python3 subshell, 都做 status+history+event 三件原子更新:
- `plan-verdict` — 审判官审批计划 (planning→approved/active)
- `handoff-submit` — 建设者提交实现 (approved→reviewing)
- `eval-verdict` — 审判官评审判定 (reviewing→passed/failed_review)

**修复**:
1. 新增 `solar-harness handoff-submit <sid>` 原子命令 — tempfile+rename 更新 status+round+history+last_handoff_mtime, emit_event handoff_submitted
2. 幂等: 记录 last_handoff_mtime, 同一 handoff.md 不重复 round++
3. handle_approved + handle_failed_review 两处 dispatch 指令更新为 `bash solar-harness.sh handoff-submit ${sid}`
4. verify-events 增加每轮 completeness 检查: 缺 implementation_completed 或 eval_completed 打印 WARN + 补齐建议

**新增子命令**

| 命令 | 用途 | 原子性 |
|------|------|--------|
| `solar-harness handoff-submit <sid>` | 建设者提交实现 (替代 python3 subshell) | tempfile+rename + mtime 幂等 |

**三命令成套规范**

| 命令 | 触发者 | 状态变化 | history 事件 | emit_event |
|------|--------|---------|-------------|------------|
| plan-verdict | 审判官 | planning→approved/active | plan_reviewed | plan_verdict |
| handoff-submit | 建设者 | approved→reviewing | implementation_completed | handoff_submitted |
| eval-verdict | 审判官 | reviewing→passed/failed_review | eval_completed | eval_passed/eval_failed |

## bug #9 僵尸 pidfile 回归修复

**日期**: 2026-04-22
**Sprint**: sprint-20260422-111527

### 根因

`run_coordinator()` 的 pidfile 互斥检查只在**新启动时**通过 `kill -0` 验活。当协调器被 `kill -9` 杀掉时，`trap EXIT` 不捕获 SIGKILL，pidfile 残留死 PID。若另一个实例已绕过检查启动 (竞态或 nohup)，pidfile 永远指向旧死 PID，与实际进程脱节。bug #6 (Sprint 20260420-082442) 的 kill -0 自愈只在启动流程执行，无法检测**多实例共存**场景。

### 修复方案

在 `kill -0` 失败 (PID 死) 后，增加 `ps aux` 交叉验证:

```bash
# Step 1: kill -0 验活 (同 bug #6)
# Step 2: kill -0 失败 → ps 交叉验证
real_pids=$(ps aux | grep '[b]ash.*coordinator\.sh' | awk '{print $2}')
if [[ -n "$real_pids" ]]; then
  # 活实例存在 → 自愈 pidfile + 拒绝启动 + stdout 提示
  echo "$real_pid" > "$pidfile"
  echo "⚠ coordinator 已在运行 (PID=$real_pid), pidfile 已自愈修正" >&2
  exit 1
fi
# Step 3: 无活实例 → 清锁
```

### 关键改进

1. **ps 交叉验证**: `kill -0` 失败后用 `ps aux` 二次确认，防止多实例共存
2. **stdout 提示**: 检测到已有实例时向 stderr 输出明确提示，不只写 log 文件
3. **自愈 pidfile**: 发现活实例但 pidfile 错位时，自动修正指向真实 PID
4. **grep trick**: `[b]ash.*coordinator\.sh` 防止匹配到 grep 自身

### 如何避免同类

循环内长期不执行的分支应有 PROBE 日志定期验证可达性。pidfile 检查是安全关键路径，每次启动都必须验证实际进程状态，不能只依赖文件锁。

---

## Agent-Skills 工业级模式集成 (sprint-20260425-113751)

### 5 段式合约模板 (contract-template-v2.md)

新 sprint 合约包含 5 个必须段落:

1. **Frontmatter** — name / description / triggers (YAML 格式)
2. **When to Use** — 使用/不使用各 ≥3 条
3. **Process** — 步骤化流程
4. **Red Flags** — 禁止模式 ≥3 条 (默认: 无 mock/无硬编码密钥/无 /tmp 产出)
5. **Verification Gates** — 每条 Done 含 HTML 注释格式的 verify 块

verify 块格式:
```markdown
- [ ] D1: 描述
  <!-- verify: cmd="命令" expected_exit=0 output_pattern="regex" -->
```

### 7 阶段 Sprint 生命周期

| 阶段 | entry_gate |
|------|-----------|
| spec | (always pass) |
| plan | Contract Done 已填写非 placeholder |
| build | plan.md 存在 |
| test | handoff.md 存在 |
| review | eval.md 存在 |
| ship | eval verdict=PASS |

状态机: `~/.solar/harness/lib/phase-state-machine.sh`
- `phase-state-machine.sh transition <sid> <from> <to>`
- `phase-state-machine.sh current <sid>`
- status.json 新增 `phase` 字段, 旧 sprint 默认 `legacy`

### SDD-CACHE (solar-cache)

Origin-validated 缓存, 禁止 TTL:
- HTTP: curl -I + If-None-Match → 304=hit, 200=miss
- 本地 SQLite: mtime + sha256 对比
- CLI: `solar-cache get/put/validate/stats`
- 存储: `~/.solar/harness/cache/` (权限 700)

### Verification Gates (solar-verify)

自动执行合约 Done 中的 verify 块:
- `solar-verify <sid>` — 跑所有 verify gates
- `solar-verify <sid> D1` — 只跑 D1
- `solar-verify <sid> --red-flags` — 检查 Red Flags

### 迁移工具适配

- `solar-harness migrate export --include-templates` — 打包新模板+CLI+lib
- `solar-harness migrate export --include-cache` — 打包 cache 元数据
- import 自动 chmod +x 新脚本

---

## 运行时补偿失效根因 (Bug #5)

Sprint: sprint-20260420-195648 | 日期: 2026-04-20

### 症状

coordinator.sh 运行 13+ 小时, 3766+ 次轮询, `[heal]` 日志 0 次。`loop_count % 30` 分支内的 handle_passed 扫描从未触发。多个 passed sprint 没有 .finalized, Mission 归档/KPI/通知全跳过。

### 排查假设与结果

| # | 假设 | 结果 | 验证方法 |
|---|------|------|----------|
| 1 | loop_count shadowing | ✗ 排除 | 搜索只有一处定义一处自增 |
| 2 | log 函数失效 | ✗ 排除 | 其他 log 正常输出 |
| 3 | 后台 & 语法错误 | ✗ 排除 | `bash -n` 无语法错误 |
| 4 | 不可达分支 | ✗ 排除 | 3766 次应触发 125 次 |

### 根因

**正在运行的协调器进程加载的是旧代码。** bash 脚本在进程启动时一次性读入内存, 之后磁盘文件的修改不影响已运行的进程。

证据:
1. 协调器 PID 启动于 2026-04-19 14:48 UTC
2. `% 30` handle_passed 扫描代码是 2026-04-20 添加的
3. `coordinator.sh` 最后修改在进程启动后 28 小时
4. `[boost]` capability 日志只出现一次 (启动时)

### 修复

1. 重启协调器加载新代码
2. 启动时 log coordinator.sh 的 md5, 方便对比磁盘版本
3. 关键长期分支 (mod10/mod30) 加永久低频 PROBE log

### 预防同类

1. 修改 coordinator.sh 后必须重启协调器 (`solar-harness stop && solar-harness start`)
2. 协调器启动时 log 文件 md5, 方便对比是否需要重启
3. 关键长期分支加 PROBE 日志 (每 5 分钟一行, 每天 288 行, 可接受)
4. dispatch 末尾如涉及 coordinator.sh 修改, 加 "需要重启" 提醒
