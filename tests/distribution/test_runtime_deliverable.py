from __future__ import annotations

import importlib.util
import json
import os
import shutil
import zipfile
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[2] / "distribution" / "runtime_deliverable.py"
SPEC = importlib.util.spec_from_file_location("runtime_deliverable", MODULE_PATH)
assert SPEC and SPEC.loader
runtime_deliverable = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime_deliverable)


def _refresh_assets(bundle: Path, payload: dict[str, object]) -> None:
    kind_by_path = {
        str(item["path"]): str(item["kind"])
        for item in payload["assets"]  # type: ignore[index,union-attr]
    }
    payload["assets"] = [
        runtime_deliverable._asset_entry(path, bundle, kind_by_path.get(relative, "fixture"))
        for relative, path in sorted(runtime_deliverable._iter_regular_files(bundle))
        if relative != runtime_deliverable.MANIFEST_NAME
    ]
    (bundle / runtime_deliverable.MANIFEST_NAME).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _bundle(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    bundle = tmp_path / "bundle"
    artifacts = bundle / "artifacts"
    wheelhouse = bundle / "wheelhouse"
    tools = bundle / "tools"
    artifacts.mkdir(parents=True)
    wheelhouse.mkdir()
    tools.mkdir()
    shutil.copy2(
        MODULE_PATH.with_name(runtime_deliverable.SCHEMA_NAME),
        bundle / runtime_deliverable.SCHEMA_NAME,
    )
    wheel = artifacts / "example.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("example/__init__.py", "VALUE = 1\n")
    source = artifacts / "source.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("install.sh", "#!/usr/bin/env bash\nexit 0\n")
    for relative, content in {
        "replay.sh": "#!/usr/bin/env bash\nexit 0\n",
        "bundled-get-solar.sh": "#!/usr/bin/env bash\nexit 0\n",
        "smoke.sh": "#!/usr/bin/env bash\nexit 0\n",
        "verify.py": "print('verified')\n",
        "tools/jq": "fixture jq binary\n",
    }.items():
        path = bundle / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    with zipfile.ZipFile(wheelhouse / "dependency.whl", "w") as archive:
        archive.writestr("dependency/__init__.py", "VALUE = 1\n")
    payload: dict[str, object] = {
        "schema_version": runtime_deliverable.SCHEMA_VERSION,
        "schema_path": runtime_deliverable.SCHEMA_NAME,
        "product": {"name": "example", "version": "1", "entrypoint": "example"},
        "target": {
            "kind": "python-wheel-runtime-bundle",
            "operating_system": "linux",
            "architecture": "x86_64",
            "python": "CPython 3.12",
            "python_requires": ">=3.11",
        },
        "source": {
            "git_commit": "a" * 40,
            "archive_path": "artifacts/source.zip",
            "archive_format": "git-archive-zip",
            "included_paths": ["install.sh"],
        },
        "assets": [],
        "configuration": {
            "embedded_credentials": False,
            "network_required_for_replay": False,
            "external_checkout_required_for_replay": False,
            "environment_injection_required_for_replay": False,
        },
        "replay": {
            "script": "replay.sh",
            "command": "bash replay.sh <new-empty-sandbox>",
            "required_host_tools": ["bash", "python3", "tmux"],
            "required_host_python": "CPython 3.12 with venv",
            "offline_dependency_directory": "wheelhouse",
            "bundled_jq": "tools/jq",
            "smoke_evidence": "<new-empty-sandbox>/product/smoke-evidence.json",
        },
        "lifecycle": {
            "clean_install": ["install"],
            "start_health": ["health"],
            "rollback": ["uninstall"],
        },
        "limitations": ["fixture"],
    }
    _refresh_assets(bundle, payload)
    return bundle, payload


def test_verify_bundle_accepts_schema_valid_complete_inventory(tmp_path: Path) -> None:
    bundle, _ = _bundle(tmp_path)
    payload = runtime_deliverable.verify_bundle(bundle)
    assert payload["target"]["kind"] == "python-wheel-runtime-bundle"
    assert len(payload["assets"]) >= 8


def test_verify_bundle_rejects_schema_missing_required_field(tmp_path: Path) -> None:
    bundle, payload = _bundle(tmp_path)
    del payload["replay"]
    (bundle / runtime_deliverable.MANIFEST_NAME).write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(runtime_deliverable.DeliverableError, match="JSON schema validation failed.*replay"):
        runtime_deliverable.verify_bundle(bundle)


def test_verify_bundle_rejects_tampered_asset(tmp_path: Path) -> None:
    bundle, _ = _bundle(tmp_path)
    (bundle / "tools" / "jq").write_bytes(b"tampered")
    with pytest.raises(runtime_deliverable.DeliverableError, match="mismatch"):
        runtime_deliverable.verify_bundle(bundle)


def test_verify_bundle_rejects_secret_in_non_manifest_regular_file(tmp_path: Path) -> None:
    bundle, payload = _bundle(tmp_path)
    (bundle / "tools" / "jq").write_text("Bearer abcdefghijklmnopqrstuvwxyz\n", encoding="utf-8")
    _refresh_assets(bundle, payload)
    with pytest.raises(runtime_deliverable.DeliverableError, match="secret-like content in tools/jq"):
        runtime_deliverable.verify_bundle(bundle)


def test_verify_bundle_rejects_secret_hidden_inside_wheel(tmp_path: Path) -> None:
    bundle, payload = _bundle(tmp_path)
    wheel = bundle / "artifacts" / "example.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("example/config.py", "TOKEN = 'sk-not-a-real-value-123456789'\n")
    _refresh_assets(bundle, payload)
    with pytest.raises(runtime_deliverable.DeliverableError, match="example.whl!example/config.py"):
        runtime_deliverable.verify_bundle(bundle)


def test_verify_bundle_rejects_unlisted_regular_file(tmp_path: Path) -> None:
    bundle, _ = _bundle(tmp_path)
    (bundle / "unlisted.txt").write_text("unlisted", encoding="utf-8")
    with pytest.raises(runtime_deliverable.DeliverableError, match="asset inventory mismatch"):
        runtime_deliverable.verify_bundle(bundle)


def test_verify_bundle_rejects_symlink_asset_and_escape(tmp_path: Path) -> None:
    bundle, payload = _bundle(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    link = bundle / "escape.txt"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    payload["assets"].append(  # type: ignore[union-attr]
        {"path": "escape.txt", "kind": "fixture", "bytes": 7, "sha256": "0" * 64}
    )
    (bundle / runtime_deliverable.MANIFEST_NAME).write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(runtime_deliverable.DeliverableError, match="symlink"):
        runtime_deliverable.verify_bundle(bundle)


def test_verify_bundle_rejects_symlink_bundle_root(tmp_path: Path) -> None:
    bundle, _ = _bundle(tmp_path)
    link = tmp_path / "bundle-link"
    try:
        os.symlink(bundle, link, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    with pytest.raises(runtime_deliverable.DeliverableError, match="bundle root.*symlink"):
        runtime_deliverable.verify_bundle(link)
