#!/usr/bin/env python3
"""Execute a command inside a fail-closed Landlock filesystem allowlist.

This is intentionally small and Linux-specific.  It gives Solar command
operators a kernel-enforced read boundary before the selected model runtime is
started.  Network policy remains owned by the workflow/provider contract.
"""
from __future__ import annotations

import argparse
import ctypes
import errno
import os
import sys
from pathlib import Path


SYS_LANDLOCK_CREATE_RULESET = 444
SYS_LANDLOCK_ADD_RULE = 445
SYS_LANDLOCK_RESTRICT_SELF = 446
LANDLOCK_CREATE_RULESET_VERSION = 1
LANDLOCK_RULE_PATH_BENEATH = 1
PR_SET_NO_NEW_PRIVS = 38

ACCESS_FS_EXECUTE = 1 << 0
ACCESS_FS_WRITE_FILE = 1 << 1
ACCESS_FS_READ_FILE = 1 << 2
ACCESS_FS_READ_DIR = 1 << 3
ACCESS_FS_REMOVE_DIR = 1 << 4
ACCESS_FS_REMOVE_FILE = 1 << 5
ACCESS_FS_MAKE_CHAR = 1 << 6
ACCESS_FS_MAKE_DIR = 1 << 7
ACCESS_FS_MAKE_REG = 1 << 8
ACCESS_FS_MAKE_SOCK = 1 << 9
ACCESS_FS_MAKE_FIFO = 1 << 10
ACCESS_FS_MAKE_BLOCK = 1 << 11
ACCESS_FS_MAKE_SYM = 1 << 12
ACCESS_FS_REFER = 1 << 13
ACCESS_FS_TRUNCATE = 1 << 14
ACCESS_FS_IOCTL_DEV = 1 << 15


class RulesetAttr(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64), ("scoped", ctypes.c_uint64)]


class PathBeneathAttr(ctypes.Structure):
    _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]


def landlock_abi(libc: ctypes.CDLL | None = None) -> int:
    libc = libc or ctypes.CDLL(None, use_errno=True)
    result = int(libc.syscall(SYS_LANDLOCK_CREATE_RULESET, 0, 0, LANDLOCK_CREATE_RULESET_VERSION))
    return result


def handled_access_for_abi(abi: int) -> int:
    rights = (1 << 13) - 1
    if abi >= 2:
        rights |= ACCESS_FS_REFER
    if abi >= 3:
        rights |= ACCESS_FS_TRUNCATE
    if abi >= 5:
        rights |= ACCESS_FS_IOCTL_DEV
    return rights


def read_access(handled: int) -> int:
    return handled & (ACCESS_FS_EXECUTE | ACCESS_FS_READ_FILE | ACCESS_FS_READ_DIR)


def _add_path_rule(libc: ctypes.CDLL, ruleset_fd: int, path: Path, access: int) -> None:
    flags = getattr(os, "O_PATH", os.O_RDONLY) | os.O_CLOEXEC
    parent_fd = os.open(path, flags)
    try:
        attr = PathBeneathAttr(allowed_access=access, parent_fd=parent_fd)
        result = int(
            libc.syscall(
                SYS_LANDLOCK_ADD_RULE,
                ruleset_fd,
                LANDLOCK_RULE_PATH_BENEATH,
                ctypes.byref(attr),
                0,
            )
        )
        if result < 0:
            err = ctypes.get_errno()
            raise OSError(err, f"landlock add_rule failed for {path}: {os.strerror(err)}")
    finally:
        os.close(parent_fd)


def restrict_filesystem(read_only: list[Path], read_write: list[Path]) -> dict[str, object]:
    libc = ctypes.CDLL(None, use_errno=True)
    abi = landlock_abi(libc)
    if abi < 1:
        err = ctypes.get_errno() or errno.ENOSYS
        raise OSError(err, "Landlock is unavailable; refusing an unconfined operator")
    handled = handled_access_for_abi(abi)
    ruleset_attr = RulesetAttr(handled_access_fs=handled, scoped=0)
    ruleset_fd = int(
        libc.syscall(
            SYS_LANDLOCK_CREATE_RULESET,
            ctypes.byref(ruleset_attr),
            ctypes.sizeof(ruleset_attr),
            0,
        )
    )
    if ruleset_fd < 0:
        err = ctypes.get_errno()
        raise OSError(err, f"landlock create_ruleset failed: {os.strerror(err)}")
    resolved_ro: list[str] = []
    resolved_rw: list[str] = []
    try:
        seen: set[tuple[str, str]] = set()
        for mode, paths, access, result in (
            ("ro", read_only, read_access(handled), resolved_ro),
            ("rw", read_write, handled, resolved_rw),
        ):
            for raw in paths:
                path = raw.expanduser().resolve(strict=False)
                if not path.exists():
                    continue
                key = (mode, str(path))
                if key in seen:
                    continue
                _add_path_rule(libc, ruleset_fd, path, access)
                seen.add(key)
                result.append(str(path))
        if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
            err = ctypes.get_errno()
            raise OSError(err, f"prctl(PR_SET_NO_NEW_PRIVS) failed: {os.strerror(err)}")
        if libc.syscall(SYS_LANDLOCK_RESTRICT_SELF, ruleset_fd, 0) != 0:
            err = ctypes.get_errno()
            raise OSError(err, f"landlock restrict_self failed: {os.strerror(err)}")
    finally:
        os.close(ruleset_fd)
    return {"abi": abi, "read_only": resolved_ro, "read_write": resolved_rw}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--read-only", action="append", default=[])
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
        proof = restrict_filesystem(
            [Path(item) for item in args.read_only],
            [Path(item) for item in args.read_write],
        )
    except OSError as exc:
        print(f"landlock_exec: REFUSED: {exc}", file=sys.stderr)
        return 78
    print(
        "landlock_exec: active "
        f"abi={proof['abi']} ro={len(proof['read_only'])} rw={len(proof['read_write'])}",
        file=sys.stderr,
        flush=True,
    )
    os.execvpe(args.command[0], args.command, os.environ.copy())
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
