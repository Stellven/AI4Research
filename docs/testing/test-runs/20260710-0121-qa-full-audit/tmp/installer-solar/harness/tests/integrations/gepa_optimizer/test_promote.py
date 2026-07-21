"""Promote / rollback tests with hard /tmp safety guard."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from integrations.gepa_optimizer.promote import (
    PromoteError,
    Promoter,
    PromotionTarget,
    RollbackError,
)


def test_promotion_target_rejects_production_path():
    with pytest.raises(PromoteError):
        PromotionTarget("/etc/passwd")


def test_promotion_target_rejects_non_tmp_path():
    with pytest.raises(PromoteError):
        PromotionTarget(os.path.expanduser("~/some_file.txt"))


def test_promotion_target_accepts_tmp_path():
    pt = PromotionTarget("/tmp/gepa_test_pt.txt")
    assert str(pt.resolved).startswith("/private/tmp") or str(pt.resolved).startswith("/tmp")


def _make_run_with_candidate(tmp_root: Path, candidate_id: str, body: bytes) -> Path:
    run_dir = tmp_root / f"run-{candidate_id}"
    (run_dir / "candidates").mkdir(parents=True)
    (run_dir / "candidates" / candidate_id).write_bytes(body)
    return run_dir


def test_promote_writes_target_and_backup(tmp_path):
    target_path = f"/tmp/gepa_test_promote_{os.getpid()}_{int(time.time())}.txt"
    PromotionTarget(target_path)  # validate
    Path(target_path).write_text("original")

    run_dir = _make_run_with_candidate(tmp_path, "c-1", b"improved candidate")

    try:
        promoter = Promoter()
        result = promoter.promote(
            run_dir=run_dir,
            candidate_id="c-1",
            target=PromotionTarget(target_path),
        )
        assert result["target"] == str(Path(target_path).resolve())
        backup = Path(result["backup_path"])
        assert backup.exists()
        assert Path(target_path).read_text() == "improved candidate"
        # Sidecar must exist for rollback.
        sidecar = Path(target_path + ".gepa-meta.json")
        assert sidecar.exists()
    finally:
        for p in [target_path, target_path + ".gepa-meta.json"]:
            try:
                Path(p).unlink()
            except FileNotFoundError:
                pass


def test_rollback_restores_bytes_exactly(tmp_path):
    target_path = f"/tmp/gepa_test_rollback_{os.getpid()}_{int(time.time())}.txt"
    Path(target_path).write_text("original-bytes")

    run_dir = _make_run_with_candidate(tmp_path, "c-2", b"new candidate text")

    try:
        promoter = Promoter()
        promoter.promote(
            run_dir=run_dir,
            candidate_id="c-2",
            target=PromotionTarget(target_path),
        )
        assert Path(target_path).read_text() == "new candidate text"

        promoter.rollback(target=PromotionTarget(target_path))
        assert Path(target_path).read_text() == "original-bytes"
    finally:
        for p in [target_path, target_path + ".gepa-meta.json"]:
            try:
                Path(p).unlink()
            except FileNotFoundError:
                pass


def test_rollback_without_metadata_raises(tmp_path):
    target_path = f"/tmp/gepa_test_rollback_missing_{os.getpid()}.txt"
    Path(target_path).write_text("x")
    try:
        promoter = Promoter()
        with pytest.raises(RollbackError):
            promoter.rollback(target=PromotionTarget(target_path))
    finally:
        try:
            Path(target_path).unlink()
        except FileNotFoundError:
            pass


def test_promote_unknown_candidate_raises(tmp_path):
    target_path = f"/tmp/gepa_test_unknown_{os.getpid()}.txt"
    Path(target_path).write_text("anything")
    run_dir = tmp_path / "run-empty"
    run_dir.mkdir()
    try:
        promoter = Promoter()
        with pytest.raises(PromoteError):
            promoter.promote(
                run_dir=run_dir,
                candidate_id="does-not-exist",
                target=PromotionTarget(target_path),
            )
    finally:
        try:
            Path(target_path).unlink()
        except FileNotFoundError:
            pass
