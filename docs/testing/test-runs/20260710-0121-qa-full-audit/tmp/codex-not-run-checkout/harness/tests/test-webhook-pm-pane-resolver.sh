#!/usr/bin/env bash
set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
WEBHOOK="$HARNESS_DIR/webhook-server.ts"

fail() {
  echo "FAIL $*" >&2
  exit 1
}

grep -q "function captureRawIntent" "$WEBHOOK" || fail "missing RawIntent capture helper"
grep -q "intent_gateway.py" "$WEBHOOK" || fail "webhook does not call intent_gateway.py"
grep -q "POST /intent or /mobile" "$WEBHOOK" || fail "missing native /intent or /mobile RawIntent route"
grep -q "github_webhook" "$WEBHOOK" || fail "GitHub webhook is not captured as RawIntent"

if grep -q "function notifyPmPane" "$WEBHOOK"; then
  fail "webhook still contains PM pane notifier"
fi
if grep -q "send-keys" "$WEBHOOK"; then
  fail "webhook still sends natural language to pane"
fi
if grep -q "function createSprint" "$WEBHOOK"; then
  fail "webhook still creates sprints directly"
fi

echo "PASS webhook captures RawIntent without direct pane/task dispatch"
