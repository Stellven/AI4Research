#!/usr/bin/env bash

COMPONENT_NAME="skills-calendar"
COMPONENT_DESC="macOS Calendar skills (darwin only)"
COMPONENT_DEFAULT="off"
COMPONENT_PLATFORMS="darwin"
COMPONENT_REQUIRES_BINS=""

component_install() {
    copy_skills apple-calendar email-to-calendar
}

component_verify() {
    [ -d "$CLAUDE_DIR/skills/apple-calendar" ] || die "skills-calendar verify failed: apple-calendar skill missing"
}
