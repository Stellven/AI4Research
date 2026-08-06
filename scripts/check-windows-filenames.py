#!/usr/bin/env python3
"""check-windows-filenames.py — Detect illegal Windows filenames (R8 Governance).

Windows forbids certain filenames:
  - Reserved device names: CON, PRN, AUX, NUL, COM1-COM9, LPT1-LPT9
    (case-insensitive, with or without extension)
  - Names containing characters: < > : " / \\ | ? *
  - Names ending with a space or period

This script scans all tracked files (via git ls-files) and reports any
filenames that would be illegal on Windows, even when running on Linux/macOS.

Exit 0 = clean; exit 1 = illegal filenames found; exit 2 = scan error.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import PurePosixPath


# Windows reserved device name stem pattern (case-insensitive)
_RESERVED_NAMES = re.compile(
    r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.[^.]*)?$",
    re.IGNORECASE,
)

# Forbidden characters in Windows filenames (anywhere in the name component)
_FORBIDDEN_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def is_illegal_windows_filename(name: str) -> list[str]:
    """Return list of reasons why ``name`` is illegal on Windows, or empty list."""
    reasons: list[str] = []
    if not name:
        return reasons

    # Reserved device names (check the basename only)
    stem = PurePosixPath(name).name
    if _RESERVED_NAMES.fullmatch(stem):
        reasons.append(f"reserved_device_name:{stem}")

    # Forbidden characters (in the basename only)
    match = _FORBIDDEN_CHARS.search(stem)
    if match:
        # Represent the char as its code point to avoid terminal issues
        char = match.group(0)
        if char.isprintable():
            reasons.append(f"forbidden_char:{char!r}")
        else:
            reasons.append(f"forbidden_char:U+{ord(char):04X}")

    # Trailing space or period (in the full path component check)
    if stem.endswith(" ") or stem.endswith("."):
        reasons.append(f"trailing_space_or_period:{stem!r}")

    return reasons


def _list_tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        capture_output=True, check=False,
    )
    if result.returncode != 0:
        return []
    return [
        p for p in result.stdout.decode("utf-8", errors="replace").split("\x00") if p
    ]


def main() -> int:
    files = _list_tracked_files()
    if not files:
        print("check-windows-filenames: no tracked files (not a git repo?)", file=sys.stderr)
        return 2

    violations: list[tuple[str, list[str]]] = []
    for path in files:
        # Check each component of the path
        parts = path.replace("\\", "/").split("/")
        for part in parts:
            reasons = is_illegal_windows_filename(part)
            if reasons:
                violations.append((path, reasons))
                break  # report the full path once

    if not violations:
        print(f"check-windows-filenames passed: {len(files)} files scanned, no illegal names")
        return 0

    print(
        f"check-windows-filenames FAILED: {len(violations)} illegal Windows filename(s):",
        file=sys.stderr,
    )
    for path, reasons in sorted(violations):
        for reason in reasons:
            print(f"  [{reason}] {path}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
