#!/usr/bin/env bash
# test-intent-telemetry-audit.sh — verify intent telemetry sidecar + audit.
set -euo pipefail

HARNESS_DIR_REAL="$(cd "$(dirname "$0")/.." && pwd)"
SKILLS_PY="$HARNESS_DIR_REAL/lib/solar_skills.py"
INTENT_PY="$HARNESS_DIR_REAL/lib/intent_engine_adapter.py"
TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TEST"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

DISPATCH="$TMPDIR_TEST/dispatch.md"
cat > "$DISPATCH" <<'EOF'
# Dispatch

赶紧继续修复：用系统化调试排查 browser-use localhost screenshot 问题。
EOF

python3 "$SKILLS_PY" inject "$DISPATCH" >/dev/null || fail "skills inject failed"
SIDECAR="$DISPATCH.intent.json"
[[ -s "$SIDECAR" ]] || fail "intent telemetry sidecar missing"

python3 - "$SIDECAR" <<'PY' || exit 1
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
assert data["schema_version"] == 1
assert data["intent"]["matched"] is True
assert data["worker_visible"]["solar_intent_context"] is True
assert data["worker_visible"]["solar_capability_context"] is True
providers = [c["provider"] for c in data["capabilities"]]
assert "Browser-use MCP" in providers
assert "Superpowers" in providers
PY

pass "skills inject writes intent telemetry sidecar"

SUMMARY="$(python3 "$INTENT_PY" summarize "$DISPATCH")"
grep -q "Solar能力:" <<<"$SUMMARY" || fail "visibility summary missing Solar能力 prefix"
grep -q "systematic-debugging" <<<"$SUMMARY" || fail "visibility summary missing intent skill"
grep -q "Browser-use MCP" <<<"$SUMMARY" || fail "visibility summary missing capability provider"

TITLE="$(python3 "$INTENT_PY" summarize "$DISPATCH" --title)"
grep -q "I:" <<<"$TITLE" || fail "visibility title missing intent segment"
grep -q "C:" <<<"$TITLE" || fail "visibility title missing capability segment"

pass "intent summarize produces pane-visible text and title"

FAKE_HARNESS="$TMPDIR_TEST/harness"
FAKE_SPRINTS="$FAKE_HARNESS/sprints"
mkdir -p "$FAKE_SPRINTS"
SID="sprint-20260512-intent-audit-test"
cp "$SIDECAR" "$FAKE_SPRINTS/$SID.dispatch.md.intent.json"
cat > "$FAKE_SPRINTS/$SID.handoff.md" <<'EOF'
# Handoff

使用 Superpowers systematic-debugging，并通过 Browser-use MCP 复现 localhost screenshot。
EOF
cat > "$FAKE_SPRINTS/$SID.status.json" <<'EOF'
{"id":"sprint-20260512-intent-audit-test","status":"passed","phase":"eval_passed"}
EOF

AUDIT="$(HARNESS_DIR="$FAKE_HARNESS" python3 "$INTENT_PY" audit --sid "$SID" --json --write)"
AUDIT_JSON="$AUDIT" python3 - <<'PY' || exit 1
import json, os
data = json.loads(os.environ["AUDIT_JSON"])
assert data["ok"] is True
assert data["total"] == 1
assert data["worker_used"] == 1
assert data["rows"][0]["effect"]["status"] == "used_and_passed"
PY

grep -q '"status": "used_and_passed"' "$FAKE_SPRINTS/$SID.dispatch.md.intent.json" \
  || fail "audit did not write effect status to sidecar"

pass "intent audit detects worker usage and passed effect"
echo "PROBES_PASSED=3 PROBES_FAILED=0"
