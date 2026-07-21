#!/usr/bin/env bash
# scripts/tech-hotspot-radar/lib/license-policy.sh - Normalize SPDX ids and classify policy tier
set -euo pipefail

if [[ "${1:-}" == "--list-classifications" ]]; then
    printf '%s\n' allowed restricted forbidden
    exit 0
fi

python3 - <<'PY' "${1:-}"
import json, sys

raw = (sys.argv[1] or "").strip()
normalized = raw.upper().replace(" ", "")
if not normalized:
    normalized = "UNKNOWN"

allowed = {"MIT", "APACHE-2.0", "BSD-2-CLAUSE", "BSD-3-CLAUSE", "ISC", "UNLICENSE", "CC0-1.0"}
restricted = {"GPL-2.0", "GPL-3.0", "AGPL-3.0", "LGPL-2.1", "LGPL-3.0", "MPL-2.0", "EPL-2.0", "SSPL-1.0"}
forbidden = {"PROPRIETARY", "ALL-RIGHTS-RESERVED", "CUSTOM-NONCOMMERCIAL"}

if normalized in allowed:
    classification = "allowed"
    reason = "spdx allow-list"
elif normalized in restricted:
    classification = "restricted"
    reason = "spdx restrict-list (review before productization)"
elif normalized in forbidden:
    classification = "forbidden"
    reason = "spdx forbid-list (auto-block default)"
elif normalized in {"NOASSERTION", "UNKNOWN", "NONE"}:
    classification = "restricted"
    reason = "license missing or NOASSERTION; treat as restricted"
else:
    classification = "restricted"
    reason = "spdx not on any list; treat as restricted pending review"

copy_left = normalized.startswith(("GPL", "AGPL", "LGPL"))
payload = {
    "license_id": normalized,
    "classification": classification,
    "classification_reason": reason,
    "copy_left_flag": copy_left,
    "auto_block_default": normalized in forbidden,
}
print(json.dumps(payload, ensure_ascii=False))
PY
