#!/bin/bash
# Honcho SessionEnd Hook
# 提取会话关键信息并持久化到 Honcho
#
# 触发: SessionEnd
# 行为:
#   1. 从 session-state.jsonl 提取本次会话关键事件
#   2. 将关键观察写入 Honcho (作为 AI peer 的 conclusion)
#   3. 后台执行，不阻塞退出
#   4. 如果 HONCHO_API_KEY 未设置，静默退出
#
set -u

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -r "$HOOK_DIR/lib/portable.sh" ]]; then
    # shellcheck source=lib/portable.sh
    . "$HOOK_DIR/lib/portable.sh"
fi

# 消耗 stdin
cat > /dev/null 2>&1 || true

# 检查依赖
if ! command -v curl &>/dev/null; then
    exit 0
fi

# 检查 HONCHO_API_KEY (optional for self-hosted)
HONCHO_KEY="${HONCHO_API_KEY:-self-hosted}"

# 后台执行，不阻塞退出
(
    HONCHO_BASE="${HONCHO_BASE_URL:-http://localhost:8900}"
    WORKSPACE="${HONCHO_WORKSPACE_ID:-solar}"
    SESSION_LOG="$HOME/.solar/session-state.jsonl"
    AI_PEER="solar"
    USER_PEER="user"
    SESSION_ID="solar-default"

    # 从最近事件提取关键信息 (最近 30 分钟的事件)
    if [[ -f "$SESSION_LOG" ]]; then
        CUTOFF=$(date_add -30M "%Y-%m-%dT%H:%M" 2>/dev/null || date -u -d '30 minutes ago' +"%Y-%m-%dT%H:%M" 2>/dev/null || echo "")

        if [[ -n "$CUTOFF" ]]; then
            RECENT=$(grep "$CUTOFF" "$SESSION_LOG" 2>/dev/null | tail -20)
        else
            # 没有日期计算，取最后 20 行
            RECENT=$(tail -20 "$SESSION_LOG" 2>/dev/null)
        fi

        if [[ -n "$RECENT" ]]; then
            # 提取关键信息构建观察摘要
            SKILLS_COMPLETED=$(echo "$RECENT" | grep '"skill_completed"' | sed 's/.*"skill":"\([^"]*\)".*/\1/' | sort -u | head -5)
            TASKS_COMPLETED=$(echo "$RECENT" | grep '"task_completed"' | sed 's/.*"task":"\([^"]*\)".*/\1/' | sort -u | head -5)
            TOOLS_USED=$(echo "$RECENT" | grep '"brain_router_call"' | sed 's/.*"model":"\([^"]*\)".*/\1/' | sort | uniq -c | sort -rn | head -5 | awk '{print $2": "$1" calls"}')
            ERRORS=$(echo "$RECENT" | grep '"tool_failure"' | sed 's/.*"tool":"\([^"]*\)".*/\1/' | sort | uniq -c | sort -rn | head -3)

            # 构建观察内容
            OBSERVATION="Session summary (${CUTOFF:-recent}):\n"

            if [[ -n "$SKILLS_COMPLETED" ]]; then
                OBSERVATION+="Skills used: $(echo "$SKILLS_COMPLETED" | tr '\n' ', ' | sed 's/,$//')\n"
            fi
            if [[ -n "$TASKS_COMPLETED" ]]; then
                OBSERVATION+="Tasks completed: $(echo "$TASKS_COMPLETED" | tr '\n' ', ' | sed 's/,$//')\n"
            fi
            if [[ -n "$TOOLS_USED" ]]; then
                OBSERVATION+="Models called:\n$(echo "$TOOLS_USED" | sed 's/^/  /')\n"
            fi
            if [[ -n "$ERRORS" ]]; then
                OBSERVATION+="Errors encountered: $(echo "$ERRORS" | tr '\n' ', ' | sed 's/,$//')\n"
            fi

            # 如果有实质内容，写入 Honcho
            if [[ "$OBSERVATION" != "Session summary (${CUTOFF:-recent}):\n" ]]; then
                # 使用 conclusion API 写入观察
                curl -s --connect-timeout 3 --max-time 10 \
                    -X POST \
                    -H "Authorization: Bearer $HONCHO_KEY" \
                    -H "Content-Type: application/json" \
                    "${HONCHO_BASE}/v3/workspaces/${WORKSPACE}/conclusions" \
                    -d "{
                        \"observer_id\": \"${AI_PEER}\",
                        \"observed_id\": \"${USER_PEER}\",
                        \"conclusions\": [{
                            \"content\": $(echo "$OBSERVATION" | jq -Rs .),
                            \"session_id\": \"${SESSION_ID}\"
                        }]
                    }" \
                    >/dev/null 2>&1 || true
            fi
        fi
    fi
) &

exit 0
