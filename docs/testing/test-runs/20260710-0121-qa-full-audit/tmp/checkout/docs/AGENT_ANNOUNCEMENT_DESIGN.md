# Agent 宣告机制设计

> 版本: 1.0 | 日期: 2026-01-29 | 状态: 设计中

## 一、问题分析

### 现状

```
用户: "帮我优化性能"
      ↓
Claude: 直接开始执行 (无 Agent 宣告)
```

### 根本原因

| 问题 | 原因 |
|------|------|
| CLAUDE.md 规则不被执行 | 只是建议，无强制机制 |
| Hooks 无法强制输出 | Hooks 只能阻止，不能要求输出 |
| 无任务拦截点 | Claude 收到指令直接执行 |

## 二、Skill 机制分析

### Skill 特性

```
用户: /skill-name args
      ↓
Claude Code: 加载 SKILL.md 到上下文
      ↓
Claude: 按 SKILL.md 指令执行 (高遵循率)
```

**关键洞察**: Skill 内容会被 Claude 直接处理，遵循率远高于 CLAUDE.md

### 可行性评估

| 维度 | 评估 |
|------|------|
| 技术可行性 | ✅ Skill 可包含任何指令 |
| 强制性 | ✅ Skill 内容会被执行 |
| 用户体验 | ⚠️ 需要用户使用 Skill 调用 |

## 三、设计方案

### 方案对比

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A. 任务类型 Skill | `/code`, `/research`, `/test` | 明确、可控 | 需改变习惯 |
| B. 统一入口 `/do` | `/do 实现xxx` | 一个入口 | 多一层抽象 |
| C. Agent Skill | `/@coder`, `/@researcher` | 与 @Agent 一致 | 符号冲突 |
| D. 模式增强 | `/solar` 启动后强制 | 最自然 | 实现复杂 |

### 推荐方案: A + D 组合

```
┌─────────────────────────────────────────────────────────────────┐
│                        Solar 模式                               │
│                                                                 │
│  入口:                                                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  /solar 或 "我要开发" → 进入 Solar 模式                  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              ↓                                  │
│  任务 Skill (每个内置 Agent 宣告):                              │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐       │
│  │ /code  │ │/research│ │/design │ │ /test  │ │/optimize│       │
│  │ Coder  │ │Researcher│ │Architect│ │ Tester │ │ Coder  │       │
│  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘       │
│                                                                 │
│  快捷方式 (同样触发宣告):                                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  @Coder xxx = /code xxx                                  │   │
│  │  @Researcher xxx = /research xxx                         │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## 四、Skill 设计

### 4.1 /code Skill

```markdown
---
name: code
description: 代码实现任务 - 自动触发 Coder Agent 宣告
user-invocable: true
argument-hint: "<任务描述>"
---

# /code - 代码实现

## 执行流程 (必须严格遵循)

### 步骤 1: Agent 宣告 (强制)

**必须首先输出以下格式的宣告框:**

┌─ 💻 Coder ──────────────────────────────────────┐
│ Task: [从用户输入提取任务目标]                    │
│ Plan:                                           │
│   1. [步骤1]                                    │
│   2. [步骤2]                                    │
│   3. [步骤3]                                    │
└─────────────────────────────────────────────────┘

### 步骤 2: 执行任务

按照宣告的 Plan 执行代码实现。

### 步骤 3: 完成汇报

[Solar] /code 完成 | 文件: X个 | 行数: +Y/-Z
```

### 4.2 /research Skill

```markdown
---
name: research
description: 技术调研任务 - 自动触发 Researcher Agent 宣告
user-invocable: true
argument-hint: "<调研主题>"
---

# /research - 技术调研

## 执行流程 (必须严格遵循)

### 步骤 1: Agent 宣告 (强制)

**必须首先输出:**

┌─ 🔬 Researcher ─────────────────────────────────┐
│ Task: [调研主题]                                 │
│ Plan:                                           │
│   1. [调研方向1]                                 │
│   2. [调研方向2]                                 │
│   3. [输出报告]                                  │
└─────────────────────────────────────────────────┘

### 步骤 2: 执行调研
...
```

### 4.3 完整 Skill 列表

| Skill | Agent | 用途 |
|-------|-------|------|
| `/code` | 💻 Coder | 代码实现、修复、重构 |
| `/research` | 🔬 Researcher | 技术调研、可行性分析 |
| `/design` | 🏗️ Architect | 架构设计、方案评审 |
| `/test` | 🧪 Tester | 测试编写、执行 |
| `/optimize` | 💻 Coder | 性能优化 |
| `/review` | 👁️ Reviewer | 代码审查 (已存在，需增强) |
| `/docs` | 📖 Docs | 文档生成 (已存在，需增强) |

## 五、@ 语法支持

### 识别规则

当用户输入 `@Agent xxx` 时，自动转换为对应 Skill：

```
@Coder 实现xxx       →  /code 实现xxx
@Researcher 调研xxx  →  /research 调研xxx
@Architect 设计xxx   →  /design 设计xxx
@Tester 测试xxx      →  /test 测试xxx
```

### 实现方式

在 `/agent` Skill 中添加转发逻辑：

```markdown
## @ 语法处理

当检测到 @Agent 调用时：
1. 识别 Agent 名称
2. 调用对应的任务 Skill
3. Skill 内部输出 Agent 宣告
```

## 六、/solar 模式入口

```markdown
---
name: solar
description: 启动 Solar 开发模式
user-invocable: true
---

# /solar - Solar 开发模式

## 启动

输出启动横幅:

┌─ ☀️ Solar ──────────────────────────────────────┐
│ 模式: 开发模式已激活                             │
│ Agent: 13个可用                                  │
│ 流程: P1研究 → P2设计 → P3实现 → P4验证 → P5收尾  │
├─────────────────────────────────────────────────┤
│ 使用方式:                                        │
│   /code <任务>     代码实现 (💻 Coder)           │
│   /research <主题> 技术调研 (🔬 Researcher)      │
│   /design <方案>   架构设计 (🏗️ Architect)       │
│   /test <范围>     测试执行 (🧪 Tester)          │
│   /optimize <目标> 性能优化 (💻 Coder)           │
│                                                  │
│ 或使用 @Agent 语法: @Coder 实现xxx               │
└─────────────────────────────────────────────────┘

## 模式规则

Solar 模式下，所有代码任务必须通过任务 Skill 执行。
```

## 七、实现计划

| 阶段 | 任务 | 工作量 |
|------|------|--------|
| 1 | 创建 /code Skill | 小 |
| 2 | 创建 /research Skill | 小 |
| 3 | 创建 /design Skill | 小 |
| 4 | 创建 /optimize Skill | 小 |
| 5 | 增强 /test, /review, /docs | 中 |
| 6 | 更新 /agent Skill (@ 转发) | 中 |
| 7 | 创建 /solar 入口 | 小 |
| 8 | 更新 CLAUDE.md | 小 |

## 八、预期效果

### Before

```
用户: 帮我优化 Hash Join 性能
Claude: 让我查看代码... [直接开始]
```

### After

```
用户: /optimize Hash Join 性能
或:   @Coder 优化 Hash Join 性能

Claude:
┌─ 💻 Coder ──────────────────────────────────────┐
│ Task: 优化 Hash Join 性能                        │
│ Plan:                                           │
│   1. 分析当前实现瓶颈                            │
│   2. 设计 SIMD 优化方案                          │
│   3. 实现并验证性能提升                          │
└─────────────────────────────────────────────────┘

让我开始分析...
```

## 九、风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| 用户不用 Skill | 在 CLAUDE.md 强调，/solar 启动时提示 |
| Skill 内容仍被忽略 | 使用"必须"、"强制"等强调词 |
| 使用习惯改变 | @ 语法保持兼容，自动转发 |

---

> 设计者: @Researcher | 状态: 待评审
