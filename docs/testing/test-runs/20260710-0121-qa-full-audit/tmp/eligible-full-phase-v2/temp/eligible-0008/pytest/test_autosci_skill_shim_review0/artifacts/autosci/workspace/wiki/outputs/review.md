---
entity_type: "output"
entity_id: "review-shim-review-missing-slug"
title: "Review diagnostics for shim-review-missing-slug"
run_id: "shim-review-missing-slug"
source_evidence: "artifacts/autosci/runs/shim-review-missing-slug/artifact_review.json"
managed_by: "solar-autosci-workspace-projector"
---
# Review Diagnostics: `shim-review-missing-slug`

## Status

- Evidence status: `inconclusive`
- Target: `N/A`
- Focus: `method`
- Difficulty: `hard`
- Review mode: `local_surrogate`
- Review available: `False`
- Score: `0.0`
- Recommendation: `inconclusive`
- Final acceptance ready: `False`
- Final boundary status: `review_llm_incomplete`

## Review LLM Evidence

- Review LLM status: `unavailable`
- Invocation mode: `unavailable`
- Provider: `N/A`
- Model: `N/A`
- Request sha256: `N/A`
- Response sha256: `N/A`

## Evidence

- Review evidence: `artifacts/autosci/runs/shim-review-missing-slug/artifact_review.json`

| Evidence ID |
| --- |
| review-target:idea-001 |

## Findings

- N/A

## Blocking Reasons

| Reason |
| --- |
| review_mode is `local_surrogate`, not `review_llm` |
| review_available is not true |
| review_llm status is `unavailable`, not `completed` |

## Limitations

- No local artifact or wiki entity was resolved for review.
- Review LLM evidence is required before this review can be treated as final acceptance.
- Final review acceptance requires Review LLM evidence from supplied evidence, command bridge, or provider mode.
