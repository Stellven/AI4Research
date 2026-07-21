---
name: research
description: "Solar AutoSci wrapper for $research. Use when the user invokes $research, asks for AutoSci research, or requests the corresponding Solar research workflow. This OpenSolar wrapper preserves the native AutoSci skill UX while routing execution through Solar Harness (cap.research-workflow-evolve, backend action run_research_lifecycle); do not execute native AutoSci repo tools directly."
---

# $research

This is a Solar AutoSci wrapper skill. Keep Solar as the orchestrator.

## Required Execution Path

Do not run native AutoSci repo tools directly. Do not mutate AutoSci's original `wiki/`, `tools/`, or `runtime/` paths from this skill.

When the user invokes this skill, preserve their arguments and route the request through the Solar Harness runtime, not the current worktree copy:

```bash
"${HARNESS_DIR:-$HOME/.solar/harness}/solar-harness.sh" '$research' <user args>
```

If `HARNESS_DIR` is unset but `solar-harness` is on PATH, this direct form is also valid:

```bash
solar-harness '$research' <user args>
```

Quote the dollar command in shell contexts so it is not expanded as an environment variable.

## Solar Route

- Solar capability: `cap.research-workflow-evolve`
- Backend action: `run_research_lifecycle`
- Coverage status: `partial`
- Side-effect policy: `approval_required`

## Human-Facing Outputs

After execution, report the Solar-managed run evidence and the human-facing workspace paths:

- Solar-managed run evidence: `harness/artifacts/autosci/runs/<run-id>/`
- Human-facing wiki: `harness/artifacts/autosci/workspace/wiki/`
- Human-facing outputs: `harness/artifacts/autosci/workspace/wiki/outputs/`

Logs, envelopes, retries, and operator state remain Solar-managed and should not be copied into the human-facing wiki.

## Limitations

- Evidence-aware lifecycle completion is supported when wiki/source, Review LLM, experiment runtime, collection, and compile/PDF evidence are supplied.
- `$research --scheduler-run` now defaults to `run_scientific_workflow.py`, a config-driven generic workflow runner that dispatches selected workflow nodes through operator_runtime and records `runner_contract=generic_workflow_runner`; the old bounded lifecycle smoke runner remains available only through `--scheduler-legacy-smoke-runner`.
- Scheduler resume runs on the legacy smoke path still emit `autosci_scheduler_resume_boundary.v1` with reused-node fingerprints and no-rerun checks; generic workflow lifecycle summaries emit `scientific_workflow_runtime_manifest.v1`, but production scheduler parity still requires complete non-fixture node selection plus distributed lease/quota/runtime audit.
- `--scheduler-require-workflow-config-alignment` passes only for the full supplied-evidence tail; partial/default runs surface workflow_config_alignment drift or inconclusive status rather than full parity.
- `--scheduler-require-production-dispatch` now fails when the selected scheduler runner reports fixture/smoke input markers or blocked provider/runtime evidence.
- `--scheduler-include-human-gates` records idea/results approval pauses as scheduler-visible blocked nodes, `--online` can carry supplied approval/runtime source evidence into strict scheduler source mode with non-fixture provider channel boundary checks, scheduler experiment stages can carry explicit `--experiment-*` approval/runtime evidence without reusing source evidence paths, `--experiment-execute-approved` can run an allowlisted approved local experiment command, and scheduler publication compile can use compile-specific approved runtime evidence or `--compile-execute-approved`.
- Full parity still requires real provider evidence, audited remote/session stage runners, production scheduler dispatch, and submission/anonymity checks.
