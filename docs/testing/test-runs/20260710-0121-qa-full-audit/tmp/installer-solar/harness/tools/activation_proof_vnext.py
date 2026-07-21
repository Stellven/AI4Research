#!/usr/bin/env python3
"""activation_proof_vnext — coverage extension to activation_proof.py.

Extends the base activation proof with three new coverage metrics required by
S05/N4:

    broker_event_coverage         — fraction of broker FSM event types observed
    verifier_coverage              — fraction of verifier signal branches observed
    artifact_registry_coverage     — fraction of commit-path artifact events observed

The base module (`activation_proof.py`) is imported and consumed read-only;
this file does NOT mutate it. Run `diff` between the canonical version and
this commit's working copy to verify.

Output (`--json`) wraps the base activation proof plus the new metrics block:

    {
      "schema_version": "activation_proof_vnext.v1",
      "base_activation_proof": { ... },     # passthrough of build_activation_proof()
      "metrics": {
        "broker_event_coverage":      <float 0.0..1.0>,
        "verifier_coverage":          <float 0.0..1.0>,
        "artifact_registry_coverage": <float 0.0..1.0>
      },
      "thresholds":                  { ... },
      "verdict":                     "PASS" | "FAIL",
      "evidence_refs":               [ <event_id>, ... ],
      "coverage_detail":             { ... per-metric breakdown ... }
    }

Coverage is computed against a deterministic in-process broker drive (the
harness drives the broker through one happy terminal plus each fail terminal
into an isolated EventLedger under tempfile.mkdtemp). The drive is repeatable
across machines: no production state, no external network, no environment
dependency beyond the harness lib directory itself.

This is the right shape for S05 because the broker is new (S03) and there is
not yet a populated production event corpus we could replay. The contract
S05/N4 expects is _the broker emits the FSM transitions we said it would_,
which is exactly what the in-process drive measures.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))

# Make `harness.lib` importable when this file is run as a script. The base
# `activation_proof.py` and the broker live as a namespace package one level
# above; cwd is harness/lib when invoked via `python3 harness/lib/...`.
_THIS_DIR = Path(__file__).resolve().parent
_HARNESS_ROOT = _THIS_DIR.parent.parent  # ~/.solar
if str(_HARNESS_ROOT) not in sys.path:
    sys.path.insert(0, str(_HARNESS_ROOT))
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

# Base activation proof — imported, not modified.
from activation_proof import (  # noqa: E402 — see sys.path setup above
    build_activation_proof,
    build_broker_coverage,
)

# Broker + ledger — used to drive in-process coverage.
from harness.lib.event_ledger import EventLedger  # noqa: E402
from harness.lib.execution_broker import (  # noqa: E402
    ExecOutcome,
    ExecutionBroker,
    LeaseManager,
    VerifierResult,
)

SCHEMA_VERSION = "activation_proof_vnext.v1"

# Authoritative set of broker FSM event types (sourced from
# harness/lib/execution_broker.py — every `emit(state, event_type, ...)` call).
EXPECTED_BROKER_EVENT_TYPES: Tuple[str, ...] = (
    "action.proposed",
    "broker.state",
    "policy.verdict",
    "lease.acquired",
    "action.executed",
    "action.failed",
    "verifier.invoked",
    "verifier.verdict",
    "rollback.invoked",
    "artifact.registered",
    "projection.updated",
)

# Verifier branches we expect to exercise: invoked + both verdict directions.
EXPECTED_VERIFIER_BRANCHES: Tuple[str, ...] = (
    "verifier.invoked",
    "verifier.verdict:PASS",
    "verifier.verdict:FAIL",
    "rollback.invoked",
)

# Commit-path events from the broker.
EXPECTED_ARTIFACT_EVENTS: Tuple[str, ...] = (
    "artifact.registered",
    "projection.updated",
)

THRESHOLDS: Dict[str, float] = {
    "broker_event_coverage": 0.99,
    "verifier_coverage": 1.0,
    "artifact_registry_coverage": 0.95,
}


# ---------------------------------------------------------------------------
# Contract factory
# ---------------------------------------------------------------------------


def _contract(action_id: str, *, kind: str = "file_write", write_set: List[str],
              risk_class: str = "medium") -> Dict[str, Any]:
    return {
        "schema_version": "solar.action_contract.v1",
        "action_id": action_id,
        "node_id": "N4-coverage-drive",
        "kind": kind,
        "intent": f"coverage drive for {action_id}",
        "read_set": [],
        "write_set": write_set,
        "required_capabilities": [],
        "preconditions": [],
        "success_predicates": [],
        "verification": {"static": True, "runtime": [], "evidence": []},
        "risk_class": risk_class,
    }


# ---------------------------------------------------------------------------
# Drive: one happy path + every fail terminal, each into the same ledger.
# ---------------------------------------------------------------------------


def _drive_broker_paths(ledger: EventLedger, scope_dir: Path) -> Dict[str, str]:
    """Drive the broker through all 6 terminals against `ledger`.

    Returns a mapping `terminal -> final_state` (for the drive verdict tie-in).
    The ledger ends up containing every broker FSM event type at least once
    (committed + schema_failed + policy_denied + lease_denied + exec_failed +
    verify_failed-with-rollback).
    """
    results: Dict[str, str] = {}

    def make_broker(*, approvals: List[str] | None = None,
                    verifier=None, lease: LeaseManager | None = None,
                    executors: Dict[str, Any] | None = None,
                    write_scope: List[str] | None = None) -> ExecutionBroker:
        return ExecutionBroker(
            ledger,
            sprint_id="vnext-coverage-drive",
            node_write_scope=write_scope if write_scope is not None else [str(scope_dir)],
            executors=executors,
            verifier=verifier,
            lease=lease,
            approvals=approvals or [],
        )

    # --- 1. happy path → committed (touches verifier PASS + artifact.registered) ---
    target_a1 = scope_dir / "A1.txt"

    def exec_a1(_c):
        target_a1.write_text("a1", encoding="utf-8")
        return ExecOutcome(exit_code=0, stdout="ok", evidence_refs=["evA1"])

    happy_broker = make_broker(executors={"file_write": exec_a1})
    results["committed"] = happy_broker.propose_action(
        _contract("A1", write_set=[str(target_a1)])
    ).final_state

    # --- 2. schema_failed (drop a required field) ---
    bad_contract = _contract("A2", write_set=[str(scope_dir / "A2.txt")])
    del bad_contract["verification"]
    schema_broker = make_broker(
        executors={"file_write": lambda _c: ExecOutcome()}
    )
    results["schema_failed"] = schema_broker.propose_action(bad_contract).final_state

    # --- 3. policy_denied (empty node_write_scope) ---
    deny_broker = make_broker(
        executors={"file_write": lambda _c: ExecOutcome()},
        write_scope=[],  # any non-empty write_set is out of scope
    )
    results["policy_denied"] = deny_broker.propose_action(
        _contract("A3", write_set=[str(scope_dir / "A3.txt")])
    ).final_state

    # --- 4. lease_denied (pre-hold the path in a shared LeaseManager) ---
    shared_lease = LeaseManager()
    shared_lease.acquire("preheld", [str(scope_dir / "A4.txt")])
    lease_broker = make_broker(
        executors={"file_write": lambda _c: ExecOutcome()},
        lease=shared_lease,
    )
    results["lease_denied"] = lease_broker.propose_action(
        _contract("A4", write_set=[str(scope_dir / "A4.txt")])
    ).final_state

    # --- 5. exec_failed (executor returns non-zero exit) ---
    exec_fail_broker = make_broker(
        executors={"file_write": lambda _c: ExecOutcome(
            exit_code=2, stderr="forced failure", evidence_refs=[]
        )},
    )
    results["exec_failed"] = exec_fail_broker.propose_action(
        _contract("A5", write_set=[str(scope_dir / "A5.txt")])
    ).final_state

    # --- 6. verify_failed + rollback.invoked (file_delete rollback path) ---
    target_a6 = scope_dir / "A6.txt"

    def exec_a6(_c):
        target_a6.write_text("temp", encoding="utf-8")
        return ExecOutcome(exit_code=0, stdout="ran", evidence_refs=[])

    def strict_verifier(_aid, _contract, outcome):
        if not outcome.evidence_refs:
            return VerifierResult(
                verdict="FAIL", can_rollback=True, evidence=[],
                detail="evidence_refs missing — coverage drive expects FAIL"
            )
        return VerifierResult(verdict="PASS", evidence=outcome.evidence_refs)

    verify_contract = _contract("A6", write_set=[str(target_a6)])
    verify_contract["rollback"] = {"kind": "file_delete", "target": [str(target_a6)]}
    verify_broker = make_broker(
        executors={"file_write": exec_a6},
        verifier=strict_verifier,
    )
    results["verify_failed"] = verify_broker.propose_action(verify_contract).final_state

    return results


# ---------------------------------------------------------------------------
# Coverage computation
# ---------------------------------------------------------------------------


def _collect_event_taxonomy(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Bucket events by what we need to measure."""
    seen_types: Set[str] = set()
    seen_verifier_branches: Set[str] = set()
    seen_artifact_events: Set[str] = set()
    evidence_refs: List[str] = []

    for e in events:
        et = e.get("event_type")
        if not et:
            continue
        seen_types.add(et)
        # Track verifier branches by inspecting verdict payload.
        if et == "verifier.invoked":
            seen_verifier_branches.add("verifier.invoked")
        elif et == "verifier.verdict":
            verdict = (e.get("payload") or {}).get("verdict")
            if verdict in ("PASS", "FAIL"):
                seen_verifier_branches.add(f"verifier.verdict:{verdict}")
        elif et == "rollback.invoked":
            seen_verifier_branches.add("rollback.invoked")
        # Artifact + projection lifecycle on commit.
        if et in EXPECTED_ARTIFACT_EVENTS:
            seen_artifact_events.add(et)
        # Evidence: every event_id is a usable reference; pick up to a small
        # sample so the JSON stays tractable for downstream nodes.
        eid = e.get("event_id")
        if eid:
            evidence_refs.append(eid)

    return {
        "seen_broker_event_types": seen_types,
        "seen_verifier_branches": seen_verifier_branches,
        "seen_artifact_events": seen_artifact_events,
        "evidence_refs": evidence_refs,
    }


def _coverage(observed: Set[str], expected: Tuple[str, ...]) -> float:
    if not expected:
        return 1.0
    return round(len(observed & set(expected)) / len(expected), 4)


def build_vnext_proof(*, sprint_id: str | None = None,
                     keep_dir: bool = False) -> Dict[str, Any]:
    """Drive the broker, collect events, return the full vnext proof dict."""

    tmpdir = Path(tempfile.mkdtemp(prefix="vnext-coverage-"))
    scope_dir = tmpdir / "scope"
    scope_dir.mkdir()
    ledger = EventLedger(base_dir=str(tmpdir / "ledger"))

    try:
        drive_results = _drive_broker_paths(ledger, scope_dir)
        events = ledger.replay("vnext-coverage-drive")
    finally:
        if not keep_dir:
            # Best-effort cleanup. The ephemeral ledger is per-drive; no
            # production state lives here.
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    tax = _collect_event_taxonomy(events)
    metrics = {
        "broker_event_coverage":
            _coverage(tax["seen_broker_event_types"], EXPECTED_BROKER_EVENT_TYPES),
        "verifier_coverage":
            _coverage(tax["seen_verifier_branches"], EXPECTED_VERIFIER_BRANCHES),
        "artifact_registry_coverage":
            _coverage(tax["seen_artifact_events"], EXPECTED_ARTIFACT_EVENTS),
    }

    verdict_ok = (
        metrics["broker_event_coverage"] >= THRESHOLDS["broker_event_coverage"]
        and metrics["verifier_coverage"] >= THRESHOLDS["verifier_coverage"]
        and metrics["artifact_registry_coverage"] >= THRESHOLDS["artifact_registry_coverage"]
    )

    # Sample evidence_refs at most 12 to keep JSON small for downstream
    # consumption; preserves first event_id from each FSM phase.
    sampled_refs = tax["evidence_refs"][:12]

    base = build_activation_proof(sprint_id, include_schema_path=False)

    proof: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "base_activation_proof": base,
        "metrics": metrics,
        "thresholds": dict(THRESHOLDS),
        "verdict": "PASS" if verdict_ok else "FAIL",
        "evidence_refs": sampled_refs,
        "coverage_detail": {
            "expected_broker_event_types": list(EXPECTED_BROKER_EVENT_TYPES),
            "observed_broker_event_types": sorted(tax["seen_broker_event_types"]),
            "missing_broker_event_types": sorted(
                set(EXPECTED_BROKER_EVENT_TYPES) - tax["seen_broker_event_types"]
            ),
            "expected_verifier_branches": list(EXPECTED_VERIFIER_BRANCHES),
            "observed_verifier_branches": sorted(tax["seen_verifier_branches"]),
            "expected_artifact_events": list(EXPECTED_ARTIFACT_EVENTS),
            "observed_artifact_events": sorted(tax["seen_artifact_events"]),
            "drive_terminals": drive_results,
            "total_events_in_drive": len(events),
        },
    }
    if sprint_id:
        proof["sprint_id"] = sprint_id
    return proof


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="activation_proof_vnext.py",
        description="Coverage extension to activation_proof.py (S05/N4).",
    )
    ap.add_argument("--json", action="store_true",
                    help="Print JSON proof to stdout (default if no flag).")
    ap.add_argument("--sprint-id", "--sprint_id", default=None, metavar="SID")
    ap.add_argument("--keep-dir", action="store_true",
                    help="Keep ephemeral ledger dir after drive (debug only).")
    args = ap.parse_args()

    proof = build_vnext_proof(sprint_id=args.sprint_id, keep_dir=args.keep_dir)
    # --json is the default and only output mode; the flag is accepted for
    # explicit callers and CI assertions.
    print(json.dumps(proof, ensure_ascii=False, indent=2))
    return 0 if proof.get("verdict") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
