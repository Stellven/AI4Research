# AutoSci Phase 11 Progress Log

Logged: 2026-06-18 16:16:00 EDT
Branch: `feature/autosci-solar-native`

## Scope

Phase 11 implemented fixture-mode research idea generation and idea evaluation
through Solar-native Evidence ABI artifacts. Idea generation consumes local
paper, claim, method, and memory evidence; idea evaluation emits explicit
novelty, feasibility, recommendation, duplicate status, risks, and evidence ids.

This phase does not change scheduler behavior, product logic, report logic,
fallback behavior, scoring, routing, quota, leases, model selection, or memory
mutation behavior. Idea memory records are emitted as `operation: propose`; no
wiki or research memory state is mutated.

## Files Changed

| Artifact group | Operation | Paths |
|---|---|---|
| Bridge actions | Updated | `harness/plugins/autosci/bin/autosci_bridge.py` |
| Idea adapters | Added/updated | `harness/plugins/autosci/adapters/autosci_to_{idea_candidate,idea_evaluation}.py` |
| Fixture envelopes | Added | `tests/plugins/autosci/fixtures/envelope.{generate_ideas,evaluate_ideas}.json` |
| Plugin tests | Updated | `tests/plugins/autosci/test_*.py` |
| Physical operators | Updated | `harness/config/physical-operators.json` |
| README | Updated | `harness/plugins/autosci/README.md` |

## Added / Updated / Used Classification

Phase 11 uses earlier logical-operator work. It should not be described as
adding `ScientificIdeaGenerator` or `ScientificIdeaEvaluator`.

| Item | Phase 11 classification | Originally introduced | Phase 11 note |
|---|---|---|---|
| `ScientificIdeaGenerator` | used | Phase 3 | Existing logical operator; no Phase 11 logical-operator addition. |
| `ScientificIdeaEvaluator` | used | Phase 3 | Existing logical operator; no Phase 11 logical-operator addition. |
| `generate_ideas` bridge action | implemented/enabled | Phase 5 placeholder path | Phase 11 made the action produce `idea_candidate.v1` evidence from local evidence inputs. |
| `evaluate_ideas` bridge action | added | Phase 11 | New action for `idea_evaluation.v1` and propose-only idea memory sidecar. |
| `autosci-idea-worker` | updated/enabled | Phase 5 placeholder | Existing disabled placeholder worker now dispatches only `generate_ideas`. |
| `autosci-idea-evaluate-worker` | added | Phase 11 | New physical worker for `evaluate_ideas`. |
| `autosci_to_idea_candidate.py` | updated | Earlier adapter path | Preserves limitations and candidate metadata including duplicate status. |
| `autosci_to_idea_evaluation.py` | added | Phase 11 | Converts evaluation output to `idea_evaluation.v1`. |
| `envelope.generate_ideas.json` | added | Phase 11 | Canonical human-testable smoke envelope. |
| `envelope.evaluate_ideas.json` | added | Phase 11 | Canonical human-testable smoke envelope. |

## Backend Actions

| Action | Phase 11 classification | Evidence ABI | Note |
|---|---|---|---|
| `generate_ideas` | implemented/enabled | `idea_candidate.v1` | Emits evidence-grounded candidates and marks duplicate ideas as filtered. |
| `evaluate_ideas` | added | `idea_evaluation.v1` | Emits novelty, feasibility, recommendation, risks, and evidence ids. |
| `evaluate_ideas` sidecar | added | `research_memory_update.v1` | Writes propose-only idea memory updates; does not mutate memory. |

## Physical Operator Wiring

| Operator | Phase 11 classification | Status | Action |
|---|---|---|---|
| `autosci-idea-worker` | updated/enabled | enabled | `generate_ideas` |
| `autosci-idea-evaluate-worker` | added | enabled | `evaluate_ideas` |

## Human-Testable Artifact Contract

The canonical Phase 11 smoke outputs are:

| Artifact | Schema | Path |
|---|---|---|
| Idea candidates | `idea_candidate.v1` | `harness/artifacts/scientific/smoke/idea_candidate.json` |
| Idea evaluations | `idea_evaluation.v1` | `harness/artifacts/scientific/smoke/idea_evaluation.json` |
| Idea memory sidecar | `research_memory_update.v1` | `harness/artifacts/scientific/smoke/research_memory_update.ideas.json` |

The evaluation smoke intentionally includes one promoted candidate and one
duplicate candidate. The duplicate candidate is marked `duplicate`/`filtered`
and receives a `reject` recommendation.

## Checks Run

| Check | Status | Note |
|---|---|---|
| Solar context injection | warn | Repo-local context inject worked; Mirage source was degraded. |
| Physical operator JSON | ok | `json.tool config/physical-operators.json` passed. |
| Python syntax | ok | `py_compile` passed for bridge and AutoSci adapters. |
| Phase 11 bridge smoke | ok | Wrote `idea_candidate.json`, `idea_evaluation.json`, and `research_memory_update.ideas.json`. |
| Idea gate | ok | `idea_gate.py artifacts/scientific/smoke/idea_evaluation.json` passed. |
| Idea memory gate | ok | `memory_update_gate.py artifacts/scientific/smoke/research_memory_update.ideas.json` passed. |
| Plugin tests | ok | `pytest plugins/autosci/tests`: 12 passed. |
| Operator runtime submit | ok | `autosci-idea-worker` and `autosci-idea-evaluate-worker` completed with exit code 0. |
| Runtime idea gates | ok | Runtime `idea_evaluation` and idea memory sidecar passed gates. |
| Evaluator regression tests | ok | `pytest tests/evaluators/scientific`: 12 passed. |
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
- Idea novelty is fixture-mode local novelty only. Phase 11 does not perform
  live literature search or claim external novelty.
- Existing dirty/untracked files outside this Phase 11 scope were left
  untouched.

## Binding Fix Recheck

Logged: 2026-06-18 EDT

The Phase 11 checker found that `ScientificIdeaEvaluator` was still bound to
`autosci-idea-worker`, which runs `generate_ideas`. The binding was corrected so
idea generation routes to `autosci-idea-worker` and idea evaluation routes to
`autosci-idea-evaluate-worker`.

| Check | Status | Note |
|---|---|---|
| `ScientificIdeaGenerator` binding | ok | Routes to `autosci-idea-worker`. |
| `ScientificIdeaEvaluator` binding | ok | Routes to `autosci-idea-evaluate-worker`. |
| Phase 11 bridge smoke | ok | `generate_ideas` and `evaluate_ideas` wrote native artifacts. |
| Idea candidate gate | ok | Passed with no warnings. |
| Idea evaluation gate | ok | Passed with no warnings. |
| Idea memory sidecar gate | ok | Passed with no warnings. |
| Runtime submit | ok | Both idea workers dispatched and returned to idle. |
| Manual checklist | ok | Grounding, novelty, feasibility, duplicate filtering, evidence-backed status, and propose-only memory all passed. |
| Regression tests | ok | `pytest tests/evaluators/scientific plugins/autosci/tests`: 26 passed. |
| Architecture guard | ok | Experiment lifecycle and full research lifecycle strict guards passed with zero warnings. |
| Whitespace check | ok | `git diff --check` passed. |

## Done State

Phase 11 is complete for the fixture-mode Solar-native adapter scope: idea
candidates, idea evaluations, duplicate filtering, propose-only idea memory
sidecars, physical operator submit, gates, tests, workflow validation,
architecture guard, and whitespace checks all pass.
