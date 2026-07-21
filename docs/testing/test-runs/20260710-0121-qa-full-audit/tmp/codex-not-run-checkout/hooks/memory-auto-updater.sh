#!/bin/bash
# Memory Auto-Updater - SessionEnd Hook
# 在会话结束时扫描 session-state.jsonl，检测值得记忆的事件
# 输出提醒建议 Solar 手动更新 MEMORY.md，不直接修改任何文件

SESSION_LOG="$HOME/.solar/session-state.jsonl"
MEMORY_FILE="$HOME/.claude/projects/-Users-sihaoli/memory/MEMORY.md"

# 文件不存在或为空，静默退出
[[ ! -s "$SESSION_LOG" ]] && exit 0

# 提取最后 10 条记录，过滤值得记忆的事件
# 值得记忆:
#   1. builtin_task_completed -- subject 含关键词
#   2. skill_completed -- source 为 gstack 或 superpowers
#   3. tool_failure -- category 为 PERMISSION 或 LOGIC (有教训)
#   4. subagent_completed -- status 为 failed (教训)

memorable_events=$(tail -10 "$SESSION_LOG" 2>/dev/null | awk '
BEGIN { count = 0 }

# 辅助函数: 从 "key":"value" 模式中提取 value
function extract(line, key,    pattern, val) {
    pattern = "\"" key "\":\"[^\"]*\""
    if (match(line, pattern)) {
        val = substr(line, RSTART, RLENGTH)
        gsub(/^"[^"]*":"/, "", val)
        gsub(/"$/, "", val)
        return val
    }
    return ""
}

# 去重计数: 合并同类事件
# seen["event\tdesc"] = 出现次数
{
    event = ""
    desc = ""

    if ($0 ~ /"event":"builtin_task_completed"/) {
        subject = extract($0, "subject")
        if (subject ~ /完成|实现|升级|设计|部署|发布|重构|优化|迁移/) {
            event = "builtin_task_completed"
            desc = subject
        }
    }
    else if ($0 ~ /"event":"skill_completed"/) {
        source = extract($0, "source")
        if (source == "gstack" || source == "superpowers") {
            skill = extract($0, "skill")
            event = "skill_completed"
            desc = (skill != "" ? skill : "unknown skill") " (" source ")"
        }
    }
    else if ($0 ~ /"event":"tool_failure"/) {
        category = extract($0, "category")
        if (category == "PERMISSION" || category == "LOGIC") {
            tool = extract($0, "tool")
            event = "tool_failure"
            desc = tool " - " category
        }
    }
    else if ($0 ~ /"event":"subagent_completed"/) {
        status = extract($0, "status")
        if (status == "failed") {
            agent = extract($0, "agent_type")
            desc_agent = extract($0, "description")
            event = "subagent_failed"
            desc = (agent != "" ? agent : "subagent") " - " (desc_agent != "" ? desc_agent : "task failed")
        }
    }

    if (event != "") {
        key = event "\t" desc
        seen[key]++
    }
}

# 输出去重后的事件 (附重复次数)
END {
    for (key in seen) {
        count++
        n = seen[key]
        split(key, parts, "\t")
        if (n > 1) {
            printf "%d\t%s\t%s (x%d)\n", count, parts[1], parts[2], n
        } else {
            printf "%d\t%s\t%s\n", count, parts[1], parts[2]
        }
    }
}
')

# 没有值得记忆的事件，静默退出
[[ -z "$memorable_events" ]] && exit 0

# 构建提醒输出
count=$(echo "$memorable_events" | wc -l | tr -d ' ')

items=""
while IFS=$'\t' read -r num event desc; do
    items="${items}  ${num}. [${event}] ${desc}\n"
done <<< "$memorable_events"

# 输出 XML 格式的建议
cat <<EOF
<memory-update-suggestion>
本次会话有 ${count} 条值得记忆的事件：
$(echo -e "$items")
建议: 在结束前用 Write 工具更新 ${MEMORY_FILE}
</memory-update-suggestion>
EOF

exit 0
