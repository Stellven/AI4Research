#!/bin/bash
# ── auto-boost-capability.sh ──
# Sprint sprint-20260418-065438, D2: 低分能力自启 Sprint
#
# 读 low-quality-capabilities.json, 对每条调 solar-intent 创建 drafting Sprint
# 配额控制 + 审核门槛 (drafting, 不自动激活)
#
# 用法: auto-boost-capability.sh

set -uo pipefail

HARNESS_DIR="$HOME/.solar/harness"
LOW_FILE="$HARNESS_DIR/low-quality-capabilities.json"
CONFIG_FILE="$HARNESS_DIR/auto-boost-config.json"
BOOST_LOG="$HARNESS_DIR/skipped-boosts.log"
INBOX="$HARNESS_DIR/PLANNER-INBOX.md"

TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
TODAY=$(date -u +%Y-%m-%d)

# 读配置
DAILY_LIMIT=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('daily_limit',3))" 2>/dev/null || echo "3")
TARGET_SCORE=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('target_score',0.7))" 2>/dev/null || echo "0.7")

[[ -f "$LOW_FILE" ]] || { echo "[boost] 无低分能力文件"; exit 0; }

# 计算今天已创建数
CREATED_TODAY=0
if [[ -f "$BOOST_LOG" ]]; then
  CREATED_TODAY=$(grep "$TODAY" "$BOOST_LOG" 2>/dev/null | grep '"created"' | wc -l | tr -d ' ')
fi

echo "[boost] 今日已创建: ${CREATED_TODAY}/${DAILY_LIMIT}"

# 逐条处理
python3 << PYEOF
import json, subprocess, os, sys
from datetime import datetime

low_file = "$LOW_FILE"
config_file = "$CONFIG_FILE"
boost_log = "$BOOST_LOG"
inbox = "$INBOX"
ts = "$TS"
today = "$TODAY"
daily_limit = int("$DAILY_LIMIT")
target_score = float("$TARGET_SCORE")

try:
    capabilities = json.load(open(low_file))
except:
    print("[boost] 无法读取低分能力文件")
    sys.exit(0)

if not capabilities:
    print("[boost] 无低分能力")
    sys.exit(0)

# 计算今天已创建数
created_today = 0
try:
    with open(boost_log) as f:
        for line in f:
            if today in line and '"created"' in line:
                created_today += 1
except:
    pass

remaining_quota = daily_limit - created_today
print(f"[boost] 配额剩余: {remaining_quota}/{daily_limit}")

for cap in capabilities:
    if remaining_quota <= 0:
        # 超限, 记录跳过
        record = json.dumps({"ts": ts, "capability_id": cap.get("capability_id",""),
                             "action": "skipped", "reason": f"每日上限 {daily_limit}"}, ensure_ascii=False)
        with open(boost_log, "a") as f:
            f.write(record + "\n")
        print(f"[boost] 跳过: {cap.get('name','')} (配额已满)")
        continue

    name = cap.get("name", cap.get("capability_id", ""))
    score = cap.get("quality_score", 0)
    intent = f"优化能力 {name}: 当前质量分 {score}, 目标 >= {target_score}"

    # 调 solar-intent
    try:
        result = subprocess.run(
            [os.path.expanduser("~/.solar/bin/solar-intent"), intent],
            capture_output=True, text=True, timeout=120
        )
        output = result.stdout.strip()

        # 记录创建
        record = json.dumps({"ts": ts, "capability_id": cap.get("capability_id",""),
                             "action": "created", "intent": intent[:60]}, ensure_ascii=False)
        with open(boost_log, "a") as f:
            f.write(record + "\n")

        # 通知规划者 (审核门槛)
        with open(inbox, "a") as f:
            f.write(f"- [ ] [{ts}] Auto-boost: {name} (score={score}) → 需审核\n")

        remaining_quota -= 1
        print(f"[boost] 创建: {name} ({output[:80]})")

    except Exception as e:
        record = json.dumps({"ts": ts, "capability_id": cap.get("capability_id",""),
                             "action": "error", "reason": str(e)[:80]}, ensure_ascii=False)
        with open(boost_log, "a") as f:
            f.write(record + "\n")
        print(f"[boost] 失败: {name} - {e}")

# 发桌面通知
total_created = daily_limit - remaining_quota
if total_created > 0:
    try:
        subprocess.run([os.path.expanduser("~/.solar/harness/osascript-notify.sh"),
                       "Solar Boost", f"创建了 {total_created} 个能力提升 Sprint", "Ping"],
                      timeout=10, capture_output=True)
    except:
        pass

PYEOF

exit 0
