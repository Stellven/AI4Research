# Migration Test: Paper to Claim Verification on Solar

This folder is a non-invasive migration scaffold for the target Solar-native
pipeline:

```text
paper -> claim -> contract -> run -> evidence -> verdict -> report
```

It does not modify `harness/config/*` directly. Files under `config/` are
installation fragments that can be copied or merged after review.

## Contents

| Path | Purpose |
| --- | --- |
| `schemas.py` | Python dataclass contracts for the missing Phase 0 schemas. |
| `adapter.py` | Converts a compact AI4Research Phase 0 fixture into Solar-shaped objects. |
| `comparator.py` | Minimal verdict policy and summary derivation. |
| `replay_runner.py` | Replays existing Phase 0 artifacts without running external benchmarks. |
| `fixtures/skillgen_phase0_fixture.json` | Golden fixture preserving the known SkillGen Phase 0 conclusion. |
| `schemas/phase0_claim_verification.schema.json` | JSON schema for the fixture-level artifact contract. |
| `config/capability-capsules/cap.phase0-claim-verification.yaml` | Proposed capability capsule manifest. |
| `config/capability-capsules.registry.fragment.yaml` | Registry fragment for the capsule. |
| `config/logical-operators.fragment.json` | Proposed `ResearchClaimVerifier` logical operator and binding. |
| `config/logical-operators.schema.fragment.json` | Schema extension fragment for the new logical operator enum. |
| `tests/test_migration_pipeline.py` | Focused tests for schema and golden replay behavior. |

## Validation Scope

This package validates data contracts and replay behavior only. It does not
prove that Solar can yet dispatch the full live pipeline through
`operator_runtime.submit()`. That requires installing the config fragments into
Solar and adding a runtime operator implementation.

The golden fixture intentionally preserves the previous Phase 0 high-level
conclusion:

- `paper_level_status = not_reproduced`
- `full_paper_claim_status = blocked`
- claim verdict counts: `partially_reproduced=3`, `blocked=7`, `not_reproduced=2`

Execution readiness is modeled separately and cannot upgrade claim verdicts.

