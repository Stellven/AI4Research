---
name: init
description: "Solar AutoSci wrapper for $init. Use when the user invokes $init, asks for AutoSci init, or requests the corresponding Solar research workflow. This OpenSolar wrapper preserves the native AutoSci skill UX while routing execution through Solar Harness (cap.research-literature-discover, backend action init_sources); do not execute native AutoSci repo tools directly."
---

# $init

This is a Solar AutoSci wrapper skill. Keep Solar as the orchestrator.

## Required Execution Path

Do not run native AutoSci repo tools directly. Do not mutate AutoSci's original `wiki/`, `tools/`, or `runtime/` paths from this skill.

When the user invokes this skill, preserve their arguments and route the request through the Solar Harness runtime, not the current worktree copy:

```bash
"${HARNESS_DIR:-$HOME/.solar/harness}/solar-harness.sh" '$init' <user args>
```

If `HARNESS_DIR` is unset but `solar-harness` is on PATH, this direct form is also valid:

```bash
solar-harness '$init' <user args>
```

Quote the dollar command in shell contexts so it is not expanded as an environment variable.

## Solar Route

- Solar capability: `cap.research-literature-discover`
- Backend action: `init_sources`
- Coverage status: `partial`
- Side-effect policy: `approval_required`

## Human-Facing Outputs

After execution, report the Solar-managed run evidence and the human-facing workspace paths:

- Solar-managed run evidence: `harness/artifacts/autosci/runs/<run-id>/`
- Human-facing wiki: `harness/artifacts/autosci/workspace/wiki/`
- Human-facing outputs: `harness/artifacts/autosci/workspace/wiki/outputs/`

Logs, envelopes, retries, and operator state remain Solar-managed and should not be copied into the human-facing wiki.

## Limitations

- Approved runtime source manifests can complete init evidence only with production-shaped provider or local source-channel boundary proof, and --write can fan candidates into wiki papers/log/graph; init_sources_final_fan_in_boundary requires provider/local source candidates, approved wiki fan-in, graph/log/index rebuild evidence, and verified approval/runtime evidence before initialization is final; native network fetch and bulk ingest execution remain approval/provider-gated.
