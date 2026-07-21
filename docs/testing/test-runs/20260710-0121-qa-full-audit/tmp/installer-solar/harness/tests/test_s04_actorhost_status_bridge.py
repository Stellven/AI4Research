#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


mts = _load_module("multi_task_status", LIB / "multi_task_status.py")
gnd = _load_module("graph_node_dispatcher", LIB / "graph_node_dispatcher.py")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_actorhost_resolver_uses_actor_hosts_primary(tmp_path: Path) -> None:
    actors = tmp_path / "agent-actors.json"
    hosts = tmp_path / "actor-hosts.json"
    physical = tmp_path / "physical-operators.json"
    leases = tmp_path / "actor-leases"
    _write_json(actors, {
        "actors": {
            "actor-a": {
                "host_id": "mini",
                "role": "builder",
                "capability_profile": {"code_impl": 5, "testing": 4},
            }
        }
    })
    _write_json(hosts, {"hosts": {"mini": {"host_type": "claude_code_session"}}})
    _write_json(physical, {
        "operators": {
            "actor-a": {
                "pane": "solar-harness-lab:*",
                "compat_maps_to": {"host_type": "tmux_pane"},
            }
        }
    })
    _write_json(leases / "actor-a.json", {"state": "leased", "expires_at": "2099-01-01T00:00:00Z"})

    result = mts.resolve_actorhost_status(
        actor_id="actor-a",
        pane="solar-harness-lab:0.0",
        actors_path=actors,
        hosts_path=hosts,
        physical_operators_path=physical,
        lease_dir=leases,
        required_capabilities=["code_impl", "browser_use"],
    )

    assert result["resolution_source"] == "actor_hosts"
    assert result["actor_id"] == "actor-a"
    assert result["host_id"] == "mini"
    assert result["host_type"] == "claude_code_session"
    assert result["lease_state"] == "leased"
    assert result["compat_fallback"] is False
    assert result["capability_match"]["matched"] == ["code_impl"]
    assert result["capability_match"]["missing"] == ["browser_use"]


def test_actorhost_resolver_requires_explicit_compat_fallback(tmp_path: Path) -> None:
    actors = tmp_path / "agent-actors.json"
    hosts = tmp_path / "actor-hosts.json"
    physical = tmp_path / "physical-operators.json"
    _write_json(actors, {"actors": {}})
    _write_json(hosts, {"hosts": {}})
    _write_json(physical, {
        "operators": {
            "legacy-op": {
                "pane": "solar-harness-lab:*",
                "compat_maps_to": {"host_type": "tmux_pane", "carrier_hint": {"tmux_pane_meta": {"role": "builder"}}},
            },
            "ignored-op": {"pane": "solar-harness-lab:*"},
        }
    })

    result = mts.resolve_actorhost_status(
        pane="solar-harness-lab:0.2",
        actors_path=actors,
        hosts_path=hosts,
        physical_operators_path=physical,
    )

    assert result["resolution_source"] == "physical_operators.compat_maps_to"
    assert result["actor_id"] == "legacy-op"
    assert result["host_type"] == "tmux_pane"
    assert result["compat_fallback"] is True
    assert result["canonical_host_type"] is True


def test_worker_discovery_surfaces_actorhost_fields(monkeypatch) -> None:
    monkeypatch.setattr(
        gnd.subprocess,
        "check_output",
        lambda *a, **kw: b"solar-harness-lab:0.0\tBuilder | model:Spark\n",
    )
    monkeypatch.setattr(gnd, "read_lease", lambda pane: None)
    monkeypatch.setattr(gnd, "_pane_cooldown_reason", lambda pane: "")
    monkeypatch.setattr(gnd, "_clear_stale_prompt_residue", lambda pane: False)
    monkeypatch.setattr(gnd, "_pane_unavailable_reason", lambda pane: "")
    monkeypatch.setattr(gnd, "_pane_runtime_unavailable_reason", lambda pane, title="": "")
    monkeypatch.setattr(gnd, "_pane_tui_busy", lambda pane: False)
    monkeypatch.setattr(gnd, "_pane_health", lambda pane: {})
    monkeypatch.setattr(gnd, "_pane_current_command", lambda pane: "codex")
    monkeypatch.setattr(gnd, "_builder_operator_pool_workers", lambda *a, **kw: [])
    monkeypatch.setattr(
        gnd,
        "resolve_actorhost_status",
        lambda **kw: {
            "actor_id": "spark-1",
            "host_id": "mini",
            "host_type": "claude_code_session",
            "lease_state": "idle",
            "capability_match": {"required": kw.get("required_capabilities", []), "matched": ["harness.status"], "missing": [], "observed": ["harness.status"]},
            "compat_fallback": False,
            "compat_maps_to": None,
            "resolution_source": "actor_hosts",
            "canonical_host_type": True,
        },
    )

    workers = gnd._discover_workers(dry_run=False)

    assert workers[0]["actor_id"] == "spark-1"
    assert workers[0]["host_id"] == "mini"
    assert workers[0]["host_type"] == "claude_code_session"
    assert workers[0]["lease_state"] == "idle"
    assert workers[0]["actorhost"]["resolution_source"] == "actor_hosts"


def test_operator_pool_dispatch_result_surfaces_selected_actorhost(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(gnd, "HARNESS_DIR", tmp_path)
    monkeypatch.setattr(gnd, "SPRINTS_DIR", tmp_path / "sprints")
    monkeypatch.setattr(gnd, "_builder_operator_pool_enabled", lambda: True)
    monkeypatch.setattr(
        gnd.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(
            returncode=0,
            stdout="task_id = pm-1\noperator = mini-codex-gpt53-spark-builder-1\ndispatch = dispatch.json\n",
            stderr="",
        ),
    )
    monkeypatch.setattr(
        gnd,
        "resolve_actorhost_status",
        lambda **kw: {
            "actor_id": kw.get("actor_id") or "mini-codex-gpt53-spark-builder-1",
            "host_id": "mini",
            "host_type": "claude_code_session",
            "lease_state": "idle",
            "capability_match": {"required": kw.get("required_capabilities", []), "matched": [], "missing": [], "observed": []},
            "compat_fallback": False,
            "compat_maps_to": None,
            "resolution_source": "actor_hosts",
            "canonical_host_type": True,
        },
    )

    result = gnd._submit_builder_to_operator_pool(
        item={"payload": {}},
        payload={},
        sid="sprint-test",
        node={"id": "N2", "required_capabilities": ["harness.status"]},
        node_id="N2",
        graph_path=str(tmp_path / "sprint-test.task_graph.json"),
        pane="operator-pool:builder.0",
        dispatch_id="dispatch-1",
        dry_run=True,
    )

    assert result["ok"] is True
    assert result["actor_id"] == "mini-codex-gpt53-spark-builder-1"
    assert result["host_id"] == "mini"
    assert result["host_type"] == "claude_code_session"
    assert result["lease_state"] == "idle"
    assert result["actorhost"]["resolution_source"] == "actor_hosts"
