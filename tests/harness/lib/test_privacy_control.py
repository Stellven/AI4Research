from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from privacy.control import (
    PrivacyControlError,
    apply_retention,
    delete_category,
    explicit_home,
    export_data,
    inventory,
    record_consent,
    revoke_consent,
    set_retention,
)


def _seed(root: Path) -> None:
    (root / "db").mkdir(parents=True)
    (root / "derived").mkdir()
    (root / "logs").mkdir()
    (root / "config.env").write_text("API_TOKEN=super-secret-value-1234567890\n", encoding="utf-8")
    (root / "db" / "profile.json").write_text(
        json.dumps({"email": "alex@example.com", "secret": "never-export-me"}), encoding="utf-8"
    )


def test_inventory_export_retention_delete_and_consent_revoke(tmp_path: Path) -> None:
    root = explicit_home(tmp_path / "solar-home")
    _seed(root)
    consent = record_consent(root, "message", "local memory", "message-42")
    consent_id = consent["consent_id"]
    derived = root / "derived" / "message-summary.json"
    derived.write_text(json.dumps({"consent_id": consent_id, "summary": "alex@example.com"}), encoding="utf-8")
    old_log = root / "logs" / "old.jsonl"
    old_log.write_text("alex@example.com token ABCDEFGHIJKLMNOPQRSTUVWXYZ\n", encoding="utf-8")
    old = time.time() - 3 * 86400
    os.utime(old_log, (old, old))

    view = inventory(root)
    assert view["scope"] == "local_only"
    assert view["consent_states"] == {"granted": 1, "revoked": 0}
    assert "provider_account_revocation" in view["unsupported_external_controls"]

    exported = export_data(root, root / "exports" / "personal.json", ["settings", "supplied_data"])
    text = Path(exported["out"]).read_text(encoding="utf-8")
    assert "alex@example.com" not in text
    assert "never-export-me" not in text
    assert "super-secret-value" not in text
    assert "[REDACTED]" in text

    set_retention(root, "activity_logs", 1)
    applied = apply_retention(root, now=time.time())
    assert applied["removed"] == ["logs/old.jsonl"]

    revoked = revoke_consent(root, consent_id, confirmed=True)
    assert revoked["state"] == "revoked"
    assert revoked["external_revocation"] == "not_available"
    assert not derived.exists()

    deleted = delete_category(root, "supplied_data", confirmed=True)
    assert deleted["state"] == "deleted"
    assert not (root / "db").exists()
    assert (root / "config.env").exists()


def test_controls_fail_closed_for_confirmation_and_path_escape(tmp_path: Path) -> None:
    root = explicit_home(tmp_path / "solar-home")
    _seed(root)
    try:
        delete_category(root, "supplied_data", confirmed=False)
    except PrivacyControlError as exc:
        assert exc.code == "confirmation_required"
    else:
        raise AssertionError("delete without confirmation was accepted")
    assert (root / "db" / "profile.json").exists()

    try:
        export_data(root, tmp_path / "escaped.json", ["supplied_data"])
    except (PrivacyControlError, ValueError):
        pass
    else:
        raise AssertionError("export outside explicit home was accepted")

    external = tmp_path / "external"
    external.mkdir()
    linked = root / "derived"
    linked.rmdir()
    try:
        linked.symlink_to(external, target_is_directory=True)
    except OSError:
        return  # Windows environments may disallow symlink creation.
    try:
        inventory(root)
    except PrivacyControlError as exc:
        assert exc.code == "unsafe_symlink"
    else:
        raise AssertionError("linked data surface was accepted")


def test_cli_requires_absolute_home_and_emits_structured_errors(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    tool = repo_root / "harness" / "tools" / "privacy_control.py"
    bad = subprocess.run(
        [sys.executable, str(tool), "--home", "relative", "inventory"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert bad.returncode == 2
    assert json.loads(bad.stderr)["error"] == "absolute_home_required"

    root = tmp_path / "home"
    root.mkdir()
    denied = subprocess.run(
        [sys.executable, str(tool), "--home", str(root), "delete", "--category", "settings"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert denied.returncode == 2
    assert json.loads(denied.stderr)["error"] == "confirmation_required"
