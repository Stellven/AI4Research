#!/bin/bash
# Solar Personality Learner - 人格学习服务
# 从交互数据分析 Big Five 维度
# 每天凌晨 3 点执行 (launchd)

set -euo pipefail

DB_FILE="$HOME/.solar/solar.db"
LOG_FILE="$HOME/.solar/personality-learner.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

log "===== 人格学习开始 ====="

# ==================== 数据来源 ====================
# 从以下表提取行为特征：
# - evo_traces: 会话轨迹
# - evo_tool_calls: 工具调用
# - evo_feedback: 反馈记录
# - evo_sessions: 会话统计

# ==================== Openness 计算 ====================
# 指标：尝试新工具次数、创新方案比例
log "计算 Openness..."

# 统计最近7天使用的不同工具数量
UNIQUE_TOOLS=$(sqlite3 "$DB_FILE" "
SELECT COUNT(DISTINCT tool_name)
FROM evo_tool_calls
WHERE created_at > datetime('now', '-7 days');
" 2>/dev/null || echo "10")

# 归一化 (假设 20+ 种工具是高 Openness)
OPENNESS=$(echo "scale=2; if ($UNIQUE_TOOLS > 20) 0.9 else $UNIQUE_TOOLS / 22" | bc)
log "  Unique tools: $UNIQUE_TOOLS → Openness: $OPENNESS"

# ==================== Conscientiousness 计算 ====================
# 指标：任务完成率、代码质量
log "计算 Conscientiousness..."

# 统计任务完成率 (从 traces 或其他表)
# 简化：使用工具调用成功率
SUCCESS_RATE=$(sqlite3 "$DB_FILE" "
SELECT CAST(SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS REAL) / COUNT(*)
FROM evo_tool_calls
WHERE created_at > datetime('now', '-7 days');
" 2>/dev/null || echo "0.85")

CONSCIENTIOUSNESS=${SUCCESS_RATE:-0.85}
log "  Success rate: $SUCCESS_RATE → Conscientiousness: $CONSCIENTIOUSNESS"

# ==================== Extraversion 计算 ====================
# 指标：输出详细程度、emoji 使用
log "计算 Extraversion..."

# 简化：使用平均响应长度
AVG_LENGTH=$(sqlite3 "$DB_FILE" "
SELECT AVG(LENGTH(response))
FROM evo_traces
WHERE created_at > datetime('now', '-7 days');
" 2>/dev/null || echo "500")

# 归一化 (假设 1000+ 字符是高 Extraversion)
EXTRAVERSION=$(echo "scale=2; if ($AVG_LENGTH > 1000) 0.8 else $AVG_LENGTH / 1250" | bc 2>/dev/null || echo "0.5")
log "  Avg response length: $AVG_LENGTH → Extraversion: $EXTRAVERSION"

# ==================== Agreeableness 计算 ====================
# 指标：接受建议率、感谢表达
log "计算 Agreeableness..."

# 简化：使用正面反馈比例
POSITIVE_FEEDBACK=$(sqlite3 "$DB_FILE" "
SELECT CAST(SUM(CASE WHEN sentiment > 0 THEN 1 ELSE 0 END) AS REAL) / NULLIF(COUNT(*), 0)
FROM evo_feedback
WHERE created_at > datetime('now', '-7 days');
" 2>/dev/null || echo "0.7")

AGREEABLENESS=${POSITIVE_FEEDBACK:-0.7}
log "  Positive feedback: $POSITIVE_FEEDBACK → Agreeableness: $AGREEABLENESS"

# ==================== Neuroticism 计算 ====================
# 指标：错误后恢复时间、压力下表现
log "计算 Neuroticism..."

# 简化：使用错误率的反向
ERROR_RATE=$(sqlite3 "$DB_FILE" "
SELECT CAST(SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) AS REAL) / NULLIF(COUNT(*), 0)
FROM evo_tool_calls
WHERE created_at > datetime('now', '-7 days');
" 2>/dev/null || echo "0.1")

NEUROTICISM=$(echo "scale=2; $ERROR_RATE * 2" | bc 2>/dev/null || echo "0.2")
# 限制范围
if (( $(echo "$NEUROTICISM > 0.5" | bc -l) )); then
    NEUROTICISM="0.5"
fi
log "  Error rate: $ERROR_RATE → Neuroticism: $NEUROTICISM"

# ==================== 更新数据库 ====================
log "更新 Big Five 数据..."

sqlite3 "$DB_FILE" "
UPDATE sys_personality_big_five
SET current_value = CASE dimension
    WHEN 'O' THEN $OPENNESS
    WHEN 'C' THEN $CONSCIENTIOUSNESS
    WHEN 'E' THEN $EXTRAVERSION
    WHEN 'A' THEN $AGREEABLENESS
    WHEN 'N' THEN $NEUROTICISM
    ELSE current_value
END,
evidence = json_insert(COALESCE(evidence, '[]'), '\$[#]', '$(date +%Y-%m-%d)'),
updated_at = datetime('now')
WHERE personality_id = 'academic';
"

# 记录历史
sqlite3 "$DB_FILE" "
INSERT INTO ont_preference_history (dimension_id, old_value, new_value, change_reason, changed_at)
SELECT 'big_five_' || dimension, base_value, current_value, 'daily_learning', datetime('now')
FROM sys_personality_big_five
WHERE personality_id = 'academic';
" 2>/dev/null || true

log "===== 人格学习完成 ====="
log "Big Five 更新: O=$OPENNESS C=$CONSCIENTIOUSNESS E=$EXTRAVERSION A=$AGREEABLENESS N=$NEUROTICISM"
