# Current v1 Requirement Compiler evaluation

> **SUPERSEDED TEST SETUP:** This run incorrectly treated Intent validation and
> fidelity as Requirement Compiler inputs and Requirement validation and
> coverage as compiler outputs. It is retained only as historical diagnostic
> evidence. Use `../native-intent-ir-compiler-evaluation-20260825/` for the
> corrected one-input/one-output trial.

This folder retains the result of feeding the 25 admitted Stage 2 fixture
bundles into the current Requirement Compiler implementation and comparing its
outputs with the authoritative Stage 3 templates in the parent directory.

## Production entrypoint exercised

`harness/lib/intent_gateway.py::build_requirement_ir`

The current function accepts `(intent_id, raw_intent, rewritten)` rather than
the Stage 2 bundle `(intent_ir, intent_validation, intent_fidelity)`. The run
therefore uses a documented compatibility adapter to translate the fixture
bundle into the legacy arguments. This adapter is test plumbing; it is not
counted as product support for the required handoff.

## Expected Stage 3 bundle

- `requirement_ir.json`
- `requirement_validation.json`
- `requirement_coverage.json`

The evaluator never fabricates missing outputs. Each case directory contains
the raw artifact emitted by the current compiler plus `comparison.json`.
`evaluation_summary.json` records the aggregate verdict.

Run `_run_evaluation.py` to reproduce the outputs and comparison. Run
`_validate_evaluation.py` to verify the retained files, hashes, inventories,
and aggregate verdict.
