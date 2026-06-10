---
name: office
description: 启动办公模式 - 邮件/任务/笔记/日程管理 (基于 Moltbot)
user-invocable: true
argument-hint: "[email|tasks|reminders|notes|notion|trello|status]"
---

# /office - 办公助手模式

> 基于 [Moltbot](https://github.com/suraj-subrahmanyan/opensolar) 的办公能力集成

## 启动

当用户说 **"我要办公"** 时，自动进入办公模式并显示：

```
┌─ 📋 Office Mode ────────────────────────────────┐
│ 办公助手已启动                                   │
├─────────────────────────────────────────────────┤
│ 📧 邮件    /office email    himalaya CLI        │
│ ⏰ 提醒    /office reminders  Apple Reminders   │
│ ✅ 任务    /office tasks    Things 3            │
│ 📝 笔记    /office notes    Apple Notes         │
│ 📓 Notion  /office notion   Notion API          │
│ 📋 Trello  /office trello   Trello 看板         │
├─────────────────────────────────────────────────┤
│ 💡 直接说需求，我会自动选择合适的工具           │
│    例如: "查看今天的邮件" "添加一个提醒"         │
└─────────────────────────────────────────────────┘
```

## 功能模块

### 📧 邮件管理 (`/office email`)

使用 **Himalaya** CLI 管理邮件：

| 操作 | 命令 |
|------|------|
| 列出邮件 | `himalaya envelope list` |
| 读取邮件 | `himalaya message read <id>` |
| 发送邮件 | `himalaya message write` |
| 回复邮件 | `himalaya message reply <id>` |
| 搜索邮件 | `himalaya envelope list from xxx subject xxx` |

**配置**: `~/.config/himalaya/config.toml`

### ⏰ 提醒管理 (`/office reminders`)

使用 **remindctl** 管理 Apple Reminders：

| 操作 | 命令 |
|------|------|
| 今日提醒 | `remindctl today` |
| 添加提醒 | `remindctl add "内容" --due tomorrow` |
| 完成提醒 | `remindctl complete <id>` |
| 列出清单 | `remindctl list` |

**前提**: macOS + Reminders 权限

### ✅ 任务管理 (`/office tasks`)

使用 **things** CLI 管理 Things 3：

| 操作 | 命令 |
|------|------|
| 今日任务 | `things today` |
| 收件箱 | `things inbox` |
| 添加任务 | `things add "标题" --when today` |
| 搜索任务 | `things search "关键词"` |

**前提**: macOS + Things 3 + Full Disk Access

### 📝 笔记管理 (`/office notes`)

使用 AppleScript 管理 Apple Notes：

| 操作 | 方法 |
|------|------|
| 创建笔记 | osascript |
| 搜索笔记 | osascript |

### 📓 Notion (`/office notion`)

使用 Notion API：

| 操作 | 说明 |
|------|------|
| 搜索页面 | `POST /v1/search` |
| 创建页面 | `POST /v1/pages` |
| 查询数据库 | `POST /v1/data_sources/{id}/query` |

**配置**: `~/.config/notion/api_key`

### 📋 Trello (`/office trello`)

使用 Trello API：

| 操作 | 说明 |
|------|------|
| 列出看板 | API |
| 添加卡片 | API |
| 移动卡片 | API |

## 智能路由

根据用户请求自动选择工具：

| 用户说 | 工具 |
|--------|------|
| "查看邮件" / "发邮件" | himalaya |
| "提醒我" / "设置提醒" | remindctl |
| "添加任务" / "今天要做什么" | things |
| "记个笔记" / "写备忘" | Apple Notes |
| "更新 Notion" / "查 Notion" | Notion API |
| "看板" / "Trello" | Trello API |

## 安装依赖

```bash
# 邮件 (Himalaya)
brew install himalaya

# 提醒 (remindctl)
brew install steipete/tap/remindctl

# 任务 (Things CLI)
go install github.com/ossianhempel/things3-cli/cmd/things@latest

# Notion - 设置 API Key
mkdir -p ~/.config/notion
echo "ntn_your_key" > ~/.config/notion/api_key
```

## 退出办公模式

说 **"退出办公"** 或 **"我要开发"** 切换回 Solar 开发模式。

## 与 Solar 集成

| 模式 | 触发词 | 功能 |
|------|--------|------|
| 开发模式 | "我要开发" | Solar 五阶段流程 |
| **办公模式** | **"我要办公"** | **邮件/任务/提醒** |
| 研究模式 | "我要研究" | @Researcher |
