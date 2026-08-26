# Corrected Requirement Compiler trial results

Result: **PASS (25/25)**

- Compiler input per trial: `intent_ir.json` only.
- Compiler output per trial: `requirement_ir.json` only.
- Evaluator evidence per trial: `format_evaluation.json` (not a compiler artifact).
- Exact recursive template-shape checks passed: 25/25.
- Intent reference and source-hash integrity checks passed: 25/25.
- Intent acceptance handoff-reference checks passed: 25/25.
- Legacy `title` / `problem` / `objective` outputs: 0.
- Compiler output was deterministic across repeated compilation in the test suite.

The schema-version value is treated as a non-empty string. Structural agreement
with the authoritative `requirement_ir.json` template is the enforced contract.

Run `_run_evaluation.py` to regenerate the trial and `_validate_evaluation.py`
to validate the retained evidence.
