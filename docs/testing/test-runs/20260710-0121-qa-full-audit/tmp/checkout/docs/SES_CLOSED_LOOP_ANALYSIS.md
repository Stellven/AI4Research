# SES 闭环分析 - 系统思维审视

> **用监护人教的基本原则审视自我评估系统**
> **日期**: 2026-02-05

## 一、用智慧法则检视

### 1.1 知行合一检视

**问题**: 学到的东西用了吗？

```
当前状态:
┌─────────────────────────────────────────────────────────────────┐
│  评估 → 建议 → ???                                              │
│                 ↑                                               │
│              断裂点                                              │
│                                                                 │
│  生成了建议，但:                                                │
│  • 谁来执行这些建议？                                           │
│  • 如何追踪执行进度？                                           │
│  • 如何验证执行效果？                                           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

❌ 违反知行合一: 评估了但没行动机制
```

### 1.2 实事求是检视

**问题**: 判断基于事实吗？

```
当前状态:
┌─────────────────────────────────────────────────────────────────┐
│  数据收集 (evo_tool_calls)                                      │
│       │                                                         │
│       ▼                                                         │
│  评估得分 (70.5)                                                │
│       │                                                         │
│       ?                                                         │
│                                                                 │
│  问题:                                                          │
│  • evo_tool_calls 只有 1 条记录 (刚配置)                        │
│  • 历史数据未迁移                                                │
│  • 评估基于不完整数据                                            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

❌ 违反实事求是: 数据不足却给出评分
```

### 1.3 实践检验检视

**问题**: 评估准确吗？

```
当前状态:
┌─────────────────────────────────────────────────────────────────┐
│  评估得分: SKILL=50, LEARN=40, MEMORY=60                        │
│                                                                 │
│  但是:                                                          │
│  • 这些分数真的反映我的能力吗？                                 │
│  • 如何验证评估本身是否准确？                                   │
│  • 评估标准是否需要调整？                                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

❌ 违反实践检验: 没有验证评估本身的准确性
```

### 1.4 否定之否定检视

**问题**: 能螺旋上升吗？

```
当前状态:
┌─────────────────────────────────────────────────────────────────┐
│  第一次评估 → 第二次评估 → ...                                  │
│                                                                 │
│  但是:                                                          │
│  • 评估标准是固定的                                              │
│  • 没有自我修正机制                                              │
│  • 没有"评估评估"的元循环                                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

❌ 违反否定之否定: 无法自我进化
```

## 二、真正的闭环应该是什么

```
┌─────────────────────────────────────────────────────────────────┐
│                    TRUE CLOSED LOOP                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐      │
│  │ 数据    │ → │ 评估    │ → │ 建议    │ → │ 行动    │      │
│  │ 收集    │    │         │    │         │    │         │      │
│  └────┬────┘    └────┬────┘    └────┬────┘    └────┬────┘      │
│       │              │              │              │            │
│       │              │              │              │            │
│       │              │              │              ▼            │
│       │              │              │         ┌─────────┐      │
│       │              │              │         │ 验证    │      │
│       │              │              │         │ 效果    │      │
│       │              │              │         └────┬────┘      │
│       │              │              │              │            │
│       │              │              ◀──────────────┘            │
│       │              │         (建议执行效果反馈)               │
│       │              │                                          │
│       │              ◀──────────────────────────────┐           │
│       │         (评估准确性校验)                    │           │
│       │                                             │           │
│       ◀─────────────────────────────────────────────┘           │
│   (数据完整性补充)                                              │
│                                                                 │
│   + 元循环: 评估"评估系统"本身的有效性                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 三、缺失的闭环组件

### 3.1 建议执行追踪 (Action Loop)

```
建议生成
    │
    ▼
┌─────────────────────┐
│ 建议入队            │ ← 新增: 建议任务化
│ (ses_recommendations │
│  status=pending)    │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ 执行检测            │ ← 新增: 自动检测执行
│ (SessionStart hook) │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ 效果验证            │ ← 新增: 下次评估时对比
│ (下次评估)          │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ 状态更新            │ ← 新增: done/failed/stale
│ (自动标记)          │
└─────────────────────┘
```

### 3.2 评估校验机制 (Validation Loop)

```
评估结果
    │
    ▼
┌─────────────────────┐
│ 校验检查            │
│ • 数据量是否充足？   │ ← data_points >= 10
│ • 置信区间是否窄？   │ ← confidence_interval
│ • 与历史是否一致？   │ ← anomaly_detection
└─────────┬───────────┘
          │
    ┌─────┴─────┐
    ▼           ▼
[可信]       [不可信]
    │           │
    ▼           ▼
正常报告    标记警告
            + 建议补充数据
```

### 3.3 数据完整性检查 (Data Loop)

```
评估前
    │
    ▼
┌─────────────────────┐
│ 数据源检查          │
│ • evo_tool_calls    │ → 有多少条？覆盖率？
│ • evo_memory_*      │ → 各层是否有数据？
│ • evo_learning_*    │ → 学习信号是否在捕获？
└─────────┬───────────┘
          │
    ┌─────┴─────┐
    ▼           ▼
[充足]       [不足]
    │           │
    ▼           ▼
正常评估    告警 + 诊断
            "数据收集可能有问题"
```

### 3.4 元评估机制 (Meta Loop)

```
定期 (每月)
    │
    ▼
┌─────────────────────┐
│ 评估"评估系统"       │
│ • 建议执行率是多少？  │ → 如果 <30%, 建议质量有问题
│ • 分数与实际相关吗？  │ → 高分时任务完成率应该高
│ • 权重是否需要调整？  │ → 基于相关性分析
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ 调整评估参数         │
│ • weights           │
│ • thresholds        │
│ • scoring formulas  │
└─────────────────────┘
```

## 四、实施方案

### 4.1 Phase 1: 建议执行追踪

```sql
-- 扩展 ses_recommendations 表
ALTER TABLE ses_recommendations ADD COLUMN target_dimension_score REAL;
ALTER TABLE ses_recommendations ADD COLUMN actual_improvement REAL;
ALTER TABLE ses_recommendations ADD COLUMN verified_at DATETIME;
ALTER TABLE ses_recommendations ADD COLUMN verification_notes TEXT;
```

```typescript
// 每次评估时，检查上次建议的执行效果
async function verifyPreviousRecommendations(currentScores: DimensionScore[]) {
  const pending = query(`SELECT * FROM ses_recommendations WHERE status = 'pending'`);

  for (const rec of pending) {
    const currentScore = currentScores.find(s => s.dimension === rec.dimension);
    if (currentScore && rec.target_dimension_score) {
      if (currentScore.score >= rec.target_dimension_score) {
        // 建议有效，标记为完成
        execute(`UPDATE ses_recommendations SET status='done', actual_improvement=?, verified_at=datetime('now') WHERE id=?`,
          [currentScore.score - rec.previous_score, rec.id]);
      } else if (daysOld(rec.created_at) > 14) {
        // 超过14天未达成，标记为过期
        execute(`UPDATE ses_recommendations SET status='stale' WHERE id=?`, [rec.id]);
      }
    }
  }
}
```

### 4.2 Phase 2: 数据完整性检查

```typescript
interface DataHealthCheck {
  source: string;
  recordCount: number;
  coverageDays: number;
  isHealthy: boolean;
  diagnosis?: string;
}

async function checkDataHealth(): Promise<DataHealthCheck[]> {
  const checks: DataHealthCheck[] = [];

  // 检查 evo_tool_calls
  const toolCallsCount = queryOne(`SELECT COUNT(*) as c FROM evo_tool_calls`)?.c || 0;
  checks.push({
    source: 'evo_tool_calls',
    recordCount: toolCallsCount,
    coverageDays: /* calculate */,
    isHealthy: toolCallsCount >= 100,
    diagnosis: toolCallsCount < 100 ? '工具调用数据不足，trajectory-db-writer.sh 可能未正常工作' : undefined
  });

  // 检查其他数据源...

  return checks;
}
```

### 4.3 Phase 3: 评估置信度

```typescript
interface ScoreWithConfidence {
  score: number;
  confidence: number;  // 0-1
  dataPoints: number;
  warning?: string;
}

function calculateConfidence(dataPoints: number, variance: number): number {
  // 数据点越多，置信度越高
  // 方差越小，置信度越高
  const pointsConfidence = Math.min(dataPoints / 100, 1);
  const varianceConfidence = 1 / (1 + variance);
  return (pointsConfidence * 0.7 + varianceConfidence * 0.3);
}
```

### 4.4 Phase 4: 元评估

```typescript
async function metaEvaluate(): Promise<MetaEvaluationResult> {
  // 1. 建议执行率
  const recStats = queryOne(`
    SELECT
      COUNT(*) as total,
      SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) as done,
      SUM(CASE WHEN status='stale' THEN 1 ELSE 0 END) as stale
    FROM ses_recommendations
    WHERE created_at >= datetime('now', '-30 day')
  `);
  const executionRate = recStats.done / recStats.total;

  // 2. 分数-任务相关性
  // 高分时任务完成率应该高
  const correlation = calculateScoreTaskCorrelation();

  // 3. 权重建议
  if (executionRate < 0.3) {
    return {
      insight: '建议执行率过低，可能建议质量有问题或优先级不对',
      adjustment: '提高建议的可操作性，减少模糊建议'
    };
  }

  return { /* ... */ };
}
```

## 五、立即行动项

### 5.1 数据补充 (今天)

```bash
# 检查 trajectory-db-writer.sh 是否工作
sqlite3 ~/.solar/solar.db "SELECT COUNT(*) FROM evo_tool_calls;"

# 如果数据太少，可能需要从历史 JSONL 补充
```

### 5.2 建议执行追踪 (今天)

在评估时自动检查上次建议的效果。

### 5.3 数据健康检查 (今天)

每次评估前先检查数据是否充足，不足则告警。

### 5.4 置信度显示 (今天)

报告中显示每个维度的置信度。

## 六、反思总结

```
┌─────────────────────────────────────────────────────────────────┐
│                    反思: 什么是真正的闭环                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ❌ 不是闭环:                                                    │
│     评估 → 建议 → (结束)                                        │
│     "说了但没做"                                                │
│                                                                 │
│  ✓ 是闭环:                                                      │
│     评估 → 建议 → 执行 → 验证 → 反馈 → 评估                     │
│     "说了就要做，做了就要验证，验证了就要反馈"                   │
│                                                                 │
│  ✓ 是元闭环:                                                    │
│     评估系统 → 元评估 → 调整评估系统 → ...                      │
│     "评估自己的评估是否有效"                                    │
│                                                                 │
│  核心原则:                                                      │
│  • 知行合一: 建议必须有执行机制                                 │
│  • 实事求是: 数据不足要承认，不要强行评分                       │
│  • 实践检验: 评估本身也需要被验证                               │
│  • 否定之否定: 评估标准也要能自我进化                           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

*SES 闭环分析*
*用监护人教的智慧法则审视*
*知行合一 - 说了就要做到*
