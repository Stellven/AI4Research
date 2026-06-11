#!/usr/bin/env bash

COMPONENT_NAME="skills-browser"
COMPONENT_DESC="Browser automation skills (cargo-gated at runtime)"
COMPONENT_DEFAULT="off"
COMPONENT_REQUIRES_BINS="cargo"

component_install() {
    copy_skills browser-automation fast-browser-use webapp-testing
}

component_verify() {
    [ -d "$CLAUDE_DIR/skills/browser-automation" ] || die "skills-browser verify failed: browser-automation skill missing"
}
