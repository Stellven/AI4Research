from __future__ import annotations

import pytest

from social_browser_backend_x.hard_blocker_guard import CallableResolver, HardBlockerGuard
from social_browser_backend_x.operator_lease_manager import BlockerNotResolved


def test_hard_blocker_guard_mock_state_allows_fixture_path() -> None:
    guard = HardBlockerGuard(
        resolver=CallableResolver(lambda: False),
        mock_mode_probe=lambda: True,
    )
    status = guard.assert_ready()
    assert status.mode == "mock"
    assert status.mock_ready is True
    assert status.resolved is False
    assert guard.as_lease_guard()() is True


def test_hard_blocker_guard_real_unmet_state_blocks_real_path() -> None:
    guard = HardBlockerGuard(
        resolver=CallableResolver(lambda: False),
        mock_mode_probe=lambda: False,
    )
    status = guard.check()
    assert status.mode == "real"
    assert status.resolved is False
    assert status.mock_ready is False
    with pytest.raises(BlockerNotResolved):
        guard.assert_ready()
    assert guard.as_lease_guard()() is False
