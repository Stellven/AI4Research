---
name: solar
description: 启动 Solar 开发模式 - 五阶段流程控制
user-invocable: true
argument-hint: "[start <任务>|status|stop]"
---

# /solar - Solar 流程控制

## 命令

| 命令 | 说明 |
|------|------|
| `/solar start <任务描述>` | 启动 Solar 模式，初始化流程 |
| `/solar status` | 显示当前流程状态 |
| `/solar stop` | 停止 Solar 模式 |

## 执行流程

### /solar start <任务描述>

**必须按以下步骤执行:**

#### 1. 分析任务复杂度

| 复杂度 | 判断标准 | 流程 |
|--------|----------|------|
| 简单 | <50行, 单文件 | P3 直接实现 |
| 中等 | 50-500行, 2-5文件 | P2→P3→P4 |
| 复杂 | >500行, 跨模块, 新技术 | P1→P2→P3→P4→P5 |

#### 2. 创建状态文件

```bash
mkdir -p .solar
```

根据复杂度创建 `.solar/flow-state.json`:

**复杂任务:**
```json
{
  "version": "1.0",
  "active": true,
  "task": {
    "description": "<任务描述>",
    "complexity": "complex",
    "started_at": "<当前时间>"
  },
  "flow": {
    "current_phase": "P1",
    "current_agent": "Researcher",
    "phases": ["P1", "P2", "P3", "P4", "P5"]
  },
  "gate": {
    "G1_passed": false,
    "G1_attempts": 0,
    "G2_passed": false,
    "G2_attempts": 0
  },
  "agent_announcement": {
    "required": true,
    "announced": false
  }
}
```

**中等任务:**
```json
{
  "version": "1.0",
  "active": true,
  "task": {
    "description": "<任务描述>",
    "complexity": "medium",
    "started_at": "<当前时间>"
  },
  "flow": {
    "current_phase": "P2",
    "current_agent": "Architect",
    "phases": ["P2", "P3", "P4"]
  },
  "gate": {
    "G1_passed": false,
    "G1_attempts": 0,
    "G2_passed": false,
    "G2_attempts": 0
  },
  "agent_announcement": {
    "required": true,
    "announced": false
  }
}
```

**简单任务:**
```json
{
  "version": "1.0",
  "active": true,
  "task": {
    "description": "<任务描述>",
    "complexity": "simple",
    "started_at": "<当前时间>"
  },
  "flow": {
    "current_phase": "P3",
    "current_agent": "Coder",
    "phases": ["P3"]
  },
  "gate": {},
  "agent_announcement": {
    "required": true,
    "announced": false
  }
}
```

#### 3. 输出启动横幅

```
┌─ ☀️ Solar ──────────────────────────────────────┐
│ 任务: <任务描述>                                 │
│ 复杂度: <复杂度> | 流程: <阶段列表>              │
├─────────────────────────────────────────────────┤
│ 当前阶段: <阶段> <阶段名>                        │
│ 当前 Agent: <emoji> <Agent名>                   │
├─────────────────────────────────────────────────┤
│ 下一步: 输出 Agent 宣告，开始执行                │
└─────────────────────────────────────────────────┘
```

#### 4. 输出 Agent 宣告

**必须立即输出对应 Agent 的宣告框:**

```
┌─ <emoji> <Agent名> ─────────────────────────────┐
│ Task: <从任务描述提取的具体目标>                 │
│ Plan:                                           │
│   1. <步骤1>                                    │
│   2. <步骤2>                                    │
│   3. <步骤3>                                    │
└─────────────────────────────────────────────────┘
```

#### 5. 更新宣告状态

输出宣告后，更新状态文件:
```json
"agent_announcement": {
  "required": true,
  "announced": true
}
```

### /solar status

读取 `.solar/flow-state.json` 并显示:

```
┌─ ☀️ Solar Status ───────────────────────────────┐
│ 任务: <任务描述>                                 │
│ 复杂度: <复杂度>                                 │
├─────────────────────────────────────────────────┤
│ 当前阶段: <阶段> | Agent: <emoji> <Agent名>      │
│ 已完成: <已完成阶段列表>                         │
│ 待完成: <待完成阶段列表>                         │
├─────────────────────────────────────────────────┤
│ Gate 状态: G1 <状态> | G2 <状态>                 │
└─────────────────────────────────────────────────┘
```

### /solar stop

停止 Solar 模式:

1. 设置 `active: false`
2. 输出停止信息

## Agent-阶段映射

| 阶段 | Agent | Emoji | 职责 |
|------|-------|-------|------|
| P1 | Researcher | 🔬 | 技术调研 |
| P2 | Architect | 🏗️ | 架构设计 |
| P3 | Coder | 💻 | 代码实现 |
| P4 | Tester | 🧪 | 测试验证 |
| P5 | Ops | ⚙️ | 部署收尾 |

## 注意事项

- 每次阶段转换后必须重新输出 Agent 宣告
- 使用 `/phase next` 进行阶段转换
- Gate 检查会在阶段结束时自动执行
