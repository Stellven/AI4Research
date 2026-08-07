"""Capability metadata for advanced optimization reference algorithms."""

from __future__ import annotations

CAPABILITY_METADATA: dict[str, dict[str, object]] = {
    "miprov2": {
        "display_name": "MIPROv2",
        "reference_status": "implemented",
        "production_status": "reference_only",
        "optional_dependency": "dspy",
        "reference_path": "offline_prompt_demo_search",
        "l2": ["optimizer_graph", "dataset", "trace", "policy", "evaluation"],
        "notes": "CPU-only prompt and bootstrapped demo search; no DSPy runtime is required for the reference path.",
    },
    "textgrad": {
        "display_name": "TextGrad",
        "reference_status": "implemented",
        "production_status": "reference_only",
        "optional_dependency": "textgrad",
        "reference_path": "textual_gradient_keyword_update",
        "l2": ["optimizer_graph", "dataset", "trace", "policy", "evaluation"],
        "notes": "CPU-only textual-gradient updates over failed examples; production TextGrad is optional.",
    },
    "aflow": {
        "display_name": "AFlow",
        "reference_status": "implemented",
        "production_status": "reference_only",
        "optional_dependency": None,
        "reference_path": "workflow_graph_mutation_search",
        "l2": ["optimizer_graph", "dataset", "trace", "policy", "evaluation"],
        "notes": "Mutates an explicit workflow graph with observable node additions.",
    },
    "mcts": {
        "display_name": "MCTS",
        "reference_status": "implemented",
        "production_status": "reference_only",
        "optional_dependency": None,
        "reference_path": "uct_tree_search",
        "l2": ["optimizer_graph", "dataset", "trace", "policy", "evaluation"],
        "notes": "Runs deterministic UCT-style selection, expansion, rollout, and backpropagation.",
    },
    "adas": {
        "display_name": "ADAS",
        "reference_status": "implemented",
        "production_status": "reference_only",
        "optional_dependency": None,
        "reference_path": "agent_design_population_search",
        "l2": ["optimizer_graph", "dataset", "trace", "policy", "evaluation"],
        "notes": "Evolves a population of small agent policies and selects the best scored design.",
    },
    "cegis": {
        "display_name": "CEGIS",
        "reference_status": "implemented",
        "production_status": "reference_only",
        "optional_dependency": None,
        "reference_path": "counterexample_guided_rule_synthesis",
        "l2": ["optimizer_graph", "dataset", "trace", "policy", "evaluation"],
        "notes": "Adds constraints from concrete counterexamples until no violating example remains or budget ends.",
    },
}

