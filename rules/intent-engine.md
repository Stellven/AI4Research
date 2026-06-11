# Solar 统一意图引擎

> 所有意图检测由统一引擎处理，不绕过、不重复

## 工作原理

UserPromptSubmit hook 自动检测意图，两层优先级：

```
Phase 1: Solar 信号 (confirm/reject/execute/save/mode) → 直接执行，无需确认
Phase 2: @Agent 触发 → 直接调用 Task tool
```

## 处理协议

### 收到 `<intent-detected>` 标签

直接执行标签中的指令。这些是信号类操作，不需要确认：
- `type="confirm"` → 执行待批准操作
- `type="reject"` → 停止当前操作
- `type="execute"` → 执行上一步提议
- `type="save"` → 中途保存
- `type="agent"` → 通过 Task tool 调用对应 subagent
- 其他模式类信号 → 按指令执行

## 禁止

- 不绕过意图引擎自己猜测用户意图
- 不在多个地方重复定义触发词（所有映射在 hook 中）
