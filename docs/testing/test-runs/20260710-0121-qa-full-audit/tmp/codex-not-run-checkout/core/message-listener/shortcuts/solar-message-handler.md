# Solar Message Handler Shortcut 配置

> 由于 .shortcut 文件是二进制格式，这里提供手动创建步骤

## 方案 1: 手动触发 (最简单)

**适合场景**: 需要时手动运行

### 创建步骤

1. 打开 **Shortcuts.app**
2. 点击右上角 **"+"** 创建新 Shortcut
3. 命名: **"Solar 消息处理"**
4. 添加动作:

```
Action 1: Ask for Input
  - Prompt: "输入消息内容"
  - Input Type: Text

Action 2: Run Shell Script
  - Shell: /bin/bash
  - Input: Provided Input
  - Script:
    /opt/homebrew/bin/bun ~/Solar/core/message-listener/message-handler.ts "+8613800138000" "$1"

Action 3: Show Result
  - Input: Shell Script Result
```

5. 保存并测试

### 使用方式

1. 打开 Shortcuts.app 或 Spotlight 搜索 "Solar 消息处理"
2. 输入命令，如 "backlog 列表"
3. 查看结果

---

## 方案 2: 从剪贴板读取 (推荐)

**适合场景**: 复制消息后快速处理

### 创建步骤

1. 打开 **Shortcuts.app**
2. 创建新 Shortcut: **"Solar 处理剪贴板"**
3. 添加动作:

```
Action 1: Get Clipboard
  - (自动获取剪贴板内容)

Action 2: Run Shell Script
  - Shell: /bin/bash
  - Input: Clipboard
  - Script:
    /opt/homebrew/bin/bun ~/Solar/core/message-listener/message-handler.ts "+8613800138000" "$1"

Action 3: Copy to Clipboard
  - Input: Shell Script Result
  - (将结果复制到剪贴板)

Action 4: Show Notification
  - Title: "Solar 处理完成"
  - Body: Shell Script Result
```

4. 设置键盘快捷键 (可选):
   - 右上角 "..." → Details
   - Add to Quick Actions
   - Add Keyboard Shortcut: ⌘⇧S

### 使用方式

1. 复制消息内容
2. 按 ⌘⇧S (或运行 Shortcut)
3. 结果自动复制到剪贴板，并显示通知

---

## 方案 3: iMessage Automation (全自动)

**适合场景**: 自动响应 iMessage

⚠️ **需要 macOS 14.0+ 和隐私权限**

### 创建步骤

1. 打开 **Shortcuts.app** → **Automation** 标签
2. 点击 **"+"** → **Personal Automation**
3. 选择 **"Message"** → **"When I receive a message"**

### 配置触发器

```
When: I receive a message
  ├─ From: <选择联系人或留空接收所有>
  ├─ Contains: <留空或指定关键词>
  └─ Immediately: ✓ (立即执行)
```

### 添加动作

```
Action 1: Get Details of Message
  - Detail: Sender
  - Save as: Variable "Sender"

Action 2: Get Details of Message
  - Detail: Text
  - Save as: Variable "MessageText"

Action 3: Run Shell Script
  - Shell: /bin/bash
  - Pass Input: As arguments
  - Script:
    SENDER="$1"
    MESSAGE="$2"
    /opt/homebrew/bin/bun ~/Solar/core/message-listener/message-handler.ts "$SENDER" "$MESSAGE"
  - Input: Sender, MessageText

Action 4: Send Message
  - Recipient: Sender
  - Message: Shell Script Result
```

### 权限设置

首次运行会提示授权:
- ✓ Contacts (访问联系人)
- ✓ Messages (发送消息)
- ✓ Automation (自动化)

### 使用方式

1. 给自己发消息: "backlog 列表"
2. 系统自动回复结果
3. 完全自动化，无需手动触发

---

## 方案 4: Siri 语音触发

**适合场景**: 免提操作

### 创建步骤

使用方案 1 或 2 的 Shortcut，添加 Siri 短语:

1. 打开 Shortcut 详情
2. 点击 "Add to Siri"
3. 录制短语: **"Solar 查询 Backlog"**
4. 保存

### 使用方式

```
"Hey Siri, Solar 查询 Backlog"
```

Siri 会执行 Shortcut 并朗读结果。

---

## 测试脚本

验证 Shortcut 配置是否正确:

```bash
# 测试 1: Backlog 查询
/opt/homebrew/bin/bun ~/Solar/core/message-listener/message-handler.ts "+8613800138000" "backlog 列表"

# 测试 2: 文件搜索
/opt/homebrew/bin/bun ~/Solar/core/message-listener/message-handler.ts "+8613800138000" "搜索 agent"

# 测试 3: 天气查询 (需要 weather script)
/opt/homebrew/bin/bun ~/Solar/core/message-listener/message-handler.ts "+8613800138000" "查天气 北京"

# 测试 4: 状态查询
/opt/homebrew/bin/bun ~/Solar/core/message-listener/message-handler.ts "+8613800138000" "查状态"
```

---

## 故障排查

### 问题: "command not found: bun"

**解决**: 使用完整路径
```bash
which bun  # 查找 bun 路径
```

更新 Script 中的 `/opt/homebrew/bin/bun` 为实际路径。

### 问题: Automation 不触发

**检查**:
1. System Settings → Privacy & Security → Automation
2. 确保 Shortcuts.app 有权限访问 Messages
3. 关闭 "Ask Before Running" (自动运行)

### 问题: "未授权的发送者"

**解决**: 更新手机号
```bash
sqlite3 ~/.solar/solar.db "
UPDATE bl_message_triggers
SET contact_phone = '+8613800138000'  -- 你的实际手机号
WHERE trigger_id = 'test-user'
"
```

---

## 性能优化

### 减少启动时间

在 Shortcut 中添加缓存:

```bash
# 预编译 TypeScript (可选)
cd ~/Solar/core/message-listener
bun build message-handler.ts --compile --outfile message-handler-compiled
```

使用编译版本:
```bash
~/Solar/core/message-listener/message-handler-compiled "+86..." "命令"
```

### 后台运行 (避免阻塞)

```bash
# 在 Shortcut 中使用 & 后台执行
/opt/homebrew/bin/bun ~/Solar/core/message-listener/message-handler.ts "$SENDER" "$MESSAGE" &
```

---

## 安全建议

1. **限制联系人**: Automation 中指定"From: 监护人"
2. **关键词过滤**: 添加触发关键词，如 "Solar:"
3. **速率限制**: 在 handler 中添加限流逻辑
4. **命令白名单**: 只允许特定命令

---

**版本**: v1.0
**平台**: macOS 14.0+
**依赖**: Bun, SQLite, Shortcuts.app
