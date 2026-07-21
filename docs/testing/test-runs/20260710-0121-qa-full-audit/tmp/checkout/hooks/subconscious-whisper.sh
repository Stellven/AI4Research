#!/bin/bash
# Subconscious Whisper — UserPromptSubmit hook
# 每次 prompt 注入最近 3 条教训，不做关键词匹配（Claude Code 不传 prompt 环境变量）
# 纯本地 tail + python3，< 100ms

BRAIN_DIR="$HOME/.solar/harness/brain"
LESSONS_FILE="$BRAIN_DIR/lessons.jsonl"

# 无数据则静默退出
[[ ! -f "$LESSONS_FILE" ]] && exit 0
[[ ! -s "$LESSONS_FILE" ]] && exit 0

# 取最近 3 条教训的 lesson 字段
WHISPER=$(tail -3 "$LESSONS_FILE" | python3 -c "
import json, sys
for line in sys.stdin:
    line = line.strip()
    if not line: continue
    try:
        d = json.loads(line)
        lesson = d.get('lesson', '')
        if lesson:
            print(f'- {lesson}')
    except:
        pass
" 2>/dev/null)

[[ -z "$WHISPER" ]] && exit 0

# 注入 (stdout 被 Claude Code 捕获为上下文)
cat << EOF
<system-reminder>
[Subconscious] 历史教训 (最近 3 条):
$WHISPER
</system-reminder>
EOF
