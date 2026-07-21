---
name: review
description: 代码审查流程，分析代码质量和潜在问题
user-invocable: true
context: fork
agent: reviewer
argument-hint: "[pr-number or file-path]"
---

# 代码审查

使用 Reviewer Agent 进行代码审查。

## 如果提供 PR 号

分析 PR 的所有变更:
- 正确性
- 安全性
- 性能
- 可维护性
- 一致性

## 如果提供文件路径

审查指定文件的代码质量。

## 输出格式

```markdown
## 审查结果: [通过/需修改/拒绝]

### 严重问题 (必须修复)
1. file:line - 问题描述

### 警告 (建议修复)
1. file:line - 问题描述

### 建议 (可选)
1. file:line - 优化建议

### 总结
...
```
