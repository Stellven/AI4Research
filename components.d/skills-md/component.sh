#!/usr/bin/env bash

COMPONENT_NAME="skills-md"
COMPONENT_DESC="Generic markdown skills for Claude Code discovery"
COMPONENT_DEFAULT="off"
COMPONENT_REQUIRES_BINS=""

component_install() {
    copy_skills \
        a2a-hub agent agent-orchestrator banner benchmark build clawdwork \
        commit docs mcp-builder mode phase pr report restore review save \
        skill-creator skin-check solar solar-web stats status test
}

component_verify() {
    [ -d "$CLAUDE_DIR/skills" ] || die "skills-md verify failed: skills directory missing"
}
