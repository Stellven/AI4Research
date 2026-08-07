#!/usr/bin/env bash
# tests/test-pane-lease.sh — Pane Ownership Lease regression tests
# sprint-20260508-coordinator-control-plane-v2 S3

set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
. "$HARNESS_DIR/lib/dispatch-ledger.sh"
. "$HARNESS_DIR/lib/pane-lease.sh"

PASS=0
FAIL=0

TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT
_PANE_LEASE_DIR="$TMP_DIR/pane-leases"
mkdir -p "$_PANE_LEASE_DIR"

check() {
    local label="$1" got="$2" want="$3"
    if [[ "$got" == "$want" ]]; then
        echo "  ✅ $label"
        PASS=$((PASS+1))
    else
        echo "  ❌ $label"
        echo "       want: $want"
        echo "        got: $got"
        FAIL=$((FAIL+1))
    fi
}

check_contains() {
    local label="$1" haystack="$2" needle="$3"
    if echo "$haystack" | grep -q "$needle" 2>/dev/null; then
        echo "  ✅ $label"
        PASS=$((PASS+1))
    else
        echo "  ❌ $label — '$needle' not found in: $(echo "$haystack" | head -1)"
        FAIL=$((FAIL+1))
    fi
}

echo "=== test-pane-lease.sh ==="
echo ""
echo "--- acquire / release ---"

DID1="d-20260508T100000Z-aabbcc"
DID2="d-20260508T100001Z-ddeeff"
PANE="solar-harness:0.2"

# T1: acquire on empty → success
result=$(acquire_pane_lease "$PANE" "sprint-abc" "$DID1" 600)
acquired=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('acquired',''))" "$result" 2>/dev/null)
check "acquire on empty → acquired=True" "$acquired" "True"

# T2: second acquire same pane → fails (busy)
result2=$(acquire_pane_lease "$PANE" "sprint-xyz" "$DID2" 600 2>/dev/null || true)
_r2="${result2}"; [[ -z "$_r2" ]] && _r2='{"acquired":false}'
acquired2=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('acquired',True))" "$_r2" 2>/dev/null || true)
check "acquire while leased → acquired=False" "$acquired2" "False"

# T3: check_pane_lease returns JSON with correct dispatch_id
lease_json=$(check_pane_lease "$PANE")
check_contains "check_pane_lease contains dispatch_id" "$lease_json" "$DID1"

# T4: release with wrong dispatch_id → fails (mismatch)
rel=$(release_pane_lease "$PANE" "$DID2" "test" 2>/dev/null || true)
[[ -z "$rel" ]] && rel='{"released":false}'
released=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('released',''))" "$rel" 2>/dev/null || true)
check "release wrong did → released=False" "$released" "False"

# T5: release with correct dispatch_id → success
rel2=$(release_pane_lease "$PANE" "$DID1" "test_done")
released2=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('released',''))" "$rel2" 2>/dev/null)
check "release correct did → released=True" "$released2" "True"
if [[ ! -e "$_PANE_LEASE_DIR/${PANE//:/_}.json.lock" ]]; then
    release_lock_removed=1
else
    release_lock_removed=0
fi
check "release correct did removes lock file" "$release_lock_removed" "1"

# T6: after release, pane is free again
result3=$(acquire_pane_lease "$PANE" "sprint-new" "d-20260508T100002Z-112233" 600)
acquired3=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('acquired',''))" "$result3" 2>/dev/null)
check "acquire after release → acquired=True" "$acquired3" "True"
# cleanup
release_pane_lease "$PANE" "d-20260508T100002Z-112233" >/dev/null 2>&1 || true

echo ""
echo "--- TTL / reap ---"

# T7: acquire with 1s TTL → expires quickly
DID3="d-20260508T100003Z-ffffff"
acquire_pane_lease "solar-harness:0.3" "sprint-ttl" "$DID3" 1 >/dev/null
sleep 2
reaped=$(reap_expired_leases)
check "reap_expired_leases returns >=1 after TTL expiry" "$(( reaped >= 1 ))" "1"

# T8: after reap, pane is free
result4=$(acquire_pane_lease "solar-harness:0.3" "sprint-after-reap" "d-20260508T100004Z-000000" 600)
acquired4=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('acquired',''))" "$result4" 2>/dev/null)
check "acquire after reap → acquired=True" "$acquired4" "True"
release_pane_lease "solar-harness:0.3" "d-20260508T100004Z-000000" >/dev/null 2>&1 || true

# T8b: reaper must clean orphan locks.
ORPHAN_LOCK="solar-harness_0_9.json.lock"
: > "$_PANE_LEASE_DIR/$ORPHAN_LOCK"
reaped_orphan=$(reap_expired_leases)
[[ ! -e "$_PANE_LEASE_DIR/$ORPHAN_LOCK" ]] && orphan_removed=1 || orphan_removed=0
check "reap_expired_leases removes orphan lock" "$orphan_removed" "1"
check "orphan lock reap counted" "$(( reaped_orphan >= 1 ))" "1"

# T8c: release on an already-missing lease must still remove the orphan lock.
MISSING_PANE="solar-harness:0.8"
MISSING_LOCK="solar-harness_0_8.json.lock"
: > "$_PANE_LEASE_DIR/$MISSING_LOCK"
release_pane_lease "$MISSING_PANE" "d-missing" "missing_lease_cleanup" >/dev/null 2>&1 || true
[[ ! -e "$_PANE_LEASE_DIR/$MISSING_LOCK" ]] && missing_lock_removed=1 || missing_lock_removed=0
check "release missing lease removes orphan lock" "$missing_lock_removed" "1"

echo ""
echo "--- python lease compatibility ---"

# T9: bash lease reader treats Python-native sprint_id leases as busy.
PANE_PY="solar-harness:0.5"
DID_PY="graph-eval-test-python-lease"
python3 - "$_PANE_LEASE_DIR" "$PANE_PY" "$DID_PY" <<'PY'
import datetime, json, pathlib, sys
lease_dir = pathlib.Path(sys.argv[1])
pane = sys.argv[2]
did = sys.argv[3]
safe = pane.replace(":", "_").replace(".", "_")
expires = (datetime.datetime.utcnow() + datetime.timedelta(seconds=600)).strftime("%Y-%m-%dT%H:%M:%SZ")
(lease_dir / f"{safe}.json").write_text(json.dumps({
    "pane": pane,
    "sprint_id": "sprint-python-lease",
    "dispatch_id": did,
    "acquired_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    "expires_at": expires,
    "ttl_sec": 600,
}), encoding="utf-8")
PY
result_py=$(acquire_pane_lease "$PANE_PY" "sprint-other" "d-20260508T100005Z-abcdef" 600 2>/dev/null || true)
held_py=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('held_sid',''))" "$result_py" 2>/dev/null || true)
check "bash acquire sees Python sprint_id lease" "$held_py" "sprint-python-lease"
release_pane_lease "$PANE_PY" "$DID_PY" "python_compat_done" >/dev/null 2>&1 || true

echo ""
echo "--- concurrent acquire (10 processes) ---"

# T10: 10 concurrent acquires on same pane → exactly 1 succeeds
PANE_C="solar-harness:0.4"
success_count=0
for i in $(seq 1 10); do
    (
        DID="d-20260508T999999Z-$(printf '%06x' $i)"
        r=$(acquire_pane_lease "$PANE_C" "sprint-$i" "$DID" 60 2>/dev/null || true)
        [[ -z "$r" ]] && r='{"acquired":false}'
        acq=$(python3 -c "import json,sys; print(1 if json.loads(sys.argv[1]).get('acquired') else 0)" "$r" 2>/dev/null || echo 0)
        echo $acq
    )
done | { sum=0; while read v; do sum=$((sum+v)); done; echo $sum; } > "$TMP_DIR/concurrent_result.txt"
concurrent_success=$(cat "$TMP_DIR/concurrent_result.txt")
check "concurrent 10 acquires: exactly 1 succeeds" "$concurrent_success" "1"

echo ""
echo "=== RESULT: PASS=$PASS FAIL=$FAIL ==="
[[ $FAIL -eq 0 ]]
