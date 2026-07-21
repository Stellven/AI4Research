#!/usr/bin/env bash

COMPONENT_NAME="skills-office"
COMPONENT_DESC="Office productivity skills (email, notes, tasks, notion, trello)"
COMPONENT_DEFAULT="off"
COMPONENT_REQUIRES_BINS=""

component_install() {
    copy_skills office office-email office-notes office-notion \
        office-reminders office-tasks office-trello
}

component_verify() {
    [ -d "$CLAUDE_DIR/skills/office" ] || die "skills-office verify failed: office skill missing"
}
