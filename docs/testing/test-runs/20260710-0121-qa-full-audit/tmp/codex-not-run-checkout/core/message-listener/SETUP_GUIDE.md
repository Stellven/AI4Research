# iMessage 任务监听设置指南

## ✅ 已完成

- [x] message-handler.ts 核心处理器
- [x] task-scheduler.ts 智能调度器
- [x] 数据库 Schema (bl_message_tasks, bl_message_triggers, bl_scheduled_tasks)
- [x] 意图分类系统
- [x] **三级优先级系统** (高优先级/常设级/临时级)
- [x] **智能调度决策** (基于 Rate Limit、Token 成本、重置时间)
- [x] 支持的命令:
  - backlog 列表
  - 搜索文件 <关键词>
  - 查天气 <城市>
  - HN 头条

## 🎯 三级优先级系统

Solar 消息监听器根据口令自动识别任务优先级：

| 优先级 | 口令关键词 | 执行策略 | 示例 |
|--------|-----------|---------|------|
| **高优先级** (high) | 马上、立即、快点、给我、现在、赶紧、急 | 即刻执行，即使 Rate Limit 接近上限 (95%) | "马上查天气 北京" |
| **常设级** (scheduled) | 定时、定期、经常看看、每天、每周、定时检查 | 按设定周期执行，Rate Limit < 80% 时执行 | "定期看看 Moltbook 有没有新回复" |
| **临时级** (temporary) | 你看看、看看、分析下、分析一下、研究下、帮我查 | 智能调度，基于当前 Rate Limit 和预估 Token 成本决策 | "你看看搜索 agent 相关文件" |

### 智能调度决策矩阵 (临时级)

```
Rate Limit 使用率 < 70%  → 立即执行
70% ≤ 使用率 < 85%       → 计算执行后预估使用率
  └─ 预估 < 90%          → 执行
  └─ 预估 ≥ 90%          → 延迟，等待重置
使用率 ≥ 85%             → 延迟，建议等待
```

### Rate Limit 配置

- **模型**: Claude Sonnet 4.5
- **限额**: 1,000,000 tokens / 5 分钟
- **重置周期**: 每 5 分钟滚动窗口
- **Token 预估**: 根据命令类型自动估算

## 🔧 快速设置 (2 分钟)

### Step 1: 配置白名单

添加你的联系方式到白名单：

```bash
sqlite3 ~/.solar/solar.db "
INSERT INTO bl_message_triggers (
  trigger_id,
  contact_name,
  contact_phone,
  enabled,
  priority,
  allowed_actions
) VALUES (
  'my-phone',
  '我的手机',
  '+8613800138000',  -- 改成你的手机号
  1,
  100,
  '[\"*\"]'
)"
```

### Step 2: 测试命令

在终端测试不同优先级：

```bash
cd ~/Solar/core/message-listener

# 测试 1: 高优先级 (马上执行)
bun message-handler.ts "+8613800138000" "马上搜索 agent"

# 测试 2: 临时级 (智能调度)
bun message-handler.ts "+8613800138000" "你看看搜索 agent"

# 测试 3: 查询状态
bun message-handler.ts "+8613800138000" "查状态"

# 测试 4: Backlog 列表
bun message-handler.ts "+8613800138000" "backlog 列表"
```

**预期结果:**
- 高优先级任务立即执行
- 临时级任务根据当前 Rate Limit 决定执行或延迟
- 延迟的任务会显示延迟原因和推荐时间

### Step 3: 创建 Shortcut (Apple Shortcuts)

#### 方法 A: 手动创建 (推荐)

1. 打开 Shortcuts.app
2. 点击 "+" 创建新 Shortcut
3. 命名为 "Solar Message Handler"
4. 添加以下动作：

```
1. Get Clipboard  (获取剪贴板)
2. Run Shell Script
   - Shell: /bin/bash
   - Input: Clipboard
   - Script:
     /opt/homebrew/bin/bun ~/Solar/core/message-listener/message-handler.ts "+8613800138000" "$1"
3. Show Result  (显示结果)
```

5. 保存

#### 方法 B: 自动化 Automation (需要 macOS Sonoma+)

1. 打开 Shortcuts.app → Automation 标签
2. 点击 "+" → Personal Automation
3. 选择 "Message" → "When I receive a message"
4. 条件: "Contains" → 留空 (接收所有消息)
5. 动作:
   - Get 'Message' from 'Shortcut Input'
   - Get 'Sender' from 'Shortcut Input'
   - Run Shell Script:
     ```bash
     /opt/homebrew/bin/bun ~/Solar/core/message-listener/message-handler.ts "$2" "$1"
     ```
   - Send Message to 'Sender'

**注意:** Automation 有1-2秒延迟，适合后台处理。

### Step 4: 使用 (手动版)

1. 发送消息给自己 (如 "backlog 列表")
2. 复制消息内容
3. 运行 Shortcut "Solar Message Handler"
4. 查看结果

### Step 5: 使用 (自动化版)

直接发消息给自己，系统自动回复！

## 📱 支持的命令

| 命令示例 | 意图 | 功能 |
|---------|------|------|
| backlog 列表 | query | 查看当前所有任务 |
| 查状态 | query | 今日消息任务统计 |
| 搜索 agent | task | 搜索包含"agent"的文件 |
| 查天气 北京 | task | 查询北京天气 (需要 weather script) |
| HN 头条 | task | 获取 Hacker News 热门 |

## 🛠️ 高级配置

### 添加新命令

编辑 `message-handler.ts` 的 `classifyIntent` 和 `executeIntent` 方法：

```typescript
// 1. 在 classifyIntent 中添加关键词匹配
if (msg.includes('新命令关键词')) {
  return {
    type: 'task',
    action: 'my_action',
    params: { ... },
    confidence: 0.9
  };
}

// 2. 在 executeIntent 中添加处理器
case 'my_action':
  return await this.handleMyAction(intent.params);
```

### 查看历史记录

```bash
sqlite3 ~/.solar/solar.db "
SELECT
  datetime(created_at, 'localtime') as time,
  intent_action,
  status,
  substr(result, 1, 50) as result_preview
FROM bl_message_tasks
ORDER BY created_at DESC
LIMIT 10
"
```

### 清理旧记录

```bash
sqlite3 ~/.solar/solar.db "
DELETE FROM bl_message_tasks
WHERE created_at < datetime('now', '-7 days')
"
```

## 🔒 安全注意事项

1. **白名单机制**: 只有白名单中的联系人才能执行命令
2. **命令限制**: 不支持任意代码执行，只能运行预定义的操作
3. **审计日志**: 所有操作记录在 bl_message_tasks 表中
4. **速率限制**: 建议在 message-handler 中添加速率限制逻辑

## ⚠️ 已知限制

1. **Full Disk Access**: 无法直接读取 iMessage 数据库 (~/Library/Messages/chat.db)
   - 解决方案: 使用 Shortcuts Automation 作为桥梁
2. **长任务**: 超过 30 秒的任务可能超时
   - 解决方案: 使用后台任务队列
3. **富文本**: iMessage 纯文本回复，不支持图片/链接
   - 解决方案: 返回简洁的纯文本结果

## 📊 监控与统计

查看今日统计：

```bash
sqlite3 ~/.solar/solar.db "SELECT * FROM v_message_tasks_today"
```

输出示例：
```
total|completed|failed|running|avg_time_ms
10|8|1|1|234.5
```

## 🐛 故障排查

### 问题: "未授权的发送者"

**原因**: 手机号未在白名单中

**解决**:
```bash
sqlite3 ~/.solar/solar.db "
SELECT * FROM bl_message_triggers WHERE enabled = 1
"
```

检查你的手机号是否在列表中。

### 问题: "Schema file not found"

**原因**: schema.sql 不在预期位置

**解决**: 这是警告，可以忽略。Schema 已经初始化。

### 问题: Shortcut 无法执行

**原因**: bun 路径不对

**解决**:
```bash
which bun  # 查找 bun 路径
# 更新 Shortcut 中的路径
```

## 🚀 下一步

- [ ] 集成 LLM 进行更智能的意图识别
- [ ] 支持多轮对话 (上下文记忆)
- [ ] 异步任务队列 (处理长时间任务)
- [ ] Web Dashboard (可视化管理)
- [ ] 更多预定义命令

---

**系统版本**: v1.0
**创建日期**: 2026-02-04
**测试状态**: ✅ 已测试
