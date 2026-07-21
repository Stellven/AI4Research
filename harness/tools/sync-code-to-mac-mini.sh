#!/usr/bin/env bash
# Sync Solar Harness code and Codex collaboration glue to the Mac mini.
#
# This intentionally excludes secrets and runtime state. It is a code sync,
# not a full machine migration.
set -euo pipefail

LOCAL_HOME="${HOME}"
HARNESS_DIR="${LOCAL_HOME}/.solar/harness"
REMOTE_USER="${SOLAR_MAC_MINI_USER:-solar}"
REMOTE_HOST="${SOLAR_MAC_MINI_HOST:-}"
REMOTE_PATH="${SOLAR_MAC_MINI_PATH:-}"
DRY_RUN=false
VERIFY_ONLY=false

usage() {
  cat <<'EOF'
Usage:
  sync-code-to-mac-mini.sh [--host user@host] [--dry-run] [--verify-only]

Env:
  SOLAR_MAC_MINI_USER  default: solar
  SOLAR_MAC_MINI_HOST  default: auto-detect 203.0.113.10 then 192.0.2.189
  SOLAR_MAC_MINI_PATH  default: remote $HOME
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      target="$2"; shift 2
      if [[ "$target" == *@* ]]; then
        REMOTE_USER="${target%@*}"
        REMOTE_HOST="${target#*@}"
      else
        REMOTE_HOST="$target"
      fi
      ;;
    --dry-run) DRY_RUN=true; shift ;;
    --verify-only) VERIFY_ONLY=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

log() { printf '[solar-sync] %s\n' "$*"; }
die() { printf '[solar-sync] ERROR: %s\n' "$*" >&2; exit 1; }

[[ -d "$HARNESS_DIR" ]] || die "local harness missing: $HARNESS_DIR"
command -v rsync >/dev/null 2>&1 || die "rsync not found"

ssh_try() {
  ssh -o BatchMode=yes -o ConnectTimeout=4 -o StrictHostKeyChecking=accept-new "$1" "$2"
}

detect_remote() {
  if [[ -n "$REMOTE_HOST" ]]; then
    printf '%s@%s\n' "$REMOTE_USER" "$REMOTE_HOST"
    return
  fi
  local host
  for host in 203.0.113.10 192.0.2.189; do
    if ssh_try "${REMOTE_USER}@${host}" 'printf ok' >/dev/null 2>&1; then
      printf '%s@%s\n' "$REMOTE_USER" "$host"
      return
    fi
  done
  die "cannot reach Mac mini via 203.0.113.10 or 192.0.2.189"
}

REMOTE="$(detect_remote)"
if [[ -z "$REMOTE_PATH" ]]; then
  REMOTE_PATH="$(ssh_try "$REMOTE" 'printf "%s" "$HOME"')"
fi
[[ -n "$REMOTE_PATH" ]] || die "cannot resolve remote HOME"

RSYNC_FLAGS=(-az --human-readable)
if [[ "${SOLAR_SYNC_VERBOSE:-0}" == "1" ]]; then
  RSYNC_FLAGS+=(--itemize-changes)
fi
if [[ "$DRY_RUN" == "true" ]]; then
  RSYNC_FLAGS+=(--dry-run)
fi

COMMON_EXCLUDES=(
  --exclude='.git/'
  --exclude='node_modules/'
  --exclude='.venv/'
  --exclude='.*-venv/'
  --exclude='*.venv/'
  --exclude='*-venv/'
  --exclude='venv/'
  --exclude='venvs/'
  --exclude='__pycache__/'
  --exclude='.pytest_cache/'
  --exclude='*.pyc'
  --exclude='*.pyo'
  --exclude='*.pid'
  --exclude='*.lock'
  --exclude='*.sock'
  --exclude='*.log'
  --exclude='*.db'
  --exclude='*.db-*'
  --exclude='*.sqlite'
  --exclude='*.sqlite3'
  --exclude='*.events.jsonl'
  --exclude='.DS_Store'
)

HARNESS_EXCLUDES=(
  "${COMMON_EXCLUDES[@]}"
  --exclude='model-config.sh'
  --exclude='model-config.sh.*'
  --exclude='config/solar-user-config.json'
  --exclude='config/*.local.*'
  --exclude='.token-report.log'
  --exclude='events.jsonl'
  --exclude='logs/'
  --exclude='run/'
  --exclude='sprints/'
  --exclude='cache/'
  --exclude='backups/'
  --exclude='workspace/'
  --exclude='workspaces/'
  --exclude='search-index/'
  --exclude='vendor/mineru/.venv/'
  --exclude='vendor/mermaid-viewer/node_modules/'
)

BIN_FILES=(
  solar-harness
  solar-config-ui
  solar-remote-run
  solar-remote-dispatch
  solar-net-detect
  remote-coordinator-patch.sh
)

verify_remote() {
  log "remote verify: $REMOTE"
  ssh_try "$REMOTE" "set -e
    test -d '$REMOTE_PATH/.solar/harness'
    test -x '$REMOTE_PATH/.solar/harness/solar-harness.sh'
    bash -n '$REMOTE_PATH/.solar/harness/solar-harness.sh'
    bash -n '$REMOTE_PATH/.solar/harness/coordinator.sh'
    bash -n '$REMOTE_PATH/.solar/harness/pane-launcher.sh'
    bash -n '$REMOTE_PATH/.solar/harness/chain-watcher.sh'
    python3 -m py_compile \
      '$REMOTE_PATH/.solar/harness/lib/intent_engine_adapter.py' \
      '$REMOTE_PATH/.solar/harness/lib/capability_certification_suite.py' \
      '$REMOTE_PATH/.solar/harness/lib/capability_activation_proof.py' \
      '$REMOTE_PATH/.solar/harness/lib/graph_scheduler.py' \
      '$REMOTE_PATH/.solar/harness/lib/graph_node_dispatcher.py'
    '$REMOTE_PATH/.solar/harness/solar-harness.sh' help >/tmp/solar-harness-help.verify
    grep -q 'graph-scheduler' /tmp/solar-harness-help.verify
    grep -q 'verify-integrations' /tmp/solar-harness-help.verify
    grep -q 'context inject' /tmp/solar-harness-help.verify
    if grep -R --exclude-dir='__pycache__' --exclude='*.pyc' --exclude='sync-code-to-mac-mini.sh' --exclude='model-config.sh' '~' '$REMOTE_PATH/.solar/harness/lib' '$REMOTE_PATH/.solar/harness/tools' '$REMOTE_PATH/.solar/harness/'*.sh '$REMOTE_PATH/.solar/bin' '$REMOTE_PATH/.solar/codex-bridge' >/tmp/solar-path-leaks.verify 2>/dev/null; then
      echo 'path_leaks_found'
      head -20 /tmp/solar-path-leaks.verify
      exit 42
    fi
    echo 'verify=ok'
  "
}

if [[ "$VERIFY_ONLY" == "true" ]]; then
  verify_remote
  exit 0
fi

log "remote=$REMOTE remote_home=$REMOTE_PATH dry_run=$DRY_RUN"

if [[ "$DRY_RUN" != "true" ]]; then
  log "remote lightweight code backup"
  ssh_try "$REMOTE" "set -e
    ts=\$(date -u +%Y%m%dT%H%M%SZ)
    backup='$REMOTE_PATH/.solar-sync-backups/code-before-'\$ts
    mkdir -p \"\$backup/harness\" \"\$backup/bin\"
    if [[ -d '$REMOTE_PATH/.solar/harness' ]]; then
      for item in solar-harness.sh coordinator.sh pane-launcher.sh chain-watcher.sh codex-bridge.sh solar-config-ui.sh lib integrations tools tests config skills schemas templates plugins migrate docs docker hooks personas release runbooks ADR evals; do
        [[ -e '$REMOTE_PATH/.solar/harness/'\"\$item\" ]] && rsync -a --exclude='*.log' --exclude='*.pid' --exclude='*.lock' --exclude='node_modules' --exclude='.venv' --exclude='.*-venv' --exclude='*-venv' --exclude='venvs' --exclude='run' --exclude='cache' '$REMOTE_PATH/.solar/harness/'\"\$item\" \"\$backup/harness/\" || true
      done
    fi
    if [[ -d '$REMOTE_PATH/.solar/bin' ]]; then
      rsync -a --exclude='*.log' '$REMOTE_PATH/.solar/bin/' \"\$backup/bin/\" || true
    fi
    [[ -d '$REMOTE_PATH/.solar/codex-bridge' ]] && rsync -a --exclude='*.log' '$REMOTE_PATH/.solar/codex-bridge/' \"\$backup/codex-bridge/\" || true
    mkdir -p '$REMOTE_PATH/.solar/harness' '$REMOTE_PATH/.solar/bin'
  "
fi

log "sync harness code"
rsync "${RSYNC_FLAGS[@]}" "${HARNESS_EXCLUDES[@]}" \
  "$HARNESS_DIR/" "$REMOTE:$REMOTE_PATH/.solar/harness/"

log "sync codex bridge"
if [[ -d "$LOCAL_HOME/.solar/codex-bridge" ]]; then
  rsync "${RSYNC_FLAGS[@]}" "${COMMON_EXCLUDES[@]}" \
    "$LOCAL_HOME/.solar/codex-bridge/" "$REMOTE:$REMOTE_PATH/.solar/codex-bridge/"
fi

log "sync selected ~/.solar/bin scripts"
for f in "${BIN_FILES[@]}"; do
  if [[ -e "$LOCAL_HOME/.solar/bin/$f" ]]; then
    rsync "${RSYNC_FLAGS[@]}" "${COMMON_EXCLUDES[@]}" \
      "$LOCAL_HOME/.solar/bin/$f" "$REMOTE:$REMOTE_PATH/.solar/bin/$f"
  fi
done

if [[ "$DRY_RUN" != "true" ]]; then
  log "remote path rewrite and entrypoint repair"
  ssh_try "$REMOTE" "REMOTE_HOME='$REMOTE_PATH' LOCAL_HOME='$LOCAL_HOME' python3 - <<'PY'
import os
from pathlib import Path

remote_home = os.environ['REMOTE_HOME']
local_home = os.environ['LOCAL_HOME']
roots = [
    Path(remote_home) / '.solar' / 'harness',
    Path(remote_home) / '.solar' / 'bin',
    Path(remote_home) / '.solar' / 'codex-bridge',
]
exts = {
    '.sh', '.py', '.md', '.json', '.jsonl', '.yml', '.yaml', '.toml',
    '.ts', '.js', '.html', '.css', '.plist', '.txt', '.env', '.example',
    '.conf', '.mmd'
}
skip_parts = {'node_modules', '.venv', 'venv', 'venvs', '.arena-venv', '.git', '__pycache__'}
changed = 0
for root in roots:
    if not root.exists():
        continue
    candidates = root.rglob('*') if root.is_dir() else [root]
    for path in candidates:
        if not path.is_file():
            continue
        if any(part in skip_parts for part in path.parts):
            continue
        if path.name in {'model-config.sh', 'solar-user-config.json'}:
            continue
        if path.suffix not in exts and not path.name.startswith('.'):
            continue
        try:
            data = path.read_text(encoding='utf-8')
        except Exception:
            continue
        new = data.replace(local_home, remote_home)
        if new != data:
            path.write_text(new, encoding='utf-8')
            changed += 1
print(f'path_rewrite_changed={changed}')
PY
    chmod +x '$REMOTE_PATH/.solar/harness/solar-harness.sh' '$REMOTE_PATH/.solar/harness/coordinator.sh' '$REMOTE_PATH/.solar/harness/pane-launcher.sh' '$REMOTE_PATH/.solar/harness/chain-watcher.sh' 2>/dev/null || true
    ln -sf '$REMOTE_PATH/.solar/harness/solar-harness.sh' '$REMOTE_PATH/.solar/bin/solar-harness'
    ln -sf '$REMOTE_PATH/.solar/harness/solar-config-ui.sh' '$REMOTE_PATH/.solar/bin/solar-config-ui'
  "
  verify_remote
fi

log "done"
