---
name: exp-run
description: "Solar AutoSci wrapper for $exp-run. Use when the user invokes $exp-run, asks for AutoSci exp-run, or requests the corresponding Solar research workflow. This OpenSolar wrapper preserves the native AutoSci skill UX while routing execution through Solar Harness (cap.research-experiment-run, backend action run_experiment); do not execute native AutoSci repo tools directly."
---

# $exp-run

This is a Solar AutoSci wrapper skill. Keep Solar as the orchestrator.

## Required Execution Path

Do not run native AutoSci repo tools directly. Do not mutate AutoSci's original `wiki/`, `tools/`, or `runtime/` paths from this skill.

When the user invokes this skill, preserve their arguments and route the request through the Solar Harness runtime, not the current worktree copy:

```bash
"${HARNESS_DIR:-$HOME/.solar/harness}/solar-harness.sh" '$exp-run' <user args>
```

If `HARNESS_DIR` is unset but `solar-harness` is on PATH, this direct form is also valid:

```bash
solar-harness '$exp-run' <user args>
```

Quote the dollar command in shell contexts so it is not expanded as an environment variable.

## Solar Route

- Solar capability: `cap.research-experiment-run`
- Backend action: `run_experiment`
- Coverage status: `gated`
- Side-effect policy: `approval_required`

## Human-Facing Outputs

After execution, report the Solar-managed run evidence and the human-facing workspace paths:

- Solar-managed run evidence: `harness/artifacts/autosci/runs/<run-id>/`
- Human-facing wiki: `harness/artifacts/autosci/workspace/wiki/`
- Human-facing outputs: `harness/artifacts/autosci/workspace/wiki/outputs/`

Logs, envelopes, retries, and operator state remain Solar-managed and should not be copied into the human-facing wiki.

## Limitations

- Local default mode is approval-gated and can be proven without remote/provider configuration when approval_ref, allowlist evidence, before-state evidence, runtime evidence, deploy/run reports, collection ledger where applicable, and wiki mutation evidence are present. SSH, rsync, screen sessions, remote launch/pull-results, distributed session exactly-once collection, and live provider/remote connectivity remain optional remote-mode follow-up proof and must not block local default parity; local result-dir reads remain local collection only and must not be counted as live SSH/provider collection.
