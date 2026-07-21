# Code Signal Plane — Line A/B → Unified Migration Map

## Line A: AI Influence GitHub Project Intelligence System Upgrade

| Legacy module | Status in unified | Adapter |
|---|---|---|
| `schema.py` DiscoveryCandidate | Mapped to `code_signal/models.py` RepoSnapshot | `legacy_adapter.discovery_to_snapshot()` |
| `schema.py` RepoSnapshot | Kept; new unified RepoSnapshot in `code_signal/models.py` | Direct field mapping |
| `schema.py` EvidenceAtom | Kept; referenced via `evidence_ids_json` | Enrichment operator links |
| `schema.py` ReasoningPacket | Mapped to RepoEnrichment | `legacy_adapter.reasoning_to_enrichment()` |
| `schema.py` AnalysisCard | Mapped to RepoSignal + OutputAsset | `legacy_adapter.analysis_to_signal()` + `analysis_to_card_asset()` |
| `schema.py` PlanningBrief | Mapped to OutputAsset (direction_brief) | `legacy_adapter.planning_to_brief_asset()` |
| `schema.py` Detection | Kept in legacy; G3 scoring subsumes detection | No adapter needed |
| `pipeline.py` | Kept; new pipeline in `code_signal_plane.py` | Additive |
| `scoring.py` | Kept; new scoring in G3 operator | Additive |
| `packets.py` | Kept; new packet in G4 operator | Additive |
| `cards.py` | Kept; new card in G5 asset builder | Additive |
| `briefs.py` | Kept; new brief in G5 asset builder | Additive |
| `adapters/` | Kept; `legacy_adapter.py` wraps them | Additive |
| `reports/` | Kept; G5 produces output assets instead | Additive |

## Line B: AI Influence GitHub Trend & Action Analyzer Ultimate

| Legacy asset | Status in unified | Mapping |
|---|---|---|
| Strategy assets | Folded into G3 (actionability) + G4 (packet) | Scoring flags |
| Action assets | Folded into G5 action_queue + intervention_plan | Output assets |
| Trend analysis | Folded into G1 discovery + G3 scoring | Pipeline stages |

## Legacy config files (not modified in S2)

- `github_intelligence_config.yaml` — Line A runtime config, kept as-is
- `github-trends.yaml` — trending fetch config, kept as-is
- `tech-hotspot-radar.yaml` — Line B legacy config, kept as-is
- `code-signal-plane.yaml` — NEW unified config, sole source for new operators

## Rollback

Remove these directories/files to revert:
- `harness/lib/github_intelligence/code_signal/`
- `harness/config/code-signal-plane.yaml`
- `harness/scripts/code_signal_plane.py`
- `harness/scripts/code_signal_plane/`
- `harness/tests/code_signal/`
- `harness/docs/architecture/code-signal-plane-migration.md`

No legacy files are modified; rollback is clean deletion of additive code.
