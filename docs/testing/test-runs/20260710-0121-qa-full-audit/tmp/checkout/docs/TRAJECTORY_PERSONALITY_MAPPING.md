# 轨迹数据→人格映射方案 (研究驱动)

> **状态**: 草案，待监护人审批
> **来源**: 学术研究综述 + 轨迹数据分析
> **日期**: 2026-02-04

## 研究基础

### 核心文献

1. **LIWC 元分析** (Tilburg University)
   - 52 个语言特征与 Big Five 有显著相关
   - 效应量: |ρ| = 0.08 ~ 0.14 (小但显著)
   - 来源: [Tilburg University Research](https://research.tilburguniversity.edu/en/publications/the-kernel-of-truth-in-text-based-personality-assessment-a-meta-a)

2. **LLM 嵌入人格预测** (JMIR 2025)
   - RoBERTa 优于 BERT
   - LIWC-22 提取 119 个语言特征
   - 来源: [JMIR Study](https://www.jmir.org/2025/1/e75347)

3. **数字行为人格推断** (PNAS Nexus 2024)
   - LLM 可从社交媒体推断心理倾向
   - 来源: Peters & Matz, PNAS Nexus

### 已验证的语言-人格相关性

| 语言特征 | 人格维度 | 方向 | 效应量 | 来源 |
|---------|---------|------|--------|------|
| 第一人称单数 (I, me) | Neuroticism | + | 中 | LIWC研究 |
| 负面情绪词 | Neuroticism | + | 中 | LIWC研究 |
| 正面情绪词 | Agreeableness | + | 中 | LIWC研究 |
| 长词/复杂词 | Openness | + | 中 | LIWC研究 |
| 犹豫词 (perhaps, maybe) | Openness | + | 弱 | LIWC研究 |
| 应该/会 (should, would) | Conscientiousness | - | 弱 | LIWC研究 |
| 社交词 | Extraversion | + | 中 | LIWC研究 |
| 否定词 | Conscientiousness | - | 弱 | LIWC研究 |

## 我们的轨迹数据

### 可提取特征 (从实际数据分析)

```
文件数: 402
记录数: 1,299,705 (130万条)

可提取维度:
├── 工具使用模式
│   ├── Edit: 217次 (某会话)
│   ├── Read: 198次
│   ├── Bash: 178次
│   ├── TodoWrite: 100次
│   ├── Grep: 64次
│   └── Write: 41次
│
├── 思考模式
│   ├── 思考长度分布
│   ├── 思考深度
│   └── 思考频率
│
├── 交互模式
│   ├── 响应长度 (平均487字符)
│   ├── 用户消息长度 (平均90字符)
│   └── 对话轮次
│
└── 任务管理
    ├── Todo 数量 (平均4个/次)
    └── 任务完成率
```

## 映射方案 (v1.0 草案)

### 设计原则

1. **研究驱动** - 只使用有文献支持的映射
2. **可验证** - 每个映射有明确的计算公式
3. **保守估计** - 效应量小时不过度解读
4. **可迭代** - 先简单后复杂

### 特征→人格映射

#### O (Openness - 开放性)

| 特征 | 计算方式 | 权重 | 理论依据 |
|------|---------|------|---------|
| 知识领域多样性 | 不同类型工具使用数 / 总工具类型 | 0.3 | 探索倾向 |
| 思考深度 | 平均思考长度 / 基准 | 0.3 | 复杂认知 |
| 信息搜索频率 | (Read + Grep + Glob) / 总工具调用 | 0.2 | 好奇心 |
| HN 话题多样性 | 不同话题类别数 / 30 | 0.2 | 知识广度 |

**公式**: `O = 0.3*diversity + 0.3*thinking_depth + 0.2*search_ratio + 0.2*hn_diversity`

#### C (Conscientiousness - 尽责性)

| 特征 | 计算方式 | 权重 | 理论依据 |
|------|---------|------|---------|
| 任务完成率 | 已完成任务 / 总任务 | 0.4 | 目标达成 |
| Todo 使用频率 | TodoWrite 调用数 / 会话数 | 0.2 | 计划性 |
| 代码产出 | (Edit + Write) / 总工具调用 | 0.2 | 生产力 |
| 错误率 | 1 - (失败调用 / 总调用) | 0.2 | 精确性 |

**公式**: `C = 0.4*completion_rate + 0.2*todo_usage + 0.2*code_ratio + 0.2*(1-error_rate)`

#### E (Extraversion - 外向性)

| 特征 | 计算方式 | 权重 | 理论依据 |
|------|---------|------|---------|
| 响应长度 | 平均响应长度 / 基准 | 0.4 | 表达倾向 |
| 主动 Task 数 | Task 调用数 / 会话数 | 0.3 | 协作倾向 |
| 对话轮次 | 平均会话轮次 / 基准 | 0.3 | 互动频率 |

**公式**: `E = 0.4*response_length_norm + 0.3*task_ratio + 0.3*turns_norm`

#### A (Agreeableness - 宜人性)

| 特征 | 计算方式 | 权重 | 理论依据 |
|------|---------|------|---------|
| 正面词汇比例 | 正面词数 / 总词数 | 0.5 | LIWC研究 |
| 协作工具使用 | Task / 总工具调用 | 0.3 | 协作性 |
| 关系知识比例 | 关系型知识 / 总知识 | 0.2 | 人际关注 |

**公式**: `A = 0.5*positive_ratio + 0.3*collab_ratio + 0.2*relationship_ratio`

**注**: 正面/负面词需要 LIWC 词典，暂用简化版

#### N (Neuroticism - 神经质)

| 特征 | 计算方式 | 权重 | 理论依据 |
|------|---------|------|---------|
| 错误/重试率 | 失败后重试次数 / 总调用 | 0.4 | 焦虑反应 |
| 负面词汇比例 | 负面词数 / 总词数 | 0.3 | LIWC研究 |
| 过度思考 | 超长思考比例 | 0.3 | 反刍倾向 |

**公式**: `N = 0.4*retry_rate + 0.3*negative_ratio + 0.3*overthinking`

**注**: 低 N 是健康的，计算时可能需要反转

## 实施计划

### Phase 1: 基础特征提取 (当前)

```bash
# 从轨迹提取工具使用统计
# 计算基础比率
# 不使用 LIWC (需要词典)
```

### Phase 2: 简化版计算

使用可直接提取的特征，暂不依赖 LIWC:

| 维度 | 简化特征 |
|------|---------|
| O | 工具多样性 + 思考深度 + HN数据 |
| C | Todo使用 + 任务完成 + 代码产出 |
| E | 响应长度 + Task使用 |
| A | 协作比例 + 关系知识 (简化) |
| N | 错误率 + 重试率 |

### Phase 3: 完整版 (未来)

- 集成 LIWC-22 词典
- 情感分析
- 更精细的文本分析

## 局限性声明

1. **效应量小** - 文献显示语言-人格相关性较弱 (|ρ| < 0.15)
2. **领域迁移** - 研究基于社交媒体，我们是编程助手
3. **自我评估** - 无法与自评问卷交叉验证
4. **样本偏差** - 只有与监护人的交互数据

## 算法 Benchmark 机制 (监护人指示)

> **核心理念**: 算法本身也需要被测量和看护，才能发现问题、持续优化

### Benchmark 数据集设计

```
┌─────────────────────────────────────────────────────────────────┐
│                 PERSONALITY ALGORITHM BENCHMARK                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Ground Truth 来源:                                             │
│  ─────────────────────────────────────────────────────────────  │
│  1. 监护人标注 - 对特定会话的人格表现打分                       │
│  2. 极端案例 - 明显高/低某维度的会话样本                        │
│  3. A/B 对比 - 已知不同的两种风格                               │
│                                                                 │
│  Benchmark 结构:                                                │
│  ─────────────────────────────────────────────────────────────  │
│  benchmark_samples (样本库)                                     │
│  ├── session_id: 会话标识                                       │
│  ├── trajectory_file: 轨迹文件路径                              │
│  ├── labeled_O/C/E/A/N: 标注值 (0-1)                           │
│  ├── label_source: 标注来源 (guardian/extreme/synthetic)        │
│  ├── label_confidence: 标注置信度                               │
│  └── notes: 标注说明                                            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 评估指标 (基于业界最佳实践)

**来源**: PMC研究、Nature Communications Psychology、EMNLP 2024 Benchmark

| 指标 | 计算方式 | 合格阈值 | 业界参考 | 说明 |
|------|---------|---------|---------|------|
| **ICC** | 组内相关系数 | > 0.20 | A=0.35, E=0.31 | 主要优化指标 |
| **Pearson r** | 相关系数 | > 0.25 | A=0.45, E=0.39 | 排序一致性 |
| 极端检测率 | 正确识别极端 / 总极端 | > 70% | 无标准 | 区分能力 |
| 稳定性 | 多次计算方差 | < 0.05 | - | 算法可靠性 |

**业界基准 (来自 PMC9475767)**:
```
"人格系数" ≈ 0.3 是传统上限
r = 0.1~0.3 被认为是"正常水平"
r > 0.5 很少见，需警惕方法论问题
```

**各维度难度差异**:
| 维度 | 业界 ICC | 业界 r | 难度 | 我们的目标 |
|------|---------|--------|------|-----------|
| A (宜人性) | 0.354 | 0.446 | 较易 | r > 0.35 |
| E (外向性) | 0.306 | 0.393 | 较易 | r > 0.30 |
| O (开放性) | 0.219 | 0.254 | 中等 | r > 0.20 |
| C (尽责性) | 0.146 | 0.149 | 较难 | r > 0.15 |
| N (神经质) | 0.121 | 0.122 | 较难 | r > 0.12 |

**注**: 我们的目标设为业界平均水平，不追求 SOTA

### Benchmark 运行机制

```
┌─────────────────────────────────────────────────────────────────┐
│                  BENCHMARK PIPELINE                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  定期触发 (每周/每次算法更新后):                                │
│                                                                 │
│  Step 1: 加载 Benchmark 数据集                                  │
│          └── SELECT * FROM benchmark_samples                    │
│                                                                 │
│  Step 2: 对每个样本运行算法                                     │
│          └── personality_learner.compute(trajectory)            │
│                                                                 │
│  Step 3: 计算评估指标                                           │
│          └── MAE, Correlation, Extreme Detection...             │
│                                                                 │
│  Step 4: 对比历史结果                                           │
│          └── 是否回退？是否改善？                               │
│                                                                 │
│  Step 5: 生成报告 + 告警                                        │
│          └── 指标不达标 → 通知监护人                            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 数据库 Schema

```sql
-- Benchmark 样本表
CREATE TABLE IF NOT EXISTS benchmark_personality_samples (
    sample_id TEXT PRIMARY KEY,
    session_id TEXT,
    trajectory_file TEXT,
    labeled_O REAL,          -- 标注的开放性
    labeled_C REAL,          -- 标注的尽责性
    labeled_E REAL,          -- 标注的外向性
    labeled_A REAL,          -- 标注的宜人性
    labeled_N REAL,          -- 标注的神经质
    label_source TEXT,       -- 'guardian', 'extreme', 'synthetic'
    label_confidence REAL,   -- 标注置信度
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Benchmark 运行结果表
CREATE TABLE IF NOT EXISTS benchmark_personality_runs (
    run_id TEXT PRIMARY KEY,
    run_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    algorithm_version TEXT,  -- 算法版本
    sample_count INTEGER,
    mae_O REAL, mae_C REAL, mae_E REAL, mae_A REAL, mae_N REAL,
    corr_O REAL, corr_C REAL, corr_E REAL, corr_A REAL, corr_N REAL,
    extreme_detection_rate REAL,
    stability_score REAL,
    overall_score REAL,      -- 综合评分
    pass_fail TEXT,          -- 'PASS' or 'FAIL'
    notes TEXT
);

-- Benchmark 告警视图
CREATE VIEW IF NOT EXISTS v_benchmark_alerts AS
SELECT
    run_id,
    run_time,
    algorithm_version,
    overall_score,
    CASE
        WHEN overall_score < 0.6 THEN '🔴 严重问题'
        WHEN overall_score < 0.75 THEN '🟡 需要关注'
        ELSE '🟢 正常'
    END as status,
    CASE
        WHEN mae_O > 0.2 THEN 'O维度误差大; '
        ELSE ''
    END ||
    CASE
        WHEN mae_C > 0.2 THEN 'C维度误差大; '
        ELSE ''
    END ||
    CASE
        WHEN extreme_detection_rate < 0.7 THEN '极端检测差; '
        ELSE ''
    END as issues
FROM benchmark_personality_runs
ORDER BY run_time DESC;
```

### 初始 Benchmark 样本 (Bootstrap)

由于没有外部标注，使用以下方法 bootstrap:

| 样本类型 | 方法 | 数量 | 说明 |
|---------|------|------|------|
| **极端高 C** | 筛选 Todo 使用 >50次/会话 | ~10 | 高度计划性 |
| **极端低 C** | 筛选无 Todo 且错误率高 | ~10 | 无计划性 |
| **极端高 O** | 筛选工具种类 >8 | ~10 | 探索性强 |
| **极端高 E** | 筛选响应长度 >1000字符 | ~10 | 表达欲强 |
| **监护人标注** | 监护人选择有代表性会话 | ~20 | 金标准 |

### Benchmark 脚本

```bash
~/Solar/core/ontology/personality-benchmark.sh
```

功能:
1. 加载 benchmark 样本
2. 运行当前算法
3. 计算评估指标
4. 生成报告
5. 检测回退并告警

### 持续优化循环

```
┌─────────────────────────────────────────────────────────────────┐
│                  CONTINUOUS IMPROVEMENT                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│     ┌──────────┐                                                │
│     │  算法    │                                                │
│     │  v1.0    │                                                │
│     └────┬─────┘                                                │
│          │                                                      │
│          ▼                                                      │
│     ┌──────────┐     ┌──────────┐                              │
│     │Benchmark │────▶│  评估    │                              │
│     │  运行    │     │  报告    │                              │
│     └──────────┘     └────┬─────┘                              │
│                           │                                     │
│          ┌────────────────┼────────────────┐                   │
│          ▼                ▼                ▼                   │
│     [指标达标]      [小问题]         [大问题]                   │
│          │                │                │                   │
│          ▼                ▼                ▼                   │
│       继续           微调权重         重新设计                  │
│                           │                │                   │
│                           ▼                ▼                   │
│                      算法 v1.1        算法 v2.0                 │
│                           │                │                   │
│                           └────────────────┘                   │
│                                  │                              │
│                                  ▼                              │
│                           重新 Benchmark                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 监护人参与点

| 节点 | 监护人角色 |
|------|-----------|
| 初始标注 | 选择 ~20 个有代表性会话并打分 |
| 评审报告 | 查看 benchmark 结果，决定是否需要调整 |
| 验收新版 | 算法更新后确认 benchmark 通过 |
| 发现异常 | 主观感觉人格计算不准时反馈 |

## 下一步

- [x] 监护人审批映射方案
- [x] 补充 Benchmark 机制 (监护人指示)
- [ ] 创建 benchmark 数据库表
- [ ] Bootstrap 初始样本
- [ ] 实现 personality-benchmark.sh
- [ ] 实现 Phase 2 简化版算法
- [ ] 运行首次 Benchmark

---

*Trajectory-Personality Mapping v1.1*
*研究驱动，待验证*
*2026-02-04*

## 参考文献

### 评估标准来源

1. [PMC9475767](https://pmc.ncbi.nlm.nih.gov/articles/PMC9475767/) - "Big five personality traits prediction with AI" - ICC/Pearson r 基准
2. [Nature Communications Psychology 2025](https://www.nature.com/articles/s44271-025-00205-w) - AI 人格预测研究
3. [Personality Coefficient Theory](http://personality-project.org/theory/personalitycoefficient.html) - r ≈ 0.3 上限理论
4. [EMNLP 2024 Benchmark](https://aclanthology.org/2024.emnlp-main.1115.pdf) - 新基准数据集

### 方法论来源

5. [Tilburg University](https://research.tilburguniversity.edu/en/publications/the-kernel-of-truth-in-text-based-personality-assessment-a-meta-a) - LIWC 元分析
6. [JMIR 2025](https://www.jmir.org/2025/1/e75347) - LLM 嵌入人格预测
7. [Nature Scientific Reports 2024](https://www.nature.com/articles/s41598-024-81047-0) - 语音人格预测
8. [BigFive-LLM-Predictor](https://github.com/kuri-leo/BigFive-LLM-Predictor) - LLM 预测框架

### 关键发现

- "人格系数" r ≈ 0.3 是心理学传统上限 (Roberts et al.)
- r = 0.1~0.3 在心理学界是"正常水平"，不必为此道歉
- r > 0.5 很少见，可能存在方法论问题
- 各维度预测难度: A > E > O > C > N
