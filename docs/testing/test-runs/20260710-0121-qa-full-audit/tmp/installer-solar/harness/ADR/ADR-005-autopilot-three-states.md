# ADR-005 — Autopilot Three-State Pane Model

**Status**: Accepted  
**Date**: 2026-05-09  
**Sprint**: sprint-20260509-solar-product-platform S6

## Context

The existing coordinator uses a simple binary: pane has lease → skip; no lease → dispatch.  
This causes two failure modes:

1. **Deadlock squeeze**: A pane holds a live lease but has no active Claude Code prompt
   (session crashed, SIGHUP, or frozen). Coordinator sees "busy" and never reclaims.
2. **Single-builder squeeze**: Only one builder pane exists; all queued tasks starve
   because coordinator checks lease first and exits without trying other panes.

## Decision

Three-state classification per pane:

```
no_pane  → tmux pane does not exist → clear assignment + emit pane_gone event
busy     → pane exists + lease not expired + active prompt → wait (do NOT reclaim)
dead     → pane exists + (no lease OR expired lease) → eligible for reclaim
```

Stall detection for `busy` → `stalled` promotion:
- If pane has held lease for > `AUTOPILOT_DEADLOCK_STALL_SEC` (default 300s)
- AND `tmux capture-pane` shows no Claude Code prompt indicators (❯ ⏵ spinner)
- → classify as stalled; release lease; re-enqueue sprint

## Consequences

- Normal busy builders are never interrupted (lease < 300s old)
- Crashed/frozen builders are reclaimed after stall threshold
- Single-builder squeeze: `next_free_worker()` iterates all panes, logs skip reason per pane,
  queues explicitly via task_queue.py when no worker is available (not silent drop)
- Quarantine inbox checked as a fault class (hook_failure) to surface prompt residue issues
