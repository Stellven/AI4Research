# Professor-Grade Survey Gates

This package documents the opt-in DeepResearch survey quality gates delivered by the S01-S05 hardening epic.

## Scope

The gates are package-local under `lib/research/survey`.
They do not rewrite the main harness coordinator.
They do not require live web access during verification.
They are designed to make weak survey output visible instead of silently accepting it.

## Enable Gates

1. Import the gate package so registry decorators load.
2. Run source quality checks before section synthesis.
3. Run argument density checks after section draft generation.
4. Run controversy matrix checks before chapter synthesis.
5. Run exploration logging before committing to a research direction.
6. Compile a `GateReport` and surface it in CLI/status views.

## Gate Surface

The source quality gate checks high-authority source distribution.
The argument density gate checks five required reasoning dimensions.
The controversy matrix gate checks negative evidence and synthesis usage.
The exploration package records eliminated directions and kill reasons.
The gate report aggregator exposes partial verdicts.

## CLI Examples

`solar-harness survey-eval --run <run-id> --emit-gate-report`

`solar-harness survey-review --run <run-id> --show-source-quality`

`solar-harness survey-compile --run <run-id> --gate-report-json gate_report.json`

`solar-harness survey-plan --question "small model compression" --explore-directions 3`

`solar-harness status --epic epic-20260516-deepresearch-professor-grade-survey-quality-hardening-build`

## View Registry

S04 exposes view functions through `VIEW_REGISTRY`.
The expected keys are `source_quality`, `argument_density`, `contradiction_matrix`, `exploration`, and `gate_report`.
Downstream code should consume the registry instead of hard-coding formatter modules.

## Operational Notes

Missing optional gate inputs must produce visible degradation.
The `partial_verdicts` field is the observable contract for missing gate coverage.
Verification uses local fixtures and stub LLM response files.
Live LLM and 50k-word full survey runs are deferred.
Numeric production thresholds are deferred.

## Troubleshooting

If a report looks generic, inspect `argument_density`.
If sources are mostly blogs, inspect `source_quality`.
If negative evidence is absent, inspect `controversy_matrix`.
If search directions converge too early, inspect `elimination_log.jsonl`.
If the UI hides gate status, inspect `VIEW_REGISTRY` and `format_gate_report`.

