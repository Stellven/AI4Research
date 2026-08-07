from evaluators.scientific import graph_update_gate


def _payload(edge):
    return {
        "schema": "research_graph_update.v1",
        "task_id": "task-graph",
        "sprint_id": "sprint-graph",
        "node_id": "node-graph",
        "status": "completed",
        "inputs": {},
        "outputs": {"edges": [edge]},
        "artifacts": [],
        "provenance": {
            "operator_id": "test",
            "implementation_package": "test",
            "timestamp": "2026-06-24T00:00:00Z",
        },
        "limitations": ["test graph payload"],
    }


def test_graph_update_gate_accepts_evidence_linked_edge():
    result = graph_update_gate.evaluate(
        _payload(
            {
                "source": "paper:skillgen",
                "target": "concept:generated-skills",
                "relation": "supports",
                "operation": "propose",
                "evidence_ids": ["paper:skillgen"],
            }
        )
    )

    assert result.ok is True
    assert result.status == "passed"
    assert result.reasons == []


def test_graph_update_gate_rejects_ungrounded_or_destructive_edge():
    result = graph_update_gate.evaluate(
        _payload(
            {
                "source": "paper:skillgen",
                "target": "",
                "relation": "supports",
                "operation": "remove",
                "evidence_ids": [],
            }
        )
    )

    assert result.ok is False
    assert result.status == "failed"
    joined = " ".join(result.reasons)
    assert "target" in joined
    assert "evidence_ids" in joined
    assert "approval_ref" in joined
