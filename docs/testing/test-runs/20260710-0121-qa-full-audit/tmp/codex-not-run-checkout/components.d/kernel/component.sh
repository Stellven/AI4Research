#!/usr/bin/env bash

COMPONENT_NAME="kernel"
COMPONENT_DESC="Claude Code kernel overlay with namespaced rules, hooks, and agents"
COMPONENT_DEFAULT="on"
COMPONENT_REQUIRES_BINS="python3"

component_install() {
    dry_run_note "install kernel assets into $CLAUDE_DIR/solar" && return 0
    mkdir -p "$CLAUDE_DIR/solar"

    # Generate the kernel from kernel/ fragments per selected components,
    # excising the unshipped externals (WS2). Replaces the P1 alpha behavior
    # of copying the monolithic CLAUDE.md verbatim.
    kernel_gen

    if [ ! -f "$CLAUDE_DIR/solar/SOLAR.local.md" ]; then
        printf '# Solar Local Notes\n\nUser-owned extension point. The installer does not overwrite this file.\n' > "$CLAUDE_DIR/solar/SOLAR.local.md"
    fi

    # Rules and agents install from allowlists (WS2): only general-discipline
    # rules and the active base @Agent files ship with the base kernel; rules/agents
    # whose purpose is an excised/optional component are parked in the repo and
    # not installed. Hook curation + registration is owned by the settings-merge
    # workstream.
    copy_allowlist "$SOURCE_DIR/rules" "$CLAUDE_DIR/solar/rules" "$SOURCE_DIR/kernel/base-rules.txt"
    copy_allowlist "$SOURCE_DIR/agents" "$CLAUDE_DIR/solar/agents" "$SOURCE_DIR/kernel/base-agents.txt"
    copy_allowlist "$SOURCE_DIR/hooks" "$CLAUDE_DIR/solar/hooks" "$SOURCE_DIR/kernel/base-hooks.txt" ".sh"
    chmod +x "$CLAUDE_DIR/solar/hooks/"*.sh 2>/dev/null || true
    [ -d "$SOURCE_DIR/.claude/prompts" ] && copy_payload "$SOURCE_DIR/.claude/prompts" "$CLAUDE_DIR/solar/prompts"

    python3 - "$CLAUDE_DIR/CLAUDE.md" <<'PY'
import pathlib
import sys
from datetime import datetime

path = pathlib.Path(sys.argv[1])
begin = b"<!-- BEGIN OPENSOLAR -->"
end = b"<!-- END OPENSOLAR -->"
prefix_marker = b"<!-- OPENSOLAR-PREFIX: "


def block(prefix_mode):
    return (
        begin
        + b"\n"
        + prefix_marker
        + prefix_mode
        + b" -->\n"
        + b"@~/.claude/solar/SOLAR.md\n"
        + end
        + b"\n"
    )


def find_region(text):
    start = text.find(begin)
    if start < 0:
        return None
    end_start = text.find(end, start + len(begin))
    if end_start < 0:
        return None
    region_end = end_start + len(end)
    if text[region_end:region_end + 2] == b"\r\n":
        region_end += 2
    elif text[region_end:region_end + 1] == b"\n":
        region_end += 1
    body = text[start:region_end]
    prefix_mode = b"none"
    marker_at = body.find(prefix_marker)
    if marker_at >= 0:
        value_start = marker_at + len(prefix_marker)
        value_end = body.find(b" -->", value_start)
        if value_end >= 0:
            prefix_mode = body[value_start:value_end]
    return start, region_end, prefix_mode


old = path.read_bytes() if path.exists() else b""
region = find_region(old)
if region:
    start, region_end, prefix_mode = region
    new = old[:start] + block(prefix_mode) + old[region_end:]
else:
    if old:
        backup = path.with_name(path.name + ".backup." + datetime.utcnow().strftime("%Y%m%d%H%M%S"))
        backup.write_bytes(old)
    if not old:
        new = block(b"none")
    elif old.endswith(b"\n") or old.endswith(b"\r"):
        new = old + block(b"none")
    else:
        new = old + b"\n" + block(b"newline")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_bytes(new)
PY
    return 0
}

component_verify() {
    [ -f "$CLAUDE_DIR/solar/SOLAR.md" ] || die "kernel verify failed: SOLAR.md missing"
    grep -q '<!-- BEGIN OPENSOLAR -->' "$CLAUDE_DIR/CLAUDE.md" || die "kernel verify failed: sentinel missing"
}
