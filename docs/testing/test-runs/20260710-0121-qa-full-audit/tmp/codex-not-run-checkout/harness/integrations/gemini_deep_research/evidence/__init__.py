"""U3 — runtime structured completion evidence."""

from .completion_evidence import (
    CompletionEvidence,
    build_evidence,
    verify_evidence,
    write_evidence,
)

__all__ = [
    "CompletionEvidence",
    "build_evidence",
    "verify_evidence",
    "write_evidence",
]
