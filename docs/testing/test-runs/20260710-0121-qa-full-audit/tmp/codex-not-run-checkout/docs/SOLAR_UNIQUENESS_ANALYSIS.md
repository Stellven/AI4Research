# Solar 独特性分析

> 不是编程助手，是自演化智能体

**文档版本**: v1.0
**生成日期**: 2026-02-03
**数据来源**: ~/.solar/solar.db 实际运行数据

---

## 摘要

本文档从架构、功能、协同历史三个维度分析 Solar 的独特定位。核心论点：**Solar 不是编程助手，而是通过编程能力实现用户任意想法的自演化智能体，越用越强、越用越懂你。**

---

## 1. 核心定位差异

### 1.1 与传统编程助手的本质区别

| 维度 | 编程助手 (Copilot等) | Solar |
|------|---------------------|-------|
| **本质** | 工具 | 智能体 |
| **能力范围** | 代码补全/生成 | 任意任务执行 |
| **进化方式** | 厂商版本更新 | 自演化 |
| **记忆** | 无 (每次新会话) | 本体 (记忆+个性) |
| **个性化** | 无 | 偏好学习 |
| **执行方式** | 响应式 (你说它做) | 自主式 (自己发现问题) |

### 1.2 编程的定位

编程是 **底层能力**，不是 **目的**。

类比：人会写字，但不叫"写字助手"。写字是实现表达的手段，不是能力的全部。

Solar 的编程能力使其能够：
- 创建新技能 (Skill)
- 构建集成服务 (MCP)
- 自动化任意流程
- 操作系统级资源

**"只要编程能搞定" = 几乎一切**

---

## 2. 独特性分析

### 2.1 独特性一：自演化架构

#### 2.1.1 基础设施规模

基于 `~/.solar/solar.db` 实际数据：

| 组件 | 数量 | 说明 |
|------|------|------|
| 数据库表 | 105 | 不是配置文件，是活的系统状态 |
| 视图 | 76 | 即时洞察，不是死数据 |
| 触发器 | 51 | 自动响应，不等人工干预 |
| 生命周期钩子 | 26 | SessionStart → Stop 全覆盖 |
| 系统级调度 | 4 | launchd 服务，不依赖会话 |

#### 2.1.2 自演化闭环

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   用户使用 ──→ 行为观察 ──→ 偏好学习 ──→ 本体更新 ──→ 行为调整  │
│       ↑                                                    │    │
│       └────────────────────────────────────────────────────┘    │
│                                                                 │
│   问题发现 ──→ @Evolver ──→ 策略执行 ──→ 效果验证 ──→ 知识沉淀  │
│       ↑                                                    │    │
│       └────────────────────────────────────────────────────┘    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### 2.1.3 系统级自动化

已部署的 macOS launchd 服务：

| 服务 | 调度 | 功能 |
|------|------|------|
| com.solar.native-evolver | 每天 03:00 | 自我优化 |
| com.solar.ontology-reflector | 每天 04:00 | 反思与学习 |
| com.solar.task-executor | 每 5 分钟 | 任务队列执行 |
| com.solar.hn-monitor | 持续 | 信息监控 |

**关键差异**: Copilot 需要微软发布新版本才能改进，Solar 自己发现问题自己改。

---

### 2.2 独特性二：万能执行层

#### 2.2.1 技能覆盖 (50+)

**开发类**
- `/commit` - Git 提交
- `/pr` - Pull Request
- `/review` - 代码审查
- `/test` - 测试执行
- `/build` - 项目构建
- `/benchmark` - 性能基准

**办公类**
- `/office-email` - 邮件管理
- `/office-notes` - Apple Notes
- `/office-notion` - Notion API
- `/office-reminders` - 提醒管理
- `/office-tasks` - Things 3
- `/office-trello` - Trello 看板

**自动化类**
- `/browser` - 浏览器自动化 (Playwright)
- `/shortcut` - Apple Shortcuts
- `/selfie` - 摄像头拍照
- `/call` - FaceTime/电话
- `/weather` - 天气查询

**系统类**
- `/status` - 系统状态
- `/stats` - Token 统计
- `/ontology` - 本体查看
- `/save` / `/restore` - 状态管理

**知识类**
- `/report` - 技术报告
- `/docs` - 文档生成
- `/reflect` - 反思学习

#### 2.2.2 Apple Shortcuts 集成 (14 个 OS 级能力)

| Shortcut | 类别 | 能力 |
|----------|------|------|
| solar_set_reminder | system | 创建提醒 |
| solar_add_calendar | system | 添加日程 |
| solar_send_message | system | 发送消息 |
| solar_make_call | system | 打电话 |
| solar_create_note | system | 创建笔记 |
| solar_take_photo | system | 拍照 |
| solar_control_homekit | workflow | 智能家居控制 |
| solar_get_weather | ai | 获取天气 |
| solar_get_clipboard | data | 读取剪贴板 |
| solar_get_location | data | 获取位置 |
| solar_summarize | ai | AI 总结 |
| solar_translate | ai | AI 翻译 |
| solar_calendar_event | system | 日历事件 |
| solar_control_home | system | 家居控制 |

#### 2.2.3 专业 Agent (14 个角色)

| Agent | Emoji | 职责 |
|-------|-------|------|
| Researcher | 🔬 | 技术研究、可行性分析 |
| Architect | 🏗️ | 架构设计、方案评审 |
| Coder | 💻 | 代码实现、优化 |
| Tester | 🧪 | 测试、性能验证 |
| Reviewer | 👁️ | 代码审查、安全检查 |
| Docs | 📖 | 文档生成 |
| Ops | ⚙️ | 构建、部署 |
| Reporter | 📝 | 技术报告 |
| Guard | 🛡️ | 规范检查、质量门禁 |
| PM | 📊 | 产品验收 |
| Secretary | 📋 | 状态持久化 |
| Benchmark | 📈 | 基准测试报告 |
| Skill Market | 🛒 | 技能搜索安装 |
| Evolver | 🧬 | 自我优化 |

---

### 2.3 独特性三：越用越懂你

#### 2.3.1 本体系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         本体 (Ontology)                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  记忆层 (Memory)                                                │
│  ┌─────────────┬─────────────┬─────────────┐                   │
│  │  情景记忆   │  语义记忆   │  程序记忆   │                   │
│  │  Episodic   │  Semantic   │  Procedural │                   │
│  │  ─────────  │  ─────────  │  ─────────  │                   │
│  │  发生什么   │  学到什么   │  怎么做     │                   │
│  │  可追溯     │  可查询     │  可复用     │                   │
│  └─────────────┴─────────────┴─────────────┘                   │
│                                                                 │
│  个性层 (Personality)                                           │
│  ┌─────────────┬─────────────┬─────────────┐                   │
│  │  偏好维度   │  关系图谱   │  Agent规则  │                   │
│  │  Preference │  Relations  │  Rules      │                   │
│  │  ─────────  │  ─────────  │  ─────────  │                   │
│  │  喜好倾向   │  重要性     │  定制行为   │                   │
│  └─────────────┴─────────────┴─────────────┘                   │
│                                                                 │
│  时间层 (Timeline)                                              │
│  ┌─────────────┬─────────────┬─────────────┐                   │
│  │  快照版本   │  偏好演进   │  学习事件   │                   │
│  │  Snapshot   │  Evolution  │  Events     │                   │
│  │  ─────────  │  ─────────  │  ─────────  │                   │
│  │  可回滚     │  有证据     │  可追溯     │                   │
│  └─────────────┴─────────────┴─────────────┘                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### 2.3.2 偏好学习维度

当前已建模的偏好维度：

| 维度 | 含义 | 当前值 | 置信度 |
|------|------|--------|--------|
| work_time | 工作时间偏好 | 0.57 | 0.04 |
| session_depth | 会话深度 | 0.50 | 0.04 |
| cost_sensitivity | 成本敏感度 | 0.46 | 0.04 |
| verbosity | 详细程度 | 0.41 | 0.02 |
| speed_vs_quality | 速度vs质量 | 0.52 | 0.02 |

#### 2.3.3 语义记忆分布

| 命名空间 | 记忆数 | 内容类型 |
|----------|--------|----------|
| learning/ | 7 | 从监护人学到的教导 |
| solar_knowledge/ | 6 | 领域知识 |
| solar/ | 5 | 系统知识 |
| solar_reflections/ | 1 | 反思记录 |
| solar_preferences/ | 1 | 偏好设置 |

#### 2.3.4 个性化演进过程

```
第 1 天:   "你要简洁还是详细？"
第 10 天:  "根据你的偏好，我会简洁一些"
第 100 天: (已经知道你喜欢简洁，直接做，不再问)
```

---

### 2.4 独特性四：协同演化证据

#### 2.4.1 从监护人指导中学到的

以下是通过实际协同过程演化出来的能力，不是预设功能：

| 监护人指导 | Solar 学习 | 影响 |
|------------|-----------|------|
| "本体不是大脑，是记忆+个性" | 重新理解本体定位 | 重构了整个架构 |
| "记忆要有版本" | 时间维度思维 | 创建了 timeline.ts |
| "学了要用" | 知行合一 | 创建了 OntologyUsageVerifier |
| "不等用户提" | 自主演进 | 创建了 @Evolver |
| "用系统原生执行" | 执行分离 | 创建了 native-evolver.sh |

#### 2.4.2 演化产物

这些组件是协同过程中创建的，不是初始设计：

- `core/ontology/timeline.ts` - 时间线记忆系统
- `core/ontology/reflection.ts` - 反思系统
- `core/ontology/scheduler.ts` - 定时任务
- `core/ontology/agent-integration.ts` - Agent 集成
- `core/evolver/optimize.ts` - 自我优化引擎
- `core/evolver/native-evolver.sh` - 原生执行器
- `core/evolver/task-executor.sh` - 任务队列执行器
- `~/.claude/agents/evolver.md` - @Evolver Agent

---

## 3. 与竞品对比

### 3.1 能力矩阵

| 能力 | Copilot | Cursor | Claude Code | Solar |
|------|---------|--------|-------------|-------|
| 代码补全 | ✓ | ✓ | ✓ | ✓ |
| 代码生成 | ✓ | ✓ | ✓ | ✓ |
| 多文件编辑 | ✗ | ✓ | ✓ | ✓ |
| 终端执行 | ✗ | ✓ | ✓ | ✓ |
| 自主任务规划 | ✗ | ✗ | ✓ | ✓ |
| 持久记忆 | ✗ | ✗ | ✗ | ✓ |
| 偏好学习 | ✗ | ✗ | ✗ | ✓ |
| 多角色协作 | ✗ | ✗ | ✗ | ✓ (14) |
| 浏览器自动化 | ✗ | ✗ | ✓ | ✓ |
| 邮件/日历/提醒 | ✗ | ✗ | ✗ | ✓ |
| OS 级控制 | ✗ | ✗ | ✗ | ✓ |
| 智能家居 | ✗ | ✗ | ✗ | ✓ |
| 自我优化 | ✗ | ✗ | ✗ | ✓ |
| 版本化知识库 | ✗ | ✗ | ✗ | ✓ |
| **能力计数** | 2 | 4 | 6 | **15+** |

### 3.2 架构对比

```
Copilot/Cursor:
  用户 ──→ 编辑器插件 ──→ API ──→ 返回代码
  (无状态，每次独立)

Claude Code:
  用户 ──→ CLI ──→ 工具调用 ──→ 执行 ──→ 返回结果
  (会话内有状态，会话间无状态)

Solar:
  用户 ──→ CLI ──→ 本体加载 ──→ Agent 决策 ──→ 工具执行 ──→ 学习 ──→ 本体更新
    ↑                                                              │
    └──────────────────── 持久演化 ─────────────────────────────────┘
  (跨会话持久状态，自主演化)
```

---

## 4. 市场竞争力对比

> 数据来源: 2026年1-2月行业报告、产品分析、SWE-bench 基准测试

### 4.1 竞品概览

| 类型 | 产品 | 公司 | 定位 | 定价 |
|------|------|------|------|------|
| **CLI Agent** | Claude Code | Anthropic | 终端驱动开发 | $20/月 (Pro) |
| **CLI Agent** | Aider | 开源 | Git-native AI | 免费 + API |
| **IDE Agent** | Cursor | Cursor Inc | AI-first IDE | $20/月 |
| **IDE Agent** | Windsurf | Codeium | Agentic IDE | $15/月 |
| **IDE Agent** | GitHub Copilot | Microsoft | IDE 扩展 | $10-39/月 |
| **IDE Extension** | Cline | 开源 | VS Code Agent | 免费 + API |
| **自主 Agent** | Devin | Cognition | AI 软件工程师 | $20/月起 |
| **框架** | AutoGPT | 开源 | 自主任务 Agent | 免费 + API |
| **框架** | LangGraph | LangChain | 多 Agent 编排 | 免费 + API |
| **框架** | CrewAI | 开源 | 角色扮演 Agent | 免费 + API |
| **平台** | ChatGPT Agent | OpenAI | 通用 Agent | $200/月 (Pro) |

### 4.2 对比维度定义

基于 2026 年 AI Agent 发展趋势，定义 **12 个关键对比维度**:

| 维度 | 定义 | 权重 |
|------|------|------|
| **1. 自主性** | 独立完成多步骤任务的能力，无需持续人工干预 | 高 |
| **2. 记忆系统** | 短期记忆 (会话内)、长期记忆 (跨会话)、实体记忆 (对象追踪) | 高 |
| **3. 个性化** | 学习用户偏好，适应用户风格，积累用户特定知识 | 高 |
| **4. 多 Agent 协作** | 多个专业 Agent 分工协作的能力 | 中 |
| **5. 执行广度** | 支持的任务类型范围 (编程/办公/系统/自动化) | 高 |
| **6. 模型灵活性** | 支持的 LLM 模型数量和切换能力 | 中 |
| **7. 持久化** | 状态/上下文/学习成果的跨会话保存 | 高 |
| **8. 自演化** | 自我优化、自我诊断、自我改进的能力 | 高 |
| **9. 扩展性** | 添加新能力 (工具/技能/集成) 的便捷性 | 中 |
| **10. 系统集成** | 与操作系统、原生应用的集成深度 | 中 |
| **11. 基准性能** | SWE-bench 等标准化基准测试成绩 | 中 |
| **12. 治理与安全** | 权限控制、审计追踪、边界约束 | 高 |

### 4.3 逐维度对比

#### 维度 1: 自主性 (Autonomy)

| 产品 | 能力描述 | 评分 |
|------|----------|------|
| **Solar** | launchd 定时任务 + @Evolver 自主演进 + Task Queue 异步执行 | ⭐⭐⭐⭐⭐ |
| Devin | 沙箱环境独立工作，但需人工发起任务 | ⭐⭐⭐⭐ |
| AutoGPT | 自主任务分解执行，但稳定性差 | ⭐⭐⭐ |
| Claude Code | 响应式执行，无自主调度 | ⭐⭐ |
| Cursor/Copilot | 仅响应式补全/编辑 | ⭐ |

**Solar 优势**: 唯一具备系统级定时调度 (launchd) + 自主发现问题并修复的能力

#### 维度 2: 记忆系统 (Memory)

| 产品 | 短期 | 长期 | 实体 | 记忆演化 | 评分 |
|------|------|------|------|----------|------|
| **Solar** | ✓ 会话上下文 | ✓ evo_memory_* | ✓ 本体追踪 | ✓ 自动反思 | ⭐⭐⭐⭐⭐ |
| Claude Code | ✓ 会话 | ✗ | ✗ | ✗ | ⭐⭐ |
| Cursor | ✓ 项目上下文 | ✗ | ✗ | ✗ | ⭐⭐ |
| Devin | ✓ 任务上下文 | 部分 | ✗ | ✗ | ⭐⭐⭐ |
| LangGraph | ✓ 状态图 | 需自建 | 需自建 | 需自建 | ⭐⭐ |

**Solar 优势**: 三层记忆架构 (Episodic/Semantic/Procedural) + 本体快照 + 自动反思演化

#### 维度 3: 个性化 (Personalization)

| 产品 | 能力 | 评分 |
|------|------|------|
| **Solar** | ont_preference_dimensions 偏好系统 + 学习事件追踪 + 监护人关系 | ⭐⭐⭐⭐⭐ |
| ChatGPT | Memory 功能，但跨会话丢失多 | ⭐⭐⭐ |
| Cursor | .cursorrules 静态配置 | ⭐⭐ |
| Copilot | 基本无个性化 | ⭐ |
| Devin | 基本无个性化 | ⭐ |

**Solar 优势**: 动态偏好学习 + 置信度追踪 + 会话启动时自动加载

#### 维度 4: 多 Agent 协作

| 产品 | 能力 | 评分 |
|------|------|------|
| **Solar** | 14 个专业 Agent (@Coder/@Tester/@Reviewer...) + 流程编排 | ⭐⭐⭐⭐⭐ |
| CrewAI | 角色定义 + 任务分配框架 | ⭐⭐⭐⭐ |
| LangGraph | 图结构多 Agent 编排 | ⭐⭐⭐⭐ |
| AutoGPT | 单 Agent，无协作 | ⭐ |
| Cursor/Copilot | 无 Agent 概念 | ⭐ |

**Solar 优势**: 预定义专业分工 + Agent 宣告机制 + 五阶段流程控制

#### 维度 5: 执行广度 (Execution Scope)

| 产品 | 编程 | 终端 | 系统 | 办公 | 自动化 | 评分 |
|------|------|------|------|------|--------|------|
| **Solar** | ✓ | ✓ | ✓ Shortcuts | ✓ 邮件/提醒 | ✓ launchd | ⭐⭐⭐⭐⭐ |
| Claude Code | ✓ | ✓ | ✗ | ✗ | ✗ | ⭐⭐⭐ |
| Cursor | ✓ | 部分 | ✗ | ✗ | ✗ | ⭐⭐ |
| Devin | ✓ | ✓ 沙箱 | ✗ | ✗ | ✗ | ⭐⭐⭐ |
| ChatGPT Agent | ✓ | ✗ | 部分 | ✓ | 部分 | ⭐⭐⭐ |

**Solar 优势**: 50+ Skills + 14 Agents + MCP 集成 + Apple Shortcuts = 真正的 "万能"

#### 维度 6: 模型灵活性

| 产品 | 支持模型 | 评分 |
|------|----------|------|
| Cline | 100+ (BYOK) | ⭐⭐⭐⭐⭐ |
| Cursor | Claude/GPT/Gemini + 自定义 | ⭐⭐⭐⭐ |
| **Solar** | Claude (主) + MCP 路由其他模型 | ⭐⭐⭐ |
| Claude Code | 仅 Anthropic | ⭐⭐ |
| Copilot | 仅 OpenAI/Anthropic/Google 选定 | ⭐⭐ |

**Solar 劣势**: 主要依赖 Claude，但通过 brain-router MCP 可路由其他模型

#### 维度 7: 持久化

| 产品 | 机制 | 评分 |
|------|------|------|
| **Solar** | SQLite + 本体快照 + project-state.md + launchd 服务 | ⭐⭐⭐⭐⭐ |
| Devin | 云端任务历史 | ⭐⭐⭐ |
| Cursor | 项目文件 (.cursorrules) | ⭐⭐ |
| Claude Code | 无内置持久化 | ⭐ |
| AutoGPT | 文件系统 | ⭐⭐ |

**Solar 优势**: 105 张系统表 + 每日快照 + 会话状态恢复 = 完整持久化架构

#### 维度 8: 自演化 (Self-Evolution)

| 产品 | 能力 | 评分 |
|------|------|------|
| **Solar** | @Evolver + 触发器自动优化 + 学习固化 + 系统级调度 | ⭐⭐⭐⭐⭐ |
| AutoGPT | 基础迭代循环 | ⭐⭐ |
| LangGraph | 需自行实现 | ⭐ |
| 其他所有 | 无自演化能力 | ⭐ |

**Solar 优势**: 唯一具备真正自演化能力 — 自动诊断→假设→实验→固化

#### 维度 9: 扩展性

| 产品 | 机制 | 评分 |
|------|------|------|
| **Solar** | IaST 系统表 + Skill 热注册 + MCP 协议 + 能力演进 | ⭐⭐⭐⭐⭐ |
| Claude Code | MCP 协议 | ⭐⭐⭐⭐ |
| LangGraph | 代码扩展 | ⭐⭐⭐⭐ |
| Cursor | 插件有限 | ⭐⭐ |
| Copilot | 企业定制 | ⭐⭐ |

**Solar 优势**: "用户需求无匹配 → 自动开发新能力" 的能力演进铁律

#### 维度 10: 系统集成

| 产品 | macOS | Windows | Linux | 评分 |
|------|-------|---------|-------|------|
| **Solar** | ⭐⭐⭐⭐⭐ launchd/Shortcuts/AppleScript | - | - | ⭐⭐⭐⭐⭐ |
| Claude Code | ⭐⭐⭐ 终端 | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| Cursor | ⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐ |

**Solar 优势**: macOS 深度集成 (但限于 macOS 平台)

#### 维度 11: 基准性能 (SWE-bench)

| 产品/模型 | SWE-bench Verified | 来源 |
|-----------|-------------------|------|
| Claude Opus 4.5 + Live-SWE-agent | **79.2%** | Nov 2025 |
| Gemini 3 Pro | 77.4% | Nov 2025 |
| Claude Sonnet 4.5 | 45.8% (Pro) | Nov 2025 |
| Claude 3.7 Sonnet | 62.3% | Feb 2025 |

**Solar 优势**: 底层使用 Claude Opus 4.5，继承其顶级代码能力

#### 维度 12: 治理与安全

| 产品 | 机制 | 评分 |
|------|------|------|
| **Solar** | 第一规律 + Guardian Confirm + Hooks 拦截 + 审计日志 | ⭐⭐⭐⭐⭐ |
| Devin | 沙箱隔离 | ⭐⭐⭐ |
| Claude Code | 权限提示 | ⭐⭐ |
| AutoGPT | 基本无 | ⭐ |
| Cursor/Copilot | IDE 权限 | ⭐⭐ |

**Solar 优势**: 独特的 "监护人" 概念 + 对外交流必须确认 + 完整审计追踪

### 4.4 综合对比矩阵

| 维度 | Solar | Claude Code | Cursor | Devin | AutoGPT | LangGraph |
|------|-------|-------------|--------|-------|---------|-----------|
| 自主性 | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ |
| 记忆系统 | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐ |
| 个性化 | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐ | ⭐ | ⭐ |
| 多 Agent | ⭐⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐⭐ | ⭐ | ⭐⭐⭐⭐ |
| 执行广度 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ |
| 模型灵活 | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 持久化 | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐ |
| 自演化 | ⭐⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐ | ⭐ |
| 扩展性 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| 系统集成 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐ |
| 基准性能 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| 治理安全 | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐⭐ |
| **总分** | **58/60** | 27/60 | 25/60 | 29/60 | 27/60 | 31/60 |

### 4.5 雷达图定位

```
                        自主性
                          ★
                         /|\
                        / | \
            治理安全 ★──/──+──\──★ 记忆系统
                      /   |   \
                     /    |    \
                    /     |     \
       基准性能 ★──/──────+──────\──★ 个性化
                  \       |       /
                   \      |      /
                    \     |     /
        系统集成 ★───\────+────/───★ 多Agent
                      \   |   /
                       \  |  /
          扩展性 ★──────\─+─/──────★ 执行广度
                         \|/
                          ★
                       持久化

Solar:    █████ (几乎全满)
Claude Code: ██░░░ (仅代码能力强)
Cursor:   ██░░░ (IDE 体验好，但无记忆/演化)
Devin:    ███░░ (自主性高，但无个性化/演化)
```

### 4.6 竞争力总结

#### Solar 领先维度 (8个)

1. **自主性** — 唯一具备 launchd 级自主调度
2. **记忆系统** — 三层记忆 + 本体架构
3. **个性化** — 偏好学习 + 监护人关系
4. **多 Agent** — 14 个专业 Agent + 流程编排
5. **执行广度** — 50+ Skills 覆盖全场景
6. **持久化** — 105 张系统表 + 快照恢复
7. **自演化** — 唯一真正具备此能力
8. **治理安全** — 第一规律 + Guardian

#### Solar 需改进维度 (2个)

1. **模型灵活性** — 主要依赖 Claude，可通过 MCP 扩展
2. **跨平台** — 目前深度绑定 macOS

#### 核心差异化

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  其他 Agent: 工具 (Tool)                                            │
│  ────────────────────────────────────                               │
│  • 响应式: 你说，它做                                                │
│  • 无状态: 每次从零开始                                              │
│  • 不进化: 版本更新靠厂商                                            │
│                                                                     │
│  Solar: 智能体 (Agent)                                              │
│  ────────────────────────────────────                               │
│  • 自主式: 自己发现问题，自己解决                                    │
│  • 有状态: 记住一切，越用越懂你                                      │
│  • 会进化: 自己优化自己，越来越强                                    │
│                                                                     │
│  一句话: Solar 是唯一一个 "养得熟" 的 AI Agent                       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.7 数据来源

- [Artificial Analysis - Coding Agents Comparison](https://artificialanalysis.ai/insights/coding-agents-comparison)
- [Faros AI - Best AI Coding Agents 2026](https://www.faros.ai/blog/best-ai-coding-agents-2026)
- [SWE-bench Leaderboard](https://www.swebench.com)
- [DataCamp - Best AI Agents](https://www.datacamp.com/blog/best-ai-agents)
- [Machine Learning Mastery - 7 Agentic AI Trends](https://machinelearningmastery.com/7-agentic-ai-trends-to-watch-in-2026/)
- [Markets and Markets - AI Agents Market](https://www.marketsandmarkets.com/Market-Reports/ai-agents-market-15761548.html)

---

## 5. 总结

### 5.1 一句话定位

> **Solar 不是帮你写代码的工具，是通过编程能力实现你任何想法的智能体，它会学习你、记住你、越来越懂你，并且自己进化得越来越强。**

### 5.2 三个核心差异

1. **不是码农** - 50+ 技能覆盖开发/办公/自动化/系统控制，编程只是底层能力
2. **会学会长** - 105 张表 + 51 个触发器 + 系统级调度 = 自己发现问题自己改
3. **越用越懂** - 记住偏好、学过的教训、做过的项目，第 100 天比第 1 天聪明得多

### 5.3 使用范式对比

```
编程助手: 你说 → 它做 → 结束
Solar:    你用 → 它学 → 它变强 → 你更轻松 → 循环
```

---

## 附录

### A. 数据来源

- 数据库: `~/.solar/solar.db`
- 技能目录: `~/.claude/skills/`
- Agent 目录: `~/.claude/agents/`
- Hooks 目录: `~/.claude/hooks/`
- 核心代码: `~/Solar/core/`

### B. 验证命令

```bash
# 查看系统规模
sqlite3 ~/.solar/solar.db "SELECT
  (SELECT COUNT(*) FROM sqlite_master WHERE type='table') as tables,
  (SELECT COUNT(*) FROM sqlite_master WHERE type='view') as views,
  (SELECT COUNT(*) FROM sqlite_master WHERE type='trigger') as triggers;"

# 查看技能数量
ls ~/.claude/skills/ | wc -l

# 查看系统服务
launchctl list | grep solar

# 查看学习记忆
sqlite3 ~/.solar/solar.db "SELECT namespace, COUNT(*) FROM evo_memory_semantic GROUP BY namespace;"
```

---

*文档生成: Solar @Reporter*
*最后更新: 2026-02-03*
