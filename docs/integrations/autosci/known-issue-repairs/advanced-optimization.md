# Advanced Optimization Known-Issue Repair

## Scope

This repair adds CPU-only reference execution for:

- MIPROv2
- TextGrad
- AFlow
- MCTS
- ADAS
- CEGIS

The implementation lives under `harness/lib/advanced_ai4rnd/optimization/` and is intentionally reference-only. It does not claim production integration with DSPy, TextGrad, or any large-model runtime.

## Unified Interface

`run_reference_optimizer(algorithm, problem, run_dir, seed, run_id, resume_from, interrupt_after_steps, fail_once_steps)` is the shared entrypoint. It validates a small text-classification dataset, evaluates an initial candidate, runs the selected optimizer, writes checkpoints after each step, and records observable artifacts:

- `dataset.json`
- `optimizer_graph.json`
- `trace.json`
- `policy.json`
- `evaluation.json`
- `checkpoint.json`
- `result.json`

The common result compares `baseline_objective` and `best_objective`. A run is reported as `passed` only when the best objective improves over the initial candidate. A completed run with no objective improvement is `completed_no_improvement` with `result_state: NOT_SUCCESS`.

## Algorithm Differences

MIPROv2 performs bootstrapped prompt/demo search. Each step builds a small candidate pool from failed examples, adds a demonstration and a high-signal keyword, evaluates the pool, and selects the best candidate.

TextGrad performs textual-gradient updates. It inspects a failed prediction, records a gradient summary, emphasizes a discriminating token for the target label, and can demote conflicting evidence.

AFlow mutates an explicit workflow graph. It adds graph nodes that inject label tokens when matching terms are observed, then evaluates the resulting graph-backed policy.

MCTS performs deterministic tree search. It selects candidate actions with a UCT-style score, expands a node, evaluates a rollout, and stores backpropagated value/visit data.

ADAS evolves an agent-design population. It creates role-specific agent mutations, evaluates the population, and selects the best agent policy.

CEGIS performs counterexample-guided synthesis. It records failed examples as counterexamples, synthesizes constraints from them, and updates the rule policy until the fixture is solved or the budget ends.

## Resume And Recovery

Every step writes `checkpoint.json`. A run can return `interrupted` after a requested step and later resume from that checkpoint. The same input and seed produce the same best candidate and objective as an uninterrupted run.

Failure recovery is covered with a fail-once injection. The first run records `recoverable_failed`; resuming from its checkpoint skips the already-seen injected failure and completes normally.

## Capability Metadata

`CAPABILITY_METADATA` marks all six algorithms as:

- `reference_status: implemented`
- `production_status: reference_only`
- L2 coverage: optimizer graph, dataset, trace, policy, evaluation

Optional dependencies are gates, not hidden requirements. MIPROv2 declares `dspy`; TextGrad declares `textgrad`; the reference path remains open without either package.

The worker-scoped capsule is `harness/config/capability-capsules/cap.advanced-optimization-reference-worker.yaml`.
