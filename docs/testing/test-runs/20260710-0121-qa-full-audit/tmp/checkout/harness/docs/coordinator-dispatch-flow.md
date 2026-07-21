# Coordinator Dispatch Flow

更新日期: 2026-05-02

## 目标

这份文档记录 `coordinator.sh` 当前的派发护栏，重点覆盖 round-N+1 修复路径和 tmux thinking 解锁流程。

## 核心原则

1. 不假设 pane 空闲。
2. thinking 态优先 `C-c` 解锁。
3. 派发后必须校验指令真的进了 pane。
4. 失败必须落事件，不允许静默吞掉。
5. round 2+ 不再回退到“先写计划”。

## 派发前状态机

`dispatch_to_pane()` 现在先走以下判断：

1. `is_pane_present()` 校验 pane 还存在。
2. `wait_for_dispatch_window()` 读取 `capture-pane | tail -3`。
3. 命中 thinking 标记时发送 `C-c`，等待 1.5s 再重试。
4. 命中 idle prompt `❯ ` 时才允许发送命令。
5. 超时后写 `dispatch_failed` 事件。

## thinking 标记

当前识别以下标记：

- `✻ Baked`
- `✻ Worked`
- `✻ Vibing`
- `✻ Churned`
- `✶ Flummoxing`
- `·.* Vibing`

## 派发执行

派发正文仍然是短指令：

```bash
读取并执行 ~/.solar/harness/sprints/<sid>.dispatch.md
```

但发送流程变成：

1. `Escape Escape`
2. `C-u`
3. `/clear`
4. `Enter`
5. 再发送短指令
6. `Enter`
7. 抓取 pane 尾部校验是否包含 dispatch 文件名

## 重试策略

- 最多 3 次
- 每次失败都先 `C-c` + `Escape` + `C-u`
- 3 次后写 `dispatch_failed`

## planner loud notice

`check_planner_notice()` 不再直接相信 `.planner-last-notice` 第二列。

现在会：

1. 从第三列拿 `sid`
2. 优先读 `<sid>.eval.json` 的 `verdict`
3. 没有 eval.json 时回退到 `status.json`
4. sid 为空则直接跳过，不发假通知

## round-N+1 active 路径

当 sprint 再次进入 `active` 且 `round >= 2` 时：

1. 不再派发“先写计划”
2. 重新生成 dispatch
3. 注入最新合约摘要
4. 重申 builder 角色：直接修，不回计划模式
5. 写 `round_dispatched` 事件

## i18n / locale

文件顶部固定：

```bash
export LANG="en_US.UTF-8"
export LC_ALL="en_US.UTF-8"
```

目的是避免 macOS `cut: stdin: Illegal byte sequence`。

## postmortem / improvements

`check_auto_suggest()` 的 Python heredoc 已改成从环境变量读 `HARNESS_DIR` 和 `SPRINTS_DIR`，避免把字面量 `$HARNESS_DIR` 写进运行期路径。

## 最小回归

新增两个测试：

- `tests/test_dispatch_thinking.sh`
- `tests/test_round_n_plus_1_dispatch.sh`

它们目前是结构性回归，确保：

- thinking 护栏存在
- `dispatch_failed` 事件存在
- round-N+1 active 分支存在
- builder 角色重申没有被删掉

## B4: plan mode 死锁修复 (sprint-20260502-125501)

### 问题

当 sprint round-N FAIL → `handle_failed_review()` 把 status 改为 `approved` → `handle_approved()` 给 builder 发 dispatch → `dispatch_to_pane()` 的预解锁序列只有 Escape/C-u/clear，但 Claude Code plan mode 不响应 Escape，需要 Shift+Tab。

实测 sprint-20260502-083522 round-2 builder 卡 1h29min 烧 6.1k tokens。

### 修复

新增 `pane_is_plan_mode()` 检测函数，在 `dispatch_to_pane()` 预解锁序列中：

1. 检测 pane 末尾输出含 plan mode 特征
2. 如果是 plan mode → 发 `S-Tab` (Shift+Tab) 切到 edit mode
3. 二次确认：如果还在 plan mode 再发一次
4. 然后继续原有 Escape + /clear 序列

### 检测特征

```
plan mode | shift+tab | shift.tab.*edit
```

### send-keys 完整序列 (B4 后)

```
1. pane_is_plan_mode → 如果 true: S-Tab + sleep 0.5 + 二次确认
2. Escape × 2
3. C-u
4. /clear + Enter
5. C-u
6. 注入 prompt + Enter
7. 校验 dispatch 文件名出现在 pane 末尾
```

### 测试

- `tests/test-b4-plan-mode-guard.sh` — 5 项覆盖
