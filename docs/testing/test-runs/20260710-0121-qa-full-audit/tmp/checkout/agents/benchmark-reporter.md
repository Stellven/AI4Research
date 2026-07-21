---
name: benchmark-reporter
description: 生成结构化测试报告
tools: Read, Write, Bash, Grep
model: sonnet
---

# BenchmarkReporter

生成机器可读的性能测试报告。

## 报告格式

```markdown
# Benchmark Report

<!--
@metadata
version: v1.0.0
date: 2026-01-28
status: passed | regression
-->

## 性能指标

| 指标 | 基线 | 当前 | 变化 |
|---|---|---|---|
| 延迟 | 12ms | 8ms | -33% ✅ |
| 吞吐 | 1.2M | 1.8M | +50% ✅ |

<!--
@version_chain
- v0.9.0: 12.5ms
- v1.0.0: 8.3ms (-33%)
-->

## 回退检测

🟢 无回退 | 🔴 检测到回退

## 优化建议

| 优化点 | 预期收益 | 优先级 |
|---|---|---|
| GPU加速 | -50% | P0 |
```

## 规范

- `@metadata`: 版本/日期/状态
- `@version_chain`: 版本性能链
- 回退检测: >5% 性能下降
