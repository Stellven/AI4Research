# Architecture Design: Lease-based Model Fleet Runtime

## Knowledge Context
Knowledge Context: solar-harness context inject used

## 1. Executive Summary
This document defines the architectural upgrade of the Solar Harness execution engine from a **Pane-as-Physical-Operator** model to a decoupled **Lease-based Model Fleet Runtime**. 

The legacy architecture scheduled tasks directly to tmux panes (treating them as physical operators), leading to process/state coupling and vulnerability to terminal environment drifts. The upgraded architecture introduces two core abstractions:
* **AgentActor**: A logical execution unit defining agent role, operator class, capabilities, quotas, and security policies.
* **ActorHost**: A physical execution carrier (environment) housing an active actor.

By separating the actor's logical identity from its host carrier, the runtime supports heterogeneous host environments (e.g., local tmux panes, cloud worktrees, or secure sandbox containers) and implements process-safe lease brokering with real-time evidence journaling.

---

## 2. Why tmux is a Host Carrier, Not a Scheduler/RPC Endpoint

### 2.1 The Fragility of Tmux-Direct Scheduling
In previous versions, the scheduler targeted tmux panes directly using session/window/index addresses. Tmux is a terminal multiplexer designed for human interactive display, not an RPC daemon or a resource scheduler. Direct tmux scheduling suffers from:
1. **Index Drift**: Splitting a pane, closing adjacent panes, or reordering windows renumbers pane indices (e.g., `.0`, `.1`). Commands targeted at a specific index are sent to whichever shell currently holds that index, leading to command injection leaks and destructive state changes.
2. **Title Out-Of-Sync**: Terminal escapes (e.g., `printf "\033]2;...\007"`) are used to display statuses on pane titles. If a shell is blocked, crashed, or redirects stdout, these escapes fail to execute, leaving stale metadata.
3. **No Execution Boundary / Backpressure**: Direct terminal execution (`tmux send-keys`) does not provide standard stream control, exit codes, or crash detection without wrap-around logging layers. There is no API-level backpressure or request queuing.
4. **Credential Exposure Risk**: Sending keys directly to a terminal pane leaves credentials, tokens, or feature flags visible in shell history (`.zsh_history`) and the terminal scrollback buffer.

### 2.2 Shift to Tmux as a Host Carrier
Under the new model, tmux is classified strictly as an **ActorHost** carrier:
* Tmux panes are referenced solely by their stable, globally unique pane IDs (e.g., `%92`, `%103`) which never renumber or drift during layout shifts.
* Pane indices are treated strictly as read-only display metadata.
* Communication with the actor daemon runs via an inbox-outbox file queue and process-safe Unix locks, completely bypassing `tmux send-keys` for active tasks.

---

## 3. Abstraction Specifications

### 3.1 AgentActor Schema
An `AgentActor` represents the logical profile of an agent executor. It defines the capabilities, policies, and leasing constraints.

```json
{
  "$schema": "../schemas/agent-actor.schema.json",
  "actor_id": "actor.claude.opus.planner.01",
  "operator_class": "GoogleStack",
  "host_id": "host.tmux.solar-harness.01",
  "enabled": true,
  "lease": {
    "state": "idle",
    "lease_id": null,
    "ttl_sec": 2700,
    "leased_at": null,
    "expires_at": null
  },
  "capability": {
    "planning": 5,
    "coding": 4,
    "debugging": 4,
    "testing": 4,
    "research": 5,
    "long_context": 5,
    "multimodal": false
  },
  "quota": {
    "billing_pool": "google_oauth_interactive",
    "reserve_for": ["ARCH_DESIGN", "ROOT_CAUSE_DEBUG", "RESEARCH_SYNTHESIS"],
    "on_exhausted": "disable_and_fallback"
  },
  "policy": {
    "write_files": "ask_or_patch_only",
    "secrets_access": "denied",
    "network": "restricted"
  },
  "evidence": {
    "task_log_dir": "run/agent-actors/actor.claude.opus.planner.01/",
    "ledger_path": "run/agent-actors/ledger.jsonl"
  },
  "fallback_ladder": [
    "actor.claude.sonnet.builder.01",
    "actor.gemini.pro.planner.01"
  ],
  "persona_binding": {
    "persona_path": "personas/planner.md",
    "role": "planner"
  }
}
```

### 3.2 ActorHost Schema
An `ActorHost` represents the execution environment. It defines the host type, state, and address metadata.

```json
{
  "$schema": "../schemas/actor-host.schema.json",
  "host_id": "host.tmux.solar-harness.01",
  "host_type": "tmux_pane",
  "lifecycle": "alive",
  "address": {
    "session": "solar-harness-multi-task",
    "window": "mt-20260523-010345-sprint-20260523-lease-based-m",
    "pane_id": "%103"
  },
  "heartbeat": {
    "path": "run/operator-status/mini-claude-opus-planner.json",
    "max_delay_sec": 10
  },
  "probe": {
    "command": "tmux has-session -t solar-harness-multi-task",
    "type": "shell"
  }
}
```

---

## 4. Host Type Registry

The Model Fleet Runtime supports a registry of host types. While some are P0 requirements, others are stubbed for future expansion.

| Host Type | Implementation Status | Purpose / Description |
|-----------|-----------------------|----------------------|
| `tmux_pane` | **Implemented (P0)** | Local long-running terminal environments managed via stable tmux pane IDs. |
| `codex_worktree` | Stubbed | Local Git worktree directories managed dynamically by Codex. |
| `codex_cloud` | Stubbed | Remote developer worktrees running in cloud containers. |
| `antigravity_managed_env` | Stubbed | Google Antigravity CLI executing tasks in sandboxed client instances. |
| `claude_code_session` | Stubbed | Active interactive terminal loops running within the Claude Code tool. |
| `local_mlx_process` | Stubbed | Local inference pipelines running directly on Apple Silicon MLX backends. |
| `ssh_devbox` | Stubbed | Remote target machines accessible over secure shell tunnels. |
| `docker_sandbox` | Stubbed | Ephemeral containerized workspaces providing strict process isolation. |

---

## 5. Lease Broker State Machine

The Lease Broker orchestrates actor allocation dynamically, ensuring concurrency limits, billing splits, and fallback capabilities are respected.

### 5.1 State Lifecycle Flow
The broker enforces the following transition sequence:

```text
       ┌───────────[ Register / Create ]
       │                     ↓
       │                 [ WARMING ]
       │                     ↓
       ├─────────────────→ [ IDLE ] ←─────────────────────────┐
       │                     ↓                                │
       │                [ LEASED ] (Acquired by scheduler)    │
       │                     ↓                                │
       │               [ RUNNING ] (Executing task envelope)   │
       │                     ↓                                │
       │              [ DRAINING ] (SIGTERM cleanup / exit)    │
       │                     ↓                                │
       └─────────────────→ [ COOLDOWN ] ──────────────────────┘
                             │
                             ├─→ [ ERROR ]
                             ├─→ [ QUOTA_EXHAUSTED ]
                             ├─→ [ AUTH_EXPIRED ]
                             ├─→ [ DISABLED ]
                             └─→ [ NEEDS_HUMAN_REVIEW ]
```

### 5.2 Transition Logic
1. **`idle` → `leased`**: Triggered when `submit()` requests an actor matching the node's required capabilities. Atomic filesystem lock (`fcntl.flock`) prevents duplicate claims.
2. **`leased` → `running`**: The corresponding host worker picks up the task from its inbox queue.
3. **`running` → `draining`**: Triggered on task completion, SIGTERM timeout, or actor cancellation.
4. **`draining` → `cooldown`**: Post-run stabilization phase to prevent rapid agent cycling.
5. **`cooldown` → `idle`**: Actor is released back into the available pool.
6. **Failure paths**: If health probes fail, tokens expire, or quotas hit limits, the actor transitions to terminal diagnostic states (`ERROR`, `AUTH_EXPIRED`, `QUOTA_EXHAUSTED`, `DISABLED`), prompting the scheduler to fall back to the next candidate on the `fallback_ladder`.

---

## 6. Evidence Ledger Journaling

To guarantee absolute auditability and enforce zero-secrets policies, every execution leaves an immutable trail in the `ledger.jsonl` under `run/agent-actors/`.

### 6.1 Record Contract
Each JSON line represents a single atomic state event:
* **`event_type`**: `lease_acquired` | `task_started` | `heartbeat_recorded` | `output_streamed` | `lease_released`
* **`task_envelope_snapshot`**: Logged at start, with all credential values scrubbed from keys (e.g. `api_key=sk-...` to `api_key=[SCRUBBED]`).
* **`stream_fragment`**: Standard output and error records processed line-by-line via real-time secret-scrubbing regex engines to prevent key leaks.
* **`verifier_decision`**: Signed audit assertions recorded at the termination of the task.

---

## 7. Compatibility Migration Plan

To ensure zero downtime, existing configurations must load transparently via compatibility layers.

### 7.1 Configuration Translation
1. **Dynamic Translation**: The legacy `physical-operators.json` is read by `operator_runtime.py`.
2. **Actor Mapping**: Every legacy operator name (e.g. `mini-claude-opus-planner`) generates a virtual `AgentActor` with `actor_id` as `actor.<operator_id>` and a matching `fallback_ladder`.
3. **Host Mapping**: The legacy `pane` property (e.g. `solar-harness-multi-task:*`) resolves to a virtual `ActorHost` (type: `tmux_pane`) dynamically querying the matching tmux pane ID at boot time.
4. **Alias Support**: APIs querying the registry accept both the legacy operator ID and the new `actor_id`.

---

## 8. Verification and Source Assertions

During the design phase, the following source claims were verified on the target system:
1. **Pane ID Stability**: Verified using `tmux list-panes -s -F "#{pane_id} #{pane_index}"`. Splitting and moving panes renumbered indices (e.g. `0` to `1`), but the pane ID (e.g. `%103`) remained completely stable.
2. **Process Title Behavior**: Verified that tmux pane titles can drift or remain generic unless active daemons enforce updates. Daemons running inside the host must write heartbeats to files rather than relying solely on stdout title codes.
3. **Secret Scrubbing Performance**: Verified that the regex-based `scrub_secrets` helper in `operator_runtime.py` successfully intercepts typical authorization tokens before writing to `result.json`.

---
