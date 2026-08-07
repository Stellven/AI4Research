# Dispatch

请重构这个遗留代码，按 Clean Code 和 Refactoring 方法处理；目标是减少 code smell，补 characterization test，并输出风险清单。

## 验收

- dispatch 注入后必须命中 `agent-rules-books` intent hint。
- dispatch 注入后必须把 `agent-rules-books` capability 写入 worker 可见上下文。
- telemetry sidecar 必须记录 `solar_intent_context` 和 `solar_capability_context` 为 true。
- 负例任务不得命中 `agent-rules-books`，避免全局硬塞。
