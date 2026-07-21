"""logical_operator_router.py — Maps logical operators to candidate actors via bindings.

16 P0 logical operator types mapped through data bindings, not hard-coded.
Changing a binding changes the selected actor without editing the DAG node.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HOME = Path.home()
HARNESS_DIR = Path.home() / ".solar" / "harness"
LOGICAL_OPS_PATH = HARNESS_DIR / "config" / "logical-operators.json"
ACTORS_PATH = HARNESS_DIR / "config" / "agent-actors.json"

P0_LOGICAL_OPERATORS = frozenset([
    "DeepArchitect", "RootCauseDebugger", "ImplementationWorker", "PatchWorker",
    "TestDesigner", "TestRunner", "BenchmarkRunner", "ParallelExplorer",
    "ResearchScout", "ResearchSynthesizer", "Critic", "Verifier", "VerifierLite",
    "SecurityGate", "QuotaBroker", "ContextCompressor", "ArtifactCurator",
])


class LogicalOperatorRouter:
    """Routes logical operators to candidate actors through bindings."""

    def __init__(
        self,
        bindings_path: Optional[Path] = None,
        actors_path: Optional[Path] = None,
    ):
        self.bindings_path = bindings_path or LOGICAL_OPS_PATH
        self.actors_path = actors_path or ACTORS_PATH
        self._bindings: Dict[str, Dict[str, Any]] = {}
        self._actors: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self.bindings_path.exists():
            data = json.loads(self.bindings_path.read_text(encoding="utf-8"))
            bindings = data.get("bindings", {})
            # bindings can be dict (keyed by operator_type) or list
            if isinstance(bindings, dict):
                for op, entry in bindings.items():
                    self._bindings[op] = entry
            elif isinstance(bindings, list):
                for entry in bindings:
                    op = entry.get("operator_type", "")
                    self._bindings[op] = entry

        if self.actors_path.exists():
            data = json.loads(self.actors_path.read_text(encoding="utf-8"))
            self._actors = data.get("actors", {})

    def get_candidates(self, operator_type: str) -> List[str]:
        """Get ordered candidate actor_ids for a logical operator."""
        binding = self._bindings.get(operator_type, {})
        candidates = binding.get("candidates", [])
        # candidates can be list of dicts with actor_id or list of strings
        if candidates and isinstance(candidates[0], dict):
            return [c.get("actor_id", "") for c in candidates]
        return list(candidates)

    def select_actor(
        self,
        operator_type: str,
        unavailable: Optional[set] = None,
        quota_blocked: Optional[set] = None,
        risk_denied: Optional[set] = None,
    ) -> Tuple[Optional[str], List[Dict[str, str]]]:
        """Select best available actor for operator_type.

        Returns (selected_actor_id, rejected_list_with_reasons).
        """
        candidates = self.get_candidates(operator_type)
        unavail = unavailable or set()
        blocked = quota_blocked or set()
        denied = risk_denied or set()
        rejected: List[Dict[str, str]] = []

        for actor_id in candidates:
            if actor_id in unavail:
                rejected.append({"actor_id": actor_id, "reason": "unavailable"})
                continue
            if actor_id in blocked:
                rejected.append({"actor_id": actor_id, "reason": "quota_blocked"})
                continue
            if actor_id in denied:
                rejected.append({"actor_id": actor_id, "reason": "risk_denied"})
                continue
            return actor_id, rejected

        return None, rejected

    def validate_all_operators_bound(self) -> List[str]:
        """Return list of operators with no bindings."""
        unbound = []
        for op in P0_LOGICAL_OPERATORS:
            if op not in self._bindings or not self._bindings[op].get("candidates"):
                unbound.append(op)
        return unbound
