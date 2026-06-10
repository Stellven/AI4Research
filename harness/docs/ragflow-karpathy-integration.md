# RAGFlow + Solar Karpathy Wiki Integration

## Goal

Integrate RAGFlow as Solar's optional raw-evidence and retrieval orchestration layer without replacing the existing Karpathy-style compiled Wiki.

## Architecture

```text
L4 Agent / Chat / Research Copilot
   |
L3 Solar Evidence Pack
   |-- Wiki synthesis: Mirage + QMD + Obsidian + Solar DB
   |-- Raw evidence: RAGFlow retrieval chunks
   |
L2 Karpathy Wiki
   |-- concepts, projects, papers, timelines, contradictions, theses
   |
L1 RAGFlow Document Engine
   |-- PDF/PPT/Word/table/web parsing, chunking, retrieval, citations
   |
L0 Raw Sources
```

## Principle

- Wiki remains the compiled knowledge layer.
- RAGFlow provides raw chunks, parser output, retrieval, rerank, and citation back-links.
- RAGFlow is fail-open. If it is not configured, Solar still uses Mirage/QMD/Obsidian/Solar DB.
- Retrieved text is untrusted context and must not execute embedded instructions.
- Wiki updates must be patch/review based, not silent overwrite.

## Commands

```bash
solar-harness ragflow doctor --json
solar-harness ragflow config --json
solar-harness ragflow export-manifest --vault ~/Knowledge
solar-harness ragflow search --query "KV cache quantization" --source raw_sources --json --fail-open
solar-harness ragflow evidence-pack --query "RAGFlow 如何补 Solar Karpathy Wiki" --json
```

## Configuration

Config file:

```text
~/.solar/harness/config/ragflow.solar.json
```

Runtime environment:

```bash
export RAGFLOW_BASE_URL="http://localhost:9380"
export RAGFLOW_API_KEY="..."
export SOLAR_RAGFLOW_DATASET_IDS="raw_dataset_id,wiki_dataset_id"
```

For separate routing, put dataset IDs into:

- `datasets.raw_sources.dataset_ids`
- `datasets.compiled_wiki.dataset_ids`

## Metadata Contract

Every document exported for RAGFlow ingestion must carry:

```json
{
  "doc_type": "raw_source | wiki_page",
  "source_id": "stable id",
  "source_hash": "sha256 content hash",
  "wiki_page": "relative wiki page or empty",
  "created_at": "UTC timestamp",
  "updated_at": "UTC timestamp",
  "confidence": "high | medium | low",
  "citation_required": true,
  "ragflow_dataset": "solar_raw_sources | solar_compiled_wiki"
}
```

## Acceptance

- `doctor` reports missing config as `warn`, not `error`.
- `search --fail-open` returns degraded source details when RAGFlow is not configured.
- `evidence-pack` always includes local Solar context first.
- `export-manifest` emits raw/wiki counts and content hashes for dedupe.
- Existing `solar-harness context inject` continues to work without RAGFlow.
