#!/usr/bin/env python3
"""Execute a command with a read-only mount tree and exact writable bind mounts.

WSL's DrvFS/9p mount does not honor writable Landlock rules.  This wrapper is
used inside an unprivileged user+mount namespace: it makes every writable mount
read-only, then re-exposes only Solar-declared paths as writable bind mounts.
Landlock can then enforce the read boundary without handling write rights.
"""
from __future__ import annotations

import argparse
import ctypes
import os
import sys
import tempfile
from pathlib import Path


MS_RDONLY = 1
MS_REMOUNT = 32
MS_BIND = 4096
MS_REC = 16384
MS_PRIVATE = 1 << 18


def _decode_mount_field(value: str) -> str:
    for encoded, decoded in (("\\040", " "), ("\\011", "\t"), ("\\012", "\n"), ("\\134", "\\")):
        value = value.replace(encoded, decoded)
    return value


_KERNEL_PSEUDO_FILESYSTEMS = {
    "binfmt_misc",
    "cgroup2",
    "debugfs",
    "devpts",
    "fusectl",
    "hugetlbfs",
    "mqueue",
    "proc",
    "sysfs",
    "tracefs",
}


def _writable_mounts() -> list[Path]:
    mounts: list[Path] = []
    seen_targets: set[str] = set()
    for line in Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) < 6 or "rw" not in fields[5].split(","):
            continue
        try:
            filesystem_type = fields[fields.index("-") + 1]
        except (ValueError, IndexError):
            continue
        if filesystem_type in _KERNEL_PSEUDO_FILESYSTEMS:
            continue
        mountpoint = Path(_decode_mount_field(fields[4]))
        # WSL's device tmpfs cannot be remounted from an unprivileged user
        # namespace. Device-node permissions already deny ordinary file
        # creation; writable child tmpfs mounts such as /dev/shm are handled
        # separately below.
        if mountpoint in {Path("/dev"), Path("/run")}:
            continue
        target_key = str(mountpoint.resolve(strict=False))
        if target_key in seen_targets:
            continue
        seen_targets.add(target_key)
        mounts.append(mountpoint)
    return sorted(set(mounts), key=lambda path: (len(path.parts), str(path)))


def _mount(source: str | None, target: Path, flags: int) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    result = int(
        libc.mount(
            source.encode() if source is not None else None,
            os.fsencode(target),
            None,
            flags,
            None,
        )
    )
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(
            error,
            f"mount operation failed source={source!r} target={target} flags={flags}: {os.strerror(error)}",
        )


def restrict_writes(read_write: list[Path]) -> dict[str, list[str]]:
    _mount(None, Path("/"), MS_REC | MS_PRIVATE)
    empty_read_only = Path(tempfile.mkdtemp(prefix="solar-empty-mount-", dir="/tmp"))
    read_only: list[str] = []
    for mountpoint in _writable_mounts():
        try:
            _mount(None, mountpoint, MS_REMOUNT | MS_BIND | MS_RDONLY)
        except OSError:
            try:
                _mount(str(mountpoint), mountpoint, MS_BIND)
                _mount(None, mountpoint, MS_REMOUNT | MS_BIND | MS_RDONLY)
            except OSError:
                if not mountpoint.is_dir():
                    raise
                # Some WSL tmpfs/9p mounts cannot change attributes in a user
                # namespace. Hide them behind a private empty directory.
                _mount(str(empty_read_only), mountpoint, MS_BIND)
                _mount(None, mountpoint, MS_REMOUNT | MS_BIND | MS_RDONLY)
        read_only.append(str(mountpoint))

    writable: list[str] = []
    seen: set[str] = set()
    for raw in read_write:
        path = raw.expanduser().resolve(strict=False)
        key = str(path)
        if key in seen or not path.exists():
            continue
        _mount(key, path, MS_BIND)
        _mount(None, path, MS_REMOUNT | MS_BIND)
        seen.add(key)
        writable.append(key)
    return {"read_only_mounts": read_only, "read_write": writable}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--read-write", action="append", default=[])
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("a command is required after --")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv if argv is not None else sys.argv[1:]))
    try:
        proof = restrict_writes([Path(item) for item in args.read_write])
    except OSError as exc:
        print(f"mount_namespace_exec: REFUSED: {exc}", file=sys.stderr)
        return 78
    print(
        "mount_namespace_exec: active "
        f"ro={len(proof['read_only_mounts'])} rw={len(proof['read_write'])}",
        file=sys.stderr,
        flush=True,
    )
    os.execvpe(args.command[0], args.command, os.environ.copy())
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
