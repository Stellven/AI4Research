# Solar Flow Engine 设计

> 版本: 1.0 | 日期: 2026-01-29 | 状态: 设计中

## 一、问题回顾

当前 Solar 是"文档框架"，缺乏执行保证：

| 设计 | 问题 |
|------|------|
| 五阶段流程 | Claude 可能跳过 |
| Agent 调度 | 没有强制切换 |
| Gate 检查 | 没有拦截机制 |
| 状态追踪 | 无持久化 |

## 二、技术发现

### Claude Code Hooks 关键能力

| Hook 事件 | 触发时机 | 关键能力 |
|-----------|----------|----------|
| **UserPromptSubmit** | 用户提交时 | 可注入 systemMessage |
| **PreToolUse** | 工具调用前 | 可阻止 + 注入提醒 |
| **PostToolUse** | 工具调用后 | 可提供反馈 |
| **Stop** | Claude 停止时 | 可阻止 + 要求继续 |
| **SessionStart** | 会话开始 | 可加载状态 |

### 核心机制

```json
{
  "continue": true,
  "systemMessage": "当前阶段: P3 实现 | Agent: Coder | 请先输出 Agent 宣告"
}
```

**Hooks 可以向 Claude 注入上下文信息！**

## 三、架构设计

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Solar Flow Engine                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐             │
│  │   Skills    │    │    Hooks    │    │   State     │             │
│  │  (入口点)   │───▶│  (执行器)   │◀──▶│  (持久化)   │             │
│  └─────────────┘    └─────────────┘    └─────────────┘             │
│        │                  │                  │                      │
│        │                  │                  │                      │
│        ▼                  ▼                  ▼                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                                                              │  │
│  │  /solar start  ──▶  UserPromptSubmit Hook  ──▶  flow.json   │  │
│  │       │                    │                        │        │  │
│  │       │                    ▼                        │        │  │
│  │       │         注入: "当前 P1 | @Researcher"       │        │  │
│  │       │                    │                        │        │  │
│  │       │                    ▼                        │        │  │
│  │       │              Claude 执行                    │        │  │
│  │       │                    │                        │        │  │
│  │       │                    ▼                        │        │  │
│  │       │         PreToolUse Hook (检查)              │        │  │
│  │       │                    │                        │        │  │
│  │       │                    ▼                        │        │  │
│  │       │           Stop Hook (Gate)                  │        │  │
│  │       │                    │                        │        │  │
│  │       ▼                    ▼                        ▼        │  │
│  │  [阶段转换]  ◀─────  [Gate 通过]  ──────▶  [更新状态]       │  │
│  │                                                              │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## 四、状态文件设计

### `.solar/flow-state.json`

```json
{
  "version": "1.0",
  "active": true,
  "task": {
    "description": "优化 Hash Join 性能",
    "complexity": "complex",
    "started_at": "2026-01-29T10:00:00Z"
  },
  "flow": {
    "current_phase": "P3",
    "current_agent": "Coder",
    "phase_history": [
      {"phase": "P1", "agent": "Researcher", "completed_at": "..."},
      {"phase": "P2", "agent": "Architect", "completed_at": "..."}
    ]
  },
  "gate": {
    "G1_passed": true,
    "G2_passed": false,
    "G2_attempts": 0
  },
  "agent_announcement": {
    "required": true,
    "announced": false
  }
}
```

## 五、Hooks 实现

### 5.1 SessionStart Hook

```bash
#!/bin/bash
# hooks/solar-session-start.sh
# 会话开始时加载状态

STATE_FILE="$PWD/.solar/flow-state.json"

if [[ -f "$STATE_FILE" ]]; then
    PHASE=$(jq -r '.flow.current_phase' "$STATE_FILE")
    AGENT=$(jq -r '.flow.current_agent' "$STATE_FILE")
    TASK=$(jq -r '.task.description' "$STATE_FILE")

    cat << EOF
{
  "continue": true,
  "systemMessage": "Solar 状态已恢复:\n- 阶段: $PHASE\n- Agent: $AGENT\n- 任务: $TASK\n\n请继续执行，首先输出 Agent 宣告。"
}
EOF
else
    echo '{"continue": true}'
fi
```

### 5.2 UserPromptSubmit Hook (核心)

```bash
#!/bin/bash
# hooks/solar-prompt-submit.sh
# 用户提交时注入当前状态

STATE_FILE="$PWD/.solar/flow-state.json"
INPUT=$(cat)
USER_PROMPT=$(echo "$INPUT" | jq -r '.user_prompt // empty')

# 如果没有激活 Solar 模式，正常放行
if [[ ! -f "$STATE_FILE" ]]; then
    echo '{"continue": true}'
    exit 0
fi

# 读取当前状态
ACTIVE=$(jq -r '.active' "$STATE_FILE")
if [[ "$ACTIVE" != "true" ]]; then
    echo '{"continue": true}'
    exit 0
fi

PHASE=$(jq -r '.flow.current_phase' "$STATE_FILE")
AGENT=$(jq -r '.flow.current_agent' "$STATE_FILE")
ANNOUNCED=$(jq -r '.agent_announcement.announced' "$STATE_FILE")

# 构建提醒信息
if [[ "$ANNOUNCED" == "false" ]]; then
    REMINDER="【Solar 提醒】当前阶段: $PHASE | Agent: $AGENT\n\n⚠️ 必须先输出 Agent 宣告框，格式:\n┌─ [emoji] $AGENT ────────────────────────────┐\n│ Task: [任务目标]                             │\n│ Plan:                                       │\n│   1. [步骤1]                                │\n│   2. [步骤2]                                │\n└─────────────────────────────────────────────┘"
else
    REMINDER="【Solar】阶段: $PHASE | Agent: $AGENT"
fi

cat << EOF
{
  "continue": true,
  "systemMessage": "$REMINDER"
}
EOF
```

### 5.3 PreToolUse Hook

```bash
#!/bin/bash
# hooks/solar-pre-tool.sh
# 工具调用前检查

STATE_FILE="$PWD/.solar/flow-state.json"
INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')

if [[ ! -f "$STATE_FILE" ]]; then
    echo '{"continue": true}'
    exit 0
fi

PHASE=$(jq -r '.flow.current_phase' "$STATE_FILE")
AGENT=$(jq -r '.flow.current_agent' "$STATE_FILE")
ANNOUNCED=$(jq -r '.agent_announcement.announced' "$STATE_FILE")

# 检查是否已宣告 (Write/Edit 前必须宣告)
if [[ "$ANNOUNCED" == "false" && ("$TOOL_NAME" == "Write" || "$TOOL_NAME" == "Edit") ]]; then
    cat << EOF
{
  "continue": true,
  "systemMessage": "【Solar 警告】在执行 $TOOL_NAME 前，请先输出 Agent 宣告。\n当前 Agent: $AGENT\n\n请先输出宣告框，再继续操作。"
}
EOF
    exit 0
fi

# Agent 工具限制检查
case "$AGENT" in
    "Researcher")
        if [[ "$TOOL_NAME" == "Edit" || "$TOOL_NAME" == "Bash" ]]; then
            echo '{"continue": false, "systemMessage": "【Solar 阻止】Researcher 不允许使用 '$TOOL_NAME'。请切换到 Coder 阶段。"}' >&2
            exit 2
        fi
        ;;
    "Architect")
        if [[ "$TOOL_NAME" == "Bash" ]]; then
            echo '{"continue": false, "systemMessage": "【Solar 阻止】Architect 不允许执行命令。设计阶段只做设计。"}' >&2
            exit 2
        fi
        ;;
esac

echo '{"continue": true}'
```

### 5.4 Stop Hook (Gate 检查)

```bash
#!/bin/bash
# hooks/solar-stop.sh
# Claude 停止时检查 Gate

STATE_FILE="$PWD/.solar/flow-state.json"

if [[ ! -f "$STATE_FILE" ]]; then
    echo '{"decision": "approve"}'
    exit 0
fi

PHASE=$(jq -r '.flow.current_phase' "$STATE_FILE")

case "$PHASE" in
    "P2")
        # G1 Gate: 设计完成检查
        # 检查是否有设计文档
        if [[ ! -f "docs/"*"DESIGN"* ]]; then
            cat << EOF
{
  "decision": "block",
  "reason": "G1 Gate 未通过",
  "systemMessage": "【G1 Gate】设计阶段必须输出设计文档 (docs/*_DESIGN.md)。请完成设计文档后再结束。"
}
EOF
            exit 0
        fi
        ;;
    "P4")
        # G2 Gate: 验证完成检查
        # 可以检查测试是否通过等
        ;;
esac

echo '{"decision": "approve"}'
```

### 5.5 PostToolUse Hook (状态更新)

```bash
#!/bin/bash
# hooks/solar-post-tool.sh
# 工具调用后更新状态

STATE_FILE="$PWD/.solar/flow-state.json"
INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
TOOL_RESULT=$(echo "$INPUT" | jq -r '.tool_result // empty')

if [[ ! -f "$STATE_FILE" ]]; then
    exit 0
fi

# 检测 Agent 宣告 (通过输出内容判断)
if [[ "$TOOL_RESULT" == *"┌─"*"Agent"* || "$TOOL_RESULT" == *"Task:"* ]]; then
    # 标记已宣告
    jq '.agent_announcement.announced = true' "$STATE_FILE" > "${STATE_FILE}.tmp"
    mv "${STATE_FILE}.tmp" "$STATE_FILE"
fi

exit 0
```

## 六、Skills 实现

### 6.1 /solar Skill (入口)

```markdown
---
name: solar
description: 启动 Solar 开发模式
user-invocable: true
argument-hint: "[start|status|phase <P1-P5>]"
---

# /solar - Solar 流程控制

## 命令

### /solar start <任务描述>

初始化流程状态：

1. 创建 `.solar/flow-state.json`
2. 分析任务复杂度
3. 设置初始阶段和 Agent
4. 输出启动信息

### /solar status

显示当前流程状态。

### /solar phase <P1-P5>

手动切换阶段（需要 Gate 通过）。

## 启动流程

当用户执行 `/solar start <任务>` 时：

1. **分析复杂度**
   - <50行 → 简单 → 直接 P3
   - 50-500行 → 中等 → P2→P3→P4
   - >500行 → 复杂 → P1→P2→P3→P4→P5

2. **初始化状态文件**
   ```bash
   mkdir -p .solar
   cat > .solar/flow-state.json << 'EOF'
   {
     "active": true,
     "task": {"description": "<任务>", "complexity": "<复杂度>"},
     "flow": {"current_phase": "P1", "current_agent": "Researcher"},
     "agent_announcement": {"required": true, "announced": false}
   }
   EOF
   ```

3. **输出启动信息**
   ```
   ┌─ ☀️ Solar ──────────────────────────────────────┐
   │ 任务: <任务描述>                                │
   │ 复杂度: 复杂 | 流程: P1→P2→P3→P4→P5            │
   ├─────────────────────────────────────────────────┤
   │ 当前阶段: P1 研究                               │
   │ 当前 Agent: 🔬 Researcher                       │
   │                                                 │
   │ 下一步: 输出 Agent 宣告，开始技术调研           │
   └─────────────────────────────────────────────────┘
   ```

4. **触发 Agent 宣告**
   宣告后开始执行。
```

### 6.2 /phase Skill (阶段转换)

```markdown
---
name: phase
description: Solar 阶段转换
user-invocable: true
argument-hint: "<next|P1|P2|P3|P4|P5>"
---

# /phase - 阶段转换

## 执行流程

1. **读取当前状态**
2. **检查 Gate 条件**
3. **更新阶段和 Agent**
4. **重置宣告状态**
5. **输出新阶段信息**

## 阶段-Agent 映射

| 阶段 | Agent | 进入条件 |
|------|-------|----------|
| P1 | Researcher | 复杂任务初始 |
| P2 | Architect | P1 完成 |
| P3 | Coder | G1 通过 |
| P4 | Tester | 代码完成 |
| P5 | Ops | G2 通过 |

## 转换时

更新 flow-state.json：
```json
{
  "flow": {
    "current_phase": "P3",
    "current_agent": "Coder"
  },
  "agent_announcement": {
    "announced": false
  }
}
```

然后必须输出新 Agent 宣告。
```

## 七、配置更新

### settings.json 更新

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "*",
        "hooks": [{"type": "command", "command": "~/.claude/hooks/solar-session-start.sh"}]
      }
    ],
    "UserPromptSubmit": [
      {
        "matcher": "*",
        "hooks": [{"type": "command", "command": "~/.claude/hooks/solar-prompt-submit.sh"}]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Edit|Write|Bash",
        "hooks": [{"type": "command", "command": "~/.claude/hooks/solar-pre-tool.sh"}]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [{"type": "command", "command": "~/.claude/hooks/solar-post-tool.sh"}]
      }
    ],
    "Stop": [
      {
        "matcher": "*",
        "hooks": [{"type": "command", "command": "~/.claude/hooks/solar-stop.sh"}]
      }
    ]
  }
}
```

## 八、执行流程示例

```
用户: /solar start 优化 Hash Join 性能

[/solar Skill 执行]
→ 创建 .solar/flow-state.json
→ 设置 P1 + Researcher
→ 输出启动横幅

用户: 开始研究

[UserPromptSubmit Hook]
→ 读取状态: P1 | Researcher | 未宣告
→ 注入: "【Solar 提醒】当前 P1 | Researcher，请先输出 Agent 宣告"

[Claude 输出]
┌─ 🔬 Researcher ─────────────────────────────────┐
│ Task: 研究 Hash Join 优化技术                    │
│ Plan:                                           │
│   1. 调研业界方案                                │
│   2. 分析适用性                                  │
└─────────────────────────────────────────────────┘

[PostToolUse Hook]
→ 检测到宣告格式
→ 更新 announced = true

[Claude 继续执行研究...]

[Claude 准备停止]

[Stop Hook]
→ 检查 P1 完成条件
→ 通过 → approve

用户: /phase next

[/phase Skill 执行]
→ P1 → P2
→ Agent: Architect
→ announced = false
→ 输出阶段转换信息

[UserPromptSubmit Hook 下次触发]
→ 提醒输出 Architect 宣告
...
```

## 九、实现计划

| 阶段 | 任务 | 优先级 |
|------|------|--------|
| 1 | 创建 flow-state.json 结构 | P0 |
| 2 | 实现 UserPromptSubmit Hook | P0 |
| 3 | 实现 /solar start Skill | P0 |
| 4 | 实现 PreToolUse Hook | P1 |
| 5 | 实现 Stop Hook (Gate) | P1 |
| 6 | 实现 /phase Skill | P1 |
| 7 | 实现 PostToolUse Hook | P2 |
| 8 | 测试和调优 | P2 |

## 十、风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| Hook 性能开销 | 每次操作延迟 | 优化脚本，快速路径 |
| 状态文件损坏 | 流程中断 | 备份 + 恢复机制 |
| Claude 忽略 systemMessage | 宣告不执行 | 多次提醒 + 阻止关键操作 |
| 用户不用 /solar | 流程不触发 | 在 CLAUDE.md 强调 |

## 十一、验收标准

- [ ] `/solar start` 正确初始化状态
- [ ] 每次提交时注入当前阶段信息
- [ ] Agent 宣告被正确触发
- [ ] 工具限制被正确执行
- [ ] Gate 检查正确阻止不合格转换
- [ ] 阶段转换正确更新状态

---

> 设计者: @Researcher + @Architect | 状态: 待审核
