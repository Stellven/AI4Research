# Solar 铁律: 基础设施先体检

> **来源**: 2026-04-22 监护人当场抓摆烂 — harness 协调器故障，我从表象往下查了半天，根因是 bash 3.2 vs declare -A，一条 `bash --version` 就能定位
> **核心**: 基础设施故障排查，必须**先体检运行环境**，再查上层状态。自底向上，不是自顶向下

## 铁律定义

当问题涉及 **harness / 协调器 / 牛马链路 / tmux / MCP / Hook** 这类基础设施时，**第一步必须**是环境体检：

### 体检清单 (强制，按顺序)

| # | 检查项 | 命令 | Pass 标准 |
|---|--------|------|-----------|
| EC-1 | bash 版本 | `bash --version` + `/opt/homebrew/bin/bash --version` | 至少有一个 bash 4+ 可用 |
| EC-2 | 关键命令在 PATH | `which tmux claude python3 jq sqlite3` | 全部存在 |
| EC-3 | 关键脚本语法 | `bash -n coordinator.sh` | 退出码 0 |
| EC-4 | 关键目录可写 | `test -w ~/.solar/harness` | 可写 |
| EC-5 | 关键进程活性 | `pgrep -fa coordinator` + `ls .coordinator.pid` | pidfile 有 + 进程活 |
| EC-6 | shebang 与 bash 版本匹配 | `head -1 <script>` | #!/usr/bin/env bash 且脚本兼容宿主版本 |

### 执行顺序

```
故障报告到达 → EC-1 到 EC-6 逐项查 → 发现任一不通过 → 先修底层环境 → 再查上层状态
```

**禁止**: 在环境体检未完成前去猜测 tmux session 状态、协调器行为、业务逻辑 bug。

### 正反模式

```
❌ 错误: 看到 "tmux session 消失" → 查 tmux ls → 查 pidfile → 查日志 → 猜测是系统睡眠还是 SIGHUP
   (查了半小时，真因是 bash 3.2 语法报错，coordinator 从没起来过)

✅ 正确: 看到 "tmux session 消失" → 先跑 solar-harness doctor → 发现 bash 版本问题 → 修底层 → 再看上层
```

## 为什么自顶向下会摆烂

- 上层状态（session/pidfile/日志）是**结果**，不是**原因**
- 基础环境问题会让上层呈现各种假象（pidfile 不存在、日志不更新、进程找不到）
- 一条 `bash --version` 5 秒定位的根因，从表象挖可能要半小时且猜错方向

## 持久化到启动宣告

Solar 启动（触发词 "solar"）时，**启动宣告必须包含基础设施自检摘要**：

```
bash 版本: ✅ /opt/homebrew/bin/bash 5.2.x
tmux: ✅ in PATH
协调器 pidfile: ❌ 不存在 (需要 solar-harness doctor 诊断)
```

## 触发条件

| 关键词 | 立即执行 |
|--------|----------|
| harness 有问题 / 协调器挂了 / tmux 消失 / sprint 派不出去 / 牛马失联 | 第一条命令必须是 `solar-harness doctor` |
| 启动 Solar (触发词 solar) | 启动宣告附带环境自检摘要 |

## 禁止

- ❌ 从业务表象直接往下挖，跳过环境体检
- ❌ 把旧 MEMORY.md 的状态当作当前事实（记忆会过期）
- ❌ 报告故障时只给表象不给环境版本

---

*Infrastructure First Check Protocol v1.0*
*建立于: 2026-04-22*
*来源: 监护人抓现行 — bash 3.2 declare -A 故障，自顶向下摆烂诊断*
