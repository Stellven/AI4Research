from __future__ import annotations

from pathlib import Path


def test_real_linux_journey_pins_installed_harness_ownership() -> None:
    source = Path(__file__).with_name("test_j18_real_linux_status_lifecycle.py").read_text(encoding="utf-8")

    assert '"HARNESS_DIR": str(solar_home / "harness")' in source
    assert '"SOLAR_HARNESS_DIR": str(solar_home / "harness")' in source
