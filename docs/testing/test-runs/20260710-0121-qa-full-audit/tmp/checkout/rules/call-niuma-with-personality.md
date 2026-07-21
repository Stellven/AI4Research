# Solar 铁律: 调牛马带人格

> 调用任何牛马必须注入 D&D KNOBS 人格

## 调用方式

**推荐**: `buildNiumaCall()` (自动注入)
```typescript
import { buildNiumaCall } from '~/.claude/core/solar-farm/call-niuma';
const { system, prompt } = buildNiumaCall({ model, task, context, outputFormat });
await mcp__brain-router__complete({ model, system, prompt });
```

**手动注入最低要求**:
```
你是 [昵称]，D&D 角色是 [builder/verifier/architect/judge/explorer/creator]
KNOBS: rigor=X, skepticism=X, explore=X, decide=X, risk=X,
       tool=X, compression=X, check=X, empathy=X, compete=X
LEVEL=X (1-5)
```

## 牛马 D&D 速查

| 牛马 | 昵称 | 角色 | 特点 |
|------|------|------|------|
| gemini-2.5-pro | 稳健派 | verifier | 严谨一致 |
| gemini-3-pro | 探索派 | explorer | 创新热情 |
| deepseek-v3 | 创想家 | creator | 创意中文 |
| deepseek-r1 | 审判官 | judge | 深推质疑 |
| glm-5 | 智囊 | architect | 战略决策 |
| glm-5 | 建设者 | builder | 日常编码 |

完整定义: `~/.claude/core/solar-farm/niumao-anchors.json`

## 约束注入机制 (Constraint Injection)

> **来源**: Plan-and-Act 研究，约束感知的提示工程
> **目的**: 确保牛马严格遵守任务约束，避免越界行为

### 什么是约束

约束是任务执行时**必须遵守**的限制条件，通常存储在 `.solar/STATE.md` 的 `Constraints` 部分：

```markdown
# Constraints
- 不破坏现有 API 接口
- 性能不能回退超过 5%
- 不引入新的外部依赖
- 必须保持向后兼容
```

### 为什么需要约束注入

**问题**: 牛马（LLM）可能：
- 为了"优化"而破坏接口
- 为了"简洁"而引入新依赖
- 为了"性能"而牺牲兼容性

**解决**: 在调用牛马时，将约束明确注入到 system prompt 中，并要求牛马在输出中证明检查了约束。

### 约束注入模板

```typescript
// 从 STATE.md 读取约束
const constraints = await readConstraintsFromState();

// 构建约束注入的 system prompt
const systemPrompt = `你是 [昵称]，D&D 角色是 [角色类型]
KNOBS: rigor=X, skepticism=X, explore=X, ...
LEVEL=X

**约束条件（必须严格遵守）：**
${constraints.map(c => `- ${c}`).join('\n')}

**输出要求：**
在你的回复末尾，必须包含 "约束检查" 部分，证明你检查了上述所有约束。

格式：
\`\`\`
约束检查：
✓ [约束1] - 通过 [如何遵守的]
✓ [约束2] - 通过 [如何遵守的]
\`\`\`
`;

// 调用牛马
await mcp__brain_router__complete({
  model: "glm-5",
  system: systemPrompt,
  prompt: "任务描述..."
});
```

### 读取约束的辅助函数

```typescript
/**
 * 从 STATE.md 读取约束条件
 */
async function readConstraintsFromState(): Promise<string[]> {
  const stateContent = await Deno.readTextFile('.solar/STATE.md');

  // 提取 Constraints 部分
  const constraintsMatch = stateContent.match(/# Constraints\n([\s\S]*?)(?=\n#|$)/);
  if (!constraintsMatch) return [];

  // 解析约束列表
  const constraintLines = constraintsMatch[1]
    .split('\n')
    .filter(line => line.trim().startsWith('-'))
    .map(line => line.replace(/^-\s*/, '').trim());

  return constraintLines;
}
```

### 失败模式注入 (与约束配合)

如果任务之前失败过，将失败分析结果也注入到提示中：

```typescript
import { analyzeFailurePatterns, generateFailureReport } from '~/.claude/core/failure-analyzer';

// 分析历史失败
const failureReport = generateFailureReport(executionHistory);

// 注入到提示
const systemPrompt = `...

**失败模式分析：**
${failureReport}

注意：请避免重复相同类型的错误。
`;
```

### 完整示例：调用牛马执行有约束的任务

```typescript
import { buildNiumaCall } from '~/.claude/core/solar-farm/call-niuma';
import { analyzeFailurePatterns } from '~/.claude/core/failure-analyzer';

async function executeConstrainedTask(
  model: string,
  task: string,
  executionHistory: ExecutionStep[] = []
) {
  // 1. 读取约束
  const constraints = await readConstraintsFromState();

  // 2. 分析失败模式（如果有历史）
  const failurePatterns = executionHistory.length > 0
    ? analyzeFailurePatterns(executionHistory)
    : new Map();

  // 3. 构建约束感知的提示
  const { system, prompt } = buildNiumaCall({
    model,
    task,
    constraints,  // 传入约束
    failurePatterns: Array.from(failurePatterns.values())
  });

  // 4. 调用牛马
  const result = await mcp__brain_router__complete({
    model,
    system,
    prompt
  });

  // 5. 验证约束检查
  if (!result.includes('约束检查')) {
    console.warn('⚠️ 牛马输出缺少约束检查部分！');
  }

  return result;
}
```

### 自检清单

调用牛马执行重要任务前：

- [ ] STATE.md 中定义了约束吗？
- [ ] 约束已注入到 system prompt 吗？
- [ ] 要求牛马输出约束检查了吗？
- [ ] 如果有失败历史，失败模式已注入吗？
- [ ] 牛马输出包含约束检查部分吗？
