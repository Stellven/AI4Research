#!/usr/bin/env python3
"""Build and verify the self-contained OpenSolar Linux runtime deliverable."""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from jsonschema import Draft202012Validator


SCHEMA_VERSION = "opensolar.runtime-deliverable/v1"
MANIFEST_NAME = "runtime-deliverable-manifest.json"
SCHEMA_NAME = "runtime-deliverable.schema.json"
REPLAY_NAME = "replay.sh"
BOOTSTRAP_NAME = "bundled-get-solar.sh"
VERIFY_NAME = "verify.py"
SMOKE_NAME = "smoke.sh"
SOURCE_PATHS = (
    "VERSION",
    "install.sh",
    "bin",
    "lib/installer",
    "components.d/kernel",
    "components.d/harness",
    "kernel",
    "rules",
    "agents",
    "hooks",
    ".claude/prompts",
    "harness",
    "requirements",
    "core/db",
    "distribution/pipx",
)
SECRET_VALUE_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}\b", re.IGNORECASE),
    re.compile(r"\bBasic\s+[A-Za-z0-9+/]{20,}={0,2}(?![A-Za-z0-9+/=])", re.IGNORECASE),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)
# Exact fingerprints of reviewed, deliberately fake credentials embedded in
# tracked benchmark/test/gitleaks fixtures. This does not allowlist a path or
# pattern: any changed or newly introduced secret-like value still fails.
REVIEWED_PLACEHOLDER_SECRET_SHA256_BY_PATH = {
    "harness/docs/benchmark/terminal-bench-2.md": {"e92a0768d8d452b79eef95d09cf4a9024d49a905ff7a0678842bf1e74855c185"},
    "harness/gitleaks.toml": {
        "7cf4633c4c272c2663c20eb455e83fe3cc11d6895f9d53bad1dfd5b5ddea2f58",
        "913ead83f1dfa3d87d03a613627443b9106d50e324fe050c345d89445ddcf7fc",
        "ebdb4e031287a4be980e403e26a6ccbb03a83966133d150f630f37a31f6120e2",
    },
    "harness/installer/install.sh": {
        "28a11611b79776c46f682c989cc5888c70d1d177c762d9876d005ac8d0ddbdec",
        "bee7da7ddaa2cf04d272f059b710f2ca1081fa2904defbac01db87a33f6d7532",
    },
    "harness/lib/runtime_chaos_suite.py": {"ceff7b932509dac8bb91000d9891d51d6113ae682c5af411df1c3a6b7a39e3d6"},
    "harness/plugins/autosci/tests/test_autosci_skill_shim.py": {
        "81407ef863d8ffa58139ac2ebe28b92554ecf848f3b820065de3d7c2c422f265",
        "8f8fc50915a2b2b94a7812c9fd41e88c5680cfd6079b7523daf996f4462ff49a",
        "fd5576621a2b971feb1640468a25884ad4e6fe277c63026ef7f928c4136860ca",
    },
    "harness/scripts/thunderomlx_start_8002.sh": {"f5abcc69693d0a47e84a900d4df308ba51ba5b16a671526998a55bf5b3a569cf"},
    "harness/scripts/thunderomlx_start_8003_vlm.sh": {"f5abcc69693d0a47e84a900d4df308ba51ba5b16a671526998a55bf5b3a569cf"},
    "harness/tests/integrations/gepa_optimizer/test_gepa_optimizer_evaluator.py": {"301e06ecb1a9e3be0ed91f1abda27efa7194b6941c64b6ee189f5dca48a1c56b"},
    "harness/tests/test_operatord_daemon.py": {
        "04f4dc9c28ae9ff9bfd7d8484de03cc4e339a2bf9839c58fa27e73e39f5c4033",
        "16a1d8b31fd8a907a6fa2c472c78201bda00c4231011331b99b73b1940305b77",
        "e0573a0ab82867783d5d264518b7a594a5b7d5545e56e29eeae377aa006add25",
    },
    "harness/tools/runtime_chaos_suite.py": {"ceff7b932509dac8bb91000d9891d51d6113ae682c5af411df1c3a6b7a39e3d6"},
}
FORBIDDEN_VALUE_KEYS = {
    "api_key",
    "apikey",
    "access_token",
    "auth_token",
    "password",
    "private_key",
    "credential",
}
ZIP_ARCHIVE_SUFFIXES = {".zip", ".whl"}
MAX_ARCHIVE_DEPTH = 4
MAX_ARCHIVE_MEMBERS = 20_000
MAX_ARCHIVE_MEMBER_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_TOTAL_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_COMPRESSION_RATIO = 500


class DeliverableError(RuntimeError):
    """Raised when a runtime deliverable cannot be built or verified."""


def _repo_path_from_scan_label(label: str) -> str:
    if "!blobs/" in label:
        tail = label.split("!blobs/", 1)[1]
        parts = tail.split("/", 1)
        return parts[1] if len(parts) == 2 else ""
    parts = label.split("!")
    return parts[1] if len(parts) == 2 else ""


def _is_reviewed_placeholder(value: str, label: str) -> bool:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    repo_path = _repo_path_from_scan_label(label)
    return digest in REVIEWED_PLACEHOLDER_SECRET_SHA256_BY_PATH.get(repo_path, set())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record_hash(data: bytes) -> str:
    encoded = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode("ascii").rstrip("=")
    return f"sha256={encoded}"


def _wheel_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    return info


def _build_pure_python_wheel(package_dir: Path, metadata: dict[str, Any], wheel: Path) -> None:
    normalized_name = str(metadata["name"]).replace("-", "_")
    version = str(metadata["version"])
    dist_info = f"{normalized_name}-{version}.dist-info"
    members: dict[str, bytes] = {}
    source_package = package_dir / "opensolar_cli"
    for source in sorted(source_package.glob("*.py")):
        members[f"opensolar_cli/{source.name}"] = source.read_bytes()
    members[f"{dist_info}/METADATA"] = (
        "Metadata-Version: 2.1\n"
        f"Name: {metadata['name']}\n"
        f"Version: {version}\n"
        f"Summary: {metadata['description']}\n"
        f"Requires-Python: {metadata['requires-python']}\n"
        "License: MIT\n\n"
    ).encode("utf-8")
    members[f"{dist_info}/WHEEL"] = (
        "Wheel-Version: 1.0\n"
        "Generator: opensolar-runtime-deliverable/1\n"
        "Root-Is-Purelib: true\n"
        "Tag: py3-none-any\n"
    ).encode("utf-8")
    members[f"{dist_info}/entry_points.txt"] = (
        "[console_scripts]\nopenjiuwen-solar = opensolar_cli.cli:main\n"
    ).encode("utf-8")
    record_name = f"{dist_info}/RECORD"
    record_lines = [
        f"{name},{_record_hash(data)},{len(data)}" for name, data in sorted(members.items())
    ]
    record_lines.append(f"{record_name},,")
    members[record_name] = ("\n".join(record_lines) + "\n").encode("utf-8")
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, data in sorted(members.items()):
            archive.writestr(_wheel_info(name), data)


def _repo_head(repo_root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        raise DeliverableError("source Git commit could not be resolved")
    return completed.stdout.strip()


def _git_source_archive(repo_root: Path, commit: str, target: Path) -> None:
    _, _, blobs = _collect_git_source_objects(repo_root, commit, SOURCE_PATHS)
    _write_git_source_archive_from_objects(commit, blobs, target)


def _git_object_id(kind: str, data: bytes) -> str:
    header = f"{kind} {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()  # noqa: S324 - Git object format is SHA-1.


def _git_cat_object(repo_root: Path, kind: str, oid: str) -> bytes:
    completed = subprocess.run(
        ["git", "cat-file", kind, oid],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise DeliverableError(f"Git {kind} object is unavailable: {oid}")
    data = completed.stdout
    if _git_object_id(kind, data) != oid:
        raise DeliverableError(f"Git {kind} object hash mismatch: {oid}")
    return data


def _git_cat_objects(repo_root: Path, oids: list[str]) -> dict[str, tuple[str, bytes]]:
    completed = subprocess.run(
        ["git", "cat-file", "--batch"],
        cwd=repo_root,
        input=("\n".join(oids) + "\n").encode("ascii"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise DeliverableError("Git batch object read failed")
    output = completed.stdout
    offset = 0
    objects: dict[str, tuple[str, bytes]] = {}
    for requested in oids:
        newline = output.find(b"\n", offset)
        if newline < 0:
            raise DeliverableError("Git batch object output is truncated")
        header = output[offset:newline].decode("ascii", errors="strict").split(" ")
        if len(header) != 3 or header[0] != requested:
            raise DeliverableError(f"Git batch object header mismatch: {requested}")
        oid, kind, raw_size = header
        size = int(raw_size)
        start = newline + 1
        end = start + size
        data = output[start:end]
        if len(data) != size or end >= len(output) or output[end : end + 1] != b"\n":
            raise DeliverableError(f"Git batch object payload is truncated: {oid}")
        if _git_object_id(kind, data) != oid:
            raise DeliverableError(f"Git batch {kind} object hash mismatch: {oid}")
        objects[oid] = (kind, data)
        offset = end + 1
    return objects


def _commit_tree_oid(commit_data: bytes) -> str:
    first_line = commit_data.split(b"\n", 1)[0]
    if not re.fullmatch(rb"tree [0-9a-f]{40}", first_line):
        raise DeliverableError("Git commit object has no canonical tree header")
    return first_line[5:].decode("ascii")


def _parse_git_tree(data: bytes) -> list[tuple[str, str, str]]:
    entries: list[tuple[str, str, str]] = []
    offset = 0
    while offset < len(data):
        space = data.find(b" ", offset)
        nul = data.find(b"\0", space + 1)
        if space <= offset or nul < 0 or nul + 21 > len(data):
            raise DeliverableError("malformed Git tree object")
        mode = data[offset:space].decode("ascii")
        name = data[space + 1 : nul].decode("utf-8", errors="strict")
        if not name or "/" in name or name in {".", ".."}:
            raise DeliverableError("unsafe path in Git tree object")
        oid = data[nul + 1 : nul + 21].hex()
        entries.append((mode, name, oid))
        offset = nul + 21
    return entries


def _path_relevant(path: str, included_paths: tuple[str, ...] | list[str]) -> bool:
    return any(
        path == included or path.startswith(f"{included}/") or included.startswith(f"{path}/")
        for included in included_paths
    )


def _path_selected(path: str, included_paths: tuple[str, ...] | list[str]) -> bool:
    return any(path == included or path.startswith(f"{included}/") for included in included_paths)


def _collect_git_source_objects(
    repo_root: Path, commit: str, included_paths: tuple[str, ...] | list[str]
) -> tuple[bytes, dict[str, bytes], dict[str, tuple[str, str, bytes]]]:
    commit_data = _git_cat_object(repo_root, "commit", commit)
    root_tree = _commit_tree_oid(commit_data)
    listing = subprocess.run(
        ["git", "ls-tree", "-r", "-t", "-z", commit, "--", *included_paths],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if listing.returncode != 0:
        raise DeliverableError("could not enumerate declared Git source tree")
    rows: list[tuple[str, str, str, str]] = []
    object_ids = {root_tree}
    for record in listing.stdout.split(b"\0"):
        if not record:
            continue
        try:
            header, raw_path = record.split(b"\t", 1)
            mode, kind, oid = header.decode("ascii").split(" ")
            path = raw_path.decode("utf-8", errors="strict")
        except (ValueError, UnicodeDecodeError) as exc:
            raise DeliverableError("Git source tree listing is malformed") from exc
        rows.append((mode, kind, oid, path))
        object_ids.add(oid)
    objects = _git_cat_objects(repo_root, sorted(object_ids))
    trees = {oid: data for oid, (kind, data) in objects.items() if kind == "tree"}
    blobs: dict[str, tuple[str, str, bytes]] = {}
    for mode, kind, oid, path in rows:
        if kind == "tree":
            continue
        if kind != "blob" or mode not in {"100644", "100755"}:
            raise DeliverableError(f"unsupported Git source mode {mode}: {path}")
        object_kind, data = objects[oid]
        if object_kind != "blob":
            raise DeliverableError(f"Git source object type mismatch: {path}")
        blobs[path] = (mode, oid, data)
    for included in included_paths:
        if not any(path == included or path.startswith(f"{included}/") for path in blobs):
            raise DeliverableError(f"included source path is absent from commit: {included}")
    return commit_data, trees, blobs


def _write_git_source_archive_from_objects(
    commit: str,
    blobs: dict[str, tuple[str, str, bytes]],
    target: Path,
) -> None:
    with zipfile.ZipFile(target, "w") as archive:
        archive.comment = commit.encode("ascii")
        for path, (mode, _, data) in sorted(blobs.items()):
            info = _wheel_info(path)
            info.external_attr = int(mode, 8) << 16
            archive.writestr(info, data)


def _zip_file_payloads(data: bytes, label: str) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for info in archive.infolist():
                path = _safe_archive_member_name(info.filename, label)
                if _archive_member_is_symlink(info):
                    raise DeliverableError(f"symlink archive member is forbidden: {label}!{path}")
                if info.is_dir():
                    continue
                if path in files:
                    raise DeliverableError(f"duplicate archive member: {label}!{path}")
                files[path] = archive.read(info)
    except (OSError, zipfile.BadZipFile, RuntimeError, NotImplementedError, ValueError) as exc:
        raise DeliverableError(f"unreadable ZIP archive {label}: {exc}") from exc
    return files


def _write_git_object_proof(
    repo_root: Path,
    commit: str,
    source_archive: Path,
    target: Path,
    objects: tuple[bytes, dict[str, bytes], dict[str, tuple[str, str, bytes]]] | None = None,
) -> None:
    commit_data, trees, blobs = objects or _collect_git_source_objects(repo_root, commit, SOURCE_PATHS)
    source_files = _zip_file_payloads(source_archive.read_bytes(), source_archive.name)
    if set(source_files) != set(blobs):
        raise DeliverableError("Git source archive file set differs from the declared commit paths")
    for path, (_, _, blob_data) in blobs.items():
        if source_files[path] != blob_data:
            raise DeliverableError(f"Git source archive blob differs from commit: {path}")

    members: dict[str, bytes] = {f"commit/{commit}": commit_data}
    members.update({f"trees/{oid}": data for oid, data in trees.items()})
    members.update({f"blobs/{oid}/{path}": data for path, (_, oid, data) in blobs.items()})
    with zipfile.ZipFile(target, "w") as archive:
        for name, data in sorted(members.items()):
            archive.writestr(_wheel_info(name), data)


def _safe_relative(raw: str) -> Path:
    path = Path(raw)
    if not raw or path.is_absolute() or ".." in path.parts:
        raise DeliverableError(f"unsafe relative path: {raw!r}")
    return path


def _contained_regular_file(bundle_root: Path, relative: str) -> Path:
    path = bundle_root / _safe_relative(relative)
    try:
        mode = path.lstat().st_mode
    except OSError as exc:
        raise DeliverableError(f"missing asset: {relative}") from exc
    if stat.S_ISLNK(mode):
        raise DeliverableError(f"symlink asset is forbidden: {relative}")
    if not stat.S_ISREG(mode):
        raise DeliverableError(f"asset is not a regular file: {relative}")
    root = bundle_root.resolve(strict=True)
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise DeliverableError(f"asset escapes bundle root: {relative}") from exc
    return resolved


def _iter_regular_files(bundle_root: Path) -> Iterable[tuple[str, Path]]:
    try:
        root_mode = bundle_root.lstat().st_mode
    except OSError as exc:
        raise DeliverableError(f"bundle root is unavailable: {bundle_root}") from exc
    if stat.S_ISLNK(root_mode) or not stat.S_ISDIR(root_mode):
        raise DeliverableError("bundle root must be a real directory, not a symlink")
    root = bundle_root.resolve(strict=True)
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in list(directories):
            candidate = current_path / name
            mode = candidate.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise DeliverableError(f"symlink directory is forbidden: {candidate.relative_to(root).as_posix()}")
            if not stat.S_ISDIR(mode):
                raise DeliverableError(f"non-directory entry in directory walk: {candidate}")
        for name in files:
            candidate = current_path / name
            mode = candidate.lstat().st_mode
            relative = candidate.relative_to(root).as_posix()
            if stat.S_ISLNK(mode):
                raise DeliverableError(f"symlink file is forbidden: {relative}")
            if not stat.S_ISREG(mode):
                raise DeliverableError(f"non-regular bundle entry is forbidden: {relative}")
            resolved = candidate.resolve(strict=True)
            try:
                resolved.relative_to(root)
            except ValueError as exc:
                raise DeliverableError(f"bundle entry escapes root: {relative}") from exc
            yield relative, resolved


def _walk_values(value: Any, path: str = "$") -> list[str]:
    failures: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}"
            if str(key).lower() in FORBIDDEN_VALUE_KEYS and isinstance(item, str) and item.strip():
                failures.append(f"embedded credential value at {child}")
            failures.extend(_walk_values(item, child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            failures.extend(_walk_values(item, f"{path}[{index}]"))
    elif isinstance(value, str):
        for pattern in SECRET_VALUE_PATTERNS:
            if any(not _is_reviewed_placeholder(match.group(0), path) for match in pattern.finditer(value)):
                failures.append(f"secret-like value at {path}")
                break
    return failures


def _scan_text(data: bytes, label: str) -> list[str]:
    text = data.decode("utf-8", errors="ignore")
    failures: list[str] = []
    for pattern in SECRET_VALUE_PATTERNS:
        if any(not _is_reviewed_placeholder(match.group(0), label) for match in pattern.finditer(text)):
            failures.append(f"secret-like content in {label}")
            break
    if label.lower().endswith(".json"):
        try:
            failures.extend(_walk_values(json.loads(text), label))
        except json.JSONDecodeError:
            pass
    return failures


def _archive_member_is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0o170000
    return mode == stat.S_IFLNK


def _safe_archive_member_name(raw: str, label: str) -> str:
    if not raw or "\x00" in raw or "\\" in raw:
        raise DeliverableError(f"unsafe archive member path: {label}!{raw}")
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts or re.match(r"^[A-Za-z]:", raw):
        raise DeliverableError(f"unsafe archive member path: {label}!{raw}")
    return path.as_posix()


def _scan_zip_bytes(
    data: bytes,
    label: str,
    *,
    depth: int = 0,
    budget: dict[str, int] | None = None,
) -> tuple[list[str], str, bytes]:
    """Safely inspect a ZIP-compatible archive without extracting it to disk."""

    failures: list[str] = []
    tree_records: list[dict[str, Any]] = []
    archive_comment = b""
    budget = budget if budget is not None else {"members": 0, "bytes": 0}
    if depth > MAX_ARCHIVE_DEPTH:
        return [f"archive nesting limit exceeded: {label}"], "", b""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            archive_comment = archive.comment
            seen: set[str] = set()
            failures.extend(_scan_text(archive_comment, f"{label}!<comment>"))
            for info in archive.infolist():
                try:
                    member = _safe_archive_member_name(info.filename, label)
                except DeliverableError as exc:
                    failures.append(str(exc))
                    continue
                if member in seen:
                    failures.append(f"duplicate archive member: {label}!{member}")
                    continue
                seen.add(member)
                if _archive_member_is_symlink(info):
                    failures.append(f"symlink archive member is forbidden: {label}!{member}")
                    continue
                if info.flag_bits & 0x1:
                    failures.append(f"encrypted archive member is forbidden: {label}!{member}")
                    continue
                budget["members"] += 1
                budget["bytes"] += info.file_size
                if budget["members"] > MAX_ARCHIVE_MEMBERS:
                    failures.append(f"archive member-count limit exceeded: {label}")
                    break
                if info.file_size > MAX_ARCHIVE_MEMBER_BYTES:
                    failures.append(f"archive member size limit exceeded: {label}!{member}")
                    continue
                if budget["bytes"] > MAX_ARCHIVE_TOTAL_BYTES:
                    failures.append(f"archive total size limit exceeded: {label}")
                    break
                if (
                    info.file_size > 1024 * 1024
                    and info.file_size > max(info.compress_size, 1) * MAX_ARCHIVE_COMPRESSION_RATIO
                ):
                    failures.append(f"archive compression-ratio limit exceeded: {label}!{member}")
                    continue
                if info.is_dir():
                    tree_records.append({"path": member, "type": "directory", "mode": info.external_attr >> 16})
                    continue
                with archive.open(info) as stream:
                    member_data = stream.read(MAX_ARCHIVE_MEMBER_BYTES + 1)
                if len(member_data) != info.file_size:
                    failures.append(f"archive member size mismatch: {label}!{member}")
                    continue
                member_label = f"{label}!{member}"
                failures.extend(_scan_text(member_data, member_label))
                tree_records.append(
                    {
                        "path": member,
                        "type": "file",
                        "mode": info.external_attr >> 16,
                        "bytes": len(member_data),
                        "sha256": hashlib.sha256(member_data).hexdigest(),
                    }
                )
                nested_suffix = PurePosixPath(member).suffix.lower()
                if nested_suffix in ZIP_ARCHIVE_SUFFIXES or zipfile.is_zipfile(io.BytesIO(member_data)):
                    nested_failures, _, _ = _scan_zip_bytes(
                        member_data,
                        member_label,
                        depth=depth + 1,
                        budget=budget,
                    )
                    failures.extend(nested_failures)
    except (OSError, zipfile.BadZipFile, RuntimeError, NotImplementedError, ValueError) as exc:
        failures.append(f"unreadable ZIP archive {label}: {exc}")
    encoded_tree = json.dumps(
        sorted(tree_records, key=lambda row: (row["path"], row["type"])),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return failures, hashlib.sha256(encoded_tree).hexdigest(), archive_comment


def _zip_identity(path: Path, label: str) -> tuple[str, bytes]:
    failures, tree_sha256, comment = _scan_zip_bytes(path.read_bytes(), label)
    if failures:
        raise DeliverableError("; ".join(sorted(set(failures))))
    return tree_sha256, comment


def _git_in_temp_repo(arguments: list[str], git_dir: Path, *, data: bytes | None = None) -> bytes:
    completed = subprocess.run(
        ["git", f"--git-dir={git_dir}", *arguments],
        input=data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace")[-1000:]
        raise DeliverableError(f"isolated Git object verification failed: {detail}")
    return completed.stdout


def _verify_git_object_proof(
    proof_path: Path,
    source_archive: Path,
    source: dict[str, Any],
) -> None:
    proof_files = _zip_file_payloads(proof_path.read_bytes(), proof_path.name)
    commit = source["git_commit"]
    commit_name = f"commit/{commit}"
    commit_data = proof_files.pop(commit_name, None)
    if commit_data is None or _git_object_id("commit", commit_data) != commit:
        raise DeliverableError("Git object proof does not contain the declared commit preimage")

    tree_objects: dict[str, bytes] = {}
    blob_objects: dict[str, tuple[str, bytes]] = {}
    for name, data in proof_files.items():
        tree_match = re.fullmatch(r"trees/([0-9a-f]{40})", name)
        blob_match = re.fullmatch(r"blobs/([0-9a-f]{40})/(.+)", name)
        if tree_match:
            oid = tree_match.group(1)
            if _git_object_id("tree", data) != oid:
                raise DeliverableError(f"Git tree object preimage mismatch: {oid}")
            tree_objects[oid] = data
        elif blob_match:
            oid, path = blob_match.groups()
            _safe_archive_member_name(path, proof_path.name)
            if _git_object_id("blob", data) != oid:
                raise DeliverableError(f"Git blob object preimage mismatch: {path}")
            if path in blob_objects:
                raise DeliverableError(f"duplicate Git proof blob path: {path}")
            blob_objects[path] = (oid, data)
        else:
            raise DeliverableError(f"unexpected Git object proof entry: {name}")

    with tempfile.TemporaryDirectory(prefix="opensolar-git-proof-") as temp_dir:
        git_dir = Path(temp_dir) / "proof.git"
        initialized = subprocess.run(
            ["git", "init", "--bare", "--quiet", str(git_dir)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if initialized.returncode != 0:
            raise DeliverableError("could not initialize isolated Git proof repository")
        for kind, oid, data in [
            ("commit", commit, commit_data),
            *(("tree", oid, data) for oid, data in tree_objects.items()),
            *(("blob", oid, data) for oid, data in blob_objects.values()),
        ]:
            written = _git_in_temp_repo(["hash-object", "-t", kind, "-w", "--stdin"], git_dir, data=data)
            if written.decode("ascii").strip() != oid:
                raise DeliverableError(f"isolated Git repository wrote a different {kind} object id")
        _git_in_temp_repo(["cat-file", "-e", f"{commit}^{{commit}}"], git_dir)
        listing = _git_in_temp_repo(
            ["ls-tree", "-r", "-z", commit, "--", *source["included_paths"]], git_dir
        )

    committed: dict[str, tuple[str, str]] = {}
    for record in listing.split(b"\0"):
        if not record:
            continue
        try:
            header, raw_path = record.split(b"\t", 1)
            mode, kind, oid = header.decode("ascii").split(" ")
            path = raw_path.decode("utf-8", errors="strict")
        except (ValueError, UnicodeDecodeError) as exc:
            raise DeliverableError("isolated Git ls-tree returned malformed output") from exc
        if kind != "blob" or mode not in {"100644", "100755"}:
            raise DeliverableError(f"unsupported source object in declared commit: {path}")
        committed[path] = (mode, oid)

    source_files = _zip_file_payloads(source_archive.read_bytes(), source_archive.name)
    if set(committed) != set(blob_objects) or set(committed) != set(source_files):
        raise DeliverableError("source ZIP/proof path set differs from the declared commit tree")
    for path, (_, committed_oid) in committed.items():
        proof_oid, proof_data = blob_objects[path]
        if committed_oid != proof_oid or source_files[path] != proof_data:
            raise DeliverableError(f"source ZIP blob is not bound to declared commit: {path}")


def _asset_entry(path: Path, bundle_root: Path, kind: str) -> dict[str, Any]:
    return {
        "path": path.relative_to(bundle_root).as_posix(),
        "kind": kind,
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _canonical_schema() -> tuple[dict[str, Any], bytes]:
    path = Path(__file__).resolve().with_name(SCHEMA_NAME)
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
        Draft202012Validator.check_schema(payload)
    except Exception as exc:
        raise DeliverableError(f"canonical JSON schema is unavailable or invalid: {exc}") from exc
    return payload, raw


def verify_bundle(bundle_root: Path) -> dict[str, Any]:
    bundle_root = bundle_root.absolute()
    files = dict(_iter_regular_files(bundle_root))
    manifest_path = _contained_regular_file(bundle_root, MANIFEST_NAME)
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeliverableError(f"manifest is not readable JSON: {exc}") from exc

    schema, canonical_schema_bytes = _canonical_schema()
    bundled_schema = _contained_regular_file(bundle_root, SCHEMA_NAME)
    if bundled_schema.read_bytes() != canonical_schema_bytes:
        raise DeliverableError("bundled JSON schema differs from the canonical verifier schema")
    schema_errors = sorted(Draft202012Validator(schema).iter_errors(payload), key=lambda item: list(item.path))
    if schema_errors:
        detail = "; ".join(f"{'.'.join(map(str, item.path)) or '$'}: {item.message}" for item in schema_errors)
        raise DeliverableError(f"manifest JSON schema validation failed: {detail}")

    assets = payload["assets"]
    checked_paths: set[str] = set()
    for asset in assets:
        relative = asset["path"]
        if relative in checked_paths:
            raise DeliverableError(f"duplicate asset path: {relative}")
        checked_paths.add(relative)
        path = _contained_regular_file(bundle_root, relative)
        if asset["bytes"] != path.stat().st_size:
            raise DeliverableError(f"size mismatch: {relative}")
        if asset["sha256"] != _sha256(path):
            raise DeliverableError(f"hash mismatch: {relative}")

    actual_assets = set(files) - {MANIFEST_NAME}
    if checked_paths != actual_assets:
        missing = sorted(actual_assets - checked_paths)
        extra = sorted(checked_paths - actual_assets)
        raise DeliverableError(f"asset inventory mismatch: unlisted={missing}, nonexistent={extra}")

    secret_failures = _walk_values(payload)
    archive_inspections: dict[str, tuple[str, bytes]] = {}
    archive_budget = {"members": 0, "bytes": 0}
    for relative, path in files.items():
        data = path.read_bytes()
        if path.suffix.lower() in ZIP_ARCHIVE_SUFFIXES or zipfile.is_zipfile(io.BytesIO(data)):
            archive_failures, tree_sha256, comment = _scan_zip_bytes(
                data, relative, budget=archive_budget
            )
            secret_failures.extend(archive_failures)
            archive_inspections[relative] = (tree_sha256, comment)
        else:
            secret_failures.extend(_scan_text(data, relative))

    source = payload["source"]
    source_path = source["archive_path"]
    proof_path = source["object_proof_path"]
    if source["included_paths"] != list(SOURCE_PATHS):
        secret_failures.append("manifest source.included_paths differs from the canonical runtime source set")
    source_assets = [
        asset
        for asset in assets
        if asset["path"] == source_path and asset["kind"] == "runtime-source-zip"
    ]
    if len(source_assets) != 1:
        secret_failures.append("source archive must be exactly one runtime-source-zip asset")
    proof_assets = [
        asset
        for asset in assets
        if asset["path"] == proof_path and asset["kind"] == "git-object-proof"
    ]
    if len(proof_assets) != 1:
        secret_failures.append("source proof must be exactly one git-object-proof asset")
    source_inspection = archive_inspections.get(source_path)
    if source_inspection is None:
        secret_failures.append("source archive is not a readable ZIP archive")
    else:
        source_tree_sha256, source_comment = source_inspection
        try:
            comment_commit = source_comment.decode("ascii")
        except UnicodeDecodeError:
            comment_commit = ""
        if comment_commit != source["git_commit"]:
            secret_failures.append("source Git archive comment does not match manifest source.git_commit")
        if source_tree_sha256 != source["tree_sha256"]:
            secret_failures.append("source Git archive tree identity does not match manifest source.tree_sha256")
    try:
        source_archive_file = _contained_regular_file(bundle_root, source_path)
        proof_file = _contained_regular_file(bundle_root, proof_path)
        if _sha256(proof_file) != source["object_proof_sha256"]:
            secret_failures.append("Git object proof hash does not match manifest source.object_proof_sha256")
        else:
            _verify_git_object_proof(proof_file, source_archive_file, source)
    except DeliverableError as exc:
        secret_failures.append(str(exc))
    if secret_failures:
        raise DeliverableError("; ".join(sorted(set(secret_failures))))
    return payload


def _copy_wheelhouse(source: Path, target: Path) -> list[Path]:
    if source.is_symlink() or not source.is_dir():
        raise DeliverableError(f"wheelhouse must be a real directory: {source}")
    wheels = sorted(source.glob("*.whl"))
    if not wheels:
        raise DeliverableError("wheelhouse contains no wheels")
    target.mkdir(parents=True)
    copied: list[Path] = []
    for wheel in wheels:
        if wheel.is_symlink() or not wheel.is_file():
            raise DeliverableError(f"wheelhouse entry is not a regular file: {wheel}")
        destination = target / wheel.name
        shutil.copy2(wheel, destination)
        copied.append(destination)
    return copied


def _write_replay_archive(bundle_root: Path, archive_path: Path) -> None:
    with archive_path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                for relative, path in sorted(_iter_regular_files(bundle_root)):
                    info = archive.gettarinfo(str(path), arcname=f"runtime-deliverable/{relative}")
                    info.uid = 0
                    info.gid = 0
                    info.uname = "root"
                    info.gname = "root"
                    info.mtime = 0
                    info.mode = 0o755 if relative in {REPLAY_NAME, BOOTSTRAP_NAME, SMOKE_NAME, "tools/jq"} else 0o644
                    with path.open("rb") as stream:
                        archive.addfile(info, stream)


def build_bundle(
    repo_root: Path,
    output_dir: Path,
    *,
    wheelhouse: Path,
    jq_binary: Path,
) -> tuple[Path, Path]:
    package_dir = repo_root / "distribution" / "pipx"
    project_file = package_dir / "pyproject.toml"
    schema_source = repo_root / "distribution" / SCHEMA_NAME
    replay_source = repo_root / "distribution" / "runtime-deliverable-replay.sh"
    bootstrap_source = repo_root / "distribution" / "runtime-deliverable-bootstrap.sh"
    smoke_source = package_dir / "smoke.sh"
    for required in (project_file, schema_source, replay_source, bootstrap_source, smoke_source):
        if not required.is_file():
            raise DeliverableError(f"required distribution source is missing: {required}")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise DeliverableError(f"output directory must be empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir = output_dir / "artifacts"
    tools_dir = output_dir / "tools"
    artifacts_dir.mkdir()
    tools_dir.mkdir()

    metadata = tomllib.loads(project_file.read_text(encoding="utf-8"))["project"]
    commit = _repo_head(repo_root)
    wheel = artifacts_dir / f"{str(metadata['name']).replace('-', '_')}-{metadata['version']}-py3-none-any.whl"
    _build_pure_python_wheel(package_dir, metadata, wheel)
    source_archive = artifacts_dir / f"opensolar-runtime-source-{commit}.zip"
    source_objects = _collect_git_source_objects(repo_root, commit, SOURCE_PATHS)
    _write_git_source_archive_from_objects(commit, source_objects[2], source_archive)
    source_tree_sha256, source_comment = _zip_identity(source_archive, source_archive.name)
    if source_comment.decode("ascii", errors="replace") != commit:
        raise DeliverableError("Git source archive comment does not identify the requested commit")
    object_proof = artifacts_dir / f"opensolar-runtime-git-proof-{commit}.zip"
    _write_git_object_proof(repo_root, commit, source_archive, object_proof, source_objects)

    schema_target = output_dir / SCHEMA_NAME
    replay_target = output_dir / REPLAY_NAME
    bootstrap_target = output_dir / BOOTSTRAP_NAME
    smoke_target = output_dir / SMOKE_NAME
    verify_target = output_dir / VERIFY_NAME
    shutil.copy2(schema_source, schema_target)
    shutil.copy2(replay_source, replay_target)
    shutil.copy2(bootstrap_source, bootstrap_target)
    shutil.copy2(smoke_source, smoke_target)
    shutil.copy2(Path(__file__).resolve(), verify_target)
    jq_target = tools_dir / "jq"
    if jq_binary.is_symlink() or not jq_binary.is_file():
        raise DeliverableError(f"jq input must be a regular file: {jq_binary}")
    shutil.copy2(jq_binary, jq_target)
    jq_target.chmod(0o755)
    copied_wheels = _copy_wheelhouse(wheelhouse, output_dir / "wheelhouse")

    kind_by_path: dict[str, str] = {
        wheel.relative_to(output_dir).as_posix(): "python-wheel",
        source_archive.relative_to(output_dir).as_posix(): "runtime-source-zip",
        object_proof.relative_to(output_dir).as_posix(): "git-object-proof",
        SCHEMA_NAME: "json-schema",
        REPLAY_NAME: "replay-entrypoint",
        BOOTSTRAP_NAME: "offline-installer-bootstrap",
        SMOKE_NAME: "lifecycle-smoke",
        VERIFY_NAME: "bundle-verifier",
        "tools/jq": "linux-x86_64-tool",
    }
    for dependency in copied_wheels:
        kind_by_path[dependency.relative_to(output_dir).as_posix()] = "offline-python-dependency"
    asset_paths = sorted(
        (relative, path)
        for relative, path in _iter_regular_files(output_dir)
        if relative != MANIFEST_NAME
    )
    assets = [_asset_entry(path, output_dir, kind_by_path.get(relative, "runtime-asset")) for relative, path in asset_paths]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "schema_path": SCHEMA_NAME,
        "product": {
            "name": metadata["name"],
            "version": metadata["version"],
            "entrypoint": "openjiuwen-solar",
        },
        "target": {
            "kind": "python-wheel-runtime-bundle",
            "operating_system": "linux",
            "architecture": "x86_64",
            "python": "CPython 3.12",
            "python_requires": metadata["requires-python"],
        },
        "source": {
            "git_commit": commit,
            "archive_path": source_archive.relative_to(output_dir).as_posix(),
            "archive_format": "git-archive-zip",
            "tree_sha256": source_tree_sha256,
            "object_proof_path": object_proof.relative_to(output_dir).as_posix(),
            "object_proof_sha256": _sha256(object_proof),
            "included_paths": list(SOURCE_PATHS),
        },
        "assets": assets,
        "configuration": {
            "embedded_credentials": False,
            "network_required_for_replay": False,
            "external_checkout_required_for_replay": False,
            "environment_injection_required_for_replay": False,
        },
        "replay": {
            "script": REPLAY_NAME,
            "command": "bash replay.sh <new-empty-sandbox>",
            "required_host_tools": ["bash", "git", "python3", "tmux"],
            "required_host_python": "CPython 3.12 with venv",
            "offline_dependency_directory": "wheelhouse",
            "bundled_jq": "tools/jq",
            "smoke_evidence": "<new-empty-sandbox>/product/smoke-evidence.json",
        },
        "lifecycle": {
            "clean_install": [
                "create isolated replay venv",
                "install harness dependencies from bundled wheelhouse with --no-index",
                "install bundled openjiuwen-solar wheel",
                "run bundled installer bootstrap against the bundled source snapshot",
            ],
            "start_health": [
                "openjiuwen-solar status",
                "openjiuwen-solar doctor --json",
                "openjiuwen-solar harness status-server start",
                "GET /healthz returns HTTP 200",
                "openjiuwen-solar harness status-server stop",
            ],
            "rollback": [
                "openjiuwen-solar uninstall --yes",
                "python -m pip uninstall -y openjiuwen-solar",
                "verify SOLAR_HOME and wrapper entrypoint are absent",
            ],
        },
        "limitations": [
            "This bundle covers WSL/Linux x86_64 with CPython 3.12 only.",
            "pipx is optional; when unavailable, replay records it as NOT_TESTED and exercises an isolated venv install.",
            "Container, launchd, workflow, macOS, and native-Windows targets require separate evidence.",
        ],
    }
    manifest_path = output_dir / MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    verify_bundle(output_dir)
    replay_archive = output_dir.parent / f"openjiuwen-solar-runtime-deliverable-{commit}.tar.gz"
    _write_replay_archive(output_dir, replay_archive)
    return manifest_path, replay_archive


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="construct a self-contained Linux runtime deliverable")
    build.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    build.add_argument("--output-dir", type=Path, required=True)
    build.add_argument("--wheelhouse", type=Path, required=True)
    build.add_argument("--jq-binary", type=Path, required=True)
    verify = subparsers.add_parser("verify", help="verify schema, inventory, containment, hashes, and secrets")
    verify.add_argument("--bundle", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "build":
            manifest_path, replay_archive = build_bundle(
                args.repo_root.resolve(),
                args.output_dir.resolve(),
                wheelhouse=args.wheelhouse.resolve(),
                jq_binary=args.jq_binary.resolve(),
            )
            payload = verify_bundle(args.output_dir.resolve())
            result = {
                "status": "built_and_verified",
                "manifest": str(manifest_path),
                "replay_archive": str(replay_archive),
                "replay_archive_sha256": _sha256(replay_archive),
                "assets": len(payload["assets"]),
            }
        else:
            payload = verify_bundle(args.bundle.absolute())
            result = {
                "status": "verified",
                "manifest": str(args.bundle.absolute() / MANIFEST_NAME),
                "assets": len(payload["assets"]),
            }
    except DeliverableError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
