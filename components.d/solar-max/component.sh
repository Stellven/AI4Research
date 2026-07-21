#!/usr/bin/env bash

COMPONENT_NAME="solar-max"
COMPONENT_DESC="Opt-in Solar-Max project mode (Gate-driven workflow over a personal ~/Solar-MAX dir)"
COMPONENT_DEFAULT="off"
COMPONENT_REQUIRES_BINS=""
COMPONENT_REQUIRES_COMPONENTS="kernel"

# This component has no payload of its own: selecting it makes kernel-gen
# include kernel/fragments/solar-max.md in the generated SOLAR.md (the manifest
# gates that fragment on this component). Off by default so a stranger's kernel
# never tells Claude to `cd ~/Solar-MAX`.
component_install() {
    return 0
}

component_verify() {
    file="$CLAUDE_DIR/solar/SOLAR.md"
    [ -f "$file" ] || die "solar-max verify failed: SOLAR.md missing (kernel component required)"
    grep -q "Solar-Max" "$file" || die "solar-max verify failed: fragment not present in generated kernel"
}
