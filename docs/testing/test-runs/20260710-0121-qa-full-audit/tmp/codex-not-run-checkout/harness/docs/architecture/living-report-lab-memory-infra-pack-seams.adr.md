# ADR: Living Report, Research Lab, Research Memory, and AI Infra Pack Seams v1

**ADR-ID**: `adr-living-report-lab-memory-infra-pack-seams-v1`
**Status**: Draft / Reserved
**Date**: 2026-05-25
**Sprint**: `sprint-20260524-solar-research-os-v1-core`
**Node**: `N7`
**Author**: Antigravity builder

---

## Context

As the Solar Harness control plane matures, there is an increasing demand for more advanced platform capabilities:
1. **Living Reports**: Reports that automatically update themselves with new evidence.
2. **Research Labs**: Dynamic experiment isolation and resource management environments.
3. **Research Memory**: Long-term episodic and semantic memory layers across runs.
4. **AI Infra Packs**: Bundled infrastructure profiles containing MCP servers and model configurations.

Implementing these components fully in the v1 Core phase risks over-platformization, making the architecture overly complex and brittle before the core execution/writing loops are finalized. However, failing to reserve these extension points would result in invasive changes in later sprints.

To resolve this trade-off, this ADR specifies the reservation of **draft JSON schemas** and **Python operator seams** (type-safe Protocols) for these components, without deploying runtime code or modifying the current execution behaviors.

---

## Naming & Schema Strategy

We introduce five draft JSON schemas under `schemas/draft/`:
- `living-report.v1.draft.json`
- `research-lab.v1.draft.json`
- `research-memory.v1.draft.json`
- `ai-infra-pack.v1.draft.json`
- `artifact-delta-contract.v1.draft.json` (A general patch contract to support delta-friendly updates)

These are mirrored by corresponding python dataclasses inside `lib/research/schemas.py`.

### Safeguarding v1 Core Invariants

To guarantee that the introduction of these schemas does not weaken or bypass existing v1 gate checks (such as size constraints, citation accuracy, character count floors, and section uniqueness):
1. **Model Isolation**: The new dataclasses are stored in `FUTURE_MODELS` rather than `CORE_MODELS` or `NESTED_MODELS`. This ensures that core loaders, validators, and tests (which assert exact sizes of `CORE_MODELS == 8` and `NESTED_MODELS == 5`) are entirely untouched and continue to function as intended.
2. **Post-Init Validation**: The dataclasses execute strict value check validation on creation to prevent corrupt or malformed platform definitions from entering any early-stage pipelines.

---

## Decision: Operator Seams

We introduce abstract python interfaces (seams) in `lib/research/seams.py` using `typing.Protocol` with `typing.runtime_checkable` validation:

```
                  +--------------------------------+
                  |    Downstream Research Loop    |
                  +---------------+----------------+
                                  |
                                  v
                  +---------------+----------------+
                  |        Operator Seams          |
                  | (LivingReportOperator, etc.)   |
                  +---------------+----------------+
                                  |
                                  | (degrades gracefully)
                                  v
                  +---------------+----------------+
                  |   Degraded/Stub Fallbacks      |
                  | (e.g. DegradedResearchMemory)  |
                  +--------------------------------+
```

Each seam Protocol is paired with a `Degraded*` fallback class:
- **`DegradedLivingReportOperator`**: Resolves report initialization stub but raises `NotImplementedError` on updates to indicate no active scheduler is configured.
- **`DegradedResearchLabOperator`**: Statically maps execution slots to local panes (`main:0`), skipping complex routing heuristics.
- **`DegradedResearchMemoryOperator`**: Discards episodic logging events and returns empty query results, preventing network timeouts or dependencies on external vector stores.
- **`DegradedAIInfraPackOperator`**: Returns default model mappings (`gpt-4o` templates) without launching remote MCP servers.
- **`DegradedArtifactDeltaApplier`**: Rejects delta modifications gracefully with a clear exception message.

---

## Consequences

- **Minimal Footprint**: Zero production execution pathways are altered. Core invariants remain fully enforced.
- **Clear Expansion Vector**: Sprints S05+ can implement concrete subclasses of the operator Protocols (e.g., binding to actual Redis/SQLite vector DBs or remote MCP servers) and register them at the boundary without editing the internal research structures.
