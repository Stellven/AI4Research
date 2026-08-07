# AutoSci Phase 13 Progress Log

Logged: 2026-06-18 16:47:53 EDT
Branch: `feature/autosci-solar-native`

## Scope

Phase 13 implemented fixture-mode claim verification verdict production through
Solar-native `claim_verdict.v1` Evidence ABI artifacts. The bridge now derives a
claim verdict from supplied claim evidence, experiment/static result evidence,
and optional code evidence. It maps supported, partially supported, refuting,
failed, and inconclusive result evidence without treating AutoSci/backend
self-report as final acceptance.

This phase does not change scheduler behavior, product logic, report logic,
fallback behavior, scoring, routing, quota, leases, model selection, or workflow
ownership. Claim verification remains a bounded fixture-mode adapter path.

## Files Changed

| Artifact group | Operation | Paths |
|---|---|---|
| Bridge action | Updated | `harness/plugins/autosci/bin/autosci_bridge.py` |
| Claim verdict adapter | Updated | `harness/plugins/autosci/adapters/autosci_to_claim_verdict.py` |
| Evaluator gate | Updated | `harness/evaluators/scientific/claim_verdict_gate.py` |
| Fixture envelopes | Added/updated | `tests/plugins/autosci/fixtures/envelope.verify_claim*.json` |
| Experiment result fixtures | Added | `tests/plugins/autosci/fixtures/{supported,partially_supported,not_supported,inconclusive}_experiment_result.json` |
| Plugin/evaluator tests | Updated | `tests/plugins/autosci/test_bridge_smoke.py`, `tests/harness/evaluators/scientific/test_claim_verdict_gate.py` |
| README | Updated | `harness/plugins/autosci/README.md` |
| Progress log | Added | `docs/integrations/autosci/phase13-progress-log.md` |

## Added / Updated / Used Classification

Phase 13 uses earlier logical operator and physical worker wiring. It should not
be described as adding `ScientificClaimVerifier` or
`autosci-claim-verify-worker`.

| Item | Phase 13 classification | Originally introduced | Phase 13 note |
|---|---|---|---|
| `ScientificClaimVerifier` | used | Phase 3 | Existing logical operator; no Phase 13 logical-operator addition. |
| `cap.scientific-claim-verify` | used | Phase 2 | Existing capability capsule; no Phase 13 capsule addition. |
| `claim_verdict.v1` | used | Phase 1 | Existing Evidence ABI schema; no schema change in Phase 13. |
| `verify_claim` bridge action | updated | Phase 4/5 path | Now derives verdict from supplied claim, experiment, and code evidence instead of returning a static fixture verdict. |
| `autosci-claim-verify-worker` | used | Phase 5 | Existing physical worker; Phase 13 validated runtime submit. |
| `claim_verdict_gate.py` | updated | Phase 8 | Now requires claim id, non-claim evidence, limitations, and prevents inconclusive/failed evidence from being upgraded. |
| `autosci_to_claim_verdict.py` | updated | Earlier adapter path | Preserves evidence outcome and grouped claim/experiment/code evidence ids. |
| Outcome fixtures | added | Phase 13 | Added supported, partially supported, not supported, and inconclusive result fixtures. |
| Outcome envelopes | added | Phase 13 | Added separate human-testable verify-claim envelopes for each verdict class. |

## Backend Action Behavior

| Evidence outcome | Verdict | Status |
|---|---|---|
| `supports` | `supported` | ok |
| `partially_supports` | `partially_supported` | ok |
| `refutes` | `not_supported` | ok |
| `inconclusive` | `inconclusive` | ok |
| `failed` | `inconclusive` | ok |
| missing experiment evidence | `inconclusive` | ok |

Each emitted verdict includes:

- `claim_id`
- verdict label
- confidence
- basis
- `evidence_ids`
- grouped `claim_evidence_ids`, `experiment_evidence_ids`, and `code_evidence_ids`
- limitations
- `evidence_outcome`

## Human-Testable Artifact Contract

The canonical Phase 13 smoke outputs are:

| Artifact | Schema | Path |
|---|---|---|
| Supported verdict | `claim_verdict.v1` | `harness/artifacts/scientific/smoke/claim_verdict.json` |
| Partial verdict | `claim_verdict.v1` | `harness/artifacts/scientific/smoke/claim_verdict.partially_supported.json` |
| Not-supported verdict | `claim_verdict.v1` | `harness/artifacts/scientific/smoke/claim_verdict.not_supported.json` |
| Inconclusive verdict | `claim_verdict.v1` | `harness/artifacts/scientific/smoke/claim_verdict.inconclusive.json` |

## Manual Checklist

| Checklist item | Status | Evidence |
|---|---|---|
| Verdict is one of supported / partially_supported / not_supported / inconclusive | ok | Four outcome fixtures generated the four expected verdicts. |
| Verdict cites claim artifact | ok | Gate requires `claim_id` inside `evidence_ids`; regression test covers missing claim id. |
| Verdict cites experiment/static/code evidence | ok | Gate requires at least one non-claim evidence id. Smoke outputs include experiment and code ids. |
| Verdict includes limitations | ok | Gate requires verdict-level or top-level limitations. |
| Gate catches missing evidence refs | ok | `test_claim_verdict_gate_requires_claim_id_in_evidence_ids` covers this. |
| Inconclusive evidence is not upgraded to supported | ok | Gate rejects upgraded inconclusive/failed evidence and smoke inconclusive stays inconclusive. |

## Checks Run

| Check | Status | Note |
|---|---|---|
| Solar context injection | warn | Repo-local context inject worked; Mirage source was degraded. |
| Phase 13 bridge smoke | ok | `verify_claim` regenerated supported, partially supported, not supported, and inconclusive verdict artifacts. |
| Claim verdict gates | ok | All four `claim_verdict*.json` smoke artifacts passed `claim_verdict_gate.py`. |
| Python syntax | ok | `py_compile` passed for the bridge, claim verdict adapter, and claim verdict gate. |
| Plugin/evaluator tests | ok | `pytest plugins/autosci/tests tests/evaluators/scientific`: 34 passed. |
| Operator runtime submit | ok | `autosci-claim-verify-worker` completed with exit code 0 for the supported fixture. |
| Physical operator JSON | ok | `json.tool config/physical-operators.json` passed. |
| Logical operator JSON | ok | `json.tool config/logical-operators.json` passed. |
| Plugin validation | ok | `plugin_loader.py validate --id autosci` passed. |
| Workflow validation | ok | Scientific experiment and full research lifecycle graphs passed `graph_scheduler.py validate`. |
| Architecture guard | ok | Full lifecycle strict guard passed. |
| Whitespace check | ok | `git diff --check` passed. |

## Warnings / Caveats

- AutoSci physical operators still use the existing placeholder
  `owner_host: solar@example-host` and do not declare explicit `host_id`; this is
  the pre-existing scheduler-clean warning, not changed here.
- Repo-local Solar context injection worked, but Mirage reported degraded source
  status.
- Several `.venv` invocations printed `RuntimeWarning` about `sys.prefix` /
  `sys.exec_prefix` when called as `../.venv/bin/python` from `harness/`; all
  affected commands exited successfully.
- Phase 13 verdicts are fixture-mode local verdicts only. They do not perform
  external scientific validation, live literature verification, paid API calls,
  network calls, or real benchmark execution.
- The operator result wrapper records the worker completion status and exit
  code; the claim verdict payload itself is written to the declared artifact
  path.
- Existing dirty/untracked files outside this Phase 13 scope were left
  untouched.

## Done State

Phase 13 is complete for the fixture-mode Solar-native adapter scope: claim
verification produces evidence-linked `claim_verdict.v1` artifacts for supported,
partially supported, not supported, and inconclusive outcomes; evaluator gates
enforce evidence references and non-upgrade behavior; plugin tests, workflow
validation, architecture guard, and whitespace checks pass.

## Checker Fix Pass — Expected Capsule Name

Follow-up checker required the Phase 13 capsule id to use the expected
`cap.scientific-claim-verify` name instead of the earlier research-prefixed
claim verification capsule name. Operations performed:

| Operation | Status | Note |
|---|---|---|
| Capsule rename | ok | Renamed the claim verification capsule and updated registry, operator configs, workflows, plugin manifest, and tests to `cap.scientific-claim-verify`. |
| Compatibility gate update | ok | Updated `lifecycle_gate.py` to accept `cap.scientific-*` capsules while keeping research-prefixed compatibility for earlier lifecycle nodes. |
| Runtime behavior | ok | No verdict mapping, evidence derivation, or claim-verification product logic changed. |

Rerun checker after this fix:

| Check | Status | Evidence |
|---|---|---|
| Four verdict labels | ok | Supported, partially supported, not supported, and inconclusive smoke artifacts were regenerated. |
| ClaimVerdictGate | ok | All four `claim_verdict.v1` smoke artifacts passed. |
| Negative probes | ok | Missing evidence references and inconclusive-to-supported upgrades were rejected. |
| Tests | ok | `bin/python3 -m pytest -q plugins/autosci/tests tests/evaluators/scientific`: 45 passed. |
| Workflow / architecture | ok | Claim verification, publication, full lifecycle, and resume graphs validated and passed strict guard. |
| Old capsule id check | ok | No old research-prefixed claim verification capsule references remain in harness configs, workflows, capsules, manifest, or Phase 13/14 logs. |
