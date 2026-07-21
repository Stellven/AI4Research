---
name: pr
description: 创建 Pull Request，自动生成描述
user-invocable: true
argument-hint: "[base-branch]"
---

# PR 创建流程

## 步骤

1. 检查当前分支状态
2. 确认已推送到远程
3. 分析所有提交变更
4. 生成 PR 描述
5. 使用 `gh pr create` 创建

## PR 模板

```markdown
## Summary
<1-3 bullet points>

## Changes
<详细变更列表>

## Test Plan
<测试方案>

## Checklist
- [ ] 测试通过
- [ ] 文档更新
- [ ] 代码审查

Generated with Claude Code
```

## 注意事项

- 确保所有变更已提交
- 确保已推送到远程
- PR 标题要简洁明了
