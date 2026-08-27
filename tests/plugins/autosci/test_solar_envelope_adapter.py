from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from harness.plugins.autosci.adapters.solar_envelope_to_autosci import (
    EnvelopeContractError,
    normalize_envelope,
)


BRIDGE = Path(__file__).resolve().parents[3] / "harness/plugins/autosci/bin/autosci_bridge.py"


def _scheduler_envelope(tmp_path: Path) -> dict:
    work_dir = tmp_path / "workdir"
    output_dir = work_dir / "artifacts" / "node-discover" / "literature"
    return {
        "task_id": "task-1",
        "sprint_id": "sprint-1",
        "node_id": "node-discover",
        "objective": "Find evidence about grid-storage batteries.",
        "work_dir": str(work_dir),
        "write_scope": [str(output_dir)],
        "artifact_routes": {
            "consumes": {},
            "produces": {
                "schemas/evidence/literature_discovery.v1.schema.json": str(output_dir)
            },
        },
    }


def test_scheduler_contract_is_translated_for_discovery(tmp_path: Path) -> None:
    envelope = _scheduler_envelope(tmp_path)

    normalized = normalize_envelope(envelope, action="discover_literature")

    assert normalized["output_dir"] == envelope["write_scope"][0]
    assert normalized["inputs"]["request"] == envelope["objective"]
    assert normalized["inputs"]["topic"] == envelope["objective"]
    assert normalized["mode"] == "solar_native"


def test_all_bridge_actions_receive_scheduler_output_route(tmp_path: Path) -> None:
    envelope = _scheduler_envelope(tmp_path)
    config_path = Path(__file__).resolve().parents[3] / "harness/config/physical-operators.json"
    operators = json.loads(config_path.read_text(encoding="utf-8"))["operators"]
    actions = {
        match.group(1)
        for operator in operators.values()
        if (
            match := re.search(
                r"autosci_bridge\.py.*--action\s+([a-z_]+)",
                str(operator.get("command") or ""),
            )
        )
    }
    assert len(actions) == 19
    for action in actions:
        normalized = normalize_envelope(envelope, action=action)
        assert normalized["output_dir"] == envelope["write_scope"][0], action


def test_legacy_fixture_envelope_keeps_legacy_defaults() -> None:
    normalized = normalize_envelope({"inputs": {"fixture": "sample.json"}})
    assert normalized["mode"] == "fixture"
    assert "output_dir" not in normalized


def test_explicit_values_are_preserved_when_they_match_contract(tmp_path: Path) -> None:
    envelope = _scheduler_envelope(tmp_path)
    envelope["mode"] = "fixture"
    envelope["output_dir"] = envelope["write_scope"][0] + "/"
    envelope["inputs"] = {"topic": "Explicit topic", "request": "Explicit request"}

    normalized = normalize_envelope(envelope, action="discover_literature")

    assert normalized["mode"] == "fixture"
    assert normalized["inputs"]["topic"] == "Explicit topic"
    assert normalized["inputs"]["request"] == "Explicit request"


def test_conflicting_legacy_output_fails_closed(tmp_path: Path) -> None:
    envelope = _scheduler_envelope(tmp_path)
    envelope["output_dir"] = str(tmp_path / "wrong")
    with pytest.raises(EnvelopeContractError, match="conflicts"):
        normalize_envelope(envelope, action="discover_literature")


def test_route_outside_write_scope_fails_closed(tmp_path: Path) -> None:
    envelope = _scheduler_envelope(tmp_path)
    envelope["write_scope"] = [str(tmp_path / "different")]
    with pytest.raises(EnvelopeContractError, match="write_scope"):
        normalize_envelope(envelope, action="discover_literature")


def test_multiple_output_destinations_fail_closed(tmp_path: Path) -> None:
    envelope = _scheduler_envelope(tmp_path)
    envelope["artifact_routes"]["produces"]["artifact.second.v1"] = str(tmp_path / "second")
    with pytest.raises(EnvelopeContractError, match="distinct artifact routes"):
        normalize_envelope(envelope, action="discover_literature")


def test_bridge_writes_result_inside_scheduler_route(tmp_path: Path) -> None:
    envelope = _scheduler_envelope(tmp_path)
    envelope["mode"] = "fixture"
    envelope["inputs"] = {
        "fixture_fallback": True,
        "allow_network_fetch": False,
        "topic": "grid-storage batteries",
        "limit": 1,
    }
    envelope_path = tmp_path / "operator-envelope.json"
    envelope_path.write_text(json.dumps(envelope), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(BRIDGE),
            "run",
            "--action",
            "discover_literature",
            "--envelope",
            str(envelope_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    output_dir = Path(envelope["write_scope"][0])
    assert (output_dir / "result.json").is_file()
    assert (output_dir / "discover_literature.evidence.json").is_file()
    assert (output_dir / "evidence.jsonl").is_file()
