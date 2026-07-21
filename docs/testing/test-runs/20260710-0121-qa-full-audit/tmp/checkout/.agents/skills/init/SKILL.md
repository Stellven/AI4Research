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
"${HARNESS_DIR:-$HOME/.solar/harness}/solar-harness.sh" autosci '$init <user args>'
```

If `HARNESS_DIR` is unset but `solar-harness` is on PATH, this explicit AutoSci subcommand form is also valid:

```bash
solar-harness autosci '$init <user args>'
```

Keep the AutoSci subcommand explicit and quote the dollar command in shell contexts so it is not expanded as an environment variable.

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

- Bulk fetch and ingest are decomposed into source manifest evidence plus separate ingest routes.
- Root-aware parity may recognize local source fan-in as full only when the Phase19 semantic audit/proof is loaded.
- Static route config remains partial until source preparation, final source manifest, approved wiki fan-in, graph/log/index rebuild evidence, and ingest fan-out/fan-in boundaries are proven by typed evidence.
