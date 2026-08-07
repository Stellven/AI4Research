# Adaptive Routing and Retrieval Repair Log

## Scope

- Branch: `codex/known-issues-adaptive-routing`
- Baseline: `4b5af751956f8ef1d2eb6bbce8baf9088e694d00`
- Repair area:
  - `harness/lib/advanced_ai4rnd/routing/`
  - `harness/lib/advanced_ai4rnd/retrieval/`
  - `harness/lib/advanced_ai4rnd/evaluation/`
  - `tests/repairs/adaptive_routing/`

## Result

`PASS`

The repair adds deterministic CPU-only stateful implementations for adaptive
model routing, judge calibration, reward modeling, retrieval learning,
Self-RAG, and reranker training.  No live model provider, network call, model
download, optimizer worker, or training worker path is required.

## Implemented Evidence

1. Adaptive routing no longer returns a fixed model.  It scores legal candidate
   models from task semantics, cost estimate, persisted historical feedback,
   and policy constraints.
2. Bayesian/bandit feedback updates persisted alpha/beta posterior state and
   changes later model probabilities and selected route.
3. Cost-aware routing records both quality and cost constraints in the decision
   scorecard, usage estimate, and provenance ledger.
4. Policy violations fail closed with an auditable violation payload instead of
   dispatching a blocked model.
5. Judge calibration uses an explicit held-out fixture and writes calibration
   evidence with before/after MAE.
6. Reward modeling writes and reloads a trainable reference artifact whose
   weights update from deterministic examples.
7. Memory/retrieval learning writes boosts into persistent retrieval state and
   changes later retrieval order after restart.
8. Self-RAG exposes retrieve, critique, and revise steps with citations and
   provenance.
9. The reranker trains and reloads real scoring state, changing order from the
   original ranking.
10. Model usage audit evidence records selected model, token estimate,
    cost estimate, policy, decision id, feedback, and state digest.

## Test Evidence

Command:

```powershell
& 'C:\Users\j50058254\Desktop\Github repo\OpenSolar-Canonical\.venv\Scripts\python.exe' -m pytest tests/repairs/adaptive_routing -vv --basetemp .codex-tmp/pytest-adaptive-routing -o cache_dir=.codex-tmp/pytest-cache-adaptive-routing
```

Result:

```text
8 passed in 0.13s
```

Notes:

- First attempt used system Python and did not execute tests because `pytest`
  was not installed there.
- Second attempt failed before test setup because `.codex-tmp` did not exist
  for pytest `--basetemp`.
- Final accepted run used the repository's existing virtual environment from
  the original worktree and wrote all temp/cache data into this repair
  worktree.

## Limitations

- These modules are local decision, evidence, and learning primitives.  They do
  not dispatch live provider calls.
- The reward model and reranker are intentionally tiny deterministic linear
  fixtures for repair coverage; they are not large-model training pipelines.
