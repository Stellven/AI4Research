# AutoSci Native Lifecycle Continuation Baseline

Logged: 2026-06-25 EDT
Branch: `feature/autosci-solar-native`
OpenSolar HEAD: `721e6eee4eff39cd3a35cf7d240a67f2d493864f`
Native AutoSci HEAD: `71469e89eb1381e557661da0b90c0585c48288d7`

## Scope

This baseline starts the post-handoff continuation from
`AutoSci_Solar_Native_Migration_Master_Handoff_2026-06-26.md`.

The first implementation slice is not a novelty-only repair. The immediate goal
is to make parity claims auditable and prove at least one bounded scientific node
through Solar's real scheduler/operator path.

## Working Tree State

| Repository | Status | Notes |
|---|---|---|
| OpenSolar | dirty | Many existing modified/untracked files were present before this continuation slice. Do not reset or overwrite them. |
| Native AutoSci | dirty | Treat as read-only behavioral oracle. Do not modify it. |

## Baseline Commands

| Command | Result |
|---|---|
| `bash harness/solar-harness.sh context inject --query 'AutoSci Solar native full parity first slice scheduler runtime gate registry audit' --format markdown` | warn: context returned with `mirage:nonzero` degraded source. |
| `git branch --show-current` | ok: `feature/autosci-solar-native`. |
| `git rev-parse HEAD` | ok: `721e6eee4eff39cd3a35cf7d240a67f2d493864f`. |
| `git -C /Users/jamesyuan/Developer/Github Repos (On Git)/AutoSci rev-parse HEAD` | ok: `71469e89eb1381e557661da0b90c0585c48288d7`. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest harness/plugins/autosci/tests -q` | error: 121 passed, 7 failed. |
| `env PYTHONPATH=harness .venv/bin/python -m pytest tests/harness/evaluators/scientific -q` | ok: 54 passed. |
| `.venv/bin/python harness/plugins/autosci/bin/autosci_parity_bridge.py inventory --out /tmp/autosci-parity-baseline.json` | ok: 28 native, 28 routed, 0 missing, 0 full, 17 partial, 11 gated. |
| `python3 harness/lib/architecture_guard.py validate --graph harness/workflows/scientific_research_lifecycle_full_v1.json --strict` | ok: graph structure passed architecture guard. |
| `python3 harness/lib/architecture_guard.py validate --graph harness/workflows/scientific_research_resume_v1.json --strict` | ok: graph structure passed architecture guard. |
| `python3 -m json.tool harness/config/logical-operators.json` | ok: JSON parses. |
| `python3 -m json.tool harness/config/physical-operators.json` | ok: JSON parses. |
| `python3 -m json.tool harness/config/actor-hosts.json` | ok: JSON parses. |
| `python3 -m json.tool harness/plugins/autosci/config/feature_parity_routes.v1.json` | ok: JSON parses. |
| `python3 -m json.tool harness/plugins/autosci/config/feature_operator_bindings.v1.json` | ok: JSON parses. |

## Test Failure Baseline

| Area | Status | Evidence |
|---|---|---|
| Novelty Review LLM default | error | Five `test_autosci_skill_shim.py` failures expect Review LLM status `unavailable`, but current shim triggers provider mode and returns `failed`. |
| Local provider socket tests | warn | Two tests fail under this sandbox because binding `127.0.0.1:0` is not permitted. |

## Current Parity Counts

| Semantic route status | Count |
|---|---:|
| full | 0 |
| partial | 17 |
| gated | 11 |
| missing | 0 |

## First-Slice Defects To Address

| Defect | Status | Required repair |
|---|---|---|
| Route status is one-dimensional | pending | Add `semantic_parity`, `execution_policy`, `proof_level`, `proof_refs`, and `remaining_requirements`. |
| Lifecycle gate mixes graph contract and runtime acceptance | pending | Split contract and runtime gate behavior; runtime gate must reject empty/missing result maps. |
| Scheduler binding chain is unaudited | pending | Add deterministic registry audit across workflow, logical binding, physical operator, host, action, schema, and gate. |
| Local AutoSci backend host is not explicit | pending | Add/validate a real local command host supported by operator runtime. |
| `$research` is not scheduler-native | pending | Replace bridge-owned lifecycle execution with graph submission in later slice. |

## Baseline Limitation

This baseline does not prove full parity. It establishes the starting point for
the first continuation slice and records the current failures before code
changes.
