"""Tests for N4 actor observability — status output and monitor bridge."""
import json
import tempfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from multi_task_status import (
    get_actor_status_entry,
    get_host_status_entry,
    load_actor_fleet,
    load_host_fleet,
    get_logical_operator_binding_summary,
    _redact_secrets,
)
from monitor_bridge import build_snapshot


def _make_actors(path):
    actors = {
        "actor-1": {
            "actor_id": "actor-1",
            "host_id": "host-a",
            "role": "planner",
            "enabled": True,
            "capability_profile": {"speed": 3, "code_impl": 4},
            "risk_profile": {
                "allowed_write_scope": "harness",
                "destructive_actions": "denied",
                "git_push": "denied",
            },
            "cost_profile": {
                "cost_tier": "high",
                "token_budget_class": "large",
                "effort": "heavy",
                "reserve_ratio": 0.2,
            },
            "evidence_ledger_ref": {"path": "actors/actor-1/evidence"},
            "context_packet_ref": {"path": None, "packet_id": None},
        },
        "actor-2": {
            "actor_id": "actor-2",
            "host_id": "host-b",
            "role": "runner",
            "enabled": True,
            "capability_profile": {"speed": 5, "code_impl": 3},
            "risk_profile": {
                "allowed_write_scope": "harness",
                "destructive_actions": "denied",
                "git_push": "allowed",
            },
            "cost_profile": {
                "cost_tier": "low",
                "token_budget_class": "small",
                "effort": "light",
                "reserve_ratio": 0.0,
            },
            "evidence_ledger_ref": {"path": "actors/actor-2/evidence"},
            "context_packet_ref": {"path": "pkt-42", "packet_id": "pkt-42"},
        },
    }
    Path(path).write_text(json.dumps({"actors": actors}))
    return actors


def _make_hosts(path):
    hosts = {
        "host-a": {
            "host_id": "host-a",
            "host_type": "mac_mini",
            "display_name": "Mac mini A",
            "lifecycle": {
                "state": "online",
                "started_at": "2026-05-23T00:00:00Z",
                "last_seen_at": "2026-05-23T12:00:00Z",
                "shutdown_policy": "never",
            },
            "address": {"hostname": "mini-a.local"},
            "heartbeat": {"interval_sec": 30},
            "probe": {"last_probe_result": "ok"},
        },
    }
    Path(path).write_text(json.dumps({"hosts": hosts}))
    return hosts


def _make_bindings(path):
    bindings = {
        "DeepArchitect": {
            "operator_type": "DeepArchitect",
            "candidates": [
                {"actor_id": "actor-1", "priority": 1},
                {"actor_id": "actor-2", "priority": 2},
            ],
            "selection_policy": "score",
            "fallback_policy": "next_candidate",
        },
        "TestRunner": {
            "operator_type": "TestRunner",
            "candidates": [{"actor_id": "actor-2", "priority": 1}],
            "selection_policy": "score",
            "fallback_policy": "next_candidate",
        },
    }
    Path(path).write_text(json.dumps({"bindings": bindings}))
    return bindings


def test_actor_status_entry_has_required_fields():
    with tempfile.TemporaryDirectory() as td:
        ap = Path(td) / "actors.json"
        hp = Path(td) / "hosts.json"
        _make_actors(ap)
        hosts = _make_hosts(hp)

        entry = get_actor_status_entry(
            "actor-1",
            json.loads(ap.read_text())["actors"]["actor-1"],
            hosts=hosts,
            lease_dir=Path(td) / "leases",
        )
        assert entry["actor_id"] == "actor-1"
        assert entry["host_id"] == "host-a"
        assert entry["host_type"] == "mac_mini"
        assert entry["lease_state"] == "idle"
        assert entry["billing_pool"] == "high"
        assert entry["evidence_path"] == "actors/actor-1/evidence"
        assert entry["context_packet_id"] == "N/A"
        assert isinstance(entry["capability_summary"], dict)
        assert entry["capability_summary"]["speed"] == 3
        assert isinstance(entry["risk_summary"], dict)
        assert isinstance(entry["cost_summary"], dict)
        print("PASS: actor_status_entry_has_required_fields")


def test_actor_status_with_active_lease():
    with tempfile.TemporaryDirectory() as td:
        ap = Path(td) / "actors.json"
        _make_actors(ap)
        actors = json.loads(ap.read_text())["actors"]

        # Write active lease
        lease_dir = Path(td) / "leases"
        lease_dir.mkdir()
        lease_data = {
            "state": "running",
            "expires_at": "2099-01-01T00:00:00Z",
            "task_id": "t1",
        }
        (lease_dir / "actor-1.json").write_text(json.dumps(lease_data))

        entry = get_actor_status_entry(
            "actor-1", actors["actor-1"], hosts={}, lease_dir=lease_dir,
        )
        assert entry["lease_state"] == "running"
        print("PASS: actor_status_with_active_lease")


def test_stale_actor_lease():
    with tempfile.TemporaryDirectory() as td:
        ap = Path(td) / "actors.json"
        _make_actors(ap)
        actors = json.loads(ap.read_text())["actors"]

        # Write expired lease
        lease_dir = Path(td) / "leases"
        lease_dir.mkdir()
        lease_data = {
            "state": "running",
            "expires_at": "2020-01-01T00:00:00Z",
        }
        (lease_dir / "actor-1.json").write_text(json.dumps(lease_data))

        entry = get_actor_status_entry(
            "actor-1", actors["actor-1"], hosts={}, lease_dir=lease_dir,
        )
        assert entry["lease_state"] == "stale"
        print("PASS: stale_actor_lease")


def test_missing_host():
    with tempfile.TemporaryDirectory() as td:
        ap = Path(td) / "actors.json"
        _make_actors(ap)
        actors = json.loads(ap.read_text())["actors"]

        # actor-2 has host_id="host-b" but no host entry
        entry = get_actor_status_entry(
            "actor-2", actors["actor-2"], hosts={}, lease_dir=Path(td) / "leases",
        )
        assert entry["host_id"] == "host-b"
        assert entry["host_type"] == "unknown"
        assert entry["host_state"] == "unknown"
        print("PASS: missing_host")


def test_degraded_host():
    with tempfile.TemporaryDirectory() as td:
        ap = Path(td) / "actors.json"
        hp = Path(td) / "hosts.json"
        _make_actors(ap)
        hosts = _make_hosts(hp)

        # Mark host-a as degraded
        hosts["host-a"]["lifecycle"]["state"] = "degraded"

        actors = json.loads(ap.read_text())["actors"]
        entry = get_actor_status_entry(
            "actor-1", actors["actor-1"], hosts=hosts, lease_dir=Path(td) / "leases",
        )
        assert entry["host_state"] == "degraded"
        print("PASS: degraded_host")


def test_host_status_entry():
    with tempfile.TemporaryDirectory() as td:
        hp = Path(td) / "hosts.json"
        hosts = _make_hosts(hp)

        entry = get_host_status_entry("host-a", hosts["host-a"])
        assert entry["host_id"] == "host-a"
        assert entry["host_type"] == "mac_mini"
        assert entry["state"] == "online"
        assert entry["hostname"] == "mini-a.local"
        assert entry["heartbeat_interval_sec"] == 30
        print("PASS: host_status_entry")


def test_no_secrets_emitted():
    with tempfile.TemporaryDirectory() as td:
        ap = Path(td) / "actors.json"
        _make_actors(ap)
        actors = json.loads(ap.read_text())["actors"]

        entry = get_actor_status_entry(
            "actor-1", actors["actor-1"], hosts={}, lease_dir=Path(td) / "leases",
        )
        text = json.dumps(entry)
        # These patterns must never appear in output (raw secret values)
        for secret_pattern in [
            '"api_key"', '"secret"', '"password"', '"cookie"', '"raw_key"',
            '"credential"', '"private_key"', '"access_token"', '"bearer"',
            "sk-", "session_key",
        ]:
            assert secret_pattern not in text.lower(), f"Secret pattern '{secret_pattern}' found in output"
        print("PASS: no_secrets_emitted")


def test_redact_secrets():
    dirty = {
        "name": "test",
        "api_key": "sk-12345",
        "access_token": "abc",
        "nested": {
            "secret": "hidden",
            "safe_field": 42,
        },
        "items": [
            {"password": "x", "ok": True},
        ],
    }
    clean = _redact_secrets(dirty)
    assert "api_key" not in clean
    assert "access_token" not in clean
    assert "secret" not in clean["nested"]
    assert clean["nested"]["safe_field"] == 42
    assert "password" not in clean["items"][0]
    assert clean["items"][0]["ok"] is True
    print("PASS: redact_secrets")


def test_logical_operator_binding_summary():
    with tempfile.TemporaryDirectory() as td:
        bp = Path(td) / "logical-operators.json"
        _make_bindings(bp)

        summary = get_logical_operator_binding_summary(bp)
        assert "DeepArchitect" in summary
        assert summary["DeepArchitect"]["candidates"] == ["actor-1", "actor-2"]
        assert summary["DeepArchitect"]["selection_policy"] == "score"
        assert "TestRunner" in summary
        assert summary["TestRunner"]["candidates"] == ["actor-2"]
        print("PASS: logical_operator_binding_summary")


def test_load_actor_fleet():
    with tempfile.TemporaryDirectory() as td:
        ap = Path(td) / "actors.json"
        hp = Path(td) / "hosts.json"
        _make_actors(ap)
        _make_hosts(hp)

        fleet = load_actor_fleet(ap, hp, lease_dir=Path(td) / "leases")
        assert len(fleet) == 2
        assert "actor-1" in fleet
        assert "actor-2" in fleet
        assert fleet["actor-1"]["host_type"] == "mac_mini"
        print("PASS: load_actor_fleet")


def test_load_host_fleet():
    with tempfile.TemporaryDirectory() as td:
        hp = Path(td) / "hosts.json"
        _make_hosts(hp)

        fleet = load_host_fleet(hp)
        assert len(fleet) == 1
        assert "host-a" in fleet
        assert fleet["host-a"]["host_type"] == "mac_mini"
        print("PASS: load_host_fleet")


def test_monitor_bridge_snapshot():
    with tempfile.TemporaryDirectory() as td:
        ap = Path(td) / "actors.json"
        hp = Path(td) / "hosts.json"
        bp = Path(td) / "bindings.json"
        op = Path(td) / "operators.json"
        _make_actors(ap)
        _make_hosts(hp)
        _make_bindings(bp)
        Path(op).write_text(json.dumps({"operators": {}}))

        snap = build_snapshot(
            operators_path=op,
            actors_path=ap,
            hosts_path=hp,
            logical_ops_path=bp,
            actor_lease_dir=Path(td) / "leases",
        )
        assert snap["schema"] == "solar.monitor_bridge.operator_fleet.v2"
        assert "actor_fleet" in snap
        assert "host_fleet" in snap
        assert "logical_operator_bindings" in snap
        assert "actor_lease_counts" in snap
        assert len(snap["actor_fleet"]) == 2
        assert len(snap["host_fleet"]) == 1
        assert "DeepArchitect" in snap["logical_operator_bindings"]
        print("PASS: monitor_bridge_snapshot")


def test_monitor_bridge_no_secrets():
    with tempfile.TemporaryDirectory() as td:
        ap = Path(td) / "actors.json"
        hp = Path(td) / "hosts.json"
        bp = Path(td) / "bindings.json"
        op = Path(td) / "operators.json"
        _make_actors(ap)
        _make_hosts(hp)
        _make_bindings(bp)
        Path(op).write_text(json.dumps({"operators": {}}))

        snap = build_snapshot(
            operators_path=op,
            actors_path=ap,
            hosts_path=hp,
            logical_ops_path=bp,
            actor_lease_dir=Path(td) / "leases",
        )
        text = json.dumps(snap)
        for secret_pattern in [
            '"api_key"', '"secret"', '"password"', '"cookie"', '"raw_key"',
            '"credential"', '"private_key"', '"access_token"', '"bearer"',
            "sk-", "session_key",
        ]:
            assert secret_pattern not in text.lower()
        print("PASS: monitor_bridge_no_secrets")


def test_evidence_and_context_paths_exposed():
    with tempfile.TemporaryDirectory() as td:
        ap = Path(td) / "actors.json"
        _make_actors(ap)
        actors = json.loads(ap.read_text())["actors"]

        entry = get_actor_status_entry(
            "actor-1", actors["actor-1"], hosts={}, lease_dir=Path(td) / "leases",
        )
        assert entry["evidence_path"] == "actors/actor-1/evidence"
        assert entry["context_packet_id"] == "N/A"

        # actor-2 has a context packet
        entry2 = get_actor_status_entry(
            "actor-2", actors["actor-2"], hosts={}, lease_dir=Path(td) / "leases",
        )
        assert entry2["context_packet_id"] == "pkt-42"
        assert entry2["context_packet_path"] == "pkt-42"
        print("PASS: evidence_and_context_paths_exposed")


def test_capability_token_summary_no_raw():
    with tempfile.TemporaryDirectory() as td:
        ap = Path(td) / "actors.json"
        _make_actors(ap)
        actors = json.loads(ap.read_text())["actors"]

        entry = get_actor_status_entry(
            "actor-1", actors["actor-1"], hosts={}, lease_dir=Path(td) / "leases",
        )
        # capability_token_summary is None by default (no active token)
        assert entry["capability_token_summary"] is None
        # Ensure the key exists but never contains raw token content
        text = json.dumps(entry)
        assert "sk-" not in text
        assert "bearer" not in text.lower()
        print("PASS: capability_token_summary_no_raw")


def test_failure_fingerprint_and_antigravity_fields():
    with tempfile.TemporaryDirectory() as td:
        ap = Path(td) / "actors.json"
        _make_actors(ap)
        actors = json.loads(ap.read_text())["actors"]

        entry = get_actor_status_entry(
            "actor-1", actors["actor-1"], hosts={}, lease_dir=Path(td) / "leases",
        )
        # Fields exist (None when no active scheduler decision)
        assert "failure_fingerprint_penalties" in entry
        assert "antigravity_denials" in entry
        assert "operator_score_summary" in entry
        assert "verification_gate_status" in entry
        print("PASS: failure_fingerprint_and_antigravity_fields")


if __name__ == "__main__":
    test_actor_status_entry_has_required_fields()
    test_actor_status_with_active_lease()
    test_stale_actor_lease()
    test_missing_host()
    test_degraded_host()
    test_host_status_entry()
    test_no_secrets_emitted()
    test_redact_secrets()
    test_logical_operator_binding_summary()
    test_load_actor_fleet()
    test_load_host_fleet()
    test_monitor_bridge_snapshot()
    test_monitor_bridge_no_secrets()
    test_evidence_and_context_paths_exposed()
    test_capability_token_summary_no_raw()
    test_failure_fingerprint_and_antigravity_fields()
    print("\n16/16 passed")
