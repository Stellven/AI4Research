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
    command = [
        "git",
        "archive",
        "--format=zip",
        f"--output={target}",
        commit,
        "--",
        *SOURCE_PATHS,
    ]
    completed = subprocess.run(
        command,
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0 or not target.is_file():
        detail = (completed.stderr or completed.stdout)[-2000:]
        raise DeliverableError(f"runtime source archive failed ({completed.returncode}): {detail}")


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
            if pattern.search(value):
                failures.append(f"secret-like value at {path}")
                break
    return failures


def _scan_text(data: bytes, label: str) -> list[str]:
    text = data.decode("utf-8", errors="ignore")
    failures: list[str] = []
    for pattern in SECRET_VALUE_PATTERNS:
        if pattern.search(text):
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
    source_assets = [
        asset
        for asset in assets
        if asset["path"] == source_path and asset["kind"] == "runtime-source-zip"
    ]
    if len(source_assets) != 1:
        secret_failures.append("source archive must be exactly one runtime-source-zip asset")
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
    _git_source_archive(repo_root, commit, source_archive)
    source_tree_sha256, source_comment = _zip_identity(source_archive, source_archive.name)
    if source_comment.decode("ascii", errors="replace") != commit:
        raise DeliverableError("Git source archive comment does not identify the requested commit")

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
            "required_host_tools": ["bash", "python3", "tmux"],
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
