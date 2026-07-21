#!/usr/bin/env python3
"""Regression tests: quota text → cooldown detection → surface → dispatch avoid.

Acceptance criteria:
1. planner-print quota text is classified as cooldown.
2. quotaProject= alone is NOT classified as quota exhausted.
3. fleet-status output contains reset ETA when operator is in cooldown.
4. is_dispatchable returns readable reason (not just state=cooldown) with ETA.
5. cmd_submit blocked operators emit human-readable cooldown reason.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

HARNESS_ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = HARNESS_ROOT / "lib"
TOOLS_DIR = HARNESS_ROOT / "tools"

if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def ofc():
    return _load("operator_flow_control", LIB_DIR / "operator_flow_control.py")


@pytest.fixture()
def pm(tmp_path, monkeypatch):
    mod = _load("pm_dispatch", TOOLS_DIR / "pm_dispatch.py")
    monkeypatch.setattr(mod, "OPERATOR_STATUS_DIR", tmp_path / "run" / "operator-status")
    (tmp_path / "run" / "operator-status").mkdir(parents=True, exist_ok=True)
    return mod, tmp_path


# ---------------------------------------------------------------------------
# 1. quota text classification
# ---------------------------------------------------------------------------

class TestQuotaTextClassification:
    QUOTA_SAMPLES = [
        "You've hit your limit · resets 1:40pm (America/Toronto)",
        "You've hit your limit\nPlease wait before sending more messages.",
        "RESOURCE_EXHAUSTED: quota exceeded",
        "monthly usage limit reached",
        "rate-limit exceeded",
        "too many requests",
        "Upgrade your plan to continue",
        "Individual quota reached",
        "resets in 30 minutes",
    ]

    @pytest.mark.parametrize("text", QUOTA_SAMPLES)
    def test_quota_text_classified_as_cooldown(self, ofc, text):
        state = ofc.classify_failure_state(text)
        assert state == "cooldown", f"Expected cooldown for: {text!r}, got: {state!r}"

    def test_empty_text_not_classified(self, ofc):
        assert ofc.classify_failure_state("") == ""

    def test_normal_output_not_classified(self, ofc):
        assert ofc.classify_failure_state("Task completed successfully") == ""


# ---------------------------------------------------------------------------
# 2. quotaProject= must NOT trigger quota classification
# ---------------------------------------------------------------------------

class TestQuotaProjectFalsePositive:
    FALSE_POSITIVE_SAMPLES = [
        "quotaProject=my-gcp-project",
        "?quotaProject=billing-project-123",
        "request: quotaProject=foobar",
        "quotaProject=",
        "https://api.example.com?quotaProject=xyz&key=abc",
    ]

    @pytest.mark.parametrize("text", FALSE_POSITIVE_SAMPLES)
    def test_quota_project_param_not_classified_as_quota(self, ofc, text):
        state = ofc.classify_failure_state(text)
        assert state != "cooldown", (
            f"False positive: {text!r} classified as cooldown. "
            "quotaProject= URL param should not trigger quota detection."
        )

    def test_quota_project_with_resource_exhausted_is_cooldown(self, ofc):
        """When RESOURCE_EXHAUSTED is also present, cooldown IS correct."""
        text = "RESOURCE_EXHAUSTED: quota exceeded quotaProject=my-project"
        assert ofc.classify_failure_state(text) == "cooldown"


# ---------------------------------------------------------------------------
# 3. fleet-status surface: cooldown ETA column
# ---------------------------------------------------------------------------

class TestFleetStatusCooldownSurface:
    def _write_status(self, status_dir: Path, op_id: str, state: str, expires_at: str = "") -> None:
        status_dir.mkdir(parents=True, exist_ok=True)
        data: dict = {"operator_id": op_id, "runtime_state": state}
        if expires_at:
            data["expires_at"] = expires_at
        (status_dir / f"{op_id}.json").write_text(json.dumps(data), encoding="utf-8")

    def test_format_reset_eta_returns_minutes(self, pm):
        mod, tmp_path = pm
        import datetime
        future = (
            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=47)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        eta = mod._format_reset_eta(future)
        assert "m" in eta
        assert eta.startswith("~")

    def test_format_reset_eta_returns_hours(self, pm):
        mod, tmp_path = pm
        import datetime
        future = (
            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2, minutes=15)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        eta = mod._format_reset_eta(future)
        assert "h" in eta

    def test_format_reset_eta_empty_string_on_empty_input(self, pm):
        mod, _ = pm
        assert mod._format_reset_eta("") == ""

    def test_format_reset_eta_soon_when_expired(self, pm):
        mod, _ = pm
        assert mod._format_reset_eta("2020-01-01T00:00:00Z") == "soon"

    def test_fleet_status_prints_cooldown_eta(self, pm, monkeypatch, capsys):
        import argparse, datetime
        mod, tmp_path = pm
        future = (
            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._write_status(tmp_path / "run" / "operator-status", "op-cool", "cooldown", future)

        monkeypatch.setattr(mod, "load_registry", lambda: {
            "version": 1,
            "operators": {
                "op-cool": {
                    "enabled": True, "available": True,
                    "role": "builder", "model": "sonnet",
                },
            },
        })

        rc = mod.cmd_fleet_status(argparse.Namespace())
        out = capsys.readouterr().out
        assert rc == 0
        assert "cooldown" in out
        assert "resets" in out
        assert future[:16] in out or "h" in out  # ETA or timestamp present


# ---------------------------------------------------------------------------
# 4. is_dispatchable returns readable reason with ETA
# ---------------------------------------------------------------------------

class TestIsDispatchableReason:
    def _write_status(self, status_dir: Path, op_id: str, state: str, expires_at: str = "") -> None:
        status_dir.mkdir(parents=True, exist_ok=True)
        data: dict = {"operator_id": op_id, "runtime_state": state}
        if expires_at:
            data["expires_at"] = expires_at
        (status_dir / f"{op_id}.json").write_text(json.dumps(data), encoding="utf-8")

    def test_cooldown_reason_includes_state(self, pm):
        mod, tmp_path = pm
        self._write_status(tmp_path / "run" / "operator-status", "op-a", "cooldown")
        op = {"operator_id": "op-a", "enabled": True, "available": True}
        ok, reason = mod.is_dispatchable(op)
        assert not ok
        assert "cooldown" in reason

    def test_cooldown_reason_includes_eta_when_expires_at_set(self, pm):
        import datetime
        mod, tmp_path = pm
        future = (
            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=30)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._write_status(tmp_path / "run" / "operator-status", "op-b", "cooldown", future)
        op = {"operator_id": "op-b", "enabled": True, "available": True}
        ok, reason = mod.is_dispatchable(op)
        assert not ok
        assert "resets" in reason or "until" in reason
        assert future in reason

    def test_cooldown_reason_not_just_state_equals(self, pm):
        """Reason must be more informative than bare 'runtime_state=cooldown'."""
        import datetime
        mod, tmp_path = pm
        future = (
            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._write_status(tmp_path / "run" / "operator-status", "op-c", "cooldown", future)
        op = {"operator_id": "op-c", "enabled": True, "available": True}
        _, reason = mod.is_dispatchable(op)
        assert reason != "runtime_state=cooldown"

    def test_auth_expired_reason_readable(self, pm):
        mod, tmp_path = pm
        self._write_status(tmp_path / "run" / "operator-status", "op-d", "auth_expired")
        op = {"operator_id": "op-d", "enabled": True, "available": True}
        ok, reason = mod.is_dispatchable(op)
        assert not ok
        assert "auth_expired" in reason

    def test_idle_operator_is_dispatchable(self, pm):
        mod, tmp_path = pm
        op = {"operator_id": "op-idle", "enabled": True, "available": True}
        ok, reason = mod.is_dispatchable(op)
        assert ok
        assert reason == ""


# ---------------------------------------------------------------------------
# 5. apply_failure_flow_control → operator enters cooldown
# ---------------------------------------------------------------------------

class TestApplyFailureFlowControl:
    def test_quota_text_sets_cooldown_state(self, tmp_path, monkeypatch):
        import operator_flow_control as ofc

        status_dir = tmp_path / "run" / "operator-status"
        status_dir.mkdir(parents=True, exist_ok=True)
        task_dir = tmp_path / "task"
        task_dir.mkdir()

        calls: list[dict] = []

        def _fake_set_status(op_id, state, ttl_seconds=None):
            calls.append({"op_id": op_id, "state": state, "ttl": ttl_seconds})
            return {"operator_id": op_id, "runtime_state": state}

        import operator_runtime as rt
        monkeypatch.setattr(rt, "set_operator_status", _fake_set_status)

        quota_text = "You've hit your limit · resets 1:40pm (America/Toronto)"
        result = ofc.apply_failure_flow_control(
            task_dir,
            operator_id="op-planner",
            failure_text=quota_text,
            rate_limit_cooldown_seconds=3600,
            auth_cooldown_seconds=21600,
        )

        assert result["runtime_state"] == "cooldown"
        assert any(c["state"] == "cooldown" for c in calls)
        cooldown_call = next(c for c in calls if c["state"] == "cooldown")
        assert cooldown_call["ttl"] == 3600

    def test_quota_project_param_does_not_set_cooldown(self, tmp_path, monkeypatch):
        import operator_flow_control as ofc

        task_dir = tmp_path / "task2"
        task_dir.mkdir()
        calls: list[dict] = []

        import operator_runtime as rt
        monkeypatch.setattr(rt, "set_operator_status", lambda *a, **kw: calls.append(a) or {})

        result = ofc.apply_failure_flow_control(
            task_dir,
            operator_id="op-planner",
            failure_text="quotaProject=my-gcp-project request succeeded",
            rate_limit_cooldown_seconds=3600,
            auth_cooldown_seconds=21600,
        )

        assert result["runtime_state"] == ""
        assert len(calls) == 0
