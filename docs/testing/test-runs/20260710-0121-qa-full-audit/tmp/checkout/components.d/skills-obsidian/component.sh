#!/usr/bin/env bash

COMPONENT_NAME="skills-obsidian"
COMPONENT_DESC="Obsidian vault skills"
COMPONENT_DEFAULT="off"
COMPONENT_REQUIRES_BINS=""

component_install() {
    copy_skills obsidian-daily obsidian-direct
}

component_verify() {
    [ -d "$CLAUDE_DIR/skills/obsidian-daily" ] || die "skills-obsidian verify failed: obsidian-daily skill missing"
}
