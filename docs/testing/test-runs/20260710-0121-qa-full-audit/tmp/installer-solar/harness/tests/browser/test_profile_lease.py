"""Tests for harness/lib/browser/profile_lease.py."""
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))

from browser.profile_lease import ProfileLease  # noqa: E402


def test_profile_lease_happy_path(tmp_path: Path) -> None:
    manager = ProfileLease(root=tmp_path / "leases")
    lease = manager.acquire(
        profile_id="profile-happy",
        task_id="task-1",
        runtime="playwright",
        mode="recovery",
        ttl_seconds=60,
        allowed_attach=True,
    )
    assert lease["acquired"] is True
    assert lease["lease"]["profile_id"] == "profile-happy"
    assert lease["lease"]["task_id"] == "task-1"
    assert lease["lease"]["runtime"] == "playwright"
    assert lease["lease"]["mode"] == "recovery"
    assert lease["lease"]["allowed_attach"] is True

    active = manager.list_active()
    assert len(active) == 1
    assert active[0]["profile_id"] == "profile-happy"

    released = manager.release("profile-happy", "task-1")
    assert released["released"] is True
    assert manager.list_active() == []


def test_profile_lease_conflict(tmp_path: Path) -> None:
    manager = ProfileLease(root=tmp_path / "leases")
    first = manager.acquire(
        profile_id="profile-conflict",
        task_id="task-1",
        runtime="playwright",
        mode="recovery",
        ttl_seconds=60,
    )
    assert first["acquired"] is True

    second = manager.acquire(
        profile_id="profile-conflict",
        task_id="task-2",
        runtime="playwright",
        mode="recovery",
        ttl_seconds=60,
    )
    assert second["acquired"] is False
    assert second["reason"] == "already_acquired"
    assert second["held_by"] == "task-1"
    assert manager.release("profile-conflict", "task-1")["released"] is True


def test_profile_lease_expire(tmp_path: Path) -> None:
    manager = ProfileLease(root=tmp_path / "leases", default_ttl_seconds=1)
    lease = manager.acquire(
        profile_id="profile-expire",
        task_id="task-expire",
        runtime="playwright",
        mode="recovery",
        ttl_seconds=0,
    )
    assert lease["acquired"] is True
    # expired immediately by ttl=0
    time.sleep(0.05)
    assert manager.expire("profile-expire") == 1
    assert manager.list_active() == []


def test_profile_lease_supports_nested_profile_ids(tmp_path: Path) -> None:
    manager = ProfileLease(root=tmp_path / "leases")
    lease = manager.acquire(
        profile_id="chatgpt/example-user",
        task_id="task-nested",
        runtime="browser_use",
        mode="exclusive",
        ttl_seconds=60,
    )
    assert lease["acquired"] is True
    active = manager.list_active()
    assert len(active) == 1
    assert active[0]["profile_id"] == "chatgpt/example-user"
    assert manager.release("chatgpt/example-user", "task-nested")["released"] is True
