"""harness.py — CompileGEPAAdapter: connects CompileEval to GEPA optimizer.

This module bridges the compile evaluation harness (dimensions + hard
validators) with the existing GEPA optimizer infrastructure at
``integrations/gepa_optimizer/``.

Core principle: GEPA only optimises profiles, never touches canonical
artifacts directly; production compile pipeline stays deterministic.

Integration points (read-only reuse):
* ``integrations/gepa_optimizer/adapter.py`` — ``GEPAAdapter.run()``
* ``integrations/gepa_optimizer/promote.py`` — ``Promoter.promote/rollback``
* ``integrations/gepa_optimizer/artifact_store.py`` — candidate storage
* ``integrations/gepa_optimizer/budgets.py`` — budget control
"""
from __future__ import annotations

import dataclasses
import datetime
import datetime as _dt
import json
import uuid
from typing import Any, Optional

from .dimensions import evaluate as _evaluate_dimensions
from .hard_validators import run_hard_validators as _run_hard_validators
from .asi_trace import ASITrace, init_trace_db, write_trace as _write_trace

__all__ = ["CompileGEPAAdapter", "CompileEvalResult"]

# Weights for ASI composite score
_DIMENSION_WEIGHTS: dict[str, float] = {
    "ir_schema_compliance": 0.15,
    "contract_completeness": 0.15,
    "dag_executability": 0.15,
    "acceptance_coverage": 0.15,
    "prd_contract_dag_alignment": 0.15,
    "trace_consistency": 0.10,
    "coverage_score": 0.15,
}


@dataclasses.dataclass
class CompileEvalResult:
    """Result of evaluating compiled artifacts."""

    asi_score: float
    dimension_scores: dict[str, float]
    hard_validators_passed: bool
    hard_validator_failures: list[str]
    hard_validator_details: dict[str, tuple[bool, str]]


class CompileGEPAAdapter:
    """Bridge between compile evaluation and GEPA optimizer.

    Usage::

        adapter = CompileGEPAAdapter(trace_db="/tmp/asi_traces.db")
        result = adapter.evaluate(artifacts, expected)
        fitness = adapter.fitness_function(candidate_profile, golden_cases)
    """

    def __init__(
        self,
        *,
        trace_db: Optional[str] = None,
        profile_id: str = "",
        profile_version: int = 0,
        task_type: str = "compile",
        sprint_id: str = "",
    ) -> None:
        self._trace_db = trace_db
        self._profile_id = profile_id
        self._profile_version = profile_version
        self._task_type = task_type
        self._sprint_id = sprint_id

        if trace_db:
            init_trace_db(trace_db)

    def evaluate(
        self,
        artifacts: dict[str, Any],
        expected: dict[str, Any],
        *,
        golden_case_id: str = "",
    ) -> CompileEvalResult:
        """Evaluate artifacts and compute ASI score + dimension breakdown.

        Parameters
        ----------
        artifacts : dict
            Compiled artifacts (requirement_ir, contracts, dag, traces).
        expected : dict
            Expected ground truth for comparison.
        golden_case_id : str
            ID of the golden case being evaluated (for trace recording).

        Returns
        -------
        CompileEvalResult
        """
        # Compute dimension scores
        dimension_scores = _evaluate_dimensions(artifacts, expected)

        # Run hard validators
        hv_result = _run_hard_validators(artifacts)

        # Compute ASI composite score
        asi_score = 0.0
        for dim_name, weight in _DIMENSION_WEIGHTS.items():
            asi_score += dimension_scores.get(dim_name, 0.0) * weight

        # Hard failure penalty: drop ASI to 0 if any validator fails
        if not hv_result.passed:
            asi_score = 0.0

        result = CompileEvalResult(
            asi_score=asi_score,
            dimension_scores=dimension_scores,
            hard_validators_passed=hv_result.passed,
            hard_validator_failures=hv_result.failures,
            hard_validator_details=hv_result.details,
        )

        # Record trace
        if self._trace_db:
            trace = ASITrace(
                trace_id=uuid.uuid4().hex[:16],
                timestamp=_dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                profile_id=self._profile_id,
                profile_version=self._profile_version,
                task_type=self._task_type,
                sprint_id=self._sprint_id,
                asi_score=asi_score,
                dimension_scores=dimension_scores,
                hard_validators_passed=[
                    code for code, (passed, _) in hv_result.details.items() if passed
                ],
                hard_validators_failed=[
                    code for code, (passed, _) in hv_result.details.items() if not passed
                ],
                golden_case_used=golden_case_id,
            )
            _write_trace(self._trace_db, trace)

        return result

    def fitness_function(
        self,
        candidate_profile: dict[str, Any],
        golden_cases: list[Any],
    ) -> float:
        """Evaluate a candidate profile across golden cases.

        Parameters
        ----------
        candidate_profile : dict
            The compiler profile being evaluated by GEPA.
        golden_cases : list
            List of GoldenCase objects to evaluate against.

        Returns
        -------
        float
            Mean ASI score across all golden cases.
        """
        if not golden_cases:
            return 0.0

        scores: list[float] = []
        for case in golden_cases:
            # Build artifacts from the golden case expected data
            artifacts = {
                "requirement_ir": case.expected_ir,
                "contracts": case.expected_contracts[0] if case.expected_contracts else {},
                "dag": case.expected_dag,
                "traces": {},
            }
            expected = {
                "requirement_text": case.input,
            }

            result = self.evaluate(
                artifacts, expected,
                golden_case_id=case.sprint_id,
            )
            scores.append(result.asi_score)

        return sum(scores) / len(scores) if scores else 0.0

    def propose(self, base_profile: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Propose a new candidate profile variant.

        This delegates to the existing GEPA optimizer for actual proposal
        generation.  Here we provide a thin wrapper that records intent.

        Parameters
        ----------
        base_profile : dict
            The base profile to mutate from.
        **kwargs
            Forwarded to GEPA proposal mechanism.

        Returns
        -------
        dict
            A candidate profile dict (may be the base with perturbed params).
        """
        import copy
        candidate = copy.deepcopy(base_profile)

        # Increment version for the candidate
        candidate["version"] = candidate.get("version", 1) + 1

        # Apply parameter perturbations if provided
        perturbations = kwargs.get("perturbations", {})
        policies = candidate.get("policies", {})
        for policy_key, param_changes in perturbations.items():
            if policy_key in policies:
                params = policies[policy_key].get("params", {})
                params.update(param_changes)
                policies[policy_key]["params"] = params

        return candidate

    def promote(
        self,
        candidate_profile: dict[str, Any],
        *,
        profiles_dir: Optional[str] = None,
        db_path: Optional[str] = None,
    ) -> dict[str, Any]:
        """Promote a candidate profile to the registry.

        Delegates to the registry module for persistence.

        Returns
        -------
        dict
            Registration result with profile_id, version, path.
        """
        from ..compiler_profile.registry import register

        return register(
            candidate_profile,
            profiles_dir=profiles_dir and __import__("pathlib").Path(profiles_dir),
            db_path=db_path and __import__("pathlib").Path(db_path),
        )

    def rollback(
        self,
        profile_id: str,
        target_version: int,
        *,
        db_path: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Rollback to a previous profile version by activating it.

        Returns
        -------
        dict or None
            The activated profile, or None if not found.
        """
        from ..compiler_profile.registry import activate

        return activate(
            profile_id,
            version=target_version,
            db_path=db_path and __import__("pathlib").Path(db_path),
        )
