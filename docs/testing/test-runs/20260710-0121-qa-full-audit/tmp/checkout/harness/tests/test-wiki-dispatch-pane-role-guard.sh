#!/usr/bin/env bash
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
BRIDGE="$HARNESS_DIR/integrations/obsidian-wiki-bridge.sh"

tmp="$(mktemp -d /tmp/solar-wiki-pane-role-guard.XXXXXX)"
trap 'rm -rf "$tmp"' EXIT

mkdir -p "$tmp/bin" "$tmp/vault"

cat > "$tmp/bin/tmux" <<'STUB'
#!/usr/bin/env bash
cmd="${1:-}"
shift || true

target=""
format=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -p) shift ;;
    -t) target="${2:-}"; shift 2 ;;
    *) format="$1"; shift ;;
  esac
done

case "$cmd" in
  display-message)
    if [[ "$format" == '#{pane_id}' ]]; then
      echo "%1"
      exit 0
    fi
    case "$target" in
      solar-harness:0.0) printf 'solar-harness\tPM 产品经理 | 模型:Opus\n' ;;
      solar-harness:0.2) printf 'solar-harness\tBuilder 主建设者 | 模型:Opus\n' ;;
      solar-harness-lab:0.0) printf 'solar-harness-lab\tBuilder 1 | 模型:GLM\n' ;;
      *) exit 1 ;;
    esac
    ;;
  capture-pane)
    printf 'Claude Code\n❯\n? for shortcuts\nbypass permissions\n'
    ;;
  has-session)
    exit 0
    ;;
  *)
    exit 0
    ;;
esac
STUB
chmod +x "$tmp/bin/tmux"

export PATH="$tmp/bin:$PATH"
export OBSIDIAN_VAULT_PATH="$tmp/vault"

dispatch="$tmp/wiki-dispatch.md"
cat > "$dispatch" <<'EOF'
---
type: wiki-dispatch
action: ingest
skill: wiki-ingest
status: pending
---

# Test dispatch
EOF

# shellcheck disable=SC1090
source "$BRIDGE"

if cmd_wiki_run_dispatch "$dispatch" --pane solar-harness:0.0 --dry-run >"$tmp/pm.out" 2>"$tmp/pm.err"; then
  echo "PM pane was accepted as a wiki dispatch target" >&2
  exit 1
fi

grep -q "target pane is not a builder pane" "$tmp/pm.err" || {
  echo "missing non-builder pane guard error" >&2
  cat "$tmp/pm.err" >&2
  exit 1
}

cmd_wiki_run_dispatch "$dispatch" --pane solar-harness-lab:0.0 --dry-run >"$tmp/lab.out"
grep -q "target_pane=solar-harness-lab:0.0" "$tmp/lab.out" || {
  echo "lab builder pane was not accepted" >&2
  cat "$tmp/lab.out" >&2
  exit 1
}

cmd_wiki_run_dispatch "$dispatch" --pane solar-harness:0.2 --dry-run >"$tmp/main.out"
grep -q "target_pane=solar-harness:0.2" "$tmp/main.out" || {
  echo "main builder pane was not accepted" >&2
  cat "$tmp/main.out" >&2
  exit 1
}

echo "PASS wiki dispatch rejects non-builder panes"
