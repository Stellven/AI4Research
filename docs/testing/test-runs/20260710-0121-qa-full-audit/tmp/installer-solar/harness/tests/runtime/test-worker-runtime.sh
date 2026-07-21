#!/usr/bin/env bash
# test-worker-runtime.sh — R4 Worker Runtime tests
set -euo pipefail

HARNESS_DIR="${HOME}/.solar/harness"
LIB_DIR="${HARNESS_DIR}/lib"
TEST_STATE="${HARNESS_DIR}/state/workers"
PASS=0
FAIL=0

export PYTHONPATH="${LIB_DIR}:${PYTHONPATH:-}"

cleanup() {
    rm -rf "${TEST_STATE}"
}
trap cleanup EXIT

assert_eq() {
    local label="$1" actual="$2" expected="$3"
    if [ "$actual" = "$expected" ]; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
        echo "FAIL: $label — expected '$expected', got '$actual'"
    fi
}

echo "=== test-worker-runtime ==="

# T1: Register worker
T1_OUT=$(python3 -c "
from worker_runtime import WorkerRuntime
wr = WorkerRuntime()
info = wr.register('test-worker-1', capabilities=['bash', 'python'], location='local')
print(info.worker_id)
print(len(info.capabilities) == 2)
print(info.location == 'local')
print(len(info.registered_at) > 0)
")
assert_eq "T1: worker id" "$(echo "$T1_OUT" | head -1)" "test-worker-1"
assert_eq "T1: caps" "$(echo "$T1_OUT" | sed -n '2p')" "True"
assert_eq "T1: location" "$(echo "$T1_OUT" | sed -n '3p')" "True"
assert_eq "T1: registered_at" "$(echo "$T1_OUT" | sed -n '4p')" "True"

# T2: Heartbeat updates last_heartbeat
T2_OUT=$(python3 -c "
import time
from worker_runtime import WorkerRuntime
wr = WorkerRuntime()
wr.register('test-worker-2')
time.sleep(0.1)
ok = wr.heartbeat('test-worker-2')
info = wr.get_worker('test-worker-2')
print(ok)
print(len(info.last_heartbeat) > 0)
")
assert_eq "T2: heartbeat ok" "$(echo "$T2_OUT" | head -1)" "True"
assert_eq "T2: heartbeat updated" "$(echo "$T2_OUT" | sed -n '2p')" "True"

# T3: Heartbeat on unknown worker returns False
T3_OUT=$(python3 -c "
from worker_runtime import WorkerRuntime
wr = WorkerRuntime()
print(wr.heartbeat('nonexistent'))
")
assert_eq "T3: unknown heartbeat" "$T3_OUT" "False"

# T4: Acquire lease
T4_OUT=$(python3 -c "
from worker_runtime import WorkerRuntime
from runtime_interfaces import LeaseStatus
wr = WorkerRuntime()
wr.register('test-worker-3')
lease = wr.acquire_lease('test-worker-3', 'session-X', 'activity-A', ttl_seconds=60)
print(lease is not None)
print(lease.worker_id)
print(lease.session_id)
print(lease.activity_id)
print(lease.status == LeaseStatus.ACTIVE)
")
assert_eq "T4: lease acquired" "$(echo "$T4_OUT" | head -1)" "True"
assert_eq "T4: lease worker" "$(echo "$T4_OUT" | sed -n '2p')" "test-worker-3"
assert_eq "T4: lease session" "$(echo "$T4_OUT" | sed -n '3p')" "session-X"
assert_eq "T4: lease activity" "$(echo "$T4_OUT" | sed -n '4p')" "activity-A"
assert_eq "T4: lease active" "$(echo "$T4_OUT" | sed -n '5p')" "True"

# T5: Duplicate lease on same worker blocked
T5_OUT=$(python3 -c "
from worker_runtime import WorkerRuntime
wr = WorkerRuntime()
wr.register('test-worker-4')
lease1 = wr.acquire_lease('test-worker-4', 's1', 'a1')
lease2 = wr.acquire_lease('test-worker-4', 's2', 'a2')
print(lease1 is not None)
print(lease2 is None)
")
assert_eq "T5: first lease ok" "$(echo "$T5_OUT" | head -1)" "True"
assert_eq "T5: second lease blocked" "$(echo "$T5_OUT" | sed -n '2p')" "True"

# T6: Release lease
rm -rf "${TEST_STATE}"
T6_OUT=$(python3 -c "
from worker_runtime import WorkerRuntime
wr = WorkerRuntime()
wr.register('test-worker-5')
lease = wr.acquire_lease('test-worker-5', 's1', 'a1')
released = wr.release_lease('test-worker-5', 'a1', reason='done')
# Can acquire new lease after release
lease2 = wr.acquire_lease('test-worker-5', 's2', 'a2')
print(released)
print(lease2 is not None)
")
assert_eq "T6: released" "$(echo "$T6_OUT" | head -1)" "True"
assert_eq "T6: re-acquire" "$(echo "$T6_OUT" | sed -n '2p')" "True"

# T7: Lease idempotency — release non-existent lease returns False
T7_OUT=$(python3 -c "
from worker_runtime import WorkerRuntime
wr = WorkerRuntime()
print(wr.release_lease('nonexistent', 'no-act'))
")
assert_eq "T7: release non-existent" "$T7_OUT" "False"

# T8: List workers
rm -rf "${TEST_STATE}"
T8_OUT=$(python3 -c "
from worker_runtime import WorkerRuntime
wr = WorkerRuntime()
wr.register('w-list-1', capabilities=['bash'])
wr.register('w-list-2', capabilities=['python'])
workers = wr.list_workers()
print(len(workers))
print(any(w.worker_id == 'w-list-1' for w in workers))
print(any(w.worker_id == 'w-list-2' for w in workers))
")
assert_eq "T8: count" "$(echo "$T8_OUT" | head -1)" "2"
assert_eq "T8: w-list-1" "$(echo "$T8_OUT" | sed -n '2p')" "True"
assert_eq "T8: w-list-2" "$(echo "$T8_OUT" | sed -n '3p')" "True"

# T9: Expire leases
rm -rf "${TEST_STATE}"
T9_OUT=$(python3 -c "
from worker_runtime import WorkerRuntime
from runtime_interfaces import LeaseStatus
wr = WorkerRuntime()
wr.register('test-worker-6')
lease = wr.acquire_lease('test-worker-6', 's1', 'a1', ttl_seconds=0)
# ttl=0 means expires immediately
import time; time.sleep(1)
expired = wr.expire_leases()
print(len(expired))
active = wr.get_active_leases()
print(len(active))
")
assert_eq "T9: expired count" "$(echo "$T9_OUT" | head -1)" "1"
assert_eq "T9: no active" "$(echo "$T9_OUT" | sed -n '2p')" "0"

# T10: Unknown worker lease returns None
T10_OUT=$(python3 -c "
from worker_runtime import WorkerRuntime
wr = WorkerRuntime()
lease = wr.acquire_lease('ghost-worker', 's1', 'a1')
print(lease is None)
")
assert_eq "T10: ghost worker" "$T10_OUT" "True"

# T11: Duplicate activity lease blocked (different workers)
T11_OUT=$(python3 -c "
from worker_runtime import WorkerRuntime
wr = WorkerRuntime()
wr.register('w-dup-1')
wr.register('w-dup-2')
l1 = wr.acquire_lease('w-dup-1', 's1', 'shared-act')
l2 = wr.acquire_lease('w-dup-2', 's2', 'shared-act')
print(l1 is not None)
print(l2 is None)
")
assert_eq "T11: first activity lease" "$(echo "$T11_OUT" | head -1)" "True"
assert_eq "T11: duplicate activity lease" "$(echo "$T11_OUT" | sed -n '2p')" "True"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ]
