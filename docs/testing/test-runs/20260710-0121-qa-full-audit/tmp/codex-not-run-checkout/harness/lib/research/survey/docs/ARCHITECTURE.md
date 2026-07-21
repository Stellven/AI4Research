# Survey Gate Architecture

## Package Boundary

The architecture is package-first.
Core gate logic lives under `lib/research/survey/gates`.
Exploration logic lives under `lib/research/survey/explorer`.
Display logic lives under `lib/research/survey/cli`.
Verification artifacts live under `runtime/survey-continue/sample-run-001`.

## Gate Registry

`GateRegistry` owns gate lookup.
`register_gate` attaches package-local gate functions.
Source quality is registered as `source_quality`.
Argument density is registered as `argument_density`.
Controversy is registered as `controversy`.
`compile_gate_report` aliases `controversy_matrix` to the registered controversy gate.

## Five Gate Surfaces

Source quality produces `SourceQualityDistribution`.
Argument density produces `ArgumentDensityProfile`.
Contradiction handling produces a matrix-shaped dict.
Exploration produces `ExplorationRunResult` and `elimination_log.jsonl`.
Gate report aggregation produces `GateReport`.

## Explorer

The explorer scores candidate directions.
At least two directions are needed for elimination.
The lowest scoring direction is killed when no explicit threshold is configured.
Each elimination record includes a non-empty kill reason.
Each elimination record includes evidence references.
The log writer appends JSONL records durably.

## View Layer

`VIEW_REGISTRY` exposes formatter and `to_dict` functions.
The registry keys are stable.
The formatters are pure.
The formatters do not perform network calls.
The formatters do not mutate gate outputs.

## Status And Dispatch Hint

S04 adds epic status rendering.
S04 adds dispatch gate hints.
The hint path is fail-open.
The status path reads traceability and graph evidence.
S05 verifies visibility rather than adding new status logic.

## Report Flow

Evidence pack enters source quality.
Section text enters argument density.
Claim-evidence rows enter controversy.
Candidate directions enter exploration.
The aggregator compiles the visible gate report.
The CLI view renders the gate report for humans.

## Non-Goals

No main architecture rewrite.
No new CLI subcommand in S05.
No live LLM dependency in S05 verification.
No production default enablement in S05.
No numeric quality thresholds in S05.

