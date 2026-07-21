#!/bin/bash
# Solar Shortcuts Installer
# 通过 URL Scheme 安装 Solar Shortcuts 到 Shortcuts.app

set -e

echo "┌─────────────────────────────────────────────────────────────┐"
echo "│              ☀️ SOLAR SHORTCUTS INSTALLER                   │"
echo "├─────────────────────────────────────────────────────────────┤"
echo "│                                                             │"
echo "│  This will install Solar AI OS shortcuts to your Mac.      │"
echo "│                                                             │"
echo "└─────────────────────────────────────────────────────────────┘"
echo ""

# 检查是否是 macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "❌ Error: This script only works on macOS"
    exit 1
fi

# 检查 shortcuts 命令
if ! command -v shortcuts &> /dev/null; then
    echo "❌ Error: shortcuts command not found. Requires macOS 12+"
    exit 1
fi

# 创建临时目录
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

# ==================== Shortcut Definitions ====================

# 函数: 创建简单的 Shortcut (通过 AppleScript)
create_shortcut_via_applescript() {
    local name="$1"
    local description="$2"

    osascript <<EOF
tell application "Shortcuts"
    -- Note: Shortcuts app doesn't have full AppleScript support
    -- This is a placeholder for manual creation guidance
end tell
EOF
}

# ==================== Manual Installation Guide ====================

echo "📋 由于 macOS 安全限制，需要手动在 Shortcuts.app 中创建以下快捷指令："
echo ""

cat << 'GUIDE'
┌─────────────────────────────────────────────────────────────────────────┐
│ SHORTCUT 1: solar_get_weather                                           │
├─────────────────────────────────────────────────────────────────────────┤
│ 1. 打开 Shortcuts.app                                                   │
│ 2. 点击 + 创建新快捷指令                                                │
│ 3. 命名为 "solar_get_weather"                                           │
│ 4. 添加动作:                                                            │
│    - Get Current Weather                                                │
│    - Set Variable (weather)                                             │
│    - Get details of weather (Condition, Temperature, etc.)              │
│    - Dictionary: combine into JSON                                      │
│    - Output result                                                      │
│ 5. 保存                                                                 │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ SHORTCUT 2: solar_set_reminder                                          │
├─────────────────────────────────────────────────────────────────────────┤
│ 1. 打开 Shortcuts.app                                                   │
│ 2. 点击 + 创建新快捷指令                                                │
│ 3. 命名为 "solar_set_reminder"                                          │
│ 4. 添加动作:                                                            │
│    - Shortcut Input (Get input from Share Sheet / Shortcut)             │
│    - Get Dictionary Value (key: "title")                                │
│    - Get Dictionary Value (key: "datetime")                             │
│    - Add New Reminder                                                   │
│    - Dictionary: {"success": true, "reminder_id": Reminder ID}          │
│    - Output result                                                      │
│ 5. 保存                                                                 │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ SHORTCUT 3: solar_get_clipboard                                         │
├─────────────────────────────────────────────────────────────────────────┤
│ 1. 打开 Shortcuts.app                                                   │
│ 2. 点击 + 创建新快捷指令                                                │
│ 3. 命名为 "solar_get_clipboard"                                         │
│ 4. 添加动作:                                                            │
│    - Get Clipboard                                                      │
│    - Dictionary: {"content": Clipboard, "type": "text"}                 │
│    - Output result                                                      │
│ 5. 保存                                                                 │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ SHORTCUT 4: solar_send_message                                          │
├─────────────────────────────────────────────────────────────────────────┤
│ 1. 打开 Shortcuts.app                                                   │
│ 2. 点击 + 创建新快捷指令                                                │
│ 3. 命名为 "solar_send_message"                                          │
│ 4. 添加动作:                                                            │
│    - Shortcut Input                                                     │
│    - Get Dictionary Value (key: "recipient")                            │
│    - Get Dictionary Value (key: "content")                              │
│    - Send Message (to: recipient, content: message)                     │
│    - Dictionary: {"success": true}                                      │
│    - Output result                                                      │
│ 5. 保存                                                                 │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ SHORTCUT 5: solar_router (核心路由器)                                   │
├─────────────────────────────────────────────────────────────────────────┤
│ 1. 打开 Shortcuts.app                                                   │
│ 2. 点击 + 创建新快捷指令                                                │
│ 3. 命名为 "solar_router"                                                │
│ 4. 配置 Siri 短语: "Solar"                                              │
│ 5. 添加动作:                                                            │
│    - Ask for Input (with voice)                                         │
│    - Set Variable (user_query)                                          │
│    - Run Shell Script:                                                  │
│      curl -s "http://localhost:3000/route" \                            │
│        -d '{"query":"[user_query]"}'                                    │
│    - Get Dictionary Value (key: "shortcut")                             │
│    - Run Shortcut (shortcut name from variable)                         │
│    - Show Result / Speak                                                │
│ 6. 保存                                                                 │
└─────────────────────────────────────────────────────────────────────────┘
GUIDE

echo ""
echo "💡 提示: 你也可以从 iCloud 共享链接导入预制的 Shortcuts"
echo ""

# ==================== 验证已安装的 Shortcuts ====================

echo "📊 检查已安装的 Solar Shortcuts..."
echo ""

INSTALLED=$(shortcuts list 2>/dev/null | grep -c "^solar_" || echo "0")
echo "已安装 Solar Shortcuts: $INSTALLED 个"
echo ""

if [ "$INSTALLED" -gt 0 ]; then
    echo "已安装列表:"
    shortcuts list 2>/dev/null | grep "^solar_" | while read -r name; do
        echo "  ✓ $name"
    done
else
    echo "⚠️  尚未安装任何 Solar Shortcuts"
    echo "   请按照上面的指南手动创建，或从 iCloud 链接导入"
fi

echo ""
echo "┌─────────────────────────────────────────────────────────────┐"
echo "│                    安装完成                                 │"
echo "├─────────────────────────────────────────────────────────────┤"
echo "│  测试命令:                                                  │"
echo "│  shortcuts run solar_get_weather                            │"
echo "│  shortcuts run solar_get_clipboard                          │"
echo "│                                                             │"
echo "│  或使用 Solar Skill:                                        │"
echo "│  /shortcut run solar_get_weather                            │"
echo "└─────────────────────────────────────────────────────────────┘"
