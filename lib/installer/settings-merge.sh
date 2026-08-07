#!/usr/bin/env bash

# settings-merge.sh — merge each selected component's hooks.json into the
# user's ~/.claude/settings.json. Merges with python3 (never sed) and keys
# Solar entries by the "/solar/hooks/" command path segment so add/remove is
# idempotent and never touches user-owned entries. A timestamped backup is
# written only when the merge actually changes pre-existing content, so a
# fresh install and an idempotent re-run leave no backup residue.
#
# Component hooks.json format:
#   { "<EventName>": ["<hook-script.sh>", ...], ... }
# Each script becomes a command "<CLAUDE_DIR>/solar/hooks/<script>".

SETTINGS_MARKER="/solar/hooks/"

settings_merge() {
    [ "${NO_HOOKS:-false}" = "true" ] && { info "skipping settings.json hook merge (--no-hooks)"; return 0; }
    settings_file="$CLAUDE_DIR/settings.json"
    set --
    for name in $SELECTED_COMPONENTS; do
        hj="$SOURCE_DIR/components.d/$name/hooks.json"
        [ -f "$hj" ] && set -- "$@" "$hj"
    done
    [ "$#" -eq 0 ] && { info "no component hooks to register"; return 0; }

    dry_run_note "merge $# component hooks.json into $settings_file" && return 0
    mkdir -p "$CLAUDE_DIR"
    SETTINGS_MARKER="$SETTINGS_MARKER" SETTINGS_BACKUP_TS="$(date -u +%Y%m%d%H%M%S)" \
    "${SOLAR_PYTHON:-python3}" - "$settings_file" "$CLAUDE_DIR" "$@" <<'PY'
import json
import os
import sys

settings_file = sys.argv[1]
claude_dir = sys.argv[2]
hooks_files = sys.argv[3:]
marker = os.environ["SETTINGS_MARKER"]
backup_ts = os.environ["SETTINGS_BACKUP_TS"]
hooks_root = os.path.join(claude_dir, "solar", "hooks")

if os.path.isfile(settings_file):
    with open(settings_file, encoding="utf-8") as f:
        old_text = f.read()
else:
    old_text = ""

settings = json.loads(old_text) if old_text.strip() else {}
if not isinstance(settings, dict):
    raise SystemExit(f"settings.json is not a JSON object: {settings_file}")
before = json.dumps(settings, sort_keys=True)

hooks = settings.setdefault("hooks", {})
desired = {}
for hf in hooks_files:
    with open(hf, encoding="utf-8") as f:
        spec = json.load(f)
    for event, scripts in spec.items():
        for script in scripts:
            desired.setdefault(event, []).append(os.path.join(hooks_root, script))

for event, cmds in desired.items():
    groups = hooks.setdefault(event, [])
    existing = set()
    for group in groups:
        if isinstance(group, dict):
            for h in group.get("hooks", []):
                if isinstance(h, dict) and h.get("command"):
                    existing.add(h["command"])
    for cmd in cmds:
        if cmd in existing:
            continue  # idempotent
        groups.append({"hooks": [{"type": "command", "command": cmd}]})
        existing.add(cmd)

after = json.dumps(settings, sort_keys=True)
if after == before:
    print(f"settings.json already current: {settings_file}")
    sys.exit(0)

# Real change: back up prior content (only if it existed and was non-empty).
if old_text.strip():
    backup = f"{settings_file}.backup.{backup_ts}"
    with open(backup, "w", encoding="utf-8") as f:
        f.write(old_text)
    print(f"backed up settings.json -> {os.path.basename(backup)}")

tmp = settings_file + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")
os.replace(tmp, settings_file)
print(f"settings.json merged: {settings_file}")
PY
}
