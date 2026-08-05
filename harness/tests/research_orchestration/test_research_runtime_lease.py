from __future__ import annotations

import datetime as dt
import json
from concurrent.futures import ThreadPoolExecutor

from harness.lib.research_orchestration.runtime_lease import ResearchLeaseAdapter


class Clock:
    def __init__(self) -> None:
        self.value = dt.datetime(2026, 8, 5, 12, 0, tzinfo=dt.timezone.utc)

    def __call__(self) -> dt.datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += dt.timedelta(seconds=seconds)


def test_acquire_conflict_same_run_node_returns_blocker(tmp_path) -> None:
    adapter = ResearchLeaseAdapter(tmp_path, clock=Clock())
    first = adapter.acquire("run-1", "N1", "operator-a")
    second = adapter.acquire("run-1", "N1", "operator-b")

    assert first["acquired"] is True
    assert second["acquired"] is False
    assert second["blocker"]["reason"] == "run_node_already_active"


def test_operator_busy_conflict_returns_structured_blocker(tmp_path) -> None:
    adapter = ResearchLeaseAdapter(tmp_path, clock=Clock())
    adapter.acquire("run-1", "N1", "operator-a")
    blocked = adapter.acquire("run-2", "N2", "operator-a")

    assert blocked["blocker"]["reason"] == "operator_busy"
    assert blocked["blocker"]["operator_id"] == "operator-a"


def test_heartbeat_renews_expiry_and_writes_status(tmp_path) -> None:
    clock = Clock()
    adapter = ResearchLeaseAdapter(tmp_path, clock=clock)
    lease = adapter.acquire("run-1", "N1", "operator-a", ttl_seconds=30)["lease"]
    clock.advance(10)

    renewed = adapter.heartbeat("run-1", "N1", "operator-a", lease_id=lease["lease_id"], ttl_seconds=90)
    status = json.loads((tmp_path / "run" / "operator-status" / "operator-a.json").read_text(encoding="utf-8"))

    assert renewed["ok"] is True
    assert renewed["lease"]["state"] == "running"
    assert renewed["lease"]["expires_at"] == "2026-08-05T12:01:40Z"
    assert status["runtime_state"] == "running"


def test_stale_lease_recovery_allows_new_acquire(tmp_path) -> None:
    clock = Clock()
    adapter = ResearchLeaseAdapter(tmp_path, clock=clock)
    adapter.acquire("run-1", "N1", "operator-a", ttl_seconds=5, heartbeat_timeout_seconds=5)
    clock.advance(10)

    blocked = adapter.acquire("run-1", "N1", "operator-b")
    recovered = adapter.acquire("run-1", "N1", "operator-b", recover_stale=True)

    assert blocked["blocker"]["reason"] == "stale_lease_requires_recovery"
    assert recovered["acquired"] is True
    assert recovered["lease"]["operator_id"] == "operator-b"


def test_live_lease_is_not_recovered_or_preempted(tmp_path) -> None:
    adapter = ResearchLeaseAdapter(tmp_path, clock=Clock())
    adapter.acquire("run-1", "N1", "operator-a", ttl_seconds=300)
    recovered = adapter.recover_stale("run-1", "N1")

    assert recovered["blocker"]["reason"] == "active_lease_not_recovered"
    assert (tmp_path / "run" / "operator-leases" / "operator-a.json").exists()


def test_release_removes_active_lease_and_archives(tmp_path) -> None:
    adapter = ResearchLeaseAdapter(tmp_path, clock=Clock())
    lease = adapter.acquire("run-1", "N1", "operator-a")["lease"]
    released = adapter.release("run-1", "N1", "operator-a", lease_id=lease["lease_id"], reason="done")

    assert released["released"] is True
    assert not (tmp_path / "run" / "operator-leases" / "operator-a.json").exists()
    assert list((tmp_path / "run" / "operator-leases" / "archive").glob("*.json"))


def test_crash_restart_reads_existing_active_lease(tmp_path) -> None:
    clock = Clock()
    ResearchLeaseAdapter(tmp_path, clock=clock).acquire("run-1", "N1", "operator-a", ttl_seconds=300)
    restarted = ResearchLeaseAdapter(tmp_path, clock=clock)

    blocked = restarted.acquire("run-1", "N1", "operator-b")

    assert blocked["blocker"]["reason"] == "run_node_already_active"


def test_corrupted_lease_can_be_recovered_by_operator(tmp_path) -> None:
    lease_dir = tmp_path / "run" / "operator-leases"
    lease_dir.mkdir(parents=True)
    (lease_dir / "operator-a.json").write_text("{not json", encoding="utf-8")
    adapter = ResearchLeaseAdapter(tmp_path, clock=Clock())

    result = adapter.acquire("run-1", "N1", "operator-a", recover_stale=True)

    assert result["acquired"] is True


def test_concurrent_same_node_only_one_acquisition_succeeds(tmp_path) -> None:
    adapter = ResearchLeaseAdapter(tmp_path, clock=Clock())

    def acquire(index: int) -> bool:
        return bool(adapter.acquire("run-1", "N1", f"operator-{index}")["acquired"])

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(acquire, range(4)))

    assert results.count(True) == 1
