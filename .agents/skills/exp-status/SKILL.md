---
name: exp-status
description: "Solar AutoSci wrapper for $exp-status. Use when the user invokes $exp-status, asks for AutoSci exp-status, or requests the corresponding Solar research workflow. This OpenSolar wrapper preserves the native AutoSci skill UX while routing execution through Solar Harness (cap.research-experiment-monitor, backend action monitor_experiment); do not execute native AutoSci repo tools directly."
---

# $exp-status

This is a Solar AutoSci wrapper skill. Keep Solar as the orchestrator.

## Required Execution Path

Do not run native AutoSci repo tools directly. Do not mutate AutoSci's original `wiki/`, `tools/`, or `runtime/` paths from this skill.

When the user invokes this skill, preserve their arguments and route the request through the Solar Harness runtime, not the current worktree copy:

```bash
"${HARNESS_DIR:-$HOME/.solar/harness}/solar-harness.sh" autosci '$exp-status <user args>'
```

If `HARNESS_DIR` is unset but `solar-harness` is on PATH, this explicit AutoSci subcommand form is also valid:

```bash
solar-harness autosci '$exp-status <user args>'
```

Keep the AutoSci subcommand explicit and quote the dollar command in shell contexts so it is not expanded as an environment variable.

## Solar Route

- Solar capability: `cap.research-experiment-monitor`
- Backend action: `monitor_experiment`
- Coverage status: `full`
- Side-effect policy: `none`

## Human-Facing Outputs

After execution, report the Solar-managed run evidence and the human-facing workspace paths:

- Solar-managed run evidence: `harness/artifacts/autosci/runs/<run-id>/`
- Human-facing wiki: `harness/artifacts/autosci/workspace/wiki/`
- Human-facing outputs: `harness/artifacts/autosci/workspace/wiki/outputs/`

Logs, envelopes, retries, and operator state remain Solar-managed and should not be copied into the human-facing wiki.

## Limitations

- Remote status requires live remote connectivity; unavailable connectivity must be reported as warning evidence.
