"""Distinct reference implementations for advanced optimization algorithms."""

from __future__ import annotations

from typing import Any, Mapping

from .core import (
    OptimizationProblem,
    ReferenceOptimizer,
    add_keyword,
    best_discriminating_token,
    clone_candidate,
    evaluate_candidate,
    failed_predictions,
    _softmax,
    _stable_random,
)


class MIPROv2Optimizer(ReferenceOptimizer):
    mechanism = "bootstrapped_prompt_demo_search"

    def propose(
        self,
        problem: OptimizationProblem,
        state: Mapping[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        failures = failed_predictions(state["current_evaluation"])
        pool = []
        for offset, failure in enumerate(failures[:2] or [self.failed_or_hardest(problem, state)]):
            row = problem.dataset[failure["index"]]
            token = best_discriminating_token(problem, label=row["label"], text=row["text"])
            candidate = clone_candidate(state["current_candidate"])
            candidate["instruction"] = (
                "Predict labels using bootstrapped demonstrations and high-signal keywords."
            )
            candidate.setdefault("demos", []).append(
                {"text_hash": failure["text_hash"], "label": row["label"], "keyword": token}
            )
            add_keyword(candidate, row["label"], token, weight=1.0 + (0.1 * offset))
            evaluation = evaluate_candidate(problem, candidate)
            pool.append({"token": token, "label": row["label"], "candidate": candidate, "evaluation": evaluation})
        selected = max(pool, key=lambda item: item["evaluation"]["objective"])
        return selected["candidate"], {
            "mechanism": self.mechanism,
            "candidate_pool": [
                {
                    "label": item["label"],
                    "token": item["token"],
                    "objective": item["evaluation"]["objective"],
                }
                for item in pool
            ],
            "selected_token": selected["token"],
            "demo_count": len(selected["candidate"].get("demos", [])),
        }


class TextGradOptimizer(ReferenceOptimizer):
    mechanism = "textual_gradient_keyword_update"

    def propose(
        self,
        problem: OptimizationProblem,
        state: Mapping[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        failure = self.failed_or_hardest(problem, state)
        row = problem.dataset[failure["index"]]
        token = best_discriminating_token(
            problem,
            label=row["label"],
            text=row["text"],
            avoid_labels=[failure["predicted"]],
        )
        candidate = clone_candidate(state["current_candidate"])
        add_keyword(candidate, row["label"], token, weight=1.25)
        predicted_rules = candidate.setdefault("keyword_rules", {}).setdefault(failure["predicted"], {})
        if token in predicted_rules:
            predicted_rules[token] = round(float(predicted_rules[token]) - 0.5, 6)
        candidate["instruction"] = (
            f"Textual gradient: missed label {row['label']}; emphasize token {token}."
        )
        candidate.setdefault("policy", {})["last_gradient"] = {
            "failed_index": failure["index"],
            "target_label": row["label"],
            "predicted_label": failure["predicted"],
            "positive_token": token,
        }
        return candidate, {
            "mechanism": self.mechanism,
            "gradient": candidate["policy"]["last_gradient"],
        }


class AFlowOptimizer(ReferenceOptimizer):
    mechanism = "workflow_graph_mutation_search"

    def propose(
        self,
        problem: OptimizationProblem,
        state: Mapping[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        failure = self.failed_or_hardest(problem, state)
        row = problem.dataset[failure["index"]]
        token = best_discriminating_token(problem, label=row["label"], text=row["text"])
        label_token = f"label:{row['label']}"
        candidate = clone_candidate(state["current_candidate"])
        graph = candidate.setdefault("graph", [])
        node = {
            "id": f"aflow-node-{len(graph) + 1}",
            "kind": "inject_label_token",
            "match_terms": [token],
            "token": label_token,
            "emits_label": row["label"],
        }
        graph.append(node)
        add_keyword(candidate, row["label"], label_token, weight=1.5)
        candidate.setdefault("policy", {})["graph_execution"] = "sequential_token_injection"
        return candidate, {
            "mechanism": self.mechanism,
            "added_node": node,
            "graph_nodes": len(graph),
        }


class MCTSOptimizer(ReferenceOptimizer):
    mechanism = "uct_tree_search"

    def propose(
        self,
        problem: OptimizationProblem,
        state: Mapping[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        candidate = clone_candidate(state["current_candidate"])
        tree = candidate.setdefault("tree", {"nodes": [], "edges": []})
        failures = failed_predictions(state["current_evaluation"]) or [self.failed_or_hardest(problem, state)]
        actions = []
        for failure in failures:
            row = problem.dataset[failure["index"]]
            token = best_discriminating_token(problem, label=row["label"], text=row["text"])
            actions.append({"label": row["label"], "token": token, "source_index": failure["index"]})

        rng = _stable_random(int(state["seed"]), "mcts", int(state["step"]))
        scored_actions = []
        parent_visits = 1 + sum(node.get("visits", 0) for node in tree["nodes"])
        for action in actions:
            prior = rng.random() * 0.01
            visits = sum(
                node.get("visits", 0)
                for node in tree["nodes"]
                if node.get("action", {}).get("token") == action["token"]
            )
            value = sum(
                node.get("value", 0.0)
                for node in tree["nodes"]
                if node.get("action", {}).get("token") == action["token"]
            )
            exploitation = value / visits if visits else 0.0
            exploration = (2.0 * (parent_visits ** 0.5)) / (1 + visits)
            scored_actions.append((exploitation + exploration + prior, action))
        scored_actions.sort(key=lambda item: item[0], reverse=True)
        selected = scored_actions[0][1]
        add_keyword(candidate, selected["label"], selected["token"], weight=1.0)
        rollout = evaluate_candidate(problem, candidate)
        node_id = f"mcts-{len(tree['nodes']) + 1}"
        node = {
            "id": node_id,
            "action": selected,
            "visits": 1,
            "value": rollout["objective"],
        }
        tree["nodes"].append(node)
        if len(tree["nodes"]) > 1:
            tree["edges"].append({"from": tree["nodes"][-2]["id"], "to": node_id})
        candidate.setdefault("policy", {})["tree_policy"] = "uct"
        return candidate, {
            "mechanism": self.mechanism,
            "selection_path": [tree["nodes"][-2]["id"]] if len(tree["nodes"]) > 1 else ["root"],
            "expanded_action": selected,
            "rollout_objective": rollout["objective"],
            "backpropagated_node": node,
        }


class ADASOptimizer(ReferenceOptimizer):
    mechanism = "agent_design_population_search"

    def propose(
        self,
        problem: OptimizationProblem,
        state: Mapping[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        base = clone_candidate(state["current_candidate"])
        failure = self.failed_or_hardest(problem, state)
        row = problem.dataset[failure["index"]]
        token = best_discriminating_token(problem, label=row["label"], text=row["text"])
        population = []
        for role, weight in (("specialist", 1.2), ("critic", 0.9)):
            candidate = clone_candidate(base)
            agent = {
                "id": f"adas-{role}-{len(candidate.get('agents', [])) + 1}",
                "role": role,
                "keyword_rules": {row["label"]: {token: weight}},
                "created_from_failure": failure["index"],
            }
            candidate.setdefault("agents", []).append(agent)
            candidate.setdefault("policy", {})["agent_voting"] = "weighted_keyword_vote"
            evaluation = evaluate_candidate(problem, candidate)
            population.append({"agent": agent, "candidate": candidate, "evaluation": evaluation})
        selected = max(population, key=lambda item: item["evaluation"]["objective"])
        return selected["candidate"], {
            "mechanism": self.mechanism,
            "mutations": [
                {
                    "agent_id": item["agent"]["id"],
                    "role": item["agent"]["role"],
                    "objective": item["evaluation"]["objective"],
                }
                for item in population
            ],
            "selected_agent": selected["agent"],
        }


class CEGISOptimizer(ReferenceOptimizer):
    mechanism = "counterexample_guided_synthesis"

    def propose(
        self,
        problem: OptimizationProblem,
        state: Mapping[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        failure = self.failed_or_hardest(problem, state)
        row = problem.dataset[failure["index"]]
        token = best_discriminating_token(problem, label=row["label"], text=row["text"])
        candidate = clone_candidate(state["current_candidate"])
        counterexamples = candidate.setdefault("counterexamples", [])
        counterexample = {
            "index": failure["index"],
            "expected": row["label"],
            "observed": failure["predicted"],
            "text_hash": failure["text_hash"],
        }
        counterexamples.append(counterexample)
        constraint = {
            "if_token_present": token,
            "then_label": row["label"],
            "source_counterexample": failure["index"],
        }
        candidate.setdefault("constraints", []).append(constraint)
        add_keyword(candidate, row["label"], token, weight=1.4)
        candidate.setdefault("policy", {})["synthesis"] = "counterexample_constraints"
        return candidate, {
            "mechanism": self.mechanism,
            "counterexample": counterexample,
            "synthesized_constraint": constraint,
            "counterexample_count": len(counterexamples),
        }
