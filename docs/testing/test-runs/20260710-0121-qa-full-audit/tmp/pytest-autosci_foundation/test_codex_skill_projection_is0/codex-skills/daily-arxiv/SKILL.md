---
name: daily-arxiv
description: "Solar AutoSci wrapper for $daily-arxiv. Use when the user invokes $daily-arxiv, asks for AutoSci daily-arxiv, or requests the corresponding Solar research workflow. This OpenSolar wrapper preserves the native AutoSci skill UX while routing execution through Solar Harness (cap.research-literature-discover, backend action daily_arxiv_prepare_finalize); do not execute native AutoSci repo tools directly."
---

# $daily-arxiv

This is a Solar AutoSci wrapper skill. Keep Solar as the orchestrator.

## Required Execution Path

Do not run native AutoSci repo tools directly. Do not mutate AutoSci's original `wiki/`, `tools/`, or `runtime/` paths from this skill.

When the user invokes this skill, preserve their arguments and route the request through the Solar Harness runtime, not the current worktree copy:

```bash
"${HARNESS_DIR:-$HOME/.solar/harness}/solar-harness.sh" '$daily-arxiv' <user args>
```

If `HARNESS_DIR` is unset but `solar-harness` is on PATH, this direct form is also valid:

```bash
solar-harness '$daily-arxiv' <user args>
```

Quote the dollar command in shell contexts so it is not expanded as an environment variable.

## Solar Route

- Solar capability: `cap.research-literature-discover`
- Backend action: `daily_arxiv_prepare_finalize`
- Coverage status: `gated`
- Side-effect policy: `approval_required`

## Human-Facing Outputs

After execution, report the Solar-managed run evidence and the human-facing workspace paths:

- Solar-managed run evidence: `harness/artifacts/autosci/runs/<run-id>/`
- Human-facing wiki: `harness/artifacts/autosci/workspace/wiki/`
- Human-facing outputs: `harness/artifacts/autosci/workspace/wiki/outputs/`

Logs, envelopes, retries, and operator state remain Solar-managed and should not be copied into the human-facing wiki.

## Limitations

- Native daily arXiv recommendation semantics are complete behind explicit approval/provider boundaries: one-off inform runs can use provider/runtime evidence plus Review LLM ranking, while SMTP delivery, GitHub Actions scheduling, and auto-ingest fan-in remain approval/provider-gated side effects. daily_arxiv_final_provider_delivery_boundary must verify provider candidates, ranking evidence, and either explicit delivery or approved wiki ingest/fan-in before a digest is final; semantic full parity is attached only through route-level audit evidence.
