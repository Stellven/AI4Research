#!/usr/bin/env bash
# Regression: `solar-harness bg` creates durable tmux-backed background tasks
# without requiring operators to remember tmux window commands.
set -euo pipefail
cd "$(dirname "$0")/.."

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP"/{bin,lib,sprints,personas,templates,run/bg-tasks,work}

cp solar-harness.sh "$TMP/solar-harness.sh"
cp lib/run-state.sh "$TMP/lib/run-state.sh"
cp lib/events.sh "$TMP/lib/events.sh"

python3 - "$TMP/solar-harness.sh" "$TMP" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
tmp = sys.argv[2]
s = p.read_text()
s = s.replace('HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"', f'HARNESS_DIR="${{HARNESS_DIR:-{tmp}}}"', 1)
p.write_text(s)
PY
chmod +x "$TMP/solar-harness.sh"

cat > "$TMP/bin/tmux" <<'EOF'
#!/usr/bin/env bash
echo "$@" >> "$HARNESS_DIR/tmux-calls.log"
case "$1" in
  has-session)
    exit 1
    ;;
  new-session|new-window|kill-window|select-window|attach|display-message)
    if [[ "$1" == "display-message" ]]; then
      echo "bg-window"
    fi
    exit 0
    ;;
  *)
    exit 0
    ;;
esac
EOF
chmod +x "$TMP/bin/tmux"

PATH="$TMP/bin:$PATH" HARNESS_DIR="$TMP" "$TMP/solar-harness.sh" bg --cwd "$TMP/work" "整理昨天的实验结果并生成摘要"

status_count=$(find "$TMP/run/bg-tasks" -name status.json | wc -l | tr -d ' ')
[[ "$status_count" -eq 1 ]] || { echo "FAIL: expected one bg status, got $status_count"; exit 1; }

task_dir=$(find "$TMP/run/bg-tasks" -mindepth 1 -maxdepth 1 -type d | head -1)
[[ -f "$task_dir/request.txt" ]] || { echo "FAIL: request.txt missing"; exit 1; }
[[ -f "$task_dir/runner.sh" ]] || { echo "FAIL: runner.sh missing"; exit 1; }
grep -q "整理昨天的实验结果" "$task_dir/request.txt" || { echo "FAIL: request text missing"; exit 1; }
grep -q "intake --request" "$task_dir/runner.sh" || { echo "FAIL: runner does not call intake"; exit 1; }
grep -q "new-session" "$TMP/tmux-calls.log" || { echo "FAIL: tmux new-session not called"; exit 1; }

PATH="$TMP/bin:$PATH" HARNESS_DIR="$TMP" "$TMP/solar-harness.sh" bg status | grep -q "bg-" \
  || { echo "FAIL: bg status did not list task"; exit 1; }

PATH="$TMP/bin:$PATH" HARNESS_DIR="$TMP" "$TMP/solar-harness.sh" bg run --cwd "$TMP/work" -- "echo hello"
cmd_file=$(find "$TMP/run/bg-tasks" -name command.sh | head -1)
cmd_dir=$(dirname "$cmd_file")
[[ -f "$cmd_dir/command.sh" ]] || { echo "FAIL: command.sh missing"; exit 1; }
grep -q "echo hello" "$cmd_dir/command.sh" || { echo "FAIL: command text missing"; exit 1; }

echo "PASS: bg entrypoint creates tmux-backed task records"
