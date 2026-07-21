# AutoSci Workflow Plan - Official full-runtime AutoSci integration test through normal solar intake. Do n

sprint_id: `sprint-20260710-140625-intent-official-full-runtime-autosc-08181304`
workflow_contract: `research.autosci.v1`
workflow_template: `scientific_research_lifecycle_full_v1`

## Dispatch Contract

- Normal Solar intake has selected the AutoSci research workflow by contract.
- The workflow is graph-ready; do not send this sprint back through a generic planner.
- Autopilot should dispatch ready Scientific* DAG nodes through graph_scheduler.
- Each node must emit schema-gated scientific evidence or an explicit failed/inconclusive record.

## Nodes

| Node | Logical Operator | Depends On | Gate |
| --- | --- | --- | --- |
| literature_discover | ScientificLiteratureDiscoverer | - | G_LITERATURE_DISCOVER |
| paper_ingest | ScientificPaperIngestor | literature_discover | G_PAPER_INGEST |
| paper_analyze | ScientificPaperAnalyzer | paper_ingest | G_PAPER_ANALYZE |
| memory_update_initial | ScientificMemoryUpdater | paper_analyze | G_MEMORY_UPDATE_INITIAL |
| graph_update | ScientificGraphUpdater | memory_update_initial | G_GRAPH_UPDATE |
| claim_extract | ScientificClaimExtractor | graph_update | G_CLAIM_EXTRACT |
| method_extract | ScientificMethodExtractor | claim_extract | G_METHOD_EXTRACT |
| code_evidence_map | ScientificCodeEvidenceMapper | method_extract | G_CODE_EVIDENCE_MAP |
| idea_generate | ScientificIdeaGenerator | code_evidence_map | G_IDEA_GENERATE |
| idea_evaluate | ScientificIdeaEvaluator | idea_generate | G_IDEA_EVALUATE |
| experiment_design | ScientificExperimentDesigner | idea_evaluate | G_EXPERIMENT_DESIGN |
| experiment_run | ScientificExperimentRunner | experiment_design | G_EXPERIMENT_RUN |
| experiment_monitor | ScientificExperimentMonitor | experiment_run | G_EXPERIMENT_MONITOR |
| claim_verify | ScientificClaimVerifier | experiment_monitor | G_CLAIM_VERIFY |
| report_plan | ScientificReportPlanner | claim_verify | G_REPORT_PLAN |
| report_draft | ScientificReportDrafter | report_plan | G_REPORT_DRAFT |
| artifact_review | ScientificArtifactReviewer | report_draft | G_ARTIFACT_REVIEW |
| publication_produce | ScientificPublicationProducer | artifact_review | G_PUBLICATION_PRODUCE |
| memory_update_final | ScientificMemoryUpdater | publication_produce | G_MEMORY_UPDATE_FINAL |
| workflow_evolve | ScientificWorkflowEvolver | memory_update_final | G_WORKFLOW_EVOLVE |
