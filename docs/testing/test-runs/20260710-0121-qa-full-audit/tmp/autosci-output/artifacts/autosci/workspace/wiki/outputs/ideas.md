---
entity_type: "output"
entity_id: "ideas-shim-side-effect-access-run_experiment"
title: "Idea summary for shim-side-effect-access-run_experiment"
run_id: "shim-side-effect-access-run_experiment"
source_evidence: "artifacts/autosci/runs/shim-side-effect-access-run_experiment/idea_candidate.json"
managed_by: "solar-autosci-workspace-projector"
---
# Idea Summary: `shim-side-effect-access-run_experiment`

## Status

- Candidate evidence status: `inconclusive`
- Evaluation evidence status: `completed`
- Candidate count: `3`
- Evaluation count: `3`
- Candidate evidence: `artifacts/autosci/runs/shim-side-effect-access-run_experiment/idea_candidate.json`
- Evaluation evidence: `artifacts/autosci/runs/shim-side-effect-access-run_experiment/idea_evaluation.json`

## Ideas

| Idea | Title | Status | Duplicate | Source Mode | Recommendation | Final Ready |
| --- | --- | --- | --- | --- | --- | --- |
| idea-wiki-discovery-001 | Close the evidence gap around exp-001 | filtered | duplicate | mixed | reject | False |
| idea-method-incremental-001 | Patch a limitation in Method protocol | filtered | duplicate | mixed | reject | False |
| idea-wiki-discovery-002 | Stress-test method transfer from AutoSci Adapter Fixture Paper | filtered | duplicate | mixed | reject | False |

## Selected Details

| Idea | Hypothesis | Approach | Origin Evidence |
| --- | --- | --- | --- |
| idea-wiki-discovery-001 | Combining `AutoSci Adapter Fixture Paper` with `Runtime Verified Local Wiki Source` can expose a testable gap that is not captured by single-source reading. | Build an experiment plan from the shared assumptions and limitations in the cited wiki/discovery sources, then compare it against the strongest baseline found in the evidence graph. | discovery:AutoSci Adapter Fixture Paper, discovery:Runtime Verified Local Wiki Source |
| idea-method-incremental-001 | A focused improvement to `Method protocol` can address a method limitation visible in the wiki evidence. | Extract the method's stated limitation or unresolved evaluation gap, implement the smallest measurable change, and compare against the original method under the same evidence-backed task. | wiki:methods/method-001 |
| idea-wiki-discovery-002 | A mechanism or limitation in `AutoSci Adapter Fixture Paper` can be transferred to the context of `Runtime Verified Skill Generation Source` and evaluated with a bounded pilot. | Extract the reusable mechanism from the first source, map assumptions against the third source, and run a pilot that checks whether the transferred mechanism is compatible. | discovery:AutoSci Adapter Fixture Paper, discovery:Runtime Verified Skill Generation Source |

## Novelty And Review Boundary

| Idea | Boundary Status | External Novelty | Review LLM | Blocking Reasons |
| --- | --- | --- | --- | --- |
| idea-wiki-discovery-001 | novelty_acceptance_incomplete | missing | missing | external_novelty status is `missing`, not `completed`; external_novelty provenance status is `missing`, not `passed`; review_llm status is `missing`, not `completed` |
| idea-method-incremental-001 | novelty_acceptance_incomplete | missing | missing | external_novelty status is `missing`, not `completed`; external_novelty provenance status is `missing`, not `passed`; review_llm status is `missing`, not `completed` |
| idea-wiki-discovery-002 | novelty_acceptance_incomplete | missing | missing | external_novelty status is `missing`, not `completed`; external_novelty provenance status is `missing`, not `passed`; review_llm status is `missing`, not `completed` |

## Limitations

- Ideas are source-grounded deterministic candidates; external novelty and Review LLM validation remain required.
- Failed idea overlap is checked with token overlap and should be reviewed by a human.
- Resolver is read-only; it does not mutate wiki state, add graph edges, or rebuild wiki indexes.
- Frontmatter parsing supports scalar values and simple lists only; complex YAML is reported through missing fields.
- Final idea promotion requires wiki maturity scan, failed-idea banlist check, source-backed evidence, model brainstorm provenance, and novelty/review gate evidence references.
- Native /ideate full parity requires completed landscape scan, independent dual-model brainstorm, novelty/review validation, approved wiki writeback, pilot handoff or explicit skip, and A/B/C/D/E generation-path coverage.
- Side-effect access is required; no protected native side effects were executed.
- Novelty/review signals are derived from local wiki/discovery evidence.
- Independent Review LLM and live external search are still required before promotion.
- Novelty final acceptance boundary is incomplete for at least one evaluated idea.
- Resolver is read-only; it does not mutate wiki state, add graph edges, or rebuild wiki indexes.
- Frontmatter parsing supports scalar values and simple lists only; complex YAML is reported through missing fields.
