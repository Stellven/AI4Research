#!/bin/bash
# Solar PreCompact Anchor
# PreCompact hook: 压缩前注入 STATE.md + 会话日志恢复锚点
# 触发: PreCompact (auto/manual, stdin=JSON with compaction details)
# 输出: exit 0 → stdout 作为压缩指令注入; exit 2 → 阻止压缩
# 性能: 单次 awk 遍历 STATE.md + 单次 awk 处理日志, 目标 < 50ms

source "$(dirname "${BASH_SOURCE[0]}")/hook-logger.sh"
_START_MS=$(hook_time_ms)

set -u

# ── 常量 ──────────────────────────────────────────────────
readonly SOLAR_DIR="$HOME/.solar"
readonly STATE_FILE="$SOLAR_DIR/STATE.md"
readonly SESSION_LOG="$SOLAR_DIR/session-state.jsonl"
readonly MAX_ANCHOR_CHARS=2000
readonly MAX_RECENT_EVENTS=5

# ── 消耗 stdin (PreCompact 可能通过 stdin 传递 JSON) ──────
cat > /dev/null 2>&1 || true

# ── 单次 awk 遍历 STATE.md, 输出带标记的段落 ─────────────
# 标记格式: __SECTION_START__ / __SECTION_END__ (不与正常内容冲突)
STATE_PARSED=""
if [[ -f "$STATE_FILE" ]]; then
    STATE_PARSED=$(awk '
    BEGIN {
        section = ""
        count = 0
    }
    {
        line = $0

        # ── Mission: "# Mission" 下一行非空非注释 ──
        if (line ~ /^# Mission/) {
            section = "mission"
            next
        }
        if (section == "mission") {
            if (line ~ /^#/ || line == "") {
                section = ""
                next
            }
            print "__MISSION_START__"
            print line
            print "__MISSION_END__"
            section = ""
            next
        }

        # ── Constraints: "# Constraints" 后非空行, 最多 4 条 ──
        if (line ~ /^# Constraints/) {
            section = "constraints"
            count = 0
            print "__CONSTRAINTS_START__"
            next
        }
        if (section == "constraints") {
            if (line ~ /^#[^# ]/ || line ~ /^## /) {
                print "__CONSTRAINTS_END__"
                section = ""
                # 不 next, 让其他规则处理这一行
            } else if (line != "") {
                print line
                count++
                if (count >= 4) {
                    print "  ... (更多见 STATE.md)"
                    print "__CONSTRAINTS_END__"
                    section = ""
                    next
                }
            }
            if (section == "") next
        }

        # ── In-Progress: "## In-Progress" 到下一个 "## ", 最多 8 行 ──
        if (line ~ /^## In-Progress/) {
            section = "in_progress"
            count = 0
            print "__INPROGRESS_START__"
            next
        }
        if (section == "in_progress") {
            if (line ~ /^## /) {
                print "__INPROGRESS_END__"
                section = ""
            } else if (line != "") {
                print line
                count++
                if (count >= 8) {
                    print "  ... (更多见 STATE.md)"
                    print "__INPROGRESS_END__"
                    section = ""
                    next
                }
            }
            if (section == "") next
        }

        # ── Next Actions: "# Next Actions" 后含 P0/P1 的行, 最多 4 条 ──
        if (line ~ /^# Next Actions/) {
            section = "next_actions"
            count = 0
            print "__NEXTACTIONS_START__"
            next
        }
        if (section == "next_actions") {
            if (line ~ /^#[^# ]/ && !(line ~ /^## /)) {
                print "__NEXTACTIONS_END__"
                section = ""
            } else if (line ~ /P[01]/) {
                print line
                count++
                if (count >= 4) {
                    print "__NEXTACTIONS_END__"
                    section = ""
                }
            }
            next
        }
    }
    END {
        # 如果文件末尾没有遇到终止标记, 补发
        if (section == "constraints") print "__CONSTRAINTS_END__"
        if (section == "in_progress") print "__INPROGRESS_END__"
        if (section == "next_actions") print "__NEXTACTIONS_END__"
    }
    ' "$STATE_FILE")
fi

# ── 用 awk 提取标记之间的内容 (macOS BSD 兼容) ──────────────
extract_between() {
    local start_marker="$1"
    local end_marker="$2"
    local text="$3"
    echo "$text" | awk -v s="$start_marker" -v e="$end_marker" '
        $0 == s { in_block = 1; next }
        $0 == e { in_block = 0; next }
        in_block { print }
    '
}
MISSION=$(extract_between "__MISSION_START__" "__MISSION_END__" "$STATE_PARSED")
CONSTRAINTS=$(extract_between "__CONSTRAINTS_START__" "__CONSTRAINTS_END__" "$STATE_PARSED")
IN_PROGRESS=$(extract_between "__INPROGRESS_START__" "__INPROGRESS_END__" "$STATE_PARSED")
NEXT_ACTIONS=$(extract_between "__NEXTACTIONS_START__" "__NEXTACTIONS_END__" "$STATE_PARSED")

# ── 单次 awk 处理 session-state.jsonl 最近 N 条 ──────────
RECENT_EVENTS=""
if [[ -f "$SESSION_LOG" ]]; then
    RECENT_EVENTS=$(tail -n "$MAX_RECENT_EVENTS" "$SESSION_LOG" 2>/dev/null | awk -F'"' '
    {
        ts = event = name = source = ""
        for (i = 1; i <= NF; i++) {
            if ($i == "ts") ts = $(i+2)
            if ($i == "event") event = $(i+2)
            if ($i == "task") name = $(i+2)
            if ($i == "source") source = $(i+2)
        }
        if (ts != "" && event != "" && name != "") {
            short_ts = substr(ts, 12, 5)
            printf "  [%s] %s: %s (%s)\n", short_ts, event, name, (source != "" ? source : "?")
        }
    }')
fi

# ── 组装锚点 ──────────────────────────────────────────────
OUTPUT="## Solar 恢复锚点 (PreCompact 注入)
重要: compact 后立即读取 ~/.solar/STATE.md 恢复完整态势
"

if [[ -n "$MISSION" ]]; then
    OUTPUT+="### Mission
${MISSION}
"
fi

if [[ -n "$CONSTRAINTS" ]]; then
    OUTPUT+="### Constraints (摘要)
${CONSTRAINTS}
"
fi

if [[ -n "$IN_PROGRESS" ]]; then
    OUTPUT+="### 当前进行中
${IN_PROGRESS}
"
fi

if [[ -n "$NEXT_ACTIONS" ]]; then
    OUTPUT+="### Next Actions (P0/P1)
${NEXT_ACTIONS}
"
fi

if [[ -n "$RECENT_EVENTS" ]]; then
    OUTPUT+="### 最近操作
${RECENT_EVENTS}
"
fi

# 添加承诺检查提醒
OUTPUT+="### 未完成承诺检查
- 检查上方「当前进行中」是否有未完成项
- 检查 STATE.md Progress 部分是否有遗漏
- 如果有未完成的编辑/测试/验证, 立即继续执行"

# ── 字符数裁剪 (硬限制 MAX_ANCHOR_CHARS) ──────────────────
if [[ ${#OUTPUT} -gt $MAX_ANCHOR_CHARS ]]; then
    OUTPUT="${OUTPUT:0:$((MAX_ANCHOR_CHARS - 30))}
... (已裁剪, 完整信息见 ~/.solar/STATE.md)"
fi

# ── 输出锚点并退出 ────────────────────────────────────────
echo "$OUTPUT"

hook_log "PreCompact" "pre-compact-anchor" "ok" "$(( $(hook_time_ms) - _START_MS ))" "chars=${#OUTPUT}"

exit 0
