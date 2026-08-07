#!/usr/bin/env bash
# test-session-get-events.sh — R1 Session API pagination tests
set -euo pipefail

HARNESS_DIR="${HOME}/.solar/harness"
LIB_DIR="${HARNESS_DIR}/lib"
SESSION_ID="test-session-get-events-$$"
PASS=0
FAIL=0

export PYTHONPATH="${LIB_DIR}:${PYTHONPATH:-}"

# Cleanup
cleanup() {
    rm -rf "${HARNESS_DIR}/sessions/${SESSION_ID}"
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

assert_contains() {
    local label="$1" haystack="$2" needle="$3"
    if echo "$haystack" | grep -q "$needle"; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
        echo "FAIL: $label — expected to contain '$needle'"
    fi
}

echo "=== test-session-get-events ==="

# T1: get_events returns empty page for new session
T1_OUT=$(python3 -c "
from session_log import SessionLog
log = SessionLog('${SESSION_ID}')
page = log.get_events()
print(page['returned_count'])
print(page['has_more'])
print(page['next_cursor'] is None)
")
assert_eq "T1: empty count" "$(echo "$T1_OUT" | head -1)" "0"
assert_eq "T1: empty no more" "$(echo "$T1_OUT" | sed -n '2p')" "False"
assert_eq "T1: empty no cursor" "$(echo "$T1_OUT" | sed -n '3p')" "True"

# T2: get_events returns appended events
python3 -c "
from session_log import SessionLog
log = SessionLog('${SESSION_ID}')
for i in range(5):
    log.append('command_issued', actor='test', sprint_id='test', idempotency_key=f'test:{i}')
"
T2_OUT=$(python3 -c "
from session_log import SessionLog
log = SessionLog('${SESSION_ID}')
page = log.get_events()
print(page['returned_count'])
print(page['total_matching'])
")
assert_eq "T2: 5 events count" "$(echo "$T2_OUT" | head -1)" "5"
assert_eq "T2: 5 events total" "$(echo "$T2_OUT" | sed -n '2p')" "5"

# T3: limit pagination
T3_OUT=$(python3 -c "
from session_log import SessionLog
log = SessionLog('${SESSION_ID}')
page = log.get_events(limit=2)
print(page['returned_count'])
print(page['has_more'])
print(page['next_cursor'] is not None)
")
assert_eq "T3: limit 2 count" "$(echo "$T3_OUT" | head -1)" "2"
assert_eq "T3: limit 2 has_more" "$(echo "$T3_OUT" | sed -n '2p')" "True"
assert_eq "T3: limit 2 cursor" "$(echo "$T3_OUT" | sed -n '3p')" "True"

# T4: cursor-based continuation
T4_OUT=$(python3 -c "
from session_log import SessionLog
log = SessionLog('${SESSION_ID}')
page1 = log.get_events(limit=2)
page2 = log.get_events(cursor=page1['next_cursor'], limit=2)
page3 = log.get_events(cursor=page2['next_cursor'], limit=2)
print(page2['returned_count'], page2['has_more'])
print(page3['returned_count'], page3['has_more'])
")
assert_eq "T4: page2 has 2,more" "$(echo "$T4_OUT" | head -1)" "2 True"
assert_eq "T4: page3 has 1,no more" "$(echo "$T4_OUT" | sed -n '2p')" "1 False"

# T5: event_type filter
T5_OUT=$(python3 -c "
from session_log import SessionLog
log = SessionLog('${SESSION_ID}')
log.append('activity_started', actor='builder', sprint_id='test')
log.append('activity_succeeded', actor='builder', sprint_id='test', idempotency_key='ok:1')
page = log.get_events(event_type='activity_started')
print(page['total_matching'])
")
assert_eq "T5: filter event_type" "$(echo "$T5_OUT")" "1"

# T6: seq range filter
T6_OUT=$(python3 -c "
from session_log import SessionLog
log = SessionLog('${SESSION_ID}')
page = log.get_events(start_seq=2, end_seq=4)
print(page['total_matching'])
")
assert_eq "T6: seq range" "$(echo "$T6_OUT")" "3"

# T7: activity_id filter
python3 -c "
from session_log import SessionLog
log = SessionLog('${SESSION_ID}')
log.append('command_issued', actor='test', sprint_id='test', activity_id='act-X', idempotency_key='actX:1')
log.append('activity_started', actor='builder', activity_id='act-X')
"
T7_OUT=$(python3 -c "
from session_log import SessionLog
log = SessionLog('${SESSION_ID}')
page = log.get_events(activity_id='act-X')
print(page['total_matching'])
")
assert_eq "T7: activity_id filter" "$(echo "$T7_OUT")" "2"

# T8: replay() still works (backward compat)
T8_OUT=$(python3 -c "
from session_log import SessionLog
log = SessionLog('${SESSION_ID}')
count = sum(1 for _ in log.replay(sprint_id='test'))
print(count)
")
assert_contains "T8: replay backward compat" "$T8_OUT" "8"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ]
