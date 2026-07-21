#!/usr/bin/env bash
# ================================================================
# Solar Harness — Migrate Import
# Sprint 20260422-162434 D3 + Sprint 20260423-151839 D2+D5+D7
#
# 从 bundle 恢复 Solar + Claude + 系统配置到目标机
# 支持: diff 备份, ssh:// 远程拉取, 双备份模式
#
# 用法:
#   bash import.sh <bundle> [--password <pw>] [--dry-run] [--install-deps]
#                    [--skip-diff-backup] [--skip-full-backup] [--keep-local]
#
# @module solar-farm/harness/migrate
# ================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HARNESS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MIGRATE_DIR="$HARNESS_DIR/migrate"
LOG_DIR="$HARNESS_DIR/logs"
mkdir -p "$LOG_DIR"

G='\033[0;32m'; R='\033[0;31m'; Y='\033[1;33m'; C='\033[0;36m'; N='\033[0m'
log()  { echo -e "${C}[migrate-import]${N} $*"; }
ok()   { echo -e "  ${G}✓${N} $*"; }
warn() { echo -e "  ${Y}⚠${N} $*"; }
err()  { echo -e "  ${R}✗${N} $*"; }

TS=$(date -u +"%Y%m%d-%H%M%S")
LOG_FILE="$LOG_DIR/migrate-import-${TS}.log"
log "日志: $LOG_FILE"
exec > >(tee -a "$LOG_FILE") 2>&1

# ── 参数解析 ──
BUNDLE=""
PASSWORD=""
DRY_RUN=false
INSTALL_DEPS=false
SKIP_DIFF_BACKUP=false
SKIP_FULL_BACKUP=false
KEEP_LOCAL=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --password)         PASSWORD="$2"; shift 2 ;;
    --dry-run)          DRY_RUN=true; shift ;;
    --install-deps)     INSTALL_DEPS=true; shift ;;
    --skip-diff-backup) SKIP_DIFF_BACKUP=true; shift ;;
    --skip-full-backup) SKIP_FULL_BACKUP=true; shift ;;
    --keep-local)       KEEP_LOCAL=true; shift ;;
    -*)
      err "未知参数: $1"; exit 1 ;;
    *)
      if [[ -z "$BUNDLE" ]]; then
        BUNDLE="$1"; shift
      else
        err "多余参数: $1"; exit 1
      fi
  esac
done

# ── D7: ssh:// 前缀支持 ──
REMOTE_BUNDLE=false
LOCAL_BUNDLE_COPY=""
if [[ -n "$BUNDLE" && "$BUNDLE" == ssh://* ]]; then
  REMOTE_BUNDLE=true
  # Parse ssh://user@host/path
  SSH_URL="${BUNDLE#ssh://}"
  SSH_HOST="${SSH_URL%%/*}"
  SSH_PATH="/${SSH_URL#*/}"
  LOCAL_BUNDLE_COPY="/tmp/solar-import-${TS}.tar"

  log "检测到 SSH 远程 bundle: ${SSH_HOST}:${SSH_PATH}"

  # Verify SSH connectivity
  if ! ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 "${SSH_HOST}" "test -f '${SSH_PATH}'" 2>/dev/null; then
    err "远程文件不存在或 SSH 连接失败: ${SSH_HOST}:${SSH_PATH}"
    exit 1
  fi

  # Transfer: prefer rsync, fallback scp
  log "拉取远程 bundle..."
  if command -v rsync &>/dev/null; then
    rsync --partial --append --progress "${SSH_HOST}:${SSH_PATH}" "$LOCAL_BUNDLE_COPY" 2>&1 || \
      scp -o BatchMode=yes "${SSH_HOST}:${SSH_PATH}" "$LOCAL_BUNDLE_COPY" 2>/dev/null
  else
    scp -o BatchMode=yes "${SSH_HOST}:${SSH_PATH}" "$LOCAL_BUNDLE_COPY" 2>/dev/null
  fi

  if [[ ! -f "$LOCAL_BUNDLE_COPY" ]]; then
    err "远程 bundle 拉取失败"
    exit 1
  fi
  ok "远程 bundle 拉取完成: $LOCAL_BUNDLE_COPY"
  BUNDLE="$LOCAL_BUNDLE_COPY"
fi

if [[ -z "$BUNDLE" ]]; then
  err "用法: import.sh <bundle.tar|ssh://host/path> [--password <pw>] [--dry-run] [--install-deps]"
  err "       [--skip-diff-backup] [--skip-full-backup] [--keep-local]"
  exit 1
fi

if [[ ! -f "$BUNDLE" ]]; then
  err "Bundle 文件不存在: $BUNDLE"
  exit 1
fi

# ── 工具函数 ──
sha256_file() {
  shasum -a 256 "$1" 2>/dev/null | cut -d' ' -f1 || sha256sum "$1" | cut -d' ' -f1
}

TEXT_EXTENSIONS="md sh json py ts yml yaml conf plist zshrc bashrc txt rc cfg toml xml csv"

is_text_file() {
  local fname="$1"
  local ext="${fname##*.}"
  if [[ "$fname" == .* && "$ext" == "$fname" ]]; then
    return 0
  fi
  for te in $TEXT_EXTENSIONS; do
    [[ "$ext" == "$te" ]] && return 0
  done
  return 1
}

# ── 临时目录 ──
if [[ "$DRY_RUN" == "true" ]]; then
  WORK_DIR="/tmp/migrate-dryrun-${TS}"
else
  WORK_DIR="/tmp/solar-import-$$"
fi
mkdir -p "$WORK_DIR"

cleanup() {
  if [[ "$DRY_RUN" == "true" ]]; then
    log "dry-run: 保留临时目录 $WORK_DIR 供检查"
  else
    rm -rf "$WORK_DIR"
  fi
  # D7: clean up remote bundle copy unless --keep-local
  if [[ "$REMOTE_BUNDLE" == "true" && "$KEEP_LOCAL" == "false" && -n "$LOCAL_BUNDLE_COPY" ]]; then
    rm -f "$LOCAL_BUNDLE_COPY" 2>/dev/null || true
  fi
  unset PASSWORD 2>/dev/null || true
}
trap cleanup EXIT

# ── 1. 验证外层 SHA256 ──
log "验证 bundle 完整性..."
SHA_FILE="${BUNDLE}.sha256"
if [[ -f "$SHA_FILE" ]]; then
  EXPECTED=$(cat "$SHA_FILE" | cut -d' ' -f1)
  ACTUAL=$(sha256_file "$BUNDLE")
  if [[ "$EXPECTED" != "$ACTUAL" ]]; then
    err "SHA256 不匹配! 预期=$EXPECTED 实际=$ACTUAL"
    exit 1
  fi
  ok "SHA256 校验通过"
else
  warn "无 .sha256 伴生文件, 跳过校验"
fi

# ── 2. 解包到临时目录 ──
log "解包 bundle..."
tar xf "$BUNDLE" -C "$WORK_DIR" 2>/dev/null
BUNDLE_DIR=$(find "$WORK_DIR" -maxdepth 1 -type d -name 'solar-bundle-*' | head -1)
if [[ -z "$BUNDLE_DIR" ]]; then
  err "Bundle 内未找到 solar-bundle-* 目录"
  exit 1
fi
ok "解包到 $BUNDLE_DIR"

# ── 3. 读 bundle-meta.json ──
META="$BUNDLE_DIR/bundle-meta.json"
if [[ ! -f "$META" ]]; then
  err "bundle-meta.json 缺失"
  exit 1
fi

SRC_HOME=$(python3 -c "import json; print(json.load(open('$META'))['source_home'])" 2>/dev/null)
SRC_HOSTNAME=$(python3 -c "import json; print(json.load(open('$META'))['source_hostname'])" 2>/dev/null)
BUNDLE_ID=$(python3 -c "import json; print(json.load(open('$META'))['bundle_id'])" 2>/dev/null)
HAS_SECRETS=$(python3 -c "import json; print(json.load(open('$META')).get('has_secrets',False))" 2>/dev/null)
SECRETS_ENCRYPTED=$(python3 -c "import json; print(json.load(open('$META')).get('secrets_encrypted',False))" 2>/dev/null)
SRC_ARCH=$(python3 -c "import json; print(json.load(open('$META')).get('source_arch','unknown'))" 2>/dev/null)

ok "源机: ${SRC_HOSTNAME} (${SRC_HOME})"
ok "Bundle ID: ${BUNDLE_ID}"

# ── 4. 重复 import 检测 ──
IMPORTED_MARKER="$HOME/.solar/.migrated-bundles"
if [[ -f "$IMPORTED_MARKER" ]] && grep -q "$BUNDLE_ID" "$IMPORTED_MARKER" 2>/dev/null; then
  err "Bundle ${BUNDLE_ID} 已导入过, 重复 import 需先 rollback"
  exit 1
fi

# ── 5. 路径差异检测 ──
DST_HOME="$HOME"
PATH_REPLACE=false
SRC_USER=""
DST_USER=""

if [[ "$SRC_HOME" != "$DST_HOME" ]]; then
  PATH_REPLACE=true
  SRC_USER=$(basename "$SRC_HOME")
  DST_USER=$(basename "$DST_HOME")
  log "路径替换: ${SRC_HOME} → ${DST_HOME}"
  log "用户替换: ${SRC_USER} → ${DST_USER}"
fi

DST_ARCH=$(arch 2>/dev/null || uname -m)
if [[ "$SRC_ARCH" != "$DST_ARCH" ]]; then
  warn "架构差异: 源=${SRC_ARCH}, 目标=${DST_ARCH} — 部分 brew 依赖需重装"
fi

# ── 路径替换函数 ──
replace_paths() {
  local src_file="$1"
  local dst_file="$2"

  if is_text_file "$(basename "$src_file")"; then
    if [[ "$PATH_REPLACE" == "true" ]]; then
      sed "s|${SRC_HOME}|${DST_HOME}|g" "$src_file" > "$dst_file"
    else
      cp "$src_file" "$dst_file"
    fi
  else
    cp "$src_file" "$dst_file"
  fi
}

# ── 6. 备份目标机 (full backup) ──
BACKUP_DIR="$HOME/solar-backup-${TS}"
DIFF_BACKUP_DIR=""
if [[ "$DRY_RUN" == "false" ]]; then
  # D5: Full backup (default on, --skip-full-backup to skip)
  if [[ "$SKIP_FULL_BACKUP" == "false" ]]; then
    log "全量备份当前配置到 $BACKUP_DIR ..."
    mkdir -p "$BACKUP_DIR"
    [[ -d "$HOME/.solar" ]] && cp -a "$HOME/.solar" "$BACKUP_DIR/solar" 2>/dev/null && ok "备份 ~/.solar"
    [[ -d "$HOME/.claude" ]] && cp -a "$HOME/.claude" "$BACKUP_DIR/claude" 2>/dev/null && ok "备份 ~/.claude"
    echo "$BUNDLE_ID" > "$BACKUP_DIR/.bundle-id"
    echo "$TS" > "$BACKUP_DIR/.timestamp"
    FULL_SIZE=$(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1)
    log "全量备份大小: $FULL_SIZE"
  else
    log "跳过全量备份 (--skip-full-backup)"
  fi

  # D2+D5: Diff scan + diff backup (default on, --skip-diff-backup to skip)
  if [[ "$SKIP_DIFF_BACKUP" == "false" ]]; then
    DIFF_BACKUP_DIR="$HOME/solar-diff-backup-${TS}"
    mkdir -p "$DIFF_BACKUP_DIR"

    log "执行差分扫描..."
    bash "$MIGRATE_DIR/diff-scan.sh" "$BUNDLE_DIR" "$DST_HOME" "$DIFF_BACKUP_DIR" 2>&1

    DIFF_MANIFEST="$DIFF_BACKUP_DIR/diff-manifest.json"
    if [[ -f "$DIFF_MANIFEST" ]]; then
      # Backup originals of modified files
      ORIGINALS_DIR="$DIFF_BACKUP_DIR/originals"
      mkdir -p "$ORIGINALS_DIR"

      MODIFIED_COUNT=$(python3 -c "import json; print(len(json.load(open('$DIFF_MANIFEST')).get('modified',[])))" 2>/dev/null || echo 0)
      ADDED_COUNT=$(python3 -c "import json; print(len(json.load(open('$DIFF_MANIFEST')).get('added',[])))" 2>/dev/null || echo 0)

      if [[ "$MODIFIED_COUNT" -gt 0 ]]; then
        log "备份 $MODIFIED_COUNT 个 modified 原件..."
        python3 << PYEOF
import json, os, shutil

manifest_path = "$DIFF_MANIFEST"
originals_dir = "$ORIGINALS_DIR"
target_home = "$DST_HOME"

with open(manifest_path) as f:
    manifest = json.load(f)

for item in manifest.get("modified", []):
    rel = item["path"]
    if rel.startswith("solar/"):
        src = os.path.join(target_home, ".solar", rel[len("solar/"):])
    elif rel.startswith("claude/"):
        src = os.path.join(target_home, ".claude", rel[len("claude/"):])
    elif rel.startswith("system/"):
        src = os.path.join(target_home, rel[len("system/"):])
    else:
        continue

    if os.path.exists(src):
        dst = os.path.join(originals_dir, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        print(f"  cp -p {src} → {dst}")
PYEOF
      fi

      # Copy manifest into backup dir
      DIFF_SIZE=$(du -sh "$DIFF_BACKUP_DIR" 2>/dev/null | cut -f1)
      log "差分备份: ${MODIFIED_COUNT} modified, ${ADDED_COUNT} added (untouched 不备份)"
      log "差分备份路径: $DIFF_BACKUP_DIR (大小: $DIFF_SIZE)"

      if [[ "$SKIP_FULL_BACKUP" == "false" ]]; then
        log "双备份完成: full=$BACKUP_DIR ($FULL_SIZE) + diff=$DIFF_BACKUP_DIR ($DIFF_SIZE)"
      else
        log "差分备份完成: diff=$DIFF_BACKUP_DIR ($DIFF_SIZE)"
      fi
    else
      warn "diff-manifest.json 未生成, 跳过差分备份"
    fi
  else
    log "跳过差分备份 (--skip-diff-backup)"
  fi
fi

# ── 7. 分阶段展开 ──
TARGET_ROOT="$DST_HOME"
if [[ "$DRY_RUN" == "true" ]]; then
  TARGET_ROOT="$WORK_DIR/target"
  mkdir -p "$TARGET_ROOT"
  log "dry-run: 展开到 $TARGET_ROOT (不写入真实路径)"
fi

# Phase 1: 系统级
log "Phase 1/4: 系统级配置..."
SYSTEM_DIR="$BUNDLE_DIR/system"
if [[ -d "$SYSTEM_DIR" ]]; then
  for rc in .zshrc .zprofile .bashrc .bash_profile .tmux.conf .gitconfig; do
    if [[ -f "$SYSTEM_DIR/$rc" ]]; then
      if [[ "$DRY_RUN" == "false" ]]; then
        replace_paths "$SYSTEM_DIR/$rc" "$TARGET_ROOT/$rc"
        ok "  $rc 已写入"
      else
        replace_paths "$SYSTEM_DIR/$rc" "$TARGET_ROOT/$rc"
        ok "  $rc (dry-run)"
      fi
    fi
  done

  if [[ -f "$SYSTEM_DIR/claude-desktop/claude_desktop_config.json" ]]; then
    local_cd="$TARGET_ROOT/Library/Application Support/Claude"
    mkdir -p "$local_cd"
    replace_paths "$SYSTEM_DIR/claude-desktop/claude_desktop_config.json" "$local_cd/claude_desktop_config.json"
    ok "  Claude Desktop config $( [[ "$DRY_RUN" == "false" ]] && echo '已写入' || echo '(dry-run)' )"
  fi

  if [[ -d "$SYSTEM_DIR/LaunchAgents" ]] && ls "$SYSTEM_DIR/LaunchAgents"/*.plist &>/dev/null; then
    if [[ "$DRY_RUN" == "false" ]]; then
      mkdir -p "$TARGET_ROOT/Library/LaunchAgents"
      for plist in "$SYSTEM_DIR/LaunchAgents"/*.plist; do
        [[ -f "$plist" ]] || continue
        base=$(basename "$plist")
        replace_paths "$plist" "$TARGET_ROOT/Library/LaunchAgents/$base"
        launchctl unload "$TARGET_ROOT/Library/LaunchAgents/$base" 2>/dev/null || true
        launchctl load -w "$TARGET_ROOT/Library/LaunchAgents/$base" 2>/dev/null || true
        ok "  LaunchAgent $base loaded"
      done
    else
      ok "  LaunchAgents (dry-run, skipped)"
    fi
  fi

  if [[ -f "$SYSTEM_DIR/crontab.txt" ]] && [[ -s "$SYSTEM_DIR/crontab.txt" ]]; then
    if [[ "$DRY_RUN" == "false" ]]; then
      crontab "$SYSTEM_DIR/crontab.txt" 2>/dev/null && ok "  crontab 已恢复" || warn "  crontab 恢复失败"
    else
      ok "  crontab (dry-run)"
    fi
  fi
fi

# Phase 2: Solar 本体
log "Phase 2/4: Solar 本体..."
SOLAR_DIR="$BUNDLE_DIR/solar"
if [[ -d "$SOLAR_DIR" ]]; then
  if [[ "$DRY_RUN" == "false" ]]; then
    mkdir -p "$TARGET_ROOT/.solar"
    rsync -a "$SOLAR_DIR/" "$TARGET_ROOT/.solar/" 2>/dev/null
    if [[ "$PATH_REPLACE" == "true" ]]; then
      while IFS= read -r -d '' f; do
        if is_text_file "$(basename "$f")"; then
          sed -i '' "s|${SRC_HOME}|${DST_HOME}|g" "$f" 2>/dev/null || true
        fi
      done < <(find "$TARGET_ROOT/.solar" -type f -print0 2>/dev/null)
    fi
    ok "Solar 本体已展开"
  else
    mkdir -p "$TARGET_ROOT/.solar"
    rsync -a "$SOLAR_DIR/" "$TARGET_ROOT/.solar/" 2>/dev/null
    ok "Solar 本体 (dry-run)"
  fi

  # Auto-apply: ensure new scripts are executable
  for f in "$TARGET_ROOT/.solar/harness/lib/phase-state-machine.sh" \
           "$TARGET_ROOT/.solar/bin/solar-verify" \
           "$TARGET_ROOT/.solar/bin/solar-cache"; do
    [[ -f "$f" ]] && chmod +x "$f" 2>/dev/null && log "  chmod +x $(basename "$f")"
  done
fi

# Phase 3: Claude 配置
log "Phase 3/4: Claude 配置..."
CLAUDE_DIR="$BUNDLE_DIR/claude"
if [[ -d "$CLAUDE_DIR" ]]; then
  if [[ "$DRY_RUN" == "false" ]]; then
    mkdir -p "$TARGET_ROOT/.claude"
    rsync -a "$CLAUDE_DIR/" "$TARGET_ROOT/.claude/" 2>/dev/null
    if [[ "$PATH_REPLACE" == "true" ]]; then
      while IFS= read -r -d '' f; do
        if is_text_file "$(basename "$f")"; then
          sed -i '' "s|${SRC_HOME}|${DST_HOME}|g" "$f" 2>/dev/null || true
        fi
      done < <(find "$TARGET_ROOT/.claude" -type f -print0 2>/dev/null)
    fi
    ok "Claude 配置已展开"
  else
    mkdir -p "$TARGET_ROOT/.claude"
    rsync -a "$CLAUDE_DIR/" "$TARGET_ROOT/.claude/" 2>/dev/null
    ok "Claude 配置 (dry-run)"
  fi
fi

# Phase 4: Secrets
log "Phase 4/4: Secrets..."
SECRETS_ENC="$BUNDLE_DIR/secrets.enc"
if [[ -f "$SECRETS_ENC" ]]; then
  if [[ "$HAS_SECRETS" == "True" && "$SECRETS_ENCRYPTED" == "True" ]]; then
    if [[ -z "$PASSWORD" ]]; then
      log "Bundle 包含加密 secrets, 请输入密码 (不会显示): "
    fi
    SECRETS_TMP="$WORK_DIR/secrets-decrypted"
    mkdir -p "$SECRETS_TMP"
    if [[ -n "$PASSWORD" ]]; then
      printf '%s' "$PASSWORD" | openssl enc -aes-256-cbc -d -in "$SECRETS_ENC" -out "$WORK_DIR/secrets.tar.gz" -pass stdin 2>/dev/null
    else
      openssl enc -aes-256-cbc -d -in "$SECRETS_ENC" -out "$WORK_DIR/secrets.tar.gz" -pass stdin 2>/dev/null
    fi

    if [[ $? -ne 0 ]]; then
      err "Secrets 解密失败 (密码错误?)"
      warn "Secrets 解密失败, 继续不含 secrets 的导入"
    else
      tar xf "$WORK_DIR/secrets.tar.gz" -C "$SECRETS_TMP" 2>/dev/null
      if [[ -d "$SECRETS_TMP/ssh" ]] && [[ "$DRY_RUN" == "false" ]]; then
        mkdir -p "$TARGET_ROOT/.ssh"
        cp -a "$SECRETS_TMP/ssh/"* "$TARGET_ROOT/.ssh/" 2>/dev/null || true
        chmod 0600 "$TARGET_ROOT/.ssh"/id_* "$TARGET_ROOT/.ssh"/*.pem "$TARGET_ROOT/.ssh"/*_rsa 2>/dev/null || true
        chmod 0644 "$TARGET_ROOT/.ssh"/known_hosts "$TARGET_ROOT/.ssh"/authorized_keys "$TARGET_ROOT/.ssh"/config 2>/dev/null || true
        ok "SSH keys 已恢复 (权限 0600)"
      fi
      if [[ -d "$SECRETS_TMP/gnupg" ]] && [[ "$DRY_RUN" == "false" ]]; then
        mkdir -p "$TARGET_ROOT/.gnupg"
        cp -a "$SECRETS_TMP/gnupg/"* "$TARGET_ROOT/.gnupg/" 2>/dev/null || true
        chmod 700 "$TARGET_ROOT/.gnupg" 2>/dev/null || true
        ok "GPG 密钥已恢复"
      fi
      if [[ -d "$SECRETS_TMP/env" ]] && [[ "$DRY_RUN" == "false" ]]; then
        for envfile in "$SECRETS_TMP/env"/*.sh "$SECRETS_TMP/env"/*.env; do
          [[ -f "$envfile" ]] || continue
          base=$(basename "$envfile")
          replace_paths "$envfile" "$TARGET_ROOT/.solar/$base"
          ok "  $base 已恢复"
        done
      fi
      rm -rf "$SECRETS_TMP" "$WORK_DIR/secrets.tar.gz"
    fi
    unset PASSWORD
  fi
else
  if [[ "$HAS_SECRETS" == "True" ]]; then
    warn "Bundle 声明含 secrets 但未找到 secrets.enc"
  else
    log "Bundle 不含 secrets"
  fi
fi

# ── 8. 依赖装回 (可选) ──
if [[ "$INSTALL_DEPS" == "true" && "$DRY_RUN" == "false" ]]; then
  log "安装依赖..."
  FAILED_LOG="$HOME/migrate-deps-failed.log"
  > "$FAILED_LOG"

  DEPS_DIR="$BUNDLE_DIR/deps"
  if [[ -f "$DEPS_DIR/Brewfile" ]] && command -v brew &>/dev/null; then
    cd "$HOME" && brew bundle install --file="$DEPS_DIR/Brewfile" 2>&1 || \
      echo "brew bundle install failed ($(date))" >> "$FAILED_LOG"
    ok "brew bundle install 完成"
  fi

  if [[ -f "$DEPS_DIR/npm-global.txt" ]] && command -v npm &>/dev/null; then
    grep '/' "$DEPS_DIR/npm-global.txt" 2>/dev/null | sed 's/.* //' | while read -r pkg; do
      npm install -g "$pkg" 2>/dev/null || echo "npm install -g $pkg failed" >> "$FAILED_LOG"
    done
    ok "npm 全局包安装完成"
  fi

  if [[ -f "$DEPS_DIR/pipx.txt" ]] && command -v pipx &>/dev/null; then
    grep -v '^#' "$DEPS_DIR/pipx.txt" 2>/dev/null | while read -r pkg; do
      [[ -z "$pkg" ]] && continue
      pipx install "$pkg" 2>/dev/null || echo "pipx install $pkg failed" >> "$FAILED_LOG"
    done
    ok "pipx 工具安装完成"
  fi

  if [[ -s "$FAILED_LOG" ]]; then
    warn "部分依赖安装失败, 详见 $FAILED_LOG"
  else
    rm -f "$FAILED_LOG"
  fi
fi

# ── 9. files_hash 校验 (非 dry-run) ──
if [[ "$DRY_RUN" == "false" ]]; then
  log "校验文件完整性..."
  python3 << PYEOF
import json, hashlib, os, sys

meta_path = "$META"
target_root = "$TARGET_ROOT"

try:
    with open(meta_path) as f:
        meta = json.load(f)
except:
    print("  ⚠ 无法读取 bundle-meta.json")
    sys.exit(0)

files_hash = meta.get("files_hash", {})
if not files_hash:
    print("  ⚠ files_hash 为空, 跳过校验")
    sys.exit(0)

missing = []
mismatch = []
for rel, expected_hash in files_hash.items():
    if rel.startswith("solar/"):
        target = os.path.join(target_root, ".solar", rel[len("solar/"):])
    elif rel.startswith("claude/"):
        target = os.path.join(target_root, ".claude", rel[len("claude/"):])
    elif rel.startswith("system/"):
        target = os.path.join(target_root, rel[len("system/"):])
    elif rel.startswith("deps/"):
        continue
    elif rel == "bundle-meta.json":
        continue
    else:
        continue

    if not os.path.exists(target):
        missing.append(rel)
        continue
    try:
        actual = hashlib.sha256(open(target, 'rb').read()).hexdigest()
        if actual != expected_hash:
            mismatch.append(rel)
    except:
        pass

if missing:
    print(f"  ⚠ {len(missing)} 个文件缺失")
if mismatch:
    print(f"  ✗ {len(mismatch)} 个文件哈希不匹配")
if not missing and not mismatch:
    print(f"  ✓ 全部 {len(files_hash)} 个文件校验通过")
PYEOF
fi

# ── 10. doctor 验证 ──
if [[ "$DRY_RUN" == "false" ]]; then
  log "运行 doctor 验证..."
  if bash "$HARNESS_DIR/doctor.sh" 2>/dev/null; then
    ok "Doctor 检查通过"
  else
    warn "Doctor 检查发现问题 (详见上方输出)"
  fi
fi

# ── 11. 记录导入 ──
if [[ "$DRY_RUN" == "false" ]]; then
  mkdir -p "$TARGET_ROOT/.solar"
  echo "$BUNDLE_ID" >> "$TARGET_ROOT/.solar/.migrated-bundles"
fi

# ── 结果 ──
echo ""
echo "══════════════════════════════════════════════════"
if [[ "$DRY_RUN" == "true" ]]; then
  echo "  Solar Migration — Dry Run 完成"
  echo "  临时目录: $WORK_DIR (供检查)"
else
  echo "  Solar Migration — Import 完成"
  if [[ "$SKIP_FULL_BACKUP" == "false" ]]; then
    echo "  全量备份: $BACKUP_DIR"
  fi
  if [[ -n "$DIFF_BACKUP_DIR" && -d "$DIFF_BACKUP_DIR" ]]; then
    echo "  差分备份: $DIFF_BACKUP_DIR"
  fi
  echo "  回滚命令: solar-harness migrate rollback --diff"
  echo "            solar-harness migrate rollback --full"
fi
echo "══════════════════════════════════════════════════"
echo ""

exit 0
