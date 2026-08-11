#!/usr/bin/env python3
"""Build and verify the supported OpenSolar Python runtime deliverable.

This constructor deliberately covers the pipx/Python-wheel distribution target.
Container, launchd, and workflow bundles remain separate platform-specific assets.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "opensolar.runtime-deliverable/v1"
MANIFEST_NAME = "runtime-deliverable-manifest.json"
SCHEMA_NAME = "runtime-deliverable.schema.json"
SECRET_VALUE_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\b(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{12,}\b", re.IGNORECASE),
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


class DeliverableError(RuntimeError):
    """Raised when a runtime deliverable cannot be built or verified."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _asset_entry(path: Path, bundle_root: Path, kind: str) -> dict[str, Any]:
    return {
        "path": path.relative_to(bundle_root).as_posix(),
        "kind": kind,
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _record_hash(data: bytes) -> str:
    encoded = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode("ascii").rstrip("=")
    return f"sha256={encoded}"


def _wheel_info(name: str, data: bytes) -> zipfile.ZipInfo:
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
            archive.writestr(_wheel_info(name, data), data)


def _walk_values(value: Any, path: str = "$") -> list[str]:
    failures: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}"
            if str(key).lower() in FORBIDDEN_VALUE_KEYS and item not in (None, "", [], {}):
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


def _required(payload: dict[str, Any], key: str, expected_type: type) -> Any:
    value = payload.get(key)
    if not isinstance(value, expected_type):
        raise DeliverableError(f"manifest field {key!r} must be {expected_type.__name__}")
    return value


def verify_bundle(bundle_root: Path) -> dict[str, Any]:
    manifest_path = bundle_root / MANIFEST_NAME
    if not manifest_path.is_file():
        raise DeliverableError(f"missing {MANIFEST_NAME}")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeliverableError(f"manifest is not readable JSON: {exc}") from exc

    if payload.get("schema_version") != SCHEMA_VERSION:
        raise DeliverableError(f"unsupported schema_version: {payload.get('schema_version')!r}")
    _required(payload, "product", dict)
    target = _required(payload, "target", dict)
    if target.get("kind") != "python-wheel":
        raise DeliverableError("this constructor only verifies target.kind=python-wheel")
    assets = _required(payload, "assets", list)
    if not assets:
        raise DeliverableError("manifest assets must not be empty")
    lifecycle = _required(payload, "lifecycle", dict)
    for field in ("clean_install", "start_health", "rollback"):
        commands = lifecycle.get(field)
        if not isinstance(commands, list) or not commands or not all(isinstance(item, str) and item for item in commands):
            raise DeliverableError(f"lifecycle.{field} must contain executable command templates")

    checked_paths: set[str] = set()
    for asset in assets:
        if not isinstance(asset, dict):
            raise DeliverableError("every asset must be an object")
        relative = asset.get("path")
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise DeliverableError(f"unsafe asset path: {relative!r}")
        if relative in checked_paths:
            raise DeliverableError(f"duplicate asset path: {relative}")
        checked_paths.add(relative)
        path = bundle_root / relative
        if not path.is_file():
            raise DeliverableError(f"missing asset: {relative}")
        if asset.get("bytes") != path.stat().st_size:
            raise DeliverableError(f"size mismatch: {relative}")
        if asset.get("sha256") != _sha256(path):
            raise DeliverableError(f"hash mismatch: {relative}")

    secret_failures = _walk_values(payload)
    if secret_failures:
        raise DeliverableError("; ".join(secret_failures))
    return payload


def build_bundle(repo_root: Path, output_dir: Path) -> Path:
    package_dir = repo_root / "distribution" / "pipx"
    project_file = package_dir / "pyproject.toml"
    schema_source = repo_root / "distribution" / SCHEMA_NAME
    if not project_file.is_file() or not schema_source.is_file():
        raise DeliverableError("distribution package metadata or runtime-deliverable schema is missing")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise DeliverableError(f"output directory must be empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir = output_dir / "artifacts"
    artifacts_dir.mkdir()

    metadata = tomllib.loads(project_file.read_text(encoding="utf-8"))["project"]
    wheel = artifacts_dir / f"{str(metadata['name']).replace('-', '_')}-{metadata['version']}-py3-none-any.whl"
    _build_pure_python_wheel(package_dir, metadata, wheel)

    schema_target = output_dir / SCHEMA_NAME
    shutil.copy2(schema_source, schema_target)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "product": {
            "name": metadata["name"],
            "version": metadata["version"],
            "entrypoint": "openjiuwen-solar",
        },
        "target": {
            "kind": "python-wheel",
            "python_requires": metadata["requires-python"],
            "supported_platforms": ["linux", "macos", "wsl"],
        },
        "source": {
            "git_commit": _repo_head(repo_root),
            "package_path": "distribution/pipx",
        },
        "assets": [
            _asset_entry(wheel, output_dir, "python-wheel"),
            _asset_entry(schema_target, output_dir, "json-schema"),
        ],
        "configuration": {
            "environment_references": [
                "SOLAR_HOME",
                "SOLAR_SRC",
                "SOLAR_REPO",
                "SOLAR_CHANNEL",
                "OPENJIUWEN_SOLAR_GET_SOLAR_URL",
            ],
            "embedded_credentials": False,
        },
        "lifecycle": {
            "clean_install": [
                "python3 -m venv <sandbox>/venv",
                "<sandbox>/venv/bin/python -m pip install artifacts/<wheel>",
                "openjiuwen-solar install --yes --components kernel,harness --fake-keys --skip-llm-cli --skip-py-deps",
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
                "<sandbox>/venv/bin/python -m pip uninstall -y openjiuwen-solar",
                "verify SOLAR_HOME and wrapper entrypoint are absent",
            ],
        },
        "limitations": [
            "This bundle covers the Python wheel/pipx distribution target only.",
            "Container, launchd, workflow, and native-Windows targets require their own platform evidence.",
        ],
    }
    manifest_path = output_dir / MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    verify_bundle(output_dir)
    return manifest_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="construct a Python-wheel runtime deliverable")
    build.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    build.add_argument("--output-dir", type=Path, required=True)
    verify = subparsers.add_parser("verify", help="verify manifest, assets, hashes, lifecycle, and secret policy")
    verify.add_argument("--bundle", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "build":
            manifest_path = build_bundle(args.repo_root.resolve(), args.output_dir.resolve())
            payload = verify_bundle(args.output_dir.resolve())
            result = {"status": "built_and_verified", "manifest": str(manifest_path), "assets": len(payload["assets"])}
        else:
            payload = verify_bundle(args.bundle.resolve())
            result = {"status": "verified", "manifest": str(args.bundle.resolve() / MANIFEST_NAME), "assets": len(payload["assets"])}
    except DeliverableError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
