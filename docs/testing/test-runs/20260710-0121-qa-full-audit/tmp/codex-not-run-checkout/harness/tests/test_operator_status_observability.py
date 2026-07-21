"""Tests for operator/persona lifecycle state observability.

Verifies that:
- ``multi_task_status.get_operator_status_entry`` returns all required fields
  (operator_id, role, resolved_persona, lifecycle_state, heartbeat_at).
- ``multi_task_status.load_operator_fleet`` returns an enriched fleet dict
  keyed by operator_id.
- ``monitor_bridge.build_snapshot`` produces a JSON snapshot whose
  ``operator_fleet`` entries include submit/daemon fields.
- A lightweight secret scan confirms no credentials are embedded in the new
  source files (acceptance: "secret scan passes on new and changed files").
"""
from __future__ import annotations

import datetime
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Path setup — keep identical to conftest.py convention
# ---------------------------------------------------------------------------

HARNESS_DIR = Path(__file__).resolve().parent.parent
_LIB_DIR = HARNESS_DIR / "lib"
_TOOLS_DIR = HARNESS_DIR / "tools"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_harness(tmp_path: Path) -> dict[str, Path]:
    """Minimal harness directory with registry, persona stubs, and runtime dirs."""
    operators_path = tmp_path / "config" / "physical-operators.json"
    operators_path.parent.mkdir(parents=True)

    personas_dir = tmp_path / "personas"
    personas_dir.mkdir(parents=True)
    status_dir = tmp_path / "run" / "operator-status"
    status_dir.mkdir(parents=True)
    lease_dir = tmp_path / "run" / "operator-leases"
    lease_dir.mkdir(parents=True)

    # Stub persona files
    (personas_dir / "builder.md").write_text("# Builder\n", encoding="utf-8")
    (personas_dir / "evaluator.md").write_text("# Evaluator\n", encoding="utf-8")

    registry = {
        "version": 1,
        "operators": {
            "test-builder-01": {
                "display_name": "Test Builder 01",
                "role": "builder",
                "persona": "builder",
                "provider": "anthropic",
                "vendor": "anthropic",
                "model": "sonnet",
                "enabled": True,
            },
            "test-evaluator-01": {
                "display_name": "Test Evaluator 01",
                "role": "evaluator",
                "persona": "evaluator",
                "provider": "anthropic",
                "vendor": "anthropic",
                "model": "opus",
                "enabled": True,
            },
            "test-disabled-01": {
                "display_name": "Disabled Op",
                "role": "builder",
                "persona": "builder",
                "provider": "anthropic",
                "vendor": "anthropic",
                "model": "sonnet",
                "enabled": False,
            },
        },
    }
    operators_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")

    return {
        "operators_path": operators_path,
        "personas_dir": personas_dir,
        "status_dir": status_dir,
        "lease_dir": lease_dir,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _entry(op_id: str, role: str, persona: str, enabled: bool = True,
           status_dir: Path | None = None,
           lease_dir: Path | None = None,
           personas_dir: Path | None = None,
           tmp_path: Path | None = None) -> dict[str, Any]:
    from multi_task_status import get_operator_status_entry
    op_cfg = {"role": role, "persona": persona, "enabled": enabled}
    kw: dict[str, Any] = {}
    if status_dir is not None:
        kw["status_dir"] = status_dir
    if lease_dir is not None:
        kw["lease_dir"] = lease_dir
    if personas_dir is not None:
        kw["personas_dir"] = personas_dir
    elif tmp_path is not None:
        kw["personas_dir"] = tmp_path / "personas"
    return get_operator_status_entry(op_id, op_cfg, **kw)


# ---------------------------------------------------------------------------
# get_operator_status_entry: required fields
# ---------------------------------------------------------------------------

class TestGetOperatorStatusEntry:
    def test_all_required_fields_present(self, tmp_harness: dict[str, Path]) -> None:
        entry = _entry(
            "test-builder-01", "builder", "builder",
            status_dir=tmp_harness["status_dir"],
            lease_dir=tmp_harness["lease_dir"],
            personas_dir=tmp_harness["personas_dir"],
        )
        # Acceptance: status output includes operator_id, role, resolved_persona,
        # lifecycle_state, and heartbeat.
        for field in ("operator_id", "role", "resolved_persona", "lifecycle_state", "heartbeat_at"):
            assert field in entry, f"Missing required field: {field}"

    def test_operator_id_matches_input(self, tmp_harness: dict[str, Path]) -> None:
        entry = _entry(
            "test-builder-01", "builder", "builder",
            status_dir=tmp_harness["status_dir"],
            lease_dir=tmp_harness["lease_dir"],
            personas_dir=tmp_harness["personas_dir"],
        )
        assert entry["operator_id"] == "test-builder-01"

    def test_role_from_config(self, tmp_harness: dict[str, Path]) -> None:
        entry = _entry(
            "test-evaluator-01", "evaluator", "evaluator",
            status_dir=tmp_harness["status_dir"],
            lease_dir=tmp_harness["lease_dir"],
            personas_dir=tmp_harness["personas_dir"],
        )
        assert entry["role"] == "evaluator"

    def test_resolved_persona_from_config_persona_field(
        self, tmp_harness: dict[str, Path]
    ) -> None:
        entry = _entry(
            "test-builder-01", "builder", "builder",
            status_dir=tmp_harness["status_dir"],
            lease_dir=tmp_harness["lease_dir"],
            personas_dir=tmp_harness["personas_dir"],
        )
        assert entry["resolved_persona"] == "builder"

    def test_resolved_persona_falls_back_to_role(
        self, tmp_harness: dict[str, Path]
    ) -> None:
        from multi_task_status import get_operator_status_entry
        op_cfg = {"role": "planner", "enabled": True}  # no persona field
        entry = get_operator_status_entry(
            "test-planner",
            op_cfg,
            status_dir=tmp_harness["status_dir"],
            lease_dir=tmp_harness["lease_dir"],
            personas_dir=tmp_harness["personas_dir"],
        )
        assert entry["resolved_persona"] == "planner"

    def test_lifecycle_state_idle_no_lease_no_override(
        self, tmp_harness: dict[str, Path]
    ) -> None:
        entry = _entry(
            "test-builder-01", "builder", "builder",
            status_dir=tmp_harness["status_dir"],
            lease_dir=tmp_harness["lease_dir"],
            personas_dir=tmp_harness["personas_dir"],
        )
        assert entry["lifecycle_state"] == "idle"

    def test_lifecycle_state_disabled_for_disabled_op(
        self, tmp_harness: dict[str, Path]
    ) -> None:
        entry = _entry(
            "test-disabled-01", "builder", "builder", enabled=False,
            status_dir=tmp_harness["status_dir"],
            lease_dir=tmp_harness["lease_dir"],
            personas_dir=tmp_harness["personas_dir"],
        )
        assert entry["lifecycle_state"] == "disabled"

    def test_heartbeat_at_populated_from_status_file(
        self, tmp_harness: dict[str, Path]
    ) -> None:
        hb = {
            "operator_id": "test-builder-01",
            "runtime_state": "idle",
            "state": "idle",
            "heartbeat_at": "2026-05-22T00:00:00Z",
            "resolved_persona": "builder",
        }
        (tmp_harness["status_dir"] / "test-builder-01.json").write_text(
            json.dumps(hb), encoding="utf-8"
        )
        entry = _entry(
            "test-builder-01", "builder", "builder",
            status_dir=tmp_harness["status_dir"],
            lease_dir=tmp_harness["lease_dir"],
            personas_dir=tmp_harness["personas_dir"],
        )
        assert entry["heartbeat_at"] == "2026-05-22T00:00:00Z"

    def test_heartbeat_at_na_when_no_file(self, tmp_harness: dict[str, Path]) -> None:
        entry = _entry(
            "test-builder-01", "builder", "builder",
            status_dir=tmp_harness["status_dir"],
            lease_dir=tmp_harness["lease_dir"],
            personas_dir=tmp_harness["personas_dir"],
        )
        assert entry["heartbeat_at"] == "N/A"

    def test_submit_state_populated_from_active_lease(
        self, tmp_harness: dict[str, Path]
    ) -> None:
        expires = (
            datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(hours=1)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        lease = {
            "operator_id": "test-builder-01",
            "task_id": "task-abc",
            "sprint_id": "sprint-xyz",
            "node_id": "N5",
            "leased_at": "2026-05-22T00:00:00Z",
            "expires_at": expires,
            "state": "leased",
        }
        (tmp_harness["lease_dir"] / "test-builder-01.json").write_text(
            json.dumps(lease), encoding="utf-8"
        )
        entry = _entry(
            "test-builder-01", "builder", "builder",
            status_dir=tmp_harness["status_dir"],
            lease_dir=tmp_harness["lease_dir"],
            personas_dir=tmp_harness["personas_dir"],
        )
        assert entry["submit_state"] is not None
        assert entry["submit_state"]["task_id"] == "task-abc"
        assert entry["submit_state"]["sprint_id"] == "sprint-xyz"
        assert entry["submit_state"]["node_id"] == "N5"

    def test_submit_state_none_when_no_lease(
        self, tmp_harness: dict[str, Path]
    ) -> None:
        entry = _entry(
            "test-builder-01", "builder", "builder",
            status_dir=tmp_harness["status_dir"],
            lease_dir=tmp_harness["lease_dir"],
            personas_dir=tmp_harness["personas_dir"],
        )
        assert entry["submit_state"] is None

    def test_submit_state_none_for_expired_lease(
        self, tmp_harness: dict[str, Path]
    ) -> None:
        expired = (
            datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(hours=1)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        lease = {
            "operator_id": "test-builder-01",
            "task_id": "task-old",
            "sprint_id": "sprint-old",
            "node_id": "N1",
            "leased_at": "2026-05-01T00:00:00Z",
            "expires_at": expired,
            "state": "leased",
        }
        (tmp_harness["lease_dir"] / "test-builder-01.json").write_text(
            json.dumps(lease), encoding="utf-8"
        )
        entry = _entry(
            "test-builder-01", "builder", "builder",
            status_dir=tmp_harness["status_dir"],
            lease_dir=tmp_harness["lease_dir"],
            personas_dir=tmp_harness["personas_dir"],
        )
        assert entry["submit_state"] is None

    def test_daemon_state_from_heartbeat(
        self, tmp_harness: dict[str, Path]
    ) -> None:
        hb = {
            "operator_id": "test-builder-01",
            "runtime_state": "running",
            "state": "running",
            "heartbeat_at": "2026-05-22T01:00:00Z",
            "current_task_id": "task-xyz",
            "resolved_persona": "builder",
        }
        (tmp_harness["status_dir"] / "test-builder-01.json").write_text(
            json.dumps(hb), encoding="utf-8"
        )
        entry = _entry(
            "test-builder-01", "builder", "builder",
            status_dir=tmp_harness["status_dir"],
            lease_dir=tmp_harness["lease_dir"],
            personas_dir=tmp_harness["personas_dir"],
        )
        assert entry["daemon_state"] == "running"
        assert entry["current_task_id"] == "task-xyz"

    def test_lifecycle_state_from_active_lease(
        self, tmp_harness: dict[str, Path]
    ) -> None:
        expires = (
            datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(hours=1)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        lease = {
            "operator_id": "test-builder-01",
            "task_id": "t1",
            "sprint_id": "s1",
            "node_id": "N1",
            "leased_at": "2026-05-22T00:00:00Z",
            "expires_at": expires,
            "state": "running",
        }
        (tmp_harness["lease_dir"] / "test-builder-01.json").write_text(
            json.dumps(lease), encoding="utf-8"
        )
        entry = _entry(
            "test-builder-01", "builder", "builder",
            status_dir=tmp_harness["status_dir"],
            lease_dir=tmp_harness["lease_dir"],
            personas_dir=tmp_harness["personas_dir"],
        )
        assert entry["lifecycle_state"] == "running"


# ---------------------------------------------------------------------------
# load_operator_fleet
# ---------------------------------------------------------------------------

class TestLoadOperatorFleet:
    def test_fleet_keyed_by_operator_id(self, tmp_harness: dict[str, Path]) -> None:
        from multi_task_status import load_operator_fleet
        fleet = load_operator_fleet(
            tmp_harness["operators_path"],
            personas_dir=tmp_harness["personas_dir"],
            status_dir=tmp_harness["status_dir"],
            lease_dir=tmp_harness["lease_dir"],
        )
        assert "test-builder-01" in fleet
        assert "test-evaluator-01" in fleet
        assert "test-disabled-01" in fleet

    def test_fleet_entries_have_all_required_fields(
        self, tmp_harness: dict[str, Path]
    ) -> None:
        from multi_task_status import load_operator_fleet
        fleet = load_operator_fleet(
            tmp_harness["operators_path"],
            personas_dir=tmp_harness["personas_dir"],
            status_dir=tmp_harness["status_dir"],
            lease_dir=tmp_harness["lease_dir"],
        )
        required = {
            "operator_id",
            "role",
            "resolved_persona",
            "lifecycle_state",
            "heartbeat_at",
            "daemon_state",
            "submit_state",
        }
        for op_id, entry in fleet.items():
            missing = required - set(entry.keys())
            assert not missing, f"{op_id} entry missing fields: {missing}"

    def test_fleet_empty_on_missing_registry(self, tmp_path: Path) -> None:
        from multi_task_status import load_operator_fleet
        fleet = load_operator_fleet(
            tmp_path / "nonexistent.json",
            personas_dir=tmp_path / "personas",
            status_dir=tmp_path / "status",
            lease_dir=tmp_path / "leases",
        )
        assert fleet == {}

    def test_fleet_empty_on_malformed_registry(self, tmp_path: Path) -> None:
        from multi_task_status import load_operator_fleet
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid json", encoding="utf-8")
        fleet = load_operator_fleet(
            bad,
            personas_dir=tmp_path / "personas",
            status_dir=tmp_path / "status",
            lease_dir=tmp_path / "leases",
        )
        assert fleet == {}

    def test_disabled_operator_has_disabled_lifecycle_state(
        self, tmp_harness: dict[str, Path]
    ) -> None:
        from multi_task_status import load_operator_fleet
        fleet = load_operator_fleet(
            tmp_harness["operators_path"],
            personas_dir=tmp_harness["personas_dir"],
            status_dir=tmp_harness["status_dir"],
            lease_dir=tmp_harness["lease_dir"],
        )
        assert fleet["test-disabled-01"]["lifecycle_state"] == "disabled"
        assert fleet["test-disabled-01"]["enabled"] is False


# ---------------------------------------------------------------------------
# monitor_bridge: build_snapshot
# ---------------------------------------------------------------------------

class TestMonitorBridgeSnapshot:
    def _load_mb(self) -> Any:
        spec = importlib.util.spec_from_file_location(
            "monitor_bridge",
            HARNESS_DIR / "tools" / "monitor_bridge.py",
        )
        if spec is None or spec.loader is None:
            pytest.skip("monitor_bridge.py not loadable")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod

    def test_snapshot_schema_field(self, tmp_harness: dict[str, Path]) -> None:
        mb = self._load_mb()
        snapshot = mb.build_snapshot(
            tmp_harness["operators_path"],
            personas_dir=tmp_harness["personas_dir"],
            status_dir=tmp_harness["status_dir"],
            lease_dir=tmp_harness["lease_dir"],
        )
        assert snapshot["schema"] == "solar.monitor_bridge.operator_fleet.v2"

    def test_snapshot_top_level_fields(self, tmp_harness: dict[str, Path]) -> None:
        mb = self._load_mb()
        snapshot = mb.build_snapshot(
            tmp_harness["operators_path"],
            personas_dir=tmp_harness["personas_dir"],
            status_dir=tmp_harness["status_dir"],
            lease_dir=tmp_harness["lease_dir"],
        )
        for field in (
            "observed_at",
            "operator_count",
            "submit_count",
            "daemon_active_count",
            "lifecycle_counts",
            "operator_fleet",
        ):
            assert field in snapshot, f"Missing top-level field: {field}"

    def test_snapshot_fleet_has_submit_and_daemon_fields(
        self, tmp_harness: dict[str, Path]
    ) -> None:
        """Acceptance: bridge latest JSON includes operator_fleet submit/daemon fields."""
        mb = self._load_mb()
        snapshot = mb.build_snapshot(
            tmp_harness["operators_path"],
            personas_dir=tmp_harness["personas_dir"],
            status_dir=tmp_harness["status_dir"],
            lease_dir=tmp_harness["lease_dir"],
        )
        required = {
            "operator_id",
            "role",
            "resolved_persona",
            "lifecycle_state",
            "heartbeat_at",
            "submit_state",
            "daemon_state",
        }
        fleet = snapshot["operator_fleet"]
        assert len(fleet) == 3
        for op_id, entry in fleet.items():
            missing = required - set(entry.keys())
            assert not missing, f"Fleet entry {op_id} missing: {missing}"

    def test_snapshot_operator_count(self, tmp_harness: dict[str, Path]) -> None:
        mb = self._load_mb()
        snapshot = mb.build_snapshot(
            tmp_harness["operators_path"],
            personas_dir=tmp_harness["personas_dir"],
            status_dir=tmp_harness["status_dir"],
            lease_dir=tmp_harness["lease_dir"],
        )
        assert snapshot["operator_count"] == 3

    def test_snapshot_submit_count_zero_when_no_leases(
        self, tmp_harness: dict[str, Path]
    ) -> None:
        mb = self._load_mb()
        snapshot = mb.build_snapshot(
            tmp_harness["operators_path"],
            personas_dir=tmp_harness["personas_dir"],
            status_dir=tmp_harness["status_dir"],
            lease_dir=tmp_harness["lease_dir"],
        )
        assert snapshot["submit_count"] == 0

    def test_snapshot_submit_count_nonzero_with_active_lease(
        self, tmp_harness: dict[str, Path]
    ) -> None:
        expires = (
            datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(hours=1)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        lease = {
            "operator_id": "test-builder-01",
            "task_id": "t1",
            "sprint_id": "s1",
            "node_id": "N1",
            "leased_at": "2026-05-22T00:00:00Z",
            "expires_at": expires,
            "state": "running",
        }
        (tmp_harness["lease_dir"] / "test-builder-01.json").write_text(
            json.dumps(lease), encoding="utf-8"
        )
        mb = self._load_mb()
        snapshot = mb.build_snapshot(
            tmp_harness["operators_path"],
            personas_dir=tmp_harness["personas_dir"],
            status_dir=tmp_harness["status_dir"],
            lease_dir=tmp_harness["lease_dir"],
        )
        assert snapshot["submit_count"] == 1

    def test_snapshot_is_json_serialisable(
        self, tmp_harness: dict[str, Path]
    ) -> None:
        mb = self._load_mb()
        snapshot = mb.build_snapshot(
            tmp_harness["operators_path"],
            personas_dir=tmp_harness["personas_dir"],
            status_dir=tmp_harness["status_dir"],
            lease_dir=tmp_harness["lease_dir"],
        )
        text = json.dumps(snapshot, ensure_ascii=False)
        assert len(text) > 10

    def test_snapshot_claude_print_process_count_present(
        self, tmp_harness: dict[str, Path]
    ) -> None:
        """Acceptance: bridge JSON includes observed claude_print process count."""
        mb = self._load_mb()
        snapshot = mb.build_snapshot(
            tmp_harness["operators_path"],
            personas_dir=tmp_harness["personas_dir"],
            status_dir=tmp_harness["status_dir"],
            lease_dir=tmp_harness["lease_dir"],
        )
        assert "claude_print_process_count" in snapshot
        # Value must be an integer (non-negative when pgrep is available, -1 if not).
        assert isinstance(snapshot["claude_print_process_count"], int)

    def test_snapshot_fleet_includes_billing_pool(
        self, tmp_harness: dict[str, Path]
    ) -> None:
        """Acceptance: operator_fleet entries include billing_pool."""
        mb = self._load_mb()
        snapshot = mb.build_snapshot(
            tmp_harness["operators_path"],
            personas_dir=tmp_harness["personas_dir"],
            status_dir=tmp_harness["status_dir"],
            lease_dir=tmp_harness["lease_dir"],
        )
        for op_id, entry in snapshot["operator_fleet"].items():
            assert "billing_pool" in entry, (
                f"operator_fleet entry {op_id} missing 'billing_pool'"
            )

    def test_snapshot_fleet_billing_pool_reflects_registry(
        self, tmp_path: Path
    ) -> None:
        """billing_pool in fleet entry matches the registry value."""
        operators_path = tmp_path / "config" / "physical-operators.json"
        operators_path.parent.mkdir(parents=True)
        (tmp_path / "run" / "operator-status").mkdir(parents=True)
        (tmp_path / "run" / "operator-leases").mkdir(parents=True)
        (tmp_path / "personas").mkdir(parents=True)

        registry = {
            "version": 1,
            "operators": {
                "op-with-pool": {
                    "display_name": "Operator with Pool",
                    "role": "builder",
                    "persona": "builder",
                    "provider": "anthropic",
                    "vendor": "anthropic",
                    "model": "sonnet",
                    "billing_pool": "anthropic_subscription_interactive",
                    "enabled": True,
                },
            },
        }
        operators_path.write_text(json.dumps(registry), encoding="utf-8")

        mb = self._load_mb()
        snapshot = mb.build_snapshot(
            operators_path,
            personas_dir=tmp_path / "personas",
            status_dir=tmp_path / "run" / "operator-status",
            lease_dir=tmp_path / "run" / "operator-leases",
        )
        assert snapshot["operator_fleet"]["op-with-pool"]["billing_pool"] == (
            "anthropic_subscription_interactive"
        )


# ---------------------------------------------------------------------------
# N4 additions: surface / billing_surface / billing_pool in status entries
# ---------------------------------------------------------------------------

class TestOperatorStatusSurfaceAndBilling:
    """Acceptance: status output includes surface and billing_surface."""

    def _mk_dirs(self, tmp_path: Path) -> dict[str, Path]:
        sd = tmp_path / "run" / "operator-status"
        ld = tmp_path / "run" / "operator-leases"
        pd = tmp_path / "personas"
        sd.mkdir(parents=True)
        ld.mkdir(parents=True)
        pd.mkdir(parents=True)
        return {"status_dir": sd, "lease_dir": ld, "personas_dir": pd}

    def test_surface_field_present_and_none_when_absent(
        self, tmp_path: Path
    ) -> None:
        dirs = self._mk_dirs(tmp_path)
        from multi_task_status import get_operator_status_entry
        op_cfg = {"role": "builder", "enabled": True}
        entry = get_operator_status_entry("op-no-surface", op_cfg, **dirs)
        assert "surface" in entry
        assert entry["surface"] is None

    def test_surface_field_populated_from_config(
        self, tmp_path: Path
    ) -> None:
        dirs = self._mk_dirs(tmp_path)
        from multi_task_status import get_operator_status_entry
        surface_cfg = {
            "type": "claude_code_interactive",
            "tool": "claude",
            "launch_cmd": "claude --dangerously-skip-permissions --model sonnet",
        }
        op_cfg = {"role": "builder", "enabled": True, "surface": surface_cfg}
        entry = get_operator_status_entry("op-with-surface", op_cfg, **dirs)
        assert entry["surface"] == surface_cfg
        assert entry["surface"]["type"] == "claude_code_interactive"

    def test_surface_field_none_when_config_has_non_dict_surface(
        self, tmp_path: Path
    ) -> None:
        dirs = self._mk_dirs(tmp_path)
        from multi_task_status import get_operator_status_entry
        op_cfg = {"role": "builder", "enabled": True, "surface": "not-a-dict"}
        entry = get_operator_status_entry("op-bad-surface", op_cfg, **dirs)
        assert entry["surface"] is None

    def test_billing_surface_present_and_na_when_absent(
        self, tmp_path: Path
    ) -> None:
        dirs = self._mk_dirs(tmp_path)
        from multi_task_status import get_operator_status_entry
        op_cfg = {"role": "builder", "enabled": True}
        entry = get_operator_status_entry("op-no-billing", op_cfg, **dirs)
        assert "billing_surface" in entry
        assert entry["billing_surface"] == "N/A"

    def test_billing_surface_from_config(
        self, tmp_path: Path
    ) -> None:
        dirs = self._mk_dirs(tmp_path)
        from multi_task_status import get_operator_status_entry
        op_cfg = {
            "role": "builder",
            "enabled": True,
            "billing_surface": "subscription_interactive",
        }
        entry = get_operator_status_entry("op-bs", op_cfg, **dirs)
        assert entry["billing_surface"] == "subscription_interactive"

    def test_billing_pool_present_and_na_when_absent(
        self, tmp_path: Path
    ) -> None:
        dirs = self._mk_dirs(tmp_path)
        from multi_task_status import get_operator_status_entry
        op_cfg = {"role": "builder", "enabled": True}
        entry = get_operator_status_entry("op-no-pool", op_cfg, **dirs)
        assert "billing_pool" in entry
        assert entry["billing_pool"] == "N/A"

    def test_billing_pool_from_config(
        self, tmp_path: Path
    ) -> None:
        dirs = self._mk_dirs(tmp_path)
        from multi_task_status import get_operator_status_entry
        op_cfg = {
            "role": "builder",
            "enabled": True,
            "billing_pool": "anthropic_subscription_interactive",
        }
        entry = get_operator_status_entry("op-bp", op_cfg, **dirs)
        assert entry["billing_pool"] == "anthropic_subscription_interactive"

    def test_all_surface_billing_fields_in_required_set(
        self, tmp_path: Path
    ) -> None:
        dirs = self._mk_dirs(tmp_path)
        from multi_task_status import get_operator_status_entry
        op_cfg = {"role": "builder", "enabled": True}
        entry = get_operator_status_entry("op-check", op_cfg, **dirs)
        for field in ("surface", "billing_surface", "billing_pool"):
            assert field in entry, f"Missing field: {field}"

    def test_fleet_entries_include_surface_billing_fields(
        self, tmp_path: Path
    ) -> None:
        """load_operator_fleet entries must include surface, billing_surface, billing_pool."""
        operators_path = tmp_path / "config" / "physical-operators.json"
        operators_path.parent.mkdir(parents=True)
        dirs = self._mk_dirs(tmp_path)

        registry = {
            "version": 1,
            "operators": {
                "op-full": {
                    "display_name": "Full Operator",
                    "role": "builder",
                    "persona": "builder",
                    "provider": "anthropic",
                    "vendor": "anthropic",
                    "model": "sonnet",
                    "billing_surface": "subscription_interactive",
                    "billing_pool": "anthropic_subscription_interactive",
                    "surface": {
                        "type": "claude_code_interactive",
                        "tool": "claude",
                        "launch_cmd": "claude --dangerously-skip-permissions --model sonnet",
                    },
                    "enabled": True,
                },
            },
        }
        operators_path.write_text(json.dumps(registry), encoding="utf-8")

        from multi_task_status import load_operator_fleet
        fleet = load_operator_fleet(
            operators_path,
            personas_dir=dirs["personas_dir"],
            status_dir=dirs["status_dir"],
            lease_dir=dirs["lease_dir"],
        )
        entry = fleet["op-full"]
        assert entry["billing_surface"] == "subscription_interactive"
        assert entry["billing_pool"] == "anthropic_subscription_interactive"
        assert isinstance(entry["surface"], dict)
        assert entry["surface"]["type"] == "claude_code_interactive"


# ---------------------------------------------------------------------------
# Secret scan — lint gate covering the new source files
# ---------------------------------------------------------------------------

_SECRET_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9]{32,}"),
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),
    re.compile(r"github_pat_[a-zA-Z0-9_]{82}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"Bearer [a-zA-Z0-9\-._~+/=]{20,}"),
    re.compile(r"(?i)(api[_-]?key|apikey|api_secret)\s*[=:]\s*[^\s\"']{8,}"),
    re.compile(r"(?i)(password|passwd)\s*[=:]\s*[^\s\"']{4,}"),
    re.compile(r"(?i)(token|secret)\s*[=:]\s*[^\s\"']{8,}"),
]

_NEW_SOURCE_FILES = [
    HARNESS_DIR / "lib" / "multi_task_status.py",
    HARNESS_DIR / "tools" / "monitor_bridge.py",
    HARNESS_DIR / "tests" / "test_operator_status_observability.py",
]


@pytest.mark.parametrize(
    "src_path", _NEW_SOURCE_FILES, ids=[p.name for p in _NEW_SOURCE_FILES]
)
def test_secret_scan_passes_on_new_files(src_path: Path) -> None:
    """New source files must not contain embedded credentials."""
    if not src_path.exists():
        pytest.skip(f"{src_path.name} does not exist yet")

    text = src_path.read_text(encoding="utf-8", errors="ignore")
    hits = [
        (pat.pattern, m.group())
        for pat in _SECRET_PATTERNS
        for m in pat.finditer(text)
    ]
    assert not hits, (
        f"{src_path.name} contains potential credentials: {hits}. "
        "Remove secrets and use environment variables instead."
    )
