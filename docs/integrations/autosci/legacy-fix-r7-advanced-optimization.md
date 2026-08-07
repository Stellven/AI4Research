# Legacy Fix R7 Advanced Optimization

Baseline: `6a96d40153b919d97a2018c8267d7796d5e3e1d5`

Branch: `codex/legacy-fix-r7-advanced`

Worktree: `C:/Users/j50058254/Desktop/Github repo/.legacy-fix-worktrees/r7-advanced`

## Scope

This pass adds one executable advanced optimizer/trainer contract without
editing the Phase 22 ledger, reports, workbook, or GitHub state.

The implementation reuses existing Solar harness surfaces:

- TaskGraph runtime state: `harness/lib/task_graph_state_io.py`
- Evidence ledger: `harness/lib/evidence_ledger.py`
- Model registry resolution: `harness/lib/model_registry.py`
- Existing GEPA integration remains under `harness/integrations/gepa_optimizer/`

## FULLY_IMPLEMENTED

### Unified optimizer/trainer operator contract

Entrypoint: `harness/lib/advanced_ai4rnd_operator.py`

Implemented behavior:

- accepts an executable operator envelope with `operator_kind`, `algorithm`,
  `inputs`, `parameters`, `sprint_id`, `node_id`, and `artifact_root`;
- writes TaskGraph runtime state only, not TaskGraph spec;
- records input hash, parameters, metrics, artifact paths, output hash, and
  failure/unsupported state on the TaskGraph node result;
- writes an append-only evidence ledger entry with verification results;
- returns explicit `unsupported` for algorithms that do not have a real
  implementation.

### Bayesian optimization reference implementation

Algorithm: `bayesian_optimization`

Implemented behavior:

- runs a real local objective over a bounded numeric search space;
- performs multiple sequential updates;
- fits a tiny Gaussian-process surrogate with an RBF kernel;
- selects unevaluated points by expected improvement;
- writes `optimizer_result.json` and `artifact_graph.json`;
- records before/after score metrics and output hash.

Evidence from tests:

- `test_bayesian_optimizer_runs_real_objective_and_records_taskgraph` asserts
  score improvement, multiple evaluated points, TaskGraph node state, artifact
  graph, output hash, and evidence ledger.

### CPU-safe SFT adapter reference workflow

Algorithm: `sft_linear_adapter`

Implemented behavior:

- validates dataset rows and dataset license;
- resolves the base model through the existing model registry;
- trains a bag-of-words softmax adapter on CPU with gradient descent;
- produces a versioned adapter artifact under `model_versions/`;
- writes training manifest, dataset hash, model version id, metrics, lineage,
  and artifact graph;
- records TaskGraph node metrics and output hash.

Evidence from tests:

- `test_sft_linear_adapter_trains_versioned_artifact_with_lineage` asserts
  actual holdout improvement over a baseline classifier, versioned adapter
  artifact, manifest hash, dataset/model lineage, artifact graph, and TaskGraph
  state.

### GEPA Windows-focused regression hardening

Existing GEPA integration was preserved and made runnable on this Windows
worktree:

- `harness/integrations/gepa_optimizer/evaluator.py` now treats the Unix-only
  `resource` module as optional and disables `preexec_fn` on Windows.
- `harness/integrations/gepa_optimizer/operator_router.py` falls back to the
  repo `harness/config/physical-operators.json` when user-home harness config
  is absent.
- `harness/integrations/gepa_optimizer/cli.py` uses `os.sep` for resolved
  `/tmp` safety checks.
- `harness/tests/integrations/gepa_optimizer/test_promote.py` uses
  platform-native path resolution for the `/tmp` acceptance test.

## PARTIAL

### Dataset management

Implemented for the new executable trainer workflow:

- dataset hash;
- license validation;
- train/holdout split tracking;
- lineage from dataset to model version;
- metrics bound to the resulting adapter artifact.

Not a full repository-wide dataset graph service.

### Policy/model graph management

Implemented as per-run artifact graphs:

- Bayesian optimizer emits a routing policy candidate node;
- SFT adapter emits dataset, base-model, and model-version nodes;
- lineage edges are written and tested.

Not a global policy/model graph service or promotion registry.

### Evaluator/reward contracts, judge calibration, reward modeling, CEGIS

The new contract records metrics, failure states, evidence, and lineage, and it
keeps unsupported algorithms explicit. Dedicated judge calibration,
reward-model training, and CEGIS synthesis remain unavailable.

### GEPA

Existing GEPA artifact optimization remains the shipped GEPA surface. This pass
does not claim a new live GEPA run because the assignment required no large
downloads, no global cache use, and CPU-safe foundations.

## STILL_NOT_AVAILABLE

These algorithms now return explicit `unsupported`/`STILL_NOT_AVAILABLE` from
the advanced operator contract unless another existing subsystem handles them.
They are not marked as implemented by the Bayesian optimizer or SFT adapter:

- MIPROv2
- TextGrad
- Bandit routing
- Cost-aware RL
- AFlow
- MCTS
- ADAS
- LoRA
- DPO
- GRPO
- Agent RL
- Judge calibration
- Reward modeling
- CEGIS
- Memory/retrieval learning
- Self-RAG
- Reranker training

## Verification

Local venv: `.codex-tmp/r7-advanced-venv`

Installed lightweight dependency:

- `pytest 9.1.1`

Commands run:

```powershell
& '.codex-tmp\r7-advanced-venv\Scripts\python.exe' -m pytest harness\tests\test_advanced_ai4rnd_operator.py -q --basetemp .codex-tmp\pytest-r7-advanced-new
```

Result: `3 passed`

```powershell
& '.codex-tmp\r7-advanced-venv\Scripts\python.exe' -m pytest harness\tests\test_advanced_ai4rnd_operator.py harness\tests\integrations\gepa_optimizer harness\tests\graph\test_task_graph_state_io.py -q --basetemp .codex-tmp\pytest-r7-advanced-all-focused2
```

Result: `151 passed, 24 warnings`

```powershell
& '.codex-tmp\r7-advanced-venv\Scripts\python.exe' -m pytest harness\tests\test_model_registry_codex_aliases.py harness\tests\runtime\test_logical_operator_router.py -q --basetemp .codex-tmp\pytest-r7-advanced-registry
```

Result: `22 passed`

Known warning:

- Existing GEPA artifact-store tests emit `DeprecationWarning` for
  `datetime.datetime.utcnow()`. No failure.
