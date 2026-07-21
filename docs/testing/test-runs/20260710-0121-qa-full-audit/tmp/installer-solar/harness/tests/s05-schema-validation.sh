#!/usr/bin/env bash
set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$HARNESS_DIR/tests/s05-schema-results.json}"

python3 - "$HARNESS_DIR" "$OUT" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

harness_dir = Path(sys.argv[1])
out = Path(sys.argv[2])
expected = {
    "tmux_pane",
    "codex_worktree",
    "codex_cloud",
    "antigravity_managed_env",
    "claude_code_session",
    "local_mlx_process",
    "ssh_devbox",
    "docker_sandbox",
}


def check(name, passed, evidence):
    return {"name": name, "status": "passed" if passed else "failed", "evidence": evidence}


schema = json.loads((harness_dir / "config" / "actor-hosts.schema.json").read_text(encoding="utf-8"))
registry = json.loads((harness_dir / "config" / "actor-hosts.json").read_text(encoding="utf-8"))
hosts = registry.get("hosts", {})
enum = set(
    schema.get("$defs", {})
    .get("actor_host", {})
    .get("properties", {})
    .get("host_type", {})
    .get("enum", [])
)
host_types = {cfg.get("host_type") for cfg in hosts.values() if isinstance(cfg, dict)}
mini = hosts.get("mini", {})

checks = [
    check("schema_has_eight_host_types", enum == expected, {"enum": sorted(enum), "expected": sorted(expected)}),
    check("registry_has_at_least_eight_hosts", len(hosts) >= 8, {"host_count": len(hosts)}),
    check("registry_covers_all_host_types", expected <= host_types, {"host_types": sorted(host_types)}),
    check("registry_types_are_in_schema_enum", host_types <= enum, {"extra": sorted(host_types - enum)}),
    check("mini_maps_to_standard_host_type", mini.get("host_type") in expected, {"mini_host_type": mini.get("host_type")}),
]

payload = {
    "schema": "solar.s05.schema_results.v1",
    "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "checks": checks,
    "summary": {
        "total": len(checks),
        "passed": sum(1 for item in checks if item["status"] == "passed"),
        "failed": sum(1 for item in checks if item["status"] == "failed"),
    },
}
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(payload["summary"], ensure_ascii=False))
sys.exit(0 if payload["summary"]["failed"] == 0 else 1)
PY
