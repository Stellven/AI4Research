#!/usr/bin/env bash
# Regression: model registry doctor failures must be telemetry-only and must
# not dispatch remediation text into live panes.
set -euo pipefail

HARNESS_DIR_REAL="${HARNESS_DIR:-$HOME/.solar/harness}"
TMPDIR_TEST=$(mktemp -d)
trap 'rm -rf "$TMPDIR_TEST"' EXIT

mkdir -p "$TMPDIR_TEST"/{events,run,run/queue,run/pane-leases,sprints,state,tests,tools,bin,lib}
cp "$HARNESS_DIR_REAL/tools/solar-autopilot-monitor.py" "$TMPDIR_TEST/tools/solar-autopilot-monitor.py"
touch "$TMPDIR_TEST/events/all.jsonl"

cat > "$TMPDIR_TEST/solar-harness.sh" <<'EOF'
#!/usr/bin/env bash
if [[ "${1:-}" == "models" && "${2:-}" == "doctor" ]]; then
  echo "registry guard failed"
  exit 7
fi
exit 0
EOF
chmod +x "$TMPDIR_TEST/solar-harness.sh"

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

OUT=$(PATH="$TMPDIR_TEST/bin:$PATH" HARNESS_DIR="$TMPDIR_TEST" SOLAR_HARNESS_SESSION="solar-harness-test" SOLAR_KB_PROBE_INTERVAL_SEC=999999 SOLAR_MODEL_DOCTOR_INTERVAL_SEC=0 python3 "$TMPDIR_TEST/tools/solar-autopilot-monitor.py" --apply --dispatch --json --cooldown 0)

if [[ "$OUT" != *'"action": "model_registry_doctor_failed"'* ]]; then
  echo "FAIL: model_registry_doctor_failed action missing"
  echo "$OUT"
  exit 1
fi
if [[ "$OUT" != *'"recorded_only": true'* ]]; then
  echo "FAIL: model_registry_doctor_failed was not recorded_only"
  echo "$OUT"
  exit 1
fi
if grep -q 'send-keys' "$TMPDIR_TEST/tmux-calls.log" 2>/dev/null; then
  echo "FAIL: model doctor failure dispatched to pane"
  cat "$TMPDIR_TEST/tmux-calls.log"
  exit 1
fi
if [[ ! -s "$TMPDIR_TEST/state/model-registry-doctor-health.json" ]]; then
  echo "FAIL: model doctor health file missing"
  exit 1
fi

echo "PASS: model doctor failure recorded without pane dispatch"
