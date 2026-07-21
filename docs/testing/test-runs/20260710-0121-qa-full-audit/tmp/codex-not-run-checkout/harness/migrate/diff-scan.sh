#!/usr/bin/env bash
# ================================================================
# Solar Harness — Diff Scan
# Sprint 20260423-151839 D1+D7
#
# 扫描 bundle 与目标机的差异，分类 added/modified/untouched
# Python concurrent.futures 并行 SHA256
#
# 用法:
#   bash diff-scan.sh <bundle_dir> <target_home> <output_dir> [--jobs N]
#
# @module solar-farm/harness/migrate
# ================================================================
set -euo pipefail

G='\033[0;32m'; R='\033[0;31m'; Y='\033[1;33m'; C='\033[0;36m'; N='\033[0m'
log()  { echo -e "${C}[diff-scan]${N} $*"; }
ok()   { echo -e "  ${G}✓${N} $*"; }
warn() { echo -e "  ${Y}⚠${N} $*"; }
err()  { echo -e "  ${R}✗${N} $*"; }

BUNDLE_DIR=""
TARGET_HOME=""
OUTPUT_DIR=""
JOBS=4

while [[ $# -gt 0 ]]; do
  case "$1" in
    --jobs) JOBS="$2"; shift 2 ;;
    -*)
      err "未知参数: $1"; exit 1 ;;
    *)
      if [[ -z "$BUNDLE_DIR" ]]; then
        BUNDLE_DIR="$1"; shift
      elif [[ -z "$TARGET_HOME" ]]; then
        TARGET_HOME="$1"; shift
      elif [[ -z "$OUTPUT_DIR" ]]; then
        OUTPUT_DIR="$1"; shift
      else
        err "多余参数: $1"; exit 1
      fi
  esac
done

if [[ -z "$BUNDLE_DIR" || -z "$TARGET_HOME" || -z "$OUTPUT_DIR" ]]; then
  err "用法: bash diff-scan.sh <bundle_dir> <target_home> <output_dir> [--jobs N]"
  exit 1
fi

if [[ ! -d "$BUNDLE_DIR" ]]; then
  err "Bundle 目录不存在: $BUNDLE_DIR"
  exit 1
fi

META="$BUNDLE_DIR/bundle-meta.json"
if [[ ! -f "$META" ]]; then
  err "bundle-meta.json 缺失: $META"
  exit 1
fi

mkdir -p "$OUTPUT_DIR"

log "开始差分扫描..."
log "  Bundle: $BUNDLE_DIR"
log "  Target: $TARGET_HOME"
log "  Workers: $JOBS"

export BUNDLE_DIR TARGET_HOME OUTPUT_DIR JOBS META
python3 << 'PYEOF'
import json, hashlib, os, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

bundle_dir = os.environ["BUNDLE_DIR"]
target_home = os.environ["TARGET_HOME"]
output_dir = os.environ["OUTPUT_DIR"]
jobs = int(os.environ.get("JOBS", "4"))
meta_path = os.environ["META"]

# 跳过模式
SKIP_PATTERNS = [
    ".git/", "node_modules/", "__pycache__/",
    ".DS_Store", ".swp",
]
SKIP_SUFFIXES = (".pyc", ".pyo")

def should_skip(rel_path):
    for pat in SKIP_PATTERNS:
        if pat in rel_path:
            return True
    if rel_path.endswith(SKIP_SUFFIXES):
        return True
    return False

def sha256_file(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

def classify_file(rel_path, bundle_hash):
    """Classify a single file against target."""
    # Map bundle rel path to target path
    if rel_path.startswith("solar/"):
        target_path = os.path.join(target_home, ".solar", rel_path[len("solar/"):])
    elif rel_path.startswith("claude/"):
        target_path = os.path.join(target_home, ".claude", rel_path[len("claude/"):])
    elif rel_path.startswith("system/"):
        target_path = os.path.join(target_home, rel_path[len("system/"):])
    elif rel_path.startswith("deps/"):
        return "skip", rel_path, None
    elif rel_path == "bundle-meta.json":
        return "skip", rel_path, None
    else:
        return "skip", rel_path, None

    if not os.path.exists(target_path):
        return "added", rel_path, bundle_hash

    try:
        target_hash = sha256_file(target_path)
    except Exception:
        return "added", rel_path, bundle_hash

    if target_hash == bundle_hash:
        return "untouched", rel_path, bundle_hash
    else:
        return "modified", rel_path, {"target_sha256_before": target_hash, "bundle_sha256": bundle_hash}

# Load files_hash from bundle-meta.json
try:
    with open(meta_path) as f:
        meta = json.load(f)
except Exception as e:
    print(f"  ✗ 无法读取 bundle-meta.json: {e}", file=sys.stderr)
    sys.exit(1)

files_hash = meta.get("files_hash", {})
if not files_hash:
    print("  ⚠ files_hash 为空, 跳过扫描")
    manifest = {
        "version": "1.0",
        "created_at": __import__("datetime").datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bundle_source": meta.get("bundle_id", "unknown"),
        "target_home": target_home,
        "stats": {"added": 0, "modified": 0, "untouched": 0, "total_scanned": 0},
        "added": [],
        "modified": [],
        "untouched_count": 0
    }
    with open(os.path.join(output_dir, "diff-manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    sys.exit(0)

# Filter out skipped paths
to_scan = {k: v for k, v in files_hash.items() if not should_skip(k)}
skipped_count = len(files_hash) - len(to_scan)

print(f"  扫描 {len(to_scan)} 个文件 (跳过 {skipped_count} 个)...")

added = []
modified = []
untouched = 0

# Parallel classification (ThreadPoolExecutor for IO-bound SHA256)
from concurrent.futures import ThreadPoolExecutor
with ThreadPoolExecutor(max_workers=jobs) as executor:
    futures = {
        executor.submit(classify_file, rel, bhash): rel
        for rel, bhash in to_scan.items()
    }
    for future in as_completed(futures):
        rel = futures[future]
        try:
            category, path, data = future.result()
        except Exception as e:
            print(f"  ⚠ 扫描异常 {rel}: {e}")
            continue

        if category == "added":
            added.append({"path": path, "bundle_sha256": data})
        elif category == "modified":
            modified.append({"path": path, "target_sha256_before": data["target_sha256_before"], "bundle_sha256": data["bundle_sha256"]})
        elif category == "untouched":
            untouched += 1

# Build manifest
manifest = {
    "version": "1.0",
    "created_at": __import__("datetime").datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    "bundle_source": meta.get("bundle_id", "unknown"),
    "target_home": target_home,
    "stats": {
        "added": len(added),
        "modified": len(modified),
        "untouched": untouched,
        "total_scanned": len(to_scan)
    },
    "added": sorted(added, key=lambda x: x["path"]),
    "modified": sorted(modified, key=lambda x: x["path"]),
    "untouched_count": untouched
}

manifest_path = os.path.join(output_dir, "diff-manifest.json")
with open(manifest_path, "w") as f:
    json.dump(manifest, f, indent=2, ensure_ascii=False)

print(f"  ✓ 扫描完成: {len(added)} added, {len(modified)} modified, {untouched} untouched")
print(f"  ✓ 输出: {manifest_path}")
PYEOF

exit 0
