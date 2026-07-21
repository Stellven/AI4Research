#!/usr/bin/env bash
# ================================================================
# Solar Harness — SSH Bootstrap
# Sprint 20260423-151839 D10
#
# 首次远程种子: 把 solar-harness 种到目标机
#
# 用法:
#   bash ssh-bootstrap.sh <user@host>
#
# @module solar-farm/harness/migrate
# ================================================================
set -euo pipefail

G='\033[0;32m'; R='\033[0;31m'; Y='\033[1;33m'; C='\033[0;36m'; N='\033[0m'
log()  { echo -e "${C}[ssh-bootstrap]${N} $*"; }
ok()   { echo -e "  ${G}✓${N} $*"; }
warn() { echo -e "  ${Y}⚠${N} $*"; }
err()  { echo -e "  ${R}✗${N} $*"; }

TARGET="${1:-}"
if [[ -z "$TARGET" ]]; then
  err "用法: bash ssh-bootstrap.sh <user@host>"
  exit 1
fi

SSH_OPTS="-o BatchMode=yes -o StrictHostKeyChecking=accept-new"

echo ""
echo "══════════════════════════════════════════════════"
echo "  Solar SSH Bootstrap — 首次远程种子"
echo "══════════════════════════════════════════════════"
echo ""
log "目标: $TARGET"

# ── 1. 检查 SSH 连通性 ──
log "检查 SSH 连通性..."
if ! ssh $SSH_OPTS "$TARGET" "echo ok" &>/dev/null; then
  err "SSH 连接失败: $TARGET"
  err "请确认: (1) 目标机可达 (2) SSH key 已配置 (ssh-copy-id $TARGET)"
  exit 1
fi
ok "SSH 连通"

# ── 2. 检查目标是否已有 ~/.solar ──
HAS_SOLAR=$(ssh $SSH_OPTS "$TARGET" "test -d ~/.solar && echo yes || echo no" 2>/dev/null)
if [[ "$HAS_SOLAR" == "yes" ]]; then
  warn "目标机已有 ~/.solar — 跳过种子 (如需覆盖, 先 ssh $TARGET 'rm -rf ~/.solar')"
fi

# ── 3. 种子: scp ~/.solar ──
log "种子 ~/.solar → ${TARGET}:~/"
scp $SSH_OPTS -r "$HOME/.solar" "${TARGET}:~/" 2>/dev/null
if [[ $? -ne 0 ]]; then
  err "scp ~/.solar 失败"
  exit 1
fi
ok "~/.solar 已传输"

# ── 4. 种子: 最小 Claude 配置 ──
log "种子最小 Claude 配置..."
ssh $SSH_OPTS "$TARGET" "mkdir -p ~/.claude" 2>/dev/null
if [[ -f "$HOME/.claude/CLAUDE.md" ]]; then
  scp $SSH_OPTS "$HOME/.claude/CLAUDE.md" "${TARGET}:~/.claude/CLAUDE.md" 2>/dev/null
  ok "CLAUDE.md 已传输"
else
  warn "本机无 CLAUDE.md, 跳过"
fi

# ── 5. 验证 solar-harness ──
log "验证远程 solar-harness..."
VERSION=$(ssh $SSH_OPTS "$TARGET" "bash -lc 'solar-harness --version 2>/dev/null || bash ~/.solar/bin/solar-harness --version 2>/dev/null'" 2>/dev/null || echo "")
if [[ -n "$VERSION" ]]; then
  ok "远程 solar-harness 版本: $VERSION"
else
  warn "远程 solar-harness 未能运行"
  log "可能需要手动安装依赖:"
  log "  ssh $TARGET 'bash -lc \"brew install bash tmux jq python3\"'"
  log "  ssh $TARGET 'echo \"export PATH=\\\$HOME/.solar/bin:\\\$PATH\" >> ~/.zshrc'"
fi

echo ""
echo "──────────────────────────────────────────────────"
ok "Bootstrap 完成: $TARGET"
if [[ -z "$VERSION" ]]; then
  warn "远程依赖需手动安装 (brew install bash tmux jq python3)"
fi
echo "──────────────────────────────────────────────────"
echo ""

exit 0
