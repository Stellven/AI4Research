"""actor_runtime.py — Main submit protocol for AgentActor runtime.

Grants lease, writes task_envelope to mailbox inbox,
writes evidence ledger, loads context packet, returns lease/result paths.
No direct tmux scheduler calls.
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from actor_lease import LeaseBroker, LeaseState, READY, LEASED, RUNNING, FINALIZING
from actor_mailbox import ActorMailbox
from actor_profiles import ActorProfile, load_profiles
from logical_operator_router import LogicalOperatorRouter
from operator_score import OperatorScoreResult, rank_actors, TaskEvidence
from evidence_ledger import EvidenceLedger, build_scheduler_decision
from context_store import ContextStore
from capability_token import CapabilityToken
from verification_gate import VerificationGate
from apo_plan_compiler import compile_execution_plan_for_node, materialize_execution_plan_artifacts

HOME = Path.home()
HARNESS_DIR = Path(os.environ.get("HARNESS_DIR", HOME / ".solar" / "harness"))


class SubmitResult:
    """Result of actor_runtime.submit()."""

    def __init__(
        self,
        success: bool,
        lease: Optional[LeaseState] = None,
        inbox_path: Optional[str] = None,
        outbox_path: Optional[str] = None,
        evidence_ledger_path: Optional[str] = None,
        scheduler_decision: Optional[Dict] = None,
        error: Optional[str] = None,
    ):
        self.success = success
        self.lease = lease
        self.inbox_path = inbox_path
        self.outbox_path = outbox_path
        self.evidence_ledger_path = evidence_ledger_path
        self.scheduler_decision = scheduler_decision
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "lease": self.lease.to_dict() if self.lease else None,
            "inbox_path": self.inbox_path,
            "outbox_path": self.outbox_path,
            "evidence_ledger_path": self.evidence_ledger_path,
            "scheduler_decision": self.scheduler_decision,
            "error": self.error,
        }


class ActorRuntime:
    """Main runtime for submitting tasks to actors."""

    def __init__(
        self,
        harness_dir: Optional[Path] = None,
        lease_broker: Optional[LeaseBroker] = None,
        mailbox_base: Optional[Path] = None,
        evidence_ledger: Optional[EvidenceLedger] = None,
        context_store: Optional[ContextStore] = None,
        profiles_path: Optional[Path] = None,
        bindings_path: Optional[Path] = None,
    ):
        self.harness_dir = harness_dir or HARNESS_DIR
        self.broker = lease_broker or LeaseBroker(self.harness_dir / "run" / "actor-leases")
        self.mailbox_base = mailbox_base or self.harness_dir / "actors"
        self.ledger = evidence_ledger or EvidenceLedger(self.harness_dir / "run" / "actor-evidence")
        self.ctx_store = context_store or ContextStore(self.harness_dir / "run" / "context-store")
        self.profiles = load_profiles(profiles_path)
        self.router = LogicalOperatorRouter(bindings_path)

    def _ensure_execution_plan_metadata(
        self,
        task_envelope: Dict[str, Any],
        *,
        logical_operator: str = "",
        actor_id: str = "",
        sprint_id: str = "",
        node_id: str = "",
    ) -> Dict[str, Any]:
        payload = dict(task_envelope)
        if payload.get("capsule_plan_ir") and payload.get("physical_plan_ir"):
            return payload

        graph_node = payload.get("task_graph_node") if isinstance(payload.get("task_graph_node"), dict) else {}
        node = dict(graph_node or {})
        node.setdefault("id", node_id or str(payload.get("node_id") or ""))
        node.setdefault("goal", str(payload.get("objective") or ""))
        node.setdefault("logical_operator", logical_operator or str(payload.get("logical_operator") or ""))
        node.setdefault("type", str(payload.get("task_type") or ""))
        if payload.get("capability_capsule_id"):
            node.setdefault("capability_native", bool(payload.get("capability_native", True)))
            node.setdefault("capability_capsule_id", str(payload.get("capability_capsule_id")))
        if isinstance(payload.get("capsule_plan"), dict) and payload.get("capsule_plan"):
            node.setdefault("capsule_plan", dict(payload["capsule_plan"]))

        if not node.get("logical_operator"):
            return payload

        try:
            compiled = compile_execution_plan_for_node(
                node,
                request_type=str(payload.get("task_type") or ""),
                prefer_operator=actor_id,
            )
            capsule_plan = compiled.get("capsule_plan") or {}
            physical_plan = compiled.get("physical_plan") or {}
            payload["logical_plan_node"] = compiled.get("logical_plan_node") or {}
            payload["capsule_plan_ir"] = capsule_plan
            payload["physical_plan_ir"] = physical_plan
            if capsule_plan.get("capability_capsule_id") and not payload.get("capability_capsule_id"):
                payload["capability_capsule_id"] = str(capsule_plan["capability_capsule_id"])
            if sprint_id and node_id:
                payload["plan_artifacts"] = materialize_execution_plan_artifacts(
                    sprint_id,
                    node_id,
                    capsule_plan=capsule_plan,
                    physical_plan=physical_plan,
                    base_dir=self.harness_dir / "sprints",
                )
        except Exception:
            return payload
        return payload

    def submit(
        self,
        task_envelope: Dict[str, Any],
        logical_operator: Optional[str] = None,
        actor_id: Optional[str] = None,
        sprint_id: str = "",
        node_id: str = "",
        ttl_sec: int = 2700,
        capability_token: Optional[CapabilityToken] = None,
    ) -> SubmitResult:
        """Submit a task envelope to an actor.

        1. Validate capability token if provided
        2. Resolve actor via logical operator or direct actor_id
        3. Acquire lease
        4. Write task envelope to mailbox inbox
        5. Write evidence ledger
        6. Return lease and paths
        """
        task_id = task_envelope.get("task_id", str(uuid.uuid4()))

        # Validate capability token
        if capability_token:
            validation = capability_token.validate_for_lease()
            if not validation["valid"]:
                return SubmitResult(success=False, error=f"capability_token_invalid: {validation['issues']}")

        # Check safety boundaries
        allowed, safety_err, requires_approval = self.check_safety_boundaries(task_envelope)
        if not allowed:
            return SubmitResult(success=False, error=safety_err)
        if requires_approval and not task_envelope.get("human_approved"):
            return SubmitResult(success=False, error="human_approval_required")

        # Resolve actor
        if not actor_id and logical_operator:
            is_browser_op = (
                logical_operator in ("DeepResearchBrowser", "WebwrightPlaywright", "BrowserUseMcp") or
                task_envelope.get("requires_replayable_evidence") or
                task_envelope.get("is_long_horizon_web_task") or
                task_envelope.get("is_localhost_smoke_or_quick_extract")
            )
            if is_browser_op:
                if (
                    task_envelope.get("requires_replayable_evidence") or
                    task_envelope.get("is_long_horizon_web_task")
                ):
                    actor_id = "op.browser.webwright.playwright.01"
                elif task_envelope.get("is_localhost_smoke_or_quick_extract"):
                    actor_id = "op.browser.browser_use_mcp.quick.01"
                else:
                    # Default Fallback: Webwright
                    actor_id = "op.browser.webwright.playwright.01"
            else:
                selected, rejected = self.router.select_actor(logical_operator)
                if not selected:
                    return SubmitResult(success=False, error=f"no_available_actor_for_{logical_operator}")
                actor_id = selected
        elif not actor_id:
            return SubmitResult(success=False, error="no_actor_id_or_logical_operator")

        task_envelope = self._ensure_execution_plan_metadata(
            task_envelope,
            logical_operator=logical_operator or str(task_envelope.get("logical_operator") or ""),
            actor_id=actor_id,
            sprint_id=sprint_id,
            node_id=node_id,
        )

        # Check profile risk denial
        profile = self.profiles.get(actor_id)
        evidence_path = f"actors/{actor_id}/evidence/{task_id}"

        # Acquire lease
        lease = self.broker.acquire(
            actor_id=actor_id,
            task_id=task_id,
            sprint_id=sprint_id,
            node_id=node_id,
            ttl_sec=ttl_sec,
            evidence_path=evidence_path,
        )
        if not lease:
            return SubmitResult(success=False, error=f"lease_acquisition_failed_for_{actor_id}")

        # Write to mailbox
        mailbox = ActorMailbox(actor_id, self.mailbox_base)
        # Load context packet if referenced
        ctx_ref = task_envelope.get("context_packet_ref")
        if ctx_ref:
            ctx_data = self.ctx_store.resolve_ref(ctx_ref)
            if ctx_data:
                task_envelope["context_packet"] = ctx_data

        inbox_path = mailbox.submit_task(task_envelope)
        outbox_dir = str(mailbox.outbox)

        # Build scheduler decision
        sched_decision = build_scheduler_decision(
            selected_actor=actor_id,
            logical_operator=logical_operator or "",
            score_factors={},
            penalties={},
            rejected=[],
        )

        resolved_capsule = task_envelope.get("resolved_capability_capsule") or {}
        if not isinstance(resolved_capsule, dict):
            resolved_capsule = {}

        # Write evidence ledger
        ledger_path = self.ledger.write_run_entry(
            task_id=task_id,
            sprint_id=sprint_id,
            node_id=node_id,
            actor_id=actor_id,
            logical_operator=logical_operator or "",
            scheduler_decision=sched_decision,
            context_packet_id=ctx_ref.get("packet_id") if ctx_ref else None,
            final_report_target=f"run/{sprint_id}/final_report.md",
            capability_capsule_id=resolved_capsule.get("capability_capsule_id"),
            capsule_kind=resolved_capsule.get("capsule_kind"),
            resolved_bindings=resolved_capsule.get("resolved_mcp_bindings"),
            effect_summary=resolved_capsule.get("effect_summary"),
            guard_results=resolved_capsule.get("attached_guard_capsules"),
            verification_results=resolved_capsule.get("verification_hooks"),
            capsule_plan_ir=task_envelope.get("capsule_plan_ir") if isinstance(task_envelope.get("capsule_plan_ir"), dict) else None,
            physical_plan_ir=task_envelope.get("physical_plan_ir") if isinstance(task_envelope.get("physical_plan_ir"), dict) else None,
            plan_artifacts=task_envelope.get("plan_artifacts") if isinstance(task_envelope.get("plan_artifacts"), dict) else None,
        )

        return SubmitResult(
            success=True,
            lease=lease,
            inbox_path=inbox_path,
            outbox_path=outbox_dir,
            evidence_ledger_path=ledger_path,
            scheduler_decision=sched_decision,
        )

    def check_safety_boundaries(
        self,
        task_envelope: Dict[str, Any],
    ) -> Tuple[bool, Optional[str], bool]:
        """Check task compliance with security boundaries.

        Returns (allowed, error_message, requires_human_approval).
        """
        objective = str(task_envelope.get("objective", "")).lower()
        action_type = str(task_envelope.get("action_type", "")).lower()

        forbidden_types = {
            "payment_action",
            "credential_capture",
            "cookie_export_without_approval",
            "bot_detection_bypass",
            "unauthorized_scraping",
            "cookie heist",
        }
        requires_approval_types = {
            "login",
            "external_write",
            "form_submit",
            "account_action",
        }

        # Check explicit action type
        if action_type in forbidden_types:
            return False, f"security_violation: action_type '{action_type}' is forbidden", False
        if action_type in requires_approval_types:
            return True, None, True

        # Check text content of objective
        forbidden_keywords = {
            "payment": "payment_action",
            "cookie heist": "cookie_export_without_approval",
            "export cookies": "cookie_export_without_approval",
            "bot bypass": "bot_detection_bypass",
            "bypass bot": "bot_detection_bypass",
            "credential capture": "credential_capture",
            "unauthorized scraping": "unauthorized_scraping",
        }

        for kw, classification in forbidden_keywords.items():
            if kw in objective:
                return False, f"security_violation: task objective contains keyword associated with forbidden action '{classification}'", False

        approval_keywords = ["login", "submit form", "account action", "external write", "form_submit"]
        for kw in approval_keywords:
            if kw in objective:
                return True, None, True

        return True, None, False
