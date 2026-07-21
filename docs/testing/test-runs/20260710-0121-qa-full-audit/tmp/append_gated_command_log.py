from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "command-log.tsv"
CHECKOUT = ROOT / "tmp" / "codex-not-run-checkout"
EVIDENCE = ROOT / "evidence" / "codex-not-run-phase" / "gated-approved"


def stamp(path: Path, duration: float) -> tuple[str, str]:
    end = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).astimezone()
    start = end - timedelta(seconds=duration)
    return start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")


records = [
    {
        "command_id": "phase8_gated_autosci_approved_paths",
        "phase": "codex-not-run-gated-approved",
        "linked_feature_ids": "WF-0204;WF-0225;WF-0226;WF-0227;WF-0239;WF-0247;WF-0266",
        "cwd": str(CHECKOUT),
        "command": "isolated pytest selection: approved AutoSci edit/raw add/raw delete/reset/pilot/claim/survey routes",
        "duration_seconds": "3.322",
        "exit_code": "0",
        "stdout_path": "evidence/codex-not-run-phase/gated-approved/autosci-approved-gates.stdout.txt",
        "stderr_path": "evidence/codex-not-run-phase/gated-approved/autosci-approved-gates.stderr.txt",
        "time_source": EVIDENCE / "autosci-approved-gates.junit.xml",
    },
    {
        "command_id": "phase8_gated_plan_verdict",
        "phase": "codex-not-run-gated-approved",
        "linked_feature_ids": "WF-0013-PLAN-VERDICT-UPDATES-SPRINT-6F9A1D",
        "cwd": str(CHECKOUT),
        "command": "isolated HOME/SOLAR_HOME/CLAUDE_DIR HARNESS_DIR=<locked checkout>/harness bash harness/test-control-plane.sh",
        "duration_seconds": "0.603",
        "exit_code": "0",
        "stdout_path": "evidence/codex-not-run-phase/gated-approved/control-plane-approved-plan-verdict.txt",
        "stderr_path": "evidence/codex-not-run-phase/gated-approved/control-plane-approved-plan-verdict.txt",
        "time_source": EVIDENCE / "control-plane-approved-plan-verdict.txt",
    },
    {
        "command_id": "phase8_gated_obsidian_safety",
        "phase": "codex-not-run-gated-approved",
        "linked_feature_ids": "WF-0033-MUTATION-SYNC-EXPLICIT-PRESERVES-ACE99F;MISC-0328-ANY-EXTERNAL-WRITE-BROWSER-A76165",
        "cwd": str(CHECKOUT),
        "command": "isolated HARNESS_TEST=1 OBSIDIAN_WIKI_OFFLINE=1 bash harness/test-obsidian-wiki-integration.sh safety",
        "duration_seconds": "0.004",
        "exit_code": "0",
        "stdout_path": "evidence/codex-not-run-phase/gated-approved/obsidian-wiki-safety.txt",
        "stderr_path": "evidence/codex-not-run-phase/gated-approved/obsidian-wiki-safety.txt",
        "time_source": EVIDENCE / "obsidian-wiki-safety.txt",
    },
    {
        "command_id": "phase8_gated_atomic_audit_contracts",
        "phase": "codex-not-run-gated-approved",
        "linked_feature_ids": "WF-0006-CLEAN-START-RESETS-STALE-840E0D;WF-0228-NEW-RAW-SOURCE-ADDITION-46F58A;WF-0247-ARCHIVAL-WRITEBACK-EXPLICIT-APPROVED-0CA46A",
        "cwd": str(ROOT),
        "command": "isolated pytest evidence/codex-not-run-phase/audit-tests/test_approved_gated_atomic_contracts.py",
        "duration_seconds": "0.954",
        "exit_code": "1",
        "stdout_path": "evidence/codex-not-run-phase/gated-approved/approved-gated-atomic-contracts.stdout.txt",
        "stderr_path": "evidence/codex-not-run-phase/gated-approved/approved-gated-atomic-contracts.stderr.txt",
        "time_source": EVIDENCE / "approved-gated-atomic-contracts.junit.xml",
    },
    {
        "command_id": "phase8_misc_side_effect_gate_contracts",
        "phase": "codex-not-run-gated-approved",
        "linked_feature_ids": "MISC-0308-ANY-EXTERNAL-WRITE-BROWSER-F66FD9;MISC-0313-ANY-EXTERNAL-WRITE-BROWSER-AEAD47;MISC-0318-ANY-EXTERNAL-WRITE-BROWSER-DD521D;MISC-0338-ANY-EXTERNAL-WRITE-BROWSER-4CE79F;MISC-0348-ANY-EXTERNAL-WRITE-BROWSER-417B43",
        "cwd": str(ROOT),
        "command": "isolated pytest evidence/codex-not-run-phase/audit-tests/test_misc_side_effect_gate_contracts.py",
        "duration_seconds": "0.179",
        "exit_code": "1",
        "stdout_path": "evidence/codex-not-run-phase/gated-approved/misc-side-effect-gate-contracts.stdout.txt",
        "stderr_path": "evidence/codex-not-run-phase/gated-approved/misc-side-effect-gate-contracts.stderr.txt",
        "time_source": EVIDENCE / "misc-side-effect-gate-contracts.junit.xml",
    },
    {
        "command_id": "phase8_browser_existing_policy_control",
        "phase": "codex-not-run-gated-approved",
        "linked_feature_ids": "MISC-0348-ANY-EXTERNAL-WRITE-BROWSER-417B43",
        "cwd": str(CHECKOUT),
        "command": "isolated pytest harness/tests/test_ai_influence_youtube_report_automation_policy.py",
        "duration_seconds": "0.112",
        "exit_code": "0",
        "stdout_path": "evidence/codex-not-run-phase/gated-approved/browser-existing-policy.stdout.txt",
        "stderr_path": "evidence/codex-not-run-phase/gated-approved/browser-existing-policy.stderr.txt",
        "time_source": EVIDENCE / "browser-existing-policy.junit.xml",
    },
    {
        "command_id": "phase8_manual_oracle_atomic_contracts",
        "phase": "codex-not-run-manual-oracle-remediation",
        "linked_feature_ids": "WF-0117;WF-0134;WF-0147;WF-0158;WF-0159;WF-0172;WF-0176;WF-0177;WF-0191;WF-0203;WF-0243;WF-0250;WF-0287",
        "cwd": str(ROOT),
        "command": "isolated pytest evidence/codex-not-run-phase/audit-tests/test_manual_oracle_atomic_contracts.py",
        "duration_seconds": "7.494",
        "exit_code": "1",
        "stdout_path": "evidence/codex-not-run-phase/gated-approved/manual-oracle-atomic-contracts.stdout.txt",
        "stderr_path": "evidence/codex-not-run-phase/gated-approved/manual-oracle-atomic-contracts.stderr.txt",
        "time_source": EVIDENCE / "manual-oracle-atomic-contracts.junit.xml",
    },
    {
        "command_id": "phase8_remaining_app_browser_provider_contracts",
        "phase": "codex-not-run-gated-approved",
        "linked_feature_ids": "WF-0422;WF-0423;WF-0425;WF-0426;MISC-0300;MISC-0302;MISC-0305;MISC-0307;MISC-0310;MISC-0312;MISC-0315;MISC-0317;MISC-0322;MISC-0327;MISC-0330;MISC-0332;MISC-0335;MISC-0337;MISC-0347;MISC-0375",
        "cwd": str(ROOT),
        "command": "isolated pytest evidence/codex-not-run-phase/audit-tests/test_remaining_app_browser_provider_contracts.py",
        "duration_seconds": "2.196",
        "exit_code": "1",
        "stdout_path": "evidence/codex-not-run-phase/gated-approved/remaining-app-browser-provider-contracts.stdout.txt",
        "stderr_path": "evidence/codex-not-run-phase/gated-approved/remaining-app-browser-provider-contracts.stderr.txt",
        "time_source": EVIDENCE / "remaining-app-browser-provider-contracts.junit.xml",
    },
]


with LOG.open(encoding="utf-8", newline="") as handle:
    rows = list(csv.DictReader(handle, delimiter="\t"))
fieldnames = list(rows[0])
by_id = {row["command_id"]: row for row in rows}
for record in records:
    start, end = stamp(record.pop("time_source"), float(record["duration_seconds"]))
    record["start_time"] = start
    record["end_time"] = end
    by_id[record["command_id"]] = {name: record.get(name, "") for name in fieldnames}
with LOG.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
    writer.writeheader()
    writer.writerows(by_id.values())
print(f"command_log_rows={len(by_id)} added_or_updated={len(records)}")
