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
    # rules and the 7 base @Agent files ship with the base kernel; rules/agents
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
begin = "<!-- BEGIN OPENSOLAR -->"
end = "<!-- END OPENSOLAR -->"
block = f"{begin}\n@~/.claude/solar/SOLAR.md\n{end}\n"
old = path.read_text(encoding="utf-8") if path.exists() else ""
if begin in old and end in old:
    before = old.split(begin, 1)[0].rstrip()
    after = old.split(end, 1)[1].lstrip()
    new = (before + "\n\n" if before else "") + block + ("\n" + after if after else "")
else:
    if old:
        backup = path.with_name(path.name + ".backup." + datetime.utcnow().strftime("%Y%m%d%H%M%S"))
        backup.write_text(old, encoding="utf-8")
    new = (old.rstrip() + "\n\n" if old.strip() else "") + block
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(new, encoding="utf-8")
PY
    return 0
}

component_verify() {
    [ -f "$CLAUDE_DIR/solar/SOLAR.md" ] || die "kernel verify failed: SOLAR.md missing"
    grep -q '<!-- BEGIN OPENSOLAR -->' "$CLAUDE_DIR/CLAUDE.md" || die "kernel verify failed: sentinel missing"
}
