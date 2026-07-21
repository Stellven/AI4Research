#!/usr/bin/env bash
set -euo pipefail

# Sync portable Codex desktop state from this Mac to the Mac mini.
#
# Included:
#   - sessions/ and archived_sessions/ JSONL files
#   - session_index.jsonl, history.jsonl, .codex-global-state.json with path rewrite
#   - portable automation files: automation.toml, memory.md, run.sh, .run-jitter-salt
#   - state_5.sqlite rows via codex-state-portable-sync.py
#
# Excluded:
#   - auth.json, logs_2.sqlite, worktrees, plugins/cache, automation state/runs/logs
#   - active solar-harness sprint artifacts

LOCAL_HOME="${LOCAL_HOME:-$HOME}"
LOCAL_CODEX="${LOCAL_CODEX:-$LOCAL_HOME/.codex}"
REMOTE_HOST="${REMOTE_HOST:-solar@example-host}"
REMOTE_CODEX="${REMOTE_CODEX:-${HOME}/.codex}"
HARNESS_DIR="${HARNESS_DIR:-$LOCAL_HOME/.solar/harness}"
REMOTE_HARNESS="${REMOTE_HARNESS:-${HOME}/.solar/harness}"
FROM_PREFIX="${FROM_PREFIX:-$LOCAL_HOME}"
TO_PREFIX="${TO_PREFIX:-${HOME}}"

UTC="$(date -u +%Y%m%dT%H%M%SZ)"
TMP="$(mktemp -d)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

need_file() {
  [[ -f "$1" ]] || { echo "missing required file: $1" >&2; exit 2; }
}

need_dir() {
  [[ -d "$1" ]] || { echo "missing required dir: $1" >&2; exit 2; }
}

need_dir "$LOCAL_CODEX"
need_file "$HARNESS_DIR/scripts/codex-state-portable-sync.py"

mkdir -p "$TMP/codex-portable" "$TMP/automations"

sqlite3 "$LOCAL_CODEX/state_5.sqlite" ".backup '$TMP/codex-portable/state_5.snapshot.sqlite'"
"$HARNESS_DIR/scripts/codex-state-portable-sync.py" export \
  --db "$TMP/codex-portable/state_5.snapshot.sqlite" \
  --out "$TMP/codex-portable/state_5.portable.json" \
  --from-prefix "$FROM_PREFIX" \
  --to-prefix "$TO_PREFIX" >/tmp/codex-state-export.$UTC.json

python3 - "$LOCAL_CODEX/.codex-global-state.json" "$TMP/codex-portable/.codex-global-state.json" "$FROM_PREFIX" "$TO_PREFIX" <<'PY'
import json
import pathlib
import sys

src = pathlib.Path(sys.argv[1])
dst = pathlib.Path(sys.argv[2])
from_prefix = sys.argv[3]
to_prefix = sys.argv[4]

text = src.read_text()
text = text.replace(from_prefix, to_prefix)
data = json.loads(text)
dst.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n")
PY

for f in session_index.jsonl history.jsonl version.json; do
  [[ -f "$LOCAL_CODEX/$f" ]] && cp -p "$LOCAL_CODEX/$f" "$TMP/codex-portable/$f"
done

if [[ -d "$LOCAL_CODEX/automations" ]]; then
  cd "$LOCAL_CODEX/automations"
  [[ -f .run-jitter-salt ]] && install -m 600 .run-jitter-salt "$TMP/automations/.run-jitter-salt"
  while IFS= read -r -d '' f; do
    mkdir -p "$TMP/automations/$(dirname "$f")"
    cp -p "$f" "$TMP/automations/$f"
  done < <(find . -mindepth 2 -maxdepth 2 \( -name automation.toml -o -name memory.md -o -name run.sh \) -type f -print0)
fi

ssh -o BatchMode=yes -o ConnectTimeout=8 "$REMOTE_HOST" "
  set -euo pipefail
  mkdir -p '$REMOTE_CODEX' '$REMOTE_CODEX/backups/codex-portable-sync-$UTC' '$REMOTE_CODEX/imports' '$REMOTE_HARNESS/scripts'
  cd '$REMOTE_CODEX'
  for f in .codex-global-state.json session_index.jsonl history.jsonl version.json state_5.sqlite; do
    [[ -e \"\$f\" ]] && cp -p \"\$f\" 'backups/codex-portable-sync-$UTC/' || true
  done
  if [[ -d automations ]]; then
    tar -czf 'backups/codex-portable-sync-$UTC/automations-portable-backup.tgz' \
      --exclude='automations/*/state' \
      --exclude='automations/*/runs' \
      --exclude='automations/*/logs' \
      automations || true
  fi
  mkdir -p sessions archived_sessions automations
"

rsync -az "$LOCAL_CODEX/sessions/" "$REMOTE_HOST:$REMOTE_CODEX/sessions/"
rsync -az "$LOCAL_CODEX/archived_sessions/" "$REMOTE_HOST:$REMOTE_CODEX/archived_sessions/"
rsync -az "$TMP/codex-portable/" "$REMOTE_HOST:$REMOTE_CODEX/imports/codex-portable-sync-$UTC/"
rsync -az "$TMP/automations/" "$REMOTE_HOST:$REMOTE_CODEX/automations/"
scp -q "$HARNESS_DIR/scripts/codex-state-portable-sync.py" "$REMOTE_HOST:$REMOTE_HARNESS/scripts/codex-state-portable-sync.py"

REMOTE_OUT="$(ssh -o BatchMode=yes -o ConnectTimeout=8 "$REMOTE_HOST" "
  set -euo pipefail
  chmod +x '$REMOTE_HARNESS/scripts/codex-state-portable-sync.py'
  python3 -m py_compile '$REMOTE_HARNESS/scripts/codex-state-portable-sync.py'
  cp '$REMOTE_CODEX/imports/codex-portable-sync-$UTC/.codex-global-state.json' '$REMOTE_CODEX/.codex-global-state.json'
  for f in session_index.jsonl history.jsonl version.json; do
    [[ -f '$REMOTE_CODEX/imports/codex-portable-sync-$UTC/'\"\$f\" ]] && cp -p '$REMOTE_CODEX/imports/codex-portable-sync-$UTC/'\"\$f\" '$REMOTE_CODEX/'\"\$f\"
  done
  '$REMOTE_HARNESS/scripts/codex-state-portable-sync.py' import \
    --db '$REMOTE_CODEX/state_5.sqlite' \
    --input '$REMOTE_CODEX/imports/codex-portable-sync-$UTC/state_5.portable.json' \
    --backup-dir '$REMOTE_CODEX/backups/codex-portable-sync-$UTC'
  '$REMOTE_HARNESS/scripts/codex-state-portable-sync.py' verify --db '$REMOTE_CODEX/state_5.sqlite'
  printf 'sessions '; find '$REMOTE_CODEX/sessions' -type f | wc -l
  printf 'archived '; find '$REMOTE_CODEX/archived_sessions' -type f | wc -l
  python3 - <<'PY'
import json
from pathlib import Path
p = Path('$REMOTE_CODEX/.codex-global-state.json')
s = p.read_text()
print(json.dumps({'global_state_bytes': p.stat().st_size, 'has_from_prefix': '$FROM_PREFIX' in s, 'has_to_prefix': '$TO_PREFIX' in s}))
PY
")"

printf '%s\n' "$REMOTE_OUT"
printf 'backup=%s\n' "$UTC"
