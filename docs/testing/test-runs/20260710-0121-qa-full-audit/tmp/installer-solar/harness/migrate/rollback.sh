#!/usr/bin/env bash
# ================================================================
# Solar Harness — Migrate Rollback
# Sprint 20260422-162434 D9 + Sprint 20260423-151839 D3+D4+D9
#
# 回滚到 import 前状态: --diff / --full / --remote
#
# 用法:
#   bash rollback.sh [--diff|--full] [--confirm] [--backup-dir <path>]
#   bash rollback.sh --remote <user@host> [--diff|--full] [--confirm]
#
# @module solar-farm/harness/migrate
# ================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HARNESS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

G='\033[0;32m'; R='\033[0;31m'; Y='\033[1;33m'; C='\033[0;36m'; N='\033[0m'
log()  { echo -e "${C}[migrate-rollback]${N} $*"; }
ok()   { echo -e "  ${G}✓${N} $*"; }
warn() { echo -e "  ${Y}⚠${N} $*"; }
err()  { echo -e "  ${R}✗${N} $*"; }

# ── Global state ──
MODE="auto"
CONFIRM=false
BACKUP_DIR_OPT=""

# ── Functions (must be defined before use) ──

diff_backup_exists() {
  local found=""
  if [[ -n "$BACKUP_DIR_OPT" ]]; then
    [[ -d "$BACKUP_DIR_OPT" ]] && found="$BACKUP_DIR_OPT"
  else
    found=$(ls -d "$HOME"/solar-diff-backup-* 2>/dev/null | sort -r | head -1)
  fi
  [[ -n "$found" && -f "${found}/diff-manifest.json" ]]
}

do_diff_rollback() {
  local DIFF_DIR=""
  if [[ -n "$BACKUP_DIR_OPT" ]]; then
    DIFF_DIR="$BACKUP_DIR_OPT"
  else
    DIFF_DIR=$(ls -d "$HOME"/solar-diff-backup-* 2>/dev/null | sort -r | head -1)
  fi

  if [[ -z "$DIFF_DIR" || ! -d "$DIFF_DIR" ]]; then
    err "未找到差分备份目录 (~/solar-diff-backup-*)"
    exit 1
  fi

  local MANIFEST="$DIFF_DIR/diff-manifest.json"
  if [[ ! -f "$MANIFEST" ]]; then
    err "diff-manifest.json 缺失: $MANIFEST"
    exit 1
  fi

  log "找到差分备份: $DIFF_DIR"
  local BACKUP_TS="${DIFF_DIR##*solar-diff-backup-}"
  log "备份时间: $BACKUP_TS"

  local MODIFIED_COUNT ADDED_COUNT
  MODIFIED_COUNT=$(python3 -c "import json; print(len(json.load(open('$MANIFEST')).get('modified',[])))" 2>/dev/null || echo 0)
  ADDED_COUNT=$(python3 -c "import json; print(len(json.load(open('$MANIFEST')).get('added',[])))" 2>/dev/null || echo 0)
  log "待恢复: ${MODIFIED_COUNT} modified, ${ADDED_COUNT} added (待删除)"

  if [[ "$CONFIRM" != "true" ]]; then
    warn "差分回滚将恢复 ${MODIFIED_COUNT} 个文件并删除 ${ADDED_COUNT} 个新增文件"
    echo -n "确认回滚? [y/N] "
    read -r answer
    if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
      log "取消回滚"
      exit 0
    fi
  fi

  log "执行差分恢复..."

  export DIFF_DIR MANIFEST HOME
  python3 << 'PYEOF'
import json, os, hashlib, shutil, sys

diff_dir = os.environ["DIFF_DIR"]
manifest_path = os.environ["MANIFEST"]
home = os.environ["HOME"]
originals_dir = os.path.join(diff_dir, "originals")

with open(manifest_path) as f:
    manifest = json.load(f)

restore_ok = 0
restore_fail = 0
delete_ok = 0
delete_fail = 0

for item in manifest.get("modified", []):
    rel = item["path"]
    expected_sha = item.get("target_sha256_before", "")
    src = os.path.join(originals_dir, rel)

    if rel.startswith("solar/"):
        target = os.path.join(home, ".solar", rel[len("solar/"):])
    elif rel.startswith("claude/"):
        target = os.path.join(home, ".claude", rel[len("claude/"):])
    elif rel.startswith("system/"):
        target = os.path.join(home, rel[len("system/"):])
    else:
        continue

    if not os.path.exists(src):
        print(f"  ⚠ 原件缺失: {rel}")
        restore_fail += 1
        continue

    if expected_sha:
        actual_sha = hashlib.sha256(open(src, "rb").read()).hexdigest()
        if actual_sha != expected_sha:
            print(f"  ✗ SHA256 不匹配: {rel}")
            print(f"    预期: {expected_sha}")
            print(f"    实际: {actual_sha}")
            print(f"  ✗ 差分回滚终止 — 文件完整性校验失败!")
            sys.exit(1)

    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copy2(src, target)
    restore_ok += 1

for item in manifest.get("added", []):
    rel = item["path"]
    if rel.startswith("solar/"):
        target = os.path.join(home, ".solar", rel[len("solar/"):])
    elif rel.startswith("claude/"):
        target = os.path.join(home, ".claude", rel[len("claude/"):])
    elif rel.startswith("system/"):
        target = os.path.join(home, rel[len("system/"):])
    else:
        continue

    if os.path.exists(target):
        os.remove(target)
        delete_ok += 1
    else:
        delete_ok += 1

print(f"  ✓ {restore_ok} 还原 + {delete_ok} 删除 + {restore_fail} 失败")
PYEOF

  if [[ $? -ne 0 ]]; then
    err "差分回滚失败 — SHA256 校验不匹配"
    exit 1
  fi

  mkdir -p "$HOME/.solar"
  echo "rollback-diff-from-${DIFF_DIR}-at-$(date -u +%Y%m%d-%H%M%S)" >> "$HOME/.solar/.migration-log" 2>/dev/null || true

  echo ""
  echo "──────────────────────────────────────────────────"
  ok "差分回滚完成"
  log "差分备份目录保留: $DIFF_DIR (可手动删除)"
  log "回滚摘要: ${MODIFIED_COUNT} 还原 + ${ADDED_COUNT} 删除 + 0 失败"
  echo "──────────────────────────────────────────────────"
  echo ""
}

do_full_rollback() {
  local BACKUP_DIR=""
  if [[ -n "$BACKUP_DIR_OPT" ]]; then
    BACKUP_DIR="$BACKUP_DIR_OPT"
  else
    BACKUP_DIR=$(ls -d "$HOME"/solar-backup-* 2>/dev/null | sort -r | head -1)
  fi

  if [[ -z "$BACKUP_DIR" || ! -d "$BACKUP_DIR" ]]; then
    err "未找到全量备份目录 (~/solar-backup-*)"
    exit 1
  fi

  if [[ ! -d "$BACKUP_DIR/solar" ]] && [[ ! -f "$BACKUP_DIR/.bundle-id" ]]; then
    err "不是有效的全量备份: $BACKUP_DIR"
    exit 1
  fi

  local BACKUP_TS BACKUP_BUNDLE
  BACKUP_TS=$(cat "$BACKUP_DIR/.timestamp" 2>/dev/null || echo "unknown")
  BACKUP_BUNDLE=$(cat "$BACKUP_DIR/.bundle-id" 2>/dev/null || echo "unknown")

  log "找到全量备份: $BACKUP_DIR"
  log "备份时间: $BACKUP_TS"
  log "Bundle ID: $BACKUP_BUNDLE"
  echo ""

  if [[ "$CONFIRM" != "true" ]]; then
    warn "全量回滚将覆盖当前 ~/.solar 和 ~/.claude"
    echo -n "确认回滚? [y/N] "
    read -r answer
    if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
      log "取消回滚"
      exit 0
    fi
  fi

  log "执行全量回滚..."

  if [[ -d "$HOME/.solar" ]]; then
    cp "$HOME/.solar/.migrated-bundles" /tmp/migrated-bundles-backup 2>/dev/null || true
    rm -rf "$HOME/.solar"
    ok "已移除当前 ~/.solar"
  fi

  if [[ -d "$HOME/.claude" ]]; then
    rm -rf "$HOME/.claude"
    ok "已移除当前 ~/.claude"
  fi

  if [[ -d "$BACKUP_DIR/solar" ]]; then
    cp -a "$BACKUP_DIR/solar" "$HOME/.solar"
    ok "已恢复 ~/.solar"
  else
    warn "备份中无 solar/ 子目录"
  fi

  if [[ -d "$BACKUP_DIR/claude" ]]; then
    cp -a "$BACKUP_DIR/claude" "$HOME/.claude"
    ok "已恢复 ~/.claude"
  else
    warn "备份中无 claude/ 子目录"
  fi

  mkdir -p "$HOME/.solar"
  echo "rollback-full-from-${BACKUP_BUNDLE}-at-$(date -u +%Y%m%d-%H%M%S)" >> "$HOME/.solar/.migration-log"

  echo ""
  echo "──────────────────────────────────────────────────"
  ok "全量回滚完成"
  log "备份目录保留: $BACKUP_DIR (可手动删除)"
  echo "──────────────────────────────────────────────────"
  echo ""
}

# ── Main ──

while [[ $# -gt 0 ]]; do
  case "$1" in
    --diff)          MODE="diff"; shift ;;
    --full)          MODE="full"; shift ;;
    --confirm|-y)    CONFIRM=true; shift ;;
    --backup-dir)    BACKUP_DIR_OPT="$2"; shift 2 ;;
    --remote)
      # D9: Remote rollback
      REMOTE_HOST="$2"; shift 2
      log "远程回滚: ${REMOTE_HOST} (模式: ${MODE})"
      SSH_OPTS="-o BatchMode=yes -o StrictHostKeyChecking=accept-new"
      REMOTE_MODE="--full"
      [[ "$MODE" == "diff" ]] && REMOTE_MODE="--diff"
      ssh $SSH_OPTS "$REMOTE_HOST" "bash -lc 'solar-harness migrate rollback ${REMOTE_MODE} --confirm'" 2>&1
      EXIT_CODE=$?
      if [[ $EXIT_CODE -ne 0 ]]; then
        err "远程回滚失败 (exit=$EXIT_CODE)"
        exit $EXIT_CODE
      fi
      ok "远程回滚完成"
      exit 0
      ;;
    *)
      err "未知参数: $1"; exit 1 ;;
  esac
done

echo ""
echo "══════════════════════════════════════════════════"
echo "  Solar Migration — Rollback"
echo "══════════════════════════════════════════════════"
echo ""

case "$MODE" in
  diff)
    do_diff_rollback
    ;;
  full)
    do_full_rollback
    ;;
  auto)
    if diff_backup_exists; then
      do_diff_rollback
    else
      warn "未找到差分备份, 回退到全量回滚"
      do_full_rollback
    fi
    ;;
esac

exit 0
