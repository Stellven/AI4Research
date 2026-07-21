#!/bin/bash
# 生成 Shortcuts URL Scheme 快速安装

SHORTCUT_NAME="Solar消息处理"
SCRIPT_PATH="$HOME/Solar/core/message-listener/message-handler.ts"
SENDER="${SOLAR_SHORTCUT_SENDER:-guardian-imessage@example.com}"

# 生成 Shortcuts URL
cat << 'EOF'
╭────────────────────────────────────────────────────────────╮
│     快速安装 Solar 消息处理 Shortcut                       │
╰────────────────────────────────────────────────────────────╯

方式 1: 剪贴板触发 (最简单)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. 打开 Shortcuts.app
2. 点击 "+" 创建新 Shortcut
3. 搜索并添加以下动作:

   动作 1: Get Clipboard
   动作 2: Run Shell Script
     - Shell: /bin/bash
     - Script:
EOF

cat << EOF
       /opt/homebrew/bin/bun "$SCRIPT_PATH" "$SENDER" "\$1"
EOF

cat << 'EOF'
   动作 3: Show Result

4. 保存为 "Solar消息处理"
5. 设置快捷键: ⌘⇧S

使用方式:
  1. 复制消息内容
  2. 按 ⌘⇧S
  3. 查看结果

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

方式 2: 询问输入
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. 打开 Shortcuts.app
2. 点击 "+" 创建新 Shortcut
3. 搜索并添加以下动作:

   动作 1: Ask for Input
     - Prompt: "输入消息内容"

   动作 2: Run Shell Script
     - Shell: /bin/bash
     - Script:
EOF

cat << EOF
       /opt/homebrew/bin/bun "$SCRIPT_PATH" "$SENDER" "\$1"
EOF

cat << 'EOF'
   动作 3: Show Result

4. 保存为 "Solar消息处理"

使用方式:
  1. 运行 Shortcut
  2. 输入消息
  3. 查看结果

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

测试命令:
  • backlog 列表
  • 你看看搜索 agent
  • 查状态

EOF
