#!/bin/bash
# Subconscious Learn — 从 Sprint 评审结果提取教训
# 入口: coordinator.sh 的 handle_passed() + handle_failed_review()
# 不依赖 Claude Stop hook，确定触发

BRAIN_DIR="$HOME/.solar/harness/brain"
SPRINTS_DIR="$HOME/.solar/harness/sprints"
LESSONS_FILE="$BRAIN_DIR/lessons.jsonl"
LOG_FILE="$BRAIN_DIR/learn.log"

mkdir -p "$BRAIN_DIR"

# 找最近有 eval.json 的 Sprint
LATEST_EVAL=$(ls -t "$SPRINTS_DIR"/*.eval.json 2>/dev/null | head -1)
[[ -z "$LATEST_EVAL" ]] && exit 0

SID=$(basename "$LATEST_EVAL" .eval.json)

# 幂等: 已学过跳过
[[ -f "$LESSONS_FILE" ]] && grep -q "\"sprint_id\":\"$SID\"" "$LESSONS_FILE" 2>/dev/null && exit 0

MARKER="$BRAIN_DIR/.learning-$SID"
[[ -f "$MARKER" ]] && exit 0
touch "$MARKER"

# 异步提取
(
  TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  # === 从 eval.json 提取 (主要来源, 最结构化) ===
  python3 << PYEOF >> "$LESSONS_FILE"
import json, sys

try:
    data = json.load(open("$LATEST_EVAL"))
except:
    sys.exit(0)

sid = "$SID"
ts = "$TS"
verdict = data.get("verdict", "")
errors = data.get("errors", [])
failed = data.get("failed_conditions", [])

# 从 errors 数组提取 fix_hint (最有价值的教训)
for err in errors:
    hint = err.get("fix_hint", "")
    cond = err.get("cond", "")
    evidence = err.get("evidence", "")
    if hint and len(hint) > 10:
        print(json.dumps({
            "ts": ts, "sprint_id": sid,
            "lesson": f"[{cond}] {hint[:100]}",
            "source": "eval_error",
            "confidence": 0.9,
            "tags": ["FAIL", cond]
        }, ensure_ascii=False))

# 如果 verdict=FAIL 但 errors 为空, 从 failed_conditions 生成通用教训
if verdict == "FAIL" and not errors and failed:
    print(json.dumps({
        "ts": ts, "sprint_id": sid,
        "lesson": f"Sprint FAIL, 未通过: {', '.join(failed[:5])}",
        "source": "eval_verdict",
        "confidence": 0.7,
        "tags": ["FAIL"] + failed[:3]
    }, ensure_ascii=False))

# 如果 verdict=PASS, 记录成功模式 (低权重, 但有价值)
if verdict == "PASS" and not errors:
    passed = data.get("passed_conditions", [])
    if len(passed) >= 3:
        print(json.dumps({
            "ts": ts, "sprint_id": sid,
            "lesson": f"Sprint PASS ({len(passed)} Done 一次过)",
            "source": "eval_pass",
            "confidence": 0.5,
            "tags": ["PASS"]
        }, ensure_ascii=False))
PYEOF

  # === 从 eval.md 提取"关键发现"段落 (补充) ===
  EVAL_MD="$SPRINTS_DIR/${SID}.eval.md"
  if [[ -f "$EVAL_MD" ]]; then
    python3 << PYEOF >> "$LESSONS_FILE"
import json, re

text = open("$EVAL_MD").read()
sid = "$SID"
ts = "$TS"

# 找"关键发现"/"已知限制"/"建议"段落
for pattern in [r'##\s*关键发现\n(.*?)(?=\n##|\Z)', r'##\s*已知限制\n(.*?)(?=\n##|\Z)', r'##\s*建议\n(.*?)(?=\n##|\Z)']:
    match = re.search(pattern, text, re.DOTALL)
    if match:
        lines = [l.strip().lstrip('- ').lstrip('* ') for l in match.group(1).split('\n') if l.strip() and len(l.strip()) > 15 and len(l.strip()) < 120]
        for line in lines[:2]:
            print(json.dumps({
                "ts": ts, "sprint_id": sid,
                "lesson": line[:100],
                "source": "eval_finding",
                "confidence": 0.75,
                "tags": ["finding"]
            }, ensure_ascii=False))
        break  # 只取第一个匹配的段落
PYEOF
  fi

  echo "[$TS] $SID: learn completed" >> "$LOG_FILE"
  rm -f "$MARKER"
) &
