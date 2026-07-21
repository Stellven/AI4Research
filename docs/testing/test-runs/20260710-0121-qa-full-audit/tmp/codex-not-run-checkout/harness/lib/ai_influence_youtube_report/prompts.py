"""Prompt skeletons for Browser Agent ChatGPT 5.5 Thinking high calls."""

PHASE1_PLAN_PROMPT = "Return JSON only: trends -> chapters -> subsections -> evidence_refs."
PHASE2_CHAPTER_PROMPT = "Write exactly one chapter from the provided chapter spec and evidence refs."
PHASE3_SYNTHESIS_PROMPT = "Synthesize chapter outputs into final executive summary and cross-chapter links."
