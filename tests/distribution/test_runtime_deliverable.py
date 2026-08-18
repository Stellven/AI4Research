from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import stat
import subprocess
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
        runtime_deliverable._asset_entry(
            path,
            bundle,
            kind_by_path.get(
                relative,
                {
                    "artifacts/source.zip": "runtime-source-zip",
                    "artifacts/proof.zip": "git-object-proof",
                }.get(relative, "fixture"),
            ),
        )
        for relative, path in sorted(runtime_deliverable._iter_regular_files(bundle))
        if relative != runtime_deliverable.MANIFEST_NAME
    ]
    (bundle / runtime_deliverable.MANIFEST_NAME).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _refresh_source_tree(bundle: Path, payload: dict[str, object]) -> None:
    source = payload["source"]  # type: ignore[index]
    source_path = bundle / str(source["archive_path"])  # type: ignore[index]
    _, tree_sha256, _ = runtime_deliverable._scan_zip_bytes(
        source_path.read_bytes(), str(source["archive_path"])
    )
    source["tree_sha256"] = tree_sha256  # type: ignore[index]


def _source_commit(payload: dict[str, object]) -> bytes:
    source = payload["source"]  # type: ignore[index]
    return str(source["git_commit"]).encode("ascii")  # type: ignore[index]


def _replace_zip_member(archive_path: Path, member_name: str, replacement: bytes) -> None:
    with zipfile.ZipFile(archive_path) as source:
        comment = source.comment
        members = [(info, source.read(info) if not info.is_dir() else b"") for info in source.infolist()]
    rewritten = archive_path.with_suffix(".rewritten.zip")
    with zipfile.ZipFile(rewritten, "w") as target:
        target.comment = comment
        for info, data in members:
            target.writestr(info, replacement if info.filename == member_name else data)
    os.replace(rewritten, archive_path)


def _fixture_git_source(tmp_path: Path, source: Path, proof: Path) -> str:
    repo = tmp_path / "source-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Fixture"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=repo, check=True)
    for included in runtime_deliverable.SOURCE_PATHS:
        path = repo / included
        if included in {"VERSION", "install.sh"}:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture\n", encoding="utf-8")
        else:
            path.mkdir(parents=True, exist_ok=True)
            (path / "fixture.txt").write_text(f"fixture for {included}\n", encoding="utf-8")
    subprocess.run(["git", "add", "--all"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "--quiet", "-m", "fixture"], cwd=repo, check=True)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    runtime_deliverable._git_source_archive(repo, commit, source)
    runtime_deliverable._write_git_object_proof(repo, commit, source, proof)
    return commit


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
    proof = artifacts / "proof.zip"
    commit = _fixture_git_source(tmp_path, source, proof)
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
            "git_commit": commit,
            "archive_path": "artifacts/source.zip",
            "archive_format": "git-archive-zip",
            "tree_sha256": "0" * 64,
            "object_proof_path": "artifacts/proof.zip",
            "object_proof_sha256": runtime_deliverable._sha256(proof),
            "included_paths": list(runtime_deliverable.SOURCE_PATHS),
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
    _refresh_source_tree(bundle, payload)
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


def test_reviewed_placeholder_fingerprint_is_bound_to_repo_path() -> None:
    value = "sk-FAKE-DO-NOT-LEAK-XYZ-987654321"
    source_label = "artifacts/source.zip!harness/docs/benchmark/terminal-bench-2.md"
    proof_label = "artifacts/proof.zip!blobs/" + "a" * 40 + "/harness/docs/benchmark/terminal-bench-2.md"
    assert runtime_deliverable._is_reviewed_placeholder(value, source_label)
    assert runtime_deliverable._is_reviewed_placeholder(value, proof_label)
    assert not runtime_deliverable._is_reviewed_placeholder(value, "artifacts/source.zip!install.sh")


def test_verify_bundle_rejects_secret_hidden_inside_wheel(tmp_path: Path) -> None:
    bundle, payload = _bundle(tmp_path)
    wheel = bundle / "artifacts" / "example.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("example/config.py", "TOKEN = 'sk-not-a-real-value-123456789'\n")
    _refresh_assets(bundle, payload)
    with pytest.raises(runtime_deliverable.DeliverableError, match="example.whl!example/config.py"):
        runtime_deliverable.verify_bundle(bundle)


def test_verify_bundle_rejects_secret_hidden_in_nested_source_archive(tmp_path: Path) -> None:
    bundle, payload = _bundle(tmp_path)
    nested_bytes = io.BytesIO()
    with zipfile.ZipFile(nested_bytes, "w", compression=zipfile.ZIP_DEFLATED) as nested:
        nested.writestr("config/settings.json", '{"api_key":"sk-compressed-secret-123456"}')
    source = bundle / "artifacts" / "source.zip"
    with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.comment = _source_commit(payload)
        archive.writestr("install.sh", "#!/usr/bin/env bash\nexit 0\n")
        archive.writestr("vendor/nested.zip", nested_bytes.getvalue())
    _refresh_source_tree(bundle, payload)
    _refresh_assets(bundle, payload)
    with pytest.raises(runtime_deliverable.DeliverableError, match="source.zip!vendor/nested.zip!config/settings.json"):
        runtime_deliverable.verify_bundle(bundle)


@pytest.mark.parametrize("unsafe_kind", ["zip-slip", "symlink"])
def test_verify_bundle_rejects_unsafe_source_archive_member(
    tmp_path: Path, unsafe_kind: str
) -> None:
    bundle, payload = _bundle(tmp_path)
    source = bundle / "artifacts" / "source.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.comment = _source_commit(payload)
        archive.writestr("install.sh", "#!/usr/bin/env bash\nexit 0\n")
        if unsafe_kind == "zip-slip":
            archive.writestr("../escape.txt", "escape")
        else:
            link = zipfile.ZipInfo("linked-secret")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(link, "../outside")
    _refresh_source_tree(bundle, payload)
    _refresh_assets(bundle, payload)
    with pytest.raises(runtime_deliverable.DeliverableError, match="unsafe archive member|symlink archive member"):
        runtime_deliverable.verify_bundle(bundle)


def test_verify_bundle_rejects_archive_compression_bomb(tmp_path: Path) -> None:
    bundle, payload = _bundle(tmp_path)
    source = bundle / "artifacts" / "source.zip"
    with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.comment = _source_commit(payload)
        archive.writestr("install.sh", "#!/usr/bin/env bash\nexit 0\n")
        archive.writestr("compressed.bin", b"0" * (2 * 1024 * 1024))
    _refresh_source_tree(bundle, payload)
    _refresh_assets(bundle, payload)
    with pytest.raises(runtime_deliverable.DeliverableError, match="compression-ratio limit"):
        runtime_deliverable.verify_bundle(bundle)


def test_verify_bundle_rejects_replaced_source_after_asset_hash_refresh(tmp_path: Path) -> None:
    bundle, payload = _bundle(tmp_path)
    source = bundle / "artifacts" / "source.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.comment = _source_commit(payload)
        archive.writestr("install.sh", "#!/usr/bin/env bash\necho replaced\n")
    _refresh_assets(bundle, payload)
    with pytest.raises(runtime_deliverable.DeliverableError, match="tree identity"):
        runtime_deliverable.verify_bundle(bundle)


def test_verify_bundle_rejects_forged_source_with_all_mutable_hashes_refreshed(
    tmp_path: Path,
) -> None:
    bundle, payload = _bundle(tmp_path)
    source = bundle / "artifacts" / "source.zip"
    _replace_zip_member(source, "install.sh", b"#!/usr/bin/env bash\necho forged\n")
    _refresh_source_tree(bundle, payload)
    _refresh_assets(bundle, payload)
    with pytest.raises(runtime_deliverable.DeliverableError, match="not bound to declared commit"):
        runtime_deliverable.verify_bundle(bundle)


def test_verify_bundle_rejects_source_comment_not_matching_commit(tmp_path: Path) -> None:
    bundle, payload = _bundle(tmp_path)
    source = bundle / "artifacts" / "source.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.comment = ("b" * 40).encode("ascii")
        archive.writestr("install.sh", "#!/usr/bin/env bash\nexit 0\n")
    _refresh_source_tree(bundle, payload)
    _refresh_assets(bundle, payload)
    with pytest.raises(runtime_deliverable.DeliverableError, match="comment does not match"):
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
