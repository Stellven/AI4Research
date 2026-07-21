# N1: Unified Selector Spec

> Sprint: `sprint-20260527-operator-architecture-convergence`
> Node: N1 | Gate: G_PLAN
> Status: spec_only (no code changes)
> Evidence Policy: no_code=true, no_lib_modification=read-only

---

## 1. Purpose

Today, Solar Harness has >=6 distinct scheduling entry points, each with its own hardcoded pane IDs, session names, timeouts, and routing logic. Adding a new pane, model provider, or dispatch mode requires touching multiple files in parallel — a classic shotgun surgery smell.

This spec defines a **unified selector contract**: a single `select(candidates, context) -> decision` signature that every scheduling entry must call through, plus **drift_guard rules** that block any new entry bypassing the central registry.

---

## 2. Existing Scheduling Entry Inventory

### E1: Coordinator Main Loop

| Field | Value |
|-------|-------|
| Entry | `coordinator.sh:49-97` |
| Trigger | Manual sprint status change, cron monitoring |
| Hardcoded Points | `SESSION_NAME="solar-harness"`, `LAB_SESSION_NAME="solar-harness-lab"`, `PANE_PLANNER_DEFAULT="solar-harness:0.1"`, `PANE_BUILDER_DEFAULT="solar-harness-lab:0.0"`, `PANE_EVALUATOR_DEFAULT="solar-harness:0.3"`, `PANE_NOTIFY="solar-harness:0.0"` |
| Decision | Routes task to fixed pane by role (planner/builder/evaluator/pm) |
| Drift Risk | Adding a new role requires editing 5+ variable assignments and discovering panes by persona title regex |

### E2: Graph Scheduler — Ready Node Dispatch

| Field | Value |
|-------|-------|
| Entry | `graph_scheduler.py:1029-1047` (ready_nodes), `1457-1503` (assign_ready) |
| Trigger | Sprint enters `graph_in_progress` status; manual or autopilot-initiated |
| Hardcoded Points | `TERMINAL_STATUSES = {"passed", "failed", "skipped"}`, `ACTIVE_STATUSES = {"dispatched", "reviewing", "running"}`, `READY_STATUSES = {"ready"}`, write_scope conflict grouping logic (no external config) |
| Decision | Determines which DAG nodes are ready, batches non-conflicting nodes, assigns workers |
| Drift Risk | New status values must be manually added to all three sets across the file |

### E3: Autopilot Scan + Queue Drain

| Field | Value |
|-------|-------|
| Entry | `autopilot.py:112-167` (scan), `412-440` (drain_queue) |
| Trigger | Cron tick (manual `autopilot.py scan` or `drain-queue`) |
| Hardcoded Points | `DEADLOCK_STALL_SEC = 300`, `STALL_SEC = 900`, `BACKLOG_THRESHOLD = 3` |
| Decision | Detects stalled leases, recommends deadlock resolution, pops queued tasks and assigns to free workers |
| Drift Risk | Thresholds are magic numbers; changing deadlock detection sensitivity requires code edit |

### E4: Pane Lease Broker

| Field | Value |
|-------|-------|
| Entry | `pane_lease.py:132-190` |
| Trigger | Dispatcher `acquire_lease()` before any pane dispatch |
| Hardcoded Points | `DEFAULT_TTL = 600` (seconds), 3-state classification logic (no_pane/busy/dead) |
| Decision | Classifies pane state, grants or denies lease acquisition |
| Drift Risk | TTL is a constant; different dispatch types needing different TTLs requires branching logic |

### E5: Chain Watcher

| Field | Value |
|-------|-------|
| Entry | `chain-watcher.sh:85-101` |
| Trigger | File arrival in `~/.solar/codex-bridge/from-codex/` (polling/cron) |
| Hardcoded Points | `PANE_PLANNER_FALLBACK_TARGET="solar-harness:0.1"`, persona title regex `"Planner|规划者"`, throttle window = 60 seconds |
| Decision | Routes Codex bridge intents to Planner pane, falls back to hardcoded pane |
| Drift Risk | Fallback target is a literal string; persona title matching is regex-dependent |

### E6: Dispatch Scheduler (Spillover Pool)

| Field | Value |
|-------|-------|
| Entry | `dispatch_scheduler.py:55-199` |
| Trigger | Graph node dispatcher needs a pane for evaluation or worker assignment |
| Hardcoded Points | `PROTECTED_PANES = ["solar-harness:0.0", "solar-harness:0.1", "solar-harness:0.2"]`, `DEFAULT_SPILLOVER_POOL = ["solar-harness:0.3", "solar-harness-lab:0.0".."solar-harness-lab:0.3"]`, `max_items default = 3` |
| Decision | Round-robin spillover with deduplication, safety guard prevents killing protected panes |
| Drift Risk | Adding/removing a pane requires editing the hardcoded list |

---

## 3. Unified Selector Contract

### 3.1 Function Signature

```python
def select(
    candidates: list[Candidate],
    context: SelectContext,
) -> Decision:
    """
    Select exactly one candidate from the pool given the current context.

    Parameters
    ----------
    candidates : list[Candidate]
        Pool of eligible targets (panes, models, nodes, workers).
        Each Candidate has: id, capabilities, load, lease_state, priority_hint.
    context : SelectContext
        Immutable snapshot of dispatch-time state:
        - task_type: str (build | eval | plan | notify | research)
        - required_capabilities: list[str]
        - write_scope: list[str]  (files this task will touch)
        - risk_tier: str (critical | high | medium | low)
        - preferred_model: str | None
        - sprint_id: str
        - requesting_entry: str  (E1..E6 entry ID)
        - now: datetime  (for TTL/throttle decisions)

    Returns
    -------
    Decision
        selected: Candidate  -- the chosen target
        rejected: list[Candidate]  -- why each was skipped
        trace_id: str  -- for audit/logging
    """
```

### 3.2 Data Types

```python
@dataclass
class Candidate:
    id: str                           # e.g. "solar-harness-lab:0.3"
    capabilities: set[str]            # {"builder", "evaluator", "glm-5.1"}
    load: int                         # 0 = idle, >0 = active tasks
    lease_state: str                  # "free" | "leased" | "dead" | "no_pane"
    priority_hint: int                # 0..100, higher = more preferred
    protected: bool                   # True = cannot be killed/reassigned

@dataclass
class SelectContext:
    task_type: str                    # "build" | "eval" | "plan" | "notify" | "research"
    required_capabilities: list[str]  # ["documentation", "harness.dag"]
    write_scope: list[str]            # ["docs/operator-arch-convergence/N1-*.md"]
    risk_tier: str                    # "critical" | "high" | "medium" | "low"
    preferred_model: str | None       # e.g. "glm-5.1", None = any
    sprint_id: str
    requesting_entry: str             # "E1" | "E2" | "E3" | "E4" | "E5" | "E6"
    now: datetime

@dataclass
class Decision:
    selected: Candidate
    rejected: list[tuple[Candidate, str]]  # (candidate, reason)
    trace_id: str                           # UUID for audit trail
```

### 3.3 Selection Algorithm (Priority Order)

The selector applies these filters in order; first match wins:

1. **Capability Filter**: Remove candidates missing any `required_capabilities`.
2. **Lease Filter**: Remove candidates with `lease_state != "free"`.
3. **Write-Scope Conflict Filter**: Remove candidates currently running a task whose write_scope overlaps with the new task's write_scope.
4. **Preferred Model Match**: If `preferred_model` is set, prefer candidates advertising that model.
5. **Load Sort**: Among remaining candidates, sort by `load` ascending (pick least loaded).
6. **Priority Hint Break**: If loads are equal, break by `priority_hint` descending.
7. **Deterministic Tie-Break**: If still tied, pick the first by `id` lexicographic order.

---

## 4. Entry-to-Thin-Caller Mapping

Each existing entry (E1-E6) becomes a **thin caller** that delegates to the unified selector instead of implementing its own routing:

| Entry | Current File | Thin Caller | What Changes |
|-------|-------------|-------------|--------------|
| E1 | `coordinator.sh:49-97,244-593` | `select(task_type="build", requesting_entry="E1")` | Replace 5 hardcoded pane vars + `choose_builder_pane()` with one `select()` call; persona discovery becomes candidate capability matching |
| E2 | `graph_scheduler.py:1029-1503` | `select(task_type="build", write_scope=node.write_scope, requesting_entry="E2")` | Replace internal ready-node assignment loop with `select()`; write_scope conflict check moves into selector |
| E3 | `autopilot.py:112-440` | `select(task_type="build", requesting_entry="E3")` for drain; scan logic unchanged | Replace `next_free_worker()` + manual pane iteration with `select()`; thresholds move to config |
| E4 | `pane_lease.py:132-190` | `select()` is called *before* `acquire_lease()` | Lease broker stays as-is; it becomes a post-selection step. TTL moves from constant to `SelectContext`-derived |
| E5 | `chain-watcher.sh:85-101` | `select(task_type="plan", requesting_entry="E5")` | Replace hardcoded fallback target + persona regex with `select()`; throttle window moves to config |
| E6 | `dispatch_scheduler.py:55-199` | `select(task_type="eval", requesting_entry="E6")` | Replace `PROTECTED_PANES` list + `DEFAULT_SPILLOVER_POOL` + round-robin with `select()`; protected flag moves to `Candidate.protected` |

### Thin Caller Pattern

```python
# Before (E1 example — coordinator.sh)
dispatch_to_builder() {
  local pane=$(choose_builder_pane)  # hardcoded fallback
  tmux send-keys -t "$pane" ...
}

# After (thin caller)
dispatch_to_builder() {
  local decision=$(selector_client select \
    --task-type build \
    --entry E1 \
    --sprint "$SPRINT_ID" \
    --capabilities "builder")
  local pane=$(echo "$decision" | jq -r '.selected.id')
  tmux send-keys -t "$pane" ...
}
```

---

## 5. Drift Guard Rules

### 5.1 Registration Requirement

Any new scheduling entry point (beyond E1-E6) MUST:

1. Call `select()` through the unified selector.
2. Be registered in the entry registry (`entries.yaml` or equivalent).
3. Pass CI validation that checks no hardcoded pane/model/session values exist.

### 5.2 CI Enforcement

```yaml
# .solar/harness/ci/drift_guard.yaml
rules:
  - id: DG-001
    name: no_hardcoded_pane_ids
    pattern: 'solar-harness(-lab)?:\d\.\d'
    scope: 'lib/**/*.py'
    severity: error
    message: "Hardcoded pane ID found. Use select() instead."

  - id: DG-002
    name: no_hardcoded_session_names
    pattern: '(SESSION_NAME|LAB_SESSION_NAME)\s*=\s*"'
    scope: 'lib/**/*.sh'
    severity: error
    message: "Hardcoded session name found. Use selector config."

  - id: DG-003
    name: entry_must_register
    check: |
      # Any file calling tmux send-keys or dispatch_to_* must import selector
      grep -rn 'tmux send-keys\|dispatch_to_' lib/ --include='*.sh' --include='*.py' | \
      while read line; do
        file=$(echo "$line" | cut -d: -f1)
        grep -q 'selector_client\|from.*selector' "$file" || fail "$file uses dispatch without selector"
      finished
    severity: error
    message: "Dispatch entry not using unified selector."

  - id: DG-004
    name: no_magic_thresholds
    pattern: '(DEADLOCK_STALL_SEC|STALL_SEC|BACKLOG_THRESHOLD|DEFAULT_TTL)\s*=\s*\d+'
    scope: 'lib/**/*.py'
    severity: warning
    message: "Magic threshold found. Move to selector config."
```

### 5.3 Exemption Process

Existing entries (E1-E6) are **grandfathered** until their thin-caller migration is finished. Each migration must:

1. Create the thin caller.
2. Run dual-write mode (old path + selector, compare results).
3. Remove old hardcoded path.
4. Pass CI drift_guard rules.

The exemption is tracked per-entry in `entries.yaml`:

```yaml
entries:
  E1:
    file: coordinator.sh
    migrated: false
    exempt_until: "2026-06-15"
  E2:
    file: graph_scheduler.py
    migrated: false
    exempt_until: "2026-06-15"
  # ...
```

### 5.4 New Entry Checklist

When adding E7+:

- [ ] Entry calls `select()` for all routing decisions.
- [ ] Entry is registered in `entries.yaml` with unique ID.
- [ ] No hardcoded pane IDs, session names, or magic thresholds in the new file.
- [ ] CI drift_guard passes (DG-001 through DG-004).
- [ ] Integration test verifies entry uses selector (mock selector, assert `select()` was called).

---

## 6. Configuration Externalization

All hardcoded values discovered in the inventory move to a single config:

```yaml
# selector_config.yaml
session_names:
  main: solar-harness
  lab: solar-harness-lab

panes:
  protected:
    - id: solar-harness:0.0
      role: notify
    - id: solar-harness:0.1
      role: planner
    - id: solar-harness:0.2
      role: observer
  pool:
    - id: solar-harness:0.3
      capabilities: [evaluator, architect]
    - id: solar-harness-lab:0.0
      capabilities: [builder]
    - id: solar-harness-lab:0.1
      capabilities: [builder, evaluator]
    - id: solar-harness-lab:0.2
      capabilities: [builder, evaluator]
    - id: solar-harness-lab:0.3
      capabilities: [builder, evaluator, architect]

thresholds:
  deadlock_stall_sec: 300
  stall_sec: 900
  backlog_threshold: 3
  lease_ttl_sec: 600
  chain_watcher_throttle_sec: 60

statuses:
  terminal: [passed, failed, skipped]
  active: [dispatched, reviewing, running]
  ready: [ready]
```

---

## 7. Migration Candidates and Kill Criteria

### Candidate A: Centralized Selector Service (Recommended)

| Aspect | Detail |
|--------|--------|
| Description | Single `selector.py` module with `select()` function; all entries import and call it |
| Pros | Zero network overhead; deterministic; easy to test |
| Cons | Requires all entries to be Python-callable (shell entries need CLI wrapper) |
| Kill Criteria | If `select()` call adds >50ms latency to any dispatch path (measured by P99 benchmark), downgrade to Candidate B |

### Candidate B: Selector-as-CLI

| Aspect | Detail |
|--------|--------|
| Description | `selector_client` bash-callable CLI wrapping `select()`; shell entries call it directly |
| Pros | Works with both shell and Python entries; no import complexity |
| Cons | Subprocess overhead per call (~30ms); JSON parsing in shell |
| Kill Criteria | If subprocess overhead causes >100ms total dispatch latency, escalate to Candidate A with shell shim |

### Candidate C: Selector-as-HTTP-Service (Excluded)

| Aspect | Detail |
|--------|--------|
| Description | Microservice exposing `select()` over HTTP |
| Kill Reason | Over-engineered for single-machine tmux dispatch; adds network dependency, port management, and failure modes that don't exist in the current architecture. Eliminated per architecture guard simplicity-first principle. |

---

## 8. Acceptance Mapping

| Acceptance ID | Criterion | Spec Section |
|---------------|-----------|-------------|
| A-N1-1 | List >=4 existing scheduling entries with hardcoded points | §2 (6 entries: E1-E6, each with file/line/hardcoded-points table) |
| A-N1-2 | Selector function signature locked: `select(candidates, context) -> decision` | §3.1 (full signature), §3.2 (data types), §3.3 (algorithm) |
| A-N1-3 | Each entry mapped to a thin caller using the new selector | §4 (6-row mapping table + thin caller pattern example) |
| A-N1-4 | drift_guard rules listed (any new entry must register or fail CI) | §5 (DG-001..DG-004 rules, exemption process, new-entry checklist) |

---

## Appendix: Cross-Reference

- Contract requirement: REQ-000 (unified selector), REQ-001 (eliminate hardcoded drift points)
- Downstream consumers: N4 (migration plan uses thin-caller mapping), N5 (traceability includes selector acceptance)
- Architecture guard: `package_boundary=spec_only`, `core_patch_allowed=false` — this document prescribes changes but does not implement them.
