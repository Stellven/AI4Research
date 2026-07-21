#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import unified_selector as selector


def test_round_robin_policy_uses_persistent_cursor(monkeypatch):
    recorded: list[tuple[str, str, str]] = []
    monkeypatch.setattr(selector, "round_robin_start_index", lambda operator_type, count: 1)
    monkeypatch.setattr(
        selector,
        "record_selection",
        lambda operator_type, actor_id, selection_policy="": recorded.append((operator_type, actor_id, selection_policy)),
    )

    selected, rejected = selector.select_bound_candidate(
        [
            {"actor_id": "actor-one", "priority": 1},
            {"actor_id": "actor-two", "priority": 2},
        ],
        selection_policy="round_robin",
        operator_type="DeepArchitect",
    )

    assert selected == "actor-two"
    assert rejected == []
    assert recorded == [("DeepArchitect", "actor-two", "round_robin")]


def test_least_loaded_policy_prefers_lower_runtime_snapshot(monkeypatch):
    monkeypatch.setattr(
        selector,
        "actor_load_snapshot",
        lambda actor_id: {
            "actor-busy": {"active_lease_count": 1, "selection_count": 5, "last_selected_at": "2026-05-27T18:00:00Z"},
            "actor-free": {"active_lease_count": 0, "selection_count": 1, "last_selected_at": "2026-05-27T17:00:00Z"},
        }[actor_id],
    )
    monkeypatch.setattr(selector, "record_selection", lambda *args, **kwargs: None)

    selected, rejected = selector.select_bound_candidate(
        [
            {"actor_id": "actor-busy", "priority": 1},
            {"actor_id": "actor-free", "priority": 2},
        ],
        selection_policy="least_loaded",
        operator_type="ResearchScout",
        actor_registry={
            "actor-busy": {"actor_id": "actor-busy"},
            "actor-free": {"actor_id": "actor-free"},
        },
    )

    assert selected == "actor-free"
    assert rejected == []
