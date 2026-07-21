#!/usr/bin/env bash
# scripts/tech-hotspot-radar/lib/hard-gates.sh - License/IP/security gates before strategy decision
#
# Acceptance (P0-N5):
#   - License gate classifies SPDX IDs into allowed/restricted/forbidden (delegated to license-policy.sh)
#   - GPL/AGPL flagged but NOT auto-blocked unless RADAR_BLOCK_COPYLEFT=1 (configurable)
#
# Configurable env:
#   RADAR_BLOCK_COPYLEFT    1/true/yes/on  → block when license_gate.copy_left_flag is True
#   RADAR_BLOCK_RESTRICTED  1/true/yes/on  → block when license_gate.classification == 'restricted'

set -euo pipefail

DB_PATH=""
REPO=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --db) DB_PATH="$2"; shift 2 ;;
        --repo) REPO="$2"; shift 2 ;;
        *) echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
done

if [[ -z "$DB_PATH" || -z "$REPO" ]]; then
    echo "Usage: hard-gates.sh --db <path> --repo <owner/name>" >&2
    exit 1
fi

LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Pull the repo's reported SPDX license string.
LICENSE_RAW="$(python3 - <<'PY' "$DB_PATH" "$REPO"
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
row = conn.execute("SELECT license FROM github_repos WHERE full_name=?", (sys.argv[2],)).fetchone()
print((row[0] if row else "") or "")
conn.close()
PY
)"

# Classify via license-policy.sh.
LICENSE_JSON="$(bash "$LIB_DIR/license-policy.sh" "$LICENSE_RAW")"

python3 - <<'PY' "$DB_PATH" "$REPO" "$LICENSE_JSON"
import json, os, sqlite3, sys

def _truthy(v: str) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "on")

db_path, repo, license_json = sys.argv[1], sys.argv[2], sys.argv[3]
license_gate = json.loads(license_json)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
row = conn.execute(
    "SELECT description, readme_text, archived, license FROM github_repos WHERE full_name=?",
    (repo,),
).fetchone()
if not row:
    print(json.dumps({"ok": False, "repo": repo, "error": "repo not found in github_repos"}, ensure_ascii=False))
    sys.exit(1)

text = " ".join([(row["description"] or ""), (row["readme_text"] or "")]).lower()
security_terms = ("vulnerability", "exploit", "malware", "ransomware", "cve-", "red team")
ip_terms = ("all rights reserved", "proprietary", "commercial license", "source available only")
security_flag = any(term in text for term in security_terms)
ip_flag = any(term in text for term in ip_terms)
archived_flag = bool(int(row["archived"] or 0))

block_copyleft_enabled = _truthy(os.environ.get("RADAR_BLOCK_COPYLEFT", ""))
block_restricted_enabled = _truthy(os.environ.get("RADAR_BLOCK_RESTRICTED", ""))

classification = (license_gate.get("classification") or "").lower()
copy_left_flag = bool(license_gate.get("copy_left_flag"))
auto_block_default = bool(license_gate.get("auto_block_default"))

reasons = []
blocked = False
if auto_block_default:
    blocked = True
    reasons.append(f"license {license_gate.get('license_id')} on forbid-list (auto_block_default)")
if security_flag:
    blocked = True
    reasons.append("security-sensitive wording detected (exploit/malware/cve/...)")
if block_copyleft_enabled and copy_left_flag:
    blocked = True
    reasons.append(f"copyleft license {license_gate.get('license_id')} blocked by RADAR_BLOCK_COPYLEFT=1")
if block_restricted_enabled and classification == "restricted":
    blocked = True
    reasons.append(f"restricted license {license_gate.get('license_id')} blocked by RADAR_BLOCK_RESTRICTED=1")

notes = [
    note for note, enabled in [
        (f"copy-left license {license_gate.get('license_id')} flagged (configurable, default not blocking)", copy_left_flag and not block_copyleft_enabled),
        ("IP-sensitive wording detected (commercial/proprietary/source-available)", ip_flag),
        ("security-sensitive wording detected", security_flag),
        ("repository is archived; bias toward monitor_only or research_deep_dive", archived_flag),
        (f"restricted license {license_gate.get('license_id')} requires human review", classification == "restricted" and not block_restricted_enabled),
    ] if enabled
]

payload = {
    "ok": True,
    "repo": repo,
    "license_gate": license_gate,
    "ip_flag": ip_flag,
    "security_flag": security_flag,
    "archived_flag": archived_flag,
    "blocked": blocked,
    "block_reasons": reasons,
    "config": {
        "RADAR_BLOCK_COPYLEFT": block_copyleft_enabled,
        "RADAR_BLOCK_RESTRICTED": block_restricted_enabled,
    },
    "notes": notes,
}
print(json.dumps(payload, ensure_ascii=False))
conn.close()
PY
