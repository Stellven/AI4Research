---
name: report
description: 技术报告模板 - 基于 ADR 和业界最佳实践
user-invocable: true
argument-hint: "[full|adr|brief]"
---

# /report - 技术报告模板

基于 [ADR](https://adr.github.io/)、[MADR](https://adr.github.io/madr/) 和业界最佳实践。

## 使用

```
/report full   完整技术报告
/report adr    架构决策记录 (ADR)
/report brief  精简报告
```

---

## 1. 完整技术报告模板 (`/report full`)

```markdown
# [项目名称] 技术报告

> 版本: x.x.x | 日期: YYYY-MM-DD | 状态: Draft/Review/Final

---

## Executive Summary

[150-300字概述：目的、方法、关键发现、结论]

---

## 一、背景与愿景

### 1.1 问题陈述
- **业务痛点**: [具体问题描述]
- **技术挑战**: [技术限制/瓶颈]
- **市场机会**: [为什么现在做]

### 1.2 目标与成功标准
| 目标 | 指标 | 基线 | 目标值 |
|------|------|------|--------|
| 性能提升 | 延迟 | 100ms | <50ms |
| ... | ... | ... | ... |

### 1.3 范围与约束
- **In Scope**: ...
- **Out of Scope**: ...
- **约束条件**: 时间/预算/技术栈

---

## 二、技术分析

### 2.1 技术趋势
| 趋势 | 影响 | 机会 |
|------|------|------|
| ... | ... | ... |

### 2.2 业界 SOTA (State of the Art)
| 方案 | 性能 | 优势 | 劣势 |
|------|------|------|------|
| 方案A | ... | ... | ... |
| 方案B | ... | ... | ... |

### 2.3 竞品分析
[关键竞品的技术方案对比]

---

## 三、技术决策 (ADR 格式)

### ADR-001: [决策标题]

**Status**: Accepted | Proposed | Deprecated | Superseded

**Context**:
[决策背景和面临的问题]

**Decision**:
[做出的决策]

**Consequences**:
- ✅ 好处: ...
- ⚠️ 代价: ...
- 📋 后续: ...

### ADR-002: ...

---

## 四、实现历程

### 4.1 技术选型与验证

| 候选 | 测试结果 | 结论 |
|------|----------|------|
| 方案A | 延迟 80ms | ❌ 不满足 |
| 方案B | 延迟 45ms | ✅ 采用 |

### 4.2 关键突破

#### 挑战 1: [问题描述]
- **尝试**: [失败的方案]
- **突破**: [成功的方案]
- **洞见**: [学到了什么]

### 4.3 核心实现
```
[关键代码/架构图/流程图]
```

---

## 五、效果评估

### 5.1 性能结果
| 指标 | 基线 | 目标 | 实际 | 状态 |
|------|------|------|------|------|
| 延迟 | 100ms | <50ms | 35ms | ✅ |
| 吞吐 | 1K/s | >5K/s | 8K/s | ✅ |

### 5.2 vs SOTA 对比
| 维度 | SOTA | 我们 | 差异 |
|------|------|------|------|
| ... | ... | ... | +X% |

### 5.3 业务价值
[具体的业务收益/用户价值]

---

## 六、经验与教训

### 6.1 做对了什么
1. ...
2. ...

### 6.2 可以改进的
1. ...
2. ...

### 6.3 踩过的坑
| 坑 | 原因 | 解决 |
|-----|------|------|
| ... | ... | ... |

---

## 七、后续规划

### 短期 (1-3个月)
- [ ] ...

### 中期 (3-6个月)
- [ ] ...

### 长期
- [ ] ...

---

## 附录

- A. 术语表
- B. 参考资料
- C. 变更历史
```

---

## 2. ADR 模板 (`/report adr`)

基于 [MADR](https://adr.github.io/madr/) 格式：

```markdown
# ADR-NNN: [简短标题]

| 元数据 | 值 |
|--------|-----|
| Status | Proposed / Accepted / Deprecated / Superseded |
| Date | YYYY-MM-DD |
| Deciders | @name1, @name2 |
| Supersedes | ADR-XXX (如适用) |

## Context

[描述问题背景、驱动因素、约束条件]

## Decision Drivers

* [driver 1, e.g., 性能要求]
* [driver 2, e.g., 可维护性]
* ...

## Considered Options

1. [Option 1]
2. [Option 2]
3. [Option 3]

## Decision Outcome

**Chosen option**: "[Option X]"

**Reason**: [简要说明选择原因]

### Consequences

**Good**:
* [positive consequence 1]
* ...

**Bad**:
* [negative consequence 1]
* ...

**Neutral**:
* [neutral consequence 1]
* ...

## Pros and Cons of Options

### Option 1: [名称]

* ✅ Good: ...
* ✅ Good: ...
* ❌ Bad: ...

### Option 2: [名称]

* ✅ Good: ...
* ❌ Bad: ...
* ❌ Bad: ...

## Links

* [Link 1](url)
* Supersedes [ADR-XXX](link)
```

---

## 3. 精简报告 (`/report brief`)

```markdown
# [项目] 技术简报

**日期**: YYYY-MM-DD | **状态**: ✅ 完成

## 背景
[1-2句问题描述]

## 决策
[1-2句技术选择]

## 结果
| 指标 | 结果 |
|------|------|
| 性能 | +50% |
| ... | ... |

## 下一步
- [ ] ...
```

---

## 最佳实践

1. **一个 ADR 一个决策** - 不要混合多个决策
2. **保持简洁** - 能用表格不用段落
3. **状态明确** - Proposed → Accepted → Deprecated
4. **定期回顾** - 每月检查 ADR 与实际是否一致
5. **代码审查时引用** - 在 PR 中链接相关 ADR

---

## 参考

- [ADR GitHub](https://adr.github.io/)
- [MADR Template](https://adr.github.io/madr/)
- [joelparkerhenderson/architecture-decision-record](https://github.com/joelparkerhenderson/architecture-decision-record)
- [AWS ADR Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/adr-process.html)
