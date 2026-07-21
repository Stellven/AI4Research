#!/bin/bash
# Solar Security 安装脚本
# 安装所有安全检测 LaunchAgent

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LAUNCHD_DIR="$HOME/Solar/deploy/launchd"
AGENT_DIR="$HOME/Library/LaunchAgents"
CHECK_DIR="$SCRIPT_DIR/checks"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║          🛡️  Solar Security 安装程序                         ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# 确保目录存在
mkdir -p "$HOME/.solar/logs"
mkdir -p "$AGENT_DIR"

# 设置脚本可执行权限
echo "📝 设置脚本权限..."
chmod +x "$CHECK_DIR"/*.sh

# 确保数据库表存在
echo "📝 初始化数据库表..."
sqlite3 "$HOME/.solar/solar.db" "
    CREATE TABLE IF NOT EXISTS sec_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        risk_level TEXT NOT NULL,
        source TEXT,
        description TEXT,
        details TEXT,
        alert_sent INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS sec_alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER,
        channel TEXT NOT NULL,
        recipient TEXT,
        content TEXT,
        status TEXT DEFAULT 'pending',
        sent_at DATETIME,
        error TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS sec_scan_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_type TEXT NOT NULL,
        frequency TEXT NOT NULL,
        events_found INTEGER DEFAULT 0,
        alerts_sent INTEGER DEFAULT 0,
        duration_ms INTEGER,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
"

# 卸载旧的 agent (如果存在)
echo "📝 卸载旧版本..."
for plist in "$AGENT_DIR"/com.solar.security.*.plist; do
    if [ -f "$plist" ]; then
        label=$(basename "$plist" .plist)
        launchctl unload "$plist" 2>/dev/null || true
    fi
done

# 复制并加载新的 agent
echo ""
echo "📝 安装 LaunchAgent..."

AGENTS=(
    "com.solar.security.access:1分钟:访问安全检测"
    "com.solar.security.quota:5分钟:配额监控"
    "com.solar.security.system:1小时:系统健康检测"
    "com.solar.security.daily:每日凌晨3点:安全审计"
)

for agent_info in "${AGENTS[@]}"; do
    IFS=':' read -r label interval desc <<< "$agent_info"
    plist="$LAUNCHD_DIR/${label}.plist"

    if [ -f "$plist" ]; then
        cp "$plist" "$AGENT_DIR/"
        launchctl load "$AGENT_DIR/${label}.plist" 2>/dev/null

        if launchctl list | grep -q "$label"; then
            echo "  ✓ $desc ($interval)"
        else
            echo "  ✗ $desc - 加载失败"
        fi
    else
        echo "  ✗ $desc - plist 不存在"
    fi
done

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  ✅ 安装完成！                                               ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║                                                              ║"
echo "║  已安装的安全检测:                                           ║"
echo "║  • 访问安全检测   - 每 1 分钟                                ║"
echo "║  • 配额监控       - 每 5 分钟                                ║"
echo "║  • 系统健康检测   - 每 1 小时                                ║"
echo "║  • 每日安全审计   - 凌晨 3 点                                ║"
echo "║                                                              ║"
echo "║  预警方式:                                                   ║"
echo "║  • macOS 桌面通知 (所有级别)                                 ║"
echo "║  • 邮件 (critical/emergency)                                 ║"
echo "║                                                              ║"
echo "║  日志位置: ~/.solar/logs/security.log                        ║"
echo "║                                                              ║"
echo "║  管理命令:                                                   ║"
echo "║  • 查看状态: launchctl list | grep solar.security            ║"
echo "║  • 手动触发: bash ~/Solar/core/security/checks/*.sh          ║"
echo "║  • 卸载: bash ~/Solar/core/security/uninstall-security.sh    ║"
echo "║                                                              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
