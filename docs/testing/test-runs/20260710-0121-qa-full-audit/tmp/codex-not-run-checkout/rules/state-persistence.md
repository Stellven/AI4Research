# Solar 铁律: 状态持久化

> 对话是缓存，文件是真相。把关键状态从对话搬到外部载体。

## 存储层级

| 层级 | 载体 | 特性 |
|------|------|------|
| L0 Cache | Claude 对话 | 最易失，随时被压缩 |
| L1 Cache | 工作区文件 | 持久，可编辑 |
| L2 Cache | .solar/ 状态文件 | 结构化，可恢复 |
| WAL+CKP | git 历史 | 不可变，可回滚 |

**唯一真相源**: `.solar/STATE.md`, `.solar/DECISIONS.md`, `.solar/LOG/`

## 四条铁律

1. 新会话第一步 → 读 STATE.md
2. compact 前 → 必须更新 STATE.md
3. 完成子任务 → 更新 Progress + git commit
4. 关键约束 → 禁止只写在对话里，必须进入 STATE.md

## STATE.md 五段式

```
# Mission — 一句话目标
# Constraints — 不可破坏的约束
# Current Plan — Top-5 步骤
# Decisions — [日期] 选择 X 而不是 Y：原因
# Progress — Done / In-Progress / Blocked
# Next Actions — 精确到命令/文件/验证
```

## MUST 触发条件

| 触发条件 | 更新内容 | 时机 |
|----------|----------|------|
| 讨论新任务规划 | Mission + Plan | 下一个 action 必须 Edit STATE.md |
| 监护人说"好"/"批准" | Progress.Done | 立即 Edit STATE.md |
| 完成子任务 | Progress.Done | 完成后立即 |
| 开始新任务 | Progress.In-Progress | 开始前先更新 |
| 做出重要决策 | Decisions | 决策后立即 |
| 遇到阻塞 | Progress.Blocked | 发现时立即 |

**"立即" = 下一个工具调用必须是 Edit STATE.md**

## 自动 Hook

| Hook | 触发 | 作用 |
|------|------|------|
| PostToolUse | 每10次工具调用 | 提醒检查 STATE.md |
| SessionEnd | 会话结束 | 自动更新 AUTO-PROGRESS |

## 智能重新规划触发器

> **来源**: Plan-and-Act 研究，基于失败模式的动态重新规划
> **目的**: 自动检测执行问题，触发战略家重新规划

### 何时触发重新规划

使用 `failure-analyzer.ts` 的 `shouldReplan()` 函数判断：

```typescript
import { shouldReplan, analyzeFailurePatterns } from '~/.claude/core/failure-analyzer';

// 判断是否需要重新规划
if (shouldReplan(executionHistory, consecutiveErrors)) {
  // 触发战略家重新规划
  console.log('⚠️ 检测到执行问题，建议重新规划');
}
```

### 触发条件（满足任一即触发）

| 条件 | 阈值 | 说明 |
|------|------|------|
| 连续失败 | > 2 次 | 同一步骤反复失败 |
| 权限问题 | > 1 次 | 可能需要改变策略 |
| 逻辑错误 | > 2 次 | 说明方案有问题 |
| 总失败率 | > 50% | 步骤 > 3 且失败率过半 |

### 重新规划流程

```
执行任务 → 记录失败 → 分析失败模式
                             │
                    ┌────────┴────────┐
                    ▼                 ▼
              [不需要重新规划]   [需要重新规划]
                    │                 │
                    ▼                 ▼
              继续执行          治理官分析失败
                                      │
                                      ▼
                              战略家重新规划
                                      │
                                      ▼
                              更新 STATE.md Plan
                                      │
                                      ▼
                              从新计划继续执行
```

### 失败模式分析

重新规划前，治理官必须使用 `failure-analyzer.ts` 生成失败分析报告：

```typescript
import { generateFailureReport, analyzeFailurePatterns } from '~/.claude/core/failure-analyzer';

// 生成失败分析报告
const report = generateFailureReport(executionHistory);

// 输出报告
console.log(report);
// 示例输出：
// ⚠️ 失败模式分析：
//
// **PERMISSION** (2次)
// - 建议：权限问题，检查文件权限、API 密钥、或请求监护人授权
// - 示例：Error: EACCES: permission denied
//
// **LOGIC** (3次)
// - 建议：逻辑错误，检查代码逻辑、类型定义、或调用牛马审查
// - 示例：TypeError: Cannot read property 'x' of undefined
```

### STATE.md 更新要求

重新规划后，必须更新 STATE.md：

1. **Decisions** 部分添加：
   ```markdown
   - [日期] 重新规划：因为 [失败原因]，放弃原方案 [X]，改用 [Y]
   ```

2. **Current Plan** 部分替换为新计划

3. **Progress.Blocked** 记录原失败原因：
   ```markdown
   - Blocked (已解决): [原失败步骤] - 失败原因: [分析结果] - 新方案: [Y]
   ```

### 自检清单

任务执行失败时：

- [ ] 记录了失败到 executionHistory 吗？
- [ ] 调用 shouldReplan() 判断是否需要重新规划？
- [ ] 如果需要重新规划，生成了失败分析报告吗？
- [ ] 治理官审核了失败模式吗？
- [ ] 战略家基于失败分析重新规划了吗？
- [ ] STATE.md 的 Decisions/Plan/Progress.Blocked 更新了吗？
