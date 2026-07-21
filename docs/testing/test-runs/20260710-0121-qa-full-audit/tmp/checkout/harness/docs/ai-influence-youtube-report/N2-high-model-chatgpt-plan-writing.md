# N2: Browser Agent ChatGPT 5.5 Planning / Writing / Synthesis Contract

sprint: `sprint-20260528-p0-ai-influence-youtube-报告流默认流程固化与验收-s01-requirements`
node: `N2`
generated_at: `2026-05-29`
status: `reviewing`
package_boundary: `spec_only` - no implementation code, no API key, no model invocation

---

## 1. Core Decision

AI Influence YouTube report generation MUST use Browser Agent to operate ChatGPT 5.5 Thinking high for the three judgment-bearing phases:

1. Phase 1: report planning
2. Phase 2: per-chapter analysis and writing
3. Phase 3: final synthesis and editorial pass

ThunderOMLX / Qwen / other local models MAY be used for preprocessing, transcript cleanup, evidence atom extraction, entity normalization, and low-risk validation. They MUST NOT replace ChatGPT 5.5 Thinking high for trend judgment, report planning, chapter argumentation, or final editorial synthesis.

Hard rule:

```text
If a report contains trend judgment, chapter-level argument, source grouping, or final conclusion,
the responsible call MUST be Browser Agent -> ChatGPT 5.5 Thinking high.
```

---

## 2. Phase Interface Contract

### 2.1 Phase 1: Planning

Input:

```json
{
  "run_id": "aiyt_2026_W21_plan_001",
  "week": "2026-W21",
  "videos": [
    {
      "video_ref": "V001",
      "source_mapping": {
        "channel": "string",
        "title": "string",
        "published_at": "ISO-8601",
        "trust_level": "T0|T1|T2",
        "cited_segment_snippet": "1-2 sentence human-readable source note"
      },
      "group_type": "event|conference|keynote|interview|tutorial|product_update|other",
      "group_confidence": 0.0,
      "transcript_quality": "T0|T1|T2",
      "summary_packet": "compressed evidence packet, not raw internal pipeline fields",
      "evidence_atoms": []
    }
  ],
  "T3_exclusions": [],
  "planning_goal": "group videos into coherent reports and produce trend->chapter->subsection plan"
}
```

Output:

```json
{
  "schema_version": "ai_influence.youtube.plan.v1",
  "run_id": "aiyt_2026_W21_plan_001",
  "reports": [
    {
      "report_id": "string",
      "title": "reader-facing title",
      "reader_value": "why this report matters",
      "source_group_ids": ["string"],
      "trends": [
        {
          "trend_id": "T1",
          "trend_judgment": "clear thesis, not a keyword label",
          "chapters": [
            {
              "chapter_id": "C1",
              "title": "reader-facing chapter title",
              "purpose": "what this chapter proves",
              "subsections": [
                {
                  "subsection_id": "S1",
                  "claim": "specific claim",
                  "evidence_refs": [
                    {
                      "video_ref": "V001",
                      "source_mapping_ref": "source_mapping object or stable handle",
                      "trust_level": "T0|T1|T2",
                      "segment_hint": "timestamp or section label when available"
                    }
                  ]
                }
              ]
            }
          ]
        }
      ],
      "excluded_material": [
        {
          "reason": "T3 transcript or weak relevance",
          "source_mapping": {}
        }
      ]
    }
  ],
  "planning_notes": {
    "grouping_logic": "event/interview/product_update/source-quality based explanation",
    "risks": [],
    "follow_up_questions": []
  }
}
```

Phase 1 MUST:

- Group videos by source type and semantic event, not only keyword or time adjacency.
- Distinguish conference/keynote/event clusters from interview/tutorial/product_update clusters.
- Emit a hierarchy: `trend -> chapter -> subsection -> evidence_refs`.
- Exclude T3 transcripts from all report evidence.
- Keep internal IDs out of reader-facing fields.

### 2.2 Phase 2: Per-Chapter Writing

One Browser Agent ChatGPT session call per chapter is required. Do not batch multiple chapters into one writing call.

Input:

```json
{
  "phase": "chapter_writing",
  "report_id": "string",
  "chapter": {
    "chapter_id": "C1",
    "title": "string",
    "purpose": "string",
    "subsections": []
  },
  "allowed_evidence": [
    {
      "source_mapping": {
        "channel": "string",
        "title": "string",
        "published_at": "ISO-8601",
        "trust_level": "T0|T1|T2",
        "cited_segment_snippet": "string"
      },
      "clean_transcript_excerpt": "original-language or faithful cleaned transcript excerpt",
      "evidence_atom": "compressed evidence atom",
      "quality_note": "required when trust_level=T2"
    }
  ],
  "style_contract": {
    "audience": "AI product / engineering / strategy readers",
    "no_internal_terms": true,
    "no_video_ids": true,
    "must_show_source_mapping": true,
    "must_preserve_original_meaning": true
  }
}
```

Output:

```json
{
  "schema_version": "ai_influence.youtube.chapter.v1",
  "report_id": "string",
  "chapter_id": "C1",
  "chapter_markdown": "reader-facing markdown",
  "source_mapping_used": [],
  "claims": [
    {
      "claim": "string",
      "supporting_sources": [],
      "trust_level": "T0|T1|T2"
    }
  ],
  "visual_requests": [
    {
      "type": "svg",
      "purpose": "architecture / flow / comparison",
      "data_requirements": []
    }
  ],
  "warnings": []
}
```

Phase 2 MUST:

- Use exactly one chapter scope per call.
- Preserve source meaning; no LLM invented content.
- Show which human-readable source supports each important claim.
- Label T2 evidence as weak or partial.
- Avoid internal fields: `video_id`, `V00x`, raw pipeline refs, transcript job status, database paths, worker IDs.

### 2.3 Phase 3: Final Synthesis

Input:

```json
{
  "phase": "final_synthesis",
  "report_id": "string",
  "plan": {},
  "chapter_outputs": [],
  "validator_findings": [],
  "required_outputs": [
    "final_markdown",
    "final_html",
    "inline_svg_blocks",
    "source_map_appendix",
    "archive_metadata"
  ]
}
```

Output:

```json
{
  "schema_version": "ai_influence.youtube.final_report.v1",
  "report_id": "string",
  "final_markdown": "string",
  "final_html": "string",
  "source_map_appendix": [],
  "inline_svgs": [],
  "editorial_notes": {
    "central_judgment": "reader-facing thesis",
    "material_limits": [],
    "excluded_sources": []
  },
  "archive_metadata": {
    "browser_session_id": "string",
    "chatgpt_project": "杂项",
    "chatgpt_conversation_url": "string",
    "model": "ChatGPT 5.5 Thinking high"
  }
}
```

Phase 3 MUST:

- Reconcile chapters into one coherent report.
- Remove internal processing language.
- Replace ASCII diagrams with inline SVG.
- Preserve visible source mapping per major section.
- Produce archive metadata so Browser Agent can move the ChatGPT conversation into project `杂项`.

---

## 3. Browser Agent Session Contract

The Browser Agent wrapper MUST provide these stable fields to the pipeline:

```json
{
  "browser_session_id": "string",
  "chatgpt_model": "ChatGPT 5.5 Thinking high",
  "chatgpt_project": "杂项",
  "conversation_url": "https://chatgpt.com/...",
  "prompt_hash": "sha256",
  "input_artifact_path": "path",
  "output_artifact_path": "path",
  "created_at": "ISO-8601",
  "archived_at": "ISO-8601|null",
  "archive_status": "pending|archived|failed"
}
```

Rules:

- The wrapper reads prompt input from stdin or a prompt file.
- The wrapper selects ChatGPT 5.5 Thinking high before submitting.
- The wrapper must save raw model output and parsed JSON/Markdown output separately.
- After useful output is extracted, the wrapper must archive the ChatGPT conversation into project `杂项`.
- If archival fails, report generation can continue, but `archive_status=failed` must be visible in `model_call_ledger`.

---

## 4. model_call_ledger Schema

Every Phase 1/2/3 Browser Agent call MUST append a row/event to `model_call_ledger`.

Required fields:

```json
{
  "call_id": "string",
  "module": "ai_influence_youtube",
  "stage": "phase1_plan|phase2_chapter_write|phase3_synthesis",
  "model": "chatgpt-5.5-thinking-high",
  "provider": "browser_agent_chatgpt",
  "sprint_id": "sprint-20260528-p0-ai-influence-youtube-报告流默认流程固化与验收",
  "report_id": "string",
  "chapter_id": "string|null",
  "browser_session_id": "string",
  "chatgpt_project": "杂项",
  "conversation_url": "string|null",
  "input_tokens_estimate": 0,
  "output_tokens_estimate": 0,
  "estimated_cost_usd": 0.0,
  "call_count": 1,
  "prompt_version": "aiyt-plan-v1|aiyt-chapter-v1|aiyt-synthesis-v1",
  "schema_version": "ai_influence.youtube.*.v1",
  "archive_status": "pending|archived|failed",
  "created_at": "ISO-8601"
}
```

The daily/weekly report manifest MUST include aggregate call accounting:

```json
{
  "model_call_summary": {
    "phase1_plan_calls": 1,
    "phase2_chapter_calls": 0,
    "phase3_synthesis_calls": 1,
    "total_calls": 2,
    "estimated_cost_usd": 0.0,
    "browser_session_ids": []
  }
}
```

---

## 5. Prompt Routing Rules

| Pipeline Step | Allowed Model | Disallowed Replacement |
|---------------|---------------|------------------------|
| Transcript cleanup | ThunderOMLX/Qwen allowed | N/A |
| Evidence atom extraction | ThunderOMLX/Qwen allowed | N/A |
| Video grouping hints | local model allowed as hint only | Cannot decide final groups |
| Phase 1 report plan | Browser Agent ChatGPT 5.5 Thinking high | ThunderOMLX/Qwen |
| Phase 2 chapter writing | Browser Agent ChatGPT 5.5 Thinking high | ThunderOMLX/Qwen |
| Phase 3 synthesis | Browser Agent ChatGPT 5.5 Thinking high | ThunderOMLX/Qwen |
| Validator checks | deterministic code + optional local model hints | high model cannot override gate |

If Browser Agent is unavailable:

```text
status = blocked_high_model_unavailable
report_generation = paused
fallback_to_local_model = forbidden for final report
```

---

## 6. Required Prompt Skeletons

### 6.1 Phase 1 Planning Prompt

```text
You are an AI Influence editor and technical strategist.
Use only the provided source packets.
Group videos by event/conference/keynote/interview/tutorial/product_update/other, transcript quality, and semantic relation.
Do not group solely by keyword or date.
Return JSON matching ai_influence.youtube.plan.v1.
Do not expose internal video_id, V00x, raw_refs, pipeline status, database path, worker name, or processing logs.
```

### 6.2 Phase 2 Chapter Prompt

```text
Write exactly one chapter.
Use only the allowed evidence for this chapter.
Every important claim must map to a human-readable source mapping entry.
If evidence is T2, label it as partial transcript evidence.
Do not mention internal processing details.
Return JSON matching ai_influence.youtube.chapter.v1.
```

### 6.3 Phase 3 Synthesis Prompt

```text
Synthesize the final report from the approved plan and chapter outputs.
Remove internal implementation language.
Ensure source mapping is visible and reader-friendly.
Convert all architecture or platform diagrams to inline SVG blocks.
Return JSON matching ai_influence.youtube.final_report.v1.
```

---

## 7. Acceptance Traceability

| Acceptance Item | Section |
|-----------------|---------|
| Phase 1/2/3 interface contract documented | §2 |
| ThunderOMLX/Qwen replacement explicitly forbidden for Phase 1/2/3 final judgment | §1, §5 |
| Per-chapter call pattern specified | §2.2 |
| model_call_ledger 3 phase schema | §4 |
| Browser Agent session ID saved to archive metadata | §3, §4 |
| Structured JSON plan schema trend->chapter->subsection->evidence_refs | §2.1 |
| evidence_refs point to video/source mapping | §2.1, §2.2 |

---

## 8. Non-goals

- This node does not implement the Browser Agent wrapper.
- This node does not call ChatGPT.
- This node does not generate a W21 report.
- This node does not validate transcript quality thresholds; N1 owns that contract.
- This node does not implement final output validator; N3 owns that contract.

