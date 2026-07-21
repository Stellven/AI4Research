#!/bin/bash
# Solar Memory Consolidator - 记忆巩固服务
# Episodic → Semantic → Procedural 转换
# 每小时执行一次 (launchd)

set -euo pipefail

DB_FILE="$HOME/.solar/solar.db"
LOG_FILE="$HOME/.solar/memory-consolidator.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

log "===== 记忆巩固开始 ====="

# ==================== Phase 1: Episodic → Semantic ====================
# 找出相似的经历，提取为语义知识

log "Phase 1: Episodic → Semantic 巩固"

# 查找待巩固的情景记忆 (相似经历 >= 3 次)
sqlite3 "$DB_FILE" <<'EOF'
-- 标记需要巩固的情景记忆
INSERT INTO evo_consolidation_queue (source_type, source_id, target_type, status)
SELECT 'episodic', memory_id, 'semantic', 'pending'
FROM evo_memory_episodic
WHERE consolidated = 0
  AND importance >= 0.5
  AND memory_id NOT IN (SELECT source_id FROM evo_consolidation_queue WHERE source_type = 'episodic')
GROUP BY substr(event_summary, 1, 50)  -- 简单的相似性判断
HAVING COUNT(*) >= 2;
EOF

# 处理队列
PENDING=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM evo_consolidation_queue WHERE status='pending' AND target_type='semantic';")
log "  待处理: $PENDING 条"

if [[ "$PENDING" -gt 0 ]]; then
    # 这里需要 LLM 来做真正的模式提取
    # 目前先标记为需要 Claude 处理
    sqlite3 "$DB_FILE" "UPDATE evo_consolidation_queue SET status='needs_llm' WHERE status='pending' AND target_type='semantic';"
    log "  已标记 $PENDING 条待 LLM 处理"
fi

# ==================== Phase 2: Semantic → Procedural ====================
# 找出重复使用的知识，抽象为技能

log "Phase 2: Semantic → Procedural 抽象"

# 查找高频使用的语义记忆
sqlite3 "$DB_FILE" <<'EOF'
INSERT INTO evo_consolidation_queue (source_type, source_id, target_type, status)
SELECT 'semantic', memory_id, 'procedural', 'pending'
FROM evo_memory_semantic
WHERE access_count >= 5
  AND confidence >= 0.8
  AND memory_id NOT IN (SELECT source_id FROM evo_consolidation_queue WHERE source_type = 'semantic');
EOF

PENDING=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM evo_consolidation_queue WHERE status='pending' AND target_type='procedural';")
log "  待处理: $PENDING 条"

# ==================== Phase 3: 记忆链接更新 ====================
log "Phase 3: 更新记忆链接"

# 衰减长时间未激活的链接
sqlite3 "$DB_FILE" <<'EOF'
UPDATE evo_memory_links
SET strength = MAX(0.1, strength - 0.05)
WHERE last_activated < datetime('now', '-7 days')
  AND strength > 0.1;
EOF

# ==================== 统计 ====================
EPISODIC=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM evo_memory_episodic;")
SEMANTIC=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM evo_memory_semantic;")
PROCEDURAL=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM evo_memory_procedural;")
LINKS=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM evo_memory_links;" 2>/dev/null || echo "0")

log "===== 巩固完成 ====="
log "记忆统计: E=$EPISODIC S=$SEMANTIC P=$PROCEDURAL Links=$LINKS"
