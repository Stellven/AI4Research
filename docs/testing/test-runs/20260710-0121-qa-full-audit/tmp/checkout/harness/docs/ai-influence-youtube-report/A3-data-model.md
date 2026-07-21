# A3 — Canonical Data Model (JSON Schemas) for the AI Influence YouTube 报告流

sprint: `sprint-20260528-p0-ai-influence-youtube-报告流默认流程固化与验收-s02-architecture`
node: `A3`
write_scope: `docs/ai-influence-youtube-report/A3-data-model.md`
generated_at: 2026-05-29
status: `reviewing`
package_boundary: `spec_only` — no code; no live calls; no fixture writes; downstream S03 will codegen / hand-write Python dataclasses or pydantic models from these schemas.

Knowledge Context: `solar-harness context inject used` (Mirage degraded `mirage:timeout`; QMD solar-wiki + Solar DB + Obsidian Vault active)
Harness Modules Used: `harness-knowledge`, `harness-graph`
Solar Capabilities (injected, planned): Solar-Harness Runtime · solar-graph-scheduler · Superpowers (workflow.planning) · ATLAS (failure.structured_repair, referenced for failure terminals only) · DeepResearch Citation Verification (`evidence_map.v1` field hooks)

---

## 0. Scope, governance, and relation to A1/A2/A4

A3 owns the **canonical wire format** of every cross-component artifact in the L1-L7 pipeline locked by A1. Every artifact that crosses a layer boundary (data plane) OR a control-plane state transition is specified here. Each schema is:

- **Versioned** via a literal `schema_version` field (`"<name>.v1"`).
- **JSON-serializable** — no binary blobs, no raw transcript text in args.
- **Frozen at the major version** for the lifetime of this epic; additive minor revisions allowed only by an S03+ planner pass.
- **NG-aligned** — every reader-facing schema carries enforceable constraints that L6 validator can verify (NG1 transcript-gate, NG2 no ASCII chart, NG3 no local-model substitution, NG4 no internal-field leak, NG5 no truncation tail).

A3 does **not** finalize:
- Python class signatures, function bodies, or CLI exit codes (owned by **A2**).
- The state machine itself (owned by **A1** §3); A3 only pins the JSON shape of `run_record.v1` that materializes A1's states.
- Compat adapter (`compat_adapter_v1`) field-rename rules between this epic and the YouTube Transcript / HF Paper Insight epics (owned by **A4**).
- Sprint-level closeout (`design.md` cross-references, `eval.{md,json}`) (owned by **A5**).

### 0.1 Schema-naming and versioning policy

| Rule | Statement |
|------|-----------|
| Naming | `<artifact>.v<major>` — e.g. `gate_decision.v1`, `model_call_ledger.v1`. |
| Major bump | Breaking — any removed/renamed required field or any type change. Requires a planner sprint. |
| Minor bump | Additive — new optional field, expanded enum (new value, never removed). No major bump. |
| `schema_version` field | **Required on every top-level object**; literal string equal to the canonical name. Consumers MUST reject unknown major versions. |
| Unknown field policy | Consumers MUST accept unknown optional fields (forward compat). Required fields are always known by the consumer. |
| Time format | All `*_at` timestamps are ISO-8601 UTC with `Z` suffix (e.g. `2026-05-29T15:00:00Z`). All `published_at` for video metadata is ISO-8601 date `YYYY-MM-DD` without time. |
| Identifier format | `run_id` / `call_id` / `event_id` / `report_id` are UUID v4 strings; `chapter_id` / `subsection_id` / `trend_id` are short stable handles minted by the planner (regex `^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$`). |
| Forbidden in reader-facing fields | `video_id` (bare 11-char), `V[0-9]{3}` internal handles, `raw_refs`, `pipeline_fields`, `transcript_status`, `processing_log`. Enforced by L6 Check 1+2; defense-in-depth in §13 below. |

### 0.2 JSON-Schema dialect

Every schema in this document is expressed in **JSON Schema Draft 2020-12** (`"$schema": "https://json-schema.org/draft/2020-12/schema"`). Where a property uses a literal value (e.g. `"const": "chatgpt-5.5-thinking-high"`), the literal is part of the contract — any other value is a contract violation. Where an enum is given, only the listed values are admissible; new values require a minor version bump (§0.1).

### 0.3 Reference points (verbatim from S01 N-specs)

| Source | A3 field(s) anchored | Section |
|--------|----------------------|---------|
| N1 §1.1 T0-T3 grading metrics | `gate_decision.v1.grade / entity_recall / wer / segment_density` | §1 |
| N1 §1.4 T3 exclusions block | `t3_exclusions.v1` | §2 |
| N1 §2.4 `signal_breakdown` schema | `classification_decision.v1.signal_breakdown` | §3 |
| N2 §2.1 Phase 1 plan output | `phase1_plan.v1` | §4 |
| N2 §2.2 Phase 2 chapter output | `phase2_chapter.v1` | §5 |
| N2 §2.3 Phase 3 synthesis output | `phase3_synthesis.v1` | §6 |
| N2 §4 model ledger fields | `model_call_ledger.v1` | §10 |
| N3 §1.1 reader 5-field schema | `evidence_map.v1.entries[]` + `source_mapping.v1` | §7, §8 |
| N3 §3.1 8 validator checks | `validator_report.v1.checks[]` | §9 |
| N3 §4 archive manifest | `archive_manifest.v1` | §11 |
| A1 §3 state machine | `run_record.v1` | §12 |

---

## 1. `gate_decision.v1` — L2 per-video transcript-gate decision

**Used by:** L2 transcript gate ⇒ L3 classifier (data plane) and L6 Check 6 hook (control plane).
**Source of truth:** N1 §1.1 + §1.2.

### 1.1 Required field summary

| Field | Type | Required | Enum / range | Notes |
|-------|------|----------|--------------|-------|
| `schema_version` | string | yes | const `"gate_decision.v1"` | Forward-compat pin |
| `run_id` | string (UUID v4) | yes | — | Mints in L1; copied into every per-row decision |
| `video_id` | string | yes | regex `^[A-Za-z0-9_-]{11}$` | **Internal-only**; never leaks to L7 (NG4 enforced by L6 Check 2) |
| `video_handle` | object | yes | see §1.2 | The reader-facing identity carried forward |
| `grade` | string | yes | enum `["T0","T1","T2","T3"]` | Verbatim from N1 §1.1 |
| `entity_recall` | number | yes | range `[0.0, 1.0]` | N1 metric |
| `wer` | number | yes | range `[0.0, 1.0]` clamped at 1.0 | N1 metric |
| `segment_density` | number | yes | range `[0.0, +∞)` segments/min | N1 metric |
| `evidence_notes` | string \| null | yes | ≤ 512 chars | Free-form gate evidence (e.g. "WER>0.30 → T3"); null only when there is genuinely no note |
| `t` | string (ISO-8601 UTC) | yes | — | When the gate decision was emitted |
| `gate_version` | string | yes | regex `^v\d+\.\d+\.\d+$` | Bump when grading thresholds change |

### 1.2 `video_handle` sub-object (reader-facing identity)

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `channel` | string | yes | Reader-visible channel name (e.g. `"OpenAI Developers"`) |
| `title` | string | yes | Reader-visible title |
| `published_at` | string | yes | ISO-8601 date `YYYY-MM-DD` |

`video_handle` MUST NOT carry `video_id`, internal handles (`V001`), or pipeline fields (NG4). It is the only identifier surface allowed in `evidence_map.v1` and `source_mapping.v1`.

### 1.3 JSON Schema (Draft 2020-12)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "solar.ai_influence_youtube.gate_decision.v1",
  "title": "gate_decision.v1",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version", "run_id", "video_id", "video_handle",
    "grade", "entity_recall", "wer", "segment_density",
    "evidence_notes", "t", "gate_version"
  ],
  "properties": {
    "schema_version": { "const": "gate_decision.v1" },
    "run_id": { "type": "string", "format": "uuid" },
    "video_id": { "type": "string", "pattern": "^[A-Za-z0-9_-]{11}$" },
    "video_handle": {
      "type": "object",
      "additionalProperties": false,
      "required": ["channel", "title", "published_at"],
      "properties": {
        "channel": { "type": "string", "minLength": 1 },
        "title": { "type": "string", "minLength": 1 },
        "published_at": { "type": "string", "format": "date" }
      }
    },
    "grade": { "enum": ["T0", "T1", "T2", "T3"] },
    "entity_recall": { "type": "number", "minimum": 0.0, "maximum": 1.0 },
    "wer": { "type": "number", "minimum": 0.0, "maximum": 1.0 },
    "segment_density": { "type": "number", "minimum": 0.0 },
    "evidence_notes": { "type": ["string", "null"], "maxLength": 512 },
    "t": { "type": "string", "format": "date-time" },
    "gate_version": { "type": "string", "pattern": "^v\\d+\\.\\d+\\.\\d+$" }
  }
}
```

### 1.4 Invariants

- I-gate-1: `grade` MUST be derived strictly from N1 §1.1 thresholds applied to `(entity_recall, wer, segment_density)`; downstream tooling MAY re-derive and reject on mismatch.
- I-gate-2: A `grade == "T3"` row MUST also appear in `t3_exclusions.v1.per_video_reason` for the same run; emission is co-located (§2).
- I-gate-3: `video_handle` carries the reader-facing identity; `video_id` carries the join key; the two are paired but never mixed in L7 outputs.

---

## 2. `t3_exclusions.v1` — L2 run-level exclusion block

**Used by:** L2 ⇒ L6 Check 6 (T3-not-in-core).
**Source of truth:** N1 §1.4.

### 2.1 Required field summary

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `schema_version` | string | yes | const `"t3_exclusions.v1"` |
| `run_id` | string (UUID v4) | yes | — |
| `excluded_video_ids` | array of string | yes | Each item is an 11-char `video_id`; **internal-only** list, never serialized into L7 prose |
| `per_video_reason` | object (map) | yes | Keys are `video_id`s from `excluded_video_ids`; values are `T3ExclusionReason` (§2.2) |
| `generated_at` | string (ISO-8601 UTC) | yes | — |
| `total_excluded` | integer | yes | MUST equal `len(excluded_video_ids)`; defense-in-depth |
| `total_inventory` | integer | yes | The N at the time of exclusion; used by `run_rejected_t3_only` decision |

### 2.2 `T3ExclusionReason` sub-object

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `video_handle` | object | yes | Same shape as §1.2 |
| `gate_result` | object | yes | The triple `{grade: "T3", entity_recall, wer, segment_density}` — minimal slice of `gate_decision.v1` for forensic audit |
| `exclusion_reason` | string | yes | Free-form, ≤ 256 chars, e.g. `"entity_recall < 0.60 AND wer > 0.30"` |
| `excluded_at` | string (ISO-8601 UTC) | yes | When this row was added to the exclusion list |

### 2.3 JSON Schema (Draft 2020-12)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "solar.ai_influence_youtube.t3_exclusions.v1",
  "title": "t3_exclusions.v1",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version", "run_id", "excluded_video_ids",
    "per_video_reason", "generated_at", "total_excluded", "total_inventory"
  ],
  "properties": {
    "schema_version": { "const": "t3_exclusions.v1" },
    "run_id": { "type": "string", "format": "uuid" },
    "excluded_video_ids": {
      "type": "array",
      "items": { "type": "string", "pattern": "^[A-Za-z0-9_-]{11}$" }
    },
    "per_video_reason": {
      "type": "object",
      "propertyNames": { "pattern": "^[A-Za-z0-9_-]{11}$" },
      "additionalProperties": {
        "type": "object",
        "additionalProperties": false,
        "required": ["video_handle", "gate_result", "exclusion_reason", "excluded_at"],
        "properties": {
          "video_handle": {
            "type": "object",
            "additionalProperties": false,
            "required": ["channel", "title", "published_at"],
            "properties": {
              "channel": { "type": "string", "minLength": 1 },
              "title": { "type": "string", "minLength": 1 },
              "published_at": { "type": "string", "format": "date" }
            }
          },
          "gate_result": {
            "type": "object",
            "additionalProperties": false,
            "required": ["grade", "entity_recall", "wer", "segment_density"],
            "properties": {
              "grade": { "const": "T3" },
              "entity_recall": { "type": "number", "minimum": 0.0, "maximum": 1.0 },
              "wer": { "type": "number", "minimum": 0.0, "maximum": 1.0 },
              "segment_density": { "type": "number", "minimum": 0.0 }
            }
          },
          "exclusion_reason": { "type": "string", "maxLength": 256 },
          "excluded_at": { "type": "string", "format": "date-time" }
        }
      }
    },
    "generated_at": { "type": "string", "format": "date-time" },
    "total_excluded": { "type": "integer", "minimum": 0 },
    "total_inventory": { "type": "integer", "minimum": 0 }
  }
}
```

### 2.4 Invariants

- I-t3-1: `excluded_video_ids` MAY be empty (`[]`); the block itself is non-nullable on every run (N1 §1.4).
- I-t3-2: Every key of `per_video_reason` MUST be in `excluded_video_ids` and vice-versa (bijection).
- I-t3-3: When `total_excluded == total_inventory`, control plane MUST transition the run to `run_rejected_t3_only` (A1 §3.2).
- I-t3-4: This block is **never** rendered in reader-facing artifacts; it is consumed only by L6 Check 6 and the forensic audit trail.

---

## 3. `classification_decision.v1` — L3 per-video group classification

**Used by:** L3 ⇒ L4 hierarchy builder; L6 Check 7 (group_type whitelist).
**Source of truth:** N1 §2.4.

### 3.1 Required field summary

| Field | Type | Required | Enum / range | Notes |
|-------|------|----------|--------------|-------|
| `schema_version` | string | yes | const `"classification_decision.v1"` | |
| `run_id` | string (UUID v4) | yes | — | |
| `video_id` | string | yes | regex `^[A-Za-z0-9_-]{11}$` | Internal join key |
| `video_handle` | object | yes | §1.2 | Reader-facing identity |
| `group_type` | string | yes | enum (7 values) `["event","conference","keynote","interview","tutorial","product_update","other"]` | N1 §2.1 |
| `confidence` | number | yes | range `[0.0, 1.0]` | Argmax of `confidence_breakdown`, subject to threshold/fallback |
| `confidence_breakdown` | object | yes | 7 keys, each a number ∈ `[0.0, 1.0]` | N1 §2.4 — all 7 group_types incl. `other` |
| `signal_breakdown` | object | yes | 6 keys S1..S6 (§3.2) | All 6 signals MUST be present (N1 §2.2 — single-signal forbidden) |
| `threshold_applied` | number | yes | range `[0.0, 1.0]` | The N1 §2.3 per-group_type threshold used at decision time |
| `fallback_used` | boolean | yes | — | `true` when N1 §2.3 fallback cascade applied |
| `fallback_chain` | array of string | yes | Each item ∈ same 7-value enum; empty if `fallback_used == false` | Records the cascade (e.g. `["keynote","conference","other"]`) |
| `classified_at` | string (ISO-8601 UTC) | yes | — | |
| `classifier_version` | string | yes | regex `^v\d+\.\d+\.\d+$` | Bump when signal weights change |

### 3.2 `signal_breakdown` sub-object (all 6 signals required)

Each of `S1_title_pattern` / `S2_channel_type` / `S3_duration` / `S4_speaker_count` / `S5_qa_presence` / `S6_slide_density` is an object with these fields:

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `raw_score` | number ∈ `[0.0, 1.0]` | yes | Signal-local raw score |
| `weight` | number ∈ `[0.0, 1.0]` | yes | Per N1 §2.2 weight ceilings (S1:0.35, S2:0.25, S3:0.15, S4:0.15, S5:0.15, S6:0.10) |
| `weighted_score` | number ∈ `[0.0, 1.0]` | yes | `≈ raw_score * weight` (within float tolerance) |
| `evidence` | object | optional | Per-signal evidence (e.g. `{"matched_keywords": ["keynote","session"]}` for S1, `{"detected_speakers": 2}` for S4). Free-shape; not validated here. |

Sum invariant: `sum(weighted_score for S1..S6) ≈ confidence_breakdown[group_type]` (within `±0.01` float tolerance). Defense-in-depth in L6.

### 3.3 JSON Schema (Draft 2020-12)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "solar.ai_influence_youtube.classification_decision.v1",
  "title": "classification_decision.v1",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version", "run_id", "video_id", "video_handle",
    "group_type", "confidence", "confidence_breakdown",
    "signal_breakdown", "threshold_applied", "fallback_used",
    "fallback_chain", "classified_at", "classifier_version"
  ],
  "properties": {
    "schema_version": { "const": "classification_decision.v1" },
    "run_id": { "type": "string", "format": "uuid" },
    "video_id": { "type": "string", "pattern": "^[A-Za-z0-9_-]{11}$" },
    "video_handle": {
      "type": "object",
      "additionalProperties": false,
      "required": ["channel", "title", "published_at"],
      "properties": {
        "channel": { "type": "string", "minLength": 1 },
        "title": { "type": "string", "minLength": 1 },
        "published_at": { "type": "string", "format": "date" }
      }
    },
    "group_type": {
      "enum": ["event", "conference", "keynote", "interview", "tutorial", "product_update", "other"]
    },
    "confidence": { "type": "number", "minimum": 0.0, "maximum": 1.0 },
    "confidence_breakdown": {
      "type": "object",
      "additionalProperties": false,
      "required": ["event", "conference", "keynote", "interview", "tutorial", "product_update", "other"],
      "properties": {
        "event": { "type": "number", "minimum": 0.0, "maximum": 1.0 },
        "conference": { "type": "number", "minimum": 0.0, "maximum": 1.0 },
        "keynote": { "type": "number", "minimum": 0.0, "maximum": 1.0 },
        "interview": { "type": "number", "minimum": 0.0, "maximum": 1.0 },
        "tutorial": { "type": "number", "minimum": 0.0, "maximum": 1.0 },
        "product_update": { "type": "number", "minimum": 0.0, "maximum": 1.0 },
        "other": { "type": "number", "minimum": 0.0, "maximum": 1.0 }
      }
    },
    "signal_breakdown": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "S1_title_pattern", "S2_channel_type", "S3_duration",
        "S4_speaker_count", "S5_qa_presence", "S6_slide_density"
      ],
      "patternProperties": {
        "^S[1-6]_[a-z_]+$": {
          "type": "object",
          "required": ["raw_score", "weight", "weighted_score"],
          "properties": {
            "raw_score": { "type": "number", "minimum": 0.0, "maximum": 1.0 },
            "weight": { "type": "number", "minimum": 0.0, "maximum": 1.0 },
            "weighted_score": { "type": "number", "minimum": 0.0, "maximum": 1.0 },
            "evidence": { "type": "object" }
          }
        }
      }
    },
    "threshold_applied": { "type": "number", "minimum": 0.0, "maximum": 1.0 },
    "fallback_used": { "type": "boolean" },
    "fallback_chain": {
      "type": "array",
      "items": {
        "enum": ["event", "conference", "keynote", "interview", "tutorial", "product_update", "other"]
      }
    },
    "classified_at": { "type": "string", "format": "date-time" },
    "classifier_version": { "type": "string", "pattern": "^v\\d+\\.\\d+\\.\\d+$" }
  }
}
```

### 3.4 Invariants

- I-cls-1: All 6 `signal_breakdown` keys MUST be present; missing any signal is a contract violation (N1 §2.2 forbids single-signal classification).
- I-cls-2: `group_type` MUST equal argmax of `confidence_breakdown`, subject to threshold/fallback (N1 §2.3).
- I-cls-3: When `confidence < 0.50` for the argmax, `group_type` MUST be `"other"` and `fallback_used` MUST be `true`.
- I-cls-4: T3 videos MUST NOT have a `classification_decision.v1` (they short-circuit at L2; see §2).

---

## 4. `phase1_plan.v1` — L5 Phase 1 plan output

**Used by:** L5 Phase 1 ⇒ L4 hierarchy builder ⇒ L5 Phase 2.
**Source of truth:** N2 §2.1 + §1.

### 4.1 Required field summary

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `schema_version` | string | yes | const `"phase1_plan.v1"` |
| `run_id` | string (UUID v4) | yes | — |
| `report_id` | string | yes | Stable handle (regex `^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$`); unique per report |
| `week` | string | yes | ISO week, e.g. `"2026-W21"` |
| `trends` | array of `Trend` | yes | ≥ 1 trend; each trend has ≥ 1 chapter (A1 §3 entry condition for `planned` state) |
| `excluded_material` | array of `ExcludedMaterial` | yes | Possibly empty; carries T3-class exclusions consumed by ChatGPT during planning |
| `model_call_id` | string (UUID v4) | yes | Cross-reference to `model_call_ledger.v1.call_id` (the Phase 1 call) |
| `chatgpt_session_id` | string | yes | Browser Agent stable handle (also recorded in ledger) |
| `chatgpt_conversation_url` | string \| null | yes | URL of the ChatGPT conversation; null only when archival failed before URL was minted |
| `planning_notes` | object | optional | Free-form `{grouping_logic, risks[], follow_up_questions[]}` |
| `generated_at` | string (ISO-8601 UTC) | yes | When the Phase 1 result was returned |
| `prompt_version` | string | yes | const `"aiyt-plan-v1"` (N2 §4) |

### 4.2 `Trend → Chapter → Subsection → EvidenceRef` hierarchy

```
phase1_plan.v1
└── trends[]
    └── chapters[]
        └── subsections[]
            └── evidence_refs[]
```

| Object | Required fields | Notes |
|--------|-----------------|-------|
| `Trend` | `trend_id` (string), `trend_judgment` (string, the reader-facing thesis), `chapters` (array of `Chapter`, len ≥ 1) | |
| `Chapter` | `chapter_id` (string), `title` (string), `purpose` (string), `subsections` (array of `Subsection`, len ≥ 1) | `chapter_id` is the join key into `phase2_chapter.v1` |
| `Subsection` | `subsection_id` (string), `claim` (string, the testable statement), `evidence_refs` (array of `EvidenceRef`, len ≥ 1) | |
| `EvidenceRef` | `evidence_ref_id` (string), `video_handle` (§1.2), `trust_level` (`"T0"`/`"T1"`/`"T2"`), `segment_hint` (string \| null, timestamp or section label) | `trust_level == "T3"` is **forbidden** (NG-T3); enforced by I-plan-3 below and L6 Check 6 |

### 4.3 `ExcludedMaterial` sub-object

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `reason` | string | yes | Free-form; typical values: `"T3 transcript"`, `"weak relevance"`, `"upstream missing"` |
| `video_handle` | object (§1.2) | yes | Reader-facing handle of the excluded item |

### 4.4 JSON Schema (Draft 2020-12)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "solar.ai_influence_youtube.phase1_plan.v1",
  "title": "phase1_plan.v1",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version", "run_id", "report_id", "week", "trends",
    "excluded_material", "model_call_id", "chatgpt_session_id",
    "chatgpt_conversation_url", "generated_at", "prompt_version"
  ],
  "properties": {
    "schema_version": { "const": "phase1_plan.v1" },
    "run_id": { "type": "string", "format": "uuid" },
    "report_id": { "type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$" },
    "week": { "type": "string", "pattern": "^[0-9]{4}-W[0-5][0-9]$" },
    "trends": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["trend_id", "trend_judgment", "chapters"],
        "additionalProperties": false,
        "properties": {
          "trend_id": { "type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$" },
          "trend_judgment": { "type": "string", "minLength": 1 },
          "chapters": {
            "type": "array",
            "minItems": 1,
            "items": {
              "type": "object",
              "required": ["chapter_id", "title", "purpose", "subsections"],
              "additionalProperties": false,
              "properties": {
                "chapter_id": { "type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$" },
                "title": { "type": "string", "minLength": 1 },
                "purpose": { "type": "string", "minLength": 1 },
                "subsections": {
                  "type": "array",
                  "minItems": 1,
                  "items": {
                    "type": "object",
                    "required": ["subsection_id", "claim", "evidence_refs"],
                    "additionalProperties": false,
                    "properties": {
                      "subsection_id": { "type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$" },
                      "claim": { "type": "string", "minLength": 1 },
                      "evidence_refs": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                          "type": "object",
                          "required": ["evidence_ref_id", "video_handle", "trust_level"],
                          "additionalProperties": false,
                          "properties": {
                            "evidence_ref_id": { "type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$" },
                            "video_handle": {
                              "type": "object",
                              "required": ["channel", "title", "published_at"],
                              "additionalProperties": false,
                              "properties": {
                                "channel": { "type": "string", "minLength": 1 },
                                "title": { "type": "string", "minLength": 1 },
                                "published_at": { "type": "string", "format": "date" }
                              }
                            },
                            "trust_level": { "enum": ["T0", "T1", "T2"] },
                            "segment_hint": { "type": ["string", "null"] }
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    },
    "excluded_material": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["reason", "video_handle"],
        "additionalProperties": false,
        "properties": {
          "reason": { "type": "string", "minLength": 1 },
          "video_handle": {
            "type": "object",
            "required": ["channel", "title", "published_at"],
            "additionalProperties": false,
            "properties": {
              "channel": { "type": "string", "minLength": 1 },
              "title": { "type": "string", "minLength": 1 },
              "published_at": { "type": "string", "format": "date" }
            }
          }
        }
      }
    },
    "model_call_id": { "type": "string", "format": "uuid" },
    "chatgpt_session_id": { "type": "string", "minLength": 1 },
    "chatgpt_conversation_url": { "type": ["string", "null"] },
    "planning_notes": {
      "type": "object",
      "properties": {
        "grouping_logic": { "type": "string" },
        "risks": { "type": "array", "items": { "type": "string" } },
        "follow_up_questions": { "type": "array", "items": { "type": "string" } }
      }
    },
    "generated_at": { "type": "string", "format": "date-time" },
    "prompt_version": { "const": "aiyt-plan-v1" }
  }
}
```

### 4.5 Invariants

- I-plan-1: `trends` MUST be non-empty; each trend has ≥ 1 chapter; each chapter has ≥ 1 subsection; each subsection has ≥ 1 `evidence_ref`. (A1 §3 `planned` exit condition.)
- I-plan-2: `evidence_refs[].video_handle` MUST resolve to an item in the run's surviving (T0/T1/T2) inventory.
- I-plan-3: `evidence_refs[].trust_level == "T3"` is forbidden (enum excludes T3). Any T3 video MUST surface in `excluded_material` only.
- I-plan-4: `model_call_id` MUST match an existing row in `model_call_ledger.v1` with `stage == "phase1_plan"`.

---

## 5. `phase2_chapter.v1` — L5 Phase 2 per-chapter output (one call per chapter)

**Used by:** L5 Phase 2 (one per chapter) ⇒ L5 Phase 3 + L7 markdown render.
**Source of truth:** N2 §2.2 (one-call-per-chapter; no batching).

### 5.1 Required field summary

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `schema_version` | string | yes | const `"phase2_chapter.v1"` |
| `run_id` | string (UUID v4) | yes | — |
| `report_id` | string | yes | Same handle as in `phase1_plan.v1` |
| `chapter_id` | string | yes | Same handle as in `phase1_plan.v1.trends[].chapters[]` |
| `body_md` | string | yes | The chapter markdown body (≥ 1 char) |
| `inline_citations` | array of `InlineCitation` | yes | Per-claim citation surface (§5.2) |
| `visual_requests` | array of `VisualRequest` | optional | SVG / chart requests for L7 rendering (N2 §2.2) |
| `claims` | array of `Claim` | optional | Optional structured claim-to-source map (N2 §2.2) for replay tooling |
| `warnings` | array of string | optional | Soft warnings from the chapter writer (e.g. weak-evidence notes) |
| `model_call_id` | string (UUID v4) | yes | Cross-ref to `model_call_ledger.v1.call_id` with `stage == "phase2_chapter_write"` and matching `chapter_id` |
| `generated_at` | string (ISO-8601 UTC) | yes | — |
| `prompt_version` | string | yes | const `"aiyt-chapter-v1"` |

### 5.2 `InlineCitation` sub-object

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `evidence_ref_id` | string | yes | Refers to a `phase1_plan.v1` evidence_ref_id |
| `span` | string | yes | The verbatim cited snippet (≤ 280 chars; N3 §1.1 `cited_segment_snippet`) |
| `trust_level` | enum `["T0","T1","T2"]` | yes | NG-T3 forbidden here |

### 5.3 `VisualRequest` and `Claim` sub-objects

| `VisualRequest` field | Type | Required | Notes |
|----------------------|------|----------|-------|
| `type` | enum `["svg"]` | yes | Only inline SVG is allowed (N3 §2.1) |
| `purpose` | string | yes | E.g. `"architecture"`, `"flow"`, `"comparison"`, `"timeline"` |
| `data_requirements` | array of object | optional | Free-shape per chart type |

| `Claim` field | Type | Required | Notes |
|---------------|------|----------|-------|
| `claim` | string | yes | The reader-facing statement |
| `supporting_evidence_ref_ids` | array of string | yes | Subset of inline_citations' evidence_ref_ids |
| `trust_level` | enum `["T0","T1","T2"]` | yes | NG-T3 forbidden |

### 5.4 JSON Schema (Draft 2020-12)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "solar.ai_influence_youtube.phase2_chapter.v1",
  "title": "phase2_chapter.v1",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version", "run_id", "report_id", "chapter_id",
    "body_md", "inline_citations", "model_call_id",
    "generated_at", "prompt_version"
  ],
  "properties": {
    "schema_version": { "const": "phase2_chapter.v1" },
    "run_id": { "type": "string", "format": "uuid" },
    "report_id": { "type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$" },
    "chapter_id": { "type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$" },
    "body_md": { "type": "string", "minLength": 1 },
    "inline_citations": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["evidence_ref_id", "span", "trust_level"],
        "additionalProperties": false,
        "properties": {
          "evidence_ref_id": { "type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$" },
          "span": { "type": "string", "minLength": 1, "maxLength": 280 },
          "trust_level": { "enum": ["T0", "T1", "T2"] }
        }
      }
    },
    "visual_requests": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["type", "purpose"],
        "additionalProperties": false,
        "properties": {
          "type": { "enum": ["svg"] },
          "purpose": { "type": "string", "minLength": 1 },
          "data_requirements": { "type": "array", "items": { "type": "object" } }
        }
      }
    },
    "claims": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["claim", "supporting_evidence_ref_ids", "trust_level"],
        "additionalProperties": false,
        "properties": {
          "claim": { "type": "string", "minLength": 1 },
          "supporting_evidence_ref_ids": {
            "type": "array",
            "items": { "type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$" }
          },
          "trust_level": { "enum": ["T0", "T1", "T2"] }
        }
      }
    },
    "warnings": { "type": "array", "items": { "type": "string" } },
    "model_call_id": { "type": "string", "format": "uuid" },
    "generated_at": { "type": "string", "format": "date-time" },
    "prompt_version": { "const": "aiyt-chapter-v1" }
  }
}
```

### 5.5 Invariants (one-call-per-chapter)

- I-chap-1: Exactly one `phase2_chapter.v1` object is emitted per `chapter_id` per `run_id` — **no batching** (N2 §2.2). Defense-in-depth: L5 dispatcher rejects a second emission with the same `(run_id, chapter_id)` pair.
- I-chap-2: Every `inline_citations[].evidence_ref_id` MUST resolve to an `evidence_ref_id` in the same run's `phase1_plan.v1`.
- I-chap-3: Every `phase1_plan.v1.chapters[].chapter_id` MUST eventually have a matching `phase2_chapter.v1` before the run can enter `synthesized` state (A1 §3.1 row 5 entry condition).
- I-chap-4: `visual_requests[].type` is currently restricted to `"svg"` (NG2: no raster, no ASCII art); future expansion requires a minor version bump (§0.1).

---

## 6. `phase3_synthesis.v1` — L5 Phase 3 final synthesis

**Used by:** L5 Phase 3 ⇒ L7 markdown / HTML render + archive metadata.
**Source of truth:** N2 §2.3.

### 6.1 Required field summary

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `schema_version` | string | yes | const `"phase3_synthesis.v1"` |
| `run_id` | string (UUID v4) | yes | — |
| `report_id` | string | yes | Same handle as Phase 1/2 |
| `executive_summary_md` | string | yes | The reader-facing thesis paragraph (≥ 1 char) |
| `final_markdown` | string | yes | The full report markdown (sufficient for `report.md` write) |
| `final_html` | string | yes | The full report HTML (sufficient for `report.html` write); contains inline `<svg>` blocks (NG2) |
| `inline_svgs` | array of `InlineSvg` | yes | Per-figure SVG markup, captured verbatim from Phase 2 or template path (N3 §2.3) |
| `cross_chapter_links` | array of `CrossLink` | yes | Possibly empty; carries thematic links across chapters for L7 |
| `source_map_appendix` | array of `SourceMapAppendixRow` | yes | The reader-facing 5-field source map (§7 `evidence_map.v1` row shape, dereferenced and ordered) |
| `editorial_notes` | object | optional | `{central_judgment, material_limits[], excluded_sources[]}` per N2 §2.3 |
| `model_call_id` | string (UUID v4) | yes | Cross-ref to `model_call_ledger.v1.call_id` with `stage == "phase3_synthesis"` |
| `generated_at` | string (ISO-8601 UTC) | yes | — |
| `prompt_version` | string | yes | const `"aiyt-synthesis-v1"` |

### 6.2 Sub-objects

| `InlineSvg` field | Type | Required | Notes |
|-------------------|------|----------|-------|
| `figure_id` | string | yes | Stable handle for archive cross-ref |
| `purpose` | string | yes | Same vocabulary as `phase2_chapter.v1.visual_requests[].purpose` |
| `svg_markup` | string | yes | Verbatim `<svg ...>...</svg>` markup; MUST contain `xmlns="http://www.w3.org/2000/svg"`, `viewBox`, and an accessible label (`aria-label` or `<title>`) per N3 §2.3 |
| `caption` | string \| null | yes | Reader-facing caption; null only when caption is intentionally absent |

| `CrossLink` field | Type | Required | Notes |
|-------------------|------|----------|-------|
| `from_chapter_id` | string | yes | |
| `to_chapter_id` | string | yes | |
| `relation` | string | yes | Free-form short label, e.g. `"supports"`, `"contrasts"`, `"contextualizes"` |

`SourceMapAppendixRow` is exactly the per-entry shape of `evidence_map.v1.entries[]` (§7.2), dereferenced and ordered for reader presentation; see §7 for the canonical definition.

### 6.3 JSON Schema (Draft 2020-12)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "solar.ai_influence_youtube.phase3_synthesis.v1",
  "title": "phase3_synthesis.v1",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version", "run_id", "report_id",
    "executive_summary_md", "final_markdown", "final_html",
    "inline_svgs", "cross_chapter_links", "source_map_appendix",
    "model_call_id", "generated_at", "prompt_version"
  ],
  "properties": {
    "schema_version": { "const": "phase3_synthesis.v1" },
    "run_id": { "type": "string", "format": "uuid" },
    "report_id": { "type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$" },
    "executive_summary_md": { "type": "string", "minLength": 1 },
    "final_markdown": { "type": "string", "minLength": 1 },
    "final_html": { "type": "string", "minLength": 1 },
    "inline_svgs": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["figure_id", "purpose", "svg_markup", "caption"],
        "additionalProperties": false,
        "properties": {
          "figure_id": { "type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$" },
          "purpose": { "type": "string", "minLength": 1 },
          "svg_markup": { "type": "string", "minLength": 1 },
          "caption": { "type": ["string", "null"] }
        }
      }
    },
    "cross_chapter_links": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["from_chapter_id", "to_chapter_id", "relation"],
        "additionalProperties": false,
        "properties": {
          "from_chapter_id": { "type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$" },
          "to_chapter_id": { "type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$" },
          "relation": { "type": "string", "minLength": 1 }
        }
      }
    },
    "source_map_appendix": {
      "type": "array",
      "items": { "$ref": "solar.ai_influence_youtube.evidence_map.v1#/properties/entries/items" }
    },
    "editorial_notes": {
      "type": "object",
      "properties": {
        "central_judgment": { "type": "string" },
        "material_limits": { "type": "array", "items": { "type": "string" } },
        "excluded_sources": { "type": "array", "items": { "type": "object" } }
      }
    },
    "model_call_id": { "type": "string", "format": "uuid" },
    "generated_at": { "type": "string", "format": "date-time" },
    "prompt_version": { "const": "aiyt-synthesis-v1" }
  }
}
```

### 6.4 Invariants

- I-syn-1: `final_html` MUST contain ≥ 1 `<svg ` element (NG2; L6 Check 4).
- I-syn-2: `final_markdown` MUST end on a sentence terminator (`.`, `。`, `!`, `?`, `”`, `」`) and MUST NOT end with `...`, `TBD`, `TODO`, `(continued)` (NG5; L6 Check 3).
- I-syn-3: Every `from_chapter_id`/`to_chapter_id` in `cross_chapter_links` MUST appear in the run's `phase2_chapter.v1` set.
- I-syn-4: `source_map_appendix` MUST be a non-empty subset of the run's `evidence_map.v1.entries` (defense-in-depth for L6 Check 5).

---

## 7. `evidence_map.v1` — per-claim → 5-field source map (validator anchor)

**Used by:** L4/L5 ⇒ L7 reader-facing source map appendix + L6 Check 5.
**Source of truth:** N3 §1.1 (5 reader-facing fields per entry) + dispatch acceptance A-A3-5 (+ `group_type`).

### 7.1 Required field summary

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `schema_version` | string | yes | const `"evidence_map.v1"` |
| `run_id` | string (UUID v4) | yes | — |
| `report_id` | string | yes | |
| `entries` | array of `EvidenceMapEntry` | yes | ≥ 1 entry; L6 Check 5 rejects empty maps |
| `generated_at` | string (ISO-8601 UTC) | yes | — |

### 7.2 `EvidenceMapEntry` (the 5 reader-facing fields + `group_type`)

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `evidence_ref_id` | string | yes | Cross-ref into `phase1_plan.v1` |
| `channel` | string | yes | **(reader 1/5)** N3 §1.1 field 1 |
| `title` | string | yes | **(reader 2/5)** N3 §1.1 field 2 |
| `published_at` | string (ISO-8601 date) | yes | **(reader 3/5)** N3 §1.1 field 3 |
| `transcript_grade` | enum `["T0","T1","T2"]` | yes | **(reader 4/5)** N3 §1.1 `trust_level`; renamed in spec language to `transcript_grade` per dispatch acceptance row A-A3-5 |
| `citation_span` | string | yes | **(reader 5/5)** N3 §1.1 `cited_segment_snippet`, ≤ 280 chars, no internal `...` truncation |
| `group_type` | enum (7 values) | yes | The L3 `classification_decision.v1.group_type` for this entry's video; carried forward so the validator (Check 7) can audit reader-facing surfaces |

### 7.3 JSON Schema (Draft 2020-12)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "solar.ai_influence_youtube.evidence_map.v1",
  "title": "evidence_map.v1",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "run_id", "report_id", "entries", "generated_at"],
  "properties": {
    "schema_version": { "const": "evidence_map.v1" },
    "run_id": { "type": "string", "format": "uuid" },
    "report_id": { "type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$" },
    "entries": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": [
          "evidence_ref_id", "channel", "title", "published_at",
          "transcript_grade", "citation_span", "group_type"
        ],
        "additionalProperties": false,
        "properties": {
          "evidence_ref_id": { "type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$" },
          "channel": { "type": "string", "minLength": 1 },
          "title": { "type": "string", "minLength": 1 },
          "published_at": { "type": "string", "format": "date" },
          "transcript_grade": { "enum": ["T0", "T1", "T2"] },
          "citation_span": { "type": "string", "minLength": 1, "maxLength": 280 },
          "group_type": {
            "enum": ["event", "conference", "keynote", "interview", "tutorial", "product_update", "other"]
          }
        }
      }
    },
    "generated_at": { "type": "string", "format": "date-time" }
  }
}
```

### 7.4 Invariants

- I-evid-1: `entries[].transcript_grade == "T3"` is forbidden (enum excludes T3). Defense-in-depth at L6 Check 6.
- I-evid-2: `citation_span` MUST NOT contain internal `...` truncation (matches anywhere except boundary ellipsis). L6 Check 3 / N3 §1.1 enforce this.
- I-evid-3: Every plan-level `evidence_ref_id` in the run's `phase1_plan.v1` MUST appear in `entries` (L6 Check 5: every plan evidence_ref resolvable).
- I-evid-4: This schema is the **anchor for L6 Check 5**: the validator parses `evidence_map.json` and counts these 6 fields per entry (5 reader-facing + `group_type`).

---

## 8. `source_mapping.v1` — render contract for the reader-facing 5 fields

**Used by:** L7 markdown + HTML renderer (per N3 §1.3) — wraps a single `evidence_map.v1.entries[]` row in canonical reader form.
**Source of truth:** N3 §1.1 + §1.3.

### 8.1 Purpose

`evidence_map.v1` is the **machine-readable** anchor. `source_mapping.v1` is the **render contract** that says how a single `EvidenceMapEntry` materializes in the reader-facing markdown footer and HTML `<blockquote class="evidence">`. Both schemas reference the same 5-field surface but `source_mapping.v1` adds renderer constraints.

### 8.2 Required field summary

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `schema_version` | string | yes | const `"source_mapping.v1"` |
| `evidence_ref_id` | string | yes | Cross-ref into `evidence_map.v1.entries[]` |
| `channel` | string | yes | (reader 1/5) |
| `title` | string | yes | (reader 2/5) |
| `published_at` | string (ISO-8601 date) | yes | (reader 3/5) |
| `transcript_grade` | enum `["T0","T1","T2"]` | yes | (reader 4/5) |
| `citation_span` | string | yes | (reader 5/5), ≤ 280 chars |
| `rendering` | object | yes | (§8.3) |

### 8.3 `rendering` sub-object (render constraints)

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `markdown_format` | string | yes | const `"blockquote_quote_then_footer"`; MUST produce the 4-segment `·`-separated footer (channel · title · date · trust) per N3 §1.3 |
| `html_format` | string | yes | const `"blockquote_evidence_v1"`; MUST produce `<blockquote class="evidence" data-trust="T?">…</blockquote>` per N3 §1.3 |
| `html_class` | string | yes | const `"evidence"`; controls validator Check 1 grep behavior (no `data-video-id`, `data-internal-id`, `data-pipeline-*` allowed) |
| `data_trust_attr` | string | yes | const `"data-trust"`; the HTML data-attribute that holds the trust grade |

### 8.4 JSON Schema (Draft 2020-12)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "solar.ai_influence_youtube.source_mapping.v1",
  "title": "source_mapping.v1",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version", "evidence_ref_id", "channel", "title",
    "published_at", "transcript_grade", "citation_span", "rendering"
  ],
  "properties": {
    "schema_version": { "const": "source_mapping.v1" },
    "evidence_ref_id": { "type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$" },
    "channel": { "type": "string", "minLength": 1 },
    "title": { "type": "string", "minLength": 1 },
    "published_at": { "type": "string", "format": "date" },
    "transcript_grade": { "enum": ["T0", "T1", "T2"] },
    "citation_span": { "type": "string", "minLength": 1, "maxLength": 280 },
    "rendering": {
      "type": "object",
      "additionalProperties": false,
      "required": ["markdown_format", "html_format", "html_class", "data_trust_attr"],
      "properties": {
        "markdown_format": { "const": "blockquote_quote_then_footer" },
        "html_format": { "const": "blockquote_evidence_v1" },
        "html_class": { "const": "evidence" },
        "data_trust_attr": { "const": "data-trust" }
      }
    }
  }
}
```

### 8.5 Invariants

- I-src-1: `source_mapping.v1` is **structurally a superset** of one `evidence_map.v1.entries[]` row (it adds the `rendering` block); the 5 reader-facing fields MUST be exactly equal between the two.
- I-src-2: `transcript_grade == "T3"` is forbidden (enum excludes T3).
- I-src-3: The renderer MUST NOT emit any HTML attribute matching `data-video-id`, `data-internal-id`, `data-pipeline-*` (NG4; L6 Check 1 grep blacklist defense-in-depth).

---

## 9. `validator_report.v1` — L6 output (8 checks)

**Used by:** L6 ⇒ L7 archive gate.
**Source of truth:** N3 §3.1 (8 checks) + §3.3 (exit code policy).

### 9.1 Required field summary

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `schema_version` | string | yes | const `"validator_report.v1"` |
| `run_id` | string (UUID v4) | yes | — |
| `report_dir` | string | yes | Filesystem path to the directory holding the 4 artifacts |
| `validator_version` | string | yes | regex `^v\d+\.\d+\.\d+$`; bumped on blacklist additions per N3 §3.4 |
| `checks` | array of `CheckResult` | yes | Exactly **8** entries (§9.2) |
| `overall` | enum `["PASS","FAIL"]` | yes | `PASS` iff every `check.status == "PASS"` |
| `failed_check_ids` | array of integer | yes | Subset of `[1..8]`; empty when `overall == "PASS"` |
| `t` | string (ISO-8601 UTC) | yes | When the validator finished |

### 9.2 `CheckResult` sub-object

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `id` | integer | yes | 1..8 (one per N3 §3.1 row) |
| `name` | string | yes | Human-readable per N3 §3.1 (verbatim — see §9.4 below) |
| `status` | enum `["PASS","FAIL"]` | yes | |
| `evidence` | string | yes | Free-form, ≤ 2048 chars — for `PASS`, a short confirmation; for `FAIL`, the offending text or path |
| `diff` | string | conditional | **Required** when `status == "FAIL"`; the per-check diff (e.g. matched blacklist tokens, regex hits) |

### 9.3 JSON Schema (Draft 2020-12)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "solar.ai_influence_youtube.validator_report.v1",
  "title": "validator_report.v1",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version", "run_id", "report_dir", "validator_version",
    "checks", "overall", "failed_check_ids", "t"
  ],
  "properties": {
    "schema_version": { "const": "validator_report.v1" },
    "run_id": { "type": "string", "format": "uuid" },
    "report_dir": { "type": "string", "minLength": 1 },
    "validator_version": { "type": "string", "pattern": "^v\\d+\\.\\d+\\.\\d+$" },
    "checks": {
      "type": "array",
      "minItems": 8,
      "maxItems": 8,
      "items": {
        "type": "object",
        "required": ["id", "name", "status", "evidence"],
        "additionalProperties": false,
        "properties": {
          "id": { "type": "integer", "minimum": 1, "maximum": 8 },
          "name": { "type": "string", "minLength": 1 },
          "status": { "enum": ["PASS", "FAIL"] },
          "evidence": { "type": "string", "maxLength": 2048 },
          "diff": { "type": "string" }
        },
        "if": { "properties": { "status": { "const": "FAIL" } } },
        "then": { "required": ["diff"] }
      }
    },
    "overall": { "enum": ["PASS", "FAIL"] },
    "failed_check_ids": {
      "type": "array",
      "items": { "type": "integer", "minimum": 1, "maximum": 8 }
    },
    "t": { "type": "string", "format": "date-time" }
  }
}
```

### 9.4 Canonical 8 check names (verbatim from N3 §3.1)

| `id` | `name` |
|------|--------|
| 1 | `No internal-vocabulary leak` |
| 2 | `No bare video_id leak` |
| 3 | `No truncation tail` |
| 4 | `SVG present` |
| 5 | `evidence_map.json intact` |
| 6 | `No T3 in core evidence` |
| 7 | `group_type whitelist` |
| 8 | `Hierarchy intact` |

### 9.5 Invariants

- I-val-1: `checks.length == 8` and `{checks[].id} == {1..8}` (exhaustive, no duplicates).
- I-val-2: `overall == "PASS"` ⇔ every `checks[].status == "PASS"` ⇔ `failed_check_ids == []`.
- I-val-3: `validator_version` is bumped (minor) whenever the grep blacklist (`lib/ai-influence-report/forbidden-tokens.txt`) is extended; downstream tooling MAY read this to detect blacklist drift.
- I-val-4: The validator MUST NOT make any network call (e.g. ChatGPT URL reachability); enforced by L6 contract (A1 §1.L6) and out-of-band audit (N3 §4.3).

---

## 10. `model_call_ledger.v1` — append-only L5 call ledger row

**Used by:** L5 ⇒ central cost rollup + sprint closeout audit.
**Source of truth:** N2 §4; A1 §4.2.

### 10.1 Required field summary

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `schema_version` | string | yes | const `"model_call_ledger.v1"` |
| `call_id` | string (UUID v4) | yes | Unique per call; referenced by `runs.jsonl.model_call_id` and by every L5 phase output's `model_call_id` |
| `module` | string | yes | const `"ai_influence_youtube"` (multi-module ledger disambiguator) |
| `stage` | enum `["phase1_plan","phase2_chapter_write","phase3_synthesis"]` | yes | 1:1 with L5 phases (dispatch acceptance A-A3-7 uses the short labels phase1/phase2/phase3; the canonical wire labels are the longer forms here, aligned with N2 §4) |
| `model` | string | yes | const `"chatgpt-5.5-thinking-high"` (NG3 enforcement: any other value is a contract violation) |
| `provider` | string | yes | const `"browser_agent_chatgpt"` (NG3 sibling) |
| `sprint_id` | string | yes | The originating sprint (this sprint = `sprint-20260528-…-s02-architecture`); inherited by downstream runs |
| `report_id` | string | yes | Same handle as Phase 1/2/3 outputs |
| `chapter_id` | string \| null | yes | Required when `stage == "phase2_chapter_write"`; null otherwise (defense-in-depth conditional in §10.2) |
| `browser_session_id` | string | yes | Stable handle from the Browser Agent wrapper |
| `chatgpt_project` | string | yes | const `"杂项"` (N3 §4.3) |
| `chatgpt_url` | string \| null | yes | Reachable URL; null only when Browser Agent failed before allocating a conversation. **Aliases:** `conversation_url` is the N2 §4 wire name; `chatgpt_url` is the dispatch-row alias. This schema accepts `chatgpt_url` as canonical and treats `conversation_url` as a forbidden additional property — A4 will document the rename in the compat adapter. |
| `cost` | number | yes | Dispatch-row label for `estimated_cost_usd`; nominally USD; `0.0` when unknown |
| `input_tokens_estimate` | integer | optional | Best-effort |
| `output_tokens_estimate` | integer | optional | Best-effort |
| `latency_ms` | integer | yes | Wall-clock round-trip in milliseconds (dispatch row label) |
| `call_count` | integer | yes | Always `1` per row; central rollup is a sum |
| `prompt_version` | string | yes | enum `["aiyt-plan-v1","aiyt-chapter-v1","aiyt-synthesis-v1"]` |
| `archive_status` | enum `["pending","archived","failed"]` | yes | Reflects the 杂项 archival outcome |
| `outcome` | enum `["ok","unreachable","malformed_json","retry_then_ok"]` | yes | Drives A1 §6 rows 4-5 recovery |
| `created_at` | string (ISO-8601 UTC) | yes | When the row was appended |

### 10.2 JSON Schema (Draft 2020-12)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "solar.ai_influence_youtube.model_call_ledger.v1",
  "title": "model_call_ledger.v1",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version", "call_id", "module", "stage", "model", "provider",
    "sprint_id", "report_id", "chapter_id", "browser_session_id",
    "chatgpt_project", "chatgpt_url", "cost", "latency_ms",
    "call_count", "prompt_version", "archive_status", "outcome", "created_at"
  ],
  "properties": {
    "schema_version": { "const": "model_call_ledger.v1" },
    "call_id": { "type": "string", "format": "uuid" },
    "module": { "const": "ai_influence_youtube" },
    "stage": { "enum": ["phase1_plan", "phase2_chapter_write", "phase3_synthesis"] },
    "model": { "const": "chatgpt-5.5-thinking-high" },
    "provider": { "const": "browser_agent_chatgpt" },
    "sprint_id": { "type": "string", "minLength": 1 },
    "report_id": { "type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$" },
    "chapter_id": {
      "anyOf": [
        { "type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$" },
        { "type": "null" }
      ]
    },
    "browser_session_id": { "type": "string", "minLength": 1 },
    "chatgpt_project": { "const": "杂项" },
    "chatgpt_url": { "type": ["string", "null"] },
    "cost": { "type": "number", "minimum": 0.0 },
    "input_tokens_estimate": { "type": "integer", "minimum": 0 },
    "output_tokens_estimate": { "type": "integer", "minimum": 0 },
    "latency_ms": { "type": "integer", "minimum": 0 },
    "call_count": { "const": 1 },
    "prompt_version": { "enum": ["aiyt-plan-v1", "aiyt-chapter-v1", "aiyt-synthesis-v1"] },
    "archive_status": { "enum": ["pending", "archived", "failed"] },
    "outcome": { "enum": ["ok", "unreachable", "malformed_json", "retry_then_ok"] },
    "created_at": { "type": "string", "format": "date-time" }
  },
  "allOf": [
    {
      "if": { "properties": { "stage": { "const": "phase2_chapter_write" } } },
      "then": { "properties": { "chapter_id": { "type": "string" } } }
    },
    {
      "if": { "properties": { "stage": { "not": { "const": "phase2_chapter_write" } } } },
      "then": { "properties": { "chapter_id": { "type": "null" } } }
    }
  ]
}
```

### 10.3 Invariants

- I-led-1: Phase 2 emits exactly one ledger row per chapter (no batching; N2 §2.2).
- I-led-2: A row MUST be appended **before** the L5 call result is consumed by L6 (A1 §4.2 audit anchor).
- I-led-3: `outcome == "unreachable"` after one retry → control plane raises `run_rejected_model_unreachable`; no NG3-allowed fallback (A1 §6 row 4).
- I-led-4: `model` and `provider` are literals; any other value is a contract violation flagged at sprint closeout.
- I-led-5: The dispatch-row label `cost` and the N2 §4 wire label `estimated_cost_usd` refer to the same quantity; this schema uses `cost` as canonical; A4 compat adapter records the rename for backward compat with N2 §4 consumers.

---

## 11. `archive_manifest.v1` — L7 commit receipt

**Used by:** L7 archive writer ⇒ audit trail.
**Source of truth:** N3 §4.2 (4-artifact closeout) + A1 §4.4.

### 11.1 Required field summary

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `schema_version` | string | yes | const `"archive_manifest.v1"` |
| `archive_dir` | string | yes | Absolute path to `~/Knowledge/_raw/tech-hotspot-radar/ai-influence-planned/<YYYY-MM-DD>/reports/<report_slug>/` |
| `run_id` | string (UUID v4) | yes | The producing run |
| `report_id` | string | yes | The producing report |
| `report_slug` | string | yes | regex `^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$`; the leaf directory name |
| `artifacts` | array of `ArtifactRow` | yes | **Exactly 4** mandatory entries (§11.2), plus optional sidecars |
| `chatgpt_session_url` | string \| null | yes | From `chatgpt-session.json` sidecar (N3 §4.3); null if absent |
| `validator_report_path` | string | yes | Path to the producing `validator_report.v1` JSON |
| `state_at_commit` | string | yes | const `"archived"` (state machine pinning per A1 §3.1; the manifest is only written from the `archived` terminal-success state) |
| `created_at` | string (ISO-8601 UTC) | yes | Commit timestamp |

### 11.2 `ArtifactRow` (4 mandatory types)

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `path` | string | yes | Absolute path under `archive_dir` |
| `sha256` | string | yes | regex `^[a-f0-9]{64}$` |
| `type` | enum `["md","html","plan_json","evidence_map_json","chatgpt_session_json"]` | yes | The 4 mandatory types are `md`, `html`, `plan_json`, `evidence_map_json`; `chatgpt_session_json` is an optional sidecar (N3 §4.3); future expansion requires a minor version bump |
| `bytes` | integer | yes | File size in bytes; non-negative |

The 4 mandatory types `{md, html, plan_json, evidence_map_json}` MUST each appear exactly once in `artifacts[]`. Defense-in-depth via per-type cardinality check in §11.4.

### 11.3 JSON Schema (Draft 2020-12)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "solar.ai_influence_youtube.archive_manifest.v1",
  "title": "archive_manifest.v1",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version", "archive_dir", "run_id", "report_id",
    "report_slug", "artifacts", "chatgpt_session_url",
    "validator_report_path", "state_at_commit", "created_at"
  ],
  "properties": {
    "schema_version": { "const": "archive_manifest.v1" },
    "archive_dir": { "type": "string", "minLength": 1 },
    "run_id": { "type": "string", "format": "uuid" },
    "report_id": { "type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$" },
    "report_slug": { "type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$" },
    "artifacts": {
      "type": "array",
      "minItems": 4,
      "items": {
        "type": "object",
        "required": ["path", "sha256", "type", "bytes"],
        "additionalProperties": false,
        "properties": {
          "path": { "type": "string", "minLength": 1 },
          "sha256": { "type": "string", "pattern": "^[a-f0-9]{64}$" },
          "type": {
            "enum": ["md", "html", "plan_json", "evidence_map_json", "chatgpt_session_json"]
          },
          "bytes": { "type": "integer", "minimum": 0 }
        }
      },
      "allOf": [
        { "contains": { "properties": { "type": { "const": "md" } } } },
        { "contains": { "properties": { "type": { "const": "html" } } } },
        { "contains": { "properties": { "type": { "const": "plan_json" } } } },
        { "contains": { "properties": { "type": { "const": "evidence_map_json" } } } }
      ]
    },
    "chatgpt_session_url": { "type": ["string", "null"] },
    "validator_report_path": { "type": "string", "minLength": 1 },
    "state_at_commit": { "const": "archived" },
    "created_at": { "type": "string", "format": "date-time" }
  }
}
```

### 11.4 Invariants

- I-arc-1: The 4 mandatory types `{md, html, plan_json, evidence_map_json}` MUST appear exactly once; the optional `chatgpt_session_json` MAY appear 0 or 1 times. Defense-in-depth: a downstream validator counts type occurrences.
- I-arc-2: `archive_manifest.v1` is emitted **only** after all artifacts land via atomic rename (N3 §4.2; A1 §I-9). If any artifact write fails, none of the 4 land and `archive_manifest.json` is not emitted.
- I-arc-3: `state_at_commit` is pinned to the literal `"archived"` — the manifest is the wire-level proof of A1 §3.1 row 8 success.
- I-arc-4: `report_slug` and `archive_dir` MUST agree: `archive_dir` MUST end with `<YYYY-MM-DD>/reports/<report_slug>/` (no path validation at JSON-schema level; A4 spec lock-in).

---

## 12. `run_record.v1` — control-plane run state object

**Used by:** Control plane state machine (snapshot file `report_state.json`) and central audit.
**Source of truth:** A1 §3 (8 success states + `run_rejected_*` terminals).

### 12.1 Required field summary

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `schema_version` | string | yes | const `"run_record.v1"` |
| `run_id` | string (UUID v4) | yes | Minted at L1 |
| `replayed_from` | string (UUID v4) \| null | yes | Set when this run was started via `replay --run-id <prev>`; null on the original run |
| `state` | string | yes | enum: 8 success states ∪ 7 rejection terminals (§12.2) |
| `week` | string \| null | yes | `^[0-9]{4}-W[0-5][0-9]$`; null only if `--date-range` was used |
| `date_range` | object \| null | yes | `{start, end}` (ISO-8601 dates) if `--date-range` was used; null otherwise; **either `week` or `date_range` MUST be non-null** |
| `phase_artifacts` | object | yes | Map from phase name to artifact path + sha256 (§12.3) |
| `step_log` | array of `StepLogRow` | yes | A coarse summary of `runs.jsonl` events; the canonical log is the JSONL stream itself |
| `model_call_ids` | array of string | yes | UUIDs of all L5 ledger rows belonging to this run |
| `validator_report_path` | string \| null | yes | Path to the producing `validator_report.v1` JSON; null until L6 has run |
| `archive_manifest_path` | string \| null | yes | Path to the `archive_manifest.v1` JSON; null until L7 has committed |
| `terminal_reason` | string \| null | yes | Free-form, ≤ 256 chars; non-null only when `state` is a `run_rejected_*` terminal |
| `created_at` | string (ISO-8601 UTC) | yes | Run creation (= L1 entry) |
| `updated_at` | string (ISO-8601 UTC) | yes | Last state transition |

### 12.2 `state` enum (pinned to A1 §3)

8 success-path states (A1 §3.1):

```
created, graded, grouped, planned, chaptered, synthesized, validated, archived
```

3 PRD-required rejection terminals (A1 §3.2):

```
run_rejected_t3_only, run_rejected_validator, run_rejected_model_unreachable
```

4 additional rejection terminals (A1 §3.3):

```
run_rejected_upstream_unreachable, run_rejected_hierarchy,
run_rejected_archive_io, run_rejected_upstream_drift
```

### 12.3 `phase_artifacts` sub-object

Maps each completed phase to its artifact pointer. Keys are the canonical artifact names:

| Key | Value type | Notes |
|-----|------------|-------|
| `gate_decisions` | `{ path: string, sha256: string }` | The `gate_decision.v1` collection (typically one array of decisions per run) |
| `t3_exclusions` | `{ path: string, sha256: string }` | Per §2 |
| `classification_decisions` | `{ path: string, sha256: string }` | Per §3 |
| `phase1_plan` | `{ path: string, sha256: string }` | Per §4 |
| `phase2_chapters` | `{ path: string, sha256: string }` | A directory pointer or index file referencing per-chapter outputs (§5) |
| `phase3_synthesis` | `{ path: string, sha256: string }` | Per §6 |
| `evidence_map` | `{ path: string, sha256: string }` | Per §7 |
| `validator_report` | `{ path: string, sha256: string }` | Per §9 |
| `archive_manifest` | `{ path: string, sha256: string }` | Per §11 |

Each entry is added at the time of phase completion; missing entries indicate the phase has not yet completed for the current run. `sha256` is the file-level hash, used by A1 §3.5 R4 to validate replay safety.

### 12.4 `StepLogRow` sub-object

A coarse summary line; the canonical event log is `runs.jsonl` (A1 §4.1).

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `step` | string | yes | E.g. `"L2.gate"`, `"L5.phase2.<chapter_id>"` |
| `outcome` | enum `["ok","fail","skip","retry"]` | yes | |
| `t` | string (ISO-8601 UTC) | yes | |
| `evidence_path` | string \| null | yes | Optional pointer; null if the step produced no on-disk artifact |

### 12.5 JSON Schema (Draft 2020-12)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "solar.ai_influence_youtube.run_record.v1",
  "title": "run_record.v1",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version", "run_id", "replayed_from", "state",
    "week", "date_range", "phase_artifacts", "step_log",
    "model_call_ids", "validator_report_path", "archive_manifest_path",
    "terminal_reason", "created_at", "updated_at"
  ],
  "properties": {
    "schema_version": { "const": "run_record.v1" },
    "run_id": { "type": "string", "format": "uuid" },
    "replayed_from": { "anyOf": [{ "type": "string", "format": "uuid" }, { "type": "null" }] },
    "state": {
      "enum": [
        "created", "graded", "grouped", "planned",
        "chaptered", "synthesized", "validated", "archived",
        "run_rejected_t3_only", "run_rejected_validator", "run_rejected_model_unreachable",
        "run_rejected_upstream_unreachable", "run_rejected_hierarchy",
        "run_rejected_archive_io", "run_rejected_upstream_drift"
      ]
    },
    "week": {
      "anyOf": [
        { "type": "string", "pattern": "^[0-9]{4}-W[0-5][0-9]$" },
        { "type": "null" }
      ]
    },
    "date_range": {
      "anyOf": [
        {
          "type": "object",
          "required": ["start", "end"],
          "additionalProperties": false,
          "properties": {
            "start": { "type": "string", "format": "date" },
            "end": { "type": "string", "format": "date" }
          }
        },
        { "type": "null" }
      ]
    },
    "phase_artifacts": {
      "type": "object",
      "additionalProperties": {
        "type": "object",
        "required": ["path", "sha256"],
        "additionalProperties": false,
        "properties": {
          "path": { "type": "string", "minLength": 1 },
          "sha256": { "type": "string", "pattern": "^[a-f0-9]{64}$" }
        }
      }
    },
    "step_log": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["step", "outcome", "t", "evidence_path"],
        "additionalProperties": false,
        "properties": {
          "step": { "type": "string", "minLength": 1 },
          "outcome": { "enum": ["ok", "fail", "skip", "retry"] },
          "t": { "type": "string", "format": "date-time" },
          "evidence_path": { "type": ["string", "null"] }
        }
      }
    },
    "model_call_ids": {
      "type": "array",
      "items": { "type": "string", "format": "uuid" }
    },
    "validator_report_path": { "type": ["string", "null"] },
    "archive_manifest_path": { "type": ["string", "null"] },
    "terminal_reason": { "type": ["string", "null"], "maxLength": 256 },
    "created_at": { "type": "string", "format": "date-time" },
    "updated_at": { "type": "string", "format": "date-time" }
  },
  "allOf": [
    {
      "if": {
        "properties": {
          "state": {
            "enum": [
              "run_rejected_t3_only", "run_rejected_validator", "run_rejected_model_unreachable",
              "run_rejected_upstream_unreachable", "run_rejected_hierarchy",
              "run_rejected_archive_io", "run_rejected_upstream_drift"
            ]
          }
        }
      },
      "then": { "properties": { "terminal_reason": { "type": "string" } } }
    },
    {
      "if": { "properties": { "state": { "const": "archived" } } },
      "then": {
        "required": ["archive_manifest_path"],
        "properties": { "archive_manifest_path": { "type": "string" } }
      }
    }
  ]
}
```

### 12.6 Invariants

- I-run-1: `state` is **pinned to A1's enumeration** — 8 success + 7 rejection terminals; no new state may be introduced without bumping the major version (§0.1).
- I-run-2: `archived` requires `archive_manifest_path != null` and `validator_report_path != null`; pre-archive transitions require the corresponding `phase_artifacts` entries.
- I-run-3: Any `run_rejected_*` state requires `terminal_reason != null` (the human-readable summary; canonical evidence remains in `runs.jsonl`).
- I-run-4: `state` transitions are append-only at the event level (`runs.jsonl`); the snapshot file is overwrite-on-transition via atomic rename (A1 §3.5 R2). The JSON-schema does not enforce ordering.
- I-run-5: `replayed_from != null` implies a new `run_id` was minted by `replay --run-id <prev>` (A1 §3.5 R3); the previous run remains terminal under its own `run_id`.

---

## 13. Cross-schema invariants (locked across all 12 artifacts)

These invariants span more than one schema and are enforced at the consumer boundary. A2 codifies the Python contracts; L6 validator provides defense-in-depth.

| ID | Invariant | Schemas touched |
|----|-----------|-----------------|
| X-1 | `run_id` is identical across all per-run artifacts (`gate_decision`, `t3_exclusions`, `classification_decision`, `phase1_plan`, `phase2_chapter`, `phase3_synthesis`, `evidence_map`, `validator_report`, `archive_manifest`, `run_record`, `model_call_ledger`). | all 12 |
| X-2 | `report_id` is identical across `phase1_plan`, `phase2_chapter`, `phase3_synthesis`, `evidence_map`, `archive_manifest`, `model_call_ledger`. | 6 |
| X-3 | `chapter_id` set in `phase1_plan.trends[].chapters[]` = `chapter_id` set across all `phase2_chapter.v1` rows for that run = `chapter_id` set across all `model_call_ledger.v1` rows with `stage == "phase2_chapter_write"` for that run. | 3 |
| X-4 | `evidence_ref_id` set in `phase1_plan.trends[].chapters[].subsections[].evidence_refs[]` ⊆ `evidence_map.entries[].evidence_ref_id` (every plan ref is resolvable; L6 Check 5). | 2 |
| X-5 | `model_call_id` in any phase output `∈ model_call_ledger.call_id` set for that run, with matching `stage` (X-3 sibling for Phase 2). | 4 |
| X-6 | T3 grade never appears in `phase1_plan`, `phase2_chapter`, `phase3_synthesis`, `evidence_map`, or `source_mapping` (NG-T3; defense-in-depth at L6 Check 6). | 5 |
| X-7 | `model == "chatgpt-5.5-thinking-high"` and `provider == "browser_agent_chatgpt"` on every `model_call_ledger.v1` row for this module (NG3). | 1 |
| X-8 | `chatgpt_project == "杂项"` on every `model_call_ledger.v1` row (N3 §4.3). | 1 |
| X-9 | `archive_manifest.v1.state_at_commit == "archived"` and the corresponding `run_record.v1.state == "archived"`; both must agree for the run to be considered successful. | 2 |
| X-10 | Internal fields (`video_id` literal, `V[0-9]{3}`, `raw_refs`, `pipeline_fields`, `transcript_status`, `processing_log`) MUST NOT appear in `evidence_map`, `source_mapping`, `phase1_plan` reader-facing fields, `phase2_chapter.body_md`, `phase3_synthesis.final_markdown/final_html`. (NG4; L6 Check 1/2.) | 5 |
| X-11 | Every schema in this document declares `schema_version` as `const` — consumers can branch on it before parsing. (§0.1.) | all 12 |
| X-12 | `gate_version` (§1) and `classifier_version` (§3) are bumped together when N1 §1.1 thresholds or §2.2 signal weights change; downstream tooling MAY compare them for drift. | 2 |

---

## 14. Acceptance traceability (this node A3)

S02 dispatch acceptance for A3 (eight bullets, verbatim from the dispatch file):

| Acceptance ID | Bullet (verbatim) | Section(s) of this doc | Status |
|---------------|-------------------|-------------------------|--------|
| A-A3-1 | `gate_decision.v1` schema: video_id, grade enum T0/T1/T2/T3, entity_recall, wer, segment_density, evidence_notes | §1 (incl. §1.3 JSON Schema) | covered |
| A-A3-2 | `t3_exclusions.v1` schema: run_id, excluded_video_ids list, per_video_reason map, generated_at | §2 (incl. §2.3 JSON Schema) | covered |
| A-A3-3 | `classification_decision.v1` schema: video_id, group_type 7-value enum, confidence, signal_breakdown S1..S6, fallback_used | §3 (incl. §3.3 JSON Schema) | covered |
| A-A3-4 | `phase1_plan.v1` / `phase2_chapter.v1` / `phase3_synthesis.v1` schemas with trend→chapter→subsection→evidence_refs hierarchy and `model_call_id` linkage | §4 (incl. §4.2 hierarchy + §4.4 JSON Schema), §5 (incl. §5.4 JSON Schema), §6 (incl. §6.3 JSON Schema) | covered |
| A-A3-5 | `evidence_map.v1` schema: 5 reader-facing fields per entry (channel, title, published_at, transcript_grade, citation_span) + `group_type` | §7 (incl. §7.2 the 5-field table + group_type, §7.3 JSON Schema) | covered |
| A-A3-6 | `validator_report.v1` schema: 8 checks with status enum PASS/FAIL + evidence + diff; overall enum | §9 (incl. §9.2 CheckResult, §9.3 JSON Schema, §9.4 canonical 8 names) | covered |
| A-A3-7 | `model_call_ledger.v1` schema: call_id, stage enum phase1/phase2/phase3, cost, sprint_id, browser_session_id, chatgpt_url, latency_ms | §10 (incl. §10.2 JSON Schema with stage aliases) | covered |
| A-A3-8 | `archive_manifest.v1` + `run_record.v1` schemas with state machine pinning and 4-artifact-type closeout | §11 (incl. §11.2 the 4 mandatory types, §11.3 JSON Schema with `contains` enforcement), §12 (incl. §12.2 enum pinned to A1 §3, §12.5 JSON Schema) | covered |

In addition, `source_mapping.v1` (§8) is delivered as a sibling render contract to `evidence_map.v1` (sprint design §3 table — source_mapping listed as a top-level cross-component artifact); it is required by L7 and surfaces alongside the dispatch's acceptance row A-A3-5.

Cross-reference to S01 outcome traceability:

| S01 outcome | A3 anchors |
|-------------|------------|
| O1 (T0-T3 gate) | §1 `gate_decision.v1`, §2 `t3_exclusions.v1` |
| O2 (7 group_type) | §3 `classification_decision.v1`, §7 `evidence_map.v1.entries[].group_type` |
| O3 (3-phase ChatGPT invocation) | §4 / §5 / §6 phase outputs; §10 ledger stage enum |
| O4 (structured JSON hierarchy) | §4 `phase1_plan.v1` trend→chapter→subsection→evidence_refs |
| O5 (reader-facing source mapping) | §7 `evidence_map.v1`, §8 `source_mapping.v1` |
| O7 (8 validator checks) | §9 `validator_report.v1` with 8-entry `checks[]` |
| O8 (archive layout) | §11 `archive_manifest.v1` with 4-artifact closeout, §12 `run_record.v1` state pinning |

---

## 15. Risks and OQ (A3-local)

| OQ id | Risk | Mitigation | Owner |
|-------|------|------------|-------|
| OQ-A3-01 | Stage name divergence: dispatch acceptance uses short labels `phase1`/`phase2`/`phase3`; N2 §4 + A1 §4.2 use long labels `phase1_plan`/`phase2_chapter_write`/`phase3_synthesis`. §10 pins the long labels as canonical wire format. | A4 compat adapter MUST document the short-label aliases as renderer-only and reject short labels at the wire boundary. | A4 |
| OQ-A3-02 | `chatgpt_url` (dispatch acceptance) vs `conversation_url` (N2 §4) wire-name conflict. §10 picks `chatgpt_url`. | A4 compat adapter MUST handle the rename (one-way: accept `conversation_url` from legacy emitters, output `chatgpt_url` going forward). | A4 |
| OQ-A3-03 | `cost` (dispatch acceptance) vs `estimated_cost_usd` (N2 §4) wire-name conflict. §10 picks `cost`. | Same as OQ-A3-02 — A4 compat adapter ownership. | A4 |
| OQ-A3-04 | JSON Schema `if/then` conditional for `chapter_id` (§10.2) requires Draft 2020-12 evaluator that supports it; some lightweight validators only handle Draft 07. | Builder S03 MUST pin a Draft 2020-12 validator (e.g. `jsonschema>=4.18` on Python); A2 surface contract MUST declare this. | A2 / S03 |
| OQ-A3-05 | The 4 additional non-PRD `run_rejected_*` terminals (`upstream_unreachable`, `hierarchy`, `archive_io`, `upstream_drift`) added by A1 §3.3 enter `run_record.v1.state` enum; A1 OQ-A1-05 already flags they need A5 sprint-level sign-off. | A5 to accept them in sprint-level acceptance review. | A5 |
| OQ-A3-06 | `evidence_map.v1.entries[].citation_span` 280-char cap (N3 §1.1) may be too tight for CJK content (N3 §8.5). | A4 to decide whether to introduce a per-language byte/character cap or a minor-version bump that adds an optional `citation_span_lang` field. | A4 |
| OQ-A3-07 | `source_mapping.v1` (§8) is not in the dispatch acceptance's 12-name list explicitly but IS in the sprint design §3 cross-component-artifact table; included here for completeness. | A5 sprint-level review to confirm `source_mapping.v1` belongs in A3's deliverable set (we believe it does — the L7 render contract is part of the data model). | A5 |
| OQ-A3-08 | Mirage VFS degraded during this dispatch's KB context inject (`mirage:timeout` in the runtime context); carried from S01 OQ-S02-07 and A1 OQ-A1-07. Other 3 KB sources covered. | Not A3-fixable; cross-pane infra. | Cross-pane infra |

---

## 16. Scope compliance

- Write scope: `docs/ai-influence-youtube-report/A3-data-model.md` — exclusive single-file write. ✓
- Read scope respected: only the files listed in the dispatch's Read Scope (PRD, contract, sprint design, A1, N1, N2, N3) were consulted plus STATE.md for the pre-write Read hook. ✓
- Package boundary: `spec_only`. No code written; no `.py`/`.ts`/`.sh` files created or modified; no live calls; no fixture generation; no downstream artifact written. ✓
- Architecture guard: no `core_hits`; package_boundary respected; guard warnings/errors `none`. ✓
- NG1 / NG2 / NG3 / NG4 / NG5 enforced in spec language (X-6/X-7/X-8/X-10). ✓
- Parent epic NOT closed; only this node is marked `reviewing` by the handoff step. ✓
- No `done` / `complete` / `implemented` language about un-built downstream work. ✓

---

## 17. Self-check (pre-handoff)

| Self-check | Result |
|------------|--------|
| 12 named schemas covered (gate_decision, t3_exclusions, classification_decision, phase1_plan, phase2_chapter, phase3_synthesis, evidence_map, source_mapping, validator_report, model_call_ledger, archive_manifest, run_record) | ✓ |
| Each schema has Required field summary, sub-objects (where present), JSON Schema (Draft 2020-12), and Invariants | ✓ |
| `phase1_plan.v1` shows the trend→chapter→subsection→evidence_refs hierarchy with `model_call_id` linkage | ✓ (§4.2 + §4.4) |
| `evidence_map.v1.entries[]` carries exactly the 5 reader-facing fields plus `group_type` | ✓ (§7.2 + §7.3) |
| `validator_report.v1.checks[]` is exactly 8 entries with PASS/FAIL status, evidence, and conditionally diff | ✓ (§9.3 + §9.4) |
| `model_call_ledger.v1` includes call_id, stage (3-value enum), cost, sprint_id, browser_session_id, chatgpt_url, latency_ms | ✓ (§10.2) |
| `archive_manifest.v1` enforces the 4 mandatory artifact types via `contains` constraints | ✓ (§11.3) |
| `run_record.v1.state` enum is pinned to A1's 8 success + 7 rejection terminals | ✓ (§12.2 + §12.5) |
| Cross-schema invariants (X-1..X-12) lock the relationships between artifacts | ✓ (§13) |
| All forward references to A2 / A4 / A5 are explicit and bounded | ✓ |
| No code / no fixture / no live call / no parent-epic close | ✓ |
| No `done` / `complete` / `implemented` language for downstream work | ✓ |
