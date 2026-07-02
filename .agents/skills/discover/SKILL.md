---
name: discover
description: "Solar AutoSci wrapper for $discover. Use when the user invokes $discover, asks for AutoSci discover, or requests the corresponding Solar research workflow. This OpenSolar wrapper preserves the native AutoSci skill UX while routing execution through Solar Harness (cap.research-literature-discover, backend action discover_literature); do not execute native AutoSci repo tools directly."
---

# $discover

This is a Solar AutoSci wrapper skill. Keep Solar as the orchestrator.

## Required Execution Path

Do not run native AutoSci repo tools directly. Do not mutate AutoSci's original `wiki/`, `tools/`, or `runtime/` paths from this skill.

When the user invokes this skill, preserve their arguments and route the request through the Solar Harness runtime, not the current worktree copy:

```bash
"${HARNESS_DIR:-$HOME/.solar/harness}/solar-harness.sh" autosci '$discover <user args>'
```

If `HARNESS_DIR` is unset but `solar-harness` is on PATH, this explicit AutoSci subcommand form is also valid:

```bash
solar-harness autosci '$discover <user args>'
```

Keep the AutoSci subcommand explicit and quote the dollar command in shell contexts so it is not expanded as an environment variable.

## Solar Route

- Solar capability: `cap.research-literature-discover`
- Backend action: `discover_literature`
- Coverage status: `full`
- Side-effect policy: `none`

## Supported AutoSci-Compatible Arguments

The Solar wrapper preserves the native AutoSci discovery seed modes:

- `--anchor <id>` (repeatable) with optional `--negative <id>`
- `--topic "<query>"`
- `--from-wiki`
- `--venue <slug> --year <YYYY>`
- `--limit <N>`
- `--no-citation-expand`
- `--wiki-root <path>`

Exactly one seed mode should be used for a real discovery run. `--from-wiki`
uses the human-facing Solar AutoSci wiki by default:
`harness/artifacts/autosci/workspace/wiki/`.

## Human-Facing Outputs

After execution, report the Solar-managed run evidence and the human-facing workspace paths:

- Solar-managed run evidence: `harness/artifacts/autosci/runs/<run-id>/`
- Human-facing wiki: `harness/artifacts/autosci/workspace/wiki/`
- Human-facing outputs: `harness/artifacts/autosci/workspace/wiki/outputs/`

Logs, envelopes, retries, and operator state remain Solar-managed and should not be copied into the human-facing wiki.

## Limitations

- Live API failures must be represented as incomplete source evidence rather than synthetic recommendations.
- If Semantic Scholar or Paper Copilot access is unavailable, the run must emit inconclusive evidence rather than local fixture candidates.
