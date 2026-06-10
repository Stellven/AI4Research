#!/usr/bin/env bash

COMPONENT_NAME="skills-md"
COMPONENT_DESC="Markdown skill payloads for Claude Code discovery"
COMPONENT_DEFAULT="off"
COMPONENT_REQUIRES_BINS=""

component_install() {
    copy_payload "$SOURCE_DIR/skills" "$CLAUDE_DIR/skills"
    return 0
}

component_verify() {
    [ -d "$CLAUDE_DIR/skills" ] || die "skills-md verify failed: skills directory missing"
}
