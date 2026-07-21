# APO Optimizer Flow — Integration Note

**Sprint**: `sprint-20260524-134738` S2
**Date**: 2026-05-24
**Status**: Draft — Design-only. No runtime code in this sprint.

---

## Purpose

This note describes how the Agent Plan Optimizer (APO) integrates with the four-tier registry stack defined in `skill-mcp-capsule-operator-optimizer.adr.md`. It is intended for the APO implementation sprint builder.

---

## Integration Points (File:Line)

| Step | Code Entry Point | Action |
|------|-----------------|--------|
| 1. Task arrival | `lib/graph_scheduler.py` (dispatch) | Task enters APO via scheduler |
| 2. Skill resolution | `lib/solar_skills.py:1700` `_load_registry` | Load all `status=stable` Skills from `registry.yaml` |
| 3. MCP binding | `lib/capability_registry.py:186` `cmd_query` | Per `mcp_tools[]` entry in Skill, query active providers at level ≥ 3 |
| 4. Policy guard | `lib/solar_skills.py` `policy_refs` field | For each `policy_id` in skill's `policy_refs`, run policy check |
| 5. Operator scoring | `lib/operator_runtime.py:274` `get_operator_runtime_state` + `lib/logical_operator_router.py:65` `select_actor` | Filter idle operators, apply heuristic weights |
| 6. Capability Capsule resolution | `schemas/draft/capability-capsule.v1.draft.json` + `lib/capability_capsules.py` | Resolve capsule; set `capability_capsule_id`, `resolved_mcp_bindings`, `effect_summary`, guard/resource attachments |
| 7. Submit | `lib/operator_runtime.py:325` `submit()` | Deliver capability-native envelope after runtime gate |

---

## Passthrough Mode

When `OPTIMIZER_MODE=passthrough` (env flag):
- Steps 2-5 are bypassed
- APO calls `operator_runtime.py:325 submit()` directly with minimal envelope
- Use for debugging, testing, or when registry data is not yet populated
- Kill-switch ensures APO never blocks dispatch during early rollout

---

## APO Heuristic Score Formula (v1)

For each candidate `(skill, mcp_binding_set, operator)` triple:

```
score = (
    latency_weight    * (1 - normalized_latency)  +
    error_rate_weight * (1 - error_rate)           +
    quota_headroom_weight * quota_fraction_remaining +
    skill_affinity_weight * affinity_match_flag
)
```

Where weights come from `apo_score_weights` in `schemas/draft/operator-profile.addendum.v1.draft.json`. Default weights: `0.3 / 0.3 / 0.2 / 0.2`. APO normalizes internally; sum need not equal 1.0.

`affinity_match_flag` = 1.0 if `skill.name` matches any pattern in operator's `skill_affinity[]`, else 0.0.

---

## Enforcer Skill Gate

Before scoring, APO runs **enforcer gate** (role=enforcer skills):

```python
for skill in all_skills:
    if skill["role"] == "enforcer":
        result = run_enforcer_check(skill)
        if result != "pass":
            # Abort entire plan; log to policy_guard in Capability Capsule
            raise EnforcerGateError(skill["name"], result)
```

The only bypass is `P0_BYPASS=true` env flag (requires explicit operator intervention, never automated).

---

## Evidence Ledger Integration

After `submit()`, APO/runtime writes to `lib/evidence_ledger.py`:
- `capability_capsule_id`
- `capsule_kind`
- `resolved_bindings`
- `effect_summary`
- `guard_results`
- `verification_results`
- timestamp

This creates an immutable record for post-mortem and compliance auditing.

---

## Rollout Sequence

1. **Sprint N (this sprint)**: Schema drafts only. No runtime code.
2. **Sprint N+1 (APO v1)**: Implement skill resolution (step 2) and MCP binding (step 3). Use passthrough mode for steps 4-6.
3. **Sprint N+2**: Implement enforcer gate (step 4) and heuristic scoring (step 5).
4. **Sprint N+3**: Full Capability Capsule runtime gate + evidence ledger integration (steps 6-7).

Each sprint can be independently verified against the schema contracts defined here.

---

## Known Gaps (Not Blocking v1 Launch)

- `policy_refs` check implementation: policy IDs are declared in skills but no policy runner exists yet
- `verification_rules` runner: Capability Capsule carries rules but verifier execution remains follow-up work
- `rate_limits` enforcement: `mcp-capability.v1.draft.json` declares limits but `capability_registry.py` doesn't enforce them yet
