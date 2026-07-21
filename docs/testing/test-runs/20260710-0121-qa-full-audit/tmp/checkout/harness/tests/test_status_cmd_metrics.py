"""Tests for harness/lib/cli/status_cmd.py (S04 N6).

Acceptance (from N6 dispatch):
    1. solar-harness status shows 6 metric values + alert flag.
    2. Falls back to legacy output when observability missing.
    3. JSON mode (--json) outputs structured metrics.

Plus LR-01 import-time isolation: status_cmd.py must not transitively load
the execution_broker module, and must survive an observability import
failure without raising.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from harness.lib.cli import status_cmd
from harness.lib.cli.status_cmd import (
    SCHEMA_VERSION,
    build_payload,
    compute_metrics,
    main,
    render_text,
    validate_payload,
)
from harness.lib.observability import metrics as metrics_mod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def empty_events_file(tmp_path: Path) -> Path:
    p = tmp_path / "events_empty.jsonl"
    p.write_text("", encoding="utf-8")
    return p


@pytest.fixture
def sample_events_file(tmp_path: Path) -> Path:
    p = tmp_path / "events_sample.jsonl"
    events = [
        # action 1: proposed + PASS verdict → contracted
        {
            "event_type": "action.proposed",
            "payload": {"action_id": "a1"},
            "created_at": "2026-05-20T15:00:00Z",
        },
        {
            "event_type": "policy.verdict",
            "payload": {"action_id": "a1", "verdict": "PASS"},
            "created_at": "2026-05-20T15:00:01Z",
        },
        # action 2: proposed + FAIL approval-pending verdict → uncovered + pending
        {
            "event_type": "action.proposed",
            "payload": {"action_id": "a2"},
            "created_at": "2026-05-20T15:00:02Z",
        },
        {
            "event_type": "policy.verdict",
            "payload": {
                "action_id": "a2",
                "verdict": "FAIL",
                "reason": "HUMAN_APPROVAL_REQUIRED",
            },
            "created_at": "2026-05-20T15:00:03Z",
        },
        # dispatcher dead-letter event
        {
            "event_type": "dispatcher.dead_letter",
            "payload": {"reason": "timeout"},
            "created_at": "2026-05-20T15:00:04Z",
        },
    ]
    p.write_text(
        "\n".join(json.dumps(e) for e in events) + "\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture
def empty_sprints_dir(tmp_path: Path) -> Path:
    d = tmp_path / "sprints_empty"
    d.mkdir()
    return d


@pytest.fixture
def sprints_dir_with_one_blocked(tmp_path: Path) -> Path:
    d = tmp_path / "sprints_mixed"
    d.mkdir()
    (d / "a.status.json").write_text(
        json.dumps({"id": "a", "status": "blocked"}), encoding="utf-8"
    )
    (d / "b.status.json").write_text(
        json.dumps({"id": "b", "status": "active"}), encoding="utf-8"
    )
    (d / "c.status.json").write_text(
        json.dumps({"id": "c", "status": "passed"}), encoding="utf-8"
    )
    return d


# ---------------------------------------------------------------------------
# Acceptance #1 — six metrics + alert flag rendered.
# ---------------------------------------------------------------------------
class TestAcceptance1MetricsRendered:
    def test_payload_has_six_metric_records(
        self, sample_events_file: Path, empty_sprints_dir: Path
    ) -> None:
        api, error = status_cmd._try_load_observability()
        assert api is not None, f"observability load must succeed in tests: {error}"
        payload = build_payload(
            events_path=sample_events_file,
            sprints_dir=empty_sprints_dir,
            api=api,
            error=None,
        )
        assert payload["status"] == "ok"
        assert set(payload["metrics"].keys()) == {
            "broker_coverage_pct",
            "policy_denied_rate",
            "approval_pending_count",
            "event_ledger_lag_sec",
            "dispatcher_dead_letter",
            "sprint_blocked_count",
        }

    def test_each_metric_has_value_alert_threshold(
        self, sample_events_file: Path, empty_sprints_dir: Path
    ) -> None:
        api, _ = status_cmd._try_load_observability()
        payload = build_payload(
            events_path=sample_events_file,
            sprints_dir=empty_sprints_dir,
            api=api,
            error=None,
        )
        for name, info in payload["metrics"].items():
            assert "value" in info, f"{name} missing value"
            assert "alert" in info, f"{name} missing alert"
            assert info["alert"] in {"OK", "ALARM", "CRITICAL"}, (
                f"{name} bad alert: {info['alert']!r}"
            )
            assert "threshold" in info

    def test_text_render_contains_all_six_names(
        self, sample_events_file: Path, empty_sprints_dir: Path
    ) -> None:
        api, _ = status_cmd._try_load_observability()
        payload = build_payload(
            events_path=sample_events_file,
            sprints_dir=empty_sprints_dir,
            api=api,
            error=None,
        )
        text = render_text(payload)
        for name in (
            "broker_coverage_pct",
            "policy_denied_rate",
            "approval_pending_count",
            "event_ledger_lag_sec",
            "dispatcher_dead_letter",
            "sprint_blocked_count",
        ):
            assert name in text, f"missing {name} in text output"
        assert "alert=" in text

    def test_classify_critical_below_threshold(self) -> None:
        # broker_coverage_pct rule is op='<', threshold=95.0, severity=CRITICAL
        assert (
            status_cmd._classify(
                "broker_coverage_pct", 50.0, metrics_mod.ALARM_THRESHOLDS
            )
            == "CRITICAL"
        )
        assert (
            status_cmd._classify(
                "broker_coverage_pct", 100.0, metrics_mod.ALARM_THRESHOLDS
            )
            == "OK"
        )

    def test_classify_alarm_above_threshold(self) -> None:
        # policy_denied_rate rule is op='>', threshold=10.0, severity=ALARM
        assert (
            status_cmd._classify(
                "policy_denied_rate", 50.0, metrics_mod.ALARM_THRESHOLDS
            )
            == "ALARM"
        )
        assert (
            status_cmd._classify(
                "policy_denied_rate", 5.0, metrics_mod.ALARM_THRESHOLDS
            )
            == "OK"
        )

    def test_dispatcher_dead_letter_flagged_critical_on_real_event(
        self, sample_events_file: Path, empty_sprints_dir: Path
    ) -> None:
        api, _ = status_cmd._try_load_observability()
        payload = build_payload(
            events_path=sample_events_file,
            sprints_dir=empty_sprints_dir,
            api=api,
            error=None,
        )
        ddl = payload["metrics"]["dispatcher_dead_letter"]
        assert ddl["value"] == 1
        # rule is op='>', threshold=0, severity=CRITICAL
        assert ddl["alert"] == "CRITICAL"

    def test_sprint_blocked_count_uses_directory(
        self, sample_events_file: Path, sprints_dir_with_one_blocked: Path
    ) -> None:
        api, _ = status_cmd._try_load_observability()
        payload = build_payload(
            events_path=sample_events_file,
            sprints_dir=sprints_dir_with_one_blocked,
            api=api,
            error=None,
        )
        assert payload["metrics"]["sprint_blocked_count"]["value"] == 1

    def test_empty_events_returns_safe_defaults(
        self, empty_events_file: Path, empty_sprints_dir: Path
    ) -> None:
        api, _ = status_cmd._try_load_observability()
        payload = build_payload(
            events_path=empty_events_file,
            sprints_dir=empty_sprints_dir,
            api=api,
            error=None,
        )
        m = payload["metrics"]
        # broker coverage with no actions → 100.0 (OK, since rule is "<")
        assert m["broker_coverage_pct"]["value"] == 100.0
        assert m["broker_coverage_pct"]["alert"] == "OK"
        # other counts default to 0
        assert m["approval_pending_count"]["value"] == 0
        assert m["dispatcher_dead_letter"]["value"] == 0
        assert m["sprint_blocked_count"]["value"] == 0
        # nothing should be ALARM/CRITICAL on empty inputs
        for name, info in m.items():
            assert info["alert"] == "OK", f"{name} should be OK on empty input"


# ---------------------------------------------------------------------------
# Acceptance #2 — fallback when observability module unavailable.
# ---------------------------------------------------------------------------
class TestAcceptance2Fallback:
    def test_build_payload_when_api_none(self, tmp_path: Path) -> None:
        payload = build_payload(
            events_path=tmp_path / "events.jsonl",
            sprints_dir=tmp_path / "sprints",
            api=None,
            error="ImportError: simulated",
        )
        assert payload["status"] == "unavailable"
        assert payload["note"] == "observability_module_unavailable"
        assert payload["error"] == "ImportError: simulated"
        assert payload["metrics"] == {}
        assert "fallback" in payload

    def test_text_render_when_unavailable(self, tmp_path: Path) -> None:
        payload = build_payload(
            events_path=tmp_path / "events.jsonl",
            sprints_dir=tmp_path / "sprints",
            api=None,
            error="ModuleNotFoundError: x",
        )
        text = render_text(payload)
        assert "unavailable" in text.lower()
        assert "legacy" in text.lower() or "fallback" in text.lower()

    def test_main_does_not_raise_on_fallback(
        self, monkeypatch, tmp_path: Path, capsys
    ) -> None:
        monkeypatch.setattr(
            status_cmd,
            "_try_load_observability",
            lambda: (None, "ImportError: simulated"),
        )
        sprints = tmp_path / "sprints"
        sprints.mkdir()
        rc = main(
            [
                "--events-path",
                str(tmp_path / "missing.jsonl"),
                "--sprints-dir",
                str(sprints),
            ]
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "unavailable" in out.lower()

    def test_main_json_emits_unavailable_status(
        self, monkeypatch, tmp_path: Path, capsys
    ) -> None:
        monkeypatch.setattr(
            status_cmd,
            "_try_load_observability",
            lambda: (None, "ImportError: simulated"),
        )
        sprints = tmp_path / "sprints"
        sprints.mkdir()
        rc = main(
            [
                "--json",
                "--events-path",
                str(tmp_path / "missing.jsonl"),
                "--sprints-dir",
                str(sprints),
            ]
        )
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["schema_version"] == SCHEMA_VERSION
        assert payload["status"] == "unavailable"
        assert payload["note"] == "observability_module_unavailable"
        assert payload["metrics"] == {}

    def test_validate_payload_accepts_unavailable_status(self, tmp_path: Path) -> None:
        payload = build_payload(
            events_path=tmp_path / "events.jsonl",
            sprints_dir=tmp_path / "sprints",
            api=None,
            error="ImportError: simulated",
        )
        assert validate_payload(payload) == []


# ---------------------------------------------------------------------------
# Acceptance #3 — --json mode emits structured metrics.
# ---------------------------------------------------------------------------
class TestAcceptance3JsonMode:
    def test_json_payload_is_valid_json_with_schema_version(
        self, sample_events_file: Path, sprints_dir_with_one_blocked: Path, capsys
    ) -> None:
        rc = main(
            [
                "--json",
                "--events-path",
                str(sample_events_file),
                "--sprints-dir",
                str(sprints_dir_with_one_blocked),
            ]
        )
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["schema_version"] == SCHEMA_VERSION
        assert payload["status"] == "ok"
        assert len(payload["metrics"]) == 6

    def test_json_metric_shape(
        self, sample_events_file: Path, sprints_dir_with_one_blocked: Path, capsys
    ) -> None:
        rc = main(
            [
                "--json",
                "--events-path",
                str(sample_events_file),
                "--sprints-dir",
                str(sprints_dir_with_one_blocked),
            ]
        )
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        for name, info in payload["metrics"].items():
            assert isinstance(info, dict), f"{name} not object"
            assert "value" in info
            assert "alert" in info
            assert "threshold" in info
            assert info["alert"] in {"OK", "ALARM", "CRITICAL"}

    def test_json_threshold_matches_observability_registry(
        self, sample_events_file: Path, sprints_dir_with_one_blocked: Path, capsys
    ) -> None:
        rc = main(
            [
                "--json",
                "--events-path",
                str(sample_events_file),
                "--sprints-dir",
                str(sprints_dir_with_one_blocked),
            ]
        )
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        bc = payload["metrics"]["broker_coverage_pct"]["threshold"]
        assert bc["op"] == "<"
        assert bc["threshold"] == 95.0
        assert bc["severity"] == "CRITICAL"
        ddl = payload["metrics"]["dispatcher_dead_letter"]["threshold"]
        assert ddl["op"] == ">"
        assert ddl["threshold"] == 0
        assert ddl["severity"] == "CRITICAL"

    def test_default_text_mode_human_readable(
        self, sample_events_file: Path, sprints_dir_with_one_blocked: Path, capsys
    ) -> None:
        rc = main(
            [
                "--events-path",
                str(sample_events_file),
                "--sprints-dir",
                str(sprints_dir_with_one_blocked),
            ]
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "Solar-Harness Observability Metrics" in out
        assert "broker_coverage_pct" in out
        # at least one alert flag rendered
        assert "alert=" in out

    def test_validate_only_returns_zero_for_ok_payload(
        self, sample_events_file: Path, sprints_dir_with_one_blocked: Path, capsys
    ) -> None:
        rc = main(
            [
                "--validate-only",
                "--events-path",
                str(sample_events_file),
                "--sprints-dir",
                str(sprints_dir_with_one_blocked),
            ]
        )
        assert rc == 0
        assert "schema_ok" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# LR-01 — lazy import + isolation from execution_broker.
# ---------------------------------------------------------------------------
class TestLR01LazyImport:
    def test_status_cmd_module_does_not_reference_execution_broker(self) -> None:
        src = Path(status_cmd.__file__).read_text(encoding="utf-8")
        assert "execution_broker" not in src, (
            "LR-01 violation: status_cmd.py must not reference execution_broker"
        )

    def test_observability_metrics_does_not_reference_execution_broker(self) -> None:
        src = Path(metrics_mod.__file__).read_text(encoding="utf-8")
        assert "execution_broker" not in src, (
            "LR-01 violation: observability/metrics.py must not reference "
            "execution_broker"
        )

    def test_try_load_observability_success(self) -> None:
        api, error = status_cmd._try_load_observability()
        assert api is not None, f"observability load failed: {error}"
        assert error is None
        for fn_name in (
            "broker_coverage_pct",
            "policy_denied_rate",
            "approval_pending_count",
            "event_ledger_lag_sec",
            "dispatcher_dead_letter",
            "sprint_blocked_count",
            "iter_events_from_jsonl",
        ):
            assert callable(api[fn_name]), f"{fn_name} not callable"
        assert isinstance(api["ALARM_THRESHOLDS"], dict)
        assert len(api["ALARM_THRESHOLDS"]) == 6
