---
name: save
description: 保存当前会话状态，用于崩溃后快速恢复
user-invocable: true
disable-model-invocation: false
argument-hint: "[摘要描述]"
---

# /save - 会话检查点

## 功能

保存当前会话状态到 `.solar/session.md`，包括：
- 项目状态 (git 分支、未提交变更)
- 当前任务和待办事项
- 关键决策和进展摘要
- 最近修改的文件

## 执行步骤

1. **收集项目状态**
   ```bash
   # 在项目根目录创建 .solar 目录
   mkdir -p .solar/history
   ```

2. **生成会话摘要** (用一段话总结)
   - 当前正在做什么任务
   - 已完成的关键步骤
   - 下一步计划
   - 遇到的问题或阻塞

3. **写入检查点文件** `.solar/session.md`
   ```markdown
   # Session Checkpoint

   > 保存时间: [时间戳]
   > 恢复命令: `/restore`

   ## 任务摘要
   [一段话描述当前任务和进展]

   ## 当前阶段
   - 阶段: P[0-5]
   - 状态: [进行中/阻塞/待验证]

   ## 待办事项
   - [ ] 任务1
   - [x] 已完成任务

   ## 关键文件
   - `file1.ts` - 作用描述
   - `file2.py` - 作用描述

   ## 关键决策
   - 决策1: 原因
   - 决策2: 原因

   ## 下一步
   1. 具体行动1
   2. 具体行动2
   ```

4. **备份历史** (保留最近10个)

## 自动触发

以下情况应主动调用 `/save`:
- 完成一个阶段 (P1/P2/P3/P4/P5)
- 做出重要决策
- 遇到需要用户确认的问题
- 任务暂停或切换

## 输出

```
✓ Checkpoint saved: .solar/session.md
  任务: [任务摘要]
  阶段: P[x]
  下一步: [下一步行动]
```
