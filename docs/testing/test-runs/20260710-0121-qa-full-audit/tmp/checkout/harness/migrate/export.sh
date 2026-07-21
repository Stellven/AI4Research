#!/usr/bin/env bash
# ================================================================
# Solar Harness — Migrate Export
# Sprint 20260422-162434 D2
#
# 打包 Solar + Claude + 系统配置到加密 bundle
#
# 用法:
#   bash export.sh [--out <path>] [--include-secrets] [--password <pw>]
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
log()  { echo -e "${C}[migrate-export]${N} $*"; }
ok()   { echo -e "  ${G}✓${N} $*"; }
warn() { echo -e "  ${Y}⚠${N} $*"; }
err()  { echo -e "  ${R}✗${N} $*"; }

TS=$(date -u +"%Y%m%d-%H%M%S")
LOG_FILE="$LOG_DIR/migrate-export-${TS}.log"
log "日志: $LOG_FILE"
exec > >(tee -a "$LOG_FILE") 2>&1

# ── 参数解析 ──
OUT_DIR=""
INCLUDE_SECRETS=false
INCLUDE_TEMPLATES=false
INCLUDE_CACHE=false
PASSWORD=""
PUSH_TARGET=""
CLEANUP_LOCAL=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out)       OUT_DIR="$2"; shift 2 ;;
    --include-secrets) INCLUDE_SECRETS=true; shift ;;
    --include-templates) INCLUDE_TEMPLATES=true; shift ;;
    --include-cache) INCLUDE_CACHE=true; shift ;;
    --password)  PASSWORD="$2"; shift 2 ;;
    --push)      PUSH_TARGET="$2"; shift 2 ;;
    --cleanup-local) CLEANUP_LOCAL=true; shift ;;
    *)           err "未知参数: $1"; exit 1 ;;
  esac
done

# ── 默认输出路径 ──
if [[ -z "$OUT_DIR" ]]; then
  OUT_DIR="$HOME/solar-bundles"
fi
mkdir -p "$OUT_DIR"

HOSTNAME_VAL=$(hostname -s 2>/dev/null || hostname)
BUNDLE_NAME="solar-bundle-${HOSTNAME_VAL}-${TS}"
WORK_DIR="/tmp/solar-export-$$"
BUNDLE_DIR="$WORK_DIR/$BUNDLE_NAME"

mkdir -p "$BUNDLE_DIR/deps"

# ── 清理 ──
cleanup() {
  rm -rf "$WORK_DIR"
  # 清除密码变量
  unset PASSWORD 2>/dev/null || true
}
trap cleanup EXIT

# ── 排除列表 ──
EXCLUDE_FILE="$WORK_DIR/excludes.txt"
cat > "$EXCLUDE_FILE" << 'EXCLUDES'
/tmp/
/Library/Caches/
node_modules/
__pycache__/
*.pyc
.git/
.tmux-*
.coordinator.pid
.watchdog.pid
.coordinator.lock
*.log
EXCLUDES

# ── SHA256 工具 ──
sha256_file() {
  if command -v shasum &>/dev/null; then
    shasum -a 256 "$1" | cut -d' ' -f1
  else
    sha256sum "$1" | cut -d' ' -f1
  fi
}

# ── 1. 收集文件 + 计算 files_hash ──
log "收集文件..."

FILES_HASH="{}"
add_file_hash() {
  local src="$1"
  local rel="${src#$HOME/}"
  if [[ -f "$src" ]]; then
    local h
    h=$(sha256_file "$src")
    FILES_HASH=$(python3 -c "
import json
d = json.loads('$FILES_HASH')
d['$rel'] = '$h'
print(json.dumps(d))
")
  fi
}

add_dir_hashes() {
  local dir="$1"
  if [[ ! -d "$dir" ]]; then return; fi
  while IFS= read -r -d '' f; do
    add_file_hash "$f"
  done < <(find "$dir" -type f -not -name '*.log' -not -name '*.pid' -not -name '*.lock' -print0 2>/dev/null)
}

# (A) Solar 本体
log "  打包 Solar 本体..."
mkdir -p "$BUNDLE_DIR/solar/harness" "$BUNDLE_DIR/solar/bin"
mkdir -p "$BUNDLE_DIR/solar/brain" "$BUNDLE_DIR/solar/reports" "$BUNDLE_DIR/solar/rules-archive"

# SQLite 数据库: 先 backup 再打包
if [[ -f "$HOME/.solar/solar.db" ]]; then
  sqlite3 "$HOME/.solar/solar.db" ".backup '$BUNDLE_DIR/solar/solar.db'" 2>/dev/null && \
    ok "solar.db 一致性备份完成" || cp "$HOME/.solar/solar.db" "$BUNDLE_DIR/solar/solar.db"
fi

# MemPalace ChromaDB
if [[ -d "$HOME/.solar/mempalace" ]]; then
  mkdir -p "$BUNDLE_DIR/solar/mempalace"
  # ChromaDB: 备份 sqlite
  if [[ -f "$HOME/.solar/mempalace/chroma.sqlite3" ]]; then
    sqlite3 "$HOME/.solar/mempalace/chroma.sqlite3" ".backup '$BUNDLE_DIR/solar/mempalace/chroma.sqlite3'" 2>/dev/null || \
      cp "$HOME/.solar/mempalace/chroma.sqlite3" "$BUNDLE_DIR/solar/mempalace/chroma.sqlite3"
  fi
  # 其他文件
  while IFS= read -r -d '' f; do
    [[ "$(basename "$f")" == "chroma.sqlite3" ]] && continue
    local_rel="${f#$HOME/.solar/mempalace/}"
    mkdir -p "$BUNDLE_DIR/solar/mempalace/$(dirname "$local_rel")"
    cp "$f" "$BUNDLE_DIR/solar/mempalace/$local_rel"
  done < <(find "$HOME/.solar/mempalace" -type f -print0 2>/dev/null)
  ok "MemPalace 打包完成"
fi

# 目录拷贝 (排除运行时状态)
for subdir in harness brain reports rules-archive bin; do
  if [[ -d "$HOME/.solar/$subdir" ]]; then
    rsync -a --exclude='*.pid' --exclude='*.lock' --exclude='*.log' \
      "$HOME/.solar/$subdir/" "$BUNDLE_DIR/solar/$subdir/" 2>/dev/null || true
  fi
done

# --include-templates: 新模板 + 阶段状态机 + verify/cache CLI
if $INCLUDE_TEMPLATES; then
  log "  打包 agent-skills 模板 (v2)..."
  mkdir -p "$BUNDLE_DIR/solar/harness/templates" "$BUNDLE_DIR/solar/harness/lib"
  for f in "$HOME/.solar/harness/templates/contract-template-v2.md" \
           "$HOME/.solar/harness/lib/phase-state-machine.sh"; do
    [[ -f "$f" ]] && cp "$f" "$BUNDLE_DIR/solar/harness/${f#$HOME/.solar/harness/}"
  done
  for bin in solar-verify solar-cache; do
    [[ -f "$HOME/.solar/bin/$bin" ]] && cp "$HOME/.solar/bin/$bin" "$BUNDLE_DIR/solar/bin/"
  done
  ok "templates + CLI 已打包"
fi

# --include-cache: cache 元数据 (不含 body, 因 cache 是机器本地重建)
if $INCLUDE_CACHE; then
  log "  打包 cache 元数据..."
  mkdir -p "$BUNDLE_DIR/solar/harness/cache"
  [[ -f "$HOME/.solar/harness/cache/metadata.jsonl" ]] && \
    cp "$HOME/.solar/harness/cache/metadata.jsonl" "$BUNDLE_DIR/solar/harness/cache/"
  ok "cache metadata 已打包 (不含 body)"
fi

# 散文件
for f in session-state.jsonl .session-id; do
  [[ -f "$HOME/.solar/$f" ]] && cp "$HOME/.solar/$f" "$BUNDLE_DIR/solar/"
done

# (B) Claude 配置
log "  打包 Claude 配置..."
mkdir -p "$BUNDLE_DIR/claude/rules" "$BUNDLE_DIR/claude/skills" "$BUNDLE_DIR/claude/hooks"
mkdir -p "$BUNDLE_DIR/claude/agents" "$BUNDLE_DIR/claude/core" "$BUNDLE_DIR/claude/scripts"
mkdir -p "$BUNDLE_DIR/claude/projects"

for item in CLAUDE.md settings.json settings.local.json; do
  [[ -f "$HOME/.claude/$item" ]] && cp "$HOME/.claude/$item" "$BUNDLE_DIR/claude/"
done

for subdir in rules skills hooks agents core scripts; do
  if [[ -d "$HOME/.claude/$subdir" ]]; then
    rsync -a --exclude='node_modules' "$HOME/.claude/$subdir/" "$BUNDLE_DIR/claude/$subdir/" 2>/dev/null || true
  fi
done

# Claude Memory
if [[ -d "$HOME/.claude/projects" ]]; then
  rsync -a "$HOME/.claude/projects/" "$BUNDLE_DIR/claude/projects/" 2>/dev/null || true
fi

# Claude Code config
if [[ -d "$HOME/.config/claude-code" ]]; then
  mkdir -p "$BUNDLE_DIR/config/claude-code"
  rsync -a "$HOME/.config/claude-code/" "$BUNDLE_DIR/config/claude-code/" 2>/dev/null || true
fi

# (C) 系统级
log "  打包系统级配置..."
mkdir -p "$BUNDLE_DIR/system"

for rc in .zshrc .zprofile .bashrc .bash_profile .tmux.conf .gitconfig; do
  [[ -f "$HOME/$rc" ]] && cp "$HOME/$rc" "$BUNDLE_DIR/system/"
done

# Claude Desktop MCP config
CLAUDE_DESKTOP="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
if [[ -f "$CLAUDE_DESKTOP" ]]; then
  mkdir -p "$BUNDLE_DIR/system/claude-desktop"
  cp "$CLAUDE_DESKTOP" "$BUNDLE_DIR/system/claude-desktop/"
fi

# LaunchAgents
mkdir -p "$BUNDLE_DIR/system/LaunchAgents"
for plist in "$HOME/Library/LaunchAgents"/com.solar.* "$HOME/Library/LaunchAgents"/com.anthropic.*; do
  [[ -f "$plist" ]] && cp "$plist" "$BUNDLE_DIR/system/LaunchAgents/"
done

# crontab
if crontab -l &>/dev/null; then
  crontab -l > "$BUNDLE_DIR/system/crontab.txt" 2>/dev/null || true
fi

# ── 2. 依赖快照 ──
log "生成依赖快照..."
mkdir -p "$BUNDLE_DIR/deps"

brew bundle dump --file="$BUNDLE_DIR/deps/Brewfile" 2>/dev/null && ok "Brewfile 生成" || \
  echo "# brew bundle dump failed" > "$BUNDLE_DIR/deps/Brewfile"

npm list -g --depth=0 > "$BUNDLE_DIR/deps/npm-global.txt" 2>/dev/null && ok "npm 全局列表生成" || \
  echo "# npm list failed" > "$BUNDLE_DIR/deps/npm-global.txt"

pipx list --short > "$BUNDLE_DIR/deps/pipx.txt" 2>/dev/null && ok "pipx 列表生成" || \
  echo "# pipx list failed" > "$BUNDLE_DIR/deps/pipx.txt"

python3 -m pip freeze > "$BUNDLE_DIR/deps/pip-freeze.txt" 2>/dev/null && ok "pip freeze 生成" || \
  echo "# pip freeze failed" > "$BUNDLE_DIR/deps/pip-freeze.txt"

# ── 3. Secrets 分包 (可选) ──
SECRETS_ENC=""
if [[ "$INCLUDE_SECRETS" == "true" ]]; then
  log "打包 secrets..."
  SECRETS_DIR="$WORK_DIR/secrets-$$"
  mkdir -p "$SECRETS_DIR/ssh" "$SECRETS_DIR/gnupg" "$SECRETS_DIR/env"

  # SSH 私钥
  for key in "$HOME/.ssh"/id_* "$HOME/.ssh"/*.pem "$HOME/.ssh"/*_rsa; do
    [[ -f "$key" ]] && cp "$key" "$SECRETS_DIR/ssh/"
  done
  # SSH config + known_hosts
  for f in config known_hosts authorized_keys; do
    [[ -f "$HOME/.ssh/$f" ]] && cp "$HOME/.ssh/$f" "$SECRETS_DIR/ssh/"
  done

  # GPG
  if [[ -d "$HOME/.gnupg" ]]; then
    cp -a "$HOME/.gnupg/" "$SECRETS_DIR/gnupg/" 2>/dev/null || true
  fi

  # API keys from environment
  for key_name in ANTHROPIC_API_KEY OPENAI_API_KEY DEEPSEEK_API_KEY GEMINI_API_KEY GOOGLE_API_KEY GLM_API_KEY OPENROUTER_API_KEY; do
    val="${!key_name:-}"
    if [[ -n "$val" ]]; then
      echo "export ${key_name}=\"${val}\"" >> "$SECRETS_DIR/env/api-keys.sh"
    fi
  done

  # .env files
  for envfile in "$HOME/.solar/.env" "$HOME/.claude/.env"; do
    [[ -f "$envfile" ]] && cp "$envfile" "$SECRETS_DIR/env/"
  done

  # 打包 secrets
  SECRETS_TAR="$WORK_DIR/secrets.tar.gz"
  tar cf "$SECRETS_TAR" -C "$SECRETS_DIR" . 2>/dev/null

  # AES-256 加密
  if [[ -n "$PASSWORD" ]]; then
    SECRETS_ENC="$BUNDLE_DIR/secrets.enc"
    printf '%s' "$PASSWORD" | openssl enc -aes-256-cbc -salt -in "$SECRETS_TAR" -out "$SECRETS_ENC" -pass stdin 2>/dev/null
    ok "Secrets AES-256 加密完成"
    unset PASSWORD
  else
    # 无密码: 提示输入
    SECRETS_ENC="$BUNDLE_DIR/secrets.enc"
    log "请输入加密密码 (不会显示): "
    openssl enc -aes-256-cbc -salt -in "$SECRETS_TAR" -out "$SECRETS_ENC" -pass stdin 2>/dev/null
    ok "Secrets AES-256 加密完成"
    unset PASSWORD
  fi
  rm -rf "$SECRETS_DIR" "$SECRETS_TAR"
fi

# ── 4. 计算 files_hash ──
log "计算文件哈希..."
FILES_HASH_JSON="$WORK_DIR/files_hash.json"
export BUNDLE_DIR
python3 << 'PYEOF'
import json, hashlib, os, sys

bundle_dir = os.environ.get("BUNDLE_DIR", "")
result = {}

for root, dirs, files in os.walk(bundle_dir):
    for fname in files:
        fpath = os.path.join(root, fname)
        rel = os.path.relpath(fpath, bundle_dir)
        if rel.endswith(('.enc',)):
            continue
        try:
            h = hashlib.sha256(open(fpath, 'rb').read()).hexdigest()
            result[rel] = h
        except:
            pass

with open(os.path.join(bundle_dir, '..', 'files_hash.json'), 'w') as f:
    json.dump(result, f, indent=2)
print(f"  已计算 {len(result)} 个文件哈希")
PYEOF

# ── 5. bundle-meta.json ──
log "生成 bundle-meta.json..."
MANIFEST_HASH=$(sha256_file "$MIGRATE_DIR/MIGRATION-MANIFEST.md" 2>/dev/null || echo "unknown")
SW_VERS=$(sw_vers -productVersion 2>/dev/null || echo "unknown")
ARCH=$(arch 2>/dev/null || uname -m)
BUNDLE_ID=$(python3 -c "import uuid; print(uuid.uuid4())")

export INCLUDE_SECRETS SECRETS_ENC
python3 << PYEOF
import json, os
meta = {
    "bundle_id": "$BUNDLE_ID",
    "version": "1.0",
    "source_hostname": "$HOSTNAME_VAL",
    "source_home": "$HOME",
    "source_arch": "$ARCH",
    "source_sw_vers": "$SW_VERS",
    "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "has_secrets": os.environ.get("INCLUDE_SECRETS", "false") == "true",
    "secrets_encrypted": os.environ.get("SECRETS_ENC", "") != "",
    "manifest_hash": "$MANIFEST_HASH"
}

# Load files_hash
fh_path = os.path.join("$WORK_DIR", "files_hash.json")
if os.path.exists(fh_path):
    with open(fh_path) as f:
        meta["files_hash"] = json.load(f)
else:
    meta["files_hash"] = {}

with open(os.path.join("$BUNDLE_DIR", "bundle-meta.json"), 'w') as f:
    json.dump(meta, f, indent=2, ensure_ascii=False)
print("  bundle-meta.json 生成完成")
PYEOF

# ── 6. 打包 tar ──
log "打包 bundle..."
BUNDLE_TAR="$OUT_DIR/${BUNDLE_NAME}.tar"
tar cf "$BUNDLE_TAR" -C "$WORK_DIR" "$BUNDLE_NAME" 2>/dev/null
ok "Bundle 打包完成"

# ── 7. SHA256 ──
BUNDLE_SHA=$(sha256_file "$BUNDLE_TAR")
echo "$BUNDLE_SHA" > "${BUNDLE_TAR}.sha256"
BUNDLE_SIZE=$(du -h "$BUNDLE_TAR" | cut -f1)

echo ""
echo "══════════════════════════════════════════════════"
echo "  Solar Migration Bundle 导出完成"
echo "══════════════════════════════════════════════════"
echo ""
ok "Bundle: $BUNDLE_TAR"
ok "大小: $BUNDLE_SIZE"
ok "SHA256: $BUNDLE_SHA"
ok "Bundle ID: $BUNDLE_ID"
if [[ "$INCLUDE_SECRETS" == "true" ]]; then
  ok "Secrets: 已加密打包"
else
  warn "Secrets: 未包含 (使用 --include-secrets 打包)"
fi
echo ""

# ── 8. D6: Push to remote (可选) ──
if [[ -n "$PUSH_TARGET" ]]; then
  log "推送 bundle 到远程: ${PUSH_TARGET}"

  # Ensure target path ends without / or normalize
  PUSH_HOST="${PUSH_TARGET%%:*}"
  PUSH_PATH="${PUSH_TARGET#*:}"
  [[ -z "$PUSH_PATH" ]] && PUSH_PATH="\$HOME/solar-bundles/"

  SSH_OPTS="-o BatchMode=yes -o StrictHostKeyChecking=accept-new"

  # Ensure remote dir exists
  ssh $SSH_OPTS "$PUSH_HOST" "mkdir -p '$(dirname "$PUSH_PATH")'" 2>/dev/null || true

  # Transfer bundle + sha256: prefer rsync, fallback scp
  if command -v rsync &>/dev/null; then
    log "  rsync ${BUNDLE_TAR} → ${PUSH_HOST}:${PUSH_PATH}"
    rsync --partial --append --progress "$BUNDLE_TAR" "${PUSH_HOST}:${PUSH_PATH}" 2>&1
    rsync --partial --append --progress "${BUNDLE_TAR}.sha256" "${PUSH_HOST}:${PUSH_PATH}.sha256" 2>&1
  else
    log "  scp ${BUNDLE_TAR} → ${PUSH_HOST}:${PUSH_PATH}"
    scp $SSH_OPTS "$BUNDLE_TAR" "${PUSH_HOST}:${PUSH_PATH}" 2>/dev/null
    scp $SSH_OPTS "${BUNDLE_TAR}.sha256" "${PUSH_HOST}:${PUSH_PATH}.sha256" 2>/dev/null
  fi

  if [[ $? -eq 0 ]]; then
    ok "Bundle 推送完成: ${PUSH_HOST}:${PUSH_PATH}"
  else
    err "Bundle 推送失败"
    exit 1
  fi

  # Cleanup local if requested
  if [[ "$CLEANUP_LOCAL" == "true" ]]; then
    rm -f "$BUNDLE_TAR" "${BUNDLE_TAR}.sha256"
    ok "本机 bundle 已清理 (--cleanup-local)"
  fi
fi

exit 0
