---
name: exp-eval
description: "Solar AutoSci wrapper for $exp-eval. Use when the user invokes $exp-eval, asks for AutoSci exp-eval, or requests the corresponding Solar research workflow. This OpenSolar wrapper preserves the native AutoSci skill UX while routing execution through Solar Harness (cap.research-claim-verify, backend action verify_claim); do not execute native AutoSci repo tools directly."
---

# $exp-eval

This is a Solar AutoSci wrapper skill. Keep Solar as the orchestrator.

## Required Execution Path

Do not run native AutoSci repo tools directly. Do not mutate AutoSci's original `wiki/`, `tools/`, or `runtime/` paths from this skill.

When the user invokes this skill, preserve their arguments and route the request through the Solar Harness runtime, not the current worktree copy:

```bash
"${HARNESS_DIR:-$HOME/.solar/harness}/solar-harness.sh" '$exp-eval' <user args>
```

If `HARNESS_DIR` is unset but `solar-harness` is on PATH, this direct form is also valid:

```bash
solar-harness '$exp-eval' <user args>
```

Quote the dollar command in shell contexts so it is not expanded as an environment variable.

## Solar Route

- Solar capability: `cap.research-claim-verify`
- Backend action: `verify_claim`
- Coverage status: `partial`
- Side-effect policy: `approval_required`

## Human-Facing Outputs

After execution, report the Solar-managed run evidence and the human-facing workspace paths:

- Solar-managed run evidence: `harness/artifacts/autosci/runs/<run-id>/`
- Human-facing wiki: `harness/artifacts/autosci/workspace/wiki/`
- Human-facing outputs: `harness/artifacts/autosci/workspace/wiki/outputs/`

Logs, envelopes, retries, and operator state remain Solar-managed and should not be copied into the human-facing wiki.

## Limitations

- Experiment result, claim, code, and Review LLM evidence can be supplied explicitly for review-backed verdicts; approved --write can update linked wiki idea/experiment status, while unapproved mutation remains blocked; experiment_evaluation_final_verdict_boundary requires completed experiment_result.v1 evidence, linked claim/code evidence, completed Review LLM proof, and completed approved wiki writeback before a verdict is treated as final.
