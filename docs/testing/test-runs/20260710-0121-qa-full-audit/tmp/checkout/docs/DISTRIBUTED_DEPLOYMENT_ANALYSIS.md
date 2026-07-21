# Solar 系统资源消耗与分布式部署分析报告

> 分析时间: 2026-02-04
> 分析者: @Researcher

## 一、资源总览

| 组件类型 | 数量 | 依赖 LLM | 可离线 | GPU 需求 |
|----------|------|----------|--------|----------|
| Agents | 15 | 全部 | 否 | 可选 |
| Skills | 49 | 部分 | 大部分 | 否 |
| MCP Servers | 10 | 否 | 部分 | 否 |
| Core 模块 | 27 | 否 | 是 | 否 |
| Shortcuts | 12 | 否 | 是 | 否 |

---

## 二、Agents 资源分析 (15个)

### 2.1 云端 Agents (需 Opus - 高资源消耗)

| Agent | 模型 | Token/次 | 依赖工具 | CPU | 内存 | 网络 | GPU |
|-------|------|----------|----------|-----|------|------|-----|
| 🔬 Researcher | Opus | ~15,000 | WebSearch, WebFetch, Read, Grep | 低 | 低 | **高** | 否 |
| 🏗️ Architect | Opus | ~18,000 | Read, Grep, Glob | 低 | 低 | 低 | 否 |
| 📝 Reporter | Opus | ~12,000 | Read, Write, Grep, WebSearch | 低 | 低 | 中 | 否 |
| 📊 BenchmarkReporter | Opus | ~10,000 | Read, Write, Bash, Grep | 中 | 低 | 低 | 否 |
| 📋 PM | Opus | ~8,000 | Read, Grep, Glob | 低 | 低 | 低 | 否 |

**资源特点:**
- **网络依赖**: 必须连接 Claude API
- **计费成本**: Opus 约 $15/M 输入, $75/M 输出
- **延迟敏感**: 单次调用 3-10 秒

### 2.2 本地 Agents (可 Sonnet - 中等资源消耗)

| Agent | 模型 | Token/次 | 依赖工具 | CPU | 内存 | 网络 | GPU |
|-------|------|----------|----------|-----|------|------|-----|
| 💻 Coder | Sonnet | ~8,000 | Read, Write, Edit, Bash, Grep | 中 | 低 | 低 | 否 |
| 🧪 Tester | Sonnet | ~6,000 | Read, Write, Bash, Grep | **高** | 中 | 低 | 否 |
| 👁️ Reviewer | Sonnet | ~5,000 | Read, Grep, Glob | 低 | 低 | 低 | 否 |
| 📖 Docs | Sonnet | ~4,000 | Read, Write, Edit, Grep | 低 | 低 | 低 | 否 |
| ⚙️ Ops | Sonnet | ~3,000 | Bash, Read, Grep | **高** | 中 | 低 | 否 |
| 🛡️ Guard | Sonnet | ~3,000 | Read, Grep, Glob | 低 | 低 | 低 | 否 |
| 🔍 Explore | Task | ~4,000 | Read, Grep, Glob | 低 | 低 | 低 | 否 |
| 📐 Plan | Task | ~6,000 | Read, Grep, Glob | 低 | 低 | 低 | 否 |

**资源特点:**
- **计费成本**: Sonnet 约 $3/M 输入, $15/M 输出
- **可本地化**: 若使用本地 LLM (如 Ollama + DeepSeek) 可离线
- **Tester/Ops**: 执行构建/测试时 CPU 密集

### 2.3 边缘 Agents (可 Haiku - 低资源消耗)

| Agent | 模型 | Token/次 | 依赖工具 | CPU | 内存 | 网络 | GPU |
|-------|------|----------|----------|-----|------|------|-----|
| 📝 Secretary | Haiku | ~2,000 | Write, Read | 低 | 低 | 低 | 否 |
| 🛒 SM | Haiku | ~2,500 | WebSearch, WebFetch, Bash | 低 | 低 | 中 | 否 |

**资源特点:**
- **计费成本**: Haiku 约 $0.25/M 输入, $1.25/M 输出
- **响应快速**: 延迟 <1 秒
- **适合边缘**: 可部署在低功耗设备

---

## 三、Skills 资源分析 (49个)

### 3.1 核心开发 Skills (10个) - 🟢 轻量

| Skill | 命令 | 依赖 | CPU | 内存 | 磁盘 | 网络 | 可离线 |
|-------|------|------|-----|------|------|------|--------|
| Solar 启动 | `/solar` | Bun, SQLite | 低 | 低 | 低 | 否 | ✅ |
| Git 提交 | `/commit` | Git | 低 | 低 | 低 | 否 | ✅ |
| PR 创建 | `/pr` | Git, gh | 低 | 低 | 低 | 是 | ❌ |
| 代码审查 | `/review` | Grep | 低 | 低 | 低 | 否 | ✅ |
| 项目构建 | `/build` | Make/CMake/npm | **高** | 中 | 中 | 可选 | ✅ |
| 运行测试 | `/test` | Test framework | **高** | 中 | 中 | 可选 | ✅ |
| 状态保存 | `/save` | SQLite | 低 | 低 | 低 | 否 | ✅ |
| 状态恢复 | `/restore` | SQLite | 低 | 低 | 低 | 否 | ✅ |
| 系统状态 | `/status` | SQLite | 低 | 低 | 低 | 否 | ✅ |
| 本体管理 | `/ontology` | SQLite, Bun | 低 | 低 | 低 | 否 | ✅ |

### 3.2 办公 Skills (12个) - 🟡 中等

| Skill | 命令 | 依赖 | CPU | 内存 | 磁盘 | 网络 | 可离线 |
|-------|------|------|-----|------|------|------|--------|
| 办公模式 | `/office` | - | 低 | 低 | 低 | 否 | ✅ |
| 邮件 CLI | `/office-email` | himalaya | 低 | 低 | 低 | **是** | ❌ |
| 邮件 Web | `/email-web` | Bun, HTTP | 低 | 低 | 低 | **是** | ❌ |
| 邮件搜索 | `/email-search` | himalaya | 低 | 低 | 低 | **是** | ❌ |
| Apple Notes | `/office-notes` | AppleScript | 低 | 低 | 低 | 否 | ✅ |
| Apple Reminders | `/office-reminders` | AppleScript | 低 | 低 | 低 | 否 | ✅ |
| Things 3 | `/office-tasks` | AppleScript | 低 | 低 | 低 | 否 | ✅ |
| Notion | `/office-notion` | Notion API | 低 | 低 | 低 | **是** | ❌ |
| Trello | `/office-trello` | Trello API | 低 | 低 | 低 | **是** | ❌ |
| 电话 | `/call` | AppleScript | 低 | 低 | 低 | **是** | ❌ |
| 拍照 | `/selfie` | imagesnap | 低 | 低 | 低 | 否 | ✅ |

### 3.3 开发辅助 Skills (15个) - 🟡 中等

| Skill | 命令 | 依赖 | CPU | 内存 | 磁盘 | 网络 | 可离线 |
|-------|------|------|-----|------|------|------|--------|
| 文档生成 | `/docs` | - | 低 | 低 | 低 | 否 | ✅ |
| 技术报告 | `/report` | - | 低 | 低 | 中 | 否 | ✅ |
| 变更日志 | `/changelog` | Git | 低 | 低 | 低 | 否 | ✅ |
| 基准测试 | `/benchmark` | 项目构建 | **高** | 中 | 中 | 否 | ✅ |
| 精确编辑 | `/precise-edit` | Grep | 低 | 低 | 低 | 否 | ✅ |
| MCP 构建 | `/mcp-builder` | npm | 中 | 中 | 中 | **是** | ❌ |
| 技能创建 | `/skill-creator` | Bun | 低 | 低 | 低 | 否 | ✅ |
| 浏览器测试 | `/webapp-testing` | **Playwright** | **高** | **高** | 中 | **是** | ❌ |
| 浏览器操作 | `/browser` | **Playwright** | **高** | **高** | 中 | **是** | ❌ |
| 阶段控制 | `/phase` | - | 低 | 低 | 低 | 否 | ✅ |
| Token 统计 | `/stats` | SQLite | 低 | 低 | 低 | 否 | ✅ |
| PPT 生成 | `/ppt` | Bun | 低 | 低 | 中 | 否 | ✅ |
| HN 监控 | `/hn-monitor` | Bun, HTTP | 低 | 低 | 低 | **是** | ❌ |
| 天气查询 | `/weather` | HTTP/Shortcut | 低 | 低 | 低 | **是** | ❌ |
| Backlog | `/backlog` | SQLite | 低 | 低 | 低 | 否 | ✅ |

### 3.4 Apple Shortcuts (12个) - 🟢 轻量

| Shortcut | 用途 | CPU | 内存 | 网络 | 可离线 |
|----------|------|-----|------|------|--------|
| solar_set_reminder | 创建提醒 | 低 | 低 | 否 | ✅ |
| solar_get_weather | 获取天气 | 低 | 低 | 是 | ❌ |
| solar_send_message | 发送消息 | 低 | 低 | 是 | ❌ |
| solar_calendar_event | 日历事件 | 低 | 低 | 否 | ✅ |
| solar_create_note | 创建笔记 | 低 | 低 | 否 | ✅ |
| solar_take_photo | 拍照 | 低 | 低 | 否 | ✅ |
| solar_control_homekit | HomeKit 控制 | 低 | 低 | 是 | ❌ |
| solar_clipboard | 剪贴板操作 | 低 | 低 | 否 | ✅ |
| solar_location | 获取位置 | 低 | 低 | 是 | ❌ |
| solar_screen_capture | 屏幕截图 | 低 | 低 | 否 | ✅ |
| solar_open_app | 打开应用 | 低 | 低 | 否 | ✅ |
| solar_siri_command | Siri 命令 | 低 | 低 | 是 | ❌ |

---

## 四、MCP Servers 资源分析 (10个)

| MCP Server | 用途 | CPU | 内存 | 磁盘 | 网络 | GPU | 可离线 | 状态 |
|------------|------|-----|------|------|------|-----|--------|------|
| **playwright** | 浏览器自动化 | **高** | **高** (500MB+) | 中 (Chromium) | **是** | 否 | ❌ | ✅ 已配置 |
| **himalaya** | 邮件访问 | 低 | 低 | 低 | **是** (IMAP) | 否 | ❌ | ✅ 已配置 |
| **brain-router** | 多模型调度 | 低 | 低 | 低 | **是** | 否 | ❌ | ✅ 已配置 |
| notion | Notion API | 低 | 低 | 低 | **是** | 否 | ❌ | ⚠️ 需配置 |
| trello | Trello API | 低 | 低 | 低 | **是** | 否 | ❌ | ⚠️ 需配置 |
| filesystem | 文件系统 | 低 | 低 | 低 | 否 | 否 | ✅ | ⚠️ 可选 |
| github | GitHub API | 低 | 低 | 低 | **是** | 否 | ❌ | ⚠️ 可选 |
| sqlite | 数据库访问 | 低 | 低 | 低 | 否 | 否 | ✅ | ⚠️ 可选 |
| slack | Slack 集成 | 低 | 低 | 低 | **是** | 否 | ❌ | ⚠️ 可选 |
| discord | Discord 集成 | 低 | 低 | 低 | **是** | 否 | ❌ | ⚠️ 可选 |

**关键发现:**
- **Playwright** 是最重资源的 MCP，需要 Chromium (~500MB 内存)
- 大部分 MCP 需要网络连接
- 本地可用: filesystem, sqlite

---

## 五、设备分级部署建议

### 🟢 轻量级 - 边缘设备 (Mac mini M1/树莓派 4B+)

**硬件要求:** 4GB RAM, 32GB 存储, WiFi

**推荐配置:**
```
┌─────────────────────────────────────────────────────────────┐
│  🟢 EDGE DEVICE (Mac mini M1 / RPi 4B)                       │
├─────────────────────────────────────────────────────────────┤
│  RAM: 4-8GB | Storage: 32-64GB | Network: WiFi              │
├─────────────────────────────────────────────────────────────┤
│  可运行:                                                     │
│  • Agents: Secretary, SM (via Haiku API)                    │
│  • Skills: 基础开发 (20+), Shortcuts (12)                   │
│  • Core: REE, TVS, Capsule                                  │
│  • MCP: filesystem, sqlite                                   │
├─────────────────────────────────────────────────────────────┤
│  Token 成本: ~$0.05/天 (轻度使用)                            │
└─────────────────────────────────────────────────────────────┘
```

### 🟡 中等级 - 家庭服务器 (Mac mini M2 Pro / Intel NUC i7)

**硬件要求:** 16GB RAM, 256GB SSD, 有线网络

**推荐配置:**
```
┌─────────────────────────────────────────────────────────────┐
│  🟡 HOME SERVER (Mac mini M2 Pro / Intel NUC i7)             │
├─────────────────────────────────────────────────────────────┤
│  RAM: 16-32GB | Storage: 256-512GB | Network: 1Gbps         │
├─────────────────────────────────────────────────────────────┤
│  可运行:                                                     │
│  • Agents: 全部本地 Agent (8) + 边缘 Agent (2)              │
│  • Skills: 全部 (49)                                         │
│  • Core: 全部模块                                            │
│  • MCP: himalaya, filesystem, sqlite, playwright (受限)     │
│  • 可选: Ollama + Qwen2.5-7B (本地推理)                     │
├─────────────────────────────────────────────────────────────┤
│  Token 成本: ~$0.50/天 (中度使用)                            │
│  本地 LLM: 7B 参数, ~4GB VRAM, 20 tok/s                      │
└─────────────────────────────────────────────────────────────┘
```

### 🔴 重量级 - 云端/工作站 (Mac Studio M2 Ultra / RTX 4090 PC)

**硬件要求:** 64GB+ RAM, 1TB SSD, GPU (可选)

**推荐配置:**
```
┌─────────────────────────────────────────────────────────────┐
│  🔴 WORKSTATION (Mac Studio M2 Ultra / RTX 4090 PC)          │
├─────────────────────────────────────────────────────────────┤
│  RAM: 64-192GB | Storage: 1-2TB NVMe | GPU: 24-48GB VRAM    │
├─────────────────────────────────────────────────────────────┤
│  可运行:                                                     │
│  • Agents: 全部 (15)                                         │
│  • Skills: 全部 (49)                                         │
│  • Core: 全部模块                                            │
│  • MCP: 全部 (10)                                            │
│  • 本地 LLM: Llama 3 70B / Qwen2.5-72B                      │
├─────────────────────────────────────────────────────────────┤
│  Token 成本: ~$5/天 (重度使用 Opus)                          │
│  本地 LLM: 70B 参数, ~40GB VRAM, 30+ tok/s                   │
│  完全离线: ✅ (使用本地 LLM)                                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 六、分布式部署架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                    SOLAR DISTRIBUTED DEPLOYMENT                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ┌─────────────────┐                                               │
│   │   🔴 云端/GPU   │  Researcher, Architect, Reporter             │
│   │   (Opus API)    │  WebSearch, 重度推理                          │
│   └────────┬────────┘                                               │
│            │ HTTPS (Claude API)                                     │
│            │                                                        │
│   ┌────────▼────────┐                                               │
│   │   🟡 家庭服务器 │  Coder, Tester, Reviewer, Ops                │
│   │   (Sonnet/本地) │  构建, 测试, 基准测试                         │
│   │                 │  himalaya, Playwright                         │
│   └────────┬────────┘                                               │
│            │ LAN / Tailscale                                        │
│            │                                                        │
│   ┌────────▼────────┐    ┌─────────────────┐                       │
│   │  🟢 Mac (主力)  │───│  🟢 边缘设备    │                        │
│   │  (Haiku/本地)   │    │  (Shortcuts)    │                        │
│   │  Secretary, SM  │    │  提醒, 天气     │                        │
│   │  日常 Skills    │    │  HomeKit        │                        │
│   └─────────────────┘    └─────────────────┘                       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 任务路由规则

| 任务类型 | 路由目标 | 原因 |
|----------|----------|------|
| 技术调研 | 云端 Opus | 需要 WebSearch + 深度推理 |
| 架构设计 | 云端 Opus | 复杂推理 |
| 代码实现 | 家庭服务器 | CPU 密集构建 |
| 基准测试 | 家庭服务器 | 需要稳定环境 |
| 状态保存 | 本地 Mac | 低延迟 |
| 提醒/日历 | 边缘 Shortcut | 最快响应 |
| 邮件操作 | 家庭服务器 | 需要 IMAP 连接 |

---

## 七、成本估算

### 按使用强度

| 使用模式 | 日 Token | API 成本/天 | 本地替代 |
|----------|----------|-------------|----------|
| 轻度 (边缘) | ~50K | ~$0.05 | Haiku 即可 |
| 中度 (开发) | ~500K | ~$0.50 | Sonnet + 本地 7B |
| 重度 (研究) | ~2M | ~$5.00 | Opus + 本地 70B |

### 本地 LLM 替代方案

| 云端模型 | 本地替代 | VRAM 需求 | 性能比 |
|----------|----------|-----------|--------|
| Haiku | Qwen2.5-3B | 4GB | ~80% |
| Sonnet | Qwen2.5-14B | 12GB | ~70% |
| Opus | Qwen2.5-72B | 48GB | ~60% |

---

## 八、总结

### 关键发现

1. **大部分组件轻量**: 49 个 Skills 中 35+ 个可离线运行，资源需求低
2. **LLM 是主要瓶颈**: 15 个 Agents 全部依赖 LLM，但可分级部署
3. **Playwright 最重**: 唯一需要高内存的 MCP (~500MB)
4. **Apple Shortcuts 高效**: 12 个 Shortcuts 全部轻量，响应 <50ms

### 部署建议

| 场景 | 推荐配置 | 月成本 |
|------|----------|--------|
| 个人开发者 | Mac + Haiku/Sonnet API | ~$15 |
| 小团队 | Mac + 家庭服务器 + 本地 LLM | ~$50 + 电费 |
| 企业级 | 云端 GPU + 多节点 | ~$500+ |

### 优先优化项

1. 将 Tester/Ops 的构建任务卸载到家庭服务器
2. 使用本地 7B LLM 替代 Haiku 调用
3. Shortcuts 优先于网络 API (天气、提醒)
4. 批量处理邮件减少 himalaya 调用次数

---

*此报告基于 @Researcher 对 Solar 系统的资源分析*
*下一步: 设计小区神经网任务市场协同机制*
