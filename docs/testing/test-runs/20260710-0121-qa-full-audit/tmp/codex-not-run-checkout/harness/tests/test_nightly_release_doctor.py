from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "lib/nightly_release_doctor.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("nightly_release_doctor_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_nightly_release_doctor_preflight_without_external_services(monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod.shutil, "which", lambda name: None)

    payload = mod.run_doctor(ROOT, tvs_root="", include_external=False)

    assert payload["ok"] is True
    assert payload["full_ready"] is False
    names = {item["name"]: item for item in payload["checks"]}
    assert names["release/build.sh syntax"]["status"] == "ok"
    assert names["release dry-run"]["status"] == "ok"
    assert names["plugin manifest schema"]["status"] == "ok"
    assert names["bun"]["status"] == "error"
    assert names["SOLAR_TVS_ROOT"]["status"] == "error"


def test_nightly_release_doctor_markdown_contains_full_readiness(monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod.shutil, "which", lambda name: "/tmp/bun" if name == "bun" else None)
    payload = mod.run_doctor(ROOT, tvs_root="/does/not/exist", include_external=False)

    markdown = mod.render_markdown(payload)

    assert "Solar nightly release doctor" in markdown
    assert "Full gate ready" in markdown
    assert "SOLAR_TVS_ROOT" in markdown


def test_nightly_release_doctor_blocks_lightweight_release_errors(monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        mod,
        "_check_release_dry_run",
        lambda harness_dir: mod.Check("release dry-run", "error", "boom"),
    )

    payload = mod.run_doctor(ROOT, tvs_root="", include_external=False)

    assert payload["ok"] is False
    names = {item["name"]: item for item in payload["checks"]}
    assert names["release dry-run"]["required_for_full"] is False


def test_mirage_drive_probe_uses_doctor_not_root_listing(monkeypatch):
    mod = _load_module()
    calls = []

    def fake_run(cmd, *, cwd, timeout=30, env=None):
        calls.append(cmd)
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout='{"drive":{"status":"ok","local_root":"/tmp/drive"}}',
            stderr="",
        )

    monkeypatch.setattr(mod, "_run", fake_run)

    check = mod._check_mirage_drive(ROOT)

    assert check.status == "ok"
    assert check.detail == "/tmp/drive"
    assert calls == [["bash", "solar-harness.sh", "mirage", "doctor", "--json"]]


def test_mirage_drive_probe_handles_warning_prefixed_json(monkeypatch):
    mod = _load_module()

    def fake_run(cmd, *, cwd, timeout=30, env=None):
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout='warning before json\n{"drive":{"status":"degraded","reason":"missing"}}',
            stderr="",
        )

    monkeypatch.setattr(mod, "_run", fake_run)

    check = mod._check_mirage_drive(ROOT)

    assert check.status == "error"
    assert "missing" in check.detail


def test_json_from_output_ignores_trailing_warnings():
    mod = _load_module()

    payload = mod._json_from_output('prefix\n{"drive":{"status":"ok"}}\nwarning after json')

    assert payload["drive"]["status"] == "ok"
