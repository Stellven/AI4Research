---
name: ingest
description: "Solar AutoSci wrapper for $ingest. Use when the user invokes $ingest, asks for AutoSci ingest, or requests the corresponding Solar research workflow. This OpenSolar wrapper preserves the native AutoSci skill UX while routing execution through Solar Harness (cap.research-paper-ingest, backend action ingest_paper); do not execute native AutoSci repo tools directly."
---

# $ingest

This is a Solar AutoSci wrapper skill. Keep Solar as the orchestrator.

## Required Execution Path

Do not run native AutoSci repo tools directly. Do not mutate AutoSci's original `wiki/`, `tools/`, or `runtime/` paths from this skill.

When the user invokes this skill, preserve their arguments and route the request through the Solar Harness runtime, not the current worktree copy:

```bash
"${HARNESS_DIR:-$HOME/.solar/harness}/solar-harness.sh" autosci '$ingest <user args>'
```

If `HARNESS_DIR` is unset but `solar-harness` is on PATH, this explicit AutoSci subcommand form is also valid:

```bash
solar-harness autosci '$ingest <user args>'
```

Keep the AutoSci subcommand explicit and quote the dollar command in shell contexts so it is not expanded as an environment variable.

## Solar Route

- Solar capability: `cap.research-paper-ingest`
- Backend actions: `prepare_paper_source` -> `ingest_paper`
- Coverage status: `full`
- Side-effect policy: `dry_run_only`

## Human-Facing Outputs

After execution, report the Solar-managed run evidence and the human-facing workspace paths:

- Solar-managed run evidence: `harness/artifacts/autosci/runs/<run-id>/`
- Human-facing wiki: `harness/artifacts/autosci/workspace/wiki/`
- Human-facing outputs: `harness/artifacts/autosci/workspace/wiki/outputs/`

Logs, envelopes, retries, and operator state remain Solar-managed and should not be copied into the human-facing wiki.

## Limitations

- PDF and arXiv source preparation writes explicit generated artifacts under the Solar AutoSci workspace raw area.
- Set `allow_network_fetch=false` or `AUTOSCI_DISABLE_NETWORK_FETCH=1` when a run must avoid network source retrieval and use synthetic `.tex` fallback.
