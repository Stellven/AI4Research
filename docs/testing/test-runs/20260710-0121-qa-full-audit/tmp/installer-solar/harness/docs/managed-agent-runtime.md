# Managed Agent Runtime — Architecture Guide

## Overview

Solar-Harness uses an **event-sourced, async-capable agent workflow runtime**.
The session event log is the single source of truth.
`status.json`, UI state, pane assignments, and context windows are all
**derived projections**, not independent writable truth.

---

## Core Concepts

### Session

A session is not a context window. It is a **durable, append-only event log**
stored at:

```
~/.solar/harness/sessions/<session_id>/events.jsonl
```

The harness is mostly stateless — it reconstructs execution state by
replaying session events. This means any worker can resume from any
checkpoint without re-running old LLM reasoning.

### Harness

The harness is the coordinator. It schedules activities, monitors the event
log, and updates projection caches (e.g., `status.json`). It does not hold
authoritative state in memory — it reads it from the log on each wake cycle.

### Activity

An **activity** is any unit of work with explicit side-effect boundaries:
a tool call, a model call, a pane dispatch, an MCP request, a human review.

Each activity has a lifecycle captured as events:

```
command_issued
    ↓
activity_started
    ↓
activity_succeeded  (terminal — happy path)
activity_failed     (terminal — error path)
activity_cancelled  (terminal — cancellation)
    ↓ (if failed)
activity_retry_scheduled
    ↓
activity_started    (retry loop)
    ...

activity_handoff    (signals review/takeover by another actor)
```

### Projection

A **projection** rebuilds a view from events. The canonical projection is
sprint status. The `ProjectionEngine` replays the session log for a sprint
and derives:

- `status`: queued | active | reviewing | passed | error | cancelled
- `round`: current handoff round
- `activities`: list of per-activity states
- `duplicate_commands`: idempotency-key violations
- `stale_activities`: activities stuck in `active`/`queued` too long
- `drift_detected`: mismatch between projected status and on-disk `status.json`

The `status.json` file is a **projection cache** — it is written by the engine
and read by the coordinator/UI for speed, but the event log is authoritative.

---

## File Layout

```
lib/
  session_log.py        — append-only event log, atomic writes, idempotency
  projection_engine.py  — rebuilds sprint state from events, writes status.json cache
  activity_runtime.py   — typed lifecycle helpers (command/start/succeed/fail/cancel/retry/handoff)
  runtime_doctor.py     — health diagnostics, drift detection, stale/duplicate checks

schemas/
  session-event-v2.schema.json  — JSON Schema for every session event

sessions/
  <session_id>/events.jsonl     — the durable event log
```

---

## Event Schema

Every event in the log conforms to `schemas/session-event-v2.schema.json`.

Required fields:

| Field        | Type   | Description |
|--------------|--------|-------------|
| `event_id`   | UUID4  | Globally unique event identity |
| `session_id` | string | Durable session identifier |
| `seq`        | int    | Monotonically increasing, 1-based |
| `ts`         | string | ISO 8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`) |
| `type`       | enum   | See event types below |
| `actor`      | string | Who produced this event |
| `source`     | string | Subsystem that emitted it |

Optional fields: `sprint_id`, `activity_id`, `correlation_id`, `causation_id`,
`idempotency_key`, `payload`.

### Event Types

```
command_issued          activity_started        activity_succeeded
activity_failed         activity_cancelled      activity_retry_scheduled
activity_handoff        state_transition        human_feedback
context_injected        log_message             session_started
session_ended
```

### Idempotency Key

Set `idempotency_key` on `command_issued` events to prevent duplicate side
effects from at-least-once delivery. The `SessionLog` will raise
`DuplicateEventError` and the `ActivityRuntime.command_issued()` helper will
return `""` silently on a replay.

---

## Python API

### SessionLog

```python
from session_log import SessionLog, DuplicateEventError

log = SessionLog(session_id="sprint-xyz")

# Append an event
eid = log.append(
    "command_issued",
    actor="coordinator",
    sprint_id="sprint-xyz",
    activity_id="act-1",
    idempotency_key="dispatch:sprint-xyz:round-1",
    payload={"target": "builder", "round": 1},
)

# Replay with optional filters
for ev in log.replay(sprint_id="sprint-xyz", event_type="command_issued"):
    print(ev["seq"], ev["type"])

# Scoped to a sprint (session_id == sprint_id)
log = SessionLog.for_sprint("sprint-xyz")
```

### ActivityRuntime

```python
from activity_runtime import ActivityRuntime

rt = ActivityRuntime("sprint-xyz")

rt.command_issued("act-1", actor="coordinator", target="builder", round_num=1)
rt.activity_started("act-1", actor="builder")
# ... work ...
rt.activity_succeeded("act-1", actor="builder", payload={"files": ["x.py"]})

# Error path
rt.activity_failed("act-1", actor="builder", error="compile error")
rt.activity_retry_scheduled("act-1", actor="coordinator", retry_num=1)

# Handoff to evaluator
rt.activity_handoff("act-1", actor="builder", to_actor="evaluator", round_num=1)

# Cancellation
rt.activity_cancelled("act-1", actor="coordinator", reason="user request")
```

### ProjectionEngine

```python
from projection_engine import ProjectionEngine

engine = ProjectionEngine("sprint-xyz")
state  = engine.project()

print(state.status)            # queued | active | reviewing | passed | error | cancelled
print(state.round)             # current handoff round
print(state.activities)        # list of ActivityState
print(state.duplicate_commands) # idempotency violations
print(state.stale_activities)  # activity_ids stuck too long
print(state.drift_detected)    # True if status.json is out of sync

engine.write_status_cache(state)   # update status.json
```

### Runtime Doctor

```python
from runtime_doctor import doctor_sprint, doctor_all

report = doctor_sprint("sprint-xyz")
# { "ok": bool, "warn": bool, "checks": { ... } }

report = doctor_all()
# { "ok": bool, "sprints": [ ... ] }
```

CLI:
```bash
python3 lib/runtime_doctor.py --json
python3 lib/runtime_doctor.py sprint-xyz --json
solar-harness runtime doctor --json
```

---

## Wake Routing

The `wake` command uses projection state to route work. Unknown status must
never fall back to a generic builder — it goes to PM diagnosis or runtime
doctor instead.

| Projected Status | Route to       |
|-----------------|----------------|
| `queued`        | builder        |
| `active`        | builder        |
| `reviewing`     | evaluator      |
| `passed`        | coordinator    |
| `error`         | runtime_doctor |
| `cancelled`     | coordinator    |
| unknown         | pm_diagnosis   |

---

## Migration from Legacy State Files

Existing `status.json` files are preserved unchanged — the projection engine
treats them as a writable cache and merges new projection fields without
removing existing ones.

The event log is additive: new events are appended without modifying any
existing state file.

### Migration Rules

1. **Do not delete** existing `status.json`, queue files, or dispatch ledger.
2. Use `ProjectionEngine.write_status_cache()` to update `status.json` after
   any event is appended.
3. For new sprints, seed the log with a `session_started` event.
4. For existing active sprints, seed with a `state_transition` event recording
   the current known status (source = "legacy_migration").

---

## Design Rationale

- **Append-only log**: No event is ever mutated. History is immutable.
- **Atomic writes**: `fcntl.LOCK_EX` prevents partial lines; `os.replace`
  ensures status.json is never partially written.
- **Idempotency**: The `idempotency_key` field ensures at-least-once delivery
  from tmux pane re-sends, coordinator retries, or remote worker reconnects
  does not duplicate side effects.
- **Projection drift**: If `status.json` disagrees with the projection by more
  than one status rank, the runtime doctor flags it. The log is authoritative.
- **No external dependencies**: Uses only Python stdlib + the existing
  `~/.solar/harness` directory structure. No Kafka, Redis, or Temporal.
