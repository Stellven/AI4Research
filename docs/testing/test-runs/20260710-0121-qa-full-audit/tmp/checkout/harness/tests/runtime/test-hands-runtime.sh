#!/usr/bin/env bash
# test-hands-runtime.sh — R2 Hands Runtime tests
set -euo pipefail

HARNESS_DIR="${HOME}/.solar/harness"
LIB_DIR="${HARNESS_DIR}/lib"
PASS=0
FAIL=0

export PYTHONPATH="${LIB_DIR}:${PYTHONPATH:-}"

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

echo "=== test-hands-runtime ==="

# T1: Mock hand — provision/execute/dispose lifecycle
T1_OUT=$(python3 -c "
from hands_runtime import MockHand, get_hand
from runtime_interfaces import HandType, ResultStatus

h = MockHand()
ref = h.provision(capabilities=['bash', 'python'])
print(ref.hand_id.startswith('mock-'))
print(ref.hand_type == HandType.MOCK)

result = h.execute(ref, 'test_cmd', {'key': 'val'}, idempotency_key='idem-1')
print(result.status == ResultStatus.OK)
print(result.output['mock'])

dispose = h.dispose(ref)
print(dispose.status == ResultStatus.OK)
print(dispose.output['disposed'] == ref.hand_id)
")
assert_eq "T1: mock provision id" "$(echo "$T1_OUT" | head -1)" "True"
assert_eq "T1: mock type" "$(echo "$T1_OUT" | sed -n '2p')" "True"
assert_eq "T1: mock execute" "$(echo "$T1_OUT" | sed -n '3p')" "True"
assert_eq "T1: mock output" "$(echo "$T1_OUT" | sed -n '4p')" "True"
assert_eq "T1: mock dispose" "$(echo "$T1_OUT" | sed -n '5p')" "True"
assert_eq "T1: mock dispose id" "$(echo "$T1_OUT" | sed -n '6p')" "True"

# T2: Idempotency — duplicate key returns duplicate_suppressed
T2_OUT=$(python3 -c "
from hands_runtime import MockHand
from runtime_interfaces import ResultStatus

h = MockHand()
ref = h.provision()
r1 = h.execute(ref, 'cmd', {}, idempotency_key='dup-test')
r2 = h.execute(ref, 'cmd', {}, idempotency_key='dup-test')
print(r1.status == ResultStatus.OK)
print(r2.status == ResultStatus.DUPLICATE_SUPPRESSED)
")
assert_eq "T2: first ok" "$(echo "$T2_OUT" | head -1)" "True"
assert_eq "T2: second dup" "$(echo "$T2_OUT" | sed -n '2p')" "True"

# T3: Shell hand — safe command executes
T3_OUT=$(python3 -c "
from hands_runtime import ShellHand
from runtime_interfaces import ResultStatus

h = ShellHand()
ref = h.provision()
result = h.execute(ref, 'echo', {'command': 'echo hello'}, idempotency_key='shell-1')
print(result.status == ResultStatus.OK)
print(result.output.strip())
print(result.duration_ms is not None)
")
assert_eq "T3: shell ok" "$(echo "$T3_OUT" | head -1)" "True"
assert_eq "T3: shell output" "$(echo "$T3_OUT" | sed -n '2p')" "hello"
assert_eq "T3: shell duration" "$(echo "$T3_OUT" | sed -n '3p')" "True"

# T4: Shell hand — destructive command denied
T4_OUT=$(python3 -c "
from hands_runtime import ShellHand
from runtime_interfaces import ResultStatus

h = ShellHand()
ref = h.provision()
result = h.execute(ref, 'rm_rf', {'command': 'rm -rf /'}, idempotency_key='shell-denied-1')
print(result.status == ResultStatus.ERROR)
print('denied' in (result.error or ''))
")
assert_eq "T4: denied status" "$(echo "$T4_OUT" | head -1)" "True"
assert_eq "T4: denied message" "$(echo "$T4_OUT" | sed -n '2p')" "True"

# T5: Shell hand — secret redaction
T5_OUT=$(python3 -c "
from hands_runtime import ShellHand

h = ShellHand()
ref = h.provision()
result = h.execute(ref, 'secret', {'command': 'echo api_key=sk-abcdef12345678901234567890123456789012345678 test'}, idempotency_key='shell-secret-1')
redacted = result.redacted_secrets
has_redaction = '[REDACTED]' in (result.output or '')
print(len(redacted) > 0)
print(has_redaction)
")
assert_eq "T5: secret found" "$(echo "$T5_OUT" | head -1)" "True"
assert_eq "T5: secret redacted" "$(echo "$T5_OUT" | sed -n '2p')" "True"

# T6: Factory and registry
T6_OUT=$(python3 -c "
from hands_runtime import get_hand, available_hand_types
from runtime_interfaces import HandType

types = available_hand_types()
print(HandType.MOCK in types)
print(HandType.SHELL in types)
print(HandType.SANDBOX in types)
print(HandType.PANE in types)
print(HandType.REMOTE in types)

h = get_hand(HandType.MOCK)
print(type(h).__name__)
")
assert_eq "T6: mock in types" "$(echo "$T6_OUT" | head -1)" "True"
assert_eq "T6: shell in types" "$(echo "$T6_OUT" | sed -n '2p')" "True"
assert_eq "T6: sandbox in types" "$(echo "$T6_OUT" | sed -n '3p')" "True"
assert_eq "T6: pane in types" "$(echo "$T6_OUT" | sed -n '4p')" "True"
assert_eq "T6: remote in types" "$(echo "$T6_OUT" | sed -n '5p')" "True"
assert_eq "T6: factory mock" "$(echo "$T6_OUT" | sed -n '6p')" "MockHand"

# T7: Pane hand — provision and execute (no actual tmux required)
T7_OUT=$(python3 -c "
from hands_runtime import PaneHand
from runtime_interfaces import HandType, ResultStatus

h = PaneHand()
ref = h.provision(location='0')
print(ref.hand_type == HandType.PANE)
print(ref.location == '0')

result = h.execute(ref, 'dispatch', {'command': 'echo test'}, idempotency_key='pane-1')
# May fail if no tmux session, but must not crash
print(result.status in (ResultStatus.OK, ResultStatus.ERROR))
")
assert_eq "T7: pane type" "$(echo "$T7_OUT" | head -1)" "True"
assert_eq "T7: pane location" "$(echo "$T7_OUT" | sed -n '2p')" "True"
assert_eq "T7: pane execute no crash" "$(echo "$T7_OUT" | sed -n '3p')" "True"

# T8: Remote hand — provision and execute (no actual SSH required)
T8_OUT=$(python3 -c "
from hands_runtime import RemoteHand
from runtime_interfaces import HandType, ResultStatus

h = RemoteHand()
ref = h.provision()
print(ref.hand_type == HandType.REMOTE)

result = h.execute(ref, 'remote_cmd', {'command': 'echo hi'}, idempotency_key='remote-1')
print(result.status in (ResultStatus.OK, ResultStatus.ERROR, ResultStatus.TIMEOUT))
")
assert_eq "T8: remote type" "$(echo "$T8_OUT" | head -1)" "True"
assert_eq "T8: remote execute no crash" "$(echo "$T8_OUT" | sed -n '2p')" "True"

# T9: Remote hand — missing checksum rejected
T9_OUT=$(python3 -c "
from hands_runtime import RemoteHand
from runtime_interfaces import ResultStatus

h = RemoteHand()
ref = h.provision()
result = h.execute(ref, 'manifest', {
    'command': 'echo hi',
    'manifest': {'files': ['a.py']}  # no checksum
}, idempotency_key='remote-no-checksum')
print(result.status == ResultStatus.ERROR)
print('checksum' in (result.error or '').lower())
")
assert_eq "T9: no checksum error" "$(echo "$T9_OUT" | head -1)" "True"
assert_eq "T9: checksum in msg" "$(echo "$T9_OUT" | sed -n '2p')" "True"

# T10: execute emits command/start/terminal activity events
T10_OUT=$(python3 -c "
import shutil
from hands_runtime import ShellHand
from session_log import SessionLog

sid = 'test-hand-runtime-events'
shutil.rmtree('${HARNESS_DIR}/sessions/' + sid, ignore_errors=True)
h = ShellHand()
ref = h.provision()
r = h.execute(ref, 'echo', {
    'command': 'echo hand-events',
    'session_id': sid,
    'sprint_id': sid,
    'activity_id': 'act-hand-events',
}, idempotency_key='hand-events-1')
events = SessionLog(sid).all_events()
print([e['type'] for e in events])
print(len(events) == 3)
print(events[-1]['type'] == 'activity_succeeded')
shutil.rmtree('${HARNESS_DIR}/sessions/' + sid, ignore_errors=True)
")
assert_contains "T10: activity event order" "$(echo "$T10_OUT" | head -1)" "command_issued"
assert_eq "T10: three events" "$(echo "$T10_OUT" | sed -n '2p')" "True"
assert_eq "T10: terminal event" "$(echo "$T10_OUT" | sed -n '3p')" "True"

# T11: Sandbox hand — disposable workspace + evidence
T11_OUT=$(python3 -c "
import json, os
from pathlib import Path
from hands_runtime import SandboxHand
from runtime_interfaces import ResultStatus

h = SandboxHand()
ref = h.provision(capabilities=['shell'])
workspace = Path(ref.metadata['workspace'])
r = h.execute(ref, 'write', {'command': 'printf hello > out.txt'}, idempotency_key='sandbox-write-1')
evidence = Path(r.metadata['evidence_file'])
print(ref.hand_type.value)
print(r.status == ResultStatus.OK)
print((workspace / 'out.txt').read_text() == 'hello')
print(evidence.exists())
print(json.loads(evidence.read_text())['workspace_manifest']['file_count'] >= 1)
d = h.dispose(ref)
print(d.output['workspace_removed'])
")
assert_eq "T11: sandbox type" "$(echo "$T11_OUT" | head -1)" "sandbox"
assert_eq "T11: sandbox execute ok" "$(echo "$T11_OUT" | sed -n '2p')" "True"
assert_eq "T11: sandbox file written" "$(echo "$T11_OUT" | sed -n '3p')" "True"
assert_eq "T11: evidence exists" "$(echo "$T11_OUT" | sed -n '4p')" "True"
assert_eq "T11: evidence manifest" "$(echo "$T11_OUT" | sed -n '5p')" "True"
assert_eq "T11: workspace disposed" "$(echo "$T11_OUT" | sed -n '6p')" "True"

# T12: Sandbox hand — env allowlist + secret broker redaction
T12_OUT=$(SOLAR_SAFE_TEST=visible SOLAR_SECRET_TEST='super-secret-value-12345' python3 -c "
from hands_runtime import SandboxHand
from runtime_interfaces import ResultStatus

h = SandboxHand()
ref = h.provision()
r = h.execute(ref, 'env', {
    'command': 'printf \"%s/%s\" \"\$SOLAR_SAFE_TEST\" \"\$TOKEN\"',
    'env_allow': ['SOLAR_SAFE_TEST'],
    'secret_refs': {'TOKEN': 'env:SOLAR_SECRET_TEST'}
}, idempotency_key='sandbox-env-1')
print(r.status == ResultStatus.OK)
print(r.output)
print('super-secret-value' not in r.output)
print(r.redacted_secrets == ['TOKEN'])
h.dispose(ref)
")
assert_eq "T12: sandbox env ok" "$(echo "$T12_OUT" | head -1)" "True"
assert_eq "T12: safe env visible secret redacted" "$(echo "$T12_OUT" | sed -n '2p')" "visible/[REDACTED]"
assert_eq "T12: raw secret absent" "$(echo "$T12_OUT" | sed -n '3p')" "True"
assert_eq "T12: secret name recorded" "$(echo "$T12_OUT" | sed -n '4p')" "True"

# T13: Sandbox hand — evidence command is redacted when a secret literal appears
T13_OUT=$(SOLAR_SECRET_TEST='super-secret-value-12345' python3 -c "
import json
from pathlib import Path
from hands_runtime import SandboxHand
from runtime_interfaces import ResultStatus

h = SandboxHand()
ref = h.provision()
r = h.execute(ref, 'literal-secret', {
    'command': 'printf super-secret-value-12345',
    'secret_refs': {'TOKEN': 'env:SOLAR_SECRET_TEST'}
}, idempotency_key='sandbox-evidence-redact-1')
evidence = json.loads(Path(r.metadata['evidence_file']).read_text())
print(r.status == ResultStatus.OK)
print(r.output == '[REDACTED]')
print('super-secret-value' not in evidence['command'])
print('[REDACTED]' in evidence['command'])
h.dispose(ref)
")
assert_eq "T13: literal secret ok" "$(echo "$T13_OUT" | head -1)" "True"
assert_eq "T13: output redacted" "$(echo "$T13_OUT" | sed -n '2p')" "True"
assert_eq "T13: evidence raw secret absent" "$(echo "$T13_OUT" | sed -n '3p')" "True"
assert_eq "T13: evidence command redacted" "$(echo "$T13_OUT" | sed -n '4p')" "True"

# T14: Sandbox hand — argv mode runs without shell=True and records execution mode
T14_OUT=$(python3 -c "
import json
from pathlib import Path
from hands_runtime import SandboxHand
from runtime_interfaces import ResultStatus

h = SandboxHand()
ref = h.provision()
r = h.execute(ref, 'argv-write', {
    'argv': ['/bin/sh', '-c', 'printf argv-ok > argv.txt; cat argv.txt']
}, idempotency_key='sandbox-argv-1')
evidence = json.loads(Path(r.metadata['evidence_file']).read_text())
print(r.status == ResultStatus.OK)
print(r.output == 'argv-ok')
print(evidence['execution_mode'] == 'argv')
print(evidence['workspace_manifest']['file_count'] >= 1)
h.dispose(ref)
")
assert_eq "T14: argv ok" "$(echo "$T14_OUT" | head -1)" "True"
assert_eq "T14: argv output" "$(echo "$T14_OUT" | sed -n '2p')" "True"
assert_eq "T14: evidence argv mode" "$(echo "$T14_OUT" | sed -n '3p')" "True"
assert_eq "T14: argv evidence manifest" "$(echo "$T14_OUT" | sed -n '4p')" "True"

# T15: Sandbox hand — write guard detects host writes outside workspace
T15_OUT=$(python3 -c "
import json, tempfile
from pathlib import Path
from hands_runtime import SandboxHand
from runtime_interfaces import ResultStatus

guard_root = Path(tempfile.mkdtemp(prefix='solar-host-guard-'))
h = SandboxHand()
ref = h.provision()
host_file = guard_root / 'leak.txt'
r = h.execute(ref, 'host-write', {
    'command': 'printf leak > ' + str(host_file),
    'write_guard_roots': [str(guard_root)],
}, idempotency_key='sandbox-guard-1')
evidence = json.loads(Path(r.metadata['evidence_file']).read_text())
violations = evidence['write_guard']['violations']
print(r.status == ResultStatus.ERROR)
print('write guard violation' in (r.error or ''))
print(any(v['type'] == 'created' and v['path'].endswith('leak.txt') for v in violations))
print(evidence['write_guard']['enabled'])
h.dispose(ref)
")
assert_eq "T15: guard blocks host write" "$(echo "$T15_OUT" | head -1)" "True"
assert_eq "T15: guard error message" "$(echo "$T15_OUT" | sed -n '2p')" "True"
assert_eq "T15: guard violation path" "$(echo "$T15_OUT" | sed -n '3p')" "True"
assert_eq "T15: guard enabled evidence" "$(echo "$T15_OUT" | sed -n '4p')" "True"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ]
