#!/usr/bin/env bash

COMPONENT_NAME="autosci"
COMPONENT_DESC="AutoSci research workflow assets for the Solar harness"
COMPONENT_DEFAULT="on"
COMPONENT_REQUIRES_BINS="python3"
COMPONENT_REQUIRES_COMPONENTS="harness"

component_install() {
    copy_payload "$SOURCE_DIR/tools" "$SOLAR_HOME/tools"
    copy_payload "$SOURCE_DIR/.agents/skills" "$SOLAR_HOME/.agents/skills"
    dry_run_note "prepare AutoSci root tools" && return 0
    chmod +x "$SOLAR_HOME/tools/"*.py 2>/dev/null || true
    {
        printf 'tools_source=%s\n' "$SOURCE_DIR/tools"
        printf 'skills_source=%s\n' "$SOURCE_DIR/.agents/skills"
        printf 'tools_destination=%s\n' "$SOLAR_HOME/tools"
        printf 'skills_destination=%s\n' "$SOLAR_HOME/.agents/skills"
        printf 'synced_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } > "$SOLAR_HOME/.agents/autosci-runtime-source"
    return 0
}

component_verify() {
    [ -f "$SOLAR_HOME/harness/plugins/autosci/bin/autosci_skill_shim.py" ] \
        || die "autosci verify failed: autosci_skill_shim.py missing"
    [ -f "$SOLAR_HOME/tools/research_wiki.py" ] \
        || die "autosci verify failed: tools/research_wiki.py missing"
    [ -f "$SOLAR_HOME/tools/visualize.py" ] \
        || die "autosci verify failed: tools/visualize.py missing"
    [ -f "$SOLAR_HOME/.agents/skills/ingest/SKILL.md" ] \
        || die "autosci verify failed: .agents/skills/ingest/SKILL.md missing"
    [ -f "$SOLAR_HOME/.agents/skills/prefill/foundations-catalog.yaml" ] \
        || die "autosci verify failed: prefill foundations catalog missing"
    HARNESS_DIR="$SOLAR_HOME/harness" \
        "$SOLAR_PYTHON" "$SOLAR_HOME/harness/plugins/autosci/bin/autosci_skill_shim.py" skills list >/dev/null \
        || die "autosci verify failed: installed skill shim cannot list AutoSci skills"
}
