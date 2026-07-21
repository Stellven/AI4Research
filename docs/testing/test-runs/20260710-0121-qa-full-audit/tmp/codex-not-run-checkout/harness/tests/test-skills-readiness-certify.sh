#!/usr/bin/env bash
# Verify skills readiness/certify classify capabilities without overclaiming.
set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TEST"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

python3 -m py_compile "$HARNESS_DIR/lib/solar_skills.py" || fail "solar_skills.py does not compile"
bash -n "$HARNESS_DIR/solar-harness.sh" || fail "solar-harness.sh syntax failed"
pass "syntax checks"

"$HARNESS_DIR/solar-harness.sh" skills readiness --json > "$TMPDIR_TEST/readiness.json"
python3 - "$TMPDIR_TEST/readiness.json" <<'PY' || exit 1
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
core = {item["name"]: item["level"] for item in d.get("core", [])}
required = {
    "solar-harness-runtime",
    "solar-intent-engine",
    "solar-activation-proof",
    "solar-graph-scheduler",
    "solar-model-routing",
    "solar-knowledge-ingest",
    "solar-autopilot-monitor",
}
missing = sorted(required - set(core))
if missing:
    raise SystemExit(f"missing core skills: {missing}")
if d.get("accepted_artifacts", {}).get("name") != "accepted-artifacts-knowledge-index":
    raise SystemExit("accepted artifacts readiness missing")
if "summary" not in d or "injectable" not in d["summary"]:
    raise SystemExit("readiness summary missing")
PY
pass "readiness reports 7 core skills plus accepted-artifacts gap"

"$HARNESS_DIR/solar-harness.sh" skills certify --json > "$TMPDIR_TEST/certify.json"
python3 - "$TMPDIR_TEST/certify.json" <<'PY' || exit 1
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
if d.get("probes_passed") != d.get("probes_total"):
    raise SystemExit(f"probe failure: {d.get('failed')}")
if d.get("probes_total") != 7:
    raise SystemExit(f"expected 7 probes, got {d.get('probes_total')}")
accepted = d.get("accepted_artifacts", {})
if accepted.get("level") != "effective":
    raise SystemExit(f"accepted artifacts not effective: {accepted}")
if int(accepted.get("evidence", {}).get("indexed_in_vault", 0)) <= 0:
    raise SystemExit("accepted artifacts effective without indexed vault evidence")
PY
pass "certify runs 7 probes and proves accepted artifacts effective"

sqlite3 "$HARNESS_DIR/run/state.db" \
  "select count(*) from capability_scorecards where provider='solar-data-plane' and capability='accepted_artifacts.indexed_in_vault';" \
  | grep -qx '[1-9][0-9]*' || fail "accepted artifact scorecard missing"
pass "accepted artifacts scorecard written"

DISPATCH="$TMPDIR_TEST/dispatch.md"
cat > "$DISPATCH" <<'DISPATCH_EOF'
# Dispatch

solar-harness intent engine graph scheduler model routing knowledge ingest autopilot monitor activation proof accepted artifacts
DISPATCH_EOF
"$HARNESS_DIR/solar-harness.sh" skills inject "$DISPATCH" >/tmp/skills-readiness-inject.log
for provider in \
  solar-intent-engine \
  solar-activation-proof \
  solar-graph-scheduler \
  solar-model-routing \
  solar-knowledge-ingest \
  solar-autopilot-monitor
do
  grep -q "$provider" "$DISPATCH" || fail "provider not injected: $provider"
done
grep -q "Readiness:" "$DISPATCH" || fail "readiness line missing from dispatch"
pass "dispatch shows selected providers with readiness lines"

echo "PROBES_PASSED=5 PROBES_FAILED=0"
