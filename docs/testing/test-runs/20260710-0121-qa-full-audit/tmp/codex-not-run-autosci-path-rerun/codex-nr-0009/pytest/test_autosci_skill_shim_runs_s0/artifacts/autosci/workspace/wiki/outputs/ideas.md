---
entity_type: "output"
entity_id: "ideas-shim-single-token-dollar-command"
title: "Idea summary for shim-single-token-dollar-command"
run_id: "shim-single-token-dollar-command"
source_evidence: "artifacts/autosci/runs/shim-single-token-dollar-command/idea_candidate.json"
managed_by: "solar-autosci-workspace-projector"
---
# Idea Summary: `shim-single-token-dollar-command`

## Status

- Candidate evidence status: `completed`
- Evaluation evidence status: `completed`
- Candidate count: `2`
- Evaluation count: `2`
- Candidate evidence: `artifacts/autosci/runs/shim-single-token-dollar-command/idea_candidate.json`
- Evaluation evidence: `artifacts/autosci/runs/shim-single-token-dollar-command/idea_evaluation.json`

## Ideas

| Idea | Title | Status | Duplicate | Source Mode | Recommendation | Final Ready |
| --- | --- | --- | --- | --- | --- | --- |
| idea-001 | Evidence-linked verification coverage experiment | candidate | new | fixture | advance | False |
| idea-duplicate-001 | Repeat existing fixture bridge smoke | filtered | duplicate | fixture | reject | False |

## Selected Details

| Idea | Hypothesis | Approach | Origin Evidence |
| --- | --- | --- | --- |
| idea-001 | Pairing source-grounded claims with method and code evidence will expose verification gaps before claim verdict generation. | Use claim `claim-003` and method `method-001` to compare source-only evidence against source-plus-code evidence coverage. | claim-003, method-001, task-autosci-skillgen-ingest_paper, task-autosci-skillgen-extract_claims, claim-001, claim-002, claim-003, task-autosci-skillgen-extract_methods, method-001, paper-skillgen-operator-smoke-paper |
| idea-duplicate-001 | Repeating the bridge smoke test alone will improve scientific verification. | Run the existing Method protocol without adding new evidence dimensions. | claim-003, method-001, task-autosci-skillgen-ingest_paper, task-autosci-skillgen-extract_claims, claim-001, claim-002, claim-003, task-autosci-skillgen-extract_methods, method-001, paper-skillgen-operator-smoke-paper |

## Novelty And Review Boundary

| Idea | Boundary Status | External Novelty | Review LLM | Blocking Reasons |
| --- | --- | --- | --- | --- |
| idea-001 | novelty_acceptance_incomplete | N/A | N/A | external_novelty status is `N/A`, not `completed`; external_novelty provenance status is `missing`, not `passed`; review_llm status is `N/A`, not `completed` |
| idea-duplicate-001 | novelty_acceptance_incomplete | missing | missing | external_novelty status is `missing`, not `completed`; external_novelty provenance status is `missing`, not `passed`; review_llm status is `missing`, not `completed` |

## Limitations

- Fixture ideas are generated from supplied local evidence only; external novelty is not proven.
- Final idea promotion requires wiki maturity scan, failed-idea banlist check, source-backed evidence, model brainstorm provenance, and novelty/review gate evidence references.
- Native /ideate full parity requires completed landscape scan, independent dual-model brainstorm, novelty/review validation, approved wiki writeback, pilot handoff or explicit skip, and A/B/C/D/E generation-path coverage.
- Fixture evaluation uses local evidence and does not update idea status directly.
- Novelty final acceptance boundary is incomplete for at least one evaluated idea.
