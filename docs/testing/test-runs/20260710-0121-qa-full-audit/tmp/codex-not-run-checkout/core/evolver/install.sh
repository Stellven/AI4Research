#!/bin/bash
# Solar Evolver - 安装定时任务

set -e

PLIST_SRC="$(dirname "$0")/com.solar.evolver.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.solar.evolver.plist"
LOG_DIR="$HOME/.solar/logs"

echo "🧬 安装 Solar Evolver 定时任务..."

# 创建日志目录
mkdir -p "$LOG_DIR"

# 如果已安装，先卸载
if [[ -f "$PLIST_DST" ]]; then
    echo "  卸载旧版本..."
    launchctl unload "$PLIST_DST" 2>/dev/null || true
    rm -f "$PLIST_DST"
fi

# 复制 plist
echo "  复制配置..."
cp "$PLIST_SRC" "$PLIST_DST"

# 加载
echo "  加载服务..."
launchctl load "$PLIST_DST"

echo ""
echo "✅ 安装完成！"
echo ""
echo "Evolver 将在每天凌晨 3:00 自动执行自我优化。"
echo ""
echo "手动命令:"
echo "  查看状态: launchctl list | grep solar"
echo "  手动执行: bun run ~/Solar/core/evolver/optimize.ts optimize"
echo "  查看日志: tail -f ~/.solar/logs/evolver.log"
echo "  卸载:     launchctl unload ~/Library/LaunchAgents/com.solar.evolver.plist"
