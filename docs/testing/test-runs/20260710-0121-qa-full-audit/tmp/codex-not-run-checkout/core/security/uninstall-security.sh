#!/bin/bash
# Solar Security 卸载脚本

AGENT_DIR="$HOME/Library/LaunchAgents"

echo "🗑️  卸载 Solar Security..."

for plist in "$AGENT_DIR"/com.solar.security.*.plist; do
    if [ -f "$plist" ]; then
        label=$(basename "$plist" .plist)
        launchctl unload "$plist" 2>/dev/null
        rm -f "$plist"
        echo "  ✓ 已卸载: $label"
    fi
done

echo ""
echo "✅ Solar Security 已卸载"
echo "   日志保留在: ~/.solar/logs/"
