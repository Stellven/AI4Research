#!/usr/bin/env python3
"""Own the complete lifecycle of Solar's temporary Codex trust profiles.

Pane-local EXIT traps remain the fast cleanup path.  This registry is the
product-level fallback for hard pane exits: ``solar-harness stop`` can reap
only profiles registered to its exact harness and tmux session without
globbing foreign Codex configuration.
"""

from __future__ import annotations

import argparse
import datetime
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA = "solar.codex_trust_profile.v1"
MARKER = "# OpenSolar managed Codex trust profile v2; loaded only with --profile.\n"
OWNER_PREFIX = "# OpenSolar managed owner: "
PROFILE_RE = re.compile(r"^solar-managed-[0-9a-f]{20}\.config\.toml$")


class ProfileLifecycleError(RuntimeError):
    """A managed profile could not be proven safe to create or remove."""


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolved_directory(raw: str | Path, *, create: bool = False, mode: int = 0o700) -> Path:
    path = Path(raw).expanduser()
    if create:
        path.mkdir(mode=mode, parents=True, exist_ok=True)
    try:
        metadata = path.stat()
    except OSError as exc:
        raise ProfileLifecycleError(f"directory unavailable: {path}: {exc}") from exc
    if not stat.S_ISDIR(metadata.st_mode):
        raise ProfileLifecycleError(f"not a directory: {path}")
    return path.resolve()


def _registry_dir(harness_dir: str | Path) -> tuple[Path, Path]:
    harness = _resolved_directory(harness_dir)
    current = harness
    for component in ("run", "codex-trust-profiles"):
        current = current / component
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            try:
                current.mkdir(mode=0o700)
            except FileExistsError:
                # All four cockpit panes can reach first-run setup together.
                # Re-read and validate the winner's directory below.
                pass
            metadata = current.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise ProfileLifecycleError(f"unsafe registry directory: {current}")
    os.chmod(current, 0o700)
    return harness, current


def _open_regular(path: Path, flags: int, mode: int = 0o600) -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    try:
        return os.open(path, flags | nofollow, mode)
    except OSError as exc:
        raise ProfileLifecycleError(f"refusing unsafe managed path {path}: {exc}") from exc


@contextmanager
def _registry_lock(registry: Path) -> Iterator[None]:
    lock_path = registry / ".lock"
    fd = _open_regular(lock_path, os.O_RDWR | os.O_CREAT)
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise ProfileLifecycleError(f"registry lock is not regular: {lock_path}")
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _owner_token(harness: Path, owner_id: str) -> str:
    return hashlib.sha256(f"{harness}\0{owner_id}".encode("utf-8")).hexdigest()


def _validate_session(session: str) -> str:
    value = str(session or "").strip()
    if not value or len(value) > 200 or "\x00" in value or "\n" in value:
        raise ProfileLifecycleError("session must be a nonempty single-line value")
    return value


def _validate_owner_id(owner_id: str) -> str:
    value = str(owner_id or "").strip()
    if not value or len(value) > 1024 or "\x00" in value or "\n" in value:
        raise ProfileLifecycleError("owner id must be a nonempty single-line value")
    return value


def _project_root(work_dir: str | Path) -> Path:
    work = _resolved_directory(work_dir)
    try:
        completed = subprocess.run(
            ["git", "-C", str(work), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        candidate = completed.stdout.strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        candidate = str(work)
    return _resolved_directory(candidate)


def _atomic_write(path: Path, content: str, *, mode: int = 0o600) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex}")
    fd = _open_regular(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    published = False
    committed = False
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = -1
            handle.write(content)
            handle.flush()
            os.fchmod(handle.fileno(), mode)
            os.fsync(handle.fileno())
        # Publish without replacing a path planted between validation and the
        # write. The temporary lives in the same directory, so hard-linking is
        # atomic and preserves O_EXCL semantics for the destination.
        os.link(temporary, path, follow_symlinks=False)
        published = True
        temporary.unlink()
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        committed = True
    finally:
        if fd >= 0:
            os.close(fd)
        if published and not committed:
            # The normal path is fully complete at this point. If a later
            # chmod/fsync raised, do not strand a partially committed file.
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def create_profile(
    *,
    harness_dir: str | Path,
    codex_home: str | Path,
    work_dir: str | Path,
    session: str,
    owner_id: str,
    pane: str,
    persona: str,
    launcher_pid: str,
) -> tuple[str, Path]:
    harness, registry = _registry_dir(harness_dir)
    home = _resolved_directory(codex_home, create=True)
    project = _project_root(work_dir)
    session = _validate_session(session)
    owner_id = _validate_owner_id(owner_id)
    owner = _owner_token(harness, owner_id)
    nonce = uuid.uuid4().hex
    identity = "\0".join(
        (
            str(harness),
            session,
            owner_id,
            pane,
            persona,
            str(project),
            str(launcher_pid),
            nonce,
        )
    )
    name = "solar-managed-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    profile = home / f"{name}.config.toml"
    record_path = registry / f"{name}.json"
    content = (
        MARKER
        + OWNER_PREFIX
        + owner
        + "\n"
        + f"[projects.{json.dumps(str(project), ensure_ascii=False)}]\n"
        + 'trust_level = "trusted"\n'
    )
    record = {
        "schema": SCHEMA,
        "profile_name": name,
        "profile_path": str(profile),
        "codex_home": str(home),
        "harness_dir": str(harness),
        "session": session,
        "owner_id": owner_id,
        "pane": pane,
        "persona": persona,
        "launcher_pid": str(launcher_pid),
        "owner_token": owner,
        "created_at": _now(),
    }

    with _registry_lock(registry):
        if (
            profile.exists()
            or profile.is_symlink()
            or record_path.exists()
            or record_path.is_symlink()
        ):
            raise ProfileLifecycleError(f"managed profile identity collision: {name}")
        _atomic_write(
            record_path,
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n",
        )
        try:
            _atomic_write(profile, content)
        except Exception:
            try:
                record_path.unlink()
            except FileNotFoundError:
                pass
            raise
    return name, profile


def _load_record(path: Path) -> dict[str, object]:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ProfileLifecycleError(f"managed record unavailable: {path}: {exc}") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ProfileLifecycleError(f"managed record is not a regular file: {path}")
    if metadata.st_size > 64 * 1024:
        raise ProfileLifecycleError(f"managed record is unexpectedly large: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProfileLifecycleError(f"invalid managed record {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        raise ProfileLifecycleError(f"unsupported managed record: {path}")
    return payload


def _validated_record(
    record_path: Path,
    *,
    harness: Path,
    session: str,
    owner_id: str,
) -> tuple[dict[str, object], Path]:
    payload = _load_record(record_path)
    if payload.get("harness_dir") != str(harness):
        raise ProfileLifecycleError(f"record harness mismatch: {record_path}")
    if payload.get("session") != session:
        raise ProfileLifecycleError(f"record session mismatch: {record_path}")
    if payload.get("owner_id") != owner_id:
        raise ProfileLifecycleError(f"record tmux owner mismatch: {record_path}")
    name = str(payload.get("profile_name") or "")
    filename = f"{name}.config.toml"
    if not PROFILE_RE.fullmatch(filename) or record_path.name != f"{name}.json":
        raise ProfileLifecycleError(f"record profile name mismatch: {record_path}")
    home = Path(str(payload.get("codex_home") or ""))
    profile = Path(str(payload.get("profile_path") or ""))
    if not home.is_absolute() or not profile.is_absolute():
        raise ProfileLifecycleError(f"record uses non-absolute paths: {record_path}")
    if profile.parent != home or profile.name != filename:
        raise ProfileLifecycleError(f"record profile escaped its Codex home: {record_path}")
    expected_owner = _owner_token(harness, owner_id)
    if payload.get("owner_token") != expected_owner:
        raise ProfileLifecycleError(f"record owner mismatch: {record_path}")
    return payload, profile


def _remove_record(
    record_path: Path,
    *,
    harness: Path,
    session: str,
    owner_id: str,
) -> str:
    payload, profile = _validated_record(
        record_path, harness=harness, session=session, owner_id=owner_id
    )
    try:
        metadata = profile.lstat()
    except FileNotFoundError:
        record_path.unlink()
        return "already_absent"
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ProfileLifecycleError(f"refusing non-regular managed profile: {profile}")
    if metadata.st_size > 1024 * 1024:
        raise ProfileLifecycleError(f"managed profile is unexpectedly large: {profile}")
    try:
        with profile.open("r", encoding="utf-8") as handle:
            prefix = handle.read(512)
    except (OSError, UnicodeError) as exc:
        raise ProfileLifecycleError(f"cannot verify managed profile {profile}: {exc}") from exc
    owner_line = OWNER_PREFIX + str(payload["owner_token"]) + "\n"
    if not prefix.startswith(MARKER + owner_line):
        raise ProfileLifecycleError(f"refusing non-OpenSolar or foreign profile: {profile}")
    profile.unlink()
    record_path.unlink()
    return "removed"


def remove_profile(
    *,
    harness_dir: str | Path,
    session: str,
    owner_id: str,
    profile_path: str | Path,
) -> dict[str, object]:
    harness, registry = _registry_dir(harness_dir)
    session = _validate_session(session)
    owner_id = _validate_owner_id(owner_id)
    profile = Path(profile_path)
    name = profile.name.removesuffix(".config.toml")
    if not PROFILE_RE.fullmatch(profile.name):
        raise ProfileLifecycleError(f"invalid managed profile name: {profile}")
    record_path = registry / f"{name}.json"
    with _registry_lock(registry):
        if not record_path.exists() and not record_path.is_symlink():
            if profile.exists() or profile.is_symlink():
                raise ProfileLifecycleError(
                    f"managed profile exists without its ownership record: {profile}"
                )
            return {
                "ok": True,
                "session": session,
                "profile": str(profile),
                "outcome": "already_absent",
            }
        _payload, recorded_profile = _validated_record(
            record_path, harness=harness, session=session, owner_id=owner_id
        )
        if profile != recorded_profile:
            raise ProfileLifecycleError(f"profile path does not match its record: {profile}")
        outcome = _remove_record(
            record_path, harness=harness, session=session, owner_id=owner_id
        )
    return {"ok": True, "session": session, "profile": str(profile), "outcome": outcome}


def reap_profiles(
    *,
    harness_dir: str | Path,
    session: str,
    owner_id: str | None,
) -> dict[str, object]:
    harness, registry = _registry_dir(harness_dir)
    session = _validate_session(session)
    owner_id = _validate_owner_id(owner_id) if owner_id else None
    removed: list[str] = []
    already_absent: list[str] = []
    errors: list[str] = []
    with _registry_lock(registry):
        for record_path in sorted(registry.glob("solar-managed-*.json")):
            try:
                payload = _load_record(record_path)
                if payload.get("harness_dir") != str(harness) or payload.get("session") != session:
                    continue
                if owner_id is None:
                    preserved = payload.get("profile_path", record_path)
                    errors.append(f"exact tmux owner unavailable; preserved {preserved}")
                    continue
                if payload.get("owner_id") != owner_id:
                    continue
                profile = str(payload.get("profile_path") or "")
                outcome = _remove_record(
                    record_path,
                    harness=harness,
                    session=session,
                    owner_id=owner_id,
                )
                if outcome == "removed":
                    removed.append(profile)
                else:
                    already_absent.append(profile)
            except ProfileLifecycleError as exc:
                errors.append(str(exc))
    return {
        "ok": not errors,
        "session": session,
        "removed": removed,
        "already_absent": already_absent,
        "errors": errors,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create")
    create.add_argument("--harness-dir", required=True)
    create.add_argument("--codex-home", required=True)
    create.add_argument("--work-dir", required=True)
    create.add_argument("--session", required=True)
    create.add_argument("--owner-id", required=True)
    create.add_argument("--pane", default="")
    create.add_argument("--persona", required=True)
    create.add_argument("--launcher-pid", required=True)

    remove = subparsers.add_parser("remove")
    remove.add_argument("--harness-dir", required=True)
    remove.add_argument("--session", required=True)
    remove.add_argument("--owner-id", required=True)
    remove.add_argument("--profile-path", required=True)

    reap = subparsers.add_parser("reap")
    reap.add_argument("--harness-dir", required=True)
    reap.add_argument("--session", required=True)
    reap.add_argument("--owner-id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "create":
            name, profile = create_profile(
                harness_dir=args.harness_dir,
                codex_home=args.codex_home,
                work_dir=args.work_dir,
                session=args.session,
                owner_id=args.owner_id,
                pane=args.pane,
                persona=args.persona,
                launcher_pid=args.launcher_pid,
            )
            print(name)
            print(profile)
            return 0
        if args.command == "remove":
            result = remove_profile(
                harness_dir=args.harness_dir,
                session=args.session,
                owner_id=args.owner_id,
                profile_path=args.profile_path,
            )
        else:
            result = reap_profiles(
                harness_dir=args.harness_dir,
                session=args.session,
                owner_id=args.owner_id,
            )
    except ProfileLifecycleError as exc:
        print(f"codex trust profile lifecycle error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
