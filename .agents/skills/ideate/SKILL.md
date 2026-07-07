---
name: ideate
description: "Solar AutoSci wrapper for $ideate. Use when the user invokes $ideate, asks for AutoSci ideate, or requests the corresponding Solar research workflow. This OpenSolar wrapper preserves the native AutoSci skill UX while routing execution through Solar Harness (cap.research-idea-generate, backend action generate_ideas); do not execute native AutoSci repo tools directly."
---

# $ideate

This is a Solar AutoSci wrapper skill. Keep Solar as the orchestrator.

## Required Execution Path

Do not run native AutoSci repo tools directly. Do not mutate AutoSci's original `wiki/`, `tools/`, or `runtime/` paths from this skill.

When the user invokes this skill, preserve their arguments and route the request through the Solar Harness runtime, not the current worktree copy:

```bash
"${HARNESS_DIR:-$HOME/.solar/harness}/solar-harness.sh" autosci '$ideate <user args>'
```

If `HARNESS_DIR` is unset but `solar-harness` is on PATH, this explicit AutoSci subcommand form is also valid:

```bash
solar-harness autosci '$ideate <user args>'
```

Keep the AutoSci subcommand explicit and quote the dollar command in shell contexts so it is not expanded as an environment variable.

## Solar Route

- Solar capability: `cap.research-idea-generate`
- Backend action: `generate_ideas`
- Coverage status: `partial`
- Side-effect policy: `approval_required`

## Human-Facing Outputs

After execution, report the Solar-managed run evidence and the human-facing workspace paths:

- Solar-managed run evidence: `harness/artifacts/autosci/runs/<run-id>/`
- Human-facing wiki: `harness/artifacts/autosci/workspace/wiki/`
- Human-facing outputs: `harness/artifacts/autosci/workspace/wiki/outputs/`

Logs, envelopes, retries, and operator state remain Solar-managed and should not be copied into the human-facing wiki.

## Limitations

- Pilot execution remains a separate approval-gated route.
- Root-aware parity may recognize supplied-evidence ideation as full only when the Phase19 semantic audit/proof is loaded.
- Strict/safe gate modes emit explicit `side_effect_access_request` evidence instead of silently passing as a dry run.
- Static route config remains partial until source grounding, model brainstorm provenance, novelty/review gates, approved writeback, and pilot skip/handoff are all proven by typed evidence.
