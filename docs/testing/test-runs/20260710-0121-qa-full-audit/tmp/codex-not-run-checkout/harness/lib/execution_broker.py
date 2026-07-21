"""ExecutionBroker — S03 N3.

Implements the broker FSM declared in
sprint-20260519-...-s02-architecture.state-machines.md §2 and
sprint-20260519-...-s03-core-runtime.design.md §6.2 / §7.

State enumeration (acceptance row literal, design.md §7 naming):

    happy:  proposed → validated → policy_passed → leased
                     → executing → verified → committed
    fail:   schema_failed | policy_denied | lease_denied
          | exec_failed   | verify_failed

`propose_action(contract)` is the single entry point — it drives the
contract through validate → policy → lease → execute → capture →
verify → commit/revert and emits one event per transition into the
injected EventLedger. Every state, including each terminal, has an
event record in the ledger; tests assert transitions by reading back
`ActionResult.history` and `ledger.replay()`.

Three action kinds (shell / file_write / tool_call) are accepted by the
broker; executors are injected per-kind so this module stays
side-effect free for testing. python / research_extract / human_approval
are accepted by schema but require explicitly injected executors.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

# Policy module (N4 deliverable). Import-time dependency is intentional
# because the broker is the single enforcement point: there is no
# meaningful broker without policy. Support both package imports
# (`harness.lib.execution_broker`) and legacy direct test imports
# (`execution_broker` with harness/lib on sys.path).
try:
    from harness.lib.policy.action_policy import classify_action
    from harness.lib.policy.approval_policy import check as check_approval_required
    from harness.lib.policy.write_scope_policy import check as check_write_scope
except ModuleNotFoundError:  # pragma: no cover - legacy direct import path
    from policy.action_policy import classify_action
    from policy.approval_policy import check as check_approval_required
    from policy.write_scope_policy import check as check_write_scope

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants & types
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "solar.action_contract.v1"

SUPPORTED_KINDS = (
    "shell",
    "file_write",
    "tool_call",
    "python",
    "research_extract",
    "human_approval",
)

RISK_CLASSES = ("low", "medium", "high")

HAPPY_STATES = (
    "proposed",
    "validated",
    "policy_passed",
    "leased",
    "executing",
    "verified",
    "committed",
)
FAIL_STATES = (
    "schema_failed",
    "policy_denied",
    "lease_denied",
    "exec_failed",
    "verify_failed",
)
ALL_STATES = HAPPY_STATES + FAIL_STATES
TERMINAL_STATES = {"committed"} | set(FAIL_STATES)


class BrokerError(Exception):
    """Base broker error."""


class UncontractedActionError(BrokerError):
    """Raised when propose_action is called without a contract.

    The broker is GEMS-mode: no contract = no execution. Uncontracted
    actions must crash loudly so the caller learns to register one
    upstream rather than silently bypassing the broker.
    """


# ---------------------------------------------------------------------------
# Data carriers
# ---------------------------------------------------------------------------


@dataclass
class ExecOutcome:
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    crashed: bool = False
    output_hash: Optional[str] = None
    evidence_refs: List[str] = field(default_factory=list)


@dataclass
class VerifierResult:
    verdict: str  # "PASS" or "FAIL"
    can_rollback: bool = True
    evidence: List[str] = field(default_factory=list)
    detail: str = ""


@dataclass
class ActionResult:
    action_id: str
    final_state: str
    history: List[str]
    events: List[str]
    reason: Optional[str] = None
    detail: Optional[str] = None


# ---------------------------------------------------------------------------
# Lease manager (in-process; the real one will sit in front of harness.run/)
# ---------------------------------------------------------------------------


class LeaseManager:
    def __init__(self) -> None:
        self._held: Dict[str, str] = {}

    def acquire(self, action_id: str, write_set: List[str]) -> Tuple[bool, str]:
        for path in write_set:
            holder = self._held.get(path)
            if holder is not None and holder != action_id:
                return False, f"lease conflict on '{path}' (held by {holder})"
        for path in write_set:
            self._held[path] = action_id
        return True, "lease acquired"

    def release(self, action_id: str) -> None:
        self._held = {p: h for p, h in self._held.items() if h != action_id}

    def held(self) -> Dict[str, str]:
        return dict(self._held)


# ---------------------------------------------------------------------------
# Default verifier
# ---------------------------------------------------------------------------


def _default_verifier(action_id: str, contract: dict, outcome: ExecOutcome) -> VerifierResult:
    if outcome.crashed or outcome.exit_code != 0:
        return VerifierResult(verdict="FAIL", can_rollback=True, detail="non-zero exit / crash")
    return VerifierResult(verdict="PASS", can_rollback=True, evidence=outcome.evidence_refs)


# ---------------------------------------------------------------------------
# Broker
# ---------------------------------------------------------------------------


class ExecutionBroker:
    STATES = ALL_STATES
    TERMINAL = frozenset(TERMINAL_STATES)

    def __init__(
        self,
        ledger,
        *,
        sprint_id: str,
        node_write_scope: List[str],
        executors: Optional[Dict[str, Callable[[dict], ExecOutcome]]] = None,
        verifier: Optional[Callable[[str, dict, ExecOutcome], VerifierResult]] = None,
        lease: Optional[LeaseManager] = None,
        approvals: Optional[List[str]] = None,
    ) -> None:
        if ledger is None:
            raise ValueError("ExecutionBroker requires an EventLedger instance")
        if not sprint_id:
            raise ValueError("ExecutionBroker requires a non-empty sprint_id")
        self.ledger = ledger
        self.sprint_id = sprint_id
        self.node_write_scope = list(node_write_scope or [])
        self.executors: Dict[str, Callable[[dict], ExecOutcome]] = dict(executors or {})
        self.verifier = verifier or _default_verifier
        self.lease = lease or LeaseManager()
        self.approvals = set(approvals or [])

    # -- public entry --------------------------------------------------------

    def propose_action(self, contract: Optional[dict]) -> ActionResult:
        if not contract or not isinstance(contract, dict):
            raise UncontractedActionError(
                "propose_action requires a non-empty Action Contract dict"
            )

        action_id = str(contract.get("action_id") or "anonymous")
        node_id = contract.get("node_id")
        history: List[str] = []
        events: List[str] = []

        def emit(state: str, event_type: str, payload: Optional[dict] = None) -> str:
            history.append(state)
            ev = {
                "event_type": event_type,
                "sprint_id": self.sprint_id,
                "node_id": node_id,
                "actor": "execution_broker",
                "payload": {
                    "action_id": action_id,
                    "state": state,
                    **(payload or {}),
                },
            }
            eid = self.ledger.append(ev)
            events.append(eid)
            return eid

        # 0. proposed
        emit("proposed", "action.proposed", {"kind": contract.get("kind"),
                                             "risk_class": contract.get("risk_class")})

        # 1. validate schema
        schema_err = self._validate_schema(contract)
        if schema_err:
            emit("schema_failed", "policy.verdict",
                 {"verdict": "FAIL", "reason": "schema_failed", "detail": schema_err})
            return ActionResult(action_id, "schema_failed", history, events,
                                reason="schema_failed", detail=schema_err)
        emit("validated", "broker.state", {"phase": "validated"})

        # 2. policy check (write_scope + approval + classify cross-check)
        policy_err = self._policy_check(contract)
        if policy_err:
            emit("policy_denied", "policy.verdict",
                 {"verdict": "FAIL", "reason": "policy_denied", "detail": policy_err})
            return ActionResult(action_id, "policy_denied", history, events,
                                reason="policy_denied", detail=policy_err)
        emit("policy_passed", "policy.verdict", {"verdict": "PASS"})

        # 3. lease
        ok, lease_msg = self.lease.acquire(action_id, contract.get("write_set", []))
        if not ok:
            emit("lease_denied", "policy.verdict",
                 {"verdict": "FAIL", "reason": "lease_denied", "detail": lease_msg})
            return ActionResult(action_id, "lease_denied", history, events,
                                reason="lease_denied", detail=lease_msg)
        emit("leased", "lease.acquired",
             {"write_set": contract.get("write_set", []), "detail": lease_msg})

        # 4. execute
        try:
            emit("executing", "broker.state", {"phase": "executing"})
            outcome = self._execute(contract)
        except Exception as exc:  # noqa: BLE001 — surface any executor crash
            self.lease.release(action_id)
            emit("exec_failed", "action.failed",
                 {"reason": "exec_crash", "detail": str(exc)})
            return ActionResult(action_id, "exec_failed", history, events,
                                reason="exec_failed", detail=str(exc))

        if outcome.crashed or outcome.exit_code != 0:
            self.lease.release(action_id)
            emit("exec_failed", "action.failed",
                 {"reason": "non_zero_exit",
                  "exit_code": outcome.exit_code,
                  "stderr_excerpt": outcome.stderr[:256]})
            return ActionResult(action_id, "exec_failed", history, events,
                                reason="exec_failed",
                                detail=f"exit_code={outcome.exit_code}")

        if outcome.output_hash is None:
            outcome.output_hash = _hash_outcome(outcome)
        emit("executing", "action.executed",
             {"exit_code": outcome.exit_code,
              "output_hash": outcome.output_hash,
              "evidence_refs": outcome.evidence_refs})

        # 5. verify
        emit("verified", "verifier.invoked", {})
        try:
            ver = self.verifier(action_id, contract, outcome)
        except Exception as exc:  # noqa: BLE001
            self.lease.release(action_id)
            emit("verify_failed", "verifier.verdict",
                 {"verdict": "FAIL", "reason": "verifier_crash", "detail": str(exc)})
            return ActionResult(action_id, "verify_failed", history, events,
                                reason="verify_failed", detail=str(exc))

        if ver.verdict != "PASS":
            rollback = contract.get("rollback") or {"kind": "none", "target": []}
            payload = {
                "verdict": "FAIL",
                "rollback_kind": rollback.get("kind", "none"),
                "rollback_target": rollback.get("target", []),
                "can_rollback": ver.can_rollback and rollback.get("kind") in ("git_restore", "file_delete"),
                "detail": ver.detail,
            }
            emit("verify_failed", "verifier.verdict", payload)
            if payload["can_rollback"]:
                emit("verify_failed", "rollback.invoked",
                     {"kind": rollback["kind"], "target": rollback.get("target", [])})
            self.lease.release(action_id)
            return ActionResult(action_id, "verify_failed", history, events,
                                reason="verify_failed", detail=ver.detail)

        emit("verified", "verifier.verdict", {"verdict": "PASS", "evidence": ver.evidence})

        # 6. commit
        emit("committed", "artifact.registered", {"evidence": ver.evidence})
        emit("committed", "projection.updated", {})
        self.lease.release(action_id)
        return ActionResult(action_id, "committed", history, events)

    # -- internals ------------------------------------------------------------

    def _validate_schema(self, contract: dict) -> Optional[str]:
        required = (
            "schema_version", "action_id", "node_id", "kind", "intent",
            "read_set", "write_set", "required_capabilities", "preconditions",
            "success_predicates", "verification", "risk_class",
        )
        missing = [k for k in required if k not in contract]
        if missing:
            return f"missing required fields: {missing}"
        if contract["schema_version"] != SCHEMA_VERSION:
            return f"unsupported schema_version: {contract['schema_version']!r}"
        if contract["kind"] not in SUPPORTED_KINDS:
            return f"unsupported kind: {contract['kind']!r}"
        if contract["risk_class"] not in RISK_CLASSES:
            return f"invalid risk_class: {contract['risk_class']!r}"
        ver = contract.get("verification")
        if not isinstance(ver, dict):
            return "verification must be an object"
        for sub in ("static", "runtime", "evidence"):
            if sub not in ver:
                return f"verification.{sub} missing"
        if not isinstance(contract.get("read_set"), list):
            return "read_set must be a list"
        if not isinstance(contract.get("write_set"), list):
            return "write_set must be a list"
        return None

    def _policy_check(self, contract: dict) -> Optional[str]:
        write_set = list(contract.get("write_set") or [])
        verdict, reason = check_write_scope(write_set, self.node_write_scope)
        if verdict == "DENY":
            return f"write_scope: {reason}"

        risk = contract.get("risk_class", "high")
        if check_approval_required(risk) and contract.get("action_id") not in self.approvals:
            return f"approval required for risk_class={risk}"

        # Defensive cross-check with action_policy table (best-effort hint).
        submission = self._contract_to_submission(contract)
        rule = classify_action(submission)
        if rule is not None and rule.risk_class != contract["risk_class"]:
            logger.info(
                "policy_classification_mismatch: declared=%s policy=%s (rule=%s)",
                contract["risk_class"], rule.risk_class, rule.matcher_tag,
            )
        return None

    @staticmethod
    def _contract_to_submission(contract: dict) -> dict:
        kind = contract.get("kind", "")
        if kind == "shell":
            return {"kind": "shell", "command": contract.get("intent", "")}
        if kind == "file_write":
            ws = contract.get("write_set") or []
            return {"kind": "file_write", "path": ws[0] if ws else ""}
        if kind == "tool_call":
            return {"kind": "tool_call", "tool_name": contract.get("intent", "")}
        if kind == "python":
            return {"kind": "python", "source": contract.get("intent", "")}
        return {"kind": kind}

    def _execute(self, contract: dict) -> ExecOutcome:
        kind = contract["kind"]
        executor = self.executors.get(kind)
        if executor is None:
            return ExecOutcome(
                exit_code=127,
                stderr=f"no executor registered for kind={kind}",
                evidence_refs=[],
            )
        result = executor(contract)
        if isinstance(result, ExecOutcome):
            return result
        if isinstance(result, dict):
            return ExecOutcome(**result)
        raise TypeError(
            f"executor for kind={kind!r} returned {type(result).__name__}; "
            "expected ExecOutcome or dict"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hash_outcome(outcome: ExecOutcome) -> str:
    blob = json.dumps(
        {"exit_code": outcome.exit_code, "stdout": outcome.stdout, "stderr": outcome.stderr},
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(blob).hexdigest()[:16]


__all__ = [
    "ExecutionBroker",
    "ExecOutcome",
    "VerifierResult",
    "ActionResult",
    "LeaseManager",
    "UncontractedActionError",
    "BrokerError",
    "ALL_STATES",
    "HAPPY_STATES",
    "FAIL_STATES",
    "TERMINAL_STATES",
    "SCHEMA_VERSION",
    "SUPPORTED_KINDS",
]
