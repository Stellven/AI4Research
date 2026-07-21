---
name: rebuttal
description: "Solar AutoSci wrapper for $rebuttal. Use when the user invokes $rebuttal, asks for AutoSci rebuttal, or requests the corresponding Solar research workflow. This OpenSolar wrapper preserves the native AutoSci skill UX while routing execution through Solar Harness (cap.research-publication-produce, backend action draft_rebuttal); do not execute native AutoSci repo tools directly."
---

# $rebuttal

This is a Solar AutoSci wrapper skill. Keep Solar as the orchestrator.

## Required Execution Path

Do not run native AutoSci repo tools directly. Do not mutate AutoSci's original `wiki/`, `tools/`, or `runtime/` paths from this skill.

When the user invokes this skill, preserve their arguments and route the request through the Solar Harness runtime, not the current worktree copy:

```bash
"${HARNESS_DIR:-$HOME/.solar/harness}/solar-harness.sh" '$rebuttal' <user args>
```

If `HARNESS_DIR` is unset but `solar-harness` is on PATH, this direct form is also valid:

```bash
solar-harness '$rebuttal' <user args>
```

Quote the dollar command in shell contexts so it is not expanded as an environment variable.

## Solar Route

- Solar capability: `cap.research-publication-produce`
- Backend action: `draft_rebuttal`
- Coverage status: `partial`
- Side-effect policy: `dry_run_only`

## Human-Facing Outputs

After execution, report the Solar-managed run evidence and the human-facing workspace paths:

- Solar-managed run evidence: `harness/artifacts/autosci/runs/<run-id>/`
- Human-facing wiki: `harness/artifacts/autosci/workspace/wiki/`
- Human-facing outputs: `harness/artifacts/autosci/workspace/wiki/outputs/`

Logs, envelopes, retries, and operator state remain Solar-managed and should not be copied into the human-facing wiki.

## Limitations

- Reviewer-thread evidence is atomized into RvX-CY concerns, mapped to wiki/source evidence, rendered as rich/formal rebuttal artifacts, and gated by Review LLM stress-test plus supplied submission audit evidence; portal submission itself is not claimed unless external audit evidence records it.
