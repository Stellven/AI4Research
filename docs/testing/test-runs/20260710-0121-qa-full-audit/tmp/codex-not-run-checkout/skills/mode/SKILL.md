---
name: mode
description: 切换工作模式 - 开发/办公/研究等
user-invocable: true
disable-model-invocation: true
argument-hint: "[dev|office|research]"
---

# /mode - 工作模式切换

## 功能

根据用户意图切换不同的 Agent 框架和工作流程。

## 触发短语

| 用户说 | 等同于 | 加载框架 |
|--------|--------|----------|
| "我要开发" | `/mode dev` | Solar |
| "开始开发" | `/mode dev` | Solar |
| "进入开发模式" | `/mode dev` | Solar |
| "我要办公" | `/mode office` | Clawbot |
| "处理事务" | `/mode office` | Clawbot |
| "我要研究" | `/mode research` | Solar (Researcher) |

## 工作模式

### dev - 开发模式 (Solar)

```
+=========================================================+
|              SOLAR v2.0 - Development Mode              |
+=========================================================+

Loaded:
[x] 10 Agents (Researcher, Architect, Coder...)
[x] 5-Phase Flow (Research->Design->Implement->Verify->Finalize)
[x] 16 Skills (/save, /restore, /commit...)

Quick Actions:
  @Agent name  - Call specific Agent directly
  /save        - Save session state
  /status      - Show system status

Ready. Please describe your development task.
+=========================================================+
```

**行为:**
- 加载 Solar CLAUDE.md 规范
- 启用所有开发相关 Agent 和 Skill
- 按 Solar 五阶段流程处理任务

### office - 办公模式 (Clawbot)

```
+=========================================================+
|              CLAWBOT - Office Mode                      |
+=========================================================+

Available:
- Email drafting and replies
- Schedule and reminders
- Document organization
- Meeting notes
- Task management
- Information search

Ready. Please describe your task.
+=========================================================+
```

**行为:**
- 加载 Clawbot 配置 (如存在)
- 专注于办公事务处理
- 简洁高效的输出风格

### research - 研究模式

```
+=========================================================+
|              SOLAR - Research Mode                      |
+=========================================================+

Focus:
- Technical research & paper analysis
- Feasibility assessment
- Solution comparison
- Knowledge organization

Active: @Researcher (Opus)

Ready. Please describe your research topic.
+=========================================================+
```

**行为:**
- 直接激活 Researcher Agent
- 启用 WebSearch, WebFetch
- 输出结构化研究报告

## 模式状态

切换模式后，在后续响应中标记当前模式：

```
[Solar/开发模式] 或 [Clawbot/办公模式] 或 [研究模式]
```

## 退出模式

```
"退出模式" / "结束" / "/mode off"
```

恢复为默认 Claude 行为。
