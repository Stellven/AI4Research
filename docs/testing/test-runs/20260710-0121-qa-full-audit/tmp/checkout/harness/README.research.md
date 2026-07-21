# DeepResearch Module

Solar-Harness extension for structured, evidence-backed research pipelines.
Part of the `epic-20260513-solar-deepresearch-product-line` epic.

## Architecture

```
harness/lib/research/
  schemas.py           # 8 core + 5 nested dataclass models
  ids.py               # Canonical SHA-256-based ID generation
  hashing.py           # Content hashing (SHA-256)
  storage.py           # SQLite persistence + JSONL + feature flags
  cli.py               # 14 CLI subcommands
  sources/
    base.py            # SourceConnector abstract base
    internal_mirage.py # Mirage VFS connector (default)
  evidence/
    ledger.py          # Evidence write/read + claim-evidence links
    citation_span.py   # UTF-8 span verification (char + byte offsets)
  extractors/
    markdown.py        # Markdown block extraction
  migrations/
    001_init.sql       # 7-table SQLite schema
```

### Data Models

| Model | Purpose |
|-------|---------|
| SourceDocument | External source with content hash |
| EvidenceItem | Span from a source with support rating |
| Claim | Research claim with key/non-key flag |
| ClaimEvidenceLink | Bidirectional claim-evidence binding |
| CitationSpan | Character-level citation in report text |
| ResearchRun | Top-level run tracking |
| ReportSection | Section of a report |
| ReportAST | Full report abstract syntax tree |

### ID Generation

All IDs are deterministic SHA-256-based: `make_id(*parts)` joins parts with `|`,
SHA-256 hashes the UTF-8 encoding, and takes the first 16 hex characters as suffix.

```python
from research.ids import evidence_id, claim_id, connector_id
evidence_id("doc_abc", 10, 100, "a1b2...hash")  # -> "ev_<16hex>"
claim_id("clm_001", "ev_001", "supporting")      # -> "clm_<8hex>"
connector_id("brave", unix_ts=1700000000)          # -> "sc_brave_6553f100"
```

## Installation

### Prerequisites

- Python 3.9+
- sqlite3 (bundled with Python)

### Setup

The module lives inside the Solar-Harness tree. No pip install needed.

```bash
cd /path/to/solar-harness
export PYTHONPATH="$PWD/lib:$PYTHONPATH"
python3 -c "import research; print(research.__file__)"
```

### Initialize a Research Database

```bash
# Via CLI
python3 lib/research/cli.py init /tmp/research.db --topic "Transformer Architectures" --depth-tier standard

# Via Python
from research.storage import init_db
conn = init_db("/tmp/research.db")
conn.close()
```

## CLI Usage

The CLI provides 14 subcommands under `solar-harness research`:

### Core Pipeline (S03)

```bash
# Initialize a research database
python3 lib/research/cli.py init <db_path> --topic "..." --depth-tier standard|quick|deep

# Add a source document
python3 lib/research/cli.py add-source <db_path> --run-id <id> --title "..." --text "..."

# Extract evidence from a source
python3 lib/research/cli.py extract <db_path> --run-id <id> --source-id <id>

# View evidence ledger
python3 lib/research/cli.py ledger <db_path> --run-id <id>

# Check database status
python3 lib/research/cli.py status <db_path>
```

### Full Run (S04)

```bash
# Execute a full research run
python3 lib/research/cli.py run <db_path> --topic "..." --depth-tier standard

# Generate research plan
python3 lib/research/cli.py plan <db_path> --run-id <id>

# Search for sources
python3 lib/research/cli.py search <db_path> --run-id <id> --query "..." --max-results 10

# Mine claims from evidence
python3 lib/research/cli.py mine <db_path> --run-id <id>

# Generate report outline
python3 lib/research/cli.py outline <db_path> --run-id <id>

# Write section content
python3 lib/research/cli.py write <db_path> --section-id <id> --content "..."

# Run factuality checks
python3 lib/research/cli.py check <db_path> --run-id <id>

# Compile report sections
python3 lib/research/cli.py compile <db_path> --run-id <id>

# Export to JSONL
python3 lib/research/cli.py export <db_path> --run-id <id> --output-dir ./out/
```

### Depth Tiers

| Tier | Use Case | Expected Sources |
|------|----------|-----------------|
| `quick` | Quick overview | 3-5 sources |
| `standard` | Standard research | 10-20 sources |
| `deep` | Comprehensive report | 50+ sources |

## Python API

### Content Hashing

```python
from research.hashing import content_hash, verify_content_hash

h = content_hash("The Transformer architecture...")  # 64-char SHA-256 hex
verify_content_hash("The Transformer architecture...", h)  # True
```

### Evidence Ledger

```python
from research.storage import init_db, get_connection
from research.evidence.ledger import write_evidence, check_unsupported_claims

conn = init_db("research.db")
# ... create run and source records first ...

# Write evidence
write_evidence(conn, evidence_item, run_id="run_001")

# Check unsupported claims
result = check_unsupported_claims(conn, run_id="run_001", threshold=0.05)
# result.exceeds_threshold -> True if unsupported rate > 5%
```

### Citation Span Verification

```python
from research.evidence.citation_span import (
    verify_span, verify_span_by_bytes, verify_citation_span
)

# Character offset verification
verify_span("report text with cited data here", "cited data", 12, 22)  # True

# Byte offset verification (for CJK/multibyte)
verify_span_by_bytes("报告中有引用数据", b'\xe5\xbc\x95\xe7\x94\xa8', 9, 21)  # True

# Full citation verification
verify_citation_span("report text...", "source text...", "span text", 10, 20, 50, 60)
```

### Source Connectors

```python
from research.sources.base import SourceConnector, FetchResult
from research.sources.internal_mirage import InternalMirageConnector

connector = InternalMirageConnector()
result = connector.fetch(query="transformer attention mechanism", max_results=5)
# result.items -> list of SourceDocument
```

### Report AST

```python
from research.schemas import ReportAST, Chapter, Section

ast = ReportAST(
    ast_id="ast_0a34c46c8398",
    run_id="run_001",
    chapters=[
        Chapter(chapter_id="ch_001", title="Introduction", chapter_order=1,
                sections=[
                    Section(section_id="sec_001", title="Background",
                            content="...", target_chars=2000, char_count=len("..."))
                ])
    ],
    total_target_chars=100000,
    status="draft",
)
```

## Testing

### Unit Tests (184 tests)

```bash
cd /path/to/solar-harness
python3 -m pytest tests/research/unit/ -v
# 184 passed, 196 assertions, zero mocks
```

| File | Tests | Coverage |
|------|-------|----------|
| test_schemas.py | 61 | 8 dataclass models, enums, validation |
| test_ids.py | 33 | 12 ID generators, prefix registry |
| test_hashing.py | 17 | SHA-256 hashing, type safety, unicode |
| test_storage.py | 29 | SQLite, JSONL, feature flags, WAL |
| test_evidence_span.py | 27 | UTF-8 span verification, byte offsets |
| test_claim_evidence.py | 17 | Evidence ledger, claim links, unsupported |

### Integration Tests (11 tests)

```bash
python3 -m pytest tests/research/integration/ -v
# 11 passed — full pipeline: init -> add-source -> extract -> claims -> AST -> final.md
```

### Negative Controls (10 tests)

```bash
python3 -m pytest tests/research/negative/ -v
# 10 passed — unsupported claims rejected, span mismatches fail, connector errors not silent
```

### Smoke Benchmark

```bash
# Artifacts (generated via fixture connector, zero external API calls)
cat reports/research-smoke-bench.md        # 105-line research report, 17 citations
python3 -c "import json; d=json.load(open('reports/research_eval.smoke.json')); print(d['unsupported_claim_rate'], d['citation_span_accuracy'])"
# 0.0 1.0
```

## Troubleshooting

### "Error: db_path does not exist"
Run `research init <db_path>` first. The CLI requires an initialized SQLite database for all commands except `init` and `run`.

### TypeError: content_hash requires str
The `content_hash()` function only accepts `str`. Pass `str` values, not bytes or None. This is intentional — type safety prevents silent encoding bugs.

### EvidenceItem.__post_init__ validation errors
EvidenceItem validates all fields at construction time. Common issues:
- `span_end` must be > `span_start` (not >=)
- `span_text` must be non-empty
- `content_hash` must be a 64-char hex string that matches `sha256(span_text)`
- `source_type` must be one of the valid types (e.g., "document", "paper", "webpage")
- `evidence_type` must be in `EVIDENCE_TYPES` frozenset
- `support_direction` must be in `SUPPORT_DIRECTIONS` frozenset

### WAL mode not detected on :memory: databases
SQLite `:memory:` databases always report `MEMORY` journal mode, never `WAL`. Use a file-based path for WAL mode tests.

### Byte vs character offsets
`verify_span()` uses character offsets. `verify_span_by_bytes()` uses byte offsets. For ASCII text they are identical. For CJK/emoji text, byte offsets are larger (e.g., one CJK character = 3 UTF-8 bytes). Use `char_offset_to_byte_offset()` and `byte_offset_to_char_offset()` to convert between them.

### Connector failure not silent
If a source connector raises `ConnectionError` or returns a `FetchResult` with `fetch_error` set, the pipeline does not silently continue. This is by design — the DeepResearch stop rules prohibit silent degradation.

## Factuality Metrics

| Metric | Threshold | Description |
|--------|-----------|-------------|
| unsupported_claim_rate | <= 0.05 (5%) | Key claims without evidence backing |
| citation_span_accuracy | >= 0.9 (90%) | Citation spans matching source text |
| source_authority_score | >= 0.8 | Average authority of cited sources |
| freshness_score | >= 0.7 | Recency of source material |
| contradiction_coverage | >= 0.0 | Contradictions detected and resolved |
| section_repetition_rate | <= 0.1 (10%) | Cross-section content duplication |
| cross_section_consistency | >= 0.9 | Logical consistency across sections |

## Sprint History

| Sprint | Slice | Status |
|--------|-------|--------|
| S01 | requirements | passed |
| S02 | architecture | passed |
| S03 | core-runtime | passed |
| S04 | orchestration-ui | completed |
| S05 | verification-release | passed |
