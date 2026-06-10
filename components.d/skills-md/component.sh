#!/usr/bin/env bash

COMPONENT_NAME="skills-md"
COMPONENT_DESC="Markdown skill payloads for Claude Code discovery"
COMPONENT_DEFAULT="off"
COMPONENT_REQUIRES_BINS=""

component_install() {
    copy_payload "$SOURCE_DIR/skills" "$CLAUDE_DIR/skills"
    dry_run_note "record installed skills manifest" && return 0
    mkdir -p "$CLAUDE_DIR/solar"
    : > "$CLAUDE_DIR/solar/installed-skills.txt"
    for skill_dir in "$SOURCE_DIR"/skills/*; do
        [ -d "$skill_dir" ] || continue
        basename "$skill_dir" >> "$CLAUDE_DIR/solar/installed-skills.txt"
    done
    return 0
}

component_verify() {
    [ -d "$CLAUDE_DIR/skills" ] || die "skills-md verify failed: skills directory missing"
}
