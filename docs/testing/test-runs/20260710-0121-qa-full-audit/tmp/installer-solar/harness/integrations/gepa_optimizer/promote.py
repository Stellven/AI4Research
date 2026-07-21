"""
promote.py — Atomic promote / backup / diff / rollback for GEPA candidates.

Safety
------
* The CLI already enforces ``/tmp`` targets via
  ``_is_safe_promotion_target``; this module enforces it again in code
  because it must reject production paths even when invoked directly.
* Every promote writes a backup file (raw bytes) **before** replacing the
  target, and remembers the backup path in a sidecar JSON. Rollback
  refuses to run when the backup is missing.
* All writes use ``os.replace`` (atomic on a single filesystem) so a
  half-written target can never appear on disk.

Public symbols (re-exported from ``integrations.gepa_optimizer``):

* ``PromotionTarget`` — frozen dataclass; constructor enforces /tmp guard.
* ``RollbackError``   — raised when rollback cannot proceed safely.
* ``Promoter``        — methods ``promote`` and ``rollback``.

Sidecar layout
--------------
Alongside every promoted target a ``<target>.gepa-meta.json`` is written
holding ``{backup_path, run_dir, candidate_id, target, promoted_at, sha256_before, sha256_after}``.
Rollback reads the sidecar to find the right backup file.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

__all__ = ["PromotionTarget", "Promoter", "PromoteError", "RollbackError"]


class PromoteError(RuntimeError):
    """Raised for promote-time errors (safety, missing run dir, etc.)."""


class RollbackError(RuntimeError):
    """Raised when a rollback cannot complete safely.

    Typical causes:
    * sidecar metadata file is missing or malformed
    * the recorded backup path does not exist
    * the post-restore sha256 does not match the recorded ``sha256_before``
    """


# ---------------------------------------------------------------------------
# Safety helpers
# ---------------------------------------------------------------------------


_PRODUCTION_PREFIXES: tuple[str, ...] = (
    "/etc/",
    "/usr/",
    "/opt/",
    "/var/",
    os.path.expanduser("~/.claude/"),
    os.path.expanduser("~/.solar/harness/config/"),
    os.path.expanduser("~/.solar/harness/integrations/"),
    os.path.expanduser("~/.solar/harness/lib/"),
    os.path.expanduser("~/.solar/harness/skills/"),
    os.path.expanduser("~/.solar/harness/hooks/"),
)


def _resolved(path: str | os.PathLike) -> str:
    """Resolve symlinks and return absolute string; never raises for missing files."""
    p = Path(path).expanduser()
    try:
        return str(p.resolve(strict=False))
    except OSError:
        return str(p.absolute())


def _is_tmp_path(path: str | os.PathLike) -> bool:
    """True if *path* sits under ``/tmp`` (macOS resolves to /private/tmp)."""
    resolved = _resolved(path)
    tmp_anchor = _resolved("/tmp")
    return resolved == tmp_anchor or resolved.startswith(tmp_anchor + os.sep)


def _is_production_path(path: str | os.PathLike) -> bool:
    resolved = _resolved(path)
    for prefix in _PRODUCTION_PREFIXES:
        if resolved.startswith(_resolved(prefix)):
            return True
    return False


def _sha256_file(path: Path) -> str:
    if not path.exists():
        return ""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sidecar_path(target: Path) -> Path:
    return target.with_name(target.name + ".gepa-meta.json")


# ---------------------------------------------------------------------------
# PromotionTarget
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class PromotionTarget:
    """A safe-by-construction promotion target.

    Construction rejects production prefixes and paths outside ``/tmp``.
    """

    path: str

    def __post_init__(self) -> None:
        if _is_production_path(self.path):
            raise PromoteError(
                f"refusing to promote into production path: {self.path}"
            )
        if not _is_tmp_path(self.path):
            raise PromoteError(
                f"promotion target must live under /tmp (got {self.path}); "
                "production paths are forbidden by this CLI."
            )

    @property
    def resolved(self) -> Path:
        return Path(_resolved(self.path))


# ---------------------------------------------------------------------------
# Promoter
# ---------------------------------------------------------------------------


class Promoter:
    """Promote and rollback candidates with atomic semantics."""

    # ------------------------------------------------------------------
    # promote
    # ------------------------------------------------------------------

    def promote(
        self,
        *,
        run_dir: str | os.PathLike,
        candidate_id: str,
        target: PromotionTarget,
        backup_dir: str | os.PathLike | None = None,
    ) -> dict[str, Any]:
        """Promote *candidate_id* from *run_dir* into *target* atomically.

        Returns a dict with ``{target, backup_path, sha256_before,
        sha256_after, promoted_at, diff_summary}``.
        """
        if not isinstance(target, PromotionTarget):
            raise PromoteError(
                f"target must be PromotionTarget, got {type(target).__name__}"
            )

        run_path = Path(run_dir).expanduser()
        if not run_path.exists():
            raise PromoteError(f"run_dir does not exist: {run_path}")

        candidate_path = self._locate_candidate(run_path, candidate_id)
        if candidate_path is None:
            raise PromoteError(
                f"candidate {candidate_id!r} not found under {run_path}"
            )

        target_path = target.resolved
        # backup_dir defaults to a sibling of the target (still inside /tmp).
        if backup_dir is None:
            backup_dir_path = target_path.parent / ".gepa-backups"
        else:
            backup_dir_path = Path(_resolved(backup_dir))
            if not _is_tmp_path(backup_dir_path):
                raise PromoteError(
                    f"backup_dir must live under /tmp (got {backup_dir_path})"
                )
        backup_dir_path.mkdir(parents=True, exist_ok=True)

        sha256_before = _sha256_file(target_path)
        timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        backup_path = (
            backup_dir_path
            / f"{target_path.name}.{timestamp}.{candidate_id}.bak"
        )

        # 1. Snapshot current target bytes (if any) → backup.
        if target_path.exists():
            shutil.copy2(target_path, backup_path)
        else:
            # Record an empty backup so rollback can recover the "absent" state.
            backup_path.touch()

        # 2. Atomically replace target with candidate bytes.
        candidate_bytes = candidate_path.read_bytes()
        self._atomic_write(target_path, candidate_bytes)

        sha256_after = _sha256_file(target_path)

        sidecar_data = {
            "schema_version": "gepa.promote_meta.v1",
            "target": str(target_path),
            "run_dir": str(run_path),
            "candidate_id": candidate_id,
            "candidate_path": str(candidate_path),
            "backup_path": str(backup_path),
            "promoted_at": timestamp,
            "sha256_before": sha256_before,
            "sha256_after": sha256_after,
        }
        _sidecar_path(target_path).write_text(
            json.dumps(sidecar_data, indent=2),
            encoding="utf-8",
        )

        return {
            "target": str(target_path),
            "backup_path": str(backup_path),
            "sha256_before": sha256_before,
            "sha256_after": sha256_after,
            "promoted_at": timestamp,
            "diff_summary": {
                "before_bytes": _maybe_size(backup_path),
                "after_bytes": _maybe_size(target_path),
            },
        }

    # ------------------------------------------------------------------
    # rollback
    # ------------------------------------------------------------------

    def rollback(self, *, target: PromotionTarget) -> dict[str, Any]:
        """Restore *target* to the bytes recorded in its sidecar backup."""
        if not isinstance(target, PromotionTarget):
            raise RollbackError(
                f"target must be PromotionTarget, got {type(target).__name__}"
            )

        target_path = target.resolved
        sidecar = _sidecar_path(target_path)
        if not sidecar.exists():
            raise RollbackError(
                f"no promotion metadata for {target_path} (sidecar {sidecar} missing)"
            )
        try:
            meta = json.loads(sidecar.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RollbackError(f"sidecar {sidecar} is malformed: {exc}") from exc

        backup_path = Path(meta.get("backup_path", ""))
        if not backup_path.exists():
            raise RollbackError(
                f"backup file {backup_path} is missing; cannot rollback"
            )

        expected_before = str(meta.get("sha256_before", ""))
        backup_bytes = backup_path.read_bytes()
        # An empty backup represents "no file existed before promotion" — restore
        # that state by deleting the target.
        if backup_bytes == b"" and expected_before == "":
            if target_path.exists():
                target_path.unlink()
        else:
            self._atomic_write(target_path, backup_bytes)

        sha_after_rollback = _sha256_file(target_path)
        if expected_before and sha_after_rollback != expected_before:
            raise RollbackError(
                "rollback sha256 mismatch: "
                f"expected {expected_before!r}, got {sha_after_rollback!r}"
            )

        # Remove sidecar so a subsequent rollback does not double-undo.
        sidecar.unlink()
        return {
            "target": str(target_path),
            "restored_from": str(backup_path),
            "sha256_after_rollback": sha_after_rollback,
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _locate_candidate(run_dir: Path, candidate_id: str) -> Path | None:
        """Find a file matching the candidate id under *run_dir*.

        Search order:
        1. Exact ``run_dir/candidates/<candidate_id>``
        2. ``run_dir/candidates/<candidate_id>.txt``
        3. Top-level ``<candidate_id>`` / ``<candidate_id>.txt``
        4. Glob ``run_dir/**/<candidate_id>*`` (first hit, deterministic order)
        """
        candidates_dir = run_dir / "candidates"
        candidates: list[Path] = [
            candidates_dir / candidate_id,
            candidates_dir / f"{candidate_id}.txt",
            run_dir / candidate_id,
            run_dir / f"{candidate_id}.txt",
        ]
        for p in candidates:
            if p.is_file():
                return p
        matches = sorted(run_dir.glob(f"**/{candidate_id}*"))
        for m in matches:
            if m.is_file():
                return m
        return None

    @staticmethod
    def _atomic_write(target: Path, data: bytes) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=str(target.parent),
        )
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, target)
        except Exception:
            # Best-effort cleanup; let the original exception propagate.
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise


def _maybe_size(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None
