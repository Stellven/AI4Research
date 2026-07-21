#!/usr/bin/env bash
# Regression: ciembor/agent-rules-books is safely integrated as a vendor provider.
set -euo pipefail

HARNESS="${HARNESS_DIR:-$HOME/.solar/harness}"
BIN="$HARNESS/solar-harness.sh"
ADAPTER="$HARNESS/lib/agent_rules_books_adapter.py"
VENDOR="$HARNESS/vendor/agent-rules-books"
REPORT="$HARNESS/reports/agent-rules-books-inventory.json"
EFFECT_REPORT="$HARNESS/reports/agent-rules-books-effect-proof.json"
FIXTURE="$HARNESS/tests/fixtures/agent-rules-books-effect.dispatch.md"
TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TEST"' EXIT

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

bash -n "$BIN" "$ADAPTER" "$HARNESS/lib/external-integrations-health.py" "$HARNESS/lib/solar_skills.py" "$HARNESS/lib/intent_engine_adapter.py"
[[ -d "$VENDOR/.git" ]] || fail "vendor repo missing: $VENDOR"

doctor_json="$(python3 "$ADAPTER" doctor --json)"
python3 - "$doctor_json" <<'PY' || exit 1
import json, sys
d=json.loads(sys.argv[1])
assert d["ok"], d
assert d["counts"]["books"] == 14, d["counts"]
assert d["counts"]["mini"] == 14, d["counts"]
PY

python3 "$ADAPTER" report --json >/tmp/agent-rules-books-report.json
[[ -f "$REPORT" ]] || fail "inventory report missing"

intent="$("$BIN" intent match "重构这个遗留代码，按 Clean Code 和 Refactoring 做" 2>/dev/null)"
grep -q "agent-rules-books" <<<"$intent" || fail "intent did not route to agent-rules-books: $intent"

health="$(python3 "$HARNESS/lib/external-integrations-health.py" --json 2>/dev/null)"
grep -q "ciembor/agent-rules-books" <<<"$health" || fail "external health missing agent-rules-books"

cp "$FIXTURE" "$TMPDIR_TEST/effect.dispatch.md"
"$BIN" skills inject "$TMPDIR_TEST/effect.dispatch.md" >/tmp/agent-rules-books-effect-inject.log 2>&1
grep -q "hint agent-rules-books clean-code" "$TMPDIR_TEST/effect.dispatch.md" || fail "positive fixture did not expose agent-rules-books intent"
grep -q "agent-rules-books (rules.book_catalog" "$TMPDIR_TEST/effect.dispatch.md" || fail "positive fixture did not expose agent-rules-books capability"
python3 - "$TMPDIR_TEST/effect.dispatch.md.intent.json" <<'PY' || exit 1
import json, sys
d=json.load(open(sys.argv[1], encoding="utf-8"))
assert any(m.get("source") == "agent-rules-books" for m in d["intent"]["matches"]), d["intent"]
assert any(c.get("provider") == "agent-rules-books" for c in d["capabilities"]), d["capabilities"]
assert d["worker_visible"]["solar_intent_context"] is True, d["worker_visible"]
assert d["worker_visible"]["solar_capability_context"] is True, d["worker_visible"]
PY

python3 "$ADAPTER" prove --json > "$TMPDIR_TEST/prove.json"
python3 - "$TMPDIR_TEST/prove.json" <<'PY' || exit 1
import json, sys
d=json.load(open(sys.argv[1], encoding="utf-8"))
assert d["ok"], d
assert d["level"] == "effective", d
assert d["scorecards_written"] is True, d
pos=d["evidence"]["positive"]
neg=d["evidence"]["negative"]
assert "agent-rules-books" in pos["intent_sources"], pos
assert "agent-rules-books" in pos["capability_providers"], pos
assert neg["agent_rules_books_absent"] is True, neg
PY
[[ -f "$EFFECT_REPORT" ]] || fail "effect proof report missing"
sqlite3 "$HARNESS/run/state.db" \
  "select count(*) from capability_scorecards where provider='agent-rules-books' and capability='rules.book_catalog' and level='closed_loop';" \
  | grep -qx '[1-9][0-9]*' || fail "effective scorecard missing"

echo "PASS agent-rules-books integration and effect proof"
