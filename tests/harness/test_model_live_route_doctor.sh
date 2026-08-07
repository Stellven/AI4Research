#!/usr/bin/env bash
# Regression: models doctor must fail when a live Opus pane is still routed to
# API Usage Billing or showing provider 1210 errors.
set -euo pipefail

HARNESS_DIR_REAL="${HARNESS_DIR:-$HOME/.solar/harness}"
TMPDIR_TEST=$(mktemp -d)
trap 'rm -rf "$TMPDIR_TEST"' EXIT

mkdir -p "$TMPDIR_TEST/home/.solar" "$TMPDIR_TEST/bin"
ln -s "$HARNESS_DIR_REAL" "$TMPDIR_TEST/home/.solar/harness"

cat > "$TMPDIR_TEST/bin/tmux" <<'EOF'
#!/usr/bin/env bash
case "$1" in
  has-session)
    exit 0
    ;;
  list-panes)
    printf '0 %%0\n1 %%1\n2 %%2\n3 %%3\n'
    exit 0
    ;;
  capture-pane)
    case "$*" in
      *solar-harness:0.2*)
        printf '▐▛███▜▌   Claude Code v2.1.112\n'
        printf '▝▜█████▛▘  Opus 4.7 · API Usage Billing\n'
        printf 'API Error: 400 {"error":{"code":"1210","message":"Invalid API parameter"}}\n'
        ;;
      *)
        printf '▝▜█████▛▘  Opus 4.7 · Claude Max\n'
        ;;
    esac
    exit 0
    ;;
  *)
    exit 0
    ;;
esac
EOF
chmod +x "$TMPDIR_TEST/bin/tmux"

set +e
OUT=$(PATH="$TMPDIR_TEST/bin:$PATH" HOME="$TMPDIR_TEST/home" "$HARNESS_DIR_REAL/solar-harness.sh" models doctor 2>&1)
RC=$?
set -e

if [[ "$RC" -eq 0 ]]; then
  echo "FAIL: models doctor passed despite live API Billing/1210 pane"
  echo "$OUT"
  exit 1
fi
if [[ "$OUT" != *"live pane route"* || "$OUT" != *"API Usage Billing"* || "$OUT" != *"1210"* ]]; then
  echo "FAIL: models doctor did not report live pane route evidence"
  echo "$OUT"
  exit 1
fi

STATUS_OUT=$(PATH="$TMPDIR_TEST/bin:$PATH" HOME="$TMPDIR_TEST/home" "$HARNESS_DIR_REAL/solar-harness.sh" main-status 2>&1)
if [[ "$STATUS_OUT" != *"route: error"* ]]; then
  echo "FAIL: main-status did not expose live route error"
  echo "$STATUS_OUT"
  exit 1
fi

echo "PASS: models doctor and main-status catch live Opus API Billing/1210 route"
