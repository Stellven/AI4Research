# BUG5 Root Cause: handle_passed 运行时补偿从未执行

日期: 2026-04-20
Sprint: sprint-20260420-195648

## 症状

coordinator.sh 运行 13+ 小时, 3766+ 次轮询, `[heal]` 日志出现 0 次。
`loop_count % 30` 分支内的 handle_passed 扫描从未触发。
多个 passed sprint (113026, 191039, 等) 没有 .finalized。

## 排查过的 4 个假设

### 假设 1: loop_count shadowing ✗ 排除
- 搜索 coordinator.sh 只有一个 `local loop_count=0` (line 1458) 和一个 `((loop_count++))` (line 1460)
- 无其他变量名冲突

### 假设 2: log 函数失效 ✗ 排除
- `log()` 写入 `>&2`, `exec 2>>"$COORD_LOG"` 重定向到日志文件
- 日志中其他 `log` 输出正常 (状态变化、派发等)

### 假设 3: 后台 & 语法错误 ✗ 排除
- `(bash ... ) &` 在 line 1574-1575, `for` 循环在 line 1579
- `for` 循环在 `( ... ) &` 之后, 不在子 shell 内
- `bash -n coordinator.sh` 无语法错误 (line 882 是假阳性)

### 假设 4: 不可达分支 ✗ 排除
- `(( loop_count % 30 == 0 ))` 语法正确
- `loop_count` 从 0 开始递增, 每次循环 +1
- 3766 次轮询应该触发 125 次

### ✅ 根因: 正在运行的进程加载的是旧代码

**证据**:
1. 协调器进程 PID 1582 启动于 `2026-04-19 14:48:04 UTC`
   - 日志首行: `[协调器] 协调器启动，初始状态: sprint-20260419-223020:active`
2. `% 30` handle_passed 扫描代码是 Sprint `20260420-113026` (2026-04-20) 添加的
3. `coordinator.sh` 最后修改 `2026-04-20 19:17 UTC` — 进程启动后 28 小时
4. bash 脚本在进程启动时一次性读入内存, 之后修改磁盘文件不影响已运行的进程
5. `[boost]` capability 日志只出现一次 (启动时), 之后从未出现 — 证明 `% 30` 分支用的旧代码

**结论**: 所有 Sprint 20260420-* 的 coordinator.sh 改动 (handle_passed 扫描、detect_stuck_state、per-spring dict) 只存在于磁盘, 不在运行的进程中。需要重启协调器加载新代码。

## 修复

1. 重启协调器: `bash solar-harness.sh stop && bash solar-harness.sh start`
2. 验证新进程加载了最新代码 (md5 记录)
3. 等 5-10 分钟, 观察 `[probe]` 和 `[heal]` 日志

## 预防同类

1. coordinator 启动时 log 文件 md5, 方便对比磁盘版本
2. 关键长期分支 (mod10/mod30) 加永久低频 PROBE log
3. 修改 coordinator.sh 后提醒用户重启: 在 dispatch 末尾加 "coordinator.sh 已修改, 需要重启"
