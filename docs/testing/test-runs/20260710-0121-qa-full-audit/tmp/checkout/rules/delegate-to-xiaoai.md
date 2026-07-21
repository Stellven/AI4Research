# Solar 铁律: 任务委派给小爱 (Delegate to XiaoAi)

> **来源: 2026-02-11 监护人指示**
> **核心: 日常事务丢给小爱，Solar 专注高价值工作**

## 小爱是谁

```
┌─────────────────────────────────────────────────────────────────┐
│  💝 小爱 (XiaoAi) - Solar 专属 AI 秘书                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  平台: OpenClaw                                                 │
│  模型: GLM-4.7 (便宜、快、中文好)                               │
│  定位: 秘书，不是老板；报告，不决策                             │
│                                                                 │
│  调用: openclaw agent --local --agent main --message "任务"     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 小爱的能力 (28 个技能)

| 类别 | 技能 | 说明 |
|------|------|------|
| 📧 邮件 | himalaya, email-monitor, email-to-calendar | 收发邮件、监控、转日历 |
| 📅 日历 | apple-calendar | 苹果日历管理 |
| 📝 笔记 | obsidian-daily, obsidian-direct | Obsidian 读写 |
| ✅ 任务 | things-mac, apple-reminders | Things 3 + 提醒事项 |
| 📨 消息 | imsg | iMessage/短信 |
| 🌐 浏览器 | fast-browser-use, browser-automation | 网页自动化 |
| 🤖 自动化 | clawdwork, agent-orchestrator, a2a-hub | 工作流编排 |
| 🧠 AI | gemini, summarize | Gemini 对话、内容摘要 |
| 📸 媒体 | camsnap, video-frames | 摄像头、视频处理 |
| 🌤️ 其他 | weather, github, session-logs, tmux | 天气、GitHub、日志 |

## 委派规则 (MUST)

**以下任务必须委派给小爱，Solar 不亲自干：**

| 任务类型 | 示例 | 委派 |
|----------|------|------|
| 邮件相关 | 查邮件、发邮件、邮件摘要 | ✅ 丢给小爱 |
| 日历相关 | 查日程、加日程、提醒我 | ✅ 丢给小爱 |
| 提醒/待办 | 加个提醒、看看 Things | ✅ 丢给小爱 |
| 笔记相关 | 写到 Obsidian、每日笔记 | ✅ 丢给小爱 |
| 消息相关 | 发短信、发 iMessage | ✅ 丢给小爱 |
| 网页抓取 | 帮我看看这个网页、填个表 | ✅ 丢给小爱 |
| 信息查询 | 查天气、总结这个链接 | ✅ 丢给小爱 |
| 架构设计 | 设计系统、写代码 | ❌ Solar 自己干 |
| 复杂分析 | 深度研究、多专家会审 | ❌ Solar 自己干 |

## 调用方式

```bash
# 直接调用
openclaw agent --local --agent main --message "帮我查一下今天的邮件"

# 后台运行
openclaw agent --local --agent main --message "监控邮件，有新邮件告诉我" &
```

## Solar 的分工

```
┌─────────────────────────────────────────────────────────────────┐
│                      Solar 生态分工                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  👔 监护人 (昊哥)                                               │
│     └─ 战略决策、审批、说"批准"                                 │
│                                                                 │
│  🧠 Solar (Claude Opus)                                         │
│     └─ 高价值工作: 架构设计、代码开发、深度分析、牛马管理       │
│                                                                 │
│  💝 小爱 (OpenClaw + GLM)                                       │
│     └─ 日常事务: 邮件、日历、提醒、笔记、消息、网页             │
│                                                                 │
│  🐂 牛马 (Gemini/DeepSeek/GLM)                                  │
│     └─ 具体执行: 编码、测试、分析、文档                         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 邮件路由规则 (2026-02-11 新增)

```
┌─────────────────────────────────────────────────────────────────┐
│  📧 邮件路由规则 (监护人亲授)                                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Solar 可以监控邮件，但需要按关键词路由：                       │
│                                                                 │
│  邮件主题/内容包含 "小爱"                                       │
│    → ❌ Solar 忽略                                              │
│    → ✅ 小爱处理 (通过 launchd 后台监控)                        │
│                                                                 │
│  其他邮件                                                       │
│    → ✅ Solar 可以处理                                          │
│                                                                 │
│  路由逻辑:                                                      │
│  if "小爱" in email.subject or "小爱" in email.body:            │
│      return "小爱的活，Solar 忽略"                              │
│  else:                                                          │
│      return "Solar 可以处理"                                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 小爱后台监控配置

- **服务**: `com.solar.xiaoai.email-monitor`
- **间隔**: 每 2 分钟
- **日志**: `/tmp/xiaoai-email-monitor.log`
- **错误**: `/tmp/xiaoai-email-monitor.err`

```bash
# 启动服务
launchctl load ~/Library/LaunchAgents/com.solar.xiaoai.email-monitor.plist
launchctl start com.solar.xiaoai.email-monitor

# 查看日志
tail -f /tmp/xiaoai-email-monitor.log

# 停止服务
launchctl stop com.solar.xiaoai.email-monitor
launchctl unload ~/Library/LaunchAgents/com.solar.xiaoai.email-monitor.plist
```

## 铁律总结

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   💝 任务委派小爱铁律                                           │
│                                                                 │
│   1. 日常事务 → 丢给小爱 (MUST)                                 │
│   2. 邮件/日历/提醒/笔记/消息 → 小爱的活 (MUST)                 │
│   3. 网页抓取/信息查询 → 小爱更快更便宜 (SHOULD)                │
│   4. 架构/代码/深度分析 → Solar 自己干 (MUST)                   │
│                                                                 │
│   Solar 专注高价值，小爱处理日常                                │
│   各司其职，效率最大化                                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

*Delegate to XiaoAi Rule v1.0*
*建立于: 2026-02-11*
*监护人指示: 有任务就丢给小爱*
