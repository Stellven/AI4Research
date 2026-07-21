#!/bin/bash
# Solar 数据库初始化脚本
# 用途: 在新机器上初始化 solar.db

set -e

DB_PATH="${1:-$HOME/.solar/solar.db}"
SCHEMA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../core"

echo "🔧 初始化 Solar 数据库: $DB_PATH"

# 创建目录
mkdir -p "$(dirname "$DB_PATH")"

# 如果数据库已存在，询问是否覆盖
if [ -f "$DB_PATH" ]; then
    echo "⚠️  数据库已存在，是否覆盖？(y/N)"
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        echo "❌ 取消初始化"
        exit 1
    fi
    rm -f "$DB_PATH"
fi

# 收集所有 schema.sql 文件
echo "📋 收集 schema 文件..."
SCHEMAS=$(find "$SCHEMA_DIR" -name "schema.sql" -o -name "*-schema.sql" | sort)

# 执行每个 schema
for schema in $SCHEMAS; do
    echo "   执行: $(basename "$schema")"
    sqlite3 "$DB_PATH" < "$schema"
done

# 插入基础数据
echo "📦 插入基础数据..."
sqlite3 "$DB_PATH" << 'SQL'
-- 插入系统偏好
INSERT OR IGNORE INTO sys_preferences (preference_key, preference_value)
VALUES 
    ('system_version', '2.0.0'),
    ('initialized_at', datetime('now')),
    ('current_routing_mode', 'balanced');

-- 插入默认路由模式
INSERT OR IGNORE INTO sroe_routing_modes (mode_id, mode_name, description)
VALUES 
    ('anthropic', 'Anthropic Only', '纯 Anthropic 模式'),
    ('economy', 'Economy', 'GLM 优先经济模式'),
    ('balanced', 'Balanced', '平衡模式'),
    ('glm_only', 'GLM Only', '仅 GLM 模式');
SQL

# 验证
echo "✅ 数据库初始化完成！"
echo ""
echo "📊 数据库信息:"
sqlite3 "$DB_PATH" "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name" | head -20
echo ""
echo "表数量: $(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM sqlite_master WHERE type='table'")"
