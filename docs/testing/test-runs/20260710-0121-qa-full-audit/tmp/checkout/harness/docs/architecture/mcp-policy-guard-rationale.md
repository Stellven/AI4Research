# MCP Policy Guard — Rationale

**Sprint**: `sprint-20260524-134738` S2
**Date**: 2026-05-24
**Status**: Draft — Design-only. No runtime code in this sprint.

---

## Why MCP Must Route Through the Registry

The decision to require all MCP calls to go through `capability_registry.py` (and not allow direct APO → MCP calls) is a load-bearing architectural constraint. This document records the rationale for current and future implementors.

---

## Five Justifications

### 1. Policy Enforcement — Single Choke Point

Each Skill declares `policy_refs` (list of policy IDs). Policy checks run once, at registry resolution time, before any MCP call is made.

Without registry routing: each caller would need to independently implement policy checks. Divergent implementations create drift; some callers will skip checks under time pressure.

**Evidence**: This pattern is already established in `lib/operator_runtime.py:353-361` where operator state checks (`get_operator_runtime_state`) act as a gateway before `submit()`. The MCP registry layer extends this pattern to tool resolution.

---

### 2. Provider Portability

MCP server endpoints change: host, port, auth tokens, transport type. The `mcp-capability.v1.draft.json` schema stores `endpoint_url` / `launch_cmd` as data, not as hard-coded paths in callers.

When a provider migrates from `mcp_stdio` to `mcp_sse`: update one registry entry, all callers automatically route to the new transport. No code changes required.

This is directly analogous to how `lib/logical_operator_router.py:56` `get_candidates` decouples logical operator types from physical actor IDs via data bindings — changing a binding changes routing without editing DAG nodes.

---

### 3. Quota Accounting Before Dispatch

`mcp-capability.v1.draft.json` declares:
```json
"rate_limits": {
  "requests_per_minute": ...,
  "requests_per_hour": ...,
  "concurrent_max": ...
}
```

The registry can reject a dispatch before it ever hits the MCP server if rate limits would be exceeded. This prevents cascading failures from quota exhaustion (analogous to `operator_runtime.py:358` rejecting dispatch when operator state is `quota_exhausted`).

---

### 4. Capability Level Gating

`lib/capability_registry.py:218` `cmd_scorecard` distinguishes integration levels:
- Level 1: `dead_end` — provider exists but output is unusable
- Level 2: `basic_usable` — works but not reliable
- Level 3: `default_usable` — production-ready
- Level 4: `closed_loop` — fully automated with verification

APO can require level ≥ 3 for production dispatches without knowing provider internals. This gates experimental/degraded providers from production flows without modifying provider code.

---

### 5. Audit Trail

`lib/capability_registry.py:41` `_emit_event` logs every capability resolution as a structured event:
```python
entry = {"ts": _now(), "source": "capability_registry", "event": event, **payload}
```

This creates an immutable record of which provider was chosen for which task at which time. Essential for:
- Post-mortem analysis when a dispatch fails
- Compliance auditing (which external tools were called by which sprint)
- Detecting provider reliability drift over time

Direct MCP calls produce no such record.

---

## What This Means for Implementors

1. **Never import MCP server libraries directly in APO code**. Always call `capability_registry.py:186 cmd_query` first to get the provider and its endpoint details.

2. **Never hard-code MCP endpoints** in dispatch code. Endpoint details live in registry entries (schema: `mcp-capability.v1.draft.json`).

3. **Policy checks are not optional**. The enforcer Skill gate runs before MCP binding resolution. If an enforcer check fails, no MCP call is made.

4. **The passthrough mode** (`OPTIMIZER_MODE=passthrough`) bypasses heuristic scoring but does NOT bypass policy checks. This is intentional — policy is always enforced.

5. **Rate limit enforcement** is a future implementation item (see `apo-optimizer-flow-integration-note.md` Known Gaps). The schema declares the contract now so implementations can reference it.

---

## Alternatives That Were Rejected

| Alternative | Why Rejected |
|-------------|-------------|
| Direct APO → MCP calls (no registry) | No policy enforcement, no audit trail, hard-coded endpoints |
| Registry read-only (callers still call MCP directly) | Policy still scattered, no quota accounting |
| Per-caller policy middleware | Duplicates enforcement logic; one middleware will always lag |
| Disable policy for internal tools | Creates a bypass that external tools will eventually exploit via misclassification |

---

## Relationship to Existing Infrastructure

- `capability_registry.py` already implements the storage and query layer. This ADR extends it with APO-specific usage patterns.
- `capability.schema.json` defines the base schema. `mcp-capability.v1.draft.json` extends it with transport and rate-limit fields.
- `physical-operators.schema.v2.draft.json:9` established the `missing_field_policy: warn` precedent that `operator-profile.addendum.v1.draft.json` inherits.
