# Compiler metadata incubator

This directory holds the first reviewed examples for Solar's input, intent,
and requirement compilation architecture. Each stage emits one small JSON
document that references the preceding artifact instead of copying it.

The example chain is:

1. `raw_intent.json` preserves the exact request, source, and byte identity.
2. `intent_ir.json` records normalized goals, outcomes, constraints, issues,
   and their RawIntent spans.
3. `intent_validation.json` records deterministic structural checks.
4. `intent_fidelity.json` records semantic review of the normalized meaning.
5. `requirement_ir.json` compiles accepted intent into workflow-independent,
   verifiable obligations.
6. `requirement_validation.json` records requirement integrity checks.
7. `requirement_coverage.json` maps every IntentIR item to requirements.
8. `compilation_trace.json` binds the chain with file hashes.

`artifact_registry.json` names the producer and consumers of each artifact.
`field_consumer_matrix.json` rejects semantic fields that drive no downstream
decision. `generalization_cases.json` exercises the design across diverse
prompt classes. `validate_contract_examples.py` checks this committed example
without a model or network call.

These are ordinary artifact examples, not formal JSON Schema documents and
not runtime-generated request data. Formal schemas belong in the repository's
schema package after the examples are accepted.

This metadata contract is not wired into production. The current gateway still
emits `solar.rewritten_intent.v1` and lowers it directly into
`solar.requirement_ir.v1`. Runtime wiring is a later increment.
