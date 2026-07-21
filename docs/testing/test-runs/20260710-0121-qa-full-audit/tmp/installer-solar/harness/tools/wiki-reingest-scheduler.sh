#!/usr/bin/env bash
# Dispatch quarantined paper-reingest tasks to idle lab panes.

set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
BRIDGE="${HARNESS_DIR}/integrations/obsidian-wiki-bridge.sh"
LAB_SESSION="${SOLAR_LAB_SESSION_NAME:-solar-harness-lab}"
VAULT="${OBSIDIAN_VAULT_PATH:-$HOME/Knowledge}"
DISPATCH_DIR="${OBSIDIAN_WIKI_BRIDGE_RUN_DIR:-${VAULT}/_raw/solar-harness/.dispatch}"
REINGEST_PANES="${SOLAR_REINGEST_PANES:-0 1 2 3}"

if [[ ! -f "$BRIDGE" ]]; then
  echo "bridge not found: $BRIDGE" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$BRIDGE"

next_pending_reingest() {
  python3 - "$DISPATCH_DIR" "$VAULT" <<'PY'
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
vault = Path(sys.argv[2])

def field(text: str, name: str) -> str:
    m = re.search(rf"^{re.escape(name)}:\s*(.*)$", text, re.M)
    return m.group(1).strip() if m else ""

def order_key(path: Path) -> tuple[int, int, str]:
    text = path.read_text(errors="ignore")
    src = field(text, "reingest_source")
    generated = field(text, "generated_at")
    m = re.match(r"^(\d{8}T\d{6}Z)(?:-(\d+))?$", generated)
    n = int(m.group(2) or "1") if m else 999999
    non_pdf = 0 if src.lower().endswith(".pdf") else 1
    return (non_pdf, n, path.name)

def source_exists(source: str) -> bool:
    if not source:
        return False
    source_path = Path(source).expanduser()
    if source_path.is_absolute():
        return source_path.exists()
    candidates = (
        source_path,
        vault / source_path,
        vault / "_raw" / source_path,
        vault / "_raw" / "file-uploads" / source_path.name,
    )
    return any(path.exists() for path in candidates)

items = []
for path in root.glob("wiki-paper-reingest-*.md"):
    try:
        text = path.read_text(errors="ignore")
    except OSError:
        continue
    if field(text, "type") != "wiki-dispatch":
        continue
    if field(text, "action") != "paper-reingest":
        continue
    if field(text, "status") not in ("", "pending", "dispatched"):
        continue
    if not source_exists(field(text, "reingest_source")):
        continue
    items.append(path)

for path in sorted(items, key=order_key):
    print(path)
    break
PY
}

pane_has_running_dispatch() {
  local target="$1"
  python3 - "$DISPATCH_DIR" "$target" <<'PY'
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
target = sys.argv[2]

def field(text: str, name: str) -> str:
    m = re.search(rf"^{re.escape(name)}:\s*(.*)$", text, re.M)
    return m.group(1).strip() if m else ""

for path in root.glob("wiki-paper-reingest-*.md"):
    try:
        text = path.read_text(errors="ignore")
    except OSError:
        continue
    if field(text, "action") == "paper-reingest" and field(text, "status") == "running" and field(text, "target_pane") == target:
        sys.exit(0)
sys.exit(1)
PY
}

run_once() {
  local pane target file sent=0
  for pane in $REINGEST_PANES; do
    target="${LAB_SESSION}:0.${pane}"
    _bridge_pane_exists "$target" || continue
    _bridge_pane_idle "$target" || continue
    pane_has_running_dispatch "$target" && continue
    file="$(next_pending_reingest)"
    [[ -n "$file" ]] || break
    if cmd_wiki_run_dispatch "$file" --pane "$target"; then
      sent=$((sent + 1))
      sleep 0.5
    fi
  done
  echo "sent=${sent}"
}

status() {
  python3 - "$DISPATCH_DIR" <<'PY'
import json
import re
from pathlib import Path
import sys

root = Path(sys.argv[1])
counts = {}
for path in root.glob("wiki-paper-reingest-*.md"):
    text = path.read_text(errors="ignore")
    if not re.search(r"^action:\s*paper-reingest\s*$", text, re.M):
        continue
    m = re.search(r"^status:\s*(.*)$", text, re.M)
    status = m.group(1).strip() if m else "no_status"
    counts[status] = counts.get(status, 0) + 1
print(json.dumps({"dispatch_dir": str(root), "counts": counts}, ensure_ascii=False, indent=2))
PY
}

case "${1:-run-once}" in
  run-once)
    run_once
    ;;
  loop)
    interval="${2:-60}"
    while :; do
      run_once || true
      sleep "$interval"
    done
    ;;
  status)
    status
    ;;
  *)
    echo "Usage: $0 [run-once|loop [interval]|status]" >&2
    exit 1
    ;;
esac
