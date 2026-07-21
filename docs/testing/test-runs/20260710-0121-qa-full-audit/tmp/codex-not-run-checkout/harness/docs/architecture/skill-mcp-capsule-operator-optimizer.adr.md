# ADR: Skill / MCP-Capability / Capability-Capsule / Physical-Operator / APO Four-Tier Registry Architecture

**ADR-ID**: `adr-skill-mcp-capsule-operator-optimizer-v1`
**Sprint**: `sprint-20260524-134738`
**Status**: Draft
**Date**: 2026-05-24
**Author**: solar-harness-lab:0.3 (S2)

---

## Context

The Solar Harness control plane currently has five distinct concepts handled by ad-hoc code with no shared formalism:

1. **Physical Operator** — a running pane/process with a model binding, quota, and lifecycle state  
   (managed by `lib/operator_runtime.py:60` `load_registry` + `lib/logical_operator_router.py:56` `get_candidates`)
2. **Skill** — a named, versioned capability recipe with readiness levels and injectable prompts  
   (managed by `lib/solar_skills.py:1700` `_load_registry` + `lib/solar_skills.py:1695` `REGISTRY_PATH`)
3. **MCP Capability** — an external tool endpoint surfaced through the Model Context Protocol  
   (tracked by `lib/capability_registry.py:60` `_ensure_capabilities_table` + `schemas/capability.schema.json`)
4. **Capability Capsule** — a bundled unit combining Skill + MCP bindings + Policy + Contract + Verification rules, submitted as an atomic dispatch unit  
   (concept; distinct from the existing State Capsule, see §Naming Collision below)
5. **APO (Agent Plan Optimizer)** — the heuristic optimizer that selects and scores physical plans  
   (sprint `sprint-20260523-agent-plan-optimizer-foundation`, not yet integrated with registries 1-4)

Without a unified registry architecture, each new capability adds its own lookup path, policy bypass risk, and governance gap. The APO cannot compose multi-step plans reliably because it has no machine-readable registry of what skills and MCP tools are available, what policy guardrails apply, or which physical operators can execute them.

---

## Naming Collision — Capability Capsule vs State Capsule

**Critical disambiguation**: The existing `schemas/capsule-schema.yaml` defines a **State Capsule** — a latent-state transfer structure for handoff/plan/eval documents (fields: `goal`, `facts_established`, `changes_made`, `risks`, `open_questions`, `required_next_action`, `recursion_round`, `topology`). This is a sprint context snapshot, not a capability unit.

The new concept defined in this ADR is a **Capability Capsule**:
- A bundled dispatch unit combining `Skill + MCP bindings + Policy + Contract + Verification rules`
- Uses field `capability_capsule_id` as the canonical identifier
- Accepts `execution_capsule_id` as a deprecated compatibility alias for one migration cycle
- Schema defined in `schemas/draft/capability-capsule.v1.draft.json`
- Does NOT replace or modify `schemas/capsule-schema.yaml`

All new references in this ADR and downstream schemas use `capability_capsule_id` / `Capability Capsule` to distinguish from the State Capsule. Legacy `execution_capsule_id` references are compatibility-only.

---

## Decision: Four-Tier Registry Architecture

```
APO (Agent Plan Optimizer)
         │
         ├─► Skill Registry         (solar_skills.py registry.yaml)
         │         │
         ├─► Capability Capsule Registry      (capability-capsule.v1.draft.json — NEW)
         │         │
         └─► Operator Registry      (operator_runtime.py + physical-operators.schema.v2.draft.json)
                   │
                   └─► MCP Capability Registry  (capability_registry.py + capability.schema.json)
                                   │
                                   └─► actual MCP servers / tools
```

The APO always resolves through the registry stack. It **never** calls an MCP server directly; the MCP Capability Registry is the single gateway, with policy guards applied at the `capability_registry.py:186` `cmd_query` boundary.

---

## §A — Three Skill Roles

Each Skill entry (schema: `schemas/draft/skill.v2.draft.json`) declares exactly one `role`:

| Role | Description | Effect |
|------|-------------|--------|
| `macro` | Decomposition hint — expands a task into sub-tasks | Advisory; APO may ignore with `macro_override=true` |
| `implementation` | Executable recipe — concrete steps, MCP tool list, verification contract | APO assembles physical plan from this |
| `enforcer` | Mandatory gate — blocks dispatch until satisfied | Hard stop; cannot be overridden without `P0_BYPASS` flag |

**Rationale (A)**: Conflating role types led to enforcer skills being silently skipped when treated as advisory macros. Explicit `role` field enforces correct handling at `solar_skills.py:1700` `_load_registry` → APO scoring phase.

---

## §B — Skill Registry v2 Fields

Schema: `schemas/draft/skill.v2.draft.json`

New required fields over v1:
- `role`: one of `macro | implementation | enforcer`
- `skill_version`: semver string
- `mcp_tools`: list of required MCP capability tokens (`capability.schema.json` pattern `^[a-z][a-z0-9_.:-]*$` — see `schemas/capability.schema.json:8`)
- `policy_refs`: list of policy IDs that govern execution
- `verification_contract`: inline or `$ref` to contract schema

Preserved from v1: `name`, `status`, `description`, `injectable`, `executable`, `promoted_at`, `promoted_by`.

---

## §C — MCP Capability Registry Integration

The `capability_registry.py:60` `_ensure_capabilities_table` function maintains a SQLite table `(capability TEXT, provider TEXT, level INT, status TEXT)`. The APO resolves MCP tools through this table:

1. APO asks: "which providers offer `tool.X` at level ≥ 3?"  (`capability_registry.py:186` `cmd_query`)
2. Registry returns ranked providers (by `level DESC`)
3. APO applies policy guard (`policy_refs` from Skill entry) — operators not satisfying policy are excluded
4. Surviving providers become candidate physical operators

The `schemas/draft/mcp-capability.v1.draft.json` schema extends `schemas/capability.schema.json` with:
- `endpoint_type`: `mcp_stdio | mcp_sse | mcp_http`
- `input_schema`: JSON Schema for tool input
- `output_schema`: JSON Schema for tool output
- `auth_requirements`: list of required auth token kinds
- `rate_limits`: per-minute and per-hour quotas

---

## §D — Capability Capsule Definition

Schema: `schemas/draft/capability-capsule.v1.draft.json`

A Capability Capsule bundles:
- `capability_capsule_id`: unique capsule identifier (distinct from State Capsule)
- `skill_id` + `skill_version`: resolved Skill entry
- `mcp_bindings`: map of `mcp_tool_token → provider_id` (resolved from registry)
- `policy_guard`: list of policy check results (pass/fail/waived)
- `contract`: acceptance criteria in machine-readable form
- `verification_rules`: list of post-execution checks
- `timeout_seconds`: hard limit
- `created_at`, `sprint_id`, `node_id`: provenance

Capability Capsule is the unit resolved before `operator_runtime.py:325` `submit()`. The `task_envelope` already requires `task_id, sprint_id, node_id, operator_id, task_type, objective` (see `operator_runtime.py:320` `_REQUIRED_ENVELOPE_KEYS`). Capability Capsule resolution adds pre-resolved skill/MCP/policy/effect verification before envelope creation.

---

## §E — Physical Operator Addendum

Schema: `schemas/draft/operator-profile.addendum.v1.draft.json`

Extends `schemas/physical-operators.schema.v2.draft.json` operator entries with APO-specific fields:
- `skill_affinity`: list of `skill_id` patterns this operator handles well
- `mcp_capabilities`: list of MCP capability tokens available to this operator
- `apo_score_weights`: per-dimension heuristic weight overrides
- `compat_mode`: `"warn"` when addendum fields are missing (never reject)

The `compat_mode: missing/unknown → warn` policy matches the baseline established in `schemas/physical-operators.schema.v2.draft.json:9` `"missing_field_policy": "warn"`.

---

## §F — APO Optimizer Flow (6-Step Pipeline)

```
[1] task arrives
      ↓
[2] APO resolves matching Skills (role=implementation) from registry
    → solar_skills.py:1700 _load_registry → filter by task_type, tags
      ↓
[3] For each candidate Skill: resolve MCP tool bindings
    → capability_registry.py:186 cmd_query per mcp_tools[] entry
      ↓
[4] Apply policy guard per skill.policy_refs
    → enforcer Skills (role=enforcer) run as gates; blocked → abort
      ↓
[5] Heuristic scoring: score each (Skill, MCP binding, Operator) triple
    → operator_runtime.py:274 get_operator_runtime_state → idle/available check
    → logical_operator_router.py:65 select_actor → candidate ordering
    → APO applies config-driven heuristic weights (see §H)
      ↓
[6] Emit physical plan + assemble Capability Capsule plan → submit to operator_runtime.py:325 submit()
    → evidence logged to evidence_ledger.py
```

No learned model in v1. Steps 2-5 are deterministic given config. Kill-switch: `OPTIMIZER_MODE=passthrough` bypasses steps 2-5 and submits directly.

---

## §G — Why MCP Must Go Through Registry (5 Justifications)

1. **Policy enforcement**: Direct MCP calls bypass `policy_refs` guards. Registry is the single choke point where policy checks run.
2. **Provider portability**: MCP server endpoints change (host, port, auth). Registry decouples tool tokens from physical endpoints — one config change reroutes all callers.
3. **Quota accounting**: `mcp-capability.v1.draft.json` declares `rate_limits`. Registry can reject calls before they hit the server.
4. **Capability level gating**: `capability_registry.py:218` scorecard distinguishes `dead_end (1) / basic_usable (2) / default_usable (3) / closed_loop (4)`. APO can require level ≥ 3 without knowing provider internals.
5. **Audit trail**: All MCP resolutions logged as events (`capability_registry.py:41` `_emit_event`), creating an immutable evidence trail for post-mortem and compliance.

---

## §H — Heuristic-First Rollout

| Phase | Condition | Behavior |
|-------|-----------|----------|
| v1 — config-driven | Always | Deterministic weights from `apo_score_weights` in operator addendum |
| v1.1 — runtime telemetry | After 50 dispatches | Fold in latency/error-rate signals from `operator_runtime.py:299` `get_operator_status` |
| v2 — learned model | When v1 stable for 2 sprints | Optional ML ranker; gated behind `OPTIMIZER_RANKING=ml` env flag |
| Passthrough mode | `OPTIMIZER_MODE=passthrough` | Skip scoring; dispatch to first available operator |

The v1 rollout does not require ML infrastructure. All scoring logic is config-editable without redeployment.

---

## §I — APO-Foundation Conflict Avoidance

The `sprint-20260523-agent-plan-optimizer-foundation` sprint owns baseline APO files. This sprint (134738) creates **new** schema files and documentation only. Rules:
- No modification of any file produced by the foundation sprint
- No modification of `lib/capability_registry.py`, `lib/solar_skills.py`, `lib/operator_runtime.py`, `lib/logical_operator_router.py`, `schemas/physical-operators.schema.v2.draft.json`, `schemas/capability.schema.json`, `schemas/capsule-schema.yaml`
- Schema files here are `draft/` — they do not replace production schemas

---

## §J — Risks and Mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| `capability_capsule_id` vs legacy `execution_capsule_id` naming drift in downstream code | Medium | New schemas use `capability_capsule_id`; loader accepts legacy alias for one migration cycle |
| Policy guard added to hot path adds latency | Low | Policy checks are registry reads (SQLite); < 5ms typical |
| Operator addendum compat_mode silently drops new fields | Low | `compat_mode: warn` emits log event; dashboards can alert |
| Capability Capsule not adopted if APO foundation defers integration | Medium | Capability Capsule schema is a draft; adoption gated on APO v1 stabilization |
| Skill role migration: existing skills have no `role` field | High | v2 schema defaults `role: implementation` when absent; ADR mandates migration guide in S3 |

---

## Existing Module Inventory (File:Line Citations)

| Module | Location | Relevance |
|--------|----------|-----------|
| `capability_registry.py` | `lib/capability_registry.py:60` `_ensure_capabilities_table` | MCP capability persistence; `lib/capability_registry.py:186` `cmd_query` is the APO query entry point |
| `solar_skills.py` | `lib/solar_skills.py:1700` `_load_registry`; `lib/solar_skills.py:1695` `REGISTRY_PATH` | Skill registry loader; the `registry.yaml` is the source of truth for Skill entries |
| `operator_runtime.py` | `lib/operator_runtime.py:60` `load_registry`; `lib/operator_runtime.py:325` `submit()`; `lib/operator_runtime.py:320` `_REQUIRED_ENVELOPE_KEYS` | Physical operator lease/state; `submit()` is the ECapsule delivery point |
| `logical_operator_router.py` | `lib/logical_operator_router.py:56` `get_candidates`; `lib/logical_operator_router.py:65` `select_actor`; `lib/logical_operator_router.py:17` `P0_LOGICAL_OPERATORS` | Maps logical operator types to candidate actors; APO uses this for ordering |
| `physical-operators.schema.v2.draft.json` | `schemas/physical-operators.schema.v2.draft.json:9` `compat_mode.missing_field_policy: warn` | Establishes `warn` (not reject) policy for missing fields; addendum inherits this |
| `capability.schema.json` | `schemas/capability.schema.json:8` `pattern: ^[a-z][a-z0-9_.:-]*$` | MCP capability token pattern; all `mcp_tools` lists in Skill v2 must match this pattern |
| `capsule-schema.yaml` | `schemas/capsule-schema.yaml:1` header | **State Capsule** (NOT Capability Capsule); sprint context transfer struct — distinct from capability-native dispatch |

---

## Consequences

**Positive**:
- APO has a machine-readable registry stack to compose plans from
- Policy enforcement is centralized at registry boundaries, not scattered in caller code
- `compat_mode: warn` allows incremental field adoption without flag days
- Capability Capsule naming avoids collision with existing State Capsule infrastructure while preserving legacy Execution Capsule compatibility

**Negative / Trade-offs**:
- 4 new schemas require adoption by APO implementation sprint
- Skill `role` migration required for existing registry entries
- Additional registry reads added to dispatch hot path (mitigated: SQLite, < 5ms)

---

## Alternatives Rejected

1. **Inline policy in each caller**: Rejected — creates drift, no audit trail, bypasses quota gating.
2. **Single monolithic registry**: Rejected — merging Skills/MCP/Operators into one schema couples unrelated concepts; harder to evolve independently.
3. **Direct APO → MCP calls**: Rejected — see §G; policy bypass, no portability, no quota accounting.

---

Knowledge Context: solar-harness context inject used (pre-injected in dispatch `<solar-unified-context>`)
