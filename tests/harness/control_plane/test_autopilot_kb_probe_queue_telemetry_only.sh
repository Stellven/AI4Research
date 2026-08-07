#!/usr/bin/env bash
# Regression: stale KB probe telemetry must be dropped from autopilot queue,
# never replayed into the PM pane.
set -euo pipefail

HARNESS_DIR_REAL="${HARNESS_DIR:-$HOME/.solar/harness}"
TMPDIR_TEST=$(mktemp -d)
trap 'rm -rf "$TMPDIR_TEST"' EXIT

mkdir -p "$TMPDIR_TEST"/{events,run,run/queue,run/pane-leases,sprints,state,tests,tools,bin,lib}
cp "$HARNESS_DIR_REAL/tools/solar-autopilot-monitor.py" "$TMPDIR_TEST/tools/solar-autopilot-monitor.py"
touch "$TMPDIR_TEST/events/all.jsonl"

cat > "$TMPDIR_TEST/run/autopilot-queue.jsonl" <<'EOF'
{"ts":"2026-05-13T00:00:00Z","created_at_epoch":9999999999,"sid":"","type":"knowledge_probe_failed","target":"solar-harness-test:0.0","message":"KB probe failed should not reach pane","reason":"pane_busy","detail":{},"attempts":0}
EOF

cat > "$TMPDIR_TEST/tests/test-knowledge-probe-coverage.sh" <<'EOF'
#!/usr/bin/env bash
echo "PROBES_PASSED=10 PROBES_FAILED=0"
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

OUT=$(PATH="$TMPDIR_TEST/bin:$PATH" HARNESS_DIR="$TMPDIR_TEST" SOLAR_HARNESS_SESSION="solar-harness-test" SOLAR_KB_PROBE_INTERVAL_SEC=999999 python3 "$TMPDIR_TEST/tools/solar-autopilot-monitor.py" --apply --dispatch --json --cooldown 0)

if [[ "$OUT" != *'"dropped": "telemetry_only"'* ]]; then
  echo "FAIL: stale KB probe queue item was not dropped"
  echo "$OUT"
  exit 1
fi
if grep -q 'send-keys' "$TMPDIR_TEST/tmux-calls.log" 2>/dev/null; then
  echo "FAIL: stale KB probe queue item dispatched to pane"
  cat "$TMPDIR_TEST/tmux-calls.log"
  exit 1
fi
if [[ -s "$TMPDIR_TEST/run/autopilot-queue.jsonl" ]]; then
  echo "FAIL: stale KB probe queue item retained"
  cat "$TMPDIR_TEST/run/autopilot-queue.jsonl"
  exit 1
fi

echo "PASS: stale KB probe queue telemetry dropped without pane dispatch"
