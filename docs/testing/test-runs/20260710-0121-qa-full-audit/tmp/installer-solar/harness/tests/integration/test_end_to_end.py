"""End-to-end integration tests for S03 Core Runtime (N9).

Drives real action_contracts through the live N3 ExecutionBroker, observes
the N2 EventLedger, rebuilds sprint status via the N8 projection, and
asserts the N9 activation-proof broker_coverage meets PASS criteria
(coverage_ratio == 1.0, uncontracted == 0, unscoped == 0, by_kind covers
all three action kinds).

No mocks are used for the runtime modules under test:
    N2 EventLedger        -> real SQLite WAL + JSONL writes (tmp_path)
    N3 ExecutionBroker    -> real propose_action chain (validate -> policy
                              -> lease -> execute -> verify -> commit)
    N4 policy             -> real RISK_CLASS_TABLE + write_scope checks
    N7 failure_handler    -> real classify() on synthesised failures
    N8 projections        -> real build_sprint_status replay
    N9 activation_proof   -> real compute_broker_coverage + CLI subprocess
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

# Inject harness/lib so the package-style imports below also pick up
# legacy direct imports inside execution_broker.py (it tries both).
_HARNESS_ROOT = Path(__file__).resolve().parents[2]
_LIB = str(_HARNESS_ROOT / "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)
_PROJECT_ROOT = _HARNESS_ROOT.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from harness.lib.event_ledger import EventLedger  # noqa: E402
from harness.lib.execution_broker import (  # noqa: E402
    ExecutionBroker,
    ExecOutcome,
    SCHEMA_VERSION,
    UncontractedActionError,
)
from harness.lib.projections import build_sprint_status  # noqa: E402
from harness.lib.failure_handler import (  # noqa: E402
    EXECUTION_FAILED,
    VERIFICATION_FAILED,
    classify,
)
from harness.tests.integration.activation_proof_runner import (  # noqa: E402
    SCHEMA_FIELDS,
    build_report,
    compute_broker_coverage,
    compute_ledger_lag_seconds,
)

SPRINT_ID = "sprint-n9-integration-test"
NODE_ID = "N9"
SCHEMAS_DIR = _HARNESS_ROOT / "schemas"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ledger(tmp_path) -> EventLedger:
    return EventLedger(base_dir=str(tmp_path / "run"))


@pytest.fixture
def sandbox_root(tmp_path) -> Path:
    root = tmp_path / "sandbox"
    root.mkdir()
    return root


def _make_contract(
    action_id: str,
    kind: str,
    *,
    intent: str,
    write_set: List[str],
    risk_class: str = "low",
    rollback_kind: str = "none",
) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "action_id": action_id,
        "node_id": NODE_ID,
        "kind": kind,
        "intent": intent,
        "read_set": [],
        "write_set": write_set,
        "required_capabilities": ["python", "testing"],
        "preconditions": [],
        "success_predicates": [],
        "verification": {"static": True, "runtime": [], "evidence": []},
        "risk_class": risk_class,
        "approval_required": False,
        "rollback": {"kind": rollback_kind, "target": list(write_set)},
    }


def _shell_executor(contract: Dict[str, Any]) -> ExecOutcome:
    return ExecOutcome(
        exit_code=0,
        stdout=f"ran:{contract['intent']}",
        evidence_refs=[f"shell:{contract['action_id']}"],
    )


def _file_write_executor_factory(sandbox_root: Path):
    def executor(contract: Dict[str, Any]) -> ExecOutcome:
        target = contract["write_set"][0]
        path = sandbox_root / Path(target).name
        path.write_text(f"written by {contract['action_id']}\n", encoding="utf-8")
        return ExecOutcome(
            exit_code=0,
            stdout=f"wrote:{path}",
            evidence_refs=[f"file_write:{path}"],
        )

    return executor


def _tool_call_executor(contract: Dict[str, Any]) -> ExecOutcome:
    return ExecOutcome(
        exit_code=0,
        stdout=json.dumps({"tool": contract["intent"], "ok": True}),
        evidence_refs=[f"tool_call:{contract['action_id']}"],
    )


def _make_broker(ledger: EventLedger, sandbox_root: Path) -> ExecutionBroker:
    write_scope = [str(sandbox_root)]
    return ExecutionBroker(
        ledger,
        sprint_id=SPRINT_ID,
        node_write_scope=write_scope,
        executors={
            "shell": _shell_executor,
            "file_write": _file_write_executor_factory(sandbox_root),
            "tool_call": _tool_call_executor,
        },
    )


# ---------------------------------------------------------------------------
# AC1: action -> event -> projection -> activation-proof chain
# ---------------------------------------------------------------------------


def test_full_chain_action_event_projection_proof(ledger, sandbox_root):
    broker = _make_broker(ledger, sandbox_root)
    contracts = [
        _make_contract("A1", "shell", intent="echo hello", write_set=[]),
        _make_contract(
            "A2",
            "file_write",
            intent="write smoke marker",
            write_set=[str(sandbox_root / "marker.txt")],
            risk_class="medium",
            rollback_kind="file_delete",
        ),
        _make_contract(
            "A3",
            "tool_call",
            intent="solar-harness context inject",
            write_set=[],
            risk_class="medium",
        ),
    ]
    for contract in contracts:
        result = broker.propose_action(contract)
        assert result.final_state == "committed", (
            f"{contract['action_id']} not committed: state={result.final_state} "
            f"reason={result.reason} detail={result.detail}"
        )

    events = ledger.replay(SPRINT_ID)
    event_types = {ev["event_type"] for ev in events}
    assert "action.proposed" in event_types
    assert "action.executed" in event_types
    assert "verifier.verdict" in event_types
    assert "projection.updated" in event_types

    projection = build_sprint_status(SPRINT_ID, ledger=ledger)
    assert projection["sprint_id"] == SPRINT_ID
    assert projection["event_count"] == len(events)
    assert projection["state_hash"]

    report = build_report(SPRINT_ID, ledger=ledger)
    coverage = report["broker_coverage"]
    assert set(coverage.keys()) == set(SCHEMA_FIELDS), (
        f"broker_coverage missing/extra keys: {sorted(coverage.keys())}"
    )
    assert coverage["health"] == "PASS"
    assert coverage["coverage_ratio"] == 1.0
    assert coverage["uncontracted_action_count"] == 0
    assert coverage["unscoped_write_count"] == 0
    assert coverage["total_actions"] == 3
    assert coverage["contracted_actions"] == 3
    assert coverage["by_kind"] == {"shell": 1, "file_write": 1, "tool_call": 1}
    assert coverage["legacy_path_actions"] == 0

    assert report["event_ledger_lag_seconds"] < 5.0
    assert (sandbox_root / "marker.txt").exists()


# ---------------------------------------------------------------------------
# AC2: broker_coverage payload conforms to broker_coverage.schema.json
# ---------------------------------------------------------------------------


def test_broker_coverage_conforms_to_schema(ledger, sandbox_root):
    broker = _make_broker(ledger, sandbox_root)
    broker.propose_action(_make_contract("A1", "shell", intent="ls", write_set=[]))
    broker.propose_action(_make_contract("A2", "tool_call", intent="ping", write_set=[]))

    coverage = compute_broker_coverage(ledger.replay(SPRINT_ID))

    try:
        from jsonschema import Draft202012Validator
    except ImportError:  # pragma: no cover - dev env always has jsonschema
        pytest.skip("jsonschema not installed")

    schema = json.loads((SCHEMAS_DIR / "broker_coverage.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(coverage)


# ---------------------------------------------------------------------------
# AC3: coverage degrades when uncontracted action is observed
# ---------------------------------------------------------------------------


def test_uncontracted_action_drives_health_fail(ledger):
    # Synthesise an action.executed without a matching action.proposed +
    # policy.verdict PASS — this is exactly what an uncontracted bypass
    # would look like in the event log.
    ledger.append(
        {
            "event_type": "action.executed",
            "sprint_id": SPRINT_ID,
            "node_id": NODE_ID,
            "actor": "legacy_dispatcher",
            "payload": {
                "action_id": "X9",
                "exit_code": 0,
                "output_hash": "sha256:deadbeef",
            },
        }
    )
    coverage = compute_broker_coverage(ledger.replay(SPRINT_ID))
    assert coverage["uncontracted_action_count"] == 1
    assert coverage["health"] == "FAIL"
    assert coverage["coverage_ratio"] == 1.0  # 0/0 -> 1.0 by convention
    assert coverage["total_actions"] == 0
    assert coverage["contracted_actions"] == 0


# ---------------------------------------------------------------------------
# AC4: unscoped file_write denial increments unscoped_write_count
# ---------------------------------------------------------------------------


def test_unscoped_write_denial_counts(ledger, sandbox_root, tmp_path):
    broker = _make_broker(ledger, sandbox_root)
    outside_path = tmp_path / "outside" / "evil.txt"
    contract = _make_contract(
        "A1",
        "file_write",
        intent="write outside node scope",
        write_set=[str(outside_path)],
        risk_class="medium",
        rollback_kind="file_delete",
    )
    result = broker.propose_action(contract)
    assert result.final_state == "policy_denied"
    assert "write_scope" in (result.detail or "")

    coverage = compute_broker_coverage(ledger.replay(SPRINT_ID))
    assert coverage["unscoped_write_count"] == 1
    assert coverage["health"] == "FAIL"
    assert coverage["total_actions"] == 1
    assert coverage["contracted_actions"] == 0
    # by_kind still reflects the proposal even when denied
    assert coverage["by_kind"]["file_write"] == 1


# ---------------------------------------------------------------------------
# AC5: failure_handler integration — failing action emits classifiable event
# ---------------------------------------------------------------------------


def test_failed_execution_is_classifiable_from_ledger(ledger, sandbox_root):
    def failing_executor(_: Dict[str, Any]) -> ExecOutcome:
        return ExecOutcome(exit_code=2, stderr="boom", crashed=False)

    broker = ExecutionBroker(
        ledger,
        sprint_id=SPRINT_ID,
        node_write_scope=[str(sandbox_root)],
        executors={"shell": failing_executor},
    )
    contract = _make_contract("A1", "shell", intent="exit 2", write_set=[])
    result = broker.propose_action(contract)
    assert result.final_state == "exec_failed"

    failed_events = [
        ev
        for ev in ledger.replay(SPRINT_ID)
        if ev["event_type"] in {"action.failed", "action.executed"}
        and (ev.get("payload") or {}).get("exit_code", 0) != 0
        or ev["event_type"] == "action.failed"
    ]
    assert failed_events, "no failure events in ledger"
    # Use N7 classifier — the same one S05 will use to repair sprints.
    classification = classify(failed_events[0])
    assert classification in {EXECUTION_FAILED, VERIFICATION_FAILED}


# ---------------------------------------------------------------------------
# AC6: ledger lag stays under 5.0s during active replay
# ---------------------------------------------------------------------------


def test_ledger_lag_below_threshold(ledger, sandbox_root):
    broker = _make_broker(ledger, sandbox_root)
    broker.propose_action(_make_contract("A1", "shell", intent="echo", write_set=[]))
    events = ledger.replay(SPRINT_ID)
    lag = compute_ledger_lag_seconds(events)
    assert 0.0 <= lag < 5.0, f"lag should be <5s during active sprint, got {lag}"


# ---------------------------------------------------------------------------
# AC7: uncontracted call to propose_action raises (GEMS-mode bypass guard)
# ---------------------------------------------------------------------------


def test_uncontracted_propose_action_raises(ledger, sandbox_root):
    broker = _make_broker(ledger, sandbox_root)
    with pytest.raises(UncontractedActionError):
        broker.propose_action(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# AC8: legacy_path_actions counts action.proposed events tagged legacy=true
# ---------------------------------------------------------------------------


def test_legacy_path_actions_counted(ledger):
    ledger.append(
        {
            "event_type": "action.proposed",
            "sprint_id": SPRINT_ID,
            "node_id": NODE_ID,
            "actor": "legacy_adapter",
            "payload": {"action_id": "L1", "kind": "shell", "legacy": True},
        }
    )
    ledger.append(
        {
            "event_type": "policy.verdict",
            "sprint_id": SPRINT_ID,
            "node_id": NODE_ID,
            "actor": "legacy_adapter",
            "payload": {"action_id": "L1", "verdict": "PASS"},
        }
    )
    ledger.append(
        {
            "event_type": "action.executed",
            "sprint_id": SPRINT_ID,
            "node_id": NODE_ID,
            "actor": "legacy_adapter",
            "payload": {"action_id": "L1", "exit_code": 0},
        }
    )

    coverage = compute_broker_coverage(ledger.replay(SPRINT_ID))
    assert coverage["legacy_path_actions"] == 1
    assert coverage["health"] == "PASS"


# ---------------------------------------------------------------------------
# AC9: activation_proof_runner CLI exits 0 on PASS, 1 on FAIL
# ---------------------------------------------------------------------------


def _run_cli(base_dir: Path, sid: str, out: Path) -> subprocess.CompletedProcess:
    cmd = [
        sys.executable,
        "-m",
        "harness.tests.integration.activation_proof_runner",
        "--sid",
        sid,
        "--base-dir",
        str(base_dir),
        "--out",
        str(out),
    ]
    return subprocess.run(
        cmd,
        cwd=str(_PROJECT_ROOT),
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(_PROJECT_ROOT)},
    )


def test_activation_proof_runner_cli_exit_zero(tmp_path, sandbox_root):
    base = tmp_path / "run"
    ledger = EventLedger(base_dir=str(base))
    broker = ExecutionBroker(
        ledger,
        sprint_id=SPRINT_ID,
        node_write_scope=[str(sandbox_root)],
        executors={
            "shell": _shell_executor,
            "file_write": _file_write_executor_factory(sandbox_root),
            "tool_call": _tool_call_executor,
        },
    )
    broker.propose_action(_make_contract("A1", "shell", intent="echo", write_set=[]))
    broker.propose_action(
        _make_contract(
            "A2",
            "file_write",
            intent="touch marker",
            write_set=[str(sandbox_root / "m.txt")],
            risk_class="medium",
            rollback_kind="file_delete",
        )
    )
    broker.propose_action(_make_contract("A3", "tool_call", intent="ping", write_set=[]))

    out_path = tmp_path / "report.json"
    proc = _run_cli(base, SPRINT_ID, out_path)
    assert proc.returncode == 0, f"runner exit={proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    report = json.loads(out_path.read_text())
    assert report["broker_coverage"]["health"] == "PASS"
    assert report["broker_coverage"]["coverage_ratio"] == 1.0
    assert report["event_ledger_lag_seconds"] < 5.0


def test_activation_proof_runner_cli_exit_nonzero_on_fail(tmp_path):
    base = tmp_path / "run"
    ledger = EventLedger(base_dir=str(base))
    # An uncontracted execution synthesised directly into the ledger.
    ledger.append(
        {
            "event_type": "action.executed",
            "sprint_id": SPRINT_ID,
            "node_id": NODE_ID,
            "actor": "legacy_dispatcher",
            "payload": {"action_id": "X9", "exit_code": 0},
        }
    )
    out_path = tmp_path / "report.json"
    proc = _run_cli(base, SPRINT_ID, out_path)
    assert proc.returncode == 1, f"expected exit 1 on FAIL, got {proc.returncode}"
    report = json.loads(out_path.read_text())
    assert report["broker_coverage"]["health"] == "FAIL"
    assert report["broker_coverage"]["uncontracted_action_count"] == 1
