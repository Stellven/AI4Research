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
"${HARNESS_DIR:-$HOME/.solar/harness}/solar-harness.sh" autosci '$ask <user args>'
```

If `HARNESS_DIR` is unset but `solar-harness` is on PATH, this explicit AutoSci subcommand form is also valid:

```bash
solar-harness autosci '$ask <user args>'
```

Keep the AutoSci subcommand explicit and quote the dollar command in shell contexts so it is not expanded as an environment variable.

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

- Model synthesis and confidence calibration remain explicit evidence requirements; missing retrieval evidence must be reported as inconclusive.
