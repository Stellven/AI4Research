# Product Brief — Official full-runtime AutoSci integration test

**Source**: autosci-intake-contract
**Priority**: P1
**Lane**: research
**Handoff To**: builder_main

## Intent

Official full-runtime AutoSci integration test through normal solar intake. Do not call a manual autosci shim. The workflow must ingest papers, extract claims, generate ideas, run exp-design, exp-run, exp-eval, and produce a report so we can verify whether AutoSci autonomously participates in the runtime.
- requirement 0: keep AutoSci autonomous and evidence-backed.
- requirement 1: keep AutoSci autonomous and evidence-backed.
- requirement 2: keep AutoSci autonomous and evidence-backed.
- requirement 3: keep AutoSci autonomous and evidence-backed.
- requirement 4: keep AutoSci autonomous and evidence-backed.
- requirement 5: keep AutoSci autonomous and evidence-backed.
- requirement 6: keep AutoSci autonomous and evidence-backed.
- requirement 7: keep AutoSci autonomous and evidence-backe

## Acceptance Criteria

- Normal intake emits a `research.autosci.v1` task graph.
- Scientific* nodes resolve to AutoSci research capsules and autosci-* physical operators.
- Autopilot can dispatch ready graph nodes without a manual AutoSci shim call.

## Stop Rules

- Missing scientific task graph blocks dispatch.
- Missing schema-gated evidence blocks closeout.
