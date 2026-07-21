#!/usr/bin/env bash
set -euo pipefail

HARNESS_DIR_SRC="${HARNESS_DIR_SRC:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
NIGHTWATCH="$HARNESS_DIR_SRC/tools/solar-product-platform-nightwatch.sh"

tmp="$(mktemp -d /tmp/solar-nightwatch-pane-role-guard.XXXXXX)"
trap 'rm -rf "$tmp"' EXIT

mkdir -p "$tmp/bin" "$tmp/harness/sprints" "$tmp/harness/run" "$tmp/harness/state"

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
    case "$target" in
      solar-harness:0.2) printf 'solar-harness\tBuilder 主建设者 | 模型:Opus\n' ;;
      solar-harness:0.3) printf 'solar-harness\tPM 产品经理 | 模型:Opus\n' ;;
      *) exit 1 ;;
    esac
    ;;
  capture-pane)
    printf 'Claude Code\n❯\n? for shortcuts\nbypass permissions\n'
    ;;
  send-keys)
    printf '%s\n' "$target" >> "${TMUX_SEND_KEYS_LOG:?}"
    ;;
esac
STUB
chmod +x "$tmp/bin/tmux"

cat > "$tmp/harness/sprints/sprint-20260509-solar-product-platform.status.json" <<'JSON'
{
  "id": "sprint-20260509-solar-product-platform",
  "phase": "s0_ready_for_eval",
  "handoff_to": "evaluator",
  "updated_at": "2026-05-18T00:00:00Z"
}
JSON

touch "$tmp/harness/sprints/sprint-20260509-solar-product-platform.s0-handoff.md"

export PATH="$tmp/bin:$PATH"
export HARNESS_DIR="$tmp/harness"
export TMUX_SEND_KEYS_LOG="$tmp/send-keys.log"

bash "$NIGHTWATCH" 99 >"$tmp/nightwatch.out" 2>"$tmp/nightwatch.err" &
pid=$!
sleep 1
if ! kill -0 "$pid" 2>/dev/null; then
  echo "nightwatch exited before test timeout" >&2
  cat "$tmp/nightwatch.err" >&2 || true
  exit 1
fi
kill "$pid" 2>/dev/null || true
wait "$pid" 2>/dev/null || true

grep -q "expected_role=evaluator reason=role_mismatch" "$tmp/harness/run/product-platform-nightwatch.log" || {
  echo "missing evaluator role mismatch log" >&2
  cat "$tmp/harness/run/product-platform-nightwatch.log" >&2
  exit 1
}

if [[ -f "$TMUX_SEND_KEYS_LOG" ]]; then
  echo "nightwatch sent keys despite evaluator pane mismatch" >&2
  cat "$TMUX_SEND_KEYS_LOG" >&2
  exit 1
fi

echo "PASS nightwatch rejects role-mismatched panes"
