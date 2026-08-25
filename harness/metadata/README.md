# Compiler metadata incubator

This directory is the initial, intentionally consolidated home for the Solar
intent and requirements compiler contracts. It keeps the first architecture
increment reviewable before the schemas, templates, registries, validators,
and examples are separated into their long-term package locations.

Runtime-generated request artifacts must not be committed here. Files in this
directory are repository-owned contracts, templates, or reviewed examples.

The first example chain is intentionally non-executable and uses one immutable
methane-research request throughout:

1. `raw_intent.json` preserves the exact received request.
2. `intent_ir.json` proposes a typed semantic interpretation.
3. `intent_validation.json` records reproducible structural checks.
4. `intent_fidelity.json` records the semantic decision still awaiting review.
5. `requirement_ir.json` lowers the proposed intent into workflow-independent
   obligations.
6. `requirement_validation.json` records requirement integrity checks.
7. `requirement_coverage.json` maps every intent item to requirements.
8. `compilation_trace.json` binds the example chain and its file digests.

`artifact_registry.json` names the producer and consumers for every artifact.
`validate_contract_examples.py` verifies the committed examples without an LLM
or network call. It does not claim to be the future production compiler.

This proposed chain is not wired into the current runtime. The current
`intent_gateway.py` writes `solar.rewritten_intent.v1` and then constructs
`solar.requirement_ir.v1` directly. The proposed `solar.intent_ir.v2` must not
be described as a production input until a later increment connects it to the
gateway, validators, Requirement Compiler, and planner admission gate.

The architecture is not accepted from the methane example alone.
`generalization_cases.json` contains diverse prompt fixtures and the downstream
decision each fixture must support. `field_consumer_matrix.json` requires every
IntentIR field to name the real component and decision that consume it. These
are design fixtures until a live LLM compiler is implemented and evaluated
against them.
