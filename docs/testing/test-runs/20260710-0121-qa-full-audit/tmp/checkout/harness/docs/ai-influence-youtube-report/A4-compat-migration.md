# A4 — Compatibility & Migration (AI Influence YouTube 报告流)

Sprint: `sprint-20260528-p0-ai-influence-youtube-报告流默认流程固化与验收-s02-architecture`
Node: `A4`
Scope: `spec-only`
Generated: `2026-05-29`

## 0. Purpose

A4 locks how the new default AI Influence YouTube report flow coexists with:

1. The existing `tech_hotspot_radar.py` CLI surface
2. The YouTube Transcript epic runtime outputs
3. The HF Paper Insight Browser Agent pattern
4. The migration path from legacy flow to gated default flow

## 1. Existing CLI flag inventory

### 1.1 `plan-ai-influence-reports`

| Flag | Current meaning | A4 decision |
|------|-----------------|-------------|
| `--date` | Planning date | retain |
| `--days` | Lookback days | retain |
| `--limit` | Max completed videos in planning catalog | retain |
| `--output-base` | Override output root | retain |
| `--model` | Planner model override | retain, but constrained to Browser Agent-compatible final planner |

### 1.2 `run-ai-influence-planned-reports`

| Flag | Current meaning | A4 decision |
|------|-----------------|-------------|
| `--date` | Planning date | retain |
| `--days` | Lookback days | retain |
| `--plan-file` | Explicit plan file path | retain |
| `--report-id` | Single report render | retain |
| `--output-base` | Override output root | retain |
| `--model` | Writer model override | retain, Browser Agent final writer only |
| `--send` | Send generated report by email | wrap behind validator PASS guard |
| `--skip-notebooklm` | Skip NotebookLM enrichment | retain as non-core side-path |
| `--notebook-name` | NotebookLM notebook override | retain |
| `--continue-on-error` | Continue after one failure | retain |

### 1.3 `validate-ai-influence-planned-reports`

| Flag | Current meaning | A4 decision |
|------|-----------------|-------------|
| `--date` | Planning date | retain |
| `--report-id` | Validate one report | retain |
| `--output-base` | Override output root | retain |
| `--require-project-archive` | Require ChatGPT project archive evidence | retain |

## 2. New compatibility rules

### 2.1 `--gate-on`

- Transcript gate becomes default-on for all planning and writing surfaces.
- If the implementation exposes the flag, help text must state that it is default-enabled.

### 2.2 `--allow-bypass`

- Exists only as emergency lab-only escape hatch.
- Disabled in production.
- Any use emits FATAL log + control-plane event + zero archive writes.

### 2.3 Retain vs wrap

Retain unchanged:

- `--date`
- `--days`
- `--limit`
- `--output-base`
- `--plan-file`
- `--report-id`
- `--continue-on-error`
- `--require-project-archive`

Retain but wrap:

- `--model`
- `--send`
- `--skip-notebooklm`
- `--notebook-name`

Policy-only additions:

- `--gate-on`
- `--allow-bypass`
- `--legacy-mode`

## 3. `compat_adapter_v1` for transcript-status JSON

### 3.1 Normalized output

`compat_adapter_v1` must normalize upstream transcript rows into:

- `video_id`
- `entity_recall`
- `wer`
- `segment_density`
- `transcript_path`
- `source_schema_version`

### 3.2 Rules

1. Missing required field is a hard drift error.
2. Numeric strings may coerce to numeric.
3. Unknown extra fields are ignored, not surfaced downstream.
4. Drift exits with code `3`.

### 3.3 Drift detection

CI/smoke checks must verify:

- required fields exist
- numeric fields remain numeric after normalization
- `transcript_path` remains readable when not in dry-run
- `source_schema_version` is emitted

## 4. HF Paper Insight Browser Agent reuse decision

Decision: **import wrapper pattern, not business logic fork**.

Why:

- Browser Agent + ChatGPT 5.5 routing is already proven there.
- Reuse preserves ledger semantics and session archive behavior.
- YouTube remains free to own prompts, evidence packing, and validator specifics.

Version-pin policy:

- pin a versioned wrapper contract
- keep these shared ledger fields aligned:
  - `call_id`
  - `stage`
  - `sprint_id`
  - `browser_session_id`
  - `chatgpt_url`
  - `latency_ms`
  - `cost_estimate_usd`

## 5. Migration plan M1-M6

| Step | Pre-condition | Output | Rollback |
|------|---------------|--------|----------|
| `M1` | S02 passed | Introduce gated planning package behind compatibility layer | keep legacy planner path as default |
| `M2` | M1 PASS | Introduce Browser Agent 3-phase wrapper for plan/write/synthesize | revert to legacy command path |
| `M3` | M2 PASS | Make gated `plan-ai-influence-reports` default path | restore `--legacy-mode` default |
| `M4` | M3 PASS | Wire validator before archive and gate email send behind PASS | disable validator hook and restore legacy publish behavior |
| `M5` | M4 PASS | Run 2026-W21 smoke: plan -> render -> validate | keep new path dark if smoke not green |
| `M6` | M5 PASS | Remove default legacy path, keep emergency bypass only | re-enable legacy path for one release window |

## 6. Drift detection plan

Required cross-epic checks:

1. transcript-status field contract unchanged or adapter still green
2. Browser Agent wrapper exports expected call surface
3. `model_call_ledger` required fields still align with HF pattern
4. `plan-ai-influence-reports` parser still exposes retained flags
5. final HTML still embeds SVG and hides internal identifiers

Failure mode:

- explicit blocking status
- no silent downgrade
- no local-model substitution
- no partial archive

## 7. OQ-S02-01 closure criteria

Close only when:

1. `compat_adapter_v1` implemented and unit-tested
2. parser retain/wrap decisions codified in help output or docs
3. Browser Agent wrapper reuse path pinned to versioned import surface
4. smoke test proves drift checks fail loudly on mismatch

## 8. Not in A4

- No parser edits
- No live import wiring from HF line
- No transcript-status adapter implementation
- No CI job creation
- No parent epic close
