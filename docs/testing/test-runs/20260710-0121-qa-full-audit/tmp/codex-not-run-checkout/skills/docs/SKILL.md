---
name: docs
description: 生成或更新项目文档
user-invocable: true
context: fork
agent: docs
argument-hint: "[doc-type]"
---

# 文档生成

使用 Docs Agent 生成文档。

## 文档类型

- **design**: 设计文档
- **api**: API 文档
- **readme**: README 更新
- **changelog**: 变更日志
- **guide**: 用户指南

## 设计文档模板

```markdown
# <功能名称> - 设计文档

> 版本: x.x.x | 日期: YYYY-MM-DD

## 一、概述
## 二、技术方案
## 三、详细设计
## 四、实现计划
```

## 注意事项

- 保持简洁清晰
- 包含代码示例
- 及时更新
