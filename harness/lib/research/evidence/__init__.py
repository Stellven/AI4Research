"""DeepResearch evidence subsystem.

Provides the evidence ledger (write/read/list) and citation span verifier.
"""

from .citation_span import verify_span
from .ledger import list_by_source, read_evidence, write_evidence
from .review_proof import claim_support_assessment, normalize_review_proof

__all__ = ["write_evidence", "read_evidence", "list_by_source", "verify_span", "claim_support_assessment", "normalize_review_proof"]
