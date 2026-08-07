#!/usr/bin/env bash
# Solar MIA runtime adapter tests.

set -uo pipefail
cd "$(dirname "$0")/.."
PASS=0; FAIL=0

ok() { echo "PASS: $*"; PASS=$((PASS+1)); }
fail() { echo "FAIL: $*"; FAIL=$((FAIL+1)); }

TMP_DIR="$(mktemp -d)"
SERVER_PID=""
cleanup() {
  if [[ -n "$SERVER_PID" ]]; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
  fi
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

PORT="$(python3 - <<'PY'
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
PY
)"

python3 - "$PORT" >"$TMP_DIR/fake-mia.log" 2>&1 <<'PY' &
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

port = int(sys.argv[1])

class Handler(BaseHTTPRequestHandler):
    def _json(self, payload, code=200):
        raw = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/hallo":
            self._json({"sussflu": "hallo"})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        data = json.loads(self.rfile.read(length) or b"[]")
        if self.path == "/memory":
            question = data[0].get("question", "") if data else ""
            self._json([{
                "context": "MIA_SENTINEL context for " + question,
                "pos_indices": [1],
                "neg_indices": [2],
            }])
        elif self.path == "/plan":
            self._json([{"plan": "MIA_PLAN_SENTINEL"}])
        else:
            self._json({"error": "not found"}, 404)

    def log_message(self, *args):
        pass

ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
PY
SERVER_PID=$!

python3 - "$PORT" <<'PY'
import socket
import sys
import time
port = int(sys.argv[1])
deadline = time.time() + 5
while time.time() < deadline:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            raise SystemExit(0)
    except OSError:
        time.sleep(0.05)
raise SystemExit(1)
PY
[[ $? -eq 0 ]] && ok "fake MIA server started" || fail "fake MIA server did not start"

python3 -m py_compile \
  lib/experience/mia_adapter.py \
  lib/experience/memory_serve_daemon.py \
  lib/experience/query.py \
  lib/experience/cli.py \
  lib/coordinator_hooks.py \
  && ok "MIA adapter files compile" \
  || fail "MIA adapter py_compile failed"

OUT=$(SOLAR_MIA_BASE_URL="http://127.0.0.1:$PORT" python3 lib/experience_runner.py mia-status --json 2>/dev/null)
echo "$OUT" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['adapter']['ok'] is True" \
  && ok "mia-status sees fake runtime" \
  || fail "mia-status failed: $OUT"

OUT=$(SOLAR_MIA_BASE_URL="http://127.0.0.1:$PORT" python3 lib/experience_runner.py query --text "queue block" --limit 2 --json 2>/dev/null)
echo "$OUT" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['ok'] is True; assert d['mia']['ok'] is True; assert 'MIA_SENTINEL' in d['mia']['context']; assert d['backend']=='mia+sqlite_fts'" \
  && ok "experience query uses MIA when available" \
  || fail "experience query did not use MIA: $OUT"

OUT=$(SOLAR_MIA_BASE_URL="http://127.0.0.1:$PORT" python3 lib/experience_runner.py mia-query "dispatch queue block" --json 2>/dev/null)
echo "$OUT" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['ok'] is True; assert 'MIA_SENTINEL' in d['context']" \
  && ok "mia-query direct call works" \
  || fail "mia-query failed: $OUT"

OUT=$(SOLAR_MIA_BASE_URL="http://127.0.0.1:9" SOLAR_MIA_TIMEOUT_SEC=0.05 python3 lib/experience_runner.py query --text "queue block" --limit 2 --json 2>/dev/null)
echo "$OUT" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['ok'] is True; assert d['backend']=='sqlite_fts'; assert d['mia']['ok'] is False" \
  && ok "MIA unavailable falls back to SQLite" \
  || fail "MIA fallback failed: $OUT"

OUT=$(SOLAR_MIA_BASE_URL="http://127.0.0.1:$PORT" python3 - <<'PY'
import os
import sys
sys.path.insert(0, os.path.abspath("lib"))
from experience.query import query_for_sprint
result = query_for_sprint("sprint-nonexistent-mia-test", include_mia=False)
print("mia" in result)
PY
)
[[ "$OUT" == "False" ]] \
  && ok "coordinator-safe query can disable MIA" \
  || fail "include_mia=False still called MIA: $OUT"

VENDOR_STATUS=$(git -C vendor/MIA status --porcelain 2>/dev/null || true)
[[ -z "$VENDOR_STATUS" ]] \
  && ok "vendored MIA tree remains unmodified" \
  || fail "vendored MIA tree dirty: $VENDOR_STATUS"

# -------------------------------------------------------------------------
# Native runtime readiness
# -------------------------------------------------------------------------
VENV_PY="venvs/mia-memory-serve/bin/python3"

[[ -x "$VENV_PY" ]] \
  && ok "native venv python exists" \
  || fail "venv not found: $VENV_PY"

BERT_PATH="~/.cache/huggingface/hub/models--sentence-transformers--all-MiniLM-L6-v2/snapshots/c9745ed1d9f207416be6d2e6f8de32d1f16199bf"
[[ -d "$BERT_PATH" ]] \
  && ok "BERT model cache present ($BERT_PATH)" \
  || fail "BERT model cache missing: $BERT_PATH"

"$VENV_PY" -c "import flask" 2>/dev/null \
  && ok "flask importable in venv" \
  || fail "flask missing from venv"

"$VENV_PY" -c "import torch, transformers, openai" 2>/dev/null \
  && ok "heavy deps inherited in venv (torch, transformers, openai)" \
  || fail "heavy deps not inherited in venv"

[[ -f "lib/experience/memory_functions.py" ]] \
  && ok "memory_functions shim exists" \
  || fail "memory_functions shim missing"

[[ -f "lib/experience/memory_serve_wrapper.py" ]] \
  && ok "memory_serve_wrapper.py exists" \
  || fail "memory_serve_wrapper.py missing"

# Dependency reporting via daemon
DEP_OUT=$(python3 lib/experience_runner.py mia-status --json 2>/dev/null)
echo "$DEP_OUT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
deps = d.get('dependencies', {})
assert deps.get('venv_ok') is True, f'venv_ok not True: {deps}'
assert deps.get('bert_ok') is True, f'bert_ok not True: {deps}'
assert deps.get('missing_python_modules') == [], f'missing modules: {deps}'
assert deps.get('missing_files') == [], f'missing files: {deps}'
" && ok "dependency reporting: venv_ok=true, bert_ok=true, no missing" \
  || fail "dependency reporting failed: $DEP_OUT"

# -------------------------------------------------------------------------
# Native runtime startup (server already running from earlier in this run)
# -------------------------------------------------------------------------
NATIVE_PID_FILE="run/mia-memory-serve.pid"
NATIVE_PORT=5197

# Start if not already running
if ! curl -s "http://127.0.0.1:${NATIVE_PORT}/hallo" > /dev/null 2>&1; then
  lsof -ti ":${NATIVE_PORT}" | xargs kill -9 2>/dev/null || true
  sleep 0.5
  MIA_BERT_PATH="$BERT_PATH" \
    "$VENV_PY" lib/experience/memory_serve_wrapper.py --host 127.0.0.1 --port "$NATIVE_PORT" \
    >> run/mia-memory-serve.log 2>&1 &
  NATIVE_SRV_PID=$!
  echo "$NATIVE_SRV_PID" > "$NATIVE_PID_FILE"
  # Wait up to 30s for native server
  STARTED=0
  for i in $(seq 1 30); do
    curl -s "http://127.0.0.1:${NATIVE_PORT}/hallo" > /dev/null 2>&1 && STARTED=1 && break
    sleep 1
  done
  [[ "$STARTED" -eq 1 ]] \
    && ok "native server started on 127.0.0.1:${NATIVE_PORT}" \
    || { fail "native server failed to start within 30s"; }
else
  ok "native server already running on port ${NATIVE_PORT}"
fi

# mia-status with native runtime
NATIVE_STATUS=$(python3 lib/experience_runner.py mia-status --json 2>/dev/null)
echo "$NATIVE_STATUS" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d.get('ok') is True, f'ok not true: {d}'
assert d.get('adapter', {}).get('ok') is True, f'adapter not ok: {d}'
" && ok "mia-status --json returns ok=true from native runtime" \
  || fail "mia-status from native runtime failed: $NATIVE_STATUS"

# Seed a test memory (llm_get_trace patched to return trace in local mode)
SEED_OUT=$(curl -s -X POST "http://127.0.0.1:${NATIVE_PORT}/batch_memory_save" \
  -H "Content-Type: application/json" \
  -d '[{"data_id":"test-seed","question":"queue block repair","image_caption":"","plan":"repair pipeline","judgement":"correct","used_memory_indices":[],"messages":[{"role":"assistant","content":"Identified blocked queue."},{"role":"user","content":"Queue repaired successfully."}]}]' \
  2>/dev/null)
[[ "$SEED_OUT" == *'"success"'* ]] \
  && ok "memory seeding via /batch_memory_save (llm_get_trace local mode)" \
  || fail "memory seeding failed: $SEED_OUT"

# mia-query with native runtime — must return ok=true with non-empty context
QUERY_OUT=$(python3 lib/experience_runner.py mia-query "queue block repair" --json 2>/dev/null)
echo "$QUERY_OUT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d.get('ok') is True, f'ok not true: {d}'
assert d.get('context', '').strip(), f'context empty: {d}'
" && ok "mia-query returns ok=true with non-empty context from native runtime" \
  || fail "mia-query from native runtime failed: $QUERY_OUT"

# -------------------------------------------------------------------------
# Fallback: stop native server, verify fail-open
# -------------------------------------------------------------------------
if [[ -f "$NATIVE_PID_FILE" ]]; then
  kill "$(cat "$NATIVE_PID_FILE")" 2>/dev/null || true
fi
lsof -ti ":${NATIVE_PORT}" | xargs kill -9 2>/dev/null || true
sleep 1

FALLBACK_OUT=$(SOLAR_MIA_TIMEOUT_SEC=0.1 python3 lib/experience_runner.py mia-query "test" --json 2>/dev/null || true)
echo "$FALLBACK_OUT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d.get('ok') is False, f'expected ok=False when server stopped: {d}'
assert d.get('status') == 'unreachable', f'expected unreachable: {d}'
" && ok "fallback ok=false+unreachable when native server stopped" \
  || fail "fallback did not fail-open: $FALLBACK_OUT"

# Vendor clean after all native tests
VENDOR_STATUS2=$(git -C vendor/MIA status --porcelain 2>/dev/null || true)
[[ -z "$VENDOR_STATUS2" ]] \
  && ok "vendor/MIA clean after native tests" \
  || fail "vendor/MIA dirty after native tests: $VENDOR_STATUS2"

# Restore the native service after fallback testing. This test is often run by
# evaluators against the live harness, so it must not leave the default MIA
# runtime stopped after proving the fail-open path.
if [[ "$FAIL" -eq 0 ]]; then
  RESTORE_OUT=$(python3 lib/experience_runner.py mia-start 2>/dev/null || true)
  echo "$RESTORE_OUT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d.get('ok') is True, d
" && ok "native server restored after fallback test" \
    || fail "native server restore failed: $RESTORE_OUT"
fi

echo ""
echo "========================"
echo "PASS=$PASS FAIL=$FAIL"
if [[ "$FAIL" -eq 0 ]]; then echo "PASS"; exit 0; else echo "FAIL"; exit 1; fi
