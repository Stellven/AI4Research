# Solar 铁律: 编码精简模式

> **来源**: LiveCodeBench 外部验证 — Harness 规则导致编码输出膨胀40%被截断
> **核心问题**: 设计/分析规则在纯编码场景浪费 token，应切换为精简模式

## 触发条件

当任务满足以下**全部条件**时进入编码精简模式：
- 不涉及设计/架构/规则制定
- 明确要求输出代码（非分析报告）
- 不需要多方案对比或权衡分析

触发词识别：
- "solve/implement/write code/写代码/解这道题"
- LeetCode/Codeforces/AtCoder 等竞赛平台题
- 函数签名给出，只需填写实现

## 精简模式规则

进入此模式时，**只保留**以下规则：
1. **编码边界清单** (coding-edge-cases) — 空/单/极端值检查
2. **禁止 Mock** — 但编码竞赛题通常不涉及

**必须关闭**：
- ❌ 设计完整性 (design-completeness) — 不需要伪代码语法标准
- ❌ 分析模板 (analysis-template) — 不需要量化证据链
- ❌ 输出持久化 (output-persist) — 编码输出不需要存知识库
- ❌ 约束验证 (constraint-verification) — 竞赛题约束由测试用例验证

## 输出格式

```
## 实现
```python
[code only, 完整可运行]
```

## 测试验证 (1-3行)
- case1: input → expected ✓
- case2: input → expected ✓

## 复杂度
- Time: O(?)
- Space: O(?)
```

**禁止**：PLAN/PATCH/RISKS/FALLBACK 等冗余段落

## Token 预算

| 任务类型 | 最大输出 token |
|---------|-------------|
| Easy | 500 |
| Medium | 800 |
| Hard | 1500 |

---

*Coding Compact Mode v1.0*
*建立于: 2026-04-08*
*来源: LiveCodeBench 验证 — 编码模式 token 膨胀修复*
