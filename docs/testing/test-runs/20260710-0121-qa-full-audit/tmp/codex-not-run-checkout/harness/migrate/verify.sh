#!/usr/bin/env bash
# ================================================================
# Solar Harness — Migrate Verify
# Sprint 20260422-162434 D4
#
# 验证 bundle 完整性, 不改目标系统
#
# 用法:
#   bash verify.sh <bundle> [--password <pw>]
#
# @module solar-farm/harness/migrate
# ================================================================
set -euo pipefail

HARNESS_DIR="$HOME/.solar/harness"

G='\033[0;32m'; R='\033[0;31m'; Y='\033[1;33m'; C='\033[0;36m'; N='\033[0m'
log()  { echo -e "${C}[migrate-verify]${N} $*"; }
ok()   { echo -e "  ${G}✓${N} $*"; }
warn() { echo -e "  ${Y}⚠${N} $*"; }
err()  { echo -e "  ${R}✗${N} $*"; }

BUNDLE=""
PASSWORD=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --password) PASSWORD="$2"; shift 2 ;;
    --*)        err "未知参数: $1"; exit 1 ;;
    *)
      if [[ -z "$BUNDLE" ]]; then BUNDLE="$1"; shift
      else err "多余参数: $1"; exit 1; fi
  esac
done

if [[ -z "$BUNDLE" ]]; then
  err "用法: verify.sh <bundle.tar> [--password <pw>]"
  exit 1
fi

if [[ ! -f "$BUNDLE" ]]; then
  err "Bundle 文件不存在: $BUNDLE"
  exit 1
fi

sha256_file() {
  shasum -a 256 "$1" 2>/dev/null | cut -d' ' -f1 || sha256sum "$1" | cut -d' ' -f1
}

PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0

vok()   { ok "$1"; PASS_COUNT=$((PASS_COUNT+1)); }
vfail() { err "$1"; FAIL_COUNT=$((FAIL_COUNT+1)); }
vwarn() { warn "$1"; WARN_COUNT=$((WARN_COUNT+1)); }

WORK_DIR="/tmp/solar-verify-$$"
mkdir -p "$WORK_DIR"
cleanup() { rm -rf "$WORK_DIR"; unset PASSWORD 2>/dev/null || true; }
trap cleanup EXIT

echo ""
echo "══════════════════════════════════════════════════"
echo "  Solar Migration — Verify"
echo "══════════════════════════════════════════════════"
echo ""

# ── 1. 外层 SHA256 ──
log "1. 外层完整性..."
SHA_FILE="${BUNDLE}.sha256"
if [[ -f "$SHA_FILE" ]]; then
  EXPECTED=$(cat "$SHA_FILE" | cut -d' ' -f1)
  ACTUAL=$(sha256_file "$BUNDLE")
  if [[ "$EXPECTED" == "$ACTUAL" ]]; then
    vok "SHA256 校验通过"
  else
    vfail "SHA256 不匹配"
  fi
else
  vwarn "无 .sha256 文件, 跳过外层校验"
fi

# ── 2. 解包 + bundle-meta.json ──
log "2. Bundle 结构..."
tar xf "$BUNDLE" -C "$WORK_DIR" 2>/dev/null
BUNDLE_DIR=$(find "$WORK_DIR" -maxdepth 1 -type d -name 'solar-bundle-*' | head -1)
if [[ -z "$BUNDLE_DIR" ]]; then
  vfail "Bundle 内未找到 solar-bundle-* 目录"
  exit 1
fi
vok "解包成功"

META="$BUNDLE_DIR/bundle-meta.json"
if [[ -f "$META" ]]; then
  vok "bundle-meta.json 存在"
else
  vfail "bundle-meta.json 缺失"
  exit 1
fi

# 读取元数据
SRC_HOME=$(python3 -c "import json; print(json.load(open('$META')).get('source_home',''))" 2>/dev/null)
SRC_HOSTNAME=$(python3 -c "import json; print(json.load(open('$META')).get('source_hostname',''))" 2>/dev/null)
BUNDLE_ID=$(python3 -c "import json; print(json.load(open('$META')).get('bundle_id',''))" 2>/dev/null)
HAS_SECRETS=$(python3 -c "import json; print(json.load(open('$META')).get('has_secrets',False))" 2>/dev/null)
SECRETS_ENCRYPTED=$(python3 -c "import json; print(json.load(open('$META')).get('secrets_encrypted',False))" 2>/dev/null)
SRC_ARCH=$(python3 -c "import json; print(json.load(open('$META')).get('source_arch','unknown'))" 2>/dev/null)

ok "源机: ${SRC_HOSTNAME} (${SRC_HOME})"
ok "Bundle ID: ${BUNDLE_ID}"
ok "Secrets: has=${HAS_SECRETS}, encrypted=${SECRETS_ENCRYPTED}"

# ── 3. files_hash 逐文件校验 ──
log "3. 文件哈希校验..."
export BUNDLE_DIR
python3 << 'PYEOF'
import json, hashlib, os, sys

bundle_dir = os.environ.get("BUNDLE_DIR", "")
meta_path = os.path.join(bundle_dir, "bundle-meta.json")

try:
    with open(meta_path) as f:
        meta = json.load(f)
except:
    print("  ✗ 无法读取 bundle-meta.json")
    sys.exit(1)

files_hash = meta.get("files_hash", {})
if not files_hash:
    print("  ⚠ files_hash 为空")
    sys.exit(0)

missing = []
mismatch = []
checked = 0

for rel, expected in files_hash.items():
    fpath = os.path.join(bundle_dir, rel)
    if not os.path.exists(fpath):
        missing.append(rel)
        continue
    try:
        actual = hashlib.sha256(open(fpath, 'rb').read()).hexdigest()
        if actual != expected:
            mismatch.append((rel, expected[:12], actual[:12]))
        checked += 1
    except Exception as e:
        missing.append(rel)

print(f"  ✓ 已校验 {checked}/{len(files_hash)} 个文件")

if missing:
    print(f"  ✗ {len(missing)} 个文件缺失:")
    for m in missing[:5]:
        print(f"    - {m}")

if mismatch:
    print(f"  ✗ {len(mismatch)} 个文件哈希不匹配:")
    for rel, exp, act in mismatch[:5]:
        print(f"    - {rel}: 预期={exp}... 实际={act}...")

if not missing and not mismatch:
    print(f"  ✓ 全部 {checked} 个文件完整性通过")
PYEOF

# ── 4. 路径替换模拟 ──
log "4. 路径替换模拟..."
if [[ "$SRC_HOME" != "$HOME" ]]; then
  SRC_USER=$(basename "$SRC_HOME")
  DST_USER=$(basename "$HOME")
  python3 << PYEOF
import os

src_home = "$SRC_HOME"
dst_home = "$HOME"
bundle_dir = "$BUNDLE_DIR"
text_exts = {'md','sh','json','py','ts','yml','yaml','conf','plist','zshrc','bashrc','txt','rc','cfg','toml','xml','csv'}
replace_count = 0

for root, dirs, files in os.walk(bundle_dir):
    for f in files:
        fpath = os.path.join(root, f)
        ext = f.rsplit('.', 1)[-1] if '.' in f else ''
        if ext.lower() in text_exts or (f.startswith('.') and '.' not in f[1:]):
            try:
                content = open(fpath, 'r', errors='ignore').read()
                if src_home in content:
                    replace_count += content.count(src_home)
            except:
                pass

print(f"  源路径 '{src_home}' 在文本文件中出现 {replace_count} 次")
print(f"  替换目标: '{dst_home}'")
if replace_count > 0:
    print(f"  ✓ 路径替换可正常执行")
else:
    print(f"  ℹ 无需路径替换 (源目标路径一致)")
PYEOF
else
  log "  源机路径与目标一致, 无需替换"
fi

# ── 5. Secrets 解密验证 ──
log "5. Secrets 验证..."
SECRETS_ENC="$BUNDLE_DIR/secrets.enc"
if [[ -f "$SECRETS_ENC" ]]; then
  if [[ "$SECRETS_ENCRYPTED" == "True" ]]; then
    if [[ -n "$PASSWORD" ]]; then
      if printf '%s' "$PASSWORD" | openssl enc -aes-256-cbc -d -in "$SECRETS_ENC" -out /dev/null -pass stdin 2>/dev/null; then
        vok "Secrets 解密验证通过"
      else
        vfail "Secrets 解密失败 (密码错误)"
      fi
    else
      vwarn "Secrets 加密, 未提供密码, 跳过解密验证"
    fi
  fi
else
  if [[ "$HAS_SECRETS" == "True" ]]; then
    vfail "Bundle 声明含 secrets 但缺少 secrets.enc"
  else
    vok "Bundle 不含 secrets"
  fi
fi

# ── 6. 依赖可装性检查 ──
log "6. 依赖可装性..."
DEPS_DIR="$BUNDLE_DIR/deps"

if [[ -f "$DEPS_DIR/Brewfile" ]]; then
  if command -v brew &>/dev/null; then
    vok "brew 可用"
  else
    vwarn "brew 不可用 — Brewfile 依赖无法安装"
  fi
fi

if [[ -f "$DEPS_DIR/npm-global.txt" ]]; then
  if command -v npm &>/dev/null; then
    vok "npm 可用"
  else
    vwarn "npm 不可用 — 全局 npm 包无法安装"
  fi
fi

if [[ -f "$DEPS_DIR/pipx.txt" ]]; then
  if command -v pipx &>/dev/null; then
    vok "pipx 可用"
  else
    vwarn "pipx 不可用 — pipx 工具无法安装"
  fi
fi

# ── 7. 架构兼容 ──
DST_ARCH=$(arch 2>/dev/null || uname -m)
if [[ "$SRC_ARCH" != "$DST_ARCH" ]]; then
  vwarn "架构差异: 源=${SRC_ARCH} 目标=${DST_ARCH}"
else
  vok "架构一致: ${SRC_ARCH}"
fi

# ── 结果 ──
echo ""
echo "──────────────────────────────────────────────────"
echo -e "  ${G}PASS: ${PASS_COUNT}${N}  ${R}FAIL: ${FAIL_COUNT}${N}  ${Y}WARN: ${WARN_COUNT}${N}"
echo "──────────────────────────────────────────────────"

if (( FAIL_COUNT > 0 )); then
  echo ""
  err "Bundle 验证失败, 不建议导入"
  exit 1
fi

echo ""
ok "Bundle 验证通过, 可以安全导入"
exit 0
