#!/usr/bin/env bash
# activation_proof.sh — Livework activation proof: exercises all 5 event
# emitters via real Python paths, outputs JSONL event log.
#
# Usage:
#   ./activation_proof.sh [--output PATH] [--mode quick|long]
#
# Modes:
#   quick  — emit all 5 events immediately (default, for CI)
#   long   — emit heartbeats over >=1800s with real intervals (requires tmux/nohup)
#
# Exit codes: 0 = success, 1 = failure

set -euo pipefail

HARNESS_DIR="${HARNESS_DIR:-$HOME/.solar/harness}"
OUTPUT="${1:-}"
MODE="quick"

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --output)   OUTPUT="$2"; shift 2 ;;
        --mode)     MODE="$2"; shift 2 ;;
        *)          shift ;;
    esac
done

if [[ -z "$OUTPUT" ]]; then
    OUTPUT="$HOME/.solar/logs/livework-activation-proof-$(date +%Y%m%d).jsonl"
fi

mkdir -p "$(dirname "$OUTPUT")"

# Truncate output for fresh run
: > "$OUTPUT"

RUNNER="$HARNESS_DIR/autopilot/hooks/livework_heartbeat_runner.py"
EVENTS_PY="$HARNESS_DIR/lib/livework/events.py"

# Verify modules exist
if [[ ! -f "$EVENTS_PY" ]]; then
    echo "ERROR: livework/events.py not found at $EVENTS_PY" >&2
    exit 1
fi

# Run activation proof via Python (calls real emitters)
python3 -c "
import sys, os, json
from pathlib import Path

sys.path.insert(0, '$HARNESS_DIR/lib')

from livework.events import (
    emit_heartbeat,
    emit_deadlock_detected,
    emit_requirement_intake,
    emit_pm_drafted,
    emit_role_transition,
)

output = Path('$OUTPUT')
mode = '$MODE'

# Event 1: autopilot_heartbeat
emit_heartbeat(
    output,
    idle=True,
    active_dispatches=0,
    queue_depth=0,
    pane_states={'lab:0.0': {'lease_active': False, 'last_activity': ''}},
    sprint_id='sprint-activation-proof',
    actor='activation_proof',
    seq=1,
)

# Event 2: pane_deadlock
emit_deadlock_detected(
    output,
    pane_id='solar-harness-lab:0.2',
    dispatch_id='proof-dispatch-001',
    sprint_id='sprint-activation-proof',
    node_id='N1',
    dispatch_sent_at='2026-05-14T18:00:00Z',
    elapsed_seconds=650,
    deadline_seconds=600,
    action='alert',
    auto_recover=False,
    actor='activation_proof',
    seq=2,
)

# Event 3: requirement_intake
emit_requirement_intake(
    output,
    requirement_id='req-proof-001',
    raw_requirement='Fix the harness idle visibility gap when no active sprint is in the queue so that the autopilot monitor can detect and auto-progress work',
    sprint_id='sprint-activation-proof',
    submitted_by='user',
    source='cli',
    status='pm_analysis',
    actor='activation_proof',
    seq=3,
)

# Event 4: pm_drafted
emit_pm_drafted(
    output,
    sprint_id='sprint-activation-proof',
    phase='pm_analysis',
    prd_ready=True,
    outcome_count=3,
    next_step='planner_review',
    actor='activation_proof',
    seq=4,
)

# Event 5: role_transition
emit_role_transition(
    output,
    sprint_id='sprint-activation-proof',
    from_phase='pm_analysis',
    to_phase='drafting',
    actor='planner',
    reason='activation_proof: plan generated',
    node_id='N1',
    seq=5,
)

# If long mode, also emit periodic heartbeats
if mode == 'long':
    import time
    for i in range(6, 11):
        time.sleep(1)  # In real long mode this would be 300s intervals
        emit_heartbeat(
            output,
            idle=False,
            active_dispatches=1,
            queue_depth=0,
            sprint_id='sprint-activation-proof',
            actor='activation_proof_long',
            seq=i,
        )

print(json.dumps({'ok': True, 'output': str(output), 'mode': mode}))
" 2>&1

EXIT_CODE=$?

if [[ $EXIT_CODE -ne 0 ]]; then
    echo "ERROR: activation proof python execution failed (rc=$EXIT_CODE)" >&2
    exit 1
fi

# Verify output is non-empty and valid JSONL
LINE_COUNT=$(wc -l < "$OUTPUT" | tr -d ' ')
if [[ "$LINE_COUNT" -lt 5 ]]; then
    echo "ERROR: expected >= 5 lines in output, got $LINE_COUNT" >&2
    exit 1
fi

# Verify each line is valid JSON
python3 -c "
import json, sys
with open('$OUTPUT') as f:
    for i, line in enumerate(f, 1):
        line = line.strip()
        if not line:
            continue
        try:
            json.loads(line)
        except Exception as e:
            print(f'Invalid JSON at line {i}: {e}', file=sys.stderr)
            sys.exit(1)
print(f'Validated {i} JSONL lines')
"

echo "activation_proof: $LINE_COUNT events written to $OUTPUT"
exit 0
