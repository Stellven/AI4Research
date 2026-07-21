# N4: Migration & Compatibility Plan

> Sprint: `sprint-20260527-operator-architecture-convergence`
> Node: N4 | Gate: G_PLAN
> Status: spec_only (no code changes)
> Evidence Policy: no_code=true, no_lib_modification=read-only
> Depends on: N1 (unified selector), N2 (provider adapter registry), N3 (actor derivation)

---

## 1. Purpose

N1-N3 define three new abstractions (unified selector, provider adapter registry, actor derivation) that replace the current scattered hardcoded scheduling, provider handling, and actor maintenance. This document specifies how to migrate from the current state to the converged architecture without breaking existing functionality.

Three migration tracks run in parallel, each following a 3-phase ladder (dual-write → canary → deprecated). A single environment flag provides emergency rollback. Per-phase verification gates ensure parity at each step.

---

## 2. Migration Tracks Overview

| Track | What Changes | Source Spec | Current State | Target State |
|-------|-------------|-------------|---------------|--------------|
| T1: Selector | E1-E6 scheduling entries → thin callers using `select()` | N1 §4 | 6 entries with hardcoded pane/model/session values | All entries call `select(candidates, context)` |
| T2: Registry | Scattered provider handling → `ProviderAdapterRegistry` | N2 §3 | Per-call-site auth/headers/error handling | `register/get/hot_reload` via registry |
| T3: Actor | Manual actor JSON → `derive_actor()` | N3 §3 | 15 hand-maintained actors in `agent-actors.json` | 13 derived + 2 exempt |

---

## 3. Three-Phase Ladder (Per Track)

Each track follows the same 3-phase progression:

### Phase 1: Dual-Write (Shadow Mode)

- New path runs alongside old path
- Old path is still authoritative (its result is used)
- New path result is logged but NOT used for dispatch
- Compare old vs new results; flag divergences
- Gate: zero functional regressions; divergence log exists

### Phase 2: Canary (Gradual Cutover)

- Traffic shifts from old to new path in stages: 10% → 50% → 100%
- 10%: New path is authoritative for 10% of dispatches; old path still runs as shadow
- 50%: New path handles majority; divergence monitoring continues
- 100%: New path is sole authority; old path runs as shadow only
- Gate: parity test passes at each stage; no increase in dispatch latency P99

### Phase 3: Deprecated (Old Path Removed)

- Old path code is removed
- Only new path remains
- CI drift_guard rules block any regression
- Gate: old path code deleted; all CI rules pass

---

## 4. Track T1: Selector Migration

### T1 Phase 1: Dual-Write

| Step | Action | Verification |
|------|--------|-------------|
| T1-P1-1 | Implement `select()` function per N1 §3 signature | Unit tests: `test_select_capability_filter`, `test_select_lease_filter`, `test_select_write_scope_conflict` |
| T1-P1-2 | Add `selector_config.yaml` per N1 §6 | Schema validation: `selector_config.yaml` parses and contains all 6 entries |
| T1-P1-3 | Wrap each E1-E6 entry in a thin caller per N1 §4 | Each thin caller exists and calls `select()` |
| T1-P1-4 | Enable shadow mode: old path dispatches, new path logs result | Divergence log file created per entry |
| T1-P1-5 | Run for >=48 hours or >=100 dispatches (whichever is later) | Divergence rate < 5% before proceeding to Phase 2 |

**Verification Gate T1-P1:**
- Parity test: compare old vs new dispatch decisions for last 100 dispatches
- Contract test: `select()` returns valid `Decision` for all E1-E6 contexts
- Schema validation: `selector_config.yaml` validates against schema

### T1 Phase 2: Canary

| Stage | Action | Rollback Trigger |
|-------|--------|-----------------|
| T1-P2-10 | 10% of dispatches use new path | Any dispatch to wrong pane or model |
| T1-P2-50 | 50% of dispatches use new path | Dispatch latency P99 > old path + 50ms |
| T1-P2-100 | 100% of dispatches use new path | Any functional regression |

Canary selection: deterministic hash of `sprint_id + node_id` modulo 10/2/1.

**Verification Gate T1-P2:**
- Parity test: new path matches old path for >=95% of dispatches at each stage
- Latency test: `select()` call overhead < 50ms P99
- Drift guard: DG-001 through DG-004 CI rules pass

### T1 Phase 3: Deprecated

| Step | Action | Verification |
|------|--------|-------------|
| T1-P3-1 | Remove old hardcoded paths from E1-E6 | Code search: zero hits for old pane variable patterns |
| T1-P3-2 | Remove grandfathered exemptions from `entries.yaml` | All entries: `migrated: true` |
| T1-P3-3 | Enable CI drift_guard rules as errors | DG-001..DG-004 pass at error severity |

**Verification Gate T1-P3:**
- Parity test: zero divergence over 100 dispatches
- CI rules: all drift_guard rules pass
- Integration test: each E1-E6 entry uses `select()` (verified by mock)

---

## 5. Track T2: Registry Migration

### T2 Phase 1: Dual-Write

| Step | Action | Verification |
|------|--------|-------------|
| T2-P1-1 | Implement `ProviderAdapterRegistry` with `register/get/hot_reload` per N2 §3 | Unit tests for all 3 methods |
| T2-P1-2 | Create adapter YAMLs for 3 provider groups (anthropic/zhipu/openai-compat) per N2 §4 | Schema validation: each YAML has all 4 dimensions |
| T2-P1-3 | Implement adapter classes: `AnthropicAdapter`, `ZhipuAdapter`, `OpenAICompatAdapter` | Unit tests per adapter: `test_auth_resolve`, `test_quota_check`, `test_error_classify`, `test_command_build` |
| T2-P1-4 | Register all adapters at startup | `registry.get("anthropic")` returns valid adapter |
| T2-P1-5 | Shadow mode: current call sites still handle auth/headers/errors directly; registry is queried alongside and results logged | Divergence log: compare old inline logic vs registry result |
| T2-P1-6 | Run for >=48 hours or >=200 API calls (whichever is later) | Divergence rate < 2% before proceeding |

**Verification Gate T2-P1:**
- Parity test: registry `auth_resolve` matches existing auth logic for all 3 provider groups
- Contract test: registry returns valid `AuthResult/QuotaResult/ErrorClassification/CommandResult`
- Schema validation: adapter YAMLs conform to N2 §7 configuration schema

### T2 Phase 2: Canary

| Stage | Action | Rollback Trigger |
|-------|--------|-----------------|
| T2-P2-10 | 10% of API calls use registry for auth/headers | Any auth failure or wrong header |
| T2-P2-50 | 50% of API calls use registry | Error classification mismatch rate > 1% |
| T2-P2-100 | 100% of API calls use registry | Any functional regression |

Canary selection: deterministic hash of `provider_id + model_key + timestamp_minute` modulo 10/2/1.

**Verification Gate T2-P2:**
- Parity test: registry error classification matches existing logic for >=98% of calls
- Contract test: `hot_reload` produces valid `ReloadResult`
- Latency test: registry overhead < 10ms P99 (in-process lookup)

### T2 Phase 3: Deprecated

| Step | Action | Verification |
|------|--------|-------------|
| T2-P3-1 | Remove inline auth/headers/error handling from all call sites | Code search: no direct `ANTHROPIC_API_KEY` or provider-specific header construction outside adapters |
| T2-P3-2 | All providers go through registry exclusively | Integration test: every model dispatch queries registry |
| T2-P3-3 | New-provider onboarding uses N2 §6 checklist only | Test: add a mock provider YAML and verify full onboarding flow |

**Verification Gate T2-P3:**
- Parity test: zero divergence over 200 API calls
- Schema validation: all adapter YAMLs valid
- Onboarding test: new provider onboarded via checklist in <15 minutes

---

## 6. Track T3: Actor Migration

### T3 Phase 1: Dual-Write

| Step | Action | Verification |
|------|--------|-------------|
| T3-P1-1 | Implement `derive_actor()` function per N3 §3 | Unit tests: `test_derive_planner`, `test_derive_builder`, `test_derive_evaluator` |
| T3-P1-2 | Create role overlay files per N3 §5 | 6 role YAML files validated |
| T3-P1-3 | Create actor template files per N3 §7 | 6 template YAML files validated |
| T3-P1-4 | For each of 15 existing actors, run `derive_actor()` and compare with current `agent-actors.json` entry | Diff log: 13/15 must match exactly; 2 exempt actors documented |
| T3-P1-5 | Add `derivation_source` + `derivation_exempt` fields to all 15 actors | DRIFT-001..004 pass as warnings |

**Verification Gate T3-P1:**
- Parity test: 13 derived actors match current manual entries (exact field-by-field comparison)
- Contract test: `derive_actor()` returns valid `ActorSpec` for all 6 roles
- Schema validation: role overlay YAMLs and template YAMLs parse correctly

### T3 Phase 2: Canary

| Stage | Action | Rollback Trigger |
|-------|--------|-----------------|
| T3-P2-10 | 10% of actor lookups use `derive_actor()` instead of JSON read | Any actor profile mismatch causing wrong dispatch |
| T3-P2-50 | 50% of actor lookups use derivation | Derivation latency > 5ms |
| T3-P2-100 | 100% of actor lookups use derivation | Any functional regression |

Canary selection: deterministic hash of `actor_id` — derived actors first, exempt actors last.

**Verification Gate T3-P2:**
- Parity test: derived actor profiles match JSON entries for all dispatches
- CI drift_guard: DRIFT-003 promoted from warning to error
- Latency test: `derive_actor()` < 5ms P99

### T3 Phase 3: Deprecated

| Step | Action | Verification |
|------|--------|-------------|
| T3-P3-1 | Remove 13 derived actor entries from `agent-actors.json`; keep only 2 exempt entries | `agent-actors.json` has exactly 2 entries (mini-router, mini-audit) |
| T3-P3-2 | All actor lookups call `derive_actor()` | Integration test: every role resolves correctly |
| T3-P3-3 | CI DRIFT-001..004 pass at error severity | All drift_guard rules pass |

**Verification Gate T3-P3:**
- Parity test: zero divergence over 50 actor lookups
- CI rules: DRIFT-001..004 pass at error severity
- Exempt actors still manually maintained and load correctly

---

## 7. Backward-Compatibility Facade Shim

### 7.1 Purpose

During migration, old callers must continue working without modification. The facade shim intercepts old-style calls and routes them through the new selector/registry/derivation path.

### 7.2 Shim Interface

```python
class CompatibilityShim:
    """Zero-touch facade for old callers during migration.

    Old code calling hardcoded pane IDs, inline auth, or
    direct actor-actors.json reads continues to work unchanged.
    The shim intercepts these calls and delegates to the new
    selector/registry/derivation subsystems.
    """

    # Selector shim
    @staticmethod
    def dispatch_to_builder(sprint_id: str, **kwargs) -> str:
        """Replaces: coordinator.sh choose_builder_pane()"""
        ctx = SelectContext(task_type="build", sprint_id=sprint_id, ...)
        decision = select(candidates_from_config(), ctx)
        return decision.selected.id

    @staticmethod
    def dispatch_to_evaluator(sprint_id: str, **kwargs) -> str:
        """Replaces: dispatch_scheduler.py spillover pool"""
        ctx = SelectContext(task_type="eval", sprint_id=sprint_id, ...)
        decision = select(candidates_from_config(), ctx)
        return decision.selected.id

    # Registry shim
    @staticmethod
    def get_auth_header(provider_id: str, **kwargs) -> dict:
        """Replaces: inline os.environ["ANTHROPIC_API_KEY"] patterns"""
        adapter = registry.get(provider_id)
        result = adapter.auth_resolve(AuthContext(provider_id=provider_id, ...))
        return {"Authorization": result.auth_value}

    @staticmethod
    def classify_error(provider_id: str, error: Exception) -> str:
        """Replaces: scattered if/elif error classification"""
        adapter = registry.get(provider_id)
        classification = adapter.error_classify(ProviderError(
            provider_id=provider_id,
            exception_type=type(error).__name__,
            error_message=str(error),
            ...
        ))
        return classification.error_class

    # Actor shim
    @staticmethod
    def get_actor_profile(actor_id: str) -> dict:
        """Replaces: direct agent-actors.json jq lookup"""
        if actor_id in EXEMPT_ACTORS:
            return load_from_json(actor_id)
        return derive_actor_from_id(actor_id).to_dict()
```

### 7.3 Shim Activation

- Phase 1: Shim is loaded but NOT called (old code still runs directly)
- Phase 2: Shim intercepts a percentage of calls (canary percentage)
- Phase 3: Shim is the only path (old code removed, shim becomes the entry point)

### 7.4 Shim Lifecycle

- After all three tracks reach Phase 3, the shim can be simplified
- Final state: shim methods become thin wrappers or are inlined
- Shim removal is a separate cleanup task, not blocking

---

## 8. Single-Flag Rollback

### 8.1 Environment Variable

```
SOLAR_OPERATOR_CONVERGENCE_DISABLE=1
```

When set to `1` (or any truthy value), all three tracks revert to legacy behavior:

| Track | Rollback Behavior |
|-------|------------------|
| T1 (Selector) | All dispatches use old hardcoded paths; `select()` is not called |
| T2 (Registry) | All API calls use inline auth/headers/error handling; registry is bypassed |
| T3 (Actor) | All actor lookups read from `agent-actors.json`; `derive_actor()` is not called |

### 8.2 Rollback Activation

- Set env var in the pane's shell before any dispatch: `export SOLAR_OPERATOR_CONVERGENCE_DISABLE=1`
- Can be set globally in `~/.solar/config/harness.env` or per-pane via tmux environment
- Takes effect on next dispatch cycle (no restart required for new dispatches; in-flight dispatches complete with their current path)

### 8.3 Rollback Verification

After setting the flag:
1. Confirm dispatch log shows "legacy path active"
2. Confirm no `select()` calls in telemetry
3. Confirm no registry lookups in provider call logs
4. Confirm actor profiles loaded from JSON

---

## 9. Verification Command List

These commands verify migration correctness. They are NOT run in this sprint (spec only); they are deferred to the downstream implementation sprint.

### V1: Selector Inventory Verification

```bash
# Verify all 6 scheduling entries are registered
python3 -c "
from lib.selector import entries_registry
entries = entries_registry.list_entries()
assert len(entries) == 6, f'Expected 6 entries, got {len(entries)}'
for e in entries:
    assert e['migrated'] == True, f'{e[\"id\"]} not migrated'
print('PASS: All 6 entries migrated')
"
```

### V2: Provider Adapter List

```bash
# Verify all 5 providers have registered adapters
python3 -c "
from lib.registry import ProviderAdapterRegistry
registry = ProviderAdapterRegistry()
providers = registry.list_provider_ids()
expected = {'anthropic', 'zhipu', 'deepseek', 'gemini', 'local'}
assert expected.issubset(set(providers)), f'Missing: {expected - set(providers)}'
for p in expected:
    adapter = registry.get(p)
    assert hasattr(adapter, 'auth_resolve'), f'{p} missing auth_resolve'
    assert hasattr(adapter, 'quota_check'), f'{p} missing quota_check'
    assert hasattr(adapter, 'error_classify'), f'{p} missing error_classify'
    assert hasattr(adapter, 'command_build'), f'{p} missing command_build'
print('PASS: All 5 providers have complete adapters')
"
```

### V3: Actor Derivation Diff

```bash
# Verify derived actors match current manual entries
python3 -c "
import json
from lib.actor_derivation import derive_actor_from_id

with open('config/agent-actors.json') as f:
    manual = {a['actor_id']: a for a in json.load(f)['actors']}

exempt = {'mini-router', 'mini-audit'}
mismatches = []
for actor_id, manual_entry in manual.items():
    if actor_id in exempt:
        continue
    derived = derive_actor_from_id(actor_id)
    for key in ['role', 'cost_tier', 'prefer_for', 'avoid_for']:
        if getattr(derived, key, None) != manual_entry.get(key):
            mismatches.append(f'{actor_id}.{key}')

assert not mismatches, f'Mismatches: {mismatches}'
print(f'PASS: All {len(manual) - len(exempt)} derived actors match')
"
```

### V4: Rollback Flag Test

```bash
# Verify rollback flag disables all new paths
export SOLAR_OPERATOR_CONVERGENCE_DISABLE=1
python3 -c "
from lib.compat_shim import CompatibilityShim
shim = CompatibilityShim()
assert shim.is_legacy_mode() == True, 'Legacy mode not active'
print('PASS: Rollback flag works')
"
unset SOLAR_OPERATOR_CONVERGENCE_DISABLE
```

---

## 10. Cross-Track Dependencies

| Dependency | Description | Constraint |
|------------|-------------|-----------|
| T1 → T2 | Selector needs provider info for capability matching | T1 can proceed independently; provider info is from config, not registry |
| T1 → T3 | Selector uses actor profiles for candidate capability matching | T1 Phase 1 can use current JSON; T1 Phase 2+ benefits from T3 Phase 1 |
| T2 → T3 | No direct dependency | T2 and T3 are fully independent |
| All → Rollback | Rollback flag must be available from T1 Phase 1 onward | Implement flag check before any new-path code |

**Recommended execution order:** T1-P1 + T2-P1 + T3-P1 in parallel → T1-P2 + T2-P2 + T3-P2 in parallel → T1-P3 + T2-P3 + T3-P3 in parallel.

---

## 11. Risk Matrix

| Risk | Track | Phase | Impact | Mitigation |
|------|-------|-------|--------|-----------|
| Selector returns wrong pane | T1 | P2 | High — dispatch goes to wrong role | Dual-write divergence log alerts; canary rollback |
| Registry auth fails | T2 | P2 | High — API calls fail | Shadow mode verifies before cutover; rollback flag |
| Derived actor missing field | T3 | P1 | Medium — wrong capability profile | Exact field diff in Phase 1; 2 exempt actors unaffected |
| Canary selection bias | T1/T2/T3 | P2 | Medium — 10% sample not representative | Use deterministic hash across multiple dimensions |
| hot_reload breaks running adapter | T2 | P2 | Medium — in-flight call gets swapped adapter | N2 §3.4: adapters are stateless; atomic swap safe |
| Race condition in dual-write | T1/T2/T3 | P1 | Low — logging divergence may be inaccurate | Divergence log is append-only; compare post-hoc |

---

## 12. Acceptance Mapping

| Acceptance ID | Criterion | Spec Section |
|---------------|-----------|-------------|
| A-N4-1 | 3 migration tracks defined (selector/registry/actor) with Phase 1/2/3 ladder | §4 (T1 phases), §5 (T2 phases), §6 (T3 phases), §3 (overview) |
| A-N4-2 | Backward-compat facade shim spec (zero-touch for old callers) | §7 (CompatibilityShim with dispatch/auth/actor shim methods + lifecycle) |
| A-N4-3 | Per-phase verification gate defined (parity/contract/schema) | §4 (T1 gates), §5 (T2 gates), §6 (T3 gates) — each phase has 3-gate check |
| A-N4-4 | Single-flag rollback env defined (SOLAR_OPERATOR_CONVERGENCE_DISABLE) | §8 (env var + per-track rollback behavior + activation + verification) |
| A-N4-5 | Verification command list >=3 (selector inventory / provider list-adapters / actor diff-derived) | §9 (V1 selector inventory, V2 provider adapter list, V3 actor derivation diff, V4 rollback flag test) |
