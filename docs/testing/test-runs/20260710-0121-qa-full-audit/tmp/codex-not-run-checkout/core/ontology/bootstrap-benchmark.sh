#!/bin/bash
# Bootstrap Benchmark Samples
# 从轨迹数据自动识别极端样本

set -euo pipefail

DB_FILE="$HOME/.solar/solar.db"
PROJECTS_DIR="$HOME/.claude/projects"

echo "┌─────────────────────────────────────────────────────────────────┐"
echo "│           Bootstrap Personality Benchmark 样本                  │"
echo "├─────────────────────────────────────────────────────────────────┤"

# ==================== 1. 查找极端高 C 样本 (高 Todo 使用) ====================
echo "│  查找极端高 C 样本 (Todo 使用频繁)...                           │"

for file in $(find "$PROJECTS_DIR" -name "*.jsonl" -type f -size +100k 2>/dev/null | head -50); do
    TODO_COUNT=$(grep -c '"name":"TodoWrite"' "$file" 2>/dev/null || echo "0")
    if [[ "$TODO_COUNT" -gt 30 ]]; then
        SESSION_ID=$(basename "$file" .jsonl)
        SHORT_ID="${SESSION_ID:0:8}"
        echo "│    找到: $SESSION_ID (Todo: $TODO_COUNT 次)"

        sqlite3 "$DB_FILE" "
        INSERT OR IGNORE INTO benchmark_personality_samples
        (sample_id, session_id, trajectory_file, labeled_C, label_source, label_confidence, notes)
        VALUES (
            'extreme_high_c_$SHORT_ID',
            '$SESSION_ID',
            '$file',
            0.95,
            'extreme',
            0.8,
            'Todo使用频繁，自动标注高C'
        );
        " 2>/dev/null || true
    fi
done

# ==================== 2. 查找极端高 O 样本 (工具多样性) ====================
echo "│  查找极端高 O 样本 (工具种类多)...                              │"

for file in $(find "$PROJECTS_DIR" -name "*.jsonl" -type f -size +100k 2>/dev/null | head -50); do
    TOOL_TYPES=$(grep -o '"name":"[^"]*"' "$file" 2>/dev/null | sort -u | wc -l | tr -d ' ')
    if [[ "$TOOL_TYPES" -gt 8 ]]; then
        SESSION_ID=$(basename "$file" .jsonl)
        SHORT_ID="${SESSION_ID:0:8}"
        echo "│    找到: $SESSION_ID (工具种类: $TOOL_TYPES)"

        sqlite3 "$DB_FILE" "
        INSERT OR IGNORE INTO benchmark_personality_samples
        (sample_id, session_id, trajectory_file, labeled_O, label_source, label_confidence, notes)
        VALUES (
            'extreme_high_o_$SHORT_ID',
            '$SESSION_ID',
            '$file',
            0.90,
            'extreme',
            0.7,
            '工具种类多，自动标注高O'
        );
        " 2>/dev/null || true
    fi
done

# ==================== 3. 统计结果 ====================
echo "├─────────────────────────────────────────────────────────────────┤"

TOTAL=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM benchmark_personality_samples;")
BY_SOURCE=$(sqlite3 "$DB_FILE" "
SELECT label_source, COUNT(*)
FROM benchmark_personality_samples
GROUP BY label_source;
")

echo "│  Benchmark 样本统计:                                            │"
echo "│    总数: $TOTAL"
echo "$BY_SOURCE" | while IFS='|' read -r src cnt; do
    echo "│    $src: $cnt"
done

echo "├─────────────────────────────────────────────────────────────────┤"
echo "│  需要监护人手动标注:                                            │"
echo "│    请选择 ~20 个有代表性的会话，运行:                           │"
echo "│    sqlite3 ~/.solar/solar.db \"INSERT INTO benchmark_...\"      │"
echo "└─────────────────────────────────────────────────────────────────┘"

echo ""
echo "查看已有样本:"
echo "sqlite3 ~/.solar/solar.db \"SELECT sample_id, labeled_O, labeled_C, notes FROM benchmark_personality_samples;\""
