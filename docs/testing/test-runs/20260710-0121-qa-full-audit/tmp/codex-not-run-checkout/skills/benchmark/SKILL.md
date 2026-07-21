---
name: benchmark
description: 运行性能基准测试
user-invocable: true
context: fork
agent: ops
argument-hint: "[benchmark-name]"
---

# 性能基准测试

使用 Ops Agent 运行基准测试。

## 测试要求

- 最少 10 次迭代
- 使用中位数报告
- 剔除异常值 (IQR 方法)
- 报告标准差

## 步骤

1. 识别基准测试目标
2. 运行多次迭代
3. 收集性能数据
4. 统计分析
5. 与基线对比

## 输出格式

```
基准测试结果:
├── 测试: <name>
├── 迭代: <n> 次
├── 中位数: <value> ms
├── 标准差: <value> ms
├── 最小值: <value> ms
├── 最大值: <value> ms
└── vs 基线: <ratio>x
```

## 注意事项

- 使用中位数而非平均值
- 剔除明显异常值
- 保持测试环境一致
