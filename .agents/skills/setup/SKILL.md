---
name: setup
description: "Solar AutoSci wrapper for $setup. Use when the user invokes $setup, asks for AutoSci setup, or requests the corresponding Solar research workflow. This OpenSolar wrapper preserves the native AutoSci skill UX while routing execution through Solar Harness (cap.research-workflow-evolve, backend action setup_status); do not execute native AutoSci repo tools directly."
---

# $setup

This is a Solar AutoSci wrapper skill. Keep Solar as the orchestrator.

## Required Execution Path

Do not run native AutoSci repo tools directly. Do not mutate AutoSci's original `wiki/`, `tools/`, or `runtime/` paths from this skill.

When the user invokes this skill, preserve their arguments and route the request through the Solar Harness runtime, not the current worktree copy:

```bash
"${HARNESS_DIR:-$HOME/.solar/harness}/solar-harness.sh" autosci '$setup <user args>'
```

If `HARNESS_DIR` is unset but `solar-harness` is on PATH, this explicit AutoSci subcommand form is also valid:

```bash
solar-harness autosci '$setup <user args>'
```

Keep the AutoSci subcommand explicit and quote the dollar command in shell contexts so it is not expanded as an environment variable.

## Solar Route

- Solar capability: `cap.research-workflow-evolve`
- Backend action: `setup_status`
- Coverage status: `gated`
- Side-effect policy: `approval_required`

## Human-Facing Outputs

After execution, report the Solar-managed run evidence and the human-facing workspace paths:

- Solar-managed run evidence: `harness/artifacts/autosci/runs/<run-id>/`
- Human-facing wiki: `harness/artifacts/autosci/workspace/wiki/`
- Human-facing outputs: `harness/artifacts/autosci/workspace/wiki/outputs/`

Logs, envelopes, retries, and operator state remain Solar-managed and should not be copied into the human-facing wiki.

## Limitations

- Solar must not write secrets or credentials without explicit user-provided values and approval.
