#!/usr/bin/env bash
set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$HARNESS_DIR/tests/s05-e2e-results.json}"

python3 - "$HARNESS_DIR" "$OUT" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

harness_dir = Path(sys.argv[1])
out = Path(sys.argv[2])
sys.path.insert(0, str(harness_dir / "lib"))

import multi_task_status  # type: ignore

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


actors = multi_task_status.load_actor_fleet(
    harness_dir / "config" / "agent-actors.json",
    harness_dir / "config" / "actor-hosts.json",
    lease_dir=harness_dir / "run" / "actor-leases",
)
hosts = multi_task_status.load_host_fleet(harness_dir / "config" / "actor-hosts.json")
logical = json.loads((harness_dir / "config" / "logical-operators.json").read_text(encoding="utf-8"))
logical_text = json.dumps(logical, ensure_ascii=False)

required_actor_fields = {"actor_id", "host_id", "host_type", "lease_state"}
actor_missing = {
    actor_id: sorted(required_actor_fields - set(entry))
    for actor_id, entry in actors.items()
    if required_actor_fields - set(entry)
}
host_types = {entry.get("host_type") for entry in hosts.values()}

checks = [
    check("actor_status_has_actorhost_fields", bool(actors) and not actor_missing, {
        "actor_count": len(actors),
        "missing": actor_missing,
        "sample": next(iter(actors.values()), {}),
    }),
    check("host_status_covers_eight_host_types", expected <= host_types, {
        "host_types": sorted(host_types),
    }),
    check("logical_operators_no_tmux_pane_index", "tmux_pane_index" not in logical_text, {
        "tmux_pane_index_count": logical_text.count("tmux_pane_index"),
    }),
    check("logical_operators_no_raw_tmux_pane_scheduler_key", "tmux_pane" not in logical_text, {
        "tmux_pane_count": logical_text.count("tmux_pane"),
    }),
]

payload = {
    "schema": "solar.s05.e2e_runtime_results.v1",
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
