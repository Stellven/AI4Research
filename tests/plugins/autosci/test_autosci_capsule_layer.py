"""The AutoSci bridge stages must be fully modelled in Solar's three layers.

The logical operators (Scientific*), the bindings, and the physical operators
(autosci-*-worker -> autosci_bridge.py) already existed, but no capability
capsule declared them. A node cannot bind a stage without a capsule, which is
why the fixed workflow reimplemented Part B as autosci-research-poc-*-worker
instead of using the bridge that was already built.
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

import yaml

HARNESS = Path(__file__).resolve().parents[3] / "harness"
CAPSULE_DIR = HARNESS / "config" / "capability-capsules"


def _physical() -> dict:
    return json.loads((HARNESS / "config/physical-operators.json").read_text(encoding="utf-8"))["operators"]


def _logical() -> dict:
    return json.loads((HARNESS / "config/logical-operators.json").read_text(encoding="utf-8"))["logical_operators"]


def _autosci_capsules() -> list[dict]:
    return [
        yaml.safe_load(Path(p).read_text(encoding="utf-8"))
        for p in sorted(glob.glob(str(CAPSULE_DIR / "cap.autosci-*.yaml")))
    ]


def test_autosci_capsules_exist_for_the_part_b_bridge_stages() -> None:
    ids = {c["capability_capsule_id"] for c in _autosci_capsules()}
    for required in (
        "cap.autosci-idea-generation",
        "cap.autosci-idea-evaluation",
        "cap.autosci-experiment-design",
        "cap.autosci-experiment-run",
        "cap.autosci-experiment-monitor",
        "cap.autosci-claim-verification",
        "cap.autosci-report-delivery",
    ):
        assert required in ids, f"missing capsule {required}"


def test_every_autosci_capsule_binds_a_real_worker_and_logical_operator() -> None:
    physical, logical = _physical(), _logical()
    for capsule in _autosci_capsules():
        cid = capsule["capability_capsule_id"]
        worker = capsule["operator_compatibility"]["preferred"][0]
        assert worker in physical, f"{cid} names unknown physical operator {worker}"
        assert physical[worker].get("enabled") is True, f"{cid} worker {worker} is disabled"
        op = capsule["metadata"].get("logical_operator")
        assert op in logical, f"{cid} names unknown logical operator {op}"


def test_autosci_capsule_workers_actually_invoke_the_bridge() -> None:
    """The whole point is that these stages run AutoSci, not a Solar
    reimplementation. Assert the bound worker really shells out to
    autosci_bridge.py with a concrete --action."""
    physical = _physical()
    for capsule in _autosci_capsules():
        worker = capsule["operator_compatibility"]["preferred"][0]
        command = str(physical[worker].get("command") or "")
        assert "autosci_bridge.py" in command, f"{worker} does not invoke the AutoSci bridge"
        assert "--action" in command, f"{worker} does not name a bridge action"


def test_autosci_capsules_are_registered() -> None:
    registry = yaml.safe_load((HARNESS / "config/capability-capsules.registry.yaml").read_text(encoding="utf-8"))
    # The registry groups entries by capsule_kind: {"capsules": {"capability": [...], ...}}
    registered = {
        str(entry.get("capability_capsule_id"))
        for group in (registry.get("capsules") or {}).values()
        for entry in (group if isinstance(group, list) else [])
        if isinstance(entry, dict)
    }
    for capsule in _autosci_capsules():
        assert capsule["capability_capsule_id"] in registered, (
            f"{capsule['capability_capsule_id']} is not in the capsule registry"
        )
