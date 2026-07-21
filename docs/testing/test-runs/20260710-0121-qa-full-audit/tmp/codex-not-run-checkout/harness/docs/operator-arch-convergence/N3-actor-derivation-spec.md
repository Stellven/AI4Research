# Actor Derivation Specification

sprint: `sprint-20260527-operator-architecture-convergence`
node: N3
generated: 2026-05-28T20:10:00Z

## 1. Purpose

Define a deterministic derivation rule so that actor profiles (currently hand-maintained in `config/agent-actors.json`) can be generated from physical_operator properties + role overlay. This eliminates duplicated manual maintenance and ensures adding a new provider/model only requires one template, not N role-specific copies.

## 2. Current Actor Inventory

15 actors in `config/agent-actors.json` (loaded by `lib/actor_profiles.py`):

| # | actor_id | role | cost_tier | pattern |
|---|----------|------|-----------|---------|
| 1 | mini-claude-opus-planner | planner | high | `{provider}-{model}-{role}` |
| 2 | mini-claude-opus-evaluator | evaluator | high | `{provider}-{model}-{role}` |
| 3 | mini-claude-opus-planner-print | planner | high | `{provider}-{model}-{role}-{variant}` |
| 4 | mini-claude-opus-evaluator-print | evaluator | high | `{provider}-{model}-{role}-{variant}` |
| 5 | mini-claude-sonnet-builder | builder | medium | `{provider}-{model}-{role}` |
| 6 | mini-claude-sonnet-builder-print | builder | medium | `{provider}-{model}-{role}-{variant}` |
| 7 | mini-antigravity-gemini31-pro | planner | medium | `{provider}-{model}` (role implicit) |
| 8 | mini-antigravity-gemini31-pro-image | planner | medium | `{provider}-{model}-{variant}` |
| 9 | mini-antigravity-gemini35-flash-high | builder | low | `{provider}-{model}-{variant}` |
| 10 | mini-antigravity-gemini35-flash-image | builder | low | `{provider}-{model}-{variant}` |
| 11 | mini-glm51-knowledge | knowledge-extractor | low | `{provider}-{model}-{role}` |
| 12 | mini-thunderomlx-qwen36-knowledge | knowledge-extractor | low | `{provider}-{model}-{role}` |
| 13 | mini-router | planner | low | special: routing-only |
| 14 | mini-audit | auditor | low | special: audit-only |
| 15 | mini-local-scan | builder | low | special: local-only |

### Drift observation

All 15 actors share the **identical 12-key capability_profile**:
```
architecture_reasoning, code_impl, root_cause_debug,
test_generation, test_execution, research_synthesis,
academic_critique, browser_use, gui_use, long_context,
multi_agent_coordination, speed
```

This means capability_profile is not actor-specific — it is a shared default that never varies. Differentiation is entirely driven by `role → prefer_for/avoid_for` and `provider+model → cost_tier + risk_profile`.

## 3. Derivation Function Signature

```python
def derive_actor(
    op_spec: PhysicalOperatorSpec,
    role: str,
    variant: Optional[str] = None,
) -> ActorSpec:
    """
    Derive an actor profile from physical operator properties + role overlay.

    Args:
        op_spec: Physical operator definition containing provider, model,
                 capability baseline, cost tier, and risk defaults.
        role: Execution role (planner|builder|evaluator|architect|
              knowledge-extractor|auditor|router).
        variant: Optional variant suffix (e.g., 'print', 'image', 'high').

    Returns:
        ActorSpec with capability_profile, risk_profile, and cost_profile
        derived deterministically from inputs.
    """
```

### 3.1 Input Types

```python
@dataclass
class PhysicalOperatorSpec:
    operator_id: str          # e.g., "claude-opus", "glm-51", "gemini31-pro"
    provider: str             # e.g., "anthropic", "zhipu", "google"
    model: str                # e.g., "claude-opus-4-7", "glm-5.1"
    capability_baseline: Dict[str, float]  # 12-key shared profile (all 0.8 default)
    cost_tier: str            # "high" | "medium" | "low" — from provider+model cost
    context_window: int       # max tokens
    supports_vision: bool     # image/multimodal capability

@dataclass
class RoleOverlay:
    role: str
    prefer_for: List[str]     # task types this role is optimized for
    avoid_for: List[str]      # task types this role should skip
    risk_overrides: Dict[str, str]  # role-specific risk adjustments

@dataclass
class ActorSpec:
    actor_id: str             # derived: "{provider_prefix}-{model_slug}-{role}[-{variant}]"
    role: str
    capability_profile: Dict[str, float]  # copied from op_spec.capability_baseline
    risk_profile: Dict[str, str]          # base + role_overlay.risk_overrides
    cost_profile: Dict[str, Any]          # cost_tier + prefer_for + avoid_for
    derivation_source: str    # "derived" | "template" | "manual"
    derivation_exempt: Optional[str]  # None if derived; reason if manual
```

### 3.2 Derivation Algorithm (7 steps)

```
1. Parse actor_id → extract provider, model, role, variant
2. Look up PhysicalOperatorSpec by provider+model
3. If PhysicalOperatorSpec exists:
   a. capability_profile = op_spec.capability_baseline (copy)
   b. cost_tier = op_spec.cost_tier (inherit)
4. Apply RoleOverlay for the given role:
   a. prefer_for = role_overlay.prefer_for
   b. avoid_for = role_overlay.avoid_for
   c. risk_profile = base_risk + role_overlay.risk_overrides
5. If variant specified:
   a. Apply variant-specific overlays (e.g., "print" → restrict FANOUT/BULK_EDIT/TEST_RUN)
   b. Append variant to actor_id
6. If PhysicalOperatorSpec NOT found:
   a. Fall back to actor_template/{role}.yaml
   b. Set derivation_source = "template"
7. Return ActorSpec
```

## 4. Derivability Mapping (13/15 = 87% ≥ 80% threshold)

### 4.1 Derivable from physical_operator + role_overlay (13 actors)

| actor_id | provider | model | role | derivation source |
|----------|----------|-------|------|-------------------|
| mini-claude-opus-planner | anthropic | claude-opus-4-7 | planner | op + role |
| mini-claude-opus-evaluator | anthropic | claude-opus-4-7 | evaluator | op + role |
| mini-claude-opus-planner-print | anthropic | claude-opus-4-7 | planner + print variant | op + role + variant |
| mini-claude-opus-evaluator-print | anthropic | claude-opus-4-7 | evaluator + print variant | op + role + variant |
| mini-claude-sonnet-builder | anthropic | claude-sonnet-4-6 | builder | op + role |
| mini-claude-sonnet-builder-print | anthropic | claude-sonnet-4-6 | builder + print variant | op + role + variant |
| mini-antigravity-gemini31-pro | google | gemini-2.5-pro | planner | op + role |
| mini-antigravity-gemini31-pro-image | google | gemini-2.5-pro | planner + image variant | op + role + variant |
| mini-antigravity-gemini35-flash-high | google | gemini-2.5-flash | builder | op + role |
| mini-antigravity-gemini35-flash-image | google | gemini-2.5-flash | builder + image variant | op + role + variant |
| mini-glm51-knowledge | zhipu | glm-5.1 | knowledge-extractor | op + role |
| mini-thunderomlx-qwen36-knowledge | local | qwen3-6b | knowledge-extractor | op + role |
| mini-local-scan | local | n/a | builder (local-scan) | template fallback |

### 4.2 Exempt — require manual maintenance (2 actors)

| actor_id | derivation_exempt reason |
|----------|------------------------|
| mini-router | Cross-provider routing agent with no single physical operator binding; must hand-maintain prefer_for/avoid_for as routing logic evolves independently of any single model provider. |
| mini-audit | Audit agent with compliance-specific risk_profile that cannot be derived from any model capability; deny patterns (no coding, no planning) are policy-driven, not capability-driven. |

**Derivability rate: 13/15 = 86.7% ≥ 80% threshold. PASS.**

## 5. Role Overlay Registry

Fixed set of role overlays that drive prefer_for / avoid_for:

| role | prefer_for | avoid_for | risk_overrides |
|------|-----------|-----------|----------------|
| planner | planning, architecture, schema-design | bulk-extraction | git_push=review_only |
| builder | implementation, debugging, tests, refactor | bulk-extraction | (base) |
| evaluator | review, verification, evidence | bulk-extraction | destructive_actions=denied |
| knowledge-extractor | knowledge-extraction, wiki, bulk-extraction | critical-review, complex-refactor | allowed_write_scope=wiki_only |
| auditor | auditing, ledger-log, compliance | planning, coding | allowed_write_scope=audit_log_only |
| router | routing, dispatch, fallback | coding, deep-reasoning | (base) |

### Variant overlays

| variant | additional avoid_for | notes |
|---------|---------------------|-------|
| print | FANOUT, BULK_EDIT, TEST_RUN, LOW_VALUE_SCAN | Restricts expensive operations on print-intended panes |
| image | (none additional) | Adds supports_vision=true check |
| high | (none additional) | Maps to high-traffic/fast-lane routing |

## 6. drift_guard: derivation_exempt Field

### 6.1 Rule

Every actor in `agent-actors.json` MUST have one of:
- `derivation_source: "derived"` — auto-generated from physical_operator + role_overlay
- `derivation_source: "template"` — generated from `actor_template/{role}.yaml`
- `derivation_source: "manual"` + `derivation_exempt: "<reason>"` — hand-maintained

### 6.2 CI Enforcement

```
DRIFT-001: Every actor must have a derivation_source field.
  Severity: error
  Check: jq '.actors[] | select(.derivation_source == null)' agent-actors.json → must be empty

DRIFT-002: Every manual actor must have a non-empty derivation_exempt reason.
  Severity: error
  Check: jq '.actors[] | select(.derivation_source=="manual") | .derivation_exempt' → must be non-null and non-empty

DRIFT-003: derived actors must match derive_actor(op_spec, role) output.
  Severity: warning (phase 1), error (phase 2)
  Check: re-derive and diff; any mismatch → report drift

DRIFT-004: No new manual actors without exemption review.
  Severity: error
  Check: git diff on agent-actors.json; any new entry with derivation_source=manual must include derivation_exempt with ≥20 chars reason
```

### 6.3 Exemption Review Process

1. New manual actor submitted with `derivation_exempt` reason
2. Automated check validates reason ≥20 chars
3. Within 7 days, architect review: can this be derived instead?
4. If yes → convert to derived; if no → exemption accepted with expiry date

## 7. actor_template Fallback Path

When `derive_actor` is called but no `PhysicalOperatorSpec` exists for the given provider+model:

```
derive_actor(op_spec=None, role="builder", variant=None)
  → load actor_template/builder.yaml
  → fill capability_profile from template defaults
  → fill risk_profile from RoleOverlay
  → fill cost_profile from template (cost_tier=low by default for unknown operators)
  → set derivation_source: "template"
  → return ActorSpec
```

### 7.1 Template Files

```
config/actor_template/
  planner.yaml          # default planner profile
  builder.yaml          # default builder profile
  evaluator.yaml        # default evaluator profile
  knowledge-extractor.yaml  # default knowledge-extractor profile
  auditor.yaml          # default auditor profile
  router.yaml           # default router profile
```

Each template contains:
```yaml
role: <role>
capability_profile:
  architecture_reasoning: 0.5
  code_impl: 0.5
  # ... all 12 keys with conservative defaults
cost_tier: low
prefer_for: [...]
avoid_for: [...]
risk_profile: {...}
```

### 7.2 When Template is Used

1. New provider/model added before PhysicalOperatorSpec is registered
2. Local-only operators with no cloud provider
3. Ad-hoc testing operators

Template-derived actors should be flagged for review and conversion to op-derived once the PhysicalOperatorSpec is available.

## 8. Acceptance Mapping

| AC | Requirement | Spec Section | Status |
|----|------------|---------------|--------|
| A-N3-1 | derive_actor function signature locked | §3 (signature + input/output types) | ✓ |
| A-N3-2 | ≥80% of existing actors flagged as derivable | §4 (13/15 = 86.7%) | ✓ |
| A-N3-3 | drift field derivation_exempt defined and CI-enforced | §6 (DRIFT-001..004 + review process) | ✓ |
| A-N3-4 | actor_template fallback path defined | §7 (template files + fallback algorithm) | ✓ |
