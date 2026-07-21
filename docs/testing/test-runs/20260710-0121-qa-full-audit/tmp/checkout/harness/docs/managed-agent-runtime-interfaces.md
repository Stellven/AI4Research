# Managed Agent Runtime Interfaces — Operator Guide

## Overview

Solar-Harness now exposes a stable runtime interface layer between
the coordinator/harness policy and the execution surfaces (hands).

Architecture:

```
Product Surface (CLI / Status UI / Contracts)
        ↓
Harness Policy (wake / graph / autopilot / evaluator)
        ↓
Runtime Interface Layer (Session API / Hand API / Worker API / Context Projection)
        ↓
Execution Hands (pane / shell / MCP / remote)
        ↓
Durable Facts (session events / immutable artifacts)
        ↓
Disposable Projections (status.json / status UI / context view)
```

## Key Principle

> Session log = durable facts. Harness = stateless policy. Hands = cattle.
> Context = projection, not source of truth.

## Session API

`SessionLog.get_events()` supports cursor-based pagination.

## Hand API

Four adapters: `mock`, `shell`, `pane`, `remote`. All require idempotency_key.

## Worker API

File-based register/heartbeat/lease. No daemon dependency.

## Context Projection

Never rewrites events. Provenance tracking built-in.

## Runtime Doctor

Now includes `interface_health`, with five sub-dimensions:

- `session_api`
- `hands_runtime`
- `worker_runtime`
- `context_projection`
- `chaos_suite`

## Chaos Suite

6 local, token-free failure scenarios:

- duplicate command idempotency
- destructive shell command denial
- shell secret redaction
- cancelled activity event
- worker lease expiry
- context projection no-rewrite plus redaction

## Non-Goals

- Does not replace coordinator or tmux panes.
- Does not introduce new always-on dependencies.
- Does not claim deterministic LLM replay.
