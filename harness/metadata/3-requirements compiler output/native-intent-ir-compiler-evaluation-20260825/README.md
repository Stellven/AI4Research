# Native IntentIR Requirement Compiler evaluation

This is the corrected 25-case Requirement Compiler trial.

Each case:

1. reads only the Stage 2 fixture's `intent_ir.json`;
2. calls `harness/lib/requirement_compiler/compiler.py`;
3. writes only the compiler's `requirement_ir.json` artifact; and
4. runs the separate deterministic format evaluator against the authoritative
   Stage 3 `requirement_ir/requirement_ir.json` template.

The compiler derives the required `intent_acceptance_ref.acceptance_id` using
the Intent Compiler gate's deterministic naming rule
`intent-acceptance-{raw_intent_id}`. The gate remains responsible for proving
that the referenced decision is actually `accepted` before handoff.

`format_evaluation.json` is test evidence, not a Requirement Compiler output.
Run `_run_evaluation.py` to reproduce all outputs and `evaluation_summary.json`.
