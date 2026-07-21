---
name: ask
description: "Solar AutoSci wrapper for $ask. Use when the user invokes $ask, asks for AutoSci ask, or requests the corresponding Solar research workflow. This OpenSolar wrapper preserves the native AutoSci skill UX while routing execution through Solar Harness (cap.research-memory-update, backend action ask_wiki); do not execute native AutoSci repo tools directly."
---

# $ask

This is a Solar AutoSci wrapper skill. Keep Solar as the orchestrator.

## Required Execution Path

Do not run native AutoSci repo tools directly. Do not mutate AutoSci's original `wiki/`, `tools/`, or `runtime/` paths from this skill.

When the user invokes this skill, preserve their arguments and route the request through the Solar Harness runtime, not the current worktree copy:

```bash
"${HARNESS_DIR:-$HOME/.solar/harness}/solar-harness.sh" '$ask' <user args>
```

If `HARNESS_DIR` is unset but `solar-harness` is on PATH, this direct form is also valid:

```bash
solar-harness '$ask' <user args>
```

Quote the dollar command in shell contexts so it is not expanded as an environment variable.

## Solar Route

- Solar capability: `cap.research-memory-update`
- Backend action: `ask_wiki`
- Coverage status: `partial`
- Side-effect policy: `none`

## Human-Facing Outputs

After execution, report the Solar-managed run evidence and the human-facing workspace paths:

- Solar-managed run evidence: `harness/artifacts/autosci/runs/<run-id>/`
- Human-facing wiki: `harness/artifacts/autosci/workspace/wiki/`
- Human-facing outputs: `harness/artifacts/autosci/workspace/wiki/outputs/`

Logs, envelopes, retries, and operator state remain Solar-managed and should not be copied into the human-facing wiki.

## Limitations

- Retrieval-backed ask answers now record context_brief/open_questions/index/edge context evidence, gap annotations, explicit model evidence or model-command synthesis with persisted request/response provenance, and an evidence-bound crystallize recommendation. --format table/timeline/bullets changes only the evidence-backed answer presentation. ask_final_answer_boundary requires retrieved source evidence plus completed model-backed synthesis with evidence ids before an answer is final, and missing retrieval/model evidence remains visible as incomplete rather than inferred. Optional crystallize write-back is approval-gated and can target outputs, concepts, ideas, methods, topics, or explicit wiki markdown paths while recording wiki output/log/edge/rebuild mutation evidence.
