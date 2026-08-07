#!/usr/bin/env bash
# Regression: KB probe failures must not write remediation text into live panes.
set -euo pipefail

HARNESS_DIR_REAL="${HARNESS_DIR:-$HOME/.solar/harness}"
TMPDIR_TEST=$(mktemp -d)
trap 'rm -rf "$TMPDIR_TEST"' EXIT

mkdir -p "$TMPDIR_TEST"/{events,run,run/queue,run/pane-leases,sprints,state,tests,tools,bin,lib}
cp "$HARNESS_DIR_REAL/tools/solar-autopilot-monitor.py" "$TMPDIR_TEST/tools/solar-autopilot-monitor.py"
touch "$TMPDIR_TEST/events/all.jsonl"

cat > "$TMPDIR_TEST/tests/test-knowledge-probe-coverage.sh" <<'EOF'
#!/usr/bin/env bash
echo "PROBES_PASSED=8 PROBES_FAILED=2"
exit 1
EOF
chmod +x "$TMPDIR_TEST/tests/test-knowledge-probe-coverage.sh"

cat > "$TMPDIR_TEST/bin/tmux" <<'EOF'
#!/usr/bin/env bash
echo "$@" >> "$HARNESS_DIR/tmux-calls.log"
case "$1" in
  capture-pane)
    printf '────────────────\n❯ \n  ⏵⏵ auto mode on\n'
    exit 0
    ;;
  send-keys)
    exit 0
    ;;
  *)
    exit 0
    ;;
esac
EOF
chmod +x "$TMPDIR_TEST/bin/tmux"

OUT=$(PATH="$TMPDIR_TEST/bin:$PATH" HARNESS_DIR="$TMPDIR_TEST" SOLAR_HARNESS_SESSION="solar-harness-test" SOLAR_KB_PROBE_INTERVAL_SEC=0 python3 "$TMPDIR_TEST/tools/solar-autopilot-monitor.py" --apply --dispatch --json --cooldown 0)

if [[ "$OUT" != *'"action": "knowledge_probe_failed"'* ]]; then
  echo "FAIL: knowledge_probe_failed action missing"
  echo "$OUT"
  exit 1
fi
if [[ "$OUT" != *'"recorded_only": true'* ]]; then
  echo "FAIL: knowledge_probe_failed was not recorded_only"
  echo "$OUT"
  exit 1
fi
if grep -q 'send-keys' "$TMPDIR_TEST/tmux-calls.log" 2>/dev/null; then
  echo "FAIL: KB probe failure dispatched to pane"
  cat "$TMPDIR_TEST/tmux-calls.log"
  exit 1
fi

echo "PASS: KB probe failure recorded without pane dispatch"
