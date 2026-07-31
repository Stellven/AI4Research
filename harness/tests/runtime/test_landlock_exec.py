from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
LANDLOCK_EXEC = ROOT / "tools" / "landlock_exec.py"


@pytest.mark.skipif(sys.platform != "linux", reason="Landlock is Linux-only")
def test_landlock_denies_sibling_directory_read(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    denied = tmp_path / "denied"
    allowed.mkdir()
    denied.mkdir()
    visible = allowed / "visible.txt"
    secret = denied / "secret.txt"
    visible.write_text("visible", encoding="utf-8")
    secret.write_text("must-not-cross-scope", encoding="utf-8")
    code = (
        "from pathlib import Path; import sys; "
        f"assert Path({str(visible)!r}).read_text() == 'visible'; "
        f"p=Path({str(secret)!r}); "
        "\ntry:\n p.read_text()\nexcept PermissionError:\n print('DENIED')\nelse:\n sys.exit(9)"
    )
    command = [
        sys.executable,
        str(LANDLOCK_EXEC),
        "--read-only",
        "/usr",
        "--read-only",
        "/lib",
        "--read-only",
        "/lib64",
        "--read-only",
        "/etc",
        "--read-write",
        str(allowed),
        "--",
        sys.executable,
        "-c",
        code,
    ]

    completed = subprocess.run(command, text=True, capture_output=True, check=False)

    assert completed.returncode == 0, completed.stderr
    assert "DENIED" in completed.stdout
    assert "landlock_exec: active" in completed.stderr


@pytest.mark.skipif(sys.platform != "linux", reason="Landlock is Linux-only")
def test_landlock_allows_write_only_inside_declared_root(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    denied = tmp_path / "denied"
    allowed.mkdir()
    denied.mkdir()
    inside = allowed / "inside.txt"
    outside = denied / "outside.txt"
    code = (
        "from pathlib import Path; import sys; "
        f"Path({str(inside)!r}).write_text('ok'); "
        f"p=Path({str(outside)!r}); "
        "\ntry:\n p.write_text('bad')\nexcept PermissionError:\n print('DENIED')\nelse:\n sys.exit(9)"
    )
    command = [
        sys.executable,
        str(LANDLOCK_EXEC),
        "--read-only",
        "/usr",
        "--read-only",
        "/lib",
        "--read-only",
        "/lib64",
        "--read-only",
        "/etc",
        "--read-write",
        str(allowed),
        "--",
        sys.executable,
        "-c",
        code,
    ]

    completed = subprocess.run(command, text=True, capture_output=True, check=False)

    assert completed.returncode == 0, completed.stderr
    assert inside.read_text(encoding="utf-8") == "ok"
    assert not outside.exists()
