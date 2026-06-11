#!/bin/bash
# STATE.md 自动更新器
# 在 SessionEnd 时自动更新 STATE.md 的 Progress 和 AUTO-PROGRESS 区块

STATE_FILE="$HOME/.solar/STATE.md"
DB_FILE="$HOME/.solar/db/solar.db"
HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -r "$HOOK_DIR/lib/portable.sh" ]]; then
    # shellcheck source=lib/portable.sh
    . "$HOOK_DIR/lib/portable.sh"
fi

SOLAR_PYTHON_BIN="$(solar_python 2>/dev/null || command -v python3)"

# 检查文件存在
if [[ ! -f "$STATE_FILE" ]]; then
    echo "⚠️ STATE.md 不存在"
    exit 0
fi

# 获取最近30分钟的事件统计 (字段: timestamp, command, event_type='tool_call')
RECENT_EVENTS=$(sqlite3 "$DB_FILE" 2>/dev/null << 'SQL'
SELECT
    COUNT(*) as cnt,
    GROUP_CONCAT(DISTINCT command) as tools
FROM mem_events
WHERE timestamp > datetime('now', '-30 minutes')
  AND event_type = 'tool_call';
SQL
)

EVENT_COUNT=$(echo "$RECENT_EVENTS" | cut -d'|' -f1)
TOOLS_USED=$(echo "$RECENT_EVENTS" | cut -d'|' -f2)

# 获取最近的操作描述
LAST_OP=$(sqlite3 "$DB_FILE" 2>/dev/null << 'SQL'
SELECT command || ': ' || substr(COALESCE(input_summary, module, ''), 1, 50)
FROM mem_events
WHERE event_type = 'tool_call'
ORDER BY timestamp DESC
LIMIT 1;
SQL
)

# 生成时间戳
TIMESTAMP=$(date "+%Y/%m/%d %H:%M:%S")

# 构建新的 AUTO-PROGRESS 区块
NEW_PROGRESS="<!-- AUTO-PROGRESS -->
**自动进度追踪** ($TIMESTAMP):
- 事件数: ${EVENT_COUNT:-0} (最近 30 分钟)
- 工具使用: ${TOOLS_USED:-无}
- 最近操作: ${LAST_OP:-无}
<!-- /AUTO-PROGRESS -->"

# 检查是否已有 AUTO-PROGRESS 区块
if grep -q "<!-- AUTO-PROGRESS -->" "$STATE_FILE"; then
    STATE_FILE="$STATE_FILE" NEW_PROGRESS="$NEW_PROGRESS" "$SOLAR_PYTHON_BIN" << 'PYTHON'
import os
import re

state_file = os.environ['STATE_FILE']
new_block = os.environ['NEW_PROGRESS']

with open(state_file, 'r') as f:
    content = f.read()

pattern = r'<!-- AUTO-PROGRESS -->.*?<!-- /AUTO-PROGRESS -->'
new_content = re.sub(pattern, new_block, content, flags=re.DOTALL)

with open(state_file, 'w') as f:
    f.write(new_content)
PYTHON
else
    STATE_FILE="$STATE_FILE" NEW_PROGRESS="$NEW_PROGRESS" "$SOLAR_PYTHON_BIN" << 'PYTHON' || true
import os

state_file = os.environ['STATE_FILE']
new_block = os.environ['NEW_PROGRESS']

with open(state_file, 'r') as f:
    content = f.read()

marker = '# Next Actions'
if marker in content:
    content = content.replace(marker, f'{new_block}\n\n{marker}', 1)
else:
    content = f'{content.rstrip()}\n\n{new_block}\n'

with open(state_file, 'w') as f:
    f.write(content)
PYTHON
fi

echo "✓ STATE.md 自动更新完成 ($TIMESTAMP)"
