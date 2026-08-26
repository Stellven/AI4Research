# Evaluation result

> **SUPERSEDED:** The trial boundary used here was corrected after review. The
> authoritative retry consumes only `intent_ir.json` and evaluates only the
> emitted `requirement_ir.json` structure.

**Overall: FAIL — 0 of 25 current-compiler output bundles agree with the
authoritative Stage 3 templates.**

The same defects occurred for all 10 research, 5 internet-data, 5 experiment,
and 5 child-facing cases.

| Contract point | Expected | Current output |
| --- | --- | --- |
| Input interface | Accepted `intent_ir`, `intent_validation`, and `intent_fidelity` bundle | Legacy `raw_intent` plus `rewritten` arguments; compatibility adapter required |
| Artifact inventory | `requirement_ir`, `requirement_validation`, and `requirement_coverage` | `requirement_ir` only |
| Requirement IR version | `solar.requirement_ir.v2` | `solar.requirement_ir.v1` |
| Requirement IR shape | Requirements, IntentIR reference, scope, assumptions, conflict scan, approvals, rollback | Legacy title/problem/objective/lane/planner-hints shape |
| Next handoff | Requirement validation and coverage gates | Direct `pm_planner_task_graph` handoff |

## Uniform reason codes

Each reason occurred in all 25 cases:

- `CURRENT_COMPILER_HAS_NO_NATIVE_INTENT_BUNDLE_INTERFACE`
- `MISSING_REQUIREMENT_VALIDATION`
- `MISSING_REQUIREMENT_COVERAGE`
- `REQUIREMENT_IR_SCHEMA_VERSION_MISMATCH`
- `REQUIREMENT_IR_TEMPLATE_SHAPE_MISMATCH`
- `BYPASSES_REQUIREMENT_VALIDATION_AND_COVERAGE_GATES`

## Legacy regression observation

`tests/harness/test_intent_gateway.py` produced 26 passes and 4 failures. The
four failures are Windows subprocess-output encoding failures for Chinese
prompts: `ensure_ascii=False` is printed through CP1252 and raises
`UnicodeEncodeError`. A direct ASCII CLI capture passed. This runner/platform
defect is separate from the Stage 3 template failures above.
