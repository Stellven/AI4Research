"""backend.py — orchestration layer for Solar's GEPA meta-optimizer.

This module intentionally sits above the Stage 1 GEPA substrate and below the
future Solar optimizer control plane.  It is safe to import without the
``gepa`` package installed and provides typed, auditable entry points for the
mutable optimization objects Solar wants to evolve offline.
"""

from __future__ import annotations

import dataclasses
import tempfile
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping

from .adapter import GEPAConfig, _GEPA_AVAILABLE
from .artifact_store import ArtifactStore
from .candidate_schema import CandidateType, OptimizationCandidate, normalize_candidate
from .hard_policy_checker import check_candidate

__all__ = ["GEPAOptimizerBackend", "OptimizationBackendError"]

_VALID_MODES = {"offline", "shadow", "bounded_online"}


class OptimizationBackendError(RuntimeError):
    """Raised when the GEPA backend receives an invalid request."""


@dataclasses.dataclass(frozen=True)
class _OptimizationRequest:
    candidate_type: CandidateType
    target_id: str
    suite_id: str
    mode: str
    candidate: OptimizationCandidate
    run_dir: Path


class GEPAOptimizerBackend:
    """Typed façade for offline GEPA-backed optimization workloads."""

    def __init__(
        self,
        *,
        run_root: str | Path | None = None,
        store_factory: Callable[..., ArtifactStore] = ArtifactStore,
        config_factory: Callable[..., GEPAConfig] = GEPAConfig,
    ) -> None:
        self._run_root = Path(run_root) if run_root else Path(tempfile.gettempdir()) / "solar_gepa_optimizer"
        self._store_factory = store_factory
        self._config_factory = config_factory

    def optimize_skill(
        self,
        skill_id: str,
        benchmark_suite: str,
        *,
        mode: str = "offline",
        candidate: OptimizationCandidate | Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        request = self._build_request(
            candidate_type=CandidateType.SKILL,
            target_id=skill_id,
            suite_id=benchmark_suite,
            mode=mode,
            candidate=candidate,
        )
        return self._execute_request(request)

    def optimize_capsule(
        self,
        capsule_id: str,
        benchmark_suite: str,
        *,
        mode: str = "offline",
        candidate: OptimizationCandidate | Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        request = self._build_request(
            candidate_type=CandidateType.CAPSULE,
            target_id=capsule_id,
            suite_id=benchmark_suite,
            mode=mode,
            candidate=candidate,
        )
        return self._execute_request(request)

    def optimize_routing_policy(
        self,
        policy_id: str,
        replay_suite: str,
        *,
        mode: str = "offline",
        candidate: OptimizationCandidate | Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        request = self._build_request(
            candidate_type=CandidateType.ROUTING_POLICY,
            target_id=policy_id,
            suite_id=replay_suite,
            mode=mode,
            candidate=candidate,
        )
        return self._execute_request(request)

    def optimize_rewrite_rules(
        self,
        rule_set_id: str,
        replay_suite: str,
        *,
        mode: str = "offline",
        candidate: OptimizationCandidate | Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        request = self._build_request(
            candidate_type=CandidateType.REWRITE_RULES,
            target_id=rule_set_id,
            suite_id=replay_suite,
            mode=mode,
            candidate=candidate,
        )
        return self._execute_request(request)

    def optimize_cost_model(
        self,
        cost_model_id: str,
        replay_suite: str,
        *,
        mode: str = "offline",
        candidate: OptimizationCandidate | Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        request = self._build_request(
            candidate_type=CandidateType.COST_MODEL,
            target_id=cost_model_id,
            suite_id=replay_suite,
            mode=mode,
            candidate=candidate,
        )
        return self._execute_request(request)

    def _build_request(
        self,
        *,
        candidate_type: CandidateType,
        target_id: str,
        suite_id: str,
        mode: str,
        candidate: OptimizationCandidate | Mapping[str, Any] | None,
    ) -> _OptimizationRequest:
        if mode not in _VALID_MODES:
            raise OptimizationBackendError(
                f"unsupported mode {mode!r}; expected one of {sorted(_VALID_MODES)}"
            )
        if not target_id.strip():
            raise OptimizationBackendError("target_id must be a non-empty string")
        if not suite_id.strip():
            raise OptimizationBackendError("suite_id must be a non-empty string")

        run_id = uuid.uuid4().hex[:16]
        run_dir = self._run_root / candidate_type.value / run_id
        return _OptimizationRequest(
            candidate_type=candidate_type,
            target_id=target_id.strip(),
            suite_id=suite_id.strip(),
            mode=mode,
            candidate=normalize_candidate(candidate or self._default_candidate(candidate_type, target_id)),
            run_dir=run_dir,
        )

    def _default_candidate(
        self,
        candidate_type: CandidateType,
        target_id: str,
    ) -> dict[str, Any]:
        defaults: dict[CandidateType, tuple[tuple[str, ...], tuple[str, ...], dict[str, Any]]] = {
            CandidateType.SKILL: (
                ("instructions", "examples", "failure_checklist"),
                ("safety_notes",),
                {"skill_md": "", "safety_notes": {"secrets_access": "denied"}},
            ),
            CandidateType.CAPSULE: (
                ("instructions", "quality_gates", "output_schema", "verifier_contract", "routing_hints", "failure_patterns"),
                ("safety", "secret_refs_policy", "forbidden_mcp"),
                {
                    "capsule_yaml": "",
                    "safety": {
                        "secrets_access": "denied",
                        "git_push": False,
                        "destructive_shell": "denied",
                    },
                },
            ),
            CandidateType.ROUTING_POLICY: (
                ("rules", "thresholds", "fallback_order"),
                ("hard_verifier_requirements", "forbidden_provider_pairings"),
                {"routing_policy_yaml": ""},
            ),
            CandidateType.REWRITE_RULES: (
                ("match_conditions", "insertions", "fanout_degree"),
                ("must_verify_after_write", "no_self_verification"),
                {"rewrite_rules_yaml": ""},
            ),
            CandidateType.COST_MODEL: (
                ("weights", "soft_penalties"),
                ("safety_violation", "verifier_conflict_penalty"),
                {"cost_model_yaml": ""},
            ),
        }
        mutable_sections, frozen_sections, payload = defaults[candidate_type]
        return {
            "candidate_type": candidate_type.value,
            "target_id": target_id,
            "payload": payload,
            "mutable_sections": list(mutable_sections),
            "frozen_sections": list(frozen_sections),
            "origin_run_id": None,
            "lineage": [],
            "frozen_values": {},
            "metadata": {},
        }

    def _execute_request(self, request: _OptimizationRequest) -> dict[str, Any]:
        store = self._store_factory(run_dir=request.run_dir)
        policy_result = check_candidate(request.candidate)
        seed_record = store.write_candidate(
            request.candidate.canonical_json(),
            score=None,
            operator="seed",
            metadata={
                "candidate_type": request.candidate_type.value,
                "target_id": request.target_id,
                "suite_id": request.suite_id,
                "mode": request.mode,
                "policy_decision": policy_result["decision"],
            },
        )

        base_result = {
            "run_id": store.run_record.run_id,
            "candidate_type": request.candidate_type.value,
            "target_id": request.target_id,
            "suite_id": request.suite_id,
            "mode": request.mode,
            "selected_candidate_id": seed_record.candidate_id,
            "pareto_frontier": [],
            "policy_check": policy_result,
            "run_dir": str(store.run_dir),
        }

        if not policy_result["ok"]:
            store.finish(
                status="failed",
                extra={
                    "backend_status": "hard_reject",
                    "policy_violations": policy_result["violations"],
                },
            )
            return {
                **base_result,
                "status": "hard_reject",
                "publish_decision": "reject",
            }

        adapter_cfg = self._config_factory(run_id=store.run_record.run_id)
        if not _GEPA_AVAILABLE:
            store.finish(
                status="completed",
                extra={
                    "backend_status": "gepa_unavailable",
                    "adapter_model": getattr(adapter_cfg, "model", None),
                },
            )
            return {
                **base_result,
                "status": "gepa_unavailable",
                "publish_decision": "hold",
            }

        store.finish(
            status="completed",
            extra={
                "backend_status": "proposal_ready",
                "adapter_model": getattr(adapter_cfg, "model", None),
            },
        )
        return {
            **base_result,
            "status": "proposal_ready",
            "publish_decision": "review_required",
        }
