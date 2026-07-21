#!/bin/bash
# ── whisper-hook-v2.sh ──
# Sprint sprint-20260418-232003, D2
#
# 从 session.jsonl 增量扫描用户最近需求 + lessons.jsonl 教训注入
# 解决: Claude Code hook 环境不提供 CLAUDE_USER_PROMPT
#
# 用法: 作为 UserPromptSubmit hook 或手动调用
# 输出: 最近用户需求 + 最近 3 条教训 (供上下文注入)

set -uo pipefail

HARNESS_DIR="$HOME/.solar/harness"
BRAIN_DIR="$HARNESS_DIR/brain"
LESSONS_FILE="$BRAIN_DIR/lessons.jsonl"
STATE_FILE="$HOME/.claude/.whisper-state.json"
OUTPUT_FILE="$HOME/.claude/.whisper-output.txt"

# ── 1. 从 lessons.jsonl 读取最近 3 条教训 ──
LESSONS=""
if [[ -f "$LESSONS_FILE" ]]; then
  LESSONS=$(tail -3 "$LESSONS_FILE" 2>/dev/null | python3 -c "
import sys, json
for line in sys.stdin:
    try:
        d = json.loads(line.strip())
        hint = d.get('fix_hint', d.get('lesson', ''))
        if hint:
            print(f'- {hint[:100]}')
    except: pass
" 2>/dev/null)
fi

# ── 2. 从 session.jsonl 增量扫描用户需求 ──
# 找最新的 session 文件 (最大 mtime)
SESSION_FILE=""
SESSION_DIR="$HOME/.claude/projects/-Users-sihaoli"
if [[ -d "$SESSION_DIR" ]]; then
  SESSION_FILE=$(find "$SESSION_DIR" -maxdepth 1 -name "*.jsonl" -not -path "*/subagents/*" -type f 2>/dev/null | xargs ls -t 2>/dev/null | head -1)
fi

RECENT_INPUT=""
if [[ -n "$SESSION_FILE" ]]; then
  # 增量扫描: 记录上次读到的字节数
  LAST_POS=0
  if [[ -f "$STATE_FILE" ]]; then
    LAST_POS=$(python3 -c "import json; print(json.load(open('$STATE_FILE')).get('last_pos',0))" 2>/dev/null || echo "0")
  fi

  # 获取文件大小
  FILE_SIZE=$(stat -f%z "$SESSION_FILE" 2>/dev/null || stat -c%s "$SESSION_FILE" 2>/dev/null || echo "0")

  # 如果文件变小了(新 session), 从头开始
  if [[ "$FILE_SIZE" -lt "$LAST_POS" ]]; then
    LAST_POS=0
  fi

  # 读取新增部分, 提取用户输入
  RECENT_INPUT=$(dd if="$SESSION_FILE" bs=1 skip="$LAST_POS" 2>/dev/null | python3 -c "
import sys, json
inputs = []
for line in sys.stdin:
    try:
        d = json.loads(line.strip())
        if d.get('type') == 'user':
            msg = d.get('message', {})
            content = msg.get('content', '')
            if isinstance(content, str) and len(content) > 10:
                inputs.append(content[:150])
            elif isinstance(content, list):
                for c in content:
                    if isinstance(c, dict) and c.get('type') == 'text' and len(c.get('text','')) > 10:
                        inputs.append(c['text'][:150])
    except: pass
for inp in inputs[-3:]:
    print(inp)
" 2>/dev/null)

  # 更新 position
  python3 -c "
import json
d = {'last_pos': $FILE_SIZE, 'ts': '$(date -u +%Y-%m-%dT%H:%M:%SZ)'}
json.dump(d, open('$STATE_FILE', 'w'), indent=2)
" 2>/dev/null
fi

# ── 3. 组合输出 ──
OUTPUT=""
if [[ -n "$RECENT_INPUT" ]]; then
  OUTPUT="[最近需求]\n${RECENT_INPUT}\n"
fi
if [[ -n "$LESSONS" ]]; then
  OUTPUT="${OUTPUT}[潜意识教训]\n${LESSONS}\n"
fi

if [[ -n "$OUTPUT" ]]; then
  printf "$OUTPUT" > "$OUTPUT_FILE"
  # 只在有内容时输出
  cat "$OUTPUT_FILE"
else
  echo "[whisper] 无新内容" > "$OUTPUT_FILE"
fi

exit 0
