# N1: Transcript Quality Gate + Video Group Classification Spec

sprint: `sprint-20260528-p0-ai-influence-youtube-报告流默认流程固化与验收-s01-requirements`
node: `N1`
generated_at: `2026-05-29`
status: `reviewing`
package_boundary: `spec_only` — no code, no CLI invocation

---

## Part 1: Transcript Quality Gate (O1)

### 1.1 4-Level Grading Table

Reused verbatim from YouTube Transcript epic (`epic-20260526-tech-hotspot-radar-youtube-transcript`). Do NOT redefine these thresholds independently.

| Level | entity_recall | WER | segment_density | Usage in AI Influence Report |
|-------|--------------|-----|-----------------|------------------------------|
| **T0** | ≥ 95% | ≤ 5% | ≥ 0.8 segs/min | Core evidence (unrestricted) |
| **T1** | ≥ 80% | ≤ 15% | ≥ 0.6 segs/min | Core evidence (unrestricted) |
| **T2** | ≥ 60% | ≤ 30% | ≥ 0.4 segs/min | Weak evidence — must label `"based on partial transcript"` |
| **T3** | < 60% | > 30% | < 0.4 segs/min | **Reject** — auto-excluded from plan; NOT referenced in report |

**Metric definitions:**
- `entity_recall`: fraction of expected named entities (speaker names, org names, product names from metadata) that appear verbatim in the transcript.
- `WER`: Word Error Rate (substitutions + deletions + insertions) / reference_word_count, where reference is the original video audio reference if available, else estimated from ASR confidence scores.
- `segment_density`: number of transcript segments per minute of video duration.

### 1.2 Per-Level Behavior Contract

| Level | Behavior | plan-ai-influence-reports action |
|-------|----------|----------------------------------|
| T0 | Admitted as core evidence | Included in plan without restriction |
| T1 | Admitted as core evidence | Included in plan without restriction |
| T2 | Admitted as weak evidence only | Included only with mandatory label `trust_level: "T2"` and `"based on partial transcript"` prefix on all citations |
| T3 | **Rejected** | Excluded automatically; `T3_exclusions[]` list written to plan manifest; downstream validator checks T3 not in core evidence |

**Hard constraint:** A video with T3 transcript MUST NOT appear as an evidence_ref in any report chapter body. The only allowed appearance is in the `T3_exclusions` section of the plan manifest.

### 1.3 plan-ai-influence-reports Entry Point — Gate Invocation Order

```
plan-ai-influence-reports [--week <YYYY-Www>] [--date-range <start> <end>]
```

**Mandatory gate invocation sequence (MUST follow this order, no bypass allowed):**

```
Step 1: fetch video list for period
  → output: raw_video_list[]

Step 2: invoke transcript_gate for each video
  → input: video_id + transcript_artifact_path + quality_metrics
  → output: gate_result{ level: T0|T1|T2|T3, entity_recall, WER, segment_density }

Step 3: partition by gate result
  → T0_list[], T1_list[], T2_list[], T3_list[]

Step 4: build plan from T0 + T1 (core) + T2 (weak, labeled)
  → T3_list is written to plan_manifest.T3_exclusions[] ONLY

Step 5: write plan manifest
  → plan_manifest.json includes: T0_list, T1_list, T2_list (with trust_level), T3_exclusions (IDs only, no transcript content)
```

**Gate bypass is explicitly forbidden** per `evidence_policy.no_transcript_gate_bypass = true`.

### 1.4 T3 Exclusion Evidence — Validator Hook for Downstream

The plan manifest MUST include a `T3_exclusions` block with sufficient evidence for downstream validator (N3) to verify:

```json
{
  "T3_exclusions": [
    {
      "video_handle": {
        "channel": "<channel name>",
        "title": "<video title>",
        "published_at": "<ISO 8601 date>"
      },
      "gate_result": {
        "level": "T3",
        "entity_recall": 0.45,
        "WER": 0.42,
        "segment_density": 0.3,
        "exclusion_reason": "entity_recall < 0.60 AND WER > 0.30"
      },
      "excluded_at": "<ISO 8601 timestamp>"
    }
  ]
}
```

**Downstream validator hook (N3 will implement):**
- Rule: if `evidence_refs[].video_handle` matches any `T3_exclusions[].video_handle` in the plan manifest → validator FAIL with reason `"T3_video_in_core_evidence"`.
- Rule: plan_manifest.T3_exclusions MUST be non-null (even if empty array `[]`).

---

## Part 2: Video Group Classification Spec (O2)

### 2.1 7 group_type Definitions

| group_type | Definition | Canonical Examples |
|-----------|------------|-------------------|
| `event` | Multi-session community or industry event (not single keynote) | AI Summit, NeurIPS workshops, ML conference day |
| `conference` | Academic or professional conference formal session (single paper/talk session) | ICML paper presentation, ICLR poster session |
| `keynote` | Single featured address by a prominent speaker at an event or conference | Sam Altman keynote at OpenAI DevDay, Jensen Huang GTC keynote |
| `interview` | Conversational format with host(s) and guest(s), Q&A dominant | Lex Fridman interview, Dwarkesh Patel podcast |
| `tutorial` | Step-by-step instructional, hands-on demo or walkthrough | "Build an AI agent in 30 mins", fine-tuning tutorial |
| `product_update` | Announcement or demo of a specific product/model/API update | GPT-5 launch demo, Claude API update, Gemini release |
| `other` | Fallback — none of the above with sufficient confidence | Compilations, AMAs, roundtables, mixed formats |

**Note:** `other` is NOT a weak catch-all — it is the explicit fallback when multi-signal confidence for all 6 named types falls below threshold. Total effective types = 7.

### 2.2 Multi-Signal Classification — 6 Required Signals

Single-signal classification (e.g., keyword match alone, or time-window alone) is explicitly **FORBIDDEN** per PRD impl §2.

All 6 signals MUST be evaluated and combined:

| Signal ID | Signal Name | Extraction Method | Weight Range |
|-----------|-------------|-------------------|-------------|
| S1 | `title_pattern` | Regex + keyword matching on video title (e.g., "keynote", "tutorial", "interview", "launch", "summit", "workshop") | 0–0.35 |
| S2 | `channel_type` | Channel category inference from channel metadata (edu / news / official / creator / org) | 0–0.25 |
| S3 | `duration` | Video duration bucket: <5min / 5-15min / 15-45min / 45-90min / >90min | 0–0.15 |
| S4 | `speaker_count` | Number of distinct speakers detected in transcript (1 / 2 / 3+) | 0–0.15 |
| S5 | `qa_presence` | Whether Q&A segment detected in transcript (pattern: "question", "audience", timestamped switch) | 0–0.15 |
| S6 | `slide_density` | Estimated slide transitions per minute (from chapter markers, transcript topic shifts, or video chapter data) | 0–0.10 |

**Total weight sum = 1.0.** Weights above are max per signal; actual contribution varies by group_type (see §2.3).

### 2.3 Per-group_type Signal Profiles and Confidence Thresholds

| group_type | Key signals | Min confidence to assign | Fallback if below threshold |
|-----------|-------------|--------------------------|----------------------------|
| `event` | S1(event/summit/day/track) + S5(qa_presence=high) + S3(>90min) | 0.65 | `other` |
| `conference` | S1(conference/session/paper) + S2(edu/org) + S4(speaker_count=1-2) + S6(slide_density≥1/min) | 0.65 | `other` |
| `keynote` | S1(keynote/address) + S4(speaker_count=1) + S3(15-90min) + S2(official) | 0.70 | `conference` or `other` |
| `interview` | S1(interview/podcast/ep) + S4(speaker_count=2+) + S5(qa_presence=high) + S3(30-120min) | 0.65 | `other` |
| `tutorial` | S1(tutorial/how-to/build/step) + S2(edu/creator) + S6(slide_density≥0.5/min) + S3(<60min) | 0.65 | `other` |
| `product_update` | S1(launch/release/announce/update/introducing) + S2(official) + S4(speaker_count=1-2) + S3(<45min) | 0.70 | `keynote` or `other` |
| `other` | Assigned automatically when max group_type confidence < 0.50 | N/A (forced fallback) | — |

**Fallback cascade rule:**
1. Compute confidence for all 6 named group_types.
2. Take argmax. If max confidence ≥ threshold for that type → assign.
3. If max confidence < threshold but ≥ 0.50 → use the fallback type listed in table.
4. If max confidence < 0.50 → assign `other`.

### 2.4 signal_breakdown JSON Schema

Every classification result MUST output the following schema for downstream debugging and validator audit:

```json
{
  "$schema": "solar.signal_breakdown.v1",
  "video_handle": {
    "channel": "<string>",
    "title": "<string>",
    "published_at": "<ISO 8601 date>"
  },
  "group_type": "<one of: event|conference|keynote|interview|tutorial|product_update|other>",
  "confidence": 0.78,
  "confidence_breakdown": {
    "event": 0.12,
    "conference": 0.78,
    "keynote": 0.55,
    "interview": 0.20,
    "tutorial": 0.10,
    "product_update": 0.15,
    "other": 0.00
  },
  "signal_breakdown": {
    "S1_title_pattern": {
      "matched_keywords": ["keynote", "session"],
      "raw_score": 0.30,
      "weight": 0.35,
      "weighted_score": 0.26
    },
    "S2_channel_type": {
      "inferred_type": "edu",
      "raw_score": 0.80,
      "weight": 0.25,
      "weighted_score": 0.20
    },
    "S3_duration": {
      "duration_seconds": 2700,
      "duration_bucket": "45-90min",
      "raw_score": 0.70,
      "weight": 0.15,
      "weighted_score": 0.11
    },
    "S4_speaker_count": {
      "detected_speakers": 2,
      "raw_score": 0.60,
      "weight": 0.15,
      "weighted_score": 0.09
    },
    "S5_qa_presence": {
      "qa_detected": false,
      "confidence": 0.20,
      "raw_score": 0.20,
      "weight": 0.15,
      "weighted_score": 0.03
    },
    "S6_slide_density": {
      "transitions_per_min": 1.3,
      "raw_score": 0.90,
      "weight": 0.10,
      "weighted_score": 0.09
    }
  },
  "threshold_applied": 0.65,
  "fallback_used": false,
  "classified_at": "<ISO 8601 timestamp>"
}
```

**Schema invariants:**
- `confidence_breakdown` keys MUST include all 7 group_types (including `other`).
- `signal_breakdown` MUST include all 6 signals (S1–S6); no signal may be omitted.
- `sum(weighted_score for S1..S6)` ≈ `confidence_breakdown[group_type]` (within floating point tolerance).
- `group_type` in output MUST match argmax of `confidence_breakdown` subject to threshold/fallback rules.
- `video_handle` MUST NOT contain `video_id`, `V00x`, or any internal pipeline field.

---

## Part 3: Integration Contract

### 3.1 plan-ai-influence-reports — Combined Gate + Classification Sequence

```
plan-ai-influence-reports --week 2026-W21
  │
  ├─ Step 1: fetch_video_list(week="2026-W21")
  │    → raw_video_list[N]
  │
  ├─ Step 2: for each video in raw_video_list:
  │    ├─ transcript_gate(video) → { level: T0|T1|T2|T3, metrics }
  │    └─ classify_video_group(video) → { group_type, confidence, signal_breakdown }
  │
  ├─ Step 3: partition
  │    ├─ T3 → T3_exclusions (only; no group_type required)
  │    └─ T0/T1/T2 → core_pool[] with group_type + trust_level
  │
  ├─ Step 4: organize core_pool by group_type
  │    → grouped_plan{ event: [], conference: [], keynote: [], interview: [],
  │                    tutorial: [], product_update: [], other: [] }
  │
  └─ Step 5: write plan_manifest.json
       → { grouped_plan, T3_exclusions, generated_at, week }
```

### 3.2 Downstream Validator Hooks (for N3 implementation)

N3 MUST implement the following checks against N1 outputs:

| Hook ID | Check | Source field |
|---------|-------|-------------|
| V-N1-1 | T3 not in core evidence | plan_manifest.T3_exclusions ↔ report evidence_refs |
| V-N1-2 | signal_breakdown present for all non-T3 videos | plan_manifest.grouped_plan[].signal_breakdown |
| V-N1-3 | group_type is one of 7 legal values | plan_manifest.grouped_plan[].group_type |
| V-N1-4 | T2 videos carry trust_level="T2" and "based on partial transcript" in citation | plan_manifest.T2_list[].trust_level |
| V-N1-5 | video_handle has no forbidden fields (video_id, V00x, raw_refs) | plan_manifest all video_handle objects |

---

## Acceptance Checklist

- [x] **A-N1-1**: T0-T3 4-level transcript quality classification table with entity_recall and WER thresholds — §1.1
- [x] **A-N1-2**: Per-level behavior: T0/T1 core / T2 weak (labeled) / T3 reject (auto-excluded) — §1.2
- [x] **A-N1-3**: plan-ai-influence-reports entry point with gate invocation order — §1.3
- [x] **A-N1-4**: T3 exclusion evidence captured (validator hook for downstream) — §1.4 + §3.2
- [x] **A-N1-5**: 7 group_type list with definitions (event/conference/keynote/interview/tutorial/product_update/other) — §2.1
- [x] **A-N1-6**: Multi-signal combination spec (≥6 signals: title pattern + channel type + duration + speaker count + Q&A presence + slide density) — §2.2
- [x] **A-N1-7**: Confidence threshold per group_type with fallback to 'other' — §2.3
- [x] **A-N1-8**: signal_breakdown JSON schema for downstream debug — §2.4

---

## Scope Compliance

- Write scope: `docs/ai-influence-youtube-report/N1-transcript-gate-classification.md` ✓
- No code written — spec_only package boundary respected ✓
- T0-T3 grading reused from YouTube Transcript epic — NOT redefined ✓
- No internal fields (video_id, V00x, raw_refs, pipeline_fields) in any schema ✓
- No transcript gate bypass ✓
- Single-signal classification explicitly forbidden ✓
- Parent epic NOT closed ✓

## Known Risks

- **R1**: `entity_recall` and `WER` computation methods are inherited from S03 handoff but exact metric implementation lives in YouTube Transcript epic S03 runtime. N1 spec assumes those metrics are available as structured output from `transcript-status --json`. If metric format changes, this gate spec requires update.
- **R2**: `slide_density` (S6) is the weakest signal — depends on chapter markers or topic shift heuristics in transcript, which may not be available for all videos. Implementer MUST handle S6 = null gracefully (treat as 0.0 raw_score, not error).
- **R3**: Confidence threshold values in §2.3 are design-time estimates. They should be validated against a fixture set (2026-W21 batch) during N3 smoke test and adjusted if classification accuracy is below acceptable level.

## Not Done

- No CLI implementation (spec_only node — builder eligible: false)
- No fixture data generated (that is N3's responsibility)
- No actual transcript quality metrics run (no real pipeline invocation per evidence_policy)
- N4 traceability join not yet done (depends on N1+N2+N3)
