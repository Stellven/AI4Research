#!/usr/bin/env bash
# test-context-projection-policy.sh — R3 Context Projection tests
set -euo pipefail

HARNESS_DIR="${HOME}/.solar/harness"
LIB_DIR="${HARNESS_DIR}/lib"
SESSION_ID="test-ctx-proj-$$"
PASS=0
FAIL=0

export PYTHONPATH="${LIB_DIR}:${PYTHONPATH:-}"

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

echo "=== test-context-projection ==="

# Seed events
python3 -c "
from session_log import SessionLog
log = SessionLog('${SESSION_ID}')
# High-value events
for i in range(5):
    log.append('command_issued', actor='coord', sprint_id='test',
                idempotency_key=f'cmd:{i}', payload={'target': 'builder', 'round': i})
for i in range(3):
    log.append('activity_started', actor='builder', activity_id=f'act-{i}')
    log.append('activity_succeeded', actor='builder', activity_id=f'act-{i}',
                idempotency_key=f'ok:{i}')
# Low-value events (should be summarized)
for i in range(10):
    log.append('log_message', actor='system', payload={'msg': f'debug line {i}'})
# More high-value
log.append('state_transition', actor='coord', payload={'from': 'active', 'to': 'reviewing', 'round': 1})
log.append('human_feedback', actor='human', payload={'message': 'looks good'})
"

# T1: Context view has included events
T1_OUT=$(python3 -c "
from context_projection import ContextProjection
cp = ContextProjection('${SESSION_ID}')
view = cp.build_context()
print(len(view.included_event_ids) > 0)
print(view.session_id == '${SESSION_ID}')
print(view.policy_name == 'default')
print(len(view.built_at) > 0)
")
assert_eq "T1: has events" "$(echo "$T1_OUT" | head -1)" "True"
assert_eq "T1: session_id" "$(echo "$T1_OUT" | sed -n '2p')" "True"
assert_eq "T1: policy" "$(echo "$T1_OUT" | sed -n '3p')" "True"
assert_eq "T1: built_at" "$(echo "$T1_OUT" | sed -n '4p')" "True"

# T2: Summarized ranges for low-value events
T2_OUT=$(python3 -c "
from context_projection import ContextProjection
cp = ContextProjection('${SESSION_ID}')
view = cp.build_context()
has_summary = any('summarized' in s.get('summary', '') for s in view.summarized_ranges)
print(len(view.summarized_ranges) > 0)
print(has_summary)
print(view.summarized_ranges[0]['event_count'] if view.summarized_ranges else 0)
")
assert_eq "T2: has summaries" "$(echo "$T2_OUT" | head -1)" "True"
assert_eq "T2: summary label" "$(echo "$T2_OUT" | sed -n '2p')" "True"
assert_eq "T2: summary count" "$(echo "$T2_OUT" | sed -n '3p')" "10"

# T3: Budget limit causes dropped ranges
T3_OUT=$(python3 -c "
from context_projection import ContextProjection
cp = ContextProjection('${SESSION_ID}')
view = cp.build_context(budget_tokens=100)
has_dropped = len(view.dropped_ranges) > 0
print(has_dropped)
if view.dropped_ranges:
    print(view.dropped_ranges[0]['reason'])
")
assert_eq "T3: has dropped" "$(echo "$T3_OUT" | head -1)" "True"
assert_contains "T3: drop reason" "$(echo "$T3_OUT")" "budget"

# T4: KB hits when query provided
T4_OUT=$(python3 -c "
from context_projection import ContextProjection
cp = ContextProjection('${SESSION_ID}')
view = cp.build_context(query='managed agent runtime')
print(len(view.kb_hits) > 0)
print(view.kb_hits[0]['source'] != 'solar-harness')
print('placeholder' not in str(view.kb_hits[0].get('note', '')).lower())
")
assert_eq "T4: has kb hits" "$(echo "$T4_OUT" | head -1)" "True"
assert_eq "T4: real kb source" "$(echo "$T4_OUT" | sed -n '2p')" "True"
assert_eq "T4: no placeholder" "$(echo "$T4_OUT" | sed -n '3p')" "True"

# T5: Token estimate
T5_OUT=$(python3 -c "
from context_projection import ContextProjection
cp = ContextProjection('${SESSION_ID}')
view = cp.build_context()
print(view.token_estimate > 0)
print(view.budget_tokens)
")
assert_eq "T5: token est" "$(echo "$T5_OUT" | head -1)" "True"
assert_eq "T5: default budget" "$(echo "$T5_OUT" | sed -n '2p')" "8000"

# T6: build_context_text produces readable output
T6_OUT=$(python3 -c "
from context_projection import ContextProjection
cp = ContextProjection('${SESSION_ID}')
text = cp.build_context_text()
print('Context Projection' in text)
print('Provenance' in text)
print('projection over session events' in text)
")
assert_eq "T6: has title" "$(echo "$T6_OUT" | head -1)" "True"
assert_eq "T6: has provenance" "$(echo "$T6_OUT" | sed -n '2p')" "True"
assert_eq "T6: has disclaimer" "$(echo "$T6_OUT" | sed -n '3p')" "True"

# T7: Secret redaction in context text
T7_OUT=$(python3 -c "
from session_log import SessionLog
from context_projection import ContextProjection

log = SessionLog('${SESSION_ID}')
log.append('activity_started', actor='builder', payload={'msg': 'api_key=sk-1234567890abcdef1234567890abcdef12345678 setup done'})

cp = ContextProjection('${SESSION_ID}')
text = cp.build_context_text()
has_redaction = '[REDACTED]' in text
no_raw_secret = 'sk-1234567890abcdef' not in text
print(has_redaction)
print(no_raw_secret)
")
assert_eq "T7: secret redacted" "$(echo "$T7_OUT" | head -1)" "True"
assert_eq "T7: no raw secret" "$(echo "$T7_OUT" | sed -n '2p')" "True"

# T8: Context projection never modifies session events
T8_OUT=$(python3 -c "
from session_log import SessionLog
from context_projection import ContextProjection

log = SessionLog('${SESSION_ID}')
original_count = len(log.all_events())

cp = ContextProjection('${SESSION_ID}')
cp.build_context()
cp.build_context(query='test', budget_tokens=50)
cp.build_context_text()

after_count = len(log.all_events())
print(original_count == after_count)
")
assert_eq "T8: events unchanged" "$(echo "$T8_OUT")" "True"

# T9: Empty session returns valid empty context
T9_OUT=$(python3 -c "
from context_projection import ContextProjection
cp = ContextProjection('nonexistent-session-empty')
view = cp.build_context()
print(len(view.included_event_ids))
print(len(view.summarized_ranges))
print(len(view.dropped_ranges))
print(view.token_estimate)
")
assert_eq "T9: empty events" "$(echo "$T9_OUT" | head -1)" "0"
assert_eq "T9: empty summaries" "$(echo "$T9_OUT" | sed -n '2p')" "0"
assert_eq "T9: empty dropped" "$(echo "$T9_OUT" | sed -n '3p')" "0"
assert_eq "T9: zero tokens" "$(echo "$T9_OUT" | sed -n '4p')" "0"

# T10: explicit record appends context_injected audit event
T10_OUT=$(python3 -c "
from session_log import SessionLog
from context_projection import ContextProjection
log = SessionLog('${SESSION_ID}')
before = len([e for e in log.all_events() if e.get('type') == 'context_injected'])
cp = ContextProjection('${SESSION_ID}')
result = cp.record_context_injected(query='managed agent runtime', activity_id='test-dispatch')
after_events = [e for e in log.all_events() if e.get('type') == 'context_injected']
payload = after_events[-1]['payload'] if after_events else {}
print(result['ok'])
print(len(after_events) == before + 1 or result.get('duplicate') is True)
print(bool(payload.get('context_text')))
print(len(payload.get('kb_hits') or []) > 0)
")
assert_eq "T10: record ok" "$(echo "$T10_OUT" | head -1)" "True"
assert_eq "T10: event appended" "$(echo "$T10_OUT" | sed -n '2p')" "True"
assert_eq "T10: context text" "$(echo "$T10_OUT" | sed -n '3p')" "True"
assert_eq "T10: kb hits" "$(echo "$T10_OUT" | sed -n '4p')" "True"

# T11: dispatch injector writes worker-visible runtime context and sidecar
DISPATCH_FILE="${HARNESS_DIR}/run/test-runtime-context-dispatch-${SESSION_ID}.md"
mkdir -p "${HARNESS_DIR}/run"
printf '请分析 managed agent runtime context projection\n' > "$DISPATCH_FILE"
T11_OUT=$(python3 "${LIB_DIR}/runtime_context_inject.py" "$DISPATCH_FILE" --session-id "${SESSION_ID}" --pane "test-pane" --dispatch-id "dispatch-1" --json)
DISPATCH_CONTENT=$(cat "$DISPATCH_FILE")
assert_contains "T11: visible runtime context" "$DISPATCH_CONTENT" "<solar-runtime-context>"
assert_contains "T11: visible runtime context end" "$DISPATCH_CONTENT" "</solar-runtime-context>"
assert_contains "T11: injector ok" "$T11_OUT" '"ok": true'
rm -f "$DISPATCH_FILE" "$DISPATCH_FILE.runtime-context.json"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ]
