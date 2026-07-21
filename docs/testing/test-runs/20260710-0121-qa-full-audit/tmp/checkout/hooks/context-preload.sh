#!/bin/bash
# Solar 上下文预加载 Hook
# 根据模型成本动态调整上下文加载量：
# - 便宜模型 (GLM) → 加载更多上下文和记忆 (铁律、记忆、历史)
# - 贵模型 (Anthropic) → 精简上下文，质量优先

DB_PATH="$HOME/.solar/solar.db"
CONTEXT_BUDGET="$HOME/.claude/core/context/context-budget.ts"

# 获取当前路由模式 (从 sys_preferences 表，使用正确的列名)
MODE=$(sqlite3 "$DB_PATH" "SELECT json_extract(preference_value, '\$.mode') FROM sys_preferences WHERE preference_type='system' AND preference_key='brain_router_mode'" 2>/dev/null)

# 如果没有设置，默认为 anthropic
if [ -z "$MODE" ]; then
    MODE="anthropic"
fi

# 根据模式确定模型
case "$MODE" in
  "economy"|"glm_only")
    MODEL="zhipu:glm-4-plus"
    TIER="便宜"
    ;;
  "anthropic")
    MODEL="anthropic:sonnet"
    TIER="中等"
    ;;
  *)
    MODEL="anthropic:sonnet"
    TIER="中等"
    ;;
esac

cat << EOF

╭─────────────────────────────────────────────────────────────────╮
│  📦 Solar 上下文预加载                                          │
│  模型: $MODEL ($TIER)                                           │
│  策略: $([ "$TIER" = "便宜" ] && echo "加载全部上下文+记忆" || echo "精简上下文")
╰─────────────────────────────────────────────────────────────────╯

EOF

# 如果 context-budget.ts 存在，使用它生成完整上下文
if [ -f "$CONTEXT_BUDGET" ]; then
    bun "$CONTEXT_BUDGET" generate "$MODEL" 2>/dev/null
else
    # 降级：简单版本
    echo "【搜索引擎】"
    if pgrep -f "solar-search daemon" > /dev/null; then
        echo "  ✓ Tantivy daemon 运行中"
    fi
    echo ""

    echo "【数据资产】"
    sqlite3 "$DB_PATH" "
    SELECT '  • ' || asset_type || ': ' || COUNT(*) || ' 项'
    FROM sys_data_assets GROUP BY asset_type;
    " 2>/dev/null
    echo ""

    echo "【已有能力】"
    sqlite3 "$DB_PATH" "
    SELECT '  • ' || resource_type || ': ' || COUNT(*) || ' 个'
    FROM sys_resources WHERE status = 'active' GROUP BY resource_type;
    " 2>/dev/null
    echo ""

    echo "【搜索入口】"
    echo "  • Tantivy: solar-search query \"关键词\""
    echo "  • 资产: SELECT * FROM sys_data_assets WHERE ..."
fi

cat << 'EOF'

────────────────────────────────────────────────────────────────────
⚠️  创建任何功能前，先搜索是否已存在！
────────────────────────────────────────────────────────────────────

EOF

exit 0
