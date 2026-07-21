#!/usr/bin/env bash
# verify-runtime-session.sh — CI-safe runtime verification gate. Drives the REAL engine dispatch
# path with a DETERMINISTIC fake operator (NO live Claude/Codex/GLM), fully isolated under /tmp,
# and proves: sandbox root used -> envelope created -> fake operator consumes it -> result written
# -> artifact non-empty -> status-server surfaces the session/result -> real ~/.solar untouched.
#
#   bash scripts/verify-runtime-session.sh
#
# A missing dependency is NOT VERIFIED (counts as FAIL), never a silent skip/PASS.
set -u
repo="$(cd "$(dirname "$0")/.." && pwd)"
pass=0; fail=0
PASS(){ printf '  PASS     %s\n' "$1"; pass=$((pass + 1)); }
FAIL(){ printf '  FAIL     %s\n' "$1"; fail=$((fail + 1)); }
NV(){   printf '  NOT-VER  %s\n' "$1"; fail=$((fail + 1)); }

echo "== runtime session verification (fake operator, no LLM) =="
command -v python3 >/dev/null || { NV "python3 not on PATH"; echo "RUNTIME SESSION GATE: RED"; exit 1; }

# Isolation is proven by checking this run's UNIQUE outputs never land under the real home. A
# whole-tree ~/.solar snapshot is unreliable here: a live Solar runtime / background daemons write
# to ~/.solar constantly, so a hash diff false-positives on unrelated churn.
REAL_SOLAR="$HOME/.solar"

SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/solar-rt-e2e.XXXXXX")"
trap 'rm -rf "$SANDBOX"' EXIT
export HOME="$SANDBOX/home"
export HARNESS_DIR="$HOME/.solar/harness"   # sandbox root, inside the sandbox HOME (NOT real ~)
mkdir -p "$HARNESS_DIR"/{config,run,sprints,events,sessions,reports,actors}
export FAKE_SPRINT_ID="fakeop-sprint-$$"
export FAKE_ACTOR_ID="op.fake.test.01"
export SOLAR_FAKE_OPERATOR=1
export SOLAR_BIND_HOST=127.0.0.1
export SOLAR_DB="$HARNESS_DIR/solar.db"
export PYTHONPATH="$repo/harness/lib"

# ── 1. REAL dispatch (ActorRuntime.submit) + deterministic fake operator ──────
OUT="$SANDBOX/e2e.json"
if python3 "$repo/harness/tests/runtime_session_e2e.py" >"$OUT" 2>"$SANDBOX/e2e.err"; then
  PASS "engine driver ran: real submit -> lease/scheduler/envelope/evidence -> fake operator -> result/artifact/event"
else
  FAIL "engine driver failed"; sed 's/^/      /' "$SANDBOX/e2e.err" | tail -6
fi
field(){ python3 -c "import json;print(json.load(open('$OUT')).get('$1',''))" 2>/dev/null; }
SID="$(field sprint_id)"; MARKER="$(field marker)"; DELIV="$(field deliverable)"; ALLPASS="$(field all_pass)"
if [ "$ALLPASS" = "True" ]; then
  PASS "all engine steps green (submit/lease/scheduler/inbox-envelope/evidence-ledger/consume/result/artifact/event/isolation)"
else
  FAIL "engine steps not all green: $(python3 -c "import json;print([k for k,v in json.load(open('$OUT')).get('steps',{}).items() if not v])" 2>/dev/null)"
fi

# ── 2. artifact exists + non-empty (independent re-check) ─────────────────────
if [ -n "$DELIV" ] && [ -s "$DELIV" ]; then PASS "deliverable artifact exists + non-empty ($(wc -c <"$DELIV") bytes)"; else FAIL "deliverable missing/empty"; fi

# ── 3. sandbox HARNESS_DIR used (outputs not in real home) ────────────────────
case "$DELIV" in "$HARNESS_DIR"/*) PASS "sandbox HARNESS_DIR used for outputs" ;; *) FAIL "outputs not under sandbox HARNESS_DIR ($DELIV)" ;; esac

# ── 4. status-server surfaces the new session/result ──────────────────────────
python3 "$repo/harness/lib/symphony/status-server.py" >/dev/null 2>"$SANDBOX/ss.err" &
SS_PID=$!
SURFACED="$(python3 - "$HARNESS_DIR/run/status-server.port" "$SID" "$MARKER" <<'PY'
import sys, time, urllib.request
port_file, sid, marker = sys.argv[1], sys.argv[2], sys.argv[3]
deadline = time.time() + 20
while time.time() < deadline:
    try:
        port = int(open(port_file).read().strip())
    except Exception:
        time.sleep(0.25); continue
    for ep in (f"/events?limit=20&sprint_id={sid}", f"/status?sprint_id={sid}"):
        try:
            body = urllib.request.urlopen(f"http://127.0.0.1:{port}{ep}", timeout=3).read().decode("utf-8", "replace")
            if marker and marker in body:
                print("YES"); sys.exit(0)
        except Exception:
            pass
    time.sleep(0.25)
print("NO")
PY
)"
kill "$SS_PID" 2>/dev/null; wait "$SS_PID" 2>/dev/null
if [ "$SURFACED" = "YES" ]; then PASS "status-server surfaces the new session/result (marker $MARKER in /events|/status)"; else FAIL "status-server did NOT surface the result (marker $MARKER)"; fi

# ── 5. real ~/.solar has NONE of this run's unique outputs (precise isolation proof) ──
RH="$REAL_SOLAR/harness"
leak=""
for p in "$RH/sprints/$FAKE_SPRINT_ID" "$RH/sessions/$FAKE_SPRINT_ID" "$RH/run/actor-evidence/$FAKE_SPRINT_ID.jsonl"; do
  [ -e "$p" ] && leak="$leak $p"
done
if [ -z "$leak" ]; then PASS "real ~/.solar has none of this run's unique outputs (isolation held)"; else FAIL "isolation breach — found under real home:$leak"; fi

echo
echo "================================"
echo "PASS=$pass  FAIL=$fail"
echo "UNVERIFIED by design (label): tmux pane dispatch (graph_node_dispatcher), operatord daemon,"
echo "  real Claude/Codex/GLM execution, multi-node DAG advance, crash/restart recovery, concurrent live tasks."
if [ "$fail" -eq 0 ]; then echo "RUNTIME SESSION GATE: GREEN"; exit 0; else echo "RUNTIME SESSION GATE: RED"; exit 1; fi
