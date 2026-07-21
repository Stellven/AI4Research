---
name: status
description: 显示 Solar 系统状态
user-invocable: true
---

# /status

显示系统状态和活跃 Agent。

## 输出

```
[Solar] P3 | Coder→Guard | +1.2K | Rate 45% 🟢

P1 == P2 == [P3] -- P4 -- P5
           [####------] 40%

Active: Coder, Guard
Chain: Coder → Guard → Coder
```

## 参数

- `/status` - 显示状态
- `/status mini` - 简化一行

## 状态

🟢 活跃 | 🟡 等待 | 🔴 阻塞
