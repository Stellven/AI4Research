---
name: exp-pilot-eval
description: "Solar AutoSci wrapper for $exp-pilot-eval. Use when the user invokes $exp-pilot-eval, asks for AutoSci exp-pilot-eval, or requests the corresponding Solar research workflow. This OpenSolar wrapper preserves the native AutoSci skill UX while routing execution through Solar Harness (cap.research-claim-verify, backend action evaluate_pilot_result); do not execute native AutoSci repo tools directly."
---

# $exp-pilot-eval

This is a Solar AutoSci wrapper skill. Keep Solar as the orchestrator.

## Required Execution Path

Do not run native AutoSci repo tools directly. Do not mutate AutoSci's original `wiki/`, `tools/`, or `runtime/` paths from this skill.

When the user invokes this skill, preserve their arguments and route the request through the Solar Harness runtime, not the current worktree copy:

```bash
"${HARNESS_DIR:-$HOME/.solar/harness}/solar-harness.sh" autosci '$exp-pilot-eval <user args>'
```

If `HARNESS_DIR` is unset but `solar-harness` is on PATH, this explicit AutoSci subcommand form is also valid:

```bash
solar-harness autosci '$exp-pilot-eval <user args>'
```

Keep the AutoSci subcommand explicit and quote the dollar command in shell contexts so it is not expanded as an environment variable.

## Solar Route

- Solar capability: `cap.research-claim-verify`
- Backend action: `evaluate_pilot_result`
- Coverage status: `partial`
- Side-effect policy: `approval_required`

## Human-Facing Outputs

After execution, report the Solar-managed run evidence and the human-facing workspace paths:

- Solar-managed run evidence: `harness/artifacts/autosci/runs/<run-id>/`
- Human-facing wiki: `harness/artifacts/autosci/workspace/wiki/`
- Human-facing outputs: `harness/artifacts/autosci/workspace/wiki/outputs/`

Logs, envelopes, retries, and operator state remain Solar-managed and should not be copied into the human-facing wiki.

## Limitations

- Pilot wiki writes are represented as proposed memory updates until `--write`, `--approval-ref`, and `--execute-approved` are supplied with approval/runtime evidence.
