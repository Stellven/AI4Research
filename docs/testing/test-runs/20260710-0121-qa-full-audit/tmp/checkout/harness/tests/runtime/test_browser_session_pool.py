from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))

import browser_job_runtime as bjrt


def test_browser_session_pool_reuses_released_slot(tmp_path):
    pool = bjrt.BrowserSessionPool(
        root=tmp_path / "pool",
        pool_name="test-browser",
        max_size=2,
        acquire_timeout_s=0.05,
        lease_ttl_s=60,
    )

    first = pool.acquire_slot(owner="owner-a")
    assert first["slot_id"] == "slot-001"
    assert pool.release_slot(first["slot_id"], owner="owner-a") is True

    second = pool.acquire_slot(owner="owner-b")
    assert second["slot_id"] == "slot-001"

    snapshot = pool.snapshot()
    assert len(snapshot) == 1
    assert snapshot[0]["state"] == "leased"
    assert snapshot[0]["use_count"] == 2

    assert pool.release_slot(second["slot_id"], owner="owner-b") is True
    assert pool.snapshot()[0]["state"] == "idle"


def test_browser_session_pool_enforces_max_size(tmp_path):
    pool = bjrt.BrowserSessionPool(
        root=tmp_path / "pool",
        pool_name="test-browser",
        max_size=2,
        acquire_timeout_s=0.05,
        lease_ttl_s=60,
        poll_interval_s=0.01,
    )

    first = pool.acquire_slot(owner="owner-a")
    second = pool.acquire_slot(owner="owner-b")
    with pytest.raises(TimeoutError):
        pool.acquire_slot(owner="owner-c")

    pool.release_slot(first["slot_id"], owner="owner-a")
    pool.release_slot(second["slot_id"], owner="owner-b")


def test_run_real_browser_probe_records_pool_lease(monkeypatch, tmp_path):
    jobs_dir = tmp_path / "run" / "browser-jobs"
    monkeypatch.setattr(bjrt, "HARNESS_DIR", tmp_path)
    monkeypatch.setattr(bjrt, "BROWSER_JOBS_DIR", jobs_dir)
    monkeypatch.setattr(bjrt, "BROWSER_USE_ROOT", tmp_path)

    fake_python = tmp_path / "browser-use-python"
    fake_python.write_text("", encoding="utf-8")
    monkeypatch.setattr(bjrt, "BROWSER_USE_PYTHON", fake_python)

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout='{"ok": true, "state": "done", "login_state": "healthy", "title": "Example", "final_url": "https://example.com", "text_excerpt": "ok", "artifacts": {}}\n',
            stderr="",
        )

    monkeypatch.setattr(bjrt.subprocess, "run", fake_run)

    result = bjrt._run_real_browser_probe(
        "job-test-001",
        {"url": "https://example.com", "objective": "Pool smoke"},
        timeout=10,
    )

    assert result["ok"] is True
    lease_path = jobs_dir / "job-test-001" / "daemon-artifacts" / "pool-lease.json"
    assert lease_path.exists()

    pool = bjrt.browser_session_pool_from_env(headless=True, timeout_s=10)
    snapshot = pool.snapshot()
    assert len(snapshot) == 1
    assert snapshot[0]["state"] == "idle"
    assert snapshot[0]["use_count"] == 1
