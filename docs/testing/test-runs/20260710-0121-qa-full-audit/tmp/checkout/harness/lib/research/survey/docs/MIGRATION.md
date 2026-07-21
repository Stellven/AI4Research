# Migration Guide

## Opt-In Model

The survey gate stack is opt-in.
Existing report generation can continue without enabling every gate.
Consumers should attach the runner hook or call the package-local functions directly.
No main coordinator rewrite is required.

## Frozen Modules

These modules remain unchanged by the verification release:

- `lib/research/survey/source_authority.py`
- `lib/research/survey/literature_mapping.py`
- `lib/research/survey/controversy.py`
- `lib/research/survey/chapter_review.py`
- `lib/research/survey/chief_editor.py`

## Frozen Runtime Files

These harness runtime files are not migration targets:

- `coordinator.sh`
- `autopilot.sh`
- `dispatcher.sh`
- `phase-state-machine.sh`
- `solar-harness.sh`
- `lib/research/survey/__init__.py`

## Enable Steps

1. Import `research.survey.gates.source_quality_distribution`.
2. Import `research.survey.gates.argument_density`.
3. Import `research.survey.gates.controversy_matrix`.
4. Import `research.survey.gates.compile_gate_report`.
5. Import `research.survey.cli` to populate `VIEW_REGISTRY`.
6. Call `compile_gate_report` after section evidence is available.
7. Render the report with `format_gate_report`.

## Compatibility

Existing dataclasses remain append-only.
Existing view functions remain pure.
Existing runner code can use `attach_to_survey_continue`.
Missing optional gates degrade through `partial_verdicts`.
Tests must use local fixtures instead of live network calls.

## Deferred Work

Full 50k-word live survey execution is deferred.
Production default enablement is deferred.
Numeric threshold tuning is deferred.
Live LLM verification is deferred.
Remote CI integration is deferred.

## Rollback

Disable gate imports to stop registry activation.
Remove runner hook attachment to stop callback registration.
Keep generated artifacts for audit.
Do not edit frozen runtime files during rollback.

