# iMessage 任务监听器 - 故障排查

## 问题: 发消息没有反应

### 快速诊断清单

```bash
# 1. 检查白名单
sqlite3 ~/.solar/solar.db "
SELECT contact_email, contact_phone, enabled
FROM bl_message_triggers
WHERE enabled = 1
"

# 2. 测试消息处理器
cd ~/Solar/core/message-listener
bun message-handler.ts "guardian-imessage@example.com" "测试消息"

# 3. 检查最近任务记录
sqlite3 ~/.solar/solar.db "
SELECT datetime(created_at, 'localtime') as time,
       sender,
       content,
       status,
       error
FROM bl_message_tasks
ORDER BY created_at DESC
LIMIT 5
"
```

---

## 必需配置步骤

### ✅ Step 1: 白名单 (已完成)

```bash
sqlite3 ~/.solar/solar.db "
SELECT * FROM bl_message_triggers WHERE contact_email = 'guardian-imessage@example.com'
"
```

**预期输出:** 应该看到一行记录，`enabled = 1`

---

### ⚠️ Step 2: Apple Shortcuts Automation (需要配置)

**这是最关键的一步！** 如果没有配置 Automation，iMessage 消息无法触发脚本。

#### 配置步骤:

1. **打开 Shortcuts.app**
   - 找到应用程序 → Shortcuts.app
   - 或 Spotlight 搜索 "Shortcuts"

2. **切换到 Automation 标签**
   - 点击底部的 "Automation" 标签
   - 如果没看到，说明 macOS 版本可能不支持 (需要 macOS 14.0+)

3. **创建新的 Automation**
   - 点击右上角 "+" 按钮
   - 选择 "Personal Automation"

4. **选择触发器**
   - 选择 "Message"
   - 选择 "When I receive a message"

5. **配置触发条件**
   ```
   When: I receive a message
   From: [留空或选择自己的联系人]
   Contains: [留空，接收所有消息]
   Immediately: ✓ (勾选)
   ```

6. **添加动作 (重要!)**

   **Action 1: Get Details of Message**
   - Detail: Sender
   - 保存为变量 "Sender"

   **Action 2: Get Details of Message**
   - Detail: Text
   - 保存为变量 "MessageText"

   **Action 3: Run Shell Script**
   - Shell: `/bin/bash`
   - Pass Input: `As arguments`
   - Script:
     ```bash
     SENDER="$1"
     MESSAGE="$2"
     /opt/homebrew/bin/bun ~/Solar/core/message-listener/message-handler.ts "$SENDER" "$MESSAGE"
     ```
   - Input: `Sender`, `MessageText`

   **Action 4: Send Message (可选)**
   - Recipient: `Sender`
   - Message: `Shell Script Result`
   - (如果想自动回复结果，添加这一步)

7. **保存并测试**
   - 点击 "Done" 保存
   - 给自己发一条测试消息: "测试"

---

### 检查: Shortcuts 是否安装 bun

```bash
# 检查 bun 路径
which bun

# 如果输出不是 /opt/homebrew/bin/bun，需要修改 Shortcut 脚本中的路径
```

常见路径:
- Apple Silicon Mac: `/opt/homebrew/bin/bun`
- Intel Mac: `/usr/local/bin/bun`
- 自定义安装: `~/.bun/bin/bun`

---

## 替代方案: 手动触发 (测试用)

如果 Automation 不工作，可以先用手动方式测试:

### 方案 A: 命令行测试

```bash
cd ~/Solar/core/message-listener
bun message-handler.ts "guardian-imessage@example.com" "backlog 列表"
```

### 方案 B: Shortcut 手动触发

1. 打开 Shortcuts.app
2. 点击 "+" 创建新 Shortcut
3. 命名: "Solar 消息处理"
4. 添加动作:

   ```
   Action 1: Ask for Input
     - Prompt: "输入消息内容"
     - Input Type: Text

   Action 2: Run Shell Script
     - Shell: /bin/bash
     - Script:
       /opt/homebrew/bin/bun ~/Solar/core/message-listener/message-handler.ts "guardian-imessage@example.com" "$1"

   Action 3: Show Result
     - Input: Shell Script Result
   ```

5. 运行这个 Shortcut 测试

---

## 常见错误

### 错误 1: "未授权的发送者"

**原因:** 白名单中没有你的邮箱/手机号

**解决:**
```bash
sqlite3 ~/.solar/solar.db "
INSERT INTO bl_message_triggers (
  trigger_id, contact_name, contact_email, enabled, priority, allowed_actions
) VALUES (
  'my-account', '我的账号', '你的邮箱', 1, 100, '[\"*\"]'
)
"
```

### 错误 2: "command not found: bun"

**原因:** Shortcuts 找不到 bun 命令

**解决:**
1. 找到 bun 路径: `which bun`
2. 在 Shortcut 脚本中使用完整路径，如 `/opt/homebrew/bin/bun`

### 错误 3: "Schema file not found"

**原因:** schema.sql 文件路径不对 (这是警告，不影响功能)

**解决:** 确保文件在 `~/Solar/core/message-listener/schema.sql`

### 错误 4: Automation 不触发

**原因 1:** macOS 版本不支持 (需要 14.0+)
**原因 2:** 权限未授予

**解决:**
1. 检查 macOS 版本: `sw_vers`
2. 系统设置 → Privacy & Security → Automation
3. 确保 Shortcuts.app 有权限访问 Messages

---

## 验证配置

### 完整测试流程

```bash
# 1. 白名单检查
sqlite3 ~/.solar/solar.db "SELECT * FROM bl_message_triggers WHERE enabled = 1"
# 应该看到你的邮箱

# 2. 命令行测试
cd ~/Solar/core/message-listener
bun message-handler.ts "guardian-imessage@example.com" "测试消息"
# 应该有输出 (成功或错误信息)

# 3. 查看日志
sqlite3 ~/.solar/solar.db "
SELECT datetime(created_at, 'localtime'), sender, content, status
FROM bl_message_tasks
ORDER BY created_at DESC
LIMIT 3
"
# 应该看到你的测试消息记录

# 4. iMessage 测试
# 给自己发消息: "backlog 列表"
# 等待 2-3 秒
# 检查是否收到回复或查看日志
```

---

## 系统要求

- macOS 14.0+ (用于 Shortcuts Automation)
- Bun runtime (已安装)
- SQLite (系统自带)
- Apple Shortcuts.app (系统自带)
- iMessage 已登录账号 (guardian-imessage@example.com)

---

## 日志查看

### 查看所有任务

```bash
sqlite3 ~/.solar/solar.db "
SELECT
  datetime(created_at, 'localtime') as time,
  sender,
  priority,
  intent_action,
  status,
  substr(result, 1, 40) as result_preview
FROM bl_message_tasks
ORDER BY created_at DESC
LIMIT 10
"
```

### 查看失败任务

```bash
sqlite3 ~/.solar/solar.db "
SELECT
  datetime(created_at, 'localtime') as time,
  sender,
  content,
  error
FROM bl_message_tasks
WHERE status = 'failed'
ORDER BY created_at DESC
LIMIT 5
"
```

---

**如果仍然无法工作，请提供:**
1. macOS 版本: `sw_vers`
2. 错误信息: 命令行测试的输出
3. 日志记录: 最近任务的数据库记录
