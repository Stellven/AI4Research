# ADR: Solar-Harness x OpenAI Symphony Integration

**Status**: Accepted
**Date**: 2026-05-07
**Sprint**: sprint-20260507-010946

## 1. Context

OpenAI published [Symphony](https://github.com/openai/symphony), an orchestration SPEC for managing AI coding agents at scale. Key concepts:

- Long-running orchestrator reads work items from a tracker
- Per-issue isolated workspace with deterministic paths
- Repo-owned `WORKFLOW.md` defines agent behavior, prompts, and policies
- Single-authority scheduling state: claimed → running → retry → completed
- Structured JSONL event logs for observability
- Codex app-server protocol for agent execution with concurrency, timeout, and stall handling

Solar-Harness currently uses tmux panes as both UI and execution surface. This creates fragility (pane kills lose work), lack of workspace isolation, and poor retry semantics.

## 2. Decision

Adopt Symphony SPEC concepts as a **backend execution layer** for Solar-Harness, implemented in Python/Bash using only stdlib. Do NOT replace existing coordinator, PM, planner, or evaluator roles.

## 3. Solar Current State → Symphony Mapping

| Solar Component | Symphony Role | P0 Status |
|----------------|---------------|-----------|
| `sprints/*.status.json` | Tracker / Issue Source | Issue Adapter reads these |
| PM Gate (Claude TUI pane) | Not replaced | Solar keeps PM |
| Planner (Claude TUI pane) | Not replaced | Solar keeps Planner |
| Evaluator (Claude TUI pane) | Not replaced | Solar keeps Evaluator |
| tmux panes | Status surface only | Not primary executor |
| `coordinator.sh` | Not replaced | Zero changes in P0 |
| NEW: `issue-adapter.py` | Issue normalizer | P0 |
| NEW: `scheduler.py` | Orchestrator (dry-run) | P0 |
| NEW: `workspace-manager.sh` | Workspace factory | P0 |
| NEW: `runner.sh` | Agent runner (dry-run) | P0 |
| NEW: `WORKFLOW.solar.md` | Repo-owned workflow | P0 |

## 4. Why Not Replace Coordinator

1. **Coordinator manages tmux pane lifecycle** — Symphony manages workspace/agent lifecycle. These are orthogonal.
2. **Coordinator has mature state machine** — drafting → active → planning → approved → reviewing → passed/failed_review. Symphony scheduling (claimed → running → completed) is a subset.
3. **Zero-risk P0** — Adding Symphony alongside coordinator means no regression. If Symphony module has bugs, coordinator continues working.
4. **Migration path** — P1 can gradually shift responsibilities from coordinator to scheduler.

## 5. Why P0 Does Not Connect Linear

1. **Solar already has a tracker** — `sprints/*.status.json` is the source of truth.
2. **Linear requires API key management** — security surface we don't need for P0.
3. **Issue adapter normalizes** — future Linear integration just adds another adapter, same scheduler.
4. **Focus on execution isolation** — the real value of Symphony is workspace isolation and structured scheduling, not the tracker.

## 6. Phased Roadmap

### P0 (This Sprint): Dry-Run Foundation

- Issue adapter: read Solar sprints → normalize to Symphony Issue model
- Workspace manager: create isolated workspace per sprint
- Scheduler: dry-run only, produces state files and event logs
- Runner: dry-run only, renders prompt and writes proof artifacts
- CLI integration: `solar-harness symphony status/dry-run/workspace`
- Doctor integration: Symphony section in health check

### P1: Real Execution

- Runner with guarded Codex app-server launch
- Linear adapter (optional, behind feature flag)
- Retry with exponential backoff for real failures
- Workspace cleanup / garbage collection
- Concurrency > 1

### P2: Scale

- Multi-machine SSH workers
- Web UI dashboard
- PR auto-creation and auto-landing
- Logrotate and long-term retention

## 7. Security Boundaries

| Boundary | Rule |
|----------|------|
| No live pane mutation | Never `tmux respawn-pane/kill-pane/kill-session` on `solar-harness` or `solar-harness-lab` |
| No shared worktree | Each sprint gets its own isolated workspace under `$SOLAR_SYMPHONY_WORKSPACE_ROOT` |
| No hardcoded tokens | All credentials via env vars or config files, never in source |
| No Codex by default | `--dry-run` is the safe default; `--unsafe-run-codex` requires explicit opt-in |
| Env pollution guard | Runner strips `CLAUDECODE`/`CLAUDE_CODE_*` before launching any agent |

## 8. Architecture Diagram

```
User Intent
  → Solar PM/Planner (unchanged)
  → Sprint Contract (unchanged)
  → Issue Adapter (NEW)
    → reads sprints/*.status.json
    → normalizes to Symphony Issue JSON
  → Scheduler (NEW, dry-run)
    → priority/created_at ordering
    → state/symphony/{claimed,running,retry,completed}/
    → logs/symphony-events.jsonl
    → calls Workspace Manager + Runner
  → Workspace Manager (NEW)
    → creates isolated workspace per sprint
    → copies WORKFLOW.solar.md + contract
  → Runner (NEW, dry-run)
    → renders agent prompt
    → writes proof/ artifacts
    → does NOT launch Codex in P0
  → Evaluator (unchanged)
    → reviews proof artifacts
```

## 9. Data Flow

```
sprints/*.status.json
  → issue-adapter.py --list
  → JSON [{id, identifier, title, priority, state, ...}]
  → scheduler.py --dry-run
    → workspace-manager.sh create <sprint-id>
    → runner.sh --dry-run --sprint-id <id>
    → proof/run-request.md + proof/runner-env.json
    → state/symphony/completed/<sprint-id>.json
    → logs/symphony-events.jsonl (appended)
```

## 10. Consequences

- **Positive**: Structured scheduling, workspace isolation, future-proof for Codex/Linear
- **Positive**: No changes to existing coordinator or pane lifecycle
- **Negative**: Additional Python modules to maintain
- **Negative**: P0 is dry-run only — no real productivity gain until P1
- **Risk**: Workspace root (Toshiba) may not be mounted — fallback to ~/.solar/workspaces

## Sprint 2 Additions

### Hook Lifecycle Design

**Sprint**: sprint-20260507-symphony2
**Status**: Accepted

### Overview

Sprint 2 extends the Symphony workspace model with four lifecycle hook callpoints that fire around workspace creation and destruction. Hooks allow users to attach arbitrary shell commands to key workspace events — for example, archiving proof artifacts before cleanup, or notifying downstream systems after a workspace is claimed.

### Hook Execution Order

```
workspace-manager.sh create <sid>
  │
  ├─ 1. pre_claim_workspace   ← fires before workspace is finalized
  │       on_failure=fail → abort create if hook exits non-zero
  │
  ├─ 2. mkdir + contract link + .solar-sprint-id written
  │
  └─ 3. post_claim_workspace  ← fires after workspace is fully ready
          on_failure=fail → logged, create already completed

workspace-manager.sh clean <sid>
  │
  ├─ 1. pre_release_workspace  ← fires before rm -rf (can archive proof/)
  │       on_failure=continue  → failure is logged but cleanup proceeds
  │
  ├─ 2. rm -rf <ws_dir>
  │
  └─ 3. post_release_workspace ← fires after deletion (notify/audit)
          on_failure=continue  → config read before deletion, safe after
```

### Failure Semantics

| Hook | Default on_failure | Effect |
|------|-------------------|--------|
| pre_claim_workspace | fail | Workspace is not created; create exits non-zero |
| post_claim_workspace | fail | Logged but workspace is already claimed; typically non-critical |
| pre_release_workspace | continue | Failure logged; cleanup proceeds unconditionally |
| post_release_workspace | continue | Failure logged; workspace already deleted |

Users can override `on_failure` per hook in the WORKFLOW front matter.

### Environment Isolation (Sandboxed Execution)

Every hook runs in a sanitized subprocess created with `env -i`, which completely clears the parent process environment. Only an explicit whitelist is re-injected:

- `SPRINT_ID` — current sprint identifier
- `WORKSPACE_DIR` — absolute path to the workspace directory
- `WORKSPACE_ROOT` — root directory for all workspaces
- `SOLAR_SYMPHONY_HOOK_NAME` — name of the lifecycle hook being executed
- `PATH` — inherited from host (required for basic shell utilities)

All credential variables (`*_TOKEN`, `*_KEY`) are excluded by design. The host environment may contain `ZHIPU_AUTH_TOKEN`, `ANTHROPIC_AUTH_TOKEN`, and similar secrets; these are never visible to hook subprocesses.

Additional variables can be whitelisted per-hook using `env_allow`:

```yaml
hooks:
  pre_claim_workspace:
    command: "my-script.sh"
    env_allow: ["MY_CUSTOM_VAR", "AUDIT_ENDPOINT"]
```

Only variables listed in `env_allow` and present in the host environment are passed through. Empty or unset variables in the host produce an empty string in the hook environment (never an error).

### Timeout Implementation

Hooks execute with a per-hook timeout (`timeout_ms`, default 60000ms). Two implementations are used based on what is available:

1. **`gtimeout`** (preferred, from `brew install coreutils`): sends SIGTERM at timeout, then SIGKILL after 5 seconds.
2. **`perl alarm`** (fallback, macOS built-in): sets an alarm signal that terminates the hook process. Does not provide the 5-second SIGKILL grace period, but requires no additional installation.

Timeout events are logged to `~/.solar/harness/sprints/<sid>.hook-<name>.log` with a `timeout` marker.

### Log Storage

Each hook execution writes to a dedicated log file:

```
~/.solar/harness/sprints/<sprint_id>.hook-<hook_name>.log
```

Logs include timestamps, exit codes, on_failure decisions, and timeout markers. Log files persist after workspace cleanup to support post-mortem analysis.

### WORKFLOW Front Matter Schema

```yaml
hooks:
  global_timeout_ms: 120000        # optional, default 60000
  pre_claim_workspace:
    command: "echo pre_claim sprint=$SPRINT_ID"
    timeout_ms: 30000
    on_failure: fail                # fail | continue
    env_allow: []                   # optional extra vars
  post_claim_workspace:
    command: "echo post_claim workspace=$WORKSPACE_DIR"
    timeout_ms: 30000
    on_failure: fail
  pre_release_workspace:
    command: "tar -czf /archive/${SPRINT_ID}.tar.gz $WORKSPACE_DIR/proof"
    timeout_ms: 60000
    on_failure: continue
  post_release_workspace:
    command: "echo post_release cleanup done"
    timeout_ms: 30000
    on_failure: continue
```

All fields except `command` are optional. Hooks without a `command` field are silently skipped (no-op).

---

## 10. runner.sh --unsafe-run-codex: Safety Semantics

**Added**: Sprint 3 (sprint-20260507-symphony3) — backlog item from Sprint 2

### What it does

By default, `runner.sh` operates in `--dry-run` mode: it sets up the workspace environment, sources the WORKFLOW.md hooks, and emits structured events, but does **not** invoke any external AI coding agent (Codex or otherwise). This is the safe default because:

1. Agent invocations consume paid API credits.
2. Agent output is non-deterministic and may modify workspace files in ways that are hard to undo.
3. Dry-run mode is sufficient for integration testing of the harness itself.

The `--unsafe-run-codex` flag bypasses the dry-run guard and allows `runner.sh` to invoke the Codex agent subprocess against the live workspace. The word "unsafe" is intentional: it signals that the caller accepts responsibility for agent-side effects.

### Who can approve use of --unsafe-run-codex

Usage must be explicitly authorized by one of:

- The coordinator via a `WORKFLOW.md` `allow_codex_run: true` field signed by the planner pane.
- A human operator (the Solar guardian) confirming via the PM gate.
- An automated test harness with `ALLOW_CODEX_IN_TEST=1` set in a sandboxed environment.

Callers must never embed `--unsafe-run-codex` as a hardcoded constant in non-test scripts. It should always be conditionally assembled from a policy check.

### Where logs land

When `--unsafe-run-codex` is active:

- Codex subprocess stdout → `$WORKSPACE_DIR/codex.log`
- Runner event `codex_invoked` emitted to `events/all.jsonl` with payload `{"workspace": ..., "policy_source": "workflow_field|operator|test"}`
- Exit code and duration recorded as `codex_exited` event
- If Codex exits non-zero: `hook_failed` event emitted with `severity: warn`; runner continues to `post_release_workspace` hook (no abort unless `on_failure: abort`)

---

## 11. Observability Design: events.jsonl Schema v1

**Added**: Sprint 3 (sprint-20260507-symphony3)

### Motivation

Prior to Sprint 3, observability was fragmented: coordinator wrote ad-hoc JSONL lines with no schema, workspace-manager wrote separate log lines, and hooks wrote to stderr only. This made cross-component correlation impossible and HTTP dashboard rendering unreliable.

Sprint 3 introduced a unified events.jsonl schema (v1) and a single `emit_event()` API that all components use.

### Schema

Every event line must be valid JSON conforming to `schemas/event.schema.json`:

```json
{
  "ts":        "<ISO 8601 UTC>",
  "sprint_id": "<string | null>",
  "actor":     "<coordinator | runner | workspace-manager | hooks | solar-harness>",
  "event":     "<snake_case>",
  "severity":  "<info | warn | error>",
  "payload":   { }
}
```

`additionalProperties: false` — any extra field is a schema violation and will be rejected by the validator.

### Append paths

- `$HARNESS_DIR/events/all.jsonl` — global stream, every event from every component
- `$HARNESS_DIR/sprints/<sprint_id>.events.jsonl` — per-sprint stream, filtered by `sprint_id`

### Thread safety

The `_atomic_append()` function in `lib/events.sh` uses `mkdir`-based locking (POSIX portable, works on macOS without `flock`) to prevent torn writes under 20+ concurrent callers. Measured in TC5 of `test-events-emit.sh`: 20 parallel writes, 0 torn lines.

### HTTP Status Dashboard

`lib/symphony/status-server.py` serves:
- `GET /` — HTML dashboard with 5s auto-refresh, no external CDN dependencies
- `GET /status` — JSON snapshot: `{current_sprint, panes, recent_events, kpi}`
- `GET /events?sprint_id=X&limit=N` — filtered event stream
- `GET /healthz` — liveness probe

The server binds to `127.0.0.1:8765` (internal only, no TLS required). Port fallback range 8765–8775 handles the common case of a stale process holding the primary port. Start/stop/restart managed via `solar-harness status-server [start|stop|restart|status]`.

### Backward compatibility

The coordinator's pre-existing `emit_event()` calls (≈15 call sites) used a different argument order: `emit_event <sid> <event> [actor] [data]`. A compatibility shim in `coordinator.sh` translates old-signature calls into new-signature `events_emit()` calls transparently. No call sites needed modification.

---

## 12. Coordinator Routing Bug: Post-Mortem

**Added**: Sprint 3 (sprint-20260507-symphony3)

### Symptom

`choose_evaluator_pane()` was returning pane `0.0` (the planner/PM pane) instead of pane `0.3` (the evaluator pane). As a result, evaluator dispatch messages were silently delivered to the planner, causing no-op review cycles where the evaluator never received the sprint.

### Root Cause

`discover_pane_by_persona()` scans panes in index order (0, 1, 2, 3, ...). For each pane it tries three detection strategies in order:

1. Process tree scan (`pane_process_persona`)
2. Pane title match (`pane_title_persona`)
3. `capture-pane` content regex scan

The third strategy used the pattern `Persona:[[:space:]]*evaluator([[:space:]]|$)`. This pattern was not anchored to the start of line. On the planner pane (index 0), earlier screen history could contain the word "evaluator" in a dispatch log line or banner text, causing a false match before the scan reached the real evaluator pane at index 3.

### Fix

Two changes in `coordinator.sh`:

1. **Regex anchored to line start/end**: Changed `Persona:[[:space:]]*${persona}([[:space:]]|$)` → `^Persona:[[:space:]]*${persona}[[:space:]]*$`. This ensures only lines that are exactly `Persona: <name>` match, eliminating false positives from log content.

2. **Env override escape hatch**: Added `PANE_<PERSONA_UPPER>` environment variable override (e.g. `PANE_EVALUATOR=solar-harness:0.3`). Operators can hard-wire pane assignments without relying on content scanning, useful in degraded environments where tmux pane titles are not set.

3. **Diagnostic logging**: `discover_pane_by_persona` now emits `[routing]` log lines for every pane it scans, making future misrouting incidents easy to diagnose via `tail -f ~/.solar/harness/.coordinator.log`.

### Regression Protection

`test-coordinator-routing.sh` (8 assertions) covers the env override path, the fallback path, and the strict regex behavior. TC5 specifically verifies that `evaluator-pending` does not match the strict pattern.
