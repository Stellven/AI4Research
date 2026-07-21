# ADR-007: Solar Experience Memory Layer

**Date**: 2026-05-10
**Status**: Accepted
**Sprint**: sprint-20260509-205414

## Context

Solar Harness repeatedly encounters the same failure classes across sprints:
- C-u storms from pane residue not being cleared
- Coordinator dispatching to wrong panes or already-terminal sprints (terminal_phase_wake)
- status.json corruption where phase/status disagree
- Queue blocks where leases are held but builders stall
- Mis-dispatch to wrong incarnation or role

Each failure requires manual diagnosis. There is no systematic memory of what worked or what to avoid.

Inspiration: MIA (Memory-Inspired Architecture) — compact workflow memory instead of raw transcript replay.

## Decision

Implement a local deterministic v1 Experience Memory Layer with:

1. **Extract** — read terminal sprint artifacts (status.json, events.jsonl, handoff.md, eval.md) into compact trajectory records with secret stripping
2. **Detect** — identify 5 anti-pattern classes from trajectory features
3. **Compress** — cluster trajectories by (trigger_sig, pattern_class) into deduplicated entries
4. **Index** — SQLite + FTS5 for sub-100ms retrieval
5. **Query** — coordinator calls pre_dispatch(sid, action) before each dispatch
6. **Fail-open** — any error or timeout (50ms) → allow dispatch, never block
7. **Audit** — every decision written to experience/decisions.jsonl

## Anti-Pattern Classes

| Class | Description | Action |
|-------|-------------|--------|
| `c_u_storm` | >5 send-keys/C-u events in one sprint | advisory |
| `mis_dispatch` | Dispatched but never evaluated → failure | advisory |
| `status_corruption` | status=passed but outcome=failure, or phase/status mismatch | advisory |
| `terminal_phase_wake` | Coordinator woke a terminal sprint | **abort** |
| `queue_block` | >60min duration, 0 eval rounds, failure | advisory |

Only `terminal_phase_wake` triggers hard abort. All others are advisory.

## Alternatives Considered

### A1: Online gradient learning (Ruflo)
Rejected. Requires external runtime, online training infrastructure, MCP registration. Out of scope for v1.

### A2: Raw log replay
Rejected. Unbounded context (full transcript can be MB-sized). Violates 2KB advisory bound.

### A3: External vector DB (Chroma/Pinecone)
Rejected. Adds dependency, network call latency. SQLite+FTS5 achieves <100ms without network.

### A4: Block-by-default (only allow on explicit approval)
Rejected. Too risky. Any false positive blocks legitimate sprint progress. Fail-open is the right default.

## Constraints Satisfied

- **C1**: Only reads sprints/; writes to experience/ (read-only sprint artifacts)
- **C2**: Hook is fail-open + advisory default; only high-confidence terminal_phase_wake enforces
- **C3**: Backfill is idempotent (skips already-extracted sprints by trajectory file existence)
- **C4**: No new DB engine (SQLite is already in Solar's stack)
- **C5**: events.jsonl write path untouched (experience reads, never writes events.jsonl)
- **C6**: coordinator.sh patched in exactly one location (`dispatch_to_pane` entry); 25-line patch

## Rollback

To disable the experience hook without removing code:

```bash
export EXPERIENCE_HOOK=0
# or in coordinator environment:
echo 'EXPERIENCE_HOOK=0' >> ~/.solar/harness/.env
```

To fully remove: delete `experience_pre_dispatch()` from coordinator.sh and the hook call from `dispatch_to_pane`. The 5 lines in coordinator.sh are clearly marked.

## Consequences

- Coordinator gets advisory context before each dispatch without blocking behavior
- terminal_phase_wake class is now automatically aborted (previously required manual intervention)
- All decisions are auditable via experience/decisions.jsonl
- System accumulates knowledge across sprints; quality improves over time
- v2 can add semantic similarity matching and cross-sprint pattern correlation
