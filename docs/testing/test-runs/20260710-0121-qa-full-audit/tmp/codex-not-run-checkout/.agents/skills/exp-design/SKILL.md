---
name: exp-design
description: "Solar AutoSci wrapper for $exp-design. Use when the user invokes $exp-design, asks for AutoSci exp-design, or requests the corresponding Solar research workflow. This OpenSolar wrapper preserves the native AutoSci skill UX while routing execution through Solar Harness (cap.research-experiment-design, backend action design_experiment); do not execute native AutoSci repo tools directly."
---

# $exp-design

This is a Solar AutoSci wrapper skill. Keep Solar as the orchestrator.

## Required Execution Path

Do not run native AutoSci repo tools directly. Do not mutate AutoSci's original `wiki/`, `tools/`, or `runtime/` paths from this skill.

When the user invokes this skill, preserve their arguments and route the request through the Solar Harness runtime, not the current worktree copy:

```bash
"${HARNESS_DIR:-$HOME/.solar/harness}/solar-harness.sh" autosci '$exp-design <user args>'
```

If `HARNESS_DIR` is unset but `solar-harness` is on PATH, this explicit AutoSci subcommand form is also valid:

```bash
solar-harness autosci '$exp-design <user args>'
```

Keep the AutoSci subcommand explicit and quote the dollar command in shell contexts so it is not expanded as an environment variable.

## Solar Route

- Solar capability: `cap.research-experiment-design`
- Backend action: `design_experiment`
- Coverage status: `partial`
- Side-effect policy: `dry_run_only`

## Human-Facing Outputs

After execution, report the Solar-managed run evidence and the human-facing workspace paths:

- Solar-managed run evidence: `harness/artifacts/autosci/runs/<run-id>/`
- Human-facing wiki: `harness/artifacts/autosci/workspace/wiki/`
- Human-facing outputs: `harness/artifacts/autosci/workspace/wiki/outputs/`

Logs, envelopes, retries, and operator state remain Solar-managed and should not be copied into the human-facing wiki.

## Limitations

- The local route emits evidence-linked plans and final execution readiness boundaries, but it does not yet write the native experiment wiki pages, master design document, graph edges, or rebuilt context/open-question views.
- Execution readiness requires resolved target evidence, completed Review LLM evidence, approval preflight, command handoff, and expected artifact handoff; missing pieces must remain visible as incomplete evidence.
