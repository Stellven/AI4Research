"""L2 ThesisExtractionOperator — cluster statements into Thesis claims.

S1-design §4.4 specifies two candidate directions:

- Direction A: rule + few-shot LLM extractor (default)
- Direction B: local embedding cluster + claim-template synthesis (fallback)

S2 implements the **deterministic rule core of Direction A** so the operator runs
in CI without premium-model quota or network. The LLM few-shot refinement is left
as an injectable ``claim_refiner`` hook; when absent the rule template is used and
the thesis is tagged ``extraction_source = "rule_based_v0"``. This choice (and the
Direction A/B kill criteria) is recorded in the S2 handoff.

Clustering rule: statements are grouped by their dominant shared entity; each
cluster yields one Thesis whose claim is templated from the cluster's statements.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Callable, Iterable, Optional

from .models import Statement, Thesis

EXTRACTION_METHOD = "rule_cluster_v0"
EXTRACTION_SOURCE = "rule_based_v0"

ClaimRefiner = Callable[[str, list[Statement]], str]


def _dominant_entity(stmt: Statement) -> str:
    return stmt.entities[0] if stmt.entities else "general"


def cluster_statements(statements: Iterable[Statement]) -> dict[str, list[Statement]]:
    """Group statements by dominant shared entity (deterministic)."""
    clusters: dict[str, list[Statement]] = defaultdict(list)
    for stmt in statements:
        clusters[_dominant_entity(stmt)].append(stmt)
    return dict(clusters)


def _template_claim(entity: str, members: list[Statement]) -> str:
    longest = max(members, key=lambda s: len(s.text or ""))
    snippet = (longest.text or "").strip().rstrip(".")
    return f"Influencers converge on a thesis about {entity}: {snippet}."


def _confidence(members: list[Statement]) -> float:
    # More corroborating statements => higher confidence, capped at 0.95.
    return round(min(0.95, 0.4 + 0.15 * len(members)), 2)


def extract_theses(
    statements: Iterable[Statement],
    claim_refiner: Optional[ClaimRefiner] = None,
    min_cluster_size: int = 1,
) -> list[Thesis]:
    statements = list(statements)
    theses: list[Thesis] = []
    for idx, (entity, members) in enumerate(sorted(cluster_statements(statements).items())):
        if len(members) < min_cluster_size:
            continue
        base_claim = _template_claim(entity, members)
        claim = claim_refiner(base_claim, members) if claim_refiner else base_claim
        theses.append(
            Thesis(
                thesis_id=f"thesis-{entity.lower().replace(' ', '-')}-{idx:03d}",
                claim=claim,
                derived_from_statements=[s.statement_id for s in members],
                viewpoint_cluster=entity.lower().replace(" ", "-"),
                confidence=_confidence(members),
                extraction_method=EXTRACTION_METHOD,
                extraction_source=EXTRACTION_SOURCE if claim_refiner is None else "rule_plus_refiner_v0",
            )
        )
    return theses


def thesis_recall(extracted: list[Thesis], expected_clusters: Iterable[str]) -> float:
    """Fraction of expected viewpoint clusters covered by extraction.

    Used by tests/influence/test_thesis_extractor.py to enforce the Direction A
    kill criterion (recall < 0.5 => fall back to Direction B).
    """
    expected = {c.lower().replace(" ", "-") for c in expected_clusters}
    if not expected:
        return 1.0
    got = {t.viewpoint_cluster for t in extracted}
    return len(expected & got) / len(expected)
