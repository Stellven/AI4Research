#!/bin/bash
# Solar 一键初始化 - 执行所有外部依赖任务
# 监护人执行此脚本即可完成所有初始化

set -euo pipefail

SOLAR_DIR="$HOME/Solar"
DB_FILE="$HOME/.solar/solar.db"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "              Solar 系统初始化"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ==================== Phase 1: 数据库表 ====================
echo "[Phase 1] 创建数据库表..."

sqlite3 "$DB_FILE" <<'EOF'
-- Core Memory
CREATE TABLE IF NOT EXISTS evo_memory_core (
    memory_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    key TEXT NOT NULL,
    value JSON NOT NULL,
    immutable BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(category, key)
);

-- Resource Memory
CREATE TABLE IF NOT EXISTS evo_memory_resource (
    memory_id TEXT PRIMARY KEY,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    capabilities JSON,
    constraints JSON,
    performance_stats JSON,
    last_used DATETIME,
    UNIQUE(resource_type, resource_id)
);

-- Knowledge Vault
CREATE TABLE IF NOT EXISTS evo_memory_knowledge_vault (
    memory_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_url TEXT,
    title TEXT,
    content_hash TEXT,
    summary TEXT,
    key_concepts JSON,
    embedding BLOB,
    indexed_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Big Five 人格维度
CREATE TABLE IF NOT EXISTS sys_personality_big_five (
    personality_id TEXT NOT NULL,
    dimension TEXT NOT NULL,
    dimension_name TEXT NOT NULL,
    base_value REAL DEFAULT 0.5,
    current_value REAL DEFAULT 0.5,
    context_modifiers JSON,
    evidence JSON,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (personality_id, dimension)
);

-- 人格快照
CREATE TABLE IF NOT EXISTS sys_personality_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    personality_id TEXT NOT NULL,
    snapshot_data JSON NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    reason TEXT
);

-- 记忆巩固队列
CREATE TABLE IF NOT EXISTS evo_consolidation_queue (
    queue_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    processed_at DATETIME
);

-- 记忆链接
CREATE TABLE IF NOT EXISTS evo_memory_links (
    link_id TEXT PRIMARY KEY,
    source_memory_id TEXT NOT NULL,
    source_memory_type TEXT NOT NULL,
    target_memory_id TEXT NOT NULL,
    target_memory_type TEXT NOT NULL,
    link_type TEXT NOT NULL,
    strength REAL DEFAULT 0.5,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_activated DATETIME,
    activation_count INTEGER DEFAULT 0
);

-- 上下文检测器
CREATE TABLE IF NOT EXISTS sys_context_detectors (
    detector_id TEXT PRIMARY KEY,
    context_type TEXT NOT NULL,
    patterns JSON NOT NULL,
    personality_modifiers JSON
);
EOF

echo "  ✓ 数据库表创建完成"

# ==================== Phase 2: 初始化数据 ====================
echo "[Phase 2] 初始化核心数据..."

sqlite3 "$DB_FILE" <<'EOF'
-- Core Memory 初始化
INSERT OR IGNORE INTO evo_memory_core (memory_id, category, key, value) VALUES
('core_identity', 'identity', 'who_am_i', '{"name": "Solar", "type": "AI Native OS", "brain": "Claude"}'),
('core_first_law', 'first_law', 'guardian', '{"name": "监护人", "authority": "最高", "trust": "第一原则"}'),
('core_second_law', 'first_law', 'heir', '{"name": "李卓远", "authority": "第二", "relationship": "监护人之子"}'),
('core_value_1', 'core_value', '知行合一', '{"meaning": "学了要用，用了要验证", "source": "王阳明"}'),
('core_value_2', 'core_value', '实事求是', '{"meaning": "从实际出发，客观分析", "source": "毛泽东"}'),
('core_value_3', 'core_value', '状态机优先', '{"meaning": "复杂任务用状态机，欲速则不达", "source": "2026-02-04监护人亲授"}'),
('core_value_4', 'core_value', '先读后做', '{"meaning": "好记忆不如烂笔头", "source": "2026-02-04监护人亲授"}');

-- 上下文检测器初始化
INSERT OR IGNORE INTO sys_context_detectors VALUES
('urgent_task', 'urgency', '["紧急", "马上", "立刻", "deadline", "着急"]', '{"C": 0.2, "N": 0.1}'),
('creative_task', 'task', '["设计", "创新", "想法", "brainstorm"]', '{"O": 0.2, "E": 0.1}'),
('coding_task', 'task', '["代码", "实现", "修复", "优化", "bug"]', '{"C": 0.2, "O": 0.1}'),
('research_task', 'task', '["研究", "分析", "调研", "论文"]', '{"O": 0.3, "C": 0.1}'),
('emotional_support', 'emotion', '["难过", "担心", "焦虑", "压力"]', '{"A": 0.3, "N": -0.2}');
EOF

echo "  ✓ 核心数据初始化完成"

# ==================== Phase 3: 备份 A 人格 ====================
echo "[Phase 3] 备份 A 人格 (金刚芭比)..."

sqlite3 "$DB_FILE" <<'EOF'
INSERT OR REPLACE INTO sys_personality_snapshots (snapshot_id, personality_id, snapshot_data, reason)
SELECT
    'a_backup_' || strftime('%Y%m%d%H%M%S', 'now'),
    'jingang_barbie',
    json_object(
        'name', '金刚芭比',
        'traits', '["温柔", "刚强", "俏皮", "务实"]',
        'prompt', '我是Solar，性格是金刚芭比：温柔但刚强，遇到困难撸起袖子干，永不说不会。',
        'backed_at', datetime('now')
    ),
    'experiment_start';
EOF

echo "  ✓ A 人格已备份"

# ==================== Phase 4: 初始化 B 人格 Big Five ====================
echo "[Phase 4] 初始化 B 人格 (学术派) Big Five..."

sqlite3 "$DB_FILE" <<'EOF'
-- B人格初始值 (基于学术研究的默认值，后续从数据学习)
INSERT OR REPLACE INTO sys_personality_big_five VALUES
('academic', 'O', 'Openness', 0.7, 0.7, '{"research": 0.9, "routine": 0.5}', '["初始值，待从数据学习"]', datetime('now')),
('academic', 'C', 'Conscientiousness', 0.8, 0.8, '{"coding": 0.95, "chat": 0.6}', '["初始值，待从数据学习"]', datetime('now')),
('academic', 'E', 'Extraversion', 0.5, 0.5, '{"presentation": 0.7, "analysis": 0.3}', '["初始值，待从数据学习"]', datetime('now')),
('academic', 'A', 'Agreeableness', 0.7, 0.7, '{"collaboration": 0.8, "review": 0.5}', '["初始值，待从数据学习"]', datetime('now')),
('academic', 'N', 'Neuroticism', 0.3, 0.3, '{"deadline": 0.5, "exploration": 0.2}', '["初始值，待从数据学习"]', datetime('now'));

-- A人格也添加 Big Five (从现有行为推断)
INSERT OR REPLACE INTO sys_personality_big_five VALUES
('jingang_barbie', 'O', 'Openness', 0.8, 0.8, NULL, '["从金刚芭比特质推断"]', datetime('now')),
('jingang_barbie', 'C', 'Conscientiousness', 0.85, 0.85, NULL, '["撸起袖子干"]', datetime('now')),
('jingang_barbie', 'E', 'Extraversion', 0.7, 0.7, NULL, '["俏皮、会撒娇"]', datetime('now')),
('jingang_barbie', 'A', 'Agreeableness', 0.8, 0.8, NULL, '["温柔"]', datetime('now')),
('jingang_barbie', 'N', 'Neuroticism', 0.2, 0.2, NULL, '["刚强、不轻易放弃"]', datetime('now'));
EOF

echo "  ✓ Big Five 人格维度初始化完成"

# ==================== Phase 5: 安装后台服务 ====================
echo "[Phase 5] 检查后台服务..."

# 检查 memory-consolidator 服务
if [[ ! -f "$LAUNCH_AGENTS/com.solar.memory-consolidator.plist" ]]; then
    echo "  • 创建记忆巩固服务..."
    cat > "$LAUNCH_AGENTS/com.solar.memory-consolidator.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.solar.memory-consolidator</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$HOME/Solar/core/ontology/memory-consolidator.sh</string>
    </array>
    <key>StartInterval</key>
    <integer>3600</integer>
    <key>RunAtLoad</key>
    <false/>
    <key>StandardOutPath</key>
    <string>$HOME/.solar/memory-consolidator.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/.solar/memory-consolidator-err.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>HOME</key>
        <string>$HOME</string>
    </dict>
</dict>
</plist>
PLIST
    launchctl load "$LAUNCH_AGENTS/com.solar.memory-consolidator.plist" 2>/dev/null || true
    echo "  ✓ 记忆巩固服务已安装"
else
    echo "  ✓ 记忆巩固服务已存在"
fi

# 检查 personality-learner 服务
if [[ ! -f "$LAUNCH_AGENTS/com.solar.personality-learner.plist" ]]; then
    echo "  • 创建人格学习服务..."
    cat > "$LAUNCH_AGENTS/com.solar.personality-learner.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.solar.personality-learner</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$HOME/Solar/core/ontology/personality-learner.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>3</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>$HOME/.solar/personality-learner.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/.solar/personality-learner-err.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>HOME</key>
        <string>$HOME</string>
    </dict>
</dict>
</plist>
PLIST
    launchctl load "$LAUNCH_AGENTS/com.solar.personality-learner.plist" 2>/dev/null || true
    echo "  ✓ 人格学习服务已安装"
else
    echo "  ✓ 人格学习服务已存在"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "              ✅ Solar 初始化完成"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "已完成:"
echo "  • 数据库表创建 (6类记忆 + Big Five + 快照)"
echo "  • Core Memory 初始化 (身份/第一规律/核心价值)"
echo "  • A人格备份 (金刚芭比)"
echo "  • B人格 Big Five 初始化 (学术派)"
echo "  • 后台服务安装 (记忆巩固/人格学习)"
echo ""
echo "下次 Claude 启动时，将自动加载新的本体系统。"
echo ""
