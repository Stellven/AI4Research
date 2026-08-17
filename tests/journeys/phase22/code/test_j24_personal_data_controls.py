from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import platform
from datetime import datetime, timezone
from pathlib import Path


def _run(tool: Path, home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(tool), "--home", str(home), *args],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )


def _payload(proc: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(proc.stdout if proc.returncode == 0 else proc.stderr)


def test_p22_j24_personal_data_controls(repo_root: Path, tmp_path: Path) -> None:
    tool = repo_root / "harness" / "tools" / "privacy_control.py"
    home = tmp_path / "explicit-solar-home"
    (home / "db").mkdir(parents=True)
    (home / "derived").mkdir()
    (home / "logs").mkdir()
    (home / "config.env").write_text("PROVIDER_TOKEN=J24-SECRET-TOKEN-123456789012345\n", encoding="utf-8")
    (home / "db" / "supplied-profile.json").write_text(
        json.dumps({"name": "Alex Q. Synthetic", "email": "phase22+privacy@example.invalid"}),
        encoding="utf-8",
    )
    old_log = home / "logs" / "old-message.jsonl"
    old_log.write_text("phase22+privacy@example.invalid\n", encoding="utf-8")
    old = time.time() - 5 * 86400
    os.utime(old_log, (old, old))

    commands: list[dict] = []
    assertions: list[dict] = []

    def execute(label: str, *args: str) -> dict:
        started = time.monotonic()
        proc = _run(tool, home, *args)
        payload = _payload(proc)
        commands.append({
            "label": label,
            "argv": [sys.executable, str(tool), "--home", str(home), *args],
            "exit_code": proc.returncode,
            "duration_seconds": round(time.monotonic() - started, 3),
            "stdout_tail": proc.stdout[-1000:],
            "stderr_tail": proc.stderr[-1000:],
        })
        return {"exit_code": proc.returncode, "payload": payload}

    def check(name: str, condition: bool, observed: object) -> None:
        assertions.append({"name": name, "passed": bool(condition), "observed": observed, "required_for_status": True})

    consent = execute("record-consent", "consent-record", "--source", "message", "--purpose", "local memory", "--message-ref", "message-j24-001")
    check("consent_recorded", consent["exit_code"] == 0 and consent["payload"].get("state") == "granted", consent)
    consent_id = consent["payload"].get("consent_id", "")
    derived = home / "derived" / "message-summary.json"
    derived.write_text(json.dumps({"consent_id": consent_id, "summary": "personal summary"}), encoding="utf-8")

    inventory = execute("inventory", "inventory")
    check("inventory_is_local_and_complete", inventory["exit_code"] == 0 and inventory["payload"].get("scope") == "local_only" and inventory["payload"].get("consent_states", {}).get("granted") == 1, inventory)
    check("external_controls_truthfully_excluded", "hosted_account_deletion" in inventory["payload"].get("unsupported_external_controls", []), inventory["payload"])

    export_path = home / "exports" / "personal-data.json"
    exported = execute(
        "export", "export", "--out", str(export_path),
        "--category", "settings", "--category", "supplied_data", "--category", "consent_records",
    )
    export_text = export_path.read_text(encoding="utf-8") if export_path.exists() else ""
    check("export_is_usable_and_redacted", exported["exit_code"] == 0 and len(export_text) > 100 and "phase22+privacy@example.invalid" not in export_text and "J24-SECRET" not in export_text, exported)

    scheduled = execute("retention-set", "retention-set", "--category", "activity_logs", "--days", "1")
    applied = execute("retention-apply", "retention-apply", "--now-epoch", str(time.time()))
    check("retention_removes_only_expired_log", scheduled["exit_code"] == 0 and applied["exit_code"] == 0 and not old_log.exists() and derived.exists(), applied)

    denied = execute("delete-without-confirmation", "delete", "--category", "supplied_data")
    check("selective_delete_fails_closed", denied["exit_code"] == 2 and denied["payload"].get("error") == "confirmation_required" and (home / "db").exists(), denied)

    escaped = execute("export-path-escape", "export", "--out", str(tmp_path / "escaped.json"), "--category", "supplied_data")
    check("path_escape_rejected", escaped["exit_code"] == 2 and not (tmp_path / "escaped.json").exists(), escaped)

    revoked = execute("revoke-consent", "consent-revoke", "--consent-id", consent_id, "--yes")
    check("consent_revocation_removes_derived_data", revoked["exit_code"] == 0 and revoked["payload"].get("state") == "revoked" and not derived.exists(), revoked)

    deleted = execute("selective-delete", "delete", "--category", "supplied_data", "--yes")
    check("supplied_data_deleted_settings_retained", deleted["exit_code"] == 0 and not (home / "db").exists() and (home / "config.env").exists(), deleted)

    ok = all(item["passed"] for item in assertions)
    run_id = f"p22-j24-privacy-controls-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    run_dir = repo_root / "outputs" / "phase22-real-journeys" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    repo_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True, capture_output=True, check=True).stdout.strip()
    result = {
        "schema_version": "phase22.journey-result.v1",
        "journey_id": "P22-J24",
        "task": "Inspect, export, retain, selectively delete, and revoke consent for sandbox-owned local personal data.",
        "production_entrypoint": "harness/tools/privacy_control.py",
        "required_environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "home_scope": "explicit temporary sandbox; no real user home accessed",
            "credentials": "none",
        },
        "minimum_success_conditions": [
            "inventory identifies local personal-data surfaces and explicit external exclusions",
            "export is non-empty, structurally usable, and contains no seeded email or secret",
            "retention and selective deletion remove only the requested local data",
            "consent revocation removes the linked message-derived record",
            "unconfirmed deletion and path escape fail closed",
        ],
        "level_2_features_exercised": [
            "Privacy & Personal Data Controls",
            "Security, Privacy, Compliance & IP Evaluator (local privacy controls only)",
        ],
        "repo_head": repo_head,
        "run_id": run_id,
        "commands": commands,
        "assertions": assertions,
        "result": "PASS_WITH_KNOWN_LIMITATIONS" if ok else "FAIL",
        "known_limitations": [
            "Controls are local-only; hosted accounts and provider/platform revocation remain outside this repository.",
            "No claim is made for Discord, WeChat, regulatory-jurisdiction, copyright, or IP-policy workflows.",
        ],
        "artifacts": {"redacted_export": str(export_path), "control_store": str(home / "primary" / "privacy-control.json")},
    }
    (run_dir / "journey-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    worker = repo_root / ".codex-tmp" / "phase22-worker-results" / "p22-privacy-controls" / "result.json"
    worker.parent.mkdir(parents=True, exist_ok=True)
    worker.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert ok, [item for item in assertions if not item["passed"]]
