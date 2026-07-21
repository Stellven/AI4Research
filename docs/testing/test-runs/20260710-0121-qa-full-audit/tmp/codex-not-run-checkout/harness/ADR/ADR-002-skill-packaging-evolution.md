# ADR-002 — Skill Packaging and Evolution Pipeline

**Status**: Accepted  
**Date**: 2026-05-09  
**Slice**: S2 + S5  
**Authors**: builder_main, builder_codex

---

## Context

Solar Harness needs a reproducible way to:
1. Package and distribute skills (so they survive reinstalls)
2. Evaluate skills against a registry-level quality bar
3. Promote/demote skills based on measured behavior, not manual judgment

Prior to this sprint, skills lived only in `~/.agents/skills` as raw files with no versioning, no evaluation, and no promotion lifecycle.

---

## Decision

### Skill Registry

A canonical `config/skills/registry.yaml` lists all "stable" skills with:
- `name`, `version`, `path`, `status` (`stable` | `canary` | `deprecated`)
- `eval_pack`: pointer to an eval pack that validates the skill

The registry is the single source of truth for what skills are "in product". Skills not in the registry are "wild" and not eligible for promotion.

### Skill Packaging

`lib/skill_export.py` packages a skill into a self-contained bundle:
- YAML metadata + source files
- SHA256 checksum
- Suitable for import into another Solar installation

Install via `solar-harness skills install <bundle>`.

### Eval-Based Promotion

Promotion follows the same dual-gate pattern as the evolution engine (ADR-005):

```
Gate 1: skill_metrics emit → ok: true (the skill can report events)
Gate 2: eval pack score ≥ min_score (the skill performs its contract)
```

Both gates must pass before status changes from `canary` → `stable`.

### Demotion

A skill is demoted to `deprecated` when:
- Its eval pack fails for 3 consecutive sprint cycles, OR
- The skill emitter raises an unhandled exception

Demotion is logged to `events.jsonl` with actor=`skill_registry` and reason=`eval_failure`.

---

## Alternatives Considered

### A — Manual curation only

Keep skills as raw files, curate manually. Rejected: no quality signal, no reproducible distribution.

### B — External package registry (npm/pip)

Publish skills as npm or pip packages. Rejected: introduces network dependency, login requirement, and external service reliability risk. Solar runs offline-first.

### C — Git submodules

Store each skill as a git submodule. Rejected: submodules are operationally painful (detached HEAD states, submodule update forgetting) and do not provide eval-based quality gates.

---

## Consequences

- Skills must have an `eval_pack` reference to be promoted to stable.
- `lib/skill_export.py` must be kept backward-compatible (version field in bundle).
- Wild skills (not in registry) continue to work but are not distributed or promoted.
- Skill bundles are included in the release tarball (see ADR-004).

---

## References

- `config/skills/registry.yaml`
- `lib/skill_metrics.py`
- `lib/skill_export.py`
- `lib/solar_skills.py`
- `evals/packs/skill-coverage/pack.yaml`
- ADR-003 (plugin sandbox — parallel design for plugins)
- ADR-005 (autopilot — uses skill evaluation results)
