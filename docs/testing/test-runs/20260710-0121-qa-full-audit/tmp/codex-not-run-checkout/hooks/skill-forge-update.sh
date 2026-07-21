#!/bin/bash
# Solar Skill Forge Auto-Runner
# SessionEnd hook: 会话结束时分析操作模式，生成技能
#
# 触发: SessionEnd
# 行为: 读取 session-state.jsonl 最近事件，调用 skill-forge analyze
# 如果检测到新模式 (frequency>=3)，自动保存 SKILL.md 到 ~/.claude/skills/auto/
#
# @module solar-farm/skill-forge-update

set -u

# 消耗 stdin
cat > /dev/null 2>&1 || true

BUN="$(which bun 2>/dev/null || true)"
if [[ -z "$BUN" ]]; then
    exit 0
fi

FORGE_SCRIPT="$HOME/.claude/core/solar-farm/skill-forge.ts"
STATE_FILE="$HOME/.solar/session-state.jsonl"
LOG_FILE="$HOME/.solar/logs/skill-forge.log"

# 异步执行，不阻塞会话结束
(
    mkdir -p "$(dirname "$LOG_FILE")"

    if [[ ! -f "$STATE_FILE" ]]; then
        exit 0
    fi

    # 提取最近 20 条事件作为会话摘要
    SUMMARY=$(tail -20 "$STATE_FILE" 2>/dev/null | python3 -c "
import sys, json
lines = []
for line in sys.stdin:
    try:
        d = json.loads(line.strip())
        ts = d.get('ts', '?')[:16]
        ev = d.get('event', '?')
        task = d.get('task', d.get('skill', d.get('tool', '')))
        lines.append(f'{ts} {ev}: {task[:80]}')
    except:
        pass
print('\n'.join(lines))
" 2>/dev/null)

    # 摘要太短则跳过
    if [[ -z "$SUMMARY" ]] || [[ ${#SUMMARY} -lt 20 ]]; then
        exit 0
    fi

    # 调用 skill-forge analyze (macOS 兼容，不用 timeout)
    RESULT=$("$BUN" run "$FORGE_SCRIPT" analyze "$SUMMARY" 2>&1)

    if [[ $? -eq 0 ]] && [[ -n "$RESULT" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] analyze OK: $RESULT" >> "$LOG_FILE"
    fi
) &>/dev/null &

exit 0
