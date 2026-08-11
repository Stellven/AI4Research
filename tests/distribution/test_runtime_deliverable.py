from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[2] / "distribution" / "runtime_deliverable.py"
SPEC = importlib.util.spec_from_file_location("runtime_deliverable", MODULE_PATH)
assert SPEC and SPEC.loader
runtime_deliverable = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime_deliverable)


def _bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "bundle"
    artifacts = bundle / "artifacts"
    artifacts.mkdir(parents=True)
    wheel = artifacts / "example.whl"
    wheel.write_bytes(b"real wheel payload")
    schema = bundle / runtime_deliverable.SCHEMA_NAME
    schema.write_text("{}\n", encoding="utf-8")
    payload = {
        "schema_version": runtime_deliverable.SCHEMA_VERSION,
        "product": {"name": "example", "version": "1", "entrypoint": "example"},
        "target": {"kind": "python-wheel"},
        "source": {"git_commit": "a" * 40},
        "assets": [
            runtime_deliverable._asset_entry(wheel, bundle, "python-wheel"),
            runtime_deliverable._asset_entry(schema, bundle, "json-schema"),
        ],
        "configuration": {"embedded_credentials": False},
        "lifecycle": {
            "clean_install": ["python -m pip install example.whl"],
            "start_health": ["example doctor --json"],
            "rollback": ["python -m pip uninstall -y example"],
        },
        "limitations": [],
    }
    (bundle / runtime_deliverable.MANIFEST_NAME).write_text(
        json.dumps(payload), encoding="utf-8"
    )
    return bundle


def test_verify_bundle_accepts_hash_bound_lifecycle_manifest(tmp_path: Path) -> None:
    payload = runtime_deliverable.verify_bundle(_bundle(tmp_path))
    assert payload["target"]["kind"] == "python-wheel"
    assert len(payload["assets"]) == 2


def test_verify_bundle_rejects_tampered_asset(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    (bundle / "artifacts" / "example.whl").write_bytes(b"tampered")
    with pytest.raises(runtime_deliverable.DeliverableError, match="mismatch"):
        runtime_deliverable.verify_bundle(bundle)


def test_verify_bundle_rejects_embedded_credential_value(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    manifest = bundle / runtime_deliverable.MANIFEST_NAME
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["configuration"]["api_key"] = "sk-example-secret-value-12345"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(runtime_deliverable.DeliverableError, match="credential|secret-like"):
        runtime_deliverable.verify_bundle(bundle)
