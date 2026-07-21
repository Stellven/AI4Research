# ADR: Capability Capsule Runtime Gate v1

**Status**: Draft  
**Date**: 2026-05-24

## Purpose

This ADR formalizes the runtime gate that resolves a **Capability Capsule**
before capability-native dispatch. It does not replace the existing State
Capsule flow used for `plan.md / handoff.md / eval.md`.

## Definitions

- **State Capsule**: sprint-local context transfer structure in
  `schemas/capsule-schema.yaml`
- **Capability Capsule**: capability container declaring contract, effects,
  bindings, verification, and operator compatibility
- **Execution Capsule / ECapsule**: deprecated alias accepted for one migration
  cycle at the loader boundary only

## Runtime Gate

```text
Task
  -> Capability Capsule candidate selection
  -> precondition check
  -> MCP capability resolution
  -> effect escalation
  -> guard/resource attachment
  -> ResolvedCapabilityCapsule
  -> operator submit
```

## Gate Outputs

The normalized gate output must include:

- `capability_capsule_id`
- `selected_skills[]`
- `resolved_mcp_bindings{}`
- `attached_guard_capsules[]`
- `attached_resource_capsules[]`
- `effect_summary`
- `verification_hooks[]`
- `operator_constraints`

## Fail-Closed Reasons

- `admission_failed`
- `missing_resource`
- `policy_blocked`
- `effect_escalation_requires_human`
- `operator_incompatible`

## Evidence Ledger

When a capability-native envelope is submitted, the evidence ledger must record:

- `capability_capsule_id`
- `capsule_kind`
- `resolved_bindings`
- `effect_summary`
- `guard_results`
- `verification_results`

## Compatibility

- Legacy non-capsule dispatch remains allowed
- State Capsule CLI and validators remain unchanged
- `execution_capsule_id` remains accepted as input alias only
- New emitted records must use `capability_capsule_id`
