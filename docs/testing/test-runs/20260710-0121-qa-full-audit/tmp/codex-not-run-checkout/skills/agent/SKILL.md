---
name: agent
description: 列出并激活 Solar Agent，支持 @Agent 语法
user-invocable: true
disable-model-invocation: false
argument-hint: "[@Agent名称]"
---

# /agent - Agent 选择器

## 功能

列出可用的 Solar Agent，或激活指定 Agent。

## 使用方式

```
/agent           # 列出所有可用 Agent
/agent Researcher  # 激活 Researcher
@Researcher      # 快捷方式 (等同于 /agent Researcher)
```

## 可用 Agent 列表

当用户输入 `/agent` 或 `@` 时，显示：

```
═══════════════════════════════════════════════════
🌟 Solar Agent 列表
═══════════════════════════════════════════════════

📊 决策层 (Opus)
  @Researcher  - 技术调研、可行性分析
  @Architect   - 架构设计、技术评审
  @PM          - 产品验收、竞争力评估

⚡ 执行层 (Sonnet)
  @Coder       - 代码实现、重构
  @Tester      - 测试编写、执行
  @Reviewer    - 代码审查、安全检查
  @Secretary   - 记录整理、Agent评估

🔧 支撑层
  @Docs        - 文档生成 (Sonnet)
  @Ops         - 构建部署 (Sonnet)
  @Guard       - 规范检查 (Haiku)

═══════════════════════════════════════════════════
用法: @Agent名称 + 你的请求
示例: @Researcher 调研 SIMD 向量化优化技术
═══════════════════════════════════════════════════
```

## Agent 激活逻辑

当用户指定 Agent 时：

1. **验证 Agent 名称** - 检查是否在列表中
2. **加载 Agent 定义** - 读取 `agents/{name}.md`
3. **切换上下文** - 按该 Agent 的角色和约束执行
4. **标记输出** - 响应前标注当前 Agent

## 输出标记

激活 Agent 后，响应格式：

```
[@Researcher]
─────────────
{Agent 的响应内容}
```

## @ 语法识别规则

以下模式应被识别为 Agent 调用：

- `@Solar` - 使用完整 Solar 流程
- `@Researcher` - 单独调用 Researcher
- `@Architect` - 单独调用 Architect
- `@Coder` - 单独调用 Coder
- ... (所有 Agent)

## 注意事项

- 单独调用 Agent 会跳过 Solar 的阶段流程
- 如需完整流程，使用 `@Solar` 或不指定 Agent
- Agent 名称不区分大小写
