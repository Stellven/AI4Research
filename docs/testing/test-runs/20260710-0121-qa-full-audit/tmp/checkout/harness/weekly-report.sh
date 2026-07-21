#!/bin/bash
# ── weekly-report.sh ──
# Sprint sprint-20260417-213604, D6: 周报自动生成
#
# 汇总过去 7 天的 Sprint 数据、能力趋势、改进堆积
# 产出: ~/.solar/reports/weekly-YYYYMMDD.md
#
# 手动运行: bash ~/.solar/harness/weekly-report.sh
# Cron: 0 2 * * 0 bash ~/.solar/harness/weekly-report.sh

set -uo pipefail

HARNESS_DIR="$HOME/.solar/harness"
SPRINTS_DIR="$HARNESS_DIR/sprints"
REPORTS_DIR="$HOME/.solar/reports"
GRAPH_FILE="$HARNESS_DIR/capability-graph.jsonl"
IMPROVEMENTS_FILE="$HARNESS_DIR/pending-improvements.jsonl"
LESSONS_FILE="$HARNESS_DIR/brain/lessons.jsonl"
KPI_FILE="$HARNESS_DIR/kpi.json"

mkdir -p "$REPORTS_DIR"

TODAY=$(date -u +%Y%m%d)
REPORT_FILE="$REPORTS_DIR/weekly-${TODAY}.md"
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# ── 计算时间窗口 (过去 7 天) ──
SEVEN_DAYS_AGO=$(date -u -v-7d +%Y-%m-%dT00:00:00Z 2>/dev/null || date -u -d '7 days ago' +%Y-%m-%dT00:00:00Z 2>/dev/null || echo "1970-01-01T00:00:00Z")

python3 << PYEOF
import json, os, glob, datetime

sprints_dir = "$SPRINTS_DIR"
report_file = "$REPORT_FILE"
ts = "$TS"
seven_days_ago = "$SEVEN_DAYS_AGO"
graph_file = "$GRAPH_FILE"
imp_file = "$IMPROVEMENTS_FILE"
lessons_file = "$LESSONS_FILE"
kpi_file = "$KPI_FILE"

# ── 1. Sprint 统计 (过去 7 天) ──
files = glob.glob(os.path.join(sprints_dir, "sprint-*.status.json"))
total = 0
passed = 0
failed = 0
other = 0
rounds_list = []
recent_sprints = []

for f in files:
    try:
        d = json.load(open(f))
        st = d.get("status", "")
        updated = d.get("updated_at", "1970-01-01T00:00:00Z")
        if st in ("drafting", "cancelled", "superseded"):
            continue
        total += 1
        r = d.get("round", 1)
        if st in ("passed", "eval_pass"):
            passed += 1
            rounds_list.append(r)
        elif st in ("failed",):
            failed += 1
        else:
            other += 1
        if updated >= seven_days_ago:
            recent_sprints.append(d)
    except:
        pass

pass_rate = round(passed / total, 3) if total > 0 else 0
avg_rounds = round(sum(rounds_list) / len(rounds_list), 2) if rounds_list else 0

# ── 2. 能力趋势 ──
latest_caps = {}
try:
    for line in open(graph_file):
        d = json.loads(line.strip())
        cid = d.get("capability_id", "")
        latest_caps[cid] = d
except:
    pass

cap_by_category = {}
for cid, d in latest_caps.items():
    cat = d.get("category", "Z_Unknown")
    if cat not in cap_by_category:
        cap_by_category[cat] = []
    cap_by_category[cat].append(d)

low_score_caps = [(d.get("name", cid), d.get("quality_score", 1.0), d.get("used_count", 0))
                  for cid, d in latest_caps.items() if d.get("quality_score", 1.0) < 0.5 and d.get("used_count", 0) >= 3]

# ── 3. 改进堆积 ──
improvements = []
try:
    for line in open(imp_file):
        improvements.append(json.loads(line.strip()))
except:
    pass

high_imp = [i for i in improvements if i.get("priority") == "high"]
medium_imp = [i for i in improvements if i.get("priority") == "medium"]
low_imp = [i for i in improvements if i.get("priority") == "low"]

# ── 4. 近期教训 ──
recent_lessons = []
try:
    for line in open(lessons_file):
        d = json.loads(line.strip())
        if d.get("ts", "1970") >= seven_days_ago:
            recent_lessons.append(d)
except:
    pass

# ── 5. KPI 快照 ──
kpi = {}
try:
    kpi = json.load(open(kpi_file))
except:
    pass

# ── 生成报告 ──
lines = []
lines.append(f"# Solar Harness 周报 — {ts[:10]}")
lines.append("")
lines.append("## Sprint 概览")
lines.append("")
lines.append(f"| 指标 | 值 |")
lines.append(f"|------|-----|")
lines.append(f"| 总 Sprint | {total} |")
lines.append(f"| 通过 | {passed} |")
lines.append(f"| 失败 | {failed} |")
lines.append(f"| 通过率 | {pass_rate:.1%} |")
lines.append(f"| 平均轮数 | {avg_rounds} |")
lines.append(f"| 最近 7 天活跃 | {len(recent_sprints)} |")
lines.append("")

lines.append("## 能力图谱摘要")
lines.append("")
for cat in sorted(cap_by_category.keys()):
    caps = cap_by_category[cat]
    avg_score = sum(c.get("quality_score", 0.5) for c in caps) / len(caps) if caps else 0
    lines.append(f"- **{cat}**: {len(caps)} 项, 平均分 {avg_score:.2f}")
lines.append("")

if low_score_caps:
    lines.append("### 低分能力 (quality < 0.5)")
    lines.append("")
    for name, score, used in sorted(low_score_caps, key=lambda x: x[1]):
        lines.append(f"- {name}: {score:.2f} (使用 {used} 次)")
    lines.append("")
else:
    lines.append("无低分能力告警")
    lines.append("")

lines.append("## 改进建议堆积")
lines.append("")
lines.append(f"| 优先级 | 数量 |")
lines.append(f"|--------|------|")
lines.append(f"| High | {len(high_imp)} |")
lines.append(f"| Medium | {len(medium_imp)} |")
lines.append(f"| Low | {len(low_imp)} |")
lines.append(f"| **总计** | {len(improvements)} |")
lines.append("")

if recent_lessons:
    lines.append("## 近期教训 (7 天)")
    lines.append("")
    for lesson in recent_lessons[-10:]:
        lines.append(f"- {lesson.get('lesson', 'N/A')[:100]}")
    lines.append("")

lines.append("## KPI 快照")
lines.append("")
lines.append(f"- 平均质量分: {kpi.get('avg_quality_score', 'N/A')}")
lines.append(f"- 平均轮数: {kpi.get('avg_rounds', 'N/A')}")
lines.append(f"- 通过率: {kpi.get('pass_rate', 'N/A')}")
lines.append("")
lines.append(f"---")
lines.append(f"*Auto-generated by weekly-report.sh at {ts}*")

with open(report_file, "w") as f:
    f.write("\n".join(lines))

print(f"[weekly] 报告已生成: {report_file}")
PYEOF

exit 0
