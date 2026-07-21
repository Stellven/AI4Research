---
name: skill-creator
description: 交互式创建新的 Claude Code Skill
user-invocable: true
disable-model-invocation: false
argument-hint: "[skill 名称]"
---

# /skill-creator - Skill 创建向导

## 功能

交互式引导创建符合规范的 Claude Code Skill。

## 执行步骤

### 1. 收集信息

询问用户：
- **名称**: skill 的唯一标识 (小写, 连字符)
- **描述**: 一句话说明功能
- **触发方式**: 用户调用 / 模型自动调用 / 两者
- **参数**: 是否需要参数

### 2. 生成 SKILL.md

```markdown
---
name: {name}
description: {description}
user-invocable: {true/false}
disable-model-invocation: {true/false}
argument-hint: "{hint}"
---

# /{name} - {title}

## 功能

{detailed_description}

## 执行步骤

1. 步骤一
2. 步骤二
3. 步骤三

## 输出格式

```
预期输出示例
```
```

### 3. 创建目录结构

```bash
mkdir -p ~/.claude/skills/{name}
# 写入 SKILL.md
```

### 4. 验证

- 检查 frontmatter 格式
- 确认必填字段完整
- 重启 Claude Code 生效

## Skill 规范

### Frontmatter 字段

| 字段 | 必填 | 说明 |
|------|------|------|
| name | ✅ | 唯一标识符 |
| description | ✅ | 简短描述 |
| user-invocable | ✅ | 用户可通过 / 调用 |
| disable-model-invocation | ❌ | 禁止模型自动调用 |
| argument-hint | ❌ | 参数提示 |

### 最佳实践

- 名称使用小写和连字符: `my-skill`
- 描述控制在 50 字以内
- 步骤清晰、可执行
- 包含输出示例

## 输出

```
✓ Skill 已创建: ~/.claude/skills/{name}/SKILL.md

请重启 Claude Code 以加载新 skill。
使用方式: /{name}
```
