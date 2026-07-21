---
name: check
description: "Solar AutoSci wrapper for $check. Use when the user invokes $check, asks for AutoSci check, or requests the corresponding Solar research workflow. This OpenSolar wrapper preserves the native AutoSci skill UX while routing execution through Solar Harness (cap.research-workflow-evolve, backend action check_wiki_health); do not execute native AutoSci repo tools directly."
---

# $check

This is a Solar AutoSci wrapper skill. Keep Solar as the orchestrator.

## Required Execution Path

Do not run native AutoSci repo tools directly. Do not mutate AutoSci's original `wiki/`, `tools/`, or `runtime/` paths from this skill.

When the user invokes this skill, preserve their arguments and route the request through the Solar Harness runtime, not the current worktree copy:

```bash
"${HARNESS_DIR:-$HOME/.solar/harness}/solar-harness.sh" '$check' <user args>
```

If `HARNESS_DIR` is unset but `solar-harness` is on PATH, this direct form is also valid:

```bash
solar-harness '$check' <user args>
```

Quote the dollar command in shell contexts so it is not expanded as an environment variable.

## Solar Route

- Solar capability: `cap.research-workflow-evolve`
- Backend action: `check_wiki_health`
- Coverage status: `partial`
- Side-effect policy: `none`

## Human-Facing Outputs

After execution, report the Solar-managed run evidence and the human-facing workspace paths:

- Solar-managed run evidence: `harness/artifacts/autosci/runs/<run-id>/`
- Human-facing wiki: `harness/artifacts/autosci/workspace/wiki/`
- Human-facing outputs: `harness/artifacts/autosci/workspace/wiki/outputs/`

Logs, envelopes, retries, and operator state remain Solar-managed and should not be copied into the human-facing wiki.

## Limitations

- LLM-assisted content quality checks can be backed by explicit model evidence or a model command with persisted request/response provenance; check_final_quality_boundary requires passing local wiki checks plus completed model-backed recommendation evidence, and absent model evidence is not treated as deterministic pass/fail.
