# AutoSci Phase 8 Progress Log

Logged: 2026-06-17 17:42:04 EDT
Branch: `feature/autosci-solar-native`

## Scope

Phase 8 added deterministic Solar evaluator gates for scientific Evidence ABI
artifacts. Gates decide whether artifacts pass, fail, or remain inconclusive
using local JSON/schema checks and artifact-specific rules.

This phase does not change scheduler behavior, product logic, report logic,
fallback behavior, scoring, routing, quota, leases, model selection, or backend
adapter behavior.

## Files Changed

| Artifact group | Count | Operation | Commit | Paths |
|---|---:|---|---|---|
| Scientific evaluator package | 14 | Added | this phase commit | `harness/evaluators/scientific/*.py` |
| Gate tests | 5 | Added | this phase commit | `tests/harness/evaluators/scientific/test_*_gate.py` |
| Gate fixtures | 27 | Added | this phase commit | `tests/harness/evaluators/scientific/fixtures/{pass,fail}/...` |
| Phase log | 1 | Added | this phase commit | `docs/integrations/autosci/phase8-progress-log.md` |

## Evaluator Gates

| Gate | Primary schema or input | Deterministic checks |
|---|---|---|
| `paper_gate.py` | `research_paper.v1` | Schema, paper object, sections, parse status, partial limitations. |
| `claims_gate.py` | `research_claims.v1` | Schema, claims array, `claim_id`, `claim_type`, source anchors for testable claims, explicit non-testable reasons, unverified extraction status. |
| `method_gate.py` | `research_method.v1` | Schema, methods array, procedure, source papers, evidence ids. |
| `code_evidence_gate.py` | `code_evidence_map.v1` | Schema, mappings array, files, evidence ids. |
| `idea_gate.py` | `idea_candidate.v1` or `idea_evaluation.v1` | Schema, idea origin evidence ids, evaluation evidence ids, reject/inconclusive risk or limitation notes. |
| `experiment_plan_gate.py` | `experiment_plan.v1` | Schema, variables, metrics, procedure, expected artifacts, bounded or human-approved execution mode. |
| `experiment_result_gate.py` | `experiment_result.v1` | Schema, metrics, evidence ids, limitations for failed or inconclusive outcomes. |
| `claim_verdict_gate.py` | `claim_verdict.v1` | Schema, allowed verdicts, evidence ids, limitations for confidence below 0.8, artifact paths exist or declare unavailable with reason. |
| `report_gate.py` | `scientific_report.v1` | Schema, report evidence ids, section evidence ids, limitations for unsupported claims. |
| `memory_update_gate.py` | `research_memory_update.v1` | Schema, changes array, evidence ids, approval reference for delete operations. |
| `lifecycle_gate.py` | scientific lifecycle graph | Nodes, logical operators, capabilities, scopes, gates, dependencies, no `AutoSciRunner`, bounded experiment execution. |
| `workflow_evolution_gate.py` | `workflow_evolution.v1` | Schema, proposal evidence ids, approval reference for approved/applied proposals. |

## Fixture Coverage

| Fixture set | Count | Note |
|---|---:|---|
| Pass fixtures | 12 | One pass fixture per evaluator gate. |
| Fail fixtures | 12 | One fail fixture per evaluator gate with deterministic failure reasons. |
| Artifact marker files | 3 | Existing-path artifacts for claim verdict, experiment result, and report pass fixtures. |

## Checks Run

| Check | Status | Note |
|---|---|---|
| Solar context injection | ok with warning | Used repo-local `HARNESS_DIR=<OpenSolar>/harness bash solar-harness.sh context inject`; Mirage source was degraded. |
| Python syntax | ok | `python3 -m py_compile evaluators/scientific/*.py` passed. |
| Plan pytest command with system Python | warn | `python3 -m pytest tests/evaluators/scientific` could not run because system Python has no `pytest`. |
| Pytest with repo venv | ok | `.venv/bin/python -m pytest tests/evaluators/scientific` passed: 10 tests. |
| Claims gate CLI pass | ok | `python3 evaluators/scientific/claims_gate.py tests/evaluators/scientific/fixtures/pass/research_claims.json` returned `ok: true`. |
| Claims gate CLI fail | ok | Same CLI against the fail fixture returned exit code 2 with reasons for `claim_type`, `source_anchor`, and `verification_status`. |
| All-gate fixture matrix | ok | Script verified all 12 gates accept their pass fixture and reject their fail fixture with reasons. |
| No LLM/network/process calls | ok | `rg "openai|anthropic|llm|requests|urllib|subprocess|socket|http" evaluators/scientific tests/evaluators/scientific` returned no matches. |

## Notes

- Gate modules emit structured JSON through their CLI and use exit code 0 for
  pass, 2 for fail, and 3 for inconclusive.
- Schema validation uses `jsonschema` when available and a minimal local
  structural fallback otherwise. The gates themselves do not call LLMs, network
  APIs, or subprocesses.
- Existing unrelated dirty files were left untouched.

## Done State

Phase 8 is complete when each major scientific artifact can be accepted,
rejected, or marked inconclusive by a deterministic Solar gate with explicit
failure reasons and no reliance on AutoSci self-report.
