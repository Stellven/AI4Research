# Requirement Compiler input fixtures

This directory contains synthetic, admitted Intent Compiler output bundles for
testing the Requirement Compiler. The artifact contracts in the parent
directory are the source of truth.

Each numbered case directory contains exactly the Intent Compiler artifact
passed to the Requirement Compiler:

- `intent_ir.json`

The original prompt and bundle metadata live in `fixture_catalog.json` so a
Stage 1 `raw_intent.json` is not incorrectly placed among Stage 2 outputs.
Intent validation, fidelity, and clarification are evaluator/gate outputs and
are deliberately outside these Requirement Compiler input cases.

## Handoff rule

The deterministic fixture route is:

`input_normalizer -> intent_compiler -> intent_acceptance_gate -> requirement_compiler`

The test runner must pass only `intent_ir.json` inside a case directory to the
Requirement Compiler.

## Hashing

- `raw_text_sha256` is SHA-256 over the exact UTF-8 prompt stored in the
  catalog, without an added newline.
- `intent_ir_sha256` is SHA-256 over the exact UTF-8 bytes of that case's
  generated `intent_ir.json`, including its final newline.

Run `_generate_fixtures.py` from any working directory to reproduce the
catalog and all 25 bundles deterministically.
