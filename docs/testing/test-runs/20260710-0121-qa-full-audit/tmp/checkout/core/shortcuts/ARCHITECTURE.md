# Solar × Apple Shortcuts 集成架构

> **AI OS 的系统级技能执行层**

## 核心概念

```
┌─────────────────────────────────────────────────────────────────┐
│                    SOLAR AI OS ARCHITECTURE                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   用户意图 (自然语言)                                           │
│         │                                                       │
│         ▼                                                       │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │              Solar Agent (意图理解层)                    │  │
│   │  • 解析用户需求                                          │  │
│   │  • 匹配能力 (Skill/MCP/Shortcut)                        │  │
│   │  • 生成执行计划                                          │  │
│   └──────────────────────┬──────────────────────────────────┘  │
│                          │                                      │
│            ┌─────────────┼─────────────┐                       │
│            ▼             ▼             ▼                       │
│     ┌──────────┐  ┌──────────┐  ┌──────────────┐              │
│     │  Skills  │  │   MCPs   │  │  Shortcuts   │              │
│     │ (Claude) │  │ (Server) │  │ (Apple OS)   │              │
│     └──────────┘  └──────────┘  └──────┬───────┘              │
│                                        │                       │
│                          ┌─────────────┴─────────────┐        │
│                          ▼                           ▼        │
│                    ┌──────────┐              ┌──────────┐     │
│                    │  Siri    │              │ System   │     │
│                    │  语音    │              │  APIs    │     │
│                    └──────────┘              └──────────┘     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 分层架构

### Layer 1: 意图理解层 (Solar Agent)

```
用户: "帮我把今天的会议笔记发给团队"

Solar Agent 解析:
├── 动作: 发送
├── 对象: 会议笔记 (今天)
├── 目标: 团队
└── 匹配: Shortcut "send_meeting_notes"
```

### Layer 2: 技能路由层

```sql
-- 查询最优执行路径
SELECT
    capability_type,
    capability_id,
    execution_cost,
    success_rate
FROM sys_capabilities
WHERE matches_intent('发送会议笔记给团队')
ORDER BY
    (1 - success_rate) * 100 + execution_cost
LIMIT 1;

-- 结果: shortcut/send_meeting_notes
```

### Layer 3: Shortcuts 执行层

```
┌─────────────────────────────────────────────────────────────┐
│               SHORTCUTS EXECUTION ENGINE                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Intent Schema:                                             │
│  {                                                          │
│    "shortcut": "send_meeting_notes",                        │
│    "params": {                                              │
│      "date": "today",                                       │
│      "recipients": "team"                                   │
│    }                                                        │
│  }                                                          │
│                                                             │
│  Execution:                                                 │
│  shortcuts run "send_meeting_notes" \                       │
│    --input-type "json" \                                    │
│    --input '{"date":"today","recipients":"team"}'           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Shortcuts 分类

### 1. 系统操作类 (System)

| Shortcut | 功能 | 触发词 |
|----------|------|--------|
| `solar_set_reminder` | 创建提醒 | "提醒我..." |
| `solar_add_calendar` | 添加日历 | "安排会议..." |
| `solar_send_message` | 发送消息 | "发消息给..." |
| `solar_make_call` | 打电话 | "打电话给..." |
| `solar_control_home` | 控制智能家居 | "打开/关闭..." |

### 2. AI 处理类 (AI)

| Shortcut | 功能 | 触发词 |
|----------|------|--------|
| `solar_summarize` | 文本摘要 | "总结一下..." |
| `solar_translate` | 翻译 | "翻译成..." |
| `solar_analyze_image` | 图像分析 | "分析这张图..." |
| `solar_transcribe` | 语音转文字 | "转录..." |
| `solar_generate_text` | 生成文本 | "写一段..." |

### 3. 数据获取类 (Data)

| Shortcut | 功能 | 触发词 |
|----------|------|--------|
| `solar_get_clipboard` | 获取剪贴板 | "剪贴板内容" |
| `solar_get_location` | 获取位置 | "我在哪" |
| `solar_get_weather` | 获取天气 | "今天天气" |
| `solar_get_screen` | 获取屏幕内容 | "屏幕上是什么" |
| `solar_search_files` | 搜索文件 | "找一下..." |

### 4. 工作流类 (Workflow)

| Shortcut | 功能 | 触发词 |
|----------|------|--------|
| `solar_morning_briefing` | 早间简报 | "早安" |
| `solar_end_of_day` | 日终总结 | "今天完成了什么" |
| `solar_meeting_prep` | 会议准备 | "准备会议" |
| `solar_travel_mode` | 出行模式 | "我要出门" |

## Intent Schema 标准

```json
{
  "$schema": "solar-shortcut-intent-v1",
  "shortcut": "string (shortcut name)",
  "params": {
    "type": "object",
    "description": "Shortcut 输入参数"
  },
  "context": {
    "user_query": "原始用户输入",
    "confidence": "匹配置信度 0-1",
    "fallback": "备选 shortcut"
  },
  "options": {
    "timeout": "超时时间(秒)",
    "notify": "是否通知结果",
    "background": "是否后台执行"
  }
}
```

## 执行流程

```
┌─────────────────────────────────────────────────────────────┐
│                 SHORTCUT EXECUTION FLOW                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Intent Parsing                                          │
│     ┌──────────────────────────────────────────────────┐   │
│     │ User: "提醒我明天下午3点开会"                     │   │
│     │ ↓                                                 │   │
│     │ {action: "remind", time: "tomorrow 3pm",         │   │
│     │  content: "开会"}                                 │   │
│     └──────────────────────────────────────────────────┘   │
│                          │                                  │
│                          ▼                                  │
│  2. Shortcut Matching                                       │
│     ┌──────────────────────────────────────────────────┐   │
│     │ Query sys_shortcuts WHERE action = 'remind'       │   │
│     │ ↓                                                 │   │
│     │ Match: solar_set_reminder (confidence: 0.95)      │   │
│     └──────────────────────────────────────────────────┘   │
│                          │                                  │
│                          ▼                                  │
│  3. Parameter Mapping                                       │
│     ┌──────────────────────────────────────────────────┐   │
│     │ {                                                 │   │
│     │   "shortcut": "solar_set_reminder",               │   │
│     │   "params": {                                     │   │
│     │     "title": "开会",                              │   │
│     │     "datetime": "2026-01-31T15:00:00"             │   │
│     │   }                                               │   │
│     │ }                                                 │   │
│     └──────────────────────────────────────────────────┘   │
│                          │                                  │
│                          ▼                                  │
│  4. Execution                                               │
│     ┌──────────────────────────────────────────────────┐   │
│     │ shortcuts run "solar_set_reminder" \              │   │
│     │   --input '{"title":"开会",...}'                  │   │
│     └──────────────────────────────────────────────────┘   │
│                          │                                  │
│                          ▼                                  │
│  5. Result Handling                                         │
│     ┌──────────────────────────────────────────────────┐   │
│     │ {                                                 │   │
│     │   "success": true,                                │   │
│     │   "reminder_id": "xxx",                           │   │
│     │   "message": "已创建提醒: 明天下午3点开会"         │   │
│     │ }                                                 │   │
│     └──────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 自动化触发

### 时间触发

```yaml
# solar_morning_briefing
trigger:
  type: time
  schedule: "0 7 * * *"  # 每天早上7点
actions:
  - get_weather
  - get_calendar_today
  - summarize_unread_emails
  - speak_briefing
```

### 位置触发

```yaml
# solar_arrive_office
trigger:
  type: location
  region: "office"
  event: "enter"
actions:
  - disable_dnd
  - get_today_meetings
  - notify_team_arrival
```

### 事件触发

```yaml
# solar_email_classifier
trigger:
  type: event
  source: "Mail"
  event: "new_email"
actions:
  - extract_email_content
  - classify_priority
  - auto_label
  - notify_if_urgent
```

## 与 Siri 集成

```
┌─────────────────────────────────────────────────────────────┐
│                   SIRI INTEGRATION                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  "Hey Siri, Solar 帮我..."                                  │
│         │                                                   │
│         ▼                                                   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Siri 识别 "Solar" 前缀                               │   │
│  │ → 转发到 Solar Shortcuts Router                      │   │
│  └──────────────────────┬──────────────────────────────┘   │
│                         │                                   │
│                         ▼                                   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ solar_router shortcut                                │   │
│  │ • 接收自然语言                                       │   │
│  │ • 调用 LLM 解析意图                                  │   │
│  │ • 路由到具体 Shortcut                                │   │
│  └──────────────────────┬──────────────────────────────┘   │
│                         │                                   │
│                         ▼                                   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 执行目标 Shortcut                                    │   │
│  │ → 返回结果给 Siri                                    │   │
│  │ → Siri 语音播报                                      │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## iCloud 同步

所有 Solar Shortcuts 通过 iCloud 自动同步:

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│     iPhone      │     │      iPad       │     │       Mac       │
│                 │     │                 │     │                 │
│ Solar Shortcuts │ ←── │ Solar Shortcuts │ ──→ │ Solar Shortcuts │
│                 │  ↑  │                 │  ↑  │                 │
└────────┬────────┘  │  └────────┬────────┘  │  └────────┬────────┘
         │           │           │           │           │
         └───────────┴───────────┴───────────┴───────────┘
                              │
                        ┌─────┴─────┐
                        │  iCloud   │
                        │  Sync     │
                        └───────────┘
```

## 安全模型

```
┌─────────────────────────────────────────────────────────────┐
│                   SECURITY MODEL                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  权限分级:                                                  │
│  ─────────────────────────────────────────────────────────  │
│  Level 0: 只读 (天气、时间、日历查看)                       │
│  Level 1: 本地写入 (提醒、笔记、文件)                       │
│  Level 2: 通信 (消息、邮件、电话)                           │
│  Level 3: 支付/敏感 (需要二次确认)                          │
│                                                             │
│  确认策略:                                                  │
│  ─────────────────────────────────────────────────────────  │
│  • Level 0-1: 静默执行                                      │
│  • Level 2: 显示预览，3秒后自动执行                         │
│  • Level 3: 必须明确确认                                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```
