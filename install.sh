#!/bin/bash
# Solar 一键部署脚本 — L1 + L2 全栈安装 (cp 模式)
#
# 行为:
#   L1 基础:
#     1. 备份 ~/.claude/ 现有内容 (如有)
#     2. 把仓库内 CLAUDE.md/rules/skills/agents/hooks/core/.claude/prompts 复制到 ~/.claude/
#     3. 创建 ~/.solar/ 目录 + 初始化 solar.db (如有 schema)
#   L2 高级:
#     4. 把仓库发布目录 harness/ → ~/.solar/harness/ + 创建 ~/.solar/bin/solar-harness 软链
#     5. 把 mempalace/ → ~/.solar/mempalace/
#     6. 把 codex-bridge/ → ~/.solar/codex-bridge/
#   验收:
#     7. 自检 14 项 verify
#
# 不做的事 (诚实):
#   - 不 git clone 别的仓库
#   - 不写入 API keys (用户自己编辑 .env)
#   - 不跑 Python 依赖 (mempalace 需 chromadb/mcp/sentence-transformers, 见 SKILLS-INSTALL.md)
#   - 不安装第三方 skill packs；仓库内置 skills 会复制，第三方增强包见 SKILLS-INSTALL.md

set -e

SOLAR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="$HOME/.claude"
SOLAR_HOME="$HOME/.solar"

echo "🚀 Solar 一键部署 (L1 + L2 全栈)"
echo "================================"
echo ""

# Step 1: 创建 ~/.claude/ (如不存在)
if [ ! -d "$CLAUDE_DIR" ]; then
    echo "📁 创建 $CLAUDE_DIR ..."
    mkdir -p "$CLAUDE_DIR"
fi

# Step 2: 备份现有配置 (如存在)
if [ -f "$CLAUDE_DIR/CLAUDE.md" ]; then
    BACKUP_DIR="$CLAUDE_DIR/backup-$(date +%Y%m%d_%H%M%S)"
    echo "💾 备份现有配置到 $BACKUP_DIR ..."
    mkdir -p "$BACKUP_DIR"
    [ -f "$CLAUDE_DIR/CLAUDE.md" ] && cp "$CLAUDE_DIR/CLAUDE.md" "$BACKUP_DIR/"
    for sub in rules skills agents hooks core prompts; do
        [ -d "$CLAUDE_DIR/$sub" ] && cp -r "$CLAUDE_DIR/$sub" "$BACKUP_DIR/" 2>/dev/null || true
    done
fi

# Step 3: L1 复制各部分到 ~/.claude/
copy_dir() {
    local name="$1" src="$SOLAR_DIR/$1"
    if [ -d "$src" ]; then
        echo "📋 [L1] 复制 $name ..."
        mkdir -p "$CLAUDE_DIR/$name"
        cp -r "$src/"* "$CLAUDE_DIR/$name/" 2>/dev/null || true
        return 0
    fi
    echo "⚠️  $name 在仓库里不存在,跳过"
    return 1
}

echo "📋 [L1] 复制 CLAUDE.md ..."
cp "$SOLAR_DIR/CLAUDE.md" "$CLAUDE_DIR/CLAUDE.md"

copy_dir "rules"
copy_dir "skills"
copy_dir "agents"
copy_dir "hooks"
copy_dir "core"

if [ -d "$SOLAR_DIR/.claude/prompts" ]; then
    echo "📋 [L1] 复制 prompts ..."
    mkdir -p "$CLAUDE_DIR/prompts"
    cp -r "$SOLAR_DIR/.claude/prompts/"* "$CLAUDE_DIR/prompts/" 2>/dev/null || true
fi

# 给 hooks 加可执行权限
chmod +x "$CLAUDE_DIR/hooks/"*.sh 2>/dev/null || true

# Step 4: 创建 .solar/
echo ""
echo "📂 [L2] 创建 $SOLAR_HOME ..."
mkdir -p "$SOLAR_HOME" "$SOLAR_HOME/bin"

# 初始化 db
if [ ! -f "$SOLAR_HOME/solar.db" ]; then
    if [ -f "$SOLAR_DIR/core/schema.sql" ]; then
        echo "🗄️  [L2] 初始化数据库..."
        sqlite3 "$SOLAR_HOME/solar.db" < "$SOLAR_DIR/core/schema.sql"
    else
        echo "ℹ️  无 schema.sql, 跳过 db 初始化 (Solar 启动时会自建)"
    fi
fi

# Step 5: L2 同步 harness/
if [ -d "$SOLAR_DIR/harness" ]; then
    echo "🔧 [L2] 同步 Solar Harness: $SOLAR_DIR/harness → $SOLAR_HOME/harness ..."
    SOLAR_DIR="$SOLAR_DIR" SOLAR_HOME="$SOLAR_HOME" "$SOLAR_DIR/scripts/sync-harness-runtime.sh"
else
    echo "⚠️  仓库无 harness/, 跳过 L2 协调器安装"
fi

# Step 6: L2 复制 mempalace/
if [ -d "$SOLAR_DIR/mempalace" ]; then
    echo "🧠 [L2] 复制 MemPalace (语义记忆 L3) ..."
    mkdir -p "$SOLAR_HOME/mempalace"
    rsync -a "$SOLAR_DIR/mempalace/" "$SOLAR_HOME/mempalace/"
    chmod +x "$SOLAR_HOME/mempalace/"*.py "$SOLAR_HOME/mempalace/"*.sh 2>/dev/null || true
fi

# Step 7: L2 复制 codex-bridge/
if [ -d "$SOLAR_DIR/codex-bridge" ]; then
    echo "🤝 [L2] 复制 Codex 协同协议 ..."
    mkdir -p "$SOLAR_HOME/codex-bridge"
    rsync -a "$SOLAR_DIR/codex-bridge/" "$SOLAR_HOME/codex-bridge/"
    mkdir -p "$SOLAR_HOME/codex-bridge/from-codex" "$SOLAR_HOME/codex-bridge/to-codex"
fi

# Step 8: 真实 verify 自检
echo ""
echo "🔍 安装自检"
echo "==========="
PASS=0
FAIL=0

check() {
    local name="$1" cmd="$2"
    if eval "$cmd" >/dev/null 2>&1; then
        echo "  ✅ $name"
        PASS=$((PASS+1))
    else
        echo "  ❌ $name"
        FAIL=$((FAIL+1))
    fi
}

# L1
check "[L1] CLAUDE.md 已就位"          "test -f $CLAUDE_DIR/CLAUDE.md"
check "[L1] CLAUDE.md 是 v2.0 完整版"  "[ \$(wc -l < $CLAUDE_DIR/CLAUDE.md) -gt 200 ]"
check "[L1] ~/.claude/rules/ 就位"     "test -d $CLAUDE_DIR/rules && [ \$(ls $CLAUDE_DIR/rules 2>/dev/null | wc -l) -gt 5 ]"
check "[L1] ~/.claude/agents/ 就位"    "test -d $CLAUDE_DIR/agents && [ \$(ls $CLAUDE_DIR/agents 2>/dev/null | wc -l) -gt 10 ]"
check "[L1] ~/.claude/hooks/ 就位"     "test -d $CLAUDE_DIR/hooks && [ \$(ls $CLAUDE_DIR/hooks 2>/dev/null | wc -l) -gt 10 ]"
check "[L1] safe-impl prompt 就位"      "test -f $CLAUDE_DIR/prompts/safe-impl.md"
check "[L1] ~/.solar/ 目录已建"         "test -d $SOLAR_HOME"

# L2
check "[L2] harness/coordinator.sh"         "test -f $SOLAR_HOME/harness/coordinator.sh"
check "[L2] harness/chain-watcher.sh"       "test -f $SOLAR_HOME/harness/chain-watcher.sh"
check "[L2] harness/personas/ 5 化身"        "[ \$(ls $SOLAR_HOME/harness/personas/ 2>/dev/null | wc -l) -ge 5 ]"
check "[L2] solar-harness CLI 软链"          "test -L $SOLAR_HOME/bin/solar-harness"
check "[L2] harness runtime source 标记"      "grep -q \"source=$SOLAR_DIR/harness\" $SOLAR_HOME/harness/.runtime-source"
check "[L2] mempalace_mcp_server.py"        "test -f $SOLAR_HOME/mempalace/mempalace_mcp_server.py"
check "[L2] codex-bridge/CODEX-PROTOCOL.md" "test -f $SOLAR_HOME/codex-bridge/CODEX-PROTOCOL.md"

echo ""
TOTAL=14
if [ "$FAIL" -eq 0 ]; then
    echo "✅ Solar L1 + L2 安装完成 ($PASS/$TOTAL 通过)"
    echo ""
    echo "📝 下一步:"
    echo "  1. (可选) 配置 API keys: cp $SOLAR_DIR/.env.template $SOLAR_DIR/.env"
    echo "     编辑填入需要的 API key；安装本身不依赖 API key"
    echo ""
    echo "  2. (可选) Python 依赖 (MemPalace 需要):"
    echo "     python3.11 -m pip install --user chromadb sentence-transformers langdetect mcp pyyaml"
    echo ""
    echo "  3. (可选) Skills 增强:"
    echo "     让 AI agent 按 $SOLAR_DIR/SKILLS-INSTALL.md 安装第三方 skill packs；必须先征得用户同意"
    echo ""
    echo "  4. 启动 Claude Code, 输入 'solar' 看启动宣告"
    echo ""
    echo "  5. (可选 L2) 启动 Solar Harness 协调器:"
    echo "     $SOLAR_HOME/bin/solar-harness"
    echo ""
    echo "📚 完整文档: https://github.com/suraj-subrahmanyan/opensolar"
    echo "📖 用户指南: $SOLAR_DIR/USER-GUIDE.md"
    echo "🤖 AI 安装剧本: $SOLAR_DIR/INSTALL-AGENT.md"
    echo "🔧 Skills 指南: $SOLAR_DIR/SKILLS-INSTALL.md"
    exit 0
else
    echo "❌ 安装自检失败 ($FAIL/$TOTAL 项, $PASS/$TOTAL 通过)"
    echo ""
    echo "🆘 故障排查:"
    echo "  - 检查仓库完整性: ls $SOLAR_DIR/{CLAUDE.md,rules,agents,hooks,harness,mempalace,codex-bridge}"
    echo "  - 检查权限: ls -la $CLAUDE_DIR/ $SOLAR_HOME/"
    echo "  - 提交 issue: https://github.com/suraj-subrahmanyan/opensolar/issues"
    exit 1
fi
