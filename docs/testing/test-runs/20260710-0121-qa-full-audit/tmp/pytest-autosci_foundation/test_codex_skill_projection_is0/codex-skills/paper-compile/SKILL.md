---
name: paper-compile
description: "Solar AutoSci wrapper for $paper-compile. Use when the user invokes $paper-compile, asks for AutoSci paper-compile, or requests the corresponding Solar research workflow. This OpenSolar wrapper preserves the native AutoSci skill UX while routing execution through Solar Harness (cap.research-publication-produce, backend action compile_paper); do not execute native AutoSci repo tools directly."
---

# $paper-compile

This is a Solar AutoSci wrapper skill. Keep Solar as the orchestrator.

## Required Execution Path

Do not run native AutoSci repo tools directly. Do not mutate AutoSci's original `wiki/`, `tools/`, or `runtime/` paths from this skill.

When the user invokes this skill, preserve their arguments and route the request through the Solar Harness runtime, not the current worktree copy:

```bash
"${HARNESS_DIR:-$HOME/.solar/harness}/solar-harness.sh" '$paper-compile' <user args>
```

If `HARNESS_DIR` is unset but `solar-harness` is on PATH, this direct form is also valid:

```bash
solar-harness '$paper-compile' <user args>
```

Quote the dollar command in shell contexts so it is not expanded as an environment variable.

## Solar Route

- Solar capability: `cap.research-publication-produce`
- Backend action: `compile_paper`
- Coverage status: `gated`
- Side-effect policy: `approval_required`

## Human-Facing Outputs

After execution, report the Solar-managed run evidence and the human-facing workspace paths:

- Solar-managed run evidence: `harness/artifacts/autosci/runs/<run-id>/`
- Human-facing wiki: `harness/artifacts/autosci/workspace/wiki/`
- Human-facing outputs: `harness/artifacts/autosci/workspace/wiki/outputs/`

Logs, envelopes, retries, and operator state remain Solar-managed and should not be copied into the human-facing wiki.

## Limitations

- Native paper compile semantics are complete behind the explicit approval boundary: TeX execution requires allowlist, approval, before/after artifacts, and runtime evidence; compile readiness requires structurally valid PDF output; venue submission readiness requires source-backed --submission-profile plus --pdf-inspection; submission audit readiness requires explicit --submission-audit evidence and does not imply portal upload unless that evidence says portal_submission_completed=true. The route remains coverage_status=gated because compilation and source auto-fix are side effects, while semantic full parity is attached through route-level audit evidence.
