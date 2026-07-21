---
name: test
description: 运行测试套件并分析结果
user-invocable: true
context: fork
agent: tester
argument-hint: "[test-pattern]"
---

# 测试运行

使用 Tester Agent 运行测试。

## 自动检测项目类型

- Node.js: `npm test`
- Python: `pytest`
- Rust: `cargo test`
- C++: `ctest`
- Go: `go test ./...`

## 步骤

1. 检测项目类型
2. 运行测试命令
3. 分析结果
4. 报告失败原因
5. 提供修复建议

## 输出格式

```
测试结果:
├── 通过: X 个
├── 失败: Y 个
├── 跳过: Z 个
└── 覆盖率: XX%

失败详情:
1. test_name - 错误信息
```
