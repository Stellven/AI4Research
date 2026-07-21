# Solar 铁律: MemPalace 日记协议

> **来源**: MemPalace v3.0 深度集成 — 激活 AAAK 日记系统
> **核心**: 会话关键节点写入 MemPalace 日记，跨会话可追溯

## 铁律定义

在以下时机，必须调用 `mcp__mempalace__mempalace_diary_write` 写入 AAAK 格式日记：

### 触发时机

| 时机 | 触发条件 | 日记内容 |
|------|----------|----------|
| 会话启动 | 启动宣告完成后 | SESSION:日期|启动.状态概述|ALC:xxx|★★★ |
| 重大决策 | DECISIONS.md 更新后 | DECISION:日期|决策内容|原因|★★★★ |
| 任务委派 | brain-router 调用后 | DELEGATE:模型|任务类型|结果|★★ |
| 错误恢复 | failure-analyzer 报告后 | ERROR:类型|根因|修复|★★★ |
| 压缩前 | PreCompact hook 触发 | COMPACT:日期|本次会话摘要|关键产出|★★★★ |
| 会话结束 | Stop hook 触发 | SESSION-END:日期|总产出|遗留问题|★★★★ |

### AAAK 实体码

| 码 | 含义 | 码 | 含义 |
|----|------|----|------|
| SOL | Solar | HGR | 昊哥 (监护人) |
| TLL | ThunderLLAMA | CLG | ClawGate |
| SMX | Solar-MAX | DRV | deepseek-r1 |
| DV3 | deepseek-v3 | GL5 | glm-5 |
| G2P | gemini-2.5-pro | G3P | gemini-3-pro |
| G4O | gpt-4o | O1 | o1 |
| COR | Cortex | MPL | MemPalace |

### 日记格式

```
调用方式:
mcp__mempalace__mempalace_diary_write({
  agent_name: "solar",
  entry: "SESSION:2026-04-09|mpl.integration.phase3.done|ALC:diary.rules.created|★★★★",
  topic: "integration"
})
```

### 正反模式

```
❌ 错误: 会话结束不写日记，下次无法追溯
❌ 错误: 日记写太详细浪费 token（AAAK 就是压缩格式）
❌ 错误: 忘记写 agent_name="solar"

✅ 正确: 每个关键节点写一行 AAAK 日记
✅ 正确: ★★★ 以上才值得记录（不记录琐碎操作）
✅ 正确: 压缩前必须写一条完整会话摘要
```

## 预期效果

- 跨会话记忆可追溯（不再完全失忆）
- 会话摘要供下次启动时恢复态势
- 日记可被 mempalace_diary_read 回溯

---

*MemPalace Diary Protocol v1.0*
*建立于: 2026-04-09*
*来源: MemPalace v3.0 深度集成*
