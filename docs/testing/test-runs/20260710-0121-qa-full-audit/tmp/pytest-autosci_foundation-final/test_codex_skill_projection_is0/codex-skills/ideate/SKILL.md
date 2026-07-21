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
"${HARNESS_DIR:-$HOME/.solar/harness}/solar-harness.sh" '$ideate' <user args>
```

If `HARNESS_DIR` is unset but `solar-harness` is on PATH, this direct form is also valid:

```bash
solar-harness '$ideate' <user args>
```

Quote the dollar command in shell contexts so it is not expanded as an environment variable.

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

- Explicit model-command/model-evidence brainstorming is wired for source-grounded candidates with persisted request/response provenance, ideate_final_promotion_boundary records wiki maturity scan, failed-idea banlist, source evidence, model provenance, and novelty/review gate requirements before ideas are promotable, and completed pilot handoff/runtime evidence can close phase 5. Approved durable idea-page projection now requires the full ideate pipeline to be ready, projects generated_from/has_pilot_handoff graph edges, and records those graph edges in wiki mutation proof; side-effect execution is approval-gated and strict/safe modes emit side_effect_access_request evidence instead of silently passing as dry-run. Full native ideation still requires audited provider-backed dual-model brainstorming, external discovery evidence, novelty/review gates, pilot handoff evidence or explicit --skip-pilot, and explicit bounded-test mode for sample-content runs.
