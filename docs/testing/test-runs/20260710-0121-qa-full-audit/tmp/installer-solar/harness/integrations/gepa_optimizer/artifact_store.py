"""
artifact_store.py — Run directory management, candidate records, Pareto tracking,
                    summary, audit log, evaluation cache, and secret scan.

Responsibilities
----------------
* Create and manage a **run directory** (e.g. /tmp/gepa_run_12345/).
* Persist **candidate records** (JSONL: candidates.jsonl) with full lineage.
* Maintain a **Pareto front** snapshot (pareto.jsonl) after each write.
* Write a **summary.json** capturing run-level statistics.
* Append to an **audit.log** for every mutating operation.
* Provide an **evaluation cache** keyed by SHA-256 of candidate text.
* **Secret scan** every candidate text before writing; reject or redact when
  secrets are detected (API keys, bearer tokens, private-key headers, etc.).

Public symbols (re-exported from integrations.gepa_optimizer.__init__)
-----------------------------------------------------------------------
* ArtifactStore       — main store façade
* RunRecord           — dataclass for per-run metadata
* CandidateRecord     — dataclass for a single optimisation candidate
* SecretViolationError — raised when secret-like content is rejected
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import logging
import re
import threading
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Secret detection
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: list[re.Pattern[str]] = [
    # AWS access key ID
    re.compile(r"AKIA[0-9A-Z]{16}", re.ASCII),
    # Generic API / auth / secret key assignment
    re.compile(
        r"(?i)(?:bearer|api[_\-]?key|auth[_\-]?token|secret[_\-]?key)\s*[:=]\s*['\"]?[A-Za-z0-9+/\-_]{20,}",
        re.ASCII,
    ),
    # PEM private key header
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |)PRIVATE KEY-----"),
    # GitHub tokens (PAT classic, fine-grained, Actions, OAuth, refresh)
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,}", re.ASCII),
    # Long hex secrets (≥ 40 contiguous hex chars not inside a word)
    re.compile(r"(?<!\w)[0-9a-fA-F]{40,}(?!\w)", re.ASCII),
    # Password in common assignment patterns
    re.compile(r"(?i)password\s*[:=]\s*['\"]?[^\s'\"]{8,}"),
    # Slack bot/webhook tokens
    re.compile(r"xox[baprs]-[0-9A-Za-z\-]{10,}", re.ASCII),
]


def _contains_secret(text: str) -> bool:
    """Return True if *text* matches any secret-like pattern."""
    for pat in _SECRET_PATTERNS:
        if pat.search(text):
            return True
    return False


def _redact_secrets(text: str) -> str:
    """Replace each secret-like match in *text* with ``[REDACTED]``."""
    result = text
    for pat in _SECRET_PATTERNS:
        result = pat.sub("[REDACTED]", result)
    return result


# ---------------------------------------------------------------------------
# Cache key: SHA-256 of candidate text
# ---------------------------------------------------------------------------

def _cache_key(text: str) -> str:
    """Return the SHA-256 hex digest of *text* encoded as UTF-8."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _utcnow() -> str:
    """Current UTC time as an ISO-8601 string (``YYYY-MM-DDTHH:MM:SSZ``)."""
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class SecretViolationError(ValueError):
    """Raised when candidate text or cache key text contains secret-like patterns.

    Pass ``redact=True`` to ``write_candidate`` / ``cache_put`` to silently
    redact instead of raising.
    """


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class RunRecord:
    """Per-run metadata persisted to ``run_dir/status.json``.

    Fields
    ------
    run_id
        Short unique identifier for the run (16-char hex prefix of the
        SHA-256 of ``run_dir`` when no explicit ID is given).
    run_dir
        Absolute path of the run directory.
    started_at
        ISO-8601 UTC timestamp when the store was created.
    finished_at
        ISO-8601 UTC timestamp set by :meth:`ArtifactStore.finish`, or *None*.
    status
        ``"running"`` → ``"completed"`` or ``"failed"``.
    total_candidates
        Count of all candidates written so far.
    pareto_size
        Size of the last Pareto front computed.
    extra
        Arbitrary run-level metadata.
    """

    run_id: str
    run_dir: str
    started_at: str
    finished_at: Optional[str] = None
    status: str = "running"
    total_candidates: int = 0
    pareto_size: int = 0
    extra: Dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class CandidateRecord:
    """A single optimisation candidate with full provenance / lineage.

    Lineage schema
    --------------
    candidate_id
        Deterministic ID derived from the candidate's text:
        the first 16 hex characters of ``SHA-256(text.encode())``.
    parent_id
        ``candidate_id`` of the immediate ancestor, or *None* for seeds.
    lineage
        Ordered list of ``candidate_id`` values from the root seed up to and
        including this candidate.  For seeds this is ``[candidate_id]``.
    generation
        Zero-based depth: seeds have ``generation == 0``, their children
        ``generation == 1``, and so on.
    operator
        Name of the GEPA operator that produced this candidate
        (e.g. ``"seed"``, ``"mutate"``, ``"crossover"``, ``"refine"``).

    Scoring
    -------
    score
        Primary scalar objective (higher is better by convention).  *None*
        for unevaluated candidates.
    scores
        Multi-objective dict, e.g. ``{"quality": 0.9, "cost": 0.3}``.  Used
        by the Pareto front computation when non-empty.
    """

    candidate_id: str
    text: str
    score: Optional[float]
    parent_id: Optional[str]
    lineage: List[str]
    generation: int
    operator: str
    created_at: str
    scores: Dict[str, float] = dataclasses.field(default_factory=dict)
    metadata: Dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    @staticmethod
    def make_id(text: str) -> str:
        """Derive a deterministic 16-char hex candidate ID from *text*."""
        return _cache_key(text)[:16]


# ---------------------------------------------------------------------------
# Pareto-front computation
# ---------------------------------------------------------------------------

def _dominates(d: CandidateRecord, c: CandidateRecord) -> bool:
    """Return True if candidate *d* strictly dominates candidate *c*.

    *d* dominates *c* when *d* is at least as good on every shared objective
    key and strictly better on at least one.  Missing keys default to 0.
    """
    all_keys = set(d.scores) | set(c.scores)
    if not all_keys:
        d_s = d.score or 0.0
        c_s = c.score or 0.0
        return d_s >= c_s and d_s > c_s
    at_least_as_good = all(
        d.scores.get(k, 0.0) >= c.scores.get(k, 0.0) for k in all_keys
    )
    strictly_better = any(
        d.scores.get(k, 0.0) > c.scores.get(k, 0.0) for k in all_keys
    )
    return at_least_as_good and strictly_better


def _pareto_front_multi(candidates: Sequence[CandidateRecord]) -> list[CandidateRecord]:
    """Return the non-dominated subset of *candidates* (multi-objective)."""
    pareto: list[CandidateRecord] = []
    for c in candidates:
        if not any(_dominates(d, c) for d in candidates if d is not c):
            pareto.append(c)
    return pareto


# ---------------------------------------------------------------------------
# ArtifactStore
# ---------------------------------------------------------------------------

class ArtifactStore:
    """Manage all on-disk artifacts for a single GEPA optimisation run.

    Directory layout
    ----------------
    ::

        run_dir/
        ├── status.json       ← RunRecord snapshot (updated on every mutation)
        ├── candidates.jsonl  ← append-only candidate records with full lineage
        ├── pareto.jsonl      ← Pareto-optimal candidates (rewritten on every write)
        ├── summary.json      ← final run summary (written by finish/write_summary)
        ├── audit.log         ← append-only structured audit trail (one JSON per line)
        └── cache/
            └── <sha256>.json ← evaluator results keyed by SHA-256(text)

    Thread safety
    -------------
    A single ``threading.Lock`` serialises all writes; reads from in-memory
    state do not require the lock.

    Secret scan
    -----------
    ``write_candidate`` scans candidate text before writing.  If secret-like
    patterns are found and ``redact=False`` (the default), ``SecretViolationError``
    is raised.  Pass ``redact=True`` to replace secrets with ``[REDACTED]``.

    Cache key
    ---------
    Cache files are named ``<sha256_of_text>.json`` where the hash is computed
    as ``SHA-256(text.encode("utf-8"))``.
    """

    def __init__(
        self,
        run_dir: str | Path,
        run_id: Optional[str] = None,
    ) -> None:
        self._run_dir = Path(run_dir)
        self._cache_dir = self._run_dir / "cache"
        self._lock = threading.Lock()
        self._candidates: list[CandidateRecord] = []

        # Ensure directories exist
        self._run_dir.mkdir(parents=True, exist_ok=True)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        # Initialise or reload RunRecord
        status_path = self._run_dir / "status.json"
        if status_path.exists():
            raw = json.loads(status_path.read_text(encoding="utf-8"))
            field_names = {f.name for f in dataclasses.fields(RunRecord)}
            self._run_record = RunRecord(**{k: v for k, v in raw.items() if k in field_names})
        else:
            self._run_record = RunRecord(
                run_id=run_id or _cache_key(str(self._run_dir.resolve()))[:16],
                run_dir=str(self._run_dir),
                started_at=_utcnow(),
            )
            self._persist_status()

        # Reload existing candidates from JSONL
        cand_path = self._run_dir / "candidates.jsonl"
        if cand_path.exists():
            field_names = {f.name for f in dataclasses.fields(CandidateRecord)}
            for line in cand_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    self._candidates.append(
                        CandidateRecord(**{k: v for k, v in d.items() if k in field_names})
                    )
                except Exception:
                    logger.warning("Skipped malformed line in candidates.jsonl")

        self._audit("store_opened", {"run_id": self._run_record.run_id})

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def run_dir(self) -> Path:
        """Absolute path of the run directory."""
        return self._run_dir

    @property
    def run_record(self) -> RunRecord:
        """Current RunRecord (may be stale between mutex-guarded updates)."""
        return self._run_record

    # ------------------------------------------------------------------
    # Candidate writes
    # ------------------------------------------------------------------

    def write_candidate(
        self,
        text: str,
        score: Optional[float] = None,
        *,
        parent_id: Optional[str] = None,
        operator: str = "unknown",
        scores: Optional[Dict[str, float]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        redact: bool = False,
    ) -> CandidateRecord:
        """Append a candidate to ``candidates.jsonl`` and update Pareto/status.

        Parameters
        ----------
        text:
            Candidate prompt or config text.  Scanned for secrets before storage.
        score:
            Primary scalar objective (higher is better).  *None* for unevaluated.
        parent_id:
            ``candidate_id`` of the parent candidate, or *None* for seeds.
        operator:
            GEPA operator name that produced this candidate.
        scores:
            Multi-objective score dict, e.g. ``{"quality": 0.9, "cost": 0.3}``.
        metadata:
            Arbitrary extra fields (model name, operator parameters, …).
        redact:
            When *True*, silently redact secret-like patterns from *text*
            instead of raising ``SecretViolationError``.

        Returns
        -------
        CandidateRecord
            The persisted record (with ``candidate_id`` and full lineage).

        Raises
        ------
        SecretViolationError
            When *text* contains secret-like patterns and ``redact=False``.
        """
        if _contains_secret(text):
            if redact:
                text = _redact_secrets(text)
                logger.warning("Candidate text contained secret-like content; redacted.")
            else:
                raise SecretViolationError(
                    "Candidate text contains secret-like patterns. "
                    "Pass redact=True to redact automatically, or sanitise the text first."
                )

        candidate_id = CandidateRecord.make_id(text)

        # Build lineage by looking up the parent's lineage
        parent_lineage: list[str] = []
        if parent_id is not None:
            parent_rec = self._find_candidate(parent_id)
            if parent_rec is not None:
                parent_lineage = list(parent_rec.lineage)
            else:
                logger.warning(
                    "Parent candidate %r not found in memory; lineage will be partial.",
                    parent_id,
                )

        lineage = parent_lineage + [candidate_id]
        generation = len(lineage) - 1

        record = CandidateRecord(
            candidate_id=candidate_id,
            text=text,
            score=score,
            parent_id=parent_id,
            lineage=lineage,
            generation=generation,
            operator=operator,
            created_at=_utcnow(),
            scores=scores or {},
            metadata=metadata or {},
        )

        with self._lock:
            self._candidates.append(record)
            # Append to candidates.jsonl
            cand_path = self._run_dir / "candidates.jsonl"
            with cand_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record.to_dict()) + "\n")
            # Keep Pareto and status in sync
            self._run_record.total_candidates = len(self._candidates)
            self._persist_pareto_locked()
            self._persist_status()

        self._audit(
            "candidate_written",
            {
                "candidate_id": candidate_id,
                "generation": generation,
                "operator": operator,
                "score": score,
                "parent_id": parent_id,
            },
        )
        return record

    # ------------------------------------------------------------------
    # Pareto front
    # ------------------------------------------------------------------

    def _compute_pareto_locked(self) -> list[CandidateRecord]:
        """Compute the current Pareto-optimal candidates (call under lock)."""
        evaluated = [c for c in self._candidates if c.score is not None]
        if not evaluated:
            return []
        if any(c.scores for c in evaluated):
            return _pareto_front_multi(evaluated)
        best = max(c.score for c in evaluated)  # type: ignore[type-var]
        return [c for c in evaluated if c.score == best]

    def _persist_pareto_locked(self) -> None:
        """Rewrite ``pareto.jsonl`` from in-memory Pareto front (call under lock)."""
        pareto = self._compute_pareto_locked()
        self._run_record.pareto_size = len(pareto)
        pareto_path = self._run_dir / "pareto.jsonl"
        with pareto_path.open("w", encoding="utf-8") as fh:
            for c in pareto:
                fh.write(json.dumps(c.to_dict()) + "\n")

    def get_pareto(self) -> list[CandidateRecord]:
        """Return the current Pareto-optimal candidates."""
        with self._lock:
            return self._compute_pareto_locked()

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def write_summary(self, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Compute and persist ``summary.json``.

        Parameters
        ----------
        extra:
            Additional key-value pairs merged into the summary dict.

        Returns
        -------
        Dict
            The summary dict that was written to disk.
        """
        with self._lock:
            pareto = self._compute_pareto_locked()
            all_scores = [c.score for c in self._candidates if c.score is not None]
            gens = [c.generation for c in self._candidates]
            summary: Dict[str, Any] = {
                "run_id": self._run_record.run_id,
                "run_dir": str(self._run_dir),
                "started_at": self._run_record.started_at,
                "finished_at": self._run_record.finished_at,
                "status": self._run_record.status,
                "total_candidates": len(self._candidates),
                "evaluated_candidates": len(all_scores),
                "pareto_size": len(pareto),
                "best_score": max(all_scores) if all_scores else None,
                "mean_score": sum(all_scores) / len(all_scores) if all_scores else None,
                "max_generation": max(gens, default=0),
            }
            if extra:
                summary.update(extra)
            (self._run_dir / "summary.json").write_text(
                json.dumps(summary, indent=2, default=str),
                encoding="utf-8",
            )

        self._audit(
            "summary_written",
            {
                "total_candidates": summary["total_candidates"],
                "pareto_size": summary["pareto_size"],
                "best_score": summary["best_score"],
            },
        )
        return summary

    # ------------------------------------------------------------------
    # Finish / close
    # ------------------------------------------------------------------

    def finish(
        self,
        status: str = "completed",
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Mark the run as finished, update ``status.json``, and write summary.

        Parameters
        ----------
        status:
            Final run status; typically ``"completed"`` or ``"failed"``.
        extra:
            Extra fields forwarded to :meth:`write_summary`.
        """
        with self._lock:
            self._run_record.status = status
            self._run_record.finished_at = _utcnow()
            self._persist_status()
        self.write_summary(extra=extra)
        self._audit("store_finished", {"status": status})

    # ------------------------------------------------------------------
    # Evaluation cache (keyed by SHA-256 of candidate text)
    # ------------------------------------------------------------------

    def cache_get(self, text: str) -> Optional[Dict[str, Any]]:
        """Return a cached evaluation result for *text*, or *None* if absent.

        The cache key is ``SHA-256(text.encode("utf-8"))``.
        """
        key = _cache_key(text)
        cache_file = self._cache_dir / f"{key}.json"
        if cache_file.exists():
            try:
                return json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                logger.warning("Malformed cache entry for key %s; ignoring.", key)
        return None

    def cache_put(
        self,
        text: str,
        result: Dict[str, Any],
        *,
        redact: bool = False,
    ) -> str:
        """Store an evaluator result in the cache.

        The cache file is written as ``cache/<sha256>.json`` where the SHA-256
        is computed from *text*.

        Parameters
        ----------
        text:
            Candidate text used as the cache key.  Scanned for secrets.
        result:
            Evaluator result dict to persist.
        redact:
            Silently redact secrets in *text* before hashing when *True*.

        Returns
        -------
        str
            The SHA-256 hex digest (cache key).

        Raises
        ------
        SecretViolationError
            When *text* contains secret-like patterns and ``redact=False``.
        """
        if _contains_secret(text):
            if redact:
                text = _redact_secrets(text)
            else:
                raise SecretViolationError(
                    "Cache key text contains secret-like patterns.  "
                    "Pass redact=True to redact automatically."
                )
        key = _cache_key(text)
        payload = {"key": key, "result": result, "cached_at": _utcnow()}
        (self._cache_dir / f"{key}.json").write_text(
            json.dumps(payload, indent=2, default=str),
            encoding="utf-8",
        )
        return key

    def cache_invalidate(self, text: str) -> bool:
        """Remove the cache entry for *text*.

        Returns
        -------
        bool
            *True* if an entry was present and removed, *False* otherwise.
        """
        key = _cache_key(text)
        cache_file = self._cache_dir / f"{key}.json"
        if cache_file.exists():
            cache_file.unlink()
            return True
        return False

    # ------------------------------------------------------------------
    # Candidate lookup / iteration
    # ------------------------------------------------------------------

    def _find_candidate(self, candidate_id: str) -> Optional[CandidateRecord]:
        """Return the most-recently-added in-memory record with *candidate_id*."""
        for c in reversed(self._candidates):
            if c.candidate_id == candidate_id:
                return c
        return None

    def get_candidate(self, candidate_id: str) -> Optional[CandidateRecord]:
        """Public accessor: return the record for *candidate_id*, or *None*."""
        return self._find_candidate(candidate_id)

    def iter_candidates(self) -> Iterator[CandidateRecord]:
        """Iterate over all candidates in insertion order."""
        yield from self._candidates

    # ------------------------------------------------------------------
    # Audit log
    # ------------------------------------------------------------------

    def _audit(self, event: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Append a single structured line to ``audit.log``."""
        entry = {"ts": _utcnow(), "event": event, **(details or {})}
        audit_path = self._run_dir / "audit.log"
        try:
            with audit_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
        except OSError:
            logger.warning("Failed to write audit log for event %r", event)

    # ------------------------------------------------------------------
    # Internal persistence
    # ------------------------------------------------------------------

    def _persist_status(self) -> None:
        """Write the current RunRecord to ``status.json`` (call under lock)."""
        (self._run_dir / "status.json").write_text(
            json.dumps(self._run_record.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Context-manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> "ArtifactStore":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        status = "failed" if exc_type is not None else "completed"
        self.finish(status=status)
