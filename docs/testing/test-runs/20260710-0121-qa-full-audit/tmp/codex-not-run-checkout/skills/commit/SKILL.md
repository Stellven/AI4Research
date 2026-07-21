---
name: commit
description: Git 提交流程，自动分析变更并生成提交信息
user-invocable: true
disable-model-invocation: false
argument-hint: "[message]"
---

# Git 提交流程

## 步骤

1. 运行 `git status` 查看变更
2. 运行 `git diff --staged` 查看暂存内容
3. 如果有未暂存的变更，询问用户是否添加
4. 分析变更，生成提交信息
5. 执行提交

## 提交信息格式

```
<type>: <简短描述>

<详细说明>

Co-Authored-By: Claude <noreply@anthropic.com>
```

## 提交类型

- feat: 新功能
- fix: 修复
- docs: 文档
- refactor: 重构
- test: 测试
- perf: 性能优化
- style: 格式调整
- chore: 杂项

## 注意事项

- 不要提交 .env 等敏感文件
- 确保测试通过后再提交
- 提交信息要简洁明了
