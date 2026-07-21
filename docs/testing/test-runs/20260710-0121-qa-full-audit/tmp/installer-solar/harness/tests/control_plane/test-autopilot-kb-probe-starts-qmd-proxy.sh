#!/usr/bin/env bash
# Regression: KB probe should best-effort heal QMD MCP IPv4 reachability first.
set -euo pipefail

HARNESS_DIR_REAL="${HARNESS_DIR:-$HOME/.solar/harness}"
TMPDIR_TEST=$(mktemp -d)
trap 'rm -rf "$TMPDIR_TEST"' EXIT

mkdir -p "$TMPDIR_TEST"/{events,run,run/queue,run/pane-leases,sprints,state,tests,tools,bin,lib}
cp "$HARNESS_DIR_REAL/tools/solar-autopilot-monitor.py" "$TMPDIR_TEST/tools/solar-autopilot-monitor.py"
touch "$TMPDIR_TEST/events/all.jsonl"

cat > "$TMPDIR_TEST/solar-harness.sh" <<'EOF'
#!/usr/bin/env bash
echo "$*" >> "$HARNESS_DIR/qmd-heal-calls.log"
if [[ "$*" == "wiki qmd-mcp start" ]]; then
  echo "[Harness] qmd MCP IPv4 proxy running -> 127.0.0.1:8181 -> ::1:8181"
  exit 0
fi
exit 1
EOF
chmod +x "$TMPDIR_TEST/solar-harness.sh"

cat > "$TMPDIR_TEST/tests/test-knowledge-probe-coverage.sh" <<'EOF'
#!/usr/bin/env bash
echo "ok - probe"
echo "PROBES_PASSED=10 PROBES_FAILED=0"
EOF
chmod +x "$TMPDIR_TEST/tests/test-knowledge-probe-coverage.sh"

cat > "$TMPDIR_TEST/bin/tmux" <<'EOF'
#!/usr/bin/env bash
case "$1" in
  capture-pane)
    printf '────────────────\n❯ \n  ⏵⏵ auto mode on\n'
    exit 0
    ;;
  *)
    exit 0
    ;;
esac
EOF
chmod +x "$TMPDIR_TEST/bin/tmux"

OUT=$(PATH="$TMPDIR_TEST/bin:$PATH" HARNESS_DIR="$TMPDIR_TEST" SOLAR_HARNESS_SESSION="solar-harness-test" SOLAR_KB_PROBE_INTERVAL_SEC=0 python3 "$TMPDIR_TEST/tools/solar-autopilot-monitor.py" --apply --json --cooldown 0)

if ! grep -q 'wiki qmd-mcp start' "$TMPDIR_TEST/qmd-heal-calls.log"; then
  echo "FAIL: autopilot did not start qmd IPv4 proxy before KB probe"
  echo "$OUT"
  exit 1
fi
if ! grep -q '"ok": true' "$TMPDIR_TEST/state/qmd-mcp-ipv4-health.json"; then
  echo "FAIL: qmd IPv4 health was not recorded as ok"
  cat "$TMPDIR_TEST/state/qmd-mcp-ipv4-health.json"
  exit 1
fi
if ! grep -q '"ok": true' "$TMPDIR_TEST/state/knowledge-probe-health.json"; then
  echo "FAIL: KB probe health was not recorded as ok"
  cat "$TMPDIR_TEST/state/knowledge-probe-health.json"
  exit 1
fi

echo "PASS: KB probe starts qmd IPv4 proxy first"
