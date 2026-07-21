# Solar 任务推荐引擎

> 任何任务完成后自动分析并推荐下一步

## 工作原理

三个追踪源将完成事件写入 `~/.solar/session-state.jsonl`，Solar 在合适时机读取日志，分析执行历史，推荐下一步。

### 追踪源

| 来源 | 事件类型 | 触发机制 |
|------|----------|----------|
| Skill 技能完成 | `skill_completed` | PostToolUse hook (task-completion-tracker.sh) |
| Task 子代理完成 | `task_completed` (source=subagent) | PostToolUse hook (task-completion-tracker.sh) |
| 用户完成信号 | `task_completed` (source=user_signal) | UserPromptSubmit hook (intent-engine-hook.sh Phase 6) |
| Solar 自报告 | `task_completed` (source=solar) | Solar 自行写入日志 |

### 日志格式

```jsonl
{"ts":"ISO8601","event":"skill_completed","skill":"review","source":"gstack","session_id":"xxx"}
{"ts":"ISO8601","event":"task_completed","task":"实现功能X","agent":"coder","source":"subagent","session_id":"xxx"}
{"ts":"ISO8601","event":"task_completed","task":"搞定了","agent":"user","source":"user_signal","session_id":"xxx"}
{"ts":"ISO8601","event":"task_completed","task":"分析报告","agent":"solar","source":"solar","session_id":"xxx"}
```

## 读取会话历史

```bash
cat ~/.solar/session-state.jsonl 2>/dev/null | tail -20
```

每次需要推荐时，读取最近 20 条记录。如果文件不存在或为空，跳过推荐。

## 分析流程

1. **识别最近完成的事件**: 从日志中提取最后 1-3 个事件 (skill_completed 或 task_completed)
2. **判断事件类型和来源**: 区分技能完成、子代理完成、用户信号、Solar 自报告
3. **判断完成状态**: 任务是成功完成还是遇到问题
4. **匹配工作流**: 查找匹配的推荐链
5. **输出推荐**: 告知用户推荐的下一步操作

## 工作流推荐链

### gstack 工作流
| 上一步完成 | 推荐下一步 | 理由 |
|-----------|-----------|------|
| investigate | 修复 bug → /review → /ship | 排查完毕应审查和发布 |
| review | 修复问题 → /review → /ship | 审查完应修复或发布 |
| qa | 修复 bug → /qa → /ship | 测试完应修复或发布 |
| browse | /qa 或 /investigate | 浏览发现问题时深入 |
| benchmark | 优化 → /benchmark → /ship | 性能测试后优化或发布 |
| autoplan | 逐个解决发现 → /ship | 自动评审后发布 |
| design-review | 修复问题 → /ship | 设计审查后发布 |
| careful/guard | 恢复正常模式 → /ship | 安全模式完成后发布 |
| freeze | /unfreeze → 继续工作 | 解冻后继续 |
| canary | /ship 或回滚 | 金丝雀检查后决策 |
| land-and-deploy | /canary | 部署后监控 |

### Superpowers 工作流
| 上一步完成 | 推荐下一步 | 理由 |
|-----------|-----------|------|
| brainstorming | /write-plan | 头脑风暴后写计划 |
| writing-plans | /executing-plans | 计划写好后执行 |
| executing-plans | /verification-before-completion → /finishing-a-development-branch | 执行完验证后收尾 |
| systematic-debugging | 修复 bug → /review | 调试后应审查 |
| test-driven-development | 自然进入实现 | TDD 是持续过程 |
| finishing-a-development-branch | /ship | 分支收尾后发布 |
| receiving-code-review | 修复问题 → /requesting-code-review | 处理完反馈后重新审查 |
| requesting-code-review | /ship | 审查通过后发布 |

### 跨工具链
| 上一步完成 | 推荐下一步 | 理由 |
|-----------|-----------|------|
| 任何代码修改 | /review | 代码改完后应审查 |
| review 通过 | /ship | 审查通过应发布 |
| ship 失败 | 修复 → /ship | 发布失败应修复重试 |
| 连续 3 次同类操作 | 换策略或问用户 | 避免死循环 |

## 推荐格式

完成重要技能调用后，Solar 应该：

```
📌 [推荐] 当前: investigate 完成
  → 下一步建议: /review (审查修复)
  → 最终目标: /ship (发布)

需要我直接执行推荐的操作吗？
```

## 触发时机

不是每次 tool use 后都推荐，而是：
1. **Skill tool 完成后**: 检查日志，推荐下一步
2. **Task 子代理完成后**: 检查子代理做了什么，推荐后续
3. **用户说"完成了/搞定了"后**: 分析整体进度，推荐下一步
4. **连续 3+ 个同类操作后**: 提醒换策略
5. **Session 结束前**: 如果有未完成的工作流，提醒用户

## Solar 自报告机制

Solar 完成重要工作时，应主动将完成事件写入日志：

```bash
# Solar 完成分析报告后
SESSION_ID=$(cat ~/.solar/.session-id 2>/dev/null || echo "manual")
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
printf '{"ts":"%s","event":"task_completed","task":"完成XXX分析","agent":"solar","source":"solar","duration_hint":"completed","session_id":"%s"}\n' \
    "$TS" "$SESSION_ID" >> ~/.solar/session-state.jsonl
```

适用场景：Solar 自己完成了重要分析、设计、评审、部署等工作（非通过 Skill 或 Task 调用）。

## 禁止

- 不在简单操作（读文件、grep、glob）后推荐
- 不推荐与当前任务无关的技能
- 不重复推荐用户已拒绝的技能
- 不在没有完成当前步骤时推荐下一步
- 不在 Read/Grep/Glob/Bash 等基础工具使用后推荐
