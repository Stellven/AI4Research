# Solar Demo 任务

> 两个 Demo 充分展示 Solar 核心能力

## Demo 1: 智能监控系统 (能力演进)

**触发词**: `帮我监控 Hacker News 热门话题，每小时更新`

### 展示能力

| 能力 | 触发点 |
|------|--------|
| 能力演进 | 无现成 Skill → 自动创建 `hn-monitor` |
| MCP 集成 | 自动发现/创建 WebFetch MCP |
| 五阶段流程 | P1研究→P2设计→P3实现→P4验证→P5收尾 |
| Agent 协作 | Researcher→Architect→Coder→Tester→Docs |
| IaST | 数据写入 sys_skills, evo_* 表 |
| TVS 渲染 | 监控面板实时展示 |
| 自我学习 | 记录执行效果，优化参数 |

### 预期流程

```
用户: 帮我监控 Hacker News 热门话题，每小时更新

┌─ 🔬 Researcher ────────────────────────────────────────────────┐
│ 检测到新需求: HN 监控                                           │
│ 现有能力匹配: ❌ 无                                             │
│ 决策: 触发能力演进                                              │
└─────────────────────────────────────────────────────────────────┘

┌─ 🏗️ Architect ─────────────────────────────────────────────────┐
│ 设计方案:                                                       │
│ 1. 创建 /hn-monitor Skill                                       │
│ 2. 使用 WebFetch 抓取 HN API                                    │
│ 3. 定时任务: cron 或 launchd                                    │
│ 4. 数据存储: ~/.solar/solar.db                                  │
│ 5. 展示: Solar Web Dashboard                                    │
└─────────────────────────────────────────────────────────────────┘

┌─ 💻 Coder ─────────────────────────────────────────────────────┐
│ 创建文件:                                                       │
│ • ~/.claude/skills/hn-monitor/SKILL.md                         │
│ • ~/.claude/skills/hn-monitor/fetch.ts                         │
│ • ~/Library/LaunchAgents/com.solar.hn-monitor.plist            │
└─────────────────────────────────────────────────────────────────┘

┌─ 🧪 Tester ────────────────────────────────────────────────────┐
│ 验证:                                                           │
│ ✓ Skill 可调用                                                  │
│ ✓ 数据正确写入 DB                                               │
│ ✓ Dashboard 正确显示                                            │
└─────────────────────────────────────────────────────────────────┘

┌─ 📖 Docs ──────────────────────────────────────────────────────┐
│ 生成文档:                                                       │
│ • SKILL.md 使用说明                                             │
│ • skills-index.md 更新                                          │
└─────────────────────────────────────────────────────────────────┘

────────────────────────────────────────────────────────────────────
Powered by TVS v0.4.0 · Style: zenwhite.terminal
可选风格: monolith | aurora | cyberpunk | liquid.dark | swiss ...
切换风格: /theme <style> | 查看所有: /theme list
```

---

## Demo 2: 智能代码审计 (自主 Agent)

**触发词**: `审计 ThunderDuck 项目的内存安全，生成报告`

### 展示能力

| 能力 | 触发点 |
|------|--------|
| Agent 自主创建 | 无 MemorySafetyAgent → 动态生成 |
| 多 Agent 协作 | Researcher + Reviewer + Reporter |
| 深度分析 | AST 解析 + 模式匹配 |
| TVS 报告 | 多页专业报告渲染 |
| 自我演进 | 学习新的审计规则 |
| IaST | 审计结果写入系统表 |

### 预期流程

```
用户: 审计 ThunderDuck 项目的内存安全，生成报告

┌─ 🔬 Researcher ────────────────────────────────────────────────┐
│ 任务分析:                                                       │
│ • 目标: C++ 内存安全审计                                        │
│ • 范围: ThunderDuck 项目                                        │
│ • 需要: 专门的内存安全检查能力                                  │
│                                                                 │
│ 现有 Agent 匹配:                                                │
│ • Reviewer: 通用代码审查 (部分匹配)                             │
│ • Guard: 安全规范检查 (部分匹配)                                │
│                                                                 │
│ 决策: 动态组合 + 增强规则                                       │
└─────────────────────────────────────────────────────────────────┘

┌─ 🏗️ Architect ─────────────────────────────────────────────────┐
│ 审计架构:                                                       │
│                                                                 │
│ ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│ │ StaticScan  │→ │ PatternMatch│→ │ RiskScore   │              │
│ │ (clang-tidy)│  │ (自定义规则)│  │ (ML 评分)   │              │
│ └─────────────┘  └─────────────┘  └─────────────┘              │
│        │                │                │                      │
│        └────────────────┴────────────────┘                      │
│                         │                                       │
│                         ▼                                       │
│               ┌─────────────────┐                               │
│               │  Unified Report │                               │
│               └─────────────────┘                               │
│                                                                 │
│ 检查项:                                                         │
│ • 缓冲区溢出 (buffer overflow)                                  │
│ • 悬垂指针 (dangling pointer)                                   │
│ • 双重释放 (double free)                                        │
│ • 未初始化内存 (uninitialized memory)                           │
│ • 内存泄漏 (memory leak)                                        │
└─────────────────────────────────────────────────────────────────┘

┌─ 👁️ Reviewer (增强模式) ───────────────────────────────────────┐
│ 扫描中...                                                       │
│                                                                 │
│ 进度: ████████████░░░░ 75%                                      │
│                                                                 │
│ 发现问题:                                                       │
│ • [HIGH] src/operators/hash_join.cpp:234 - 潜在缓冲区溢出       │
│ • [MED]  src/memory/pool.cpp:89 - 未检查 malloc 返回值          │
│ • [LOW]  include/types.h:45 - 建议使用 std::unique_ptr          │
└─────────────────────────────────────────────────────────────────┘

┌─ 📝 Reporter ──────────────────────────────────────────────────┐
│ 生成报告: memory-safety-audit-2026-01-31.md                     │
│                                                                 │
│ 报告结构:                                                       │
│ 1. 执行摘要                                                     │
│ 2. 风险评分: 7.2/10                                             │
│ 3. 高危问题详情                                                 │
│ 4. 修复建议                                                     │
│ 5. 附录: 扫描配置                                               │
└─────────────────────────────────────────────────────────────────┘

────────────────────────────────────────────────────────────────────
Powered by TVS v0.4.0 · Style: zenwhite.terminal
可选风格: monolith | aurora | cyberpunk | liquid.dark | swiss ...
切换风格: /theme <style> | 查看所有: /theme list
```

---

## 运行 Demo

### Demo 1: HN 监控

```bash
# 在 Claude Code 中执行
帮我监控 Hacker News 热门话题，每小时更新
```

### Demo 2: 内存审计

```bash
# 在 Claude Code 中执行
审计 ThunderDuck 项目的内存安全，生成报告
```

---

## 核心能力对照表

| 能力 | Demo 1 | Demo 2 |
|------|--------|--------|
| 能力演进 (自动创建 Skill) | ✓ | - |
| Agent 动态组合 | - | ✓ |
| 五阶段流程 | ✓ | ✓ |
| 多 Agent 协作 | ✓ | ✓ |
| TVS 渲染 | ✓ | ✓ |
| IaST 系统表 | ✓ | ✓ |
| MCP 集成 | ✓ | - |
| 自我学习 | ✓ | ✓ |
| 定时任务 | ✓ | - |
| 代码分析 | - | ✓ |

---

## 亮点总结

1. **零配置启动**: 用户只说需求，系统自动判断
2. **能力演进**: 没有就造，越用越强
3. **Agent 协作**: 自动分工，并行执行
4. **全程可视**: TVS 实时展示每个阶段
5. **数据驱动**: 所有执行记录写入系统表
6. **自我优化**: 基于历史数据自动调参

---

## Orchestrator Dashboard 健康总览

`/orchestrator` 页面已支持健康总览卡片，默认展示：

1. 队列量（pending/deferred/queued）
2. 失败率（24h）
3. 重试中节点数（pending_retry/retrying）
4. 修复分支任务数（活跃）

增强能力：

1. 失败率（1h）
2. 队列最老等待时长（分钟）
3. 修复分支任务（24h）
4. 状态灯（GOOD/WARN/BAD）
5. 24h 小时级失败/完成趋势图
6. 一键导出健康 JSON

相关 API：

1. `GET /api/orchestrator/health-summary`
2. `GET /api/orchestrator/health-history?hours=24`
3. `GET /api/orchestrator/health-config`
4. `POST /api/orchestrator/health-config`
5. `GET /api/orchestrator/health-drilldown?type=failures|repairs&limit=20`
6. `GET /api/orchestrator/health-alerts?limit=50&includeResolved=0|1`
7. `POST /api/orchestrator/health-actions/retry`
8. `POST /api/orchestrator/health-actions/repair`

说明：

1. 健康阈值与巡检配置（包含快照保留天数、告警冷却、通知渠道）都存储在 `bl_orchestrator_health_config`。
2. 健康快照落库到 `bl_orchestrator_health_snapshots`，默认保留 30 天（可配置）。
3. 告警记录在 `bl_orchestrator_health_alerts`，支持面板展示与下钻联动。
4. 巡检告警可桥接通知渠道：
   - Email（`monitor.notifyEmailEnabled + monitor.notifyEmailTo`）
   - Telegram（`monitor.notifyTelegramEnabled + monitor.notifyTelegramChatId`）

---

## 故障排查

1. 健康面板一直显示 `N/A`
   - 检查 dashboard 服务：`bun run core/dashboard/server.ts`
   - 检查数据库是否存在：`~/.solar/solar.db`
2. “一键重试/一键创建修复任务”失败
   - 确认 daemon 在运行：`/tmp/solar.sock` 存在且可访问
   - 手动探活：`curl --unix-socket /tmp/solar.sock http://localhost/health`
3. 告警列表为空
   - 先触发一次 `GET /api/orchestrator/health-summary`（会落快照并评估告警）
   - 降低阈值后再次触发，验证是否生成告警
4. Telegram 通知不发送
   - 确认环境变量：`TELEGRAM_BOT_TOKEN`
   - 配置 `monitor.notifyTelegramEnabled=true` 且 `notifyTelegramChatId` 非空
5. Email 通知不发送
   - macOS 下优先走 Mail.app；请确认已配置可发送账号
   - 配置 `monitor.notifyEmailEnabled=true` 且 `notifyEmailTo` 非空
6. 快照膨胀
   - 调整 `monitor.snapshotRetentionDays`（默认 30）
   - 触发一次健康采样后会自动执行清理
