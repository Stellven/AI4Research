# GitHub Project Intelligence · S05 Release Note

## Epic Overview

- epic_id: `epic-20260524-p0-ai-influence-github-project-intelligence-system-upgrade`
- sprint_id: `sprint-20260524-p0-ai-influence-github-project-intelligence-system-upgrade-s05-verification-release`
- scope: verification, regression, release packaging, partial epic gate statement
- boundary: this sprint may pass on its own, but the upstream epic stays blocked by S04 O2/O3/O4/O5

## S01-S05 Summary

- S01: requirements slice defined 67 AC and the report/output contract.
- S02: architecture slice mapped module boundaries, ledger decisions, and downstream contracts.
- S03: runtime slice landed schema, evidence, cards, pipeline, and model ledger behavior.
- S04: orchestration slice is only partial at epic level; O1 passed, O2/O3/O4/O5 remain blockers.
- S05: verification slice now has V1-V4 runtime evidence, this release note, and the join traceability pack.

## Evidence References

- V1: `reports/github-intelligence/s05-acceptance/V1-discovery.json`, `V1-snapshot.json`, `V1-evidence.json`, `V1-detector.json`, `V1-card_brief.json`, `V1-report.json`
- V2: `V2-thunderomlx_readme1.json`, `V2-thunderomlx_readme2.json`, `V2-thunderomlx_release1.json`, `V2-thunderomlx_release2.json`, `V2-thunderomlx_issue1.json`, `V2-thunderomlx_issue2.json`, `V2-atoms.json`
- V3: `V3-agg_provider.json`, `V3-agg_model.json`, `V3-agg_cost.json`, `V3-agg_count.json`, `V3-budget_trigger.json`, `V3-field_validation.json`
- V4: `V4-regression_report.json`

## Rollback

1. remove `docs/github-project-intelligence/RELEASE.md`
2. remove `Knowledge/_raw/tech-hotspot-radar/github-project-intelligence/release/2026-05-28-s05-release.md`
3. remove `lib/github_intelligence/` subpackage if the runtime slice needs full rollback
4. drop or restore `model_call_ledger` data from the relevant SQLite backup before replay
5. remove `reports/github-intelligence/s05-acceptance/V2-*`, `V3-*`, `V4-*` artifacts if a clean re-run is required

## S04 Epic Close Blockers

- O2_eval_sidecar_gate
- O3_quota_fallback_observability
- O4_status_surface
- O5_orchestration_release

These four items keep the epic close gate in blocked state. S05 must not claim epic-ready.

## ATLAS Hook

- repair path: `repair.pr-cot`
- structured failure path: `failure.structured_repair`
- routing guard: `routing.complexity_budget`

## Partial Epic Verdict

- sprint verdict: passable
- epic verdict: blocked by S04 O2/O3/O4/O5
- coordinator action: continue with an S04 follow-up sprint before epic close
