#!/bin/bash
# Solar Resource Discovery: 本地资源扫描
# 扫描 macOS 系统能力并写入元数据数据库
# 适配现有 sys_resources Schema (使用 resource_type 而非 category)

DB_PATH="$HOME/.solar/solar.db"
LOG_FILE="$HOME/.solar/logs/resource-discovery.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

mkdir -p "$(dirname "$LOG_FILE")"
log "开始本地资源扫描..."

#-------------------------------------------------------------------------------
# 通用插入函数
#-------------------------------------------------------------------------------
insert_resource() {
    local resource_id="$1"
    local resource_type="$2"
    local name="$3"
    local description="$4"
    local executor="$5"
    local command_template="$6"
    local keywords="$7"
    local cost_type="${8:-free}"
    local latency_ms="${9:-100}"

    sqlite3 "$DB_PATH" "
        INSERT OR REPLACE INTO sys_resources (
            resource_id, resource_type, name, description, executor,
            command_template, keywords, cost_type, cost_per_call, latency_ms,
            layer, availability, source, last_verified, status
        ) VALUES (
            '$resource_id', '$resource_type', '$name', '$description',
            '$executor', '$command_template', '$keywords',
            '$cost_type', 0, $latency_ms,
            'local', 'available', 'system_scan', datetime('now'), 'active'
        )
    " 2>/dev/null
}

#-------------------------------------------------------------------------------
# 1. 扫描 Apple Shortcuts
#-------------------------------------------------------------------------------
discover_shortcuts() {
    log "扫描 Apple Shortcuts..."
    local count=0

    shortcuts list 2>/dev/null | while read -r shortcut_name; do
        [ -z "$shortcut_name" ] && continue

        local resource_id="shortcut:$(echo "$shortcut_name" | tr ' ' '_' | tr '[:upper:]' '[:lower:]')"
        local keywords="[]"

        # 提取关键词
        case "$shortcut_name" in
            *weather*|*Weather*|*天气*) keywords='["weather", "天气", "气温"]' ;;
            *reminder*|*Reminder*|*提醒*) keywords='["reminder", "提醒", "待办"]' ;;
            *message*|*Message*|*消息*) keywords='["message", "消息", "短信"]' ;;
            *calendar*|*Calendar*|*日历*) keywords='["calendar", "日历", "日程"]' ;;
            *note*|*Note*|*笔记*) keywords='["note", "笔记", "备忘"]' ;;
            *photo*|*Photo*|*照片*) keywords='["photo", "照片", "拍照"]' ;;
            *home*|*Home*|*homekit*) keywords='["homekit", "家居", "智能"]' ;;
        esac

        insert_resource \
            "$resource_id" \
            "shortcut" \
            "$shortcut_name" \
            "Apple Shortcut: $shortcut_name" \
            "shortcut" \
            "shortcuts run \"$shortcut_name\"" \
            "$keywords" \
            "free" \
            "100"

        count=$((count + 1))
    done

    log "发现 Shortcuts"
}

#-------------------------------------------------------------------------------
# 2. 扫描 CLI 工具
#-------------------------------------------------------------------------------
discover_cli_tools() {
    log "扫描 CLI 工具..."

    # 工具列表: tool:keywords
    local tools="
curl:http,fetch,download,api
jq:json,parse,transform
sqlite3:database,query,sql
osascript:applescript,automation,macos
shortcuts:shortcut,automation,ios
himalaya:email,imap,smtp,mail
git:version,control,repo
bun:javascript,typescript,runtime
node:javascript,nodejs,runtime
python3:python,script,ml
ffmpeg:video,audio,convert
rg:search,grep,ripgrep
fd:find,search,files
gh:github,cli,repo
"

    echo "$tools" | while IFS=: read -r tool keywords; do
        [ -z "$tool" ] && continue
        tool=$(echo "$tool" | tr -d ' ')

        if command -v "$tool" &>/dev/null; then
            local path=$(which "$tool" 2>/dev/null)
            local keywords_json=$(echo "$keywords" | tr ',' '\n' | sed 's/^/"/;s/$/"/' | tr '\n' ',' | sed 's/,$//' | sed 's/^/[/;s/$/]/')

            insert_resource \
                "tool:$tool" \
                "tool" \
                "$tool" \
                "CLI Tool: $tool at $path" \
                "shell" \
                "$path" \
                "$keywords_json" \
                "free" \
                "50"
        fi
    done

    log "发现 CLI 工具"
}

#-------------------------------------------------------------------------------
# 3. 扫描 LaunchAgents
#-------------------------------------------------------------------------------
discover_launchd() {
    log "扫描 LaunchAgents..."

    for plist in ~/Library/LaunchAgents/com.solar.*.plist; do
        [ -f "$plist" ] || continue

        local label=$(defaults read "$plist" Label 2>/dev/null || basename "$plist" .plist)
        local interval=$(defaults read "$plist" StartInterval 2>/dev/null || echo "0")

        insert_resource \
            "launchd:$label" \
            "tool" \
            "$label" \
            "LaunchAgent: $label (interval: ${interval}s)" \
            "launchd" \
            "launchctl start $label" \
            '["launchd", "daemon", "scheduled"]' \
            "free" \
            "0"
    done

    log "发现 LaunchAgents"
}

#-------------------------------------------------------------------------------
# 4. 扫描 MCP 服务器
#-------------------------------------------------------------------------------
discover_mcp() {
    log "扫描 MCP 服务器..."

    local mcp_config="$HOME/.claude/claude_desktop_config.json"
    [ -f "$mcp_config" ] || return

    local servers=$(jq -r '.mcpServers // {} | keys[]' "$mcp_config" 2>/dev/null)

    for server in $servers; do
        local command=$(jq -r ".mcpServers.\"$server\".command // \"\"" "$mcp_config")

        insert_resource \
            "mcp_server:$server" \
            "mcp_server" \
            "$server" \
            "MCP Server: $server" \
            "mcp" \
            "$command" \
            '["mcp", "server", "integration"]' \
            "free" \
            "200"
    done

    log "发现 MCP 服务器"
}

#-------------------------------------------------------------------------------
# 5. 扫描 Skills
#-------------------------------------------------------------------------------
discover_skills() {
    log "扫描 Skills..."

    local skills_dir="$HOME/.claude/skills"
    [ -d "$skills_dir" ] || return

    for skill_dir in "$skills_dir"/*/; do
        [ -d "$skill_dir" ] || continue

        local skill_name=$(basename "$skill_dir")
        local description="Skill: /$skill_name"

        # 尝试读取描述
        if [ -f "$skill_dir/SKILL.md" ]; then
            description=$(head -3 "$skill_dir/SKILL.md" | grep -v '^#' | head -1 | tr -d '\n' || echo "Skill: /$skill_name")
            [ -z "$description" ] && description="Skill: /$skill_name"
        fi

        insert_resource \
            "skill:$skill_name" \
            "skill" \
            "/$skill_name" \
            "$description" \
            "skill" \
            "/$skill_name" \
            '["skill", "command"]' \
            "token" \
            "500"
    done

    log "发现 Skills"
}

#-------------------------------------------------------------------------------
# 6. 注册已知远程 API
#-------------------------------------------------------------------------------
register_remote_apis() {
    log "注册已知远程 API..."

    # wttr.in 天气
    sqlite3 "$DB_PATH" "
        INSERT OR REPLACE INTO sys_resources (
            resource_id, resource_type, name, description, executor,
            command_template, keywords, cost_type, cost_per_call, latency_ms,
            layer, availability, source, last_verified, status
        ) VALUES
        ('api:wttr.in', 'tool', 'wttr.in', '天气查询 API (免费)',
         'shell', 'curl -s \"wttr.in/\$CITY?format=3\"',
         '[\"weather\", \"天气\", \"forecast\"]',
         'free', 0, 500, 'remote', 'available', 'manual', datetime('now'), 'active'),

        ('api:ip-api', 'tool', 'ip-api.com', 'IP 地理位置查询 (免费)',
         'shell', 'curl -s \"http://ip-api.com/json/\$IP\"',
         '[\"ip\", \"location\", \"geo\", \"位置\"]',
         'free', 0, 300, 'remote', 'available', 'manual', datetime('now'), 'active'),

        ('api:hackernews', 'tool', 'Hacker News API', 'HN 资讯 (免费)',
         'shell', 'curl -s \"https://hacker-news.firebaseio.com/v0/topstories.json\"',
         '[\"news\", \"tech\", \"hackernews\", \"hn\"]',
         'free', 0, 300, 'remote', 'available', 'manual', datetime('now'), 'active'),

        ('api:exchangerate', 'tool', 'exchangerate-api', '汇率查询 (免费)',
         'shell', 'curl -s \"https://api.exchangerate-api.com/v4/latest/\$BASE\"',
         '[\"exchange\", \"currency\", \"汇率\"]',
         'free', 0, 400, 'remote', 'available', 'manual', datetime('now'), 'active')
    " 2>/dev/null

    log "注册了远程 API"
}

#-------------------------------------------------------------------------------
# 7. 注册系统服务
#-------------------------------------------------------------------------------
register_system_services() {
    log "注册系统服务..."

    sqlite3 "$DB_PATH" "
        INSERT OR REPLACE INTO sys_resources (
            resource_id, resource_type, name, description, executor,
            command_template, keywords, cost_type, cost_per_call, latency_ms,
            layer, availability, source, last_verified, status
        ) VALUES
        ('system:notification', 'tool', 'macOS Notification', '系统通知',
         'shell', 'osascript -e ''display notification \"\$MSG\" with title \"\$TITLE\"''',
         '[\"notification\", \"通知\", \"alert\"]',
         'free', 0, 10, 'local', 'available', 'system_scan', datetime('now'), 'active'),

        ('system:clipboard_read', 'tool', 'Clipboard Read', '读取剪贴板',
         'shell', 'pbpaste',
         '[\"clipboard\", \"剪贴板\", \"paste\"]',
         'free', 0, 5, 'local', 'available', 'system_scan', datetime('now'), 'active'),

        ('system:clipboard_write', 'tool', 'Clipboard Write', '写入剪贴板',
         'shell', 'pbcopy',
         '[\"clipboard\", \"剪贴板\", \"copy\"]',
         'free', 0, 5, 'local', 'available', 'system_scan', datetime('now'), 'active'),

        ('system:say', 'tool', 'Text to Speech', '语音合成',
         'shell', 'say \"\$TEXT\"',
         '[\"speech\", \"say\", \"语音\", \"朗读\"]',
         'free', 0, 100, 'local', 'available', 'system_scan', datetime('now'), 'active'),

        ('system:screenshot', 'tool', 'Screenshot', '屏幕截图',
         'shell', 'screencapture -x \"\$FILE\"',
         '[\"screenshot\", \"截图\", \"capture\"]',
         'free', 0, 500, 'local', 'available', 'system_scan', datetime('now'), 'active'),

        ('system:open_url', 'tool', 'Open URL', '打开 URL',
         'shell', 'open \"\$URL\"',
         '[\"open\", \"url\", \"browser\", \"浏览器\"]',
         'free', 0, 100, 'local', 'available', 'system_scan', datetime('now'), 'active'),

        ('system:open_app', 'tool', 'Open Application', '打开应用',
         'shell', 'open -a \"\$APP\"',
         '[\"open\", \"app\", \"application\", \"应用\"]',
         'free', 0, 500, 'local', 'available', 'system_scan', datetime('now'), 'active')
    " 2>/dev/null

    log "注册了系统服务"
}

#-------------------------------------------------------------------------------
# 主流程
#-------------------------------------------------------------------------------
main() {
    echo "🔍 Solar Resource Discovery"
    echo ""

    discover_shortcuts
    discover_cli_tools
    discover_launchd
    discover_mcp
    discover_skills
    register_remote_apis
    register_system_services

    echo ""
    echo "📊 发现结果:"
    sqlite3 -header -column "$DB_PATH" "
        SELECT
            resource_type as type,
            layer,
            COUNT(*) as count
        FROM sys_resources
        GROUP BY resource_type, layer
        ORDER BY layer, count DESC
    " 2>/dev/null

    local total=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM sys_resources" 2>/dev/null)
    echo ""
    echo "✅ 扫描完成，共 $total 个资源"

    log "本地资源扫描完成，共 $total 个资源"
}

main "$@"
