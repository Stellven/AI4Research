# AutoSci Workflow Design - Official full-runtime AutoSci integration test through normal solar intake. Do n

sprint_id: `sprint-20260710-140622-intent-official-full-runtime-autosc-602601d3`
workflow_contract: `research.autosci.v1`

## Architecture

This sprint is bound to the Solar-native AutoSci lifecycle. The task graph is the design: each Scientific* logical operator resolves to its research capability capsule and then to the matching autosci-* physical command worker.

## Logical Operators

- `ScientificArtifactReviewer` -> `cap.research-artifact-review`
- `ScientificClaimExtractor` -> `cap.research-claim-extract`
- `ScientificClaimVerifier` -> `cap.research-claim-verify`
- `ScientificCodeEvidenceMapper` -> `cap.research-code-evidence-map`
- `ScientificExperimentDesigner` -> `cap.research-experiment-design`
- `ScientificExperimentMonitor` -> `cap.research-experiment-monitor`
- `ScientificExperimentRunner` -> `cap.research-experiment-run`
- `ScientificGraphUpdater` -> `cap.research-graph-update`
- `ScientificIdeaEvaluator` -> `cap.research-idea-evaluate`
- `ScientificIdeaGenerator` -> `cap.research-idea-generate`
- `ScientificLiteratureDiscoverer` -> `cap.research-literature-discover`
- `ScientificMemoryUpdater` -> `cap.research-memory-update`
- `ScientificMethodExtractor` -> `cap.research-method-extract`
- `ScientificPaperAnalyzer` -> `cap.research-paper-analyze`
- `ScientificPaperIngestor` -> `cap.research-paper-ingest`
- `ScientificPublicationProducer` -> `cap.research-publication-produce`
- `ScientificReportDrafter` -> `cap.research-report-draft`
- `ScientificReportPlanner` -> `cap.research-report-plan`
- `ScientificWorkflowEvolver` -> `cap.research-workflow-evolve`
