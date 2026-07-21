#!/bin/bash
# Solar 数据资产检查提醒 Hook v1.1
# 在用户输入包含关键词时自动提醒先查已有资产
# FIX: 使用 stdin JSON 格式获取用户输入

# 从 stdin 读取 JSON 格式输入
INPUT=$(cat)
PROMPT=$(echo "$INPUT" | jq -r '.user_prompt // ""' 2>/dev/null)

# 如果没有输入，直接退出
[ -z "$PROMPT" ] && exit 0

KEYWORDS="索引|搜索|数据|分析|计算|统计|盘点|建立|创建|实现|开发|构建|生成"

# 排除简单查询
EXCLUDE="查看|显示|列出|帮我看|给我看|是什么|怎么"

if echo "$PROMPT" | grep -qE "$KEYWORDS"; then
    if ! echo "$PROMPT" | grep -qE "$EXCLUDE"; then
        cat << 'EOF'

┌─────────────────────────────────────────────────────────────────┐
│  ⚠️  数据资产检查提醒 (guardian-data-first)                     │
├─────────────────────────────────────────────────────────────────┤
│  请先执行以下检查，确认无现有方案后再开始：                     │
│                                                                 │
│  1. Tantivy: solar-search query "关键词"                        │
│  2. 资产表: SELECT * FROM sys_data_assets WHERE ...             │
│  3. 资源表: SELECT * FROM sys_resources WHERE ...               │
└─────────────────────────────────────────────────────────────────┘

EOF
    fi
fi

exit 0
