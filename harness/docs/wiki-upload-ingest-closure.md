# Wiki Upload-Ingest Closure — Operator Runbook

Sprint: `sprint-20260508-wiki-upload-ingest-closure`
Created: 2026-05-08
Scope: Batch upload → extract → ingest → audit → repair → searchable knowledge loop

---

## Overview

The upload-to-searchable-knowledge pipeline processes batches of user-uploaded files (PDF, `.pages`, Markdown, etc.) through:

1. **Upload** → files land in `_raw/file-uploads/<batch>/`
2. **Extract** → text/artifacts derived into safe locations
3. **Ingest** → dispatch-driven agent processing into vault wiki pages
4. **Audit** → verify completeness (qmd + Solar DB/FTS)
5. **Repair** → backfill missing entries idempotently

**Target SLA**: 23 originals preserved, 23 qmd searchable, 23 Solar DB/FTS searchable, zero false-completed dispatches.

---

## 1. Dispatch State Machine

### States

| State | Meaning | Transition |
|-------|---------|------------|
| `dispatched` | Created, waiting for agent pickup | → `running` (agent starts) |
| `running` | Agent actively processing | → `completed` or `failed` |
| `completed` | Agent finished, result file written | terminal |
| `failed` | Agent errored, no result written | → `dispatched` (retry) |
| `skipped` | Duplicate detected or intentionally omitted | terminal |
| `chained` | Result of a chained/nested dispatch, not primary | terminal |

### Rules

- **No false-completed**: A dispatch is only `completed` when both the dispatch frontmatter is updated AND a `wiki-result-<id>.md` file exists in the same directory.
- **Chained dispatches** (e.g., a batch upload that triggers individual ingests) MUST use the `chained` state, never `completed`, for the outer wrapper.
- **Collision-proof IDs**: Dispatch IDs use `YYYYMMDDTHHmmssZ` format. If multiple dispatches are created within the same second, append a unique suffix (e.g., `-2`, `-3`). Builder 1 ensures collision-proof generation.

### Verification

```bash
# Check for false-completed: dispatch says completed but no result file
for f in ~/Knowledge/_raw/solar-harness/.dispatch/wiki-ingest-*.md; do
  id=$(basename "$f" .md | sed 's/wiki-ingest-//')
  status=$(grep '^status:' "$f" | head -1 | awk '{print $2}')
  if [ "$status" = "completed" ]; then
    result="~/Knowledge/_raw/solar-harness/.dispatch/wiki-result-${id}.md"
    if [ ! -f "$result" ]; then
      echo "FALSE-COMPLETED: $id (no result file)"
    fi
  fi
done
```

---

## 2. `.pages` Extraction Runbook

### Problem

Apple Pages (`.pages`) files are ZIP archives containing IWA (protobuf + Snappy compressed) format. Standard tools (`textutil`, `pandoc`, Quick Look) often fail to extract text.

### Extraction Strategy (Priority Order)

| Priority | Method | Reliability | Notes |
|----------|--------|-------------|-------|
| 1 | `pdftotext` after Quick Look PDF export | High (if QL generates PDF) | Best quality |
| 2 | IWA protobuf + `python-snappy` binary scan | Medium | Text in fragments; needs reconstruction |
| 3 | `pandoc` direct conversion | Low | Often fails with binary error |
| 4 | `textutil -convert txt` | Low | May reject the format |
| 5 | OCR on preview image | Last resort | `preview.jpg` in ZIP |

### IWA Extraction Procedure

```bash
# 1. Install python-snappy if missing
pip3 install python-snappy 2>/dev/null

# 2. Unzip the .pages file
mkdir -p /tmp/pages_extract
unzip -o "SOURCE.pages" -d /tmp/pages_extract

# 3. Extract text from IWA files using binary scan
python3 << 'EOF'
import os, re
iwa_dir = "/tmp/pages_extract"
for root, dirs, files in os.walk(iwa_dir):
    for f in files:
        if f.endswith('.iwa'):
            path = os.path.join(root, f)
            with open(path, 'rb') as fh:
                data = fh.read()
            decoded = data.decode('utf-8', errors='ignore')
            segments = re.findall(r'[\u4e00-\u9fff][\u4e00-\u9fff\u0020-\u007e]{3,}', decoded)
            for s in segments:
                print(s.strip())
EOF
```

### Quality Assessment

| Level | Criteria | Action |
|-------|----------|--------|
| **无损 (lossless)** | `.md`, `.txt`, `.csv` source | Direct copy |
| **良好 (good)** | PDF via `pdftotext` | Use as-is |
| **部分 (partial)** | `.pages` IWA extraction | Mark `extraction_quality: partial_iwa_protobuf` in frontmatter |
| **失败 (failed)** | No text extractable | Emit `extract_failed` record, quarantine original |

### Preservation Rules

- **Original uploads are NEVER modified or deleted**
- Derived artifacts go under `_raw/file-uploads/<batch>/` alongside originals with `.extracted.md` suffix
- If extraction is impossible, record in audit as `silent_missing` with reason

---

## 3. Audit Runbook

### Command

```bash
solar-harness wiki audit-uploads --batch <BATCH_ID> --json
```

### What It Checks

1. **Upload inventory**: Count original files in `_raw/file-uploads/<batch>/`
2. **QMD coverage**: For each upload, check if a `.qmd` (searchable markdown) exists
3. **Solar DB/FTS coverage**: For each upload, check if an entry exists in `solar_kb_entries` or `cortex_sources`
4. **Dispatch state consistency**: Verify no false-completed dispatches (see §1)
5. **Result file presence**: Every `completed` dispatch must have a corresponding `wiki-result-<id>.md`

### Expected Output Schema

```json
{
  "batch": "20260508T122047Z",
  "uploads": {
    "total": 23,
    "by_type": {
      ".pdf": 15,
      ".pages": 5,
      ".md": 3
    }
  },
  "qmd": {
    "found": 23,
    "missing": []
  },
  "solar_db": {
    "found": 23,
    "missing": []
  },
  "pages": {
    "silent_missing": [],
    "partial_extraction": ["list of .pages files with partial quality"]
  },
  "dispatch": {
    "total": 23,
    "completed": 23,
    "failed": 0,
    "false_completed": 0
  }
}
```

### Manual Audit (Fallback)

If `solar-harness wiki audit-uploads` is not yet implemented:

```bash
# Count uploads
BATCH="20260508T122047Z"
UPLOAD_DIR="~/Knowledge/_raw/file-uploads"
DISPATCH_DIR="~/Knowledge/_raw/solar-harness/.dispatch"

echo "Uploads: $(find "$UPLOAD_DIR" -maxdepth 1 -type f -name "${BATCH}-*" | wc -l | tr -d ' ')"

# Count completed dispatches for this batch
echo "Completed dispatches: $(grep -rl "source:.*${BATCH}" "$DISPATCH_DIR"/wiki-ingest-*.md 2>/dev/null | xargs grep -l 'status: completed' 2>/dev/null | wc -l | tr -d ' ')"

# Count result files
echo "Result files: $(ls "$DISPATCH_DIR"/wiki-result-*.md 2>/dev/null | wc -l | tr -d ' ')"
```

---

## 4. Repair / Backfill Runbook

### Command

```bash
solar-harness wiki backfill-uploads --batch <BATCH_ID> --repair --json
```

### What It Does

1. **Scans audit output** for missing qmd/Solar DB entries
2. **Re-extracts** `.pages` files that previously failed (with updated tooling)
3. **Re-creates dispatches** for uploads that were never ingested
4. **Upserts** into Solar DB/FTS with provenance to original file
5. **Idempotent**: Running twice produces the same result; no duplicates

### Idempotency Guarantee

- Solar DB entries use `source_id + source_table` as dedup key
- Wiki pages are created only if no existing file covers the same `source_id`
- Dispatch re-creation checks for existing result files first
- QMD generation skips files that already have `.qmd` with valid content

### Manual Repair Procedures

#### Re-ingest a single file

```bash
# Find the upload file
FILE="~/Knowledge/_raw/file-uploads/20260508T122047Z-XX-name.ext"

# Create a new dispatch manually if needed
DISPATCH_ID="wiki-ingest-$(date -u +%Y%m%dT%H%M%SZ)"
cat > "~/Knowledge/_raw/solar-harness/.dispatch/${DISPATCH_ID}.md" << EOF
---
type: wiki-dispatch
action: ingest
skill: wiki-ingest
generated_at: $(date -u +%Y%m%dT%H%M%SZ)
vault_path: ~/Knowledge
status: dispatched
---
source: ${FILE}
mode: append
EOF
```

#### Fix a false-completed dispatch

```bash
# 1. Reset state to dispatched
DISPATCH_ID="wiki-ingest-XXXXXXXXXXXXXXXXX"
DISPATCH_FILE="~/Knowledge/_raw/solar-harness/.dispatch/${DISPATCH_ID}.md"

# Edit status back to dispatched
sed -i '' 's/status: completed/status: dispatched/' "$DISPATCH_FILE"

# 2. Remove orphan result file if it exists
rm -f "~/Knowledge/_raw/solar-harness/.dispatch/wiki-result-${DISPATCH_ID#wiki-ingest-}.md"

# 3. Re-process the dispatch via agent
```

---

## 5. Rollback / Quarantine Runbook

### Principles

- **Never delete original uploads**
- **Never overwrite user-authored vault notes**
- **Rollback = remove derived artifacts, not originals**
- **Quarantine = move problematic files aside, not delete**

### Rollback Derived Artifacts

```bash
BATCH="20260508T122047Z"
VAULT="~/Knowledge"
UPLOAD_DIR="${VAULT}/_raw/file-uploads"
DISPATCH_DIR="${VAULT}/_raw/solar-harness/.dispatch"

# 1. List wiki pages created from this batch (dry run)
echo "Wiki pages to review:"
grep -rl "dispatch_id:.*${BATCH}" "${VAULT}/synthesis/" "${VAULT}/concepts/" "${VAULT}/journal/" 2>/dev/null

# 2. Remove only derived .extracted.md files (not originals)
find "$UPLOAD_DIR" -maxdepth 1 -name "${BATCH}-*.extracted.md" -print
# Review before deleting:
# find "$UPLOAD_DIR" -maxdepth 1 -name "${BATCH}-*.extracted.md" -delete

# 3. Reset dispatches to dispatched state (for re-processing)
for f in "$DISPATCH_DIR"/wiki-ingest-*"$(echo $BATCH | tr -d 'Z')"*.md; do
  if grep -q 'status: completed' "$f"; then
    echo "Would reset: $(basename $f)"
    # sed -i '' 's/status: completed/status: dispatched/' "$f"
  fi
done
```

### Quarantine a Problematic Upload

```bash
# Move to quarantine instead of deleting
QUARANTINE="~/Knowledge/_raw/file-uploads/.quarantine"
mkdir -p "$QUARANTINE"

PROBLEM_FILE="20260508T122047Z-XX-problematic.pages"
mv "~/Knowledge/_raw/file-uploads/${PROBLEM_FILE}" "$QUARANTINE/"

# Record why
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) Quarantined: ${PROBLEM_FILE} — reason: extraction failed, corrupted" \
  >> "$QUARANTINE/quarantine-log.txt"
```

### Nuclear Option: Full Batch Reset

> ⚠️ **DANGEROUS** — Only use if the entire batch is corrupt or was ingested to wrong locations.

```bash
BATCH="20260508T122047Z"
VAULT="~/Knowledge"
DISPATCH_DIR="${VAULT}/_raw/solar-harness/.dispatch"

# DO NOT run without explicit human confirmation
# 1. Find all wiki pages from this batch
# 2. Move them to quarantine
# 3. Reset all dispatches
# 4. Re-run from scratch

echo "SAFETY: This section requires explicit --archive-rebuild or --restore flag"
echo "Not executing. See operator for approval."
```

---

## 6. Batch Closure Checklist

For each batch, verify the following before declaring closure:

```markdown
## Batch Closure Checklist — <BATCH_ID>

- [ ] **Upload count**: N original files in `_raw/file-uploads/<batch>/`
- [ ] **QMD coverage**: N/N `.qmd` files present (or equivalent searchable markdown)
- [ ] **Solar DB coverage**: N/N entries in `solar_kb_entries` or `cortex_sources`
- [ ] **Dispatch integrity**: Zero false-completed dispatches
- [ ] **Result files**: Every completed dispatch has a `wiki-result-<id>.md`
- [ ] **.pages handled**: All `.pages` files either extracted (with quality note) or recorded as `extract_failed`
- [ ] **No overwrites**: No user-authored vault notes were overwritten
- [ ] **Provenance**: All wiki pages have `source`, `dispatch_id`, and `ingested_at` in frontmatter
- [ ] **Duplicate detection**: Re-ingested items detected and skipped, recorded in result files
```

---

## 7. File Layout Reference

```
Knowledge/
├── _raw/
│   ├── file-uploads/
│   │   ├── 20260508T122047Z-01-name.pdf          # Original (never touched)
│   │   ├── 20260508T122047Z-01-name.qmd          # Derived searchable markdown
│   │   ├── 20260508T122047Z-02-name.pages        # Original
│   │   ├── 20260508T122047Z-02-name.extracted.md # Derived extraction
│   │   └── .quarantine/                           # Problematic files
│   ├── solar-db-export/                           # DB export for backfill
│   └── solar-harness/
│       └── .dispatch/
│           ├── wiki-ingest-<ID>.md                # Dispatch instruction
│           └── wiki-result-<ID>.md                # Agent result report
├── synthesis/                                     # Long-form ingested content
├── concepts/                                      # Structured concepts
├── journal/                                       # Session checkpoints
└── references/                                    # Reference materials
```

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Dispatch `completed` but no result file | Agent crashed mid-task | Reset to `dispatched`, re-process |
| `.pages` extraction returns garbage | IWA protobuf fragmentation | Accept partial quality, mark in frontmatter |
| Duplicate wiki pages | Dispatch was processed twice | Keep the more complete version, mark other as `skipped` |
| Missing Solar DB entry | Backfill not yet run | Run `solar-harness wiki backfill-uploads --batch <ID> --repair` |
| QMD count < upload count | Some file types not yet converted | Run audit to identify missing, then backfill |
| Batch has `dispatched` (stuck) dispatches | Agent not running or crashed | Check agent status, retry individual dispatches |

---

## Appendix A: Dispatch ID Collision Prevention

Current format: `YYYYMMDDTHHmmssZ` (second-resolution).

If two dispatches are created in the same second (common during batch uploads), collisions occur. Builder 1 is implementing collision-proof IDs. Until then:

```bash
# Check for collisions
ls ~/Knowledge/_raw/solar-harness/.dispatch/wiki-ingest-*.md | \
  xargs -I{} basename {} .md | sed 's/wiki-ingest-//' | sort | uniq -d
# If any output, there are duplicate IDs
```

## Appendix B: `.pages` File Format Details

- `.pages` = ZIP archive containing IWA (protobuf) files
- Main content: `Index/Document.iwa` (largest file)
- Metadata: `Index/Metadata.iwa`
- Styles: `Index/DocumentStylesheet.iwa`
- Preview: `preview.jpg` (first page thumbnail)
- IWA format: Varint-length-prefixed Snappy-compressed protobuf chunks
- Text is split across protobuf string fields — requires reconstruction

## Appendix C: Solar DB / FTS Indexing

The backfill process upserts uploaded documents into:

| Table | Purpose | Dedup Key |
|-------|---------|-----------|
| `solar_kb_entries` | Knowledge base entries | `source_id` + source table name |
| `cortex_sources` | Citable sources with credibility | `citation_key` |
| `evo_memory_semantic` | Session checkpoints | `session_id` + namespace |

FTS (Full-Text Search) is maintained via SQLite FTS5 virtual tables, automatically updated on upsert.

### A6 Audit Semantics Note

Contract A6 specifies: "Every original upload has a corresponding searchable Solar DB/FTS row" and mentions "`solar_kb_entries` and/or `fts_unified_search`."

**Implementation design**:

- `wiki-upload-backfill.py` writes to `obsidian_vault_index` + `fts_unified_search` tables
- It does NOT write to `solar_kb_entries` or `cortex_sources` (those are populated by different Solar subsystems)
- The audit command (`wiki audit-uploads`) checks `obsidian_vault_index` for vault visibility and `fts_unified_search` for FTS visibility
- A file is counted as `solar_db.found` if it has a row in either `obsidian_vault_index` (with `deleted_at IS NULL`) or `fts_unified_search`

**Implication**: Uploaded documents are searchable via `fts_unified_search` MATCH queries and visible in `obsidian_vault_index`, but they will NOT appear in `solar_kb_entries`-based queries (e.g., the Solar KB context hook reads from `solar_kb_entries` + `cortex_sources`). If full Solar KB context integration is needed, a future sprint should add `solar_kb_entries` population to the backfill pipeline.

This is a **design decision, not a bug** — the contract's "and/or" wording is satisfied through FTS.
