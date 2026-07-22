#!/usr/bin/env bash
# COMPONENT_* manifest fields are reset in load_component() and set by the
# sourced component.sh, then consumed cross-file (mcp-register / config-vars /
# py-deps / component scripts). shellcheck cannot see that cross-file use, so
# SC2034 ("appears unused") is a false positive for this manifest loader.
# shellcheck disable=SC2034

COMPONENT_ORDER="kernel core-runtime harness autosci skills-md skills-office skills-obsidian skills-calendar skills-browser codex-bridge solar-max mempalace daemons status-daemon"

component_manifest() {
    printf '%s/components.d/%s/component.sh\n' "$SOURCE_DIR" "$1"
}

load_component() {
    name="$1"
    manifest="$(component_manifest "$name")"
    [ -f "$manifest" ] || die "unknown component: $name"
    COMPONENT_NAME=""
    COMPONENT_DESC=""
    COMPONENT_DEFAULT="off"
    COMPONENT_REQUIRES_BINS=""
    COMPONENT_MCP_SERVERS=""
    COMPONENT_PLATFORMS=""
    COMPONENT_CONFIG_VARS=""
    COMPONENT_PYTHON_REQS=""
    COMPONENT_REQUIRES_COMPONENTS=""
    # shellcheck source=/dev/null
    . "$manifest"
}

list_components() {
    for name in $COMPONENT_ORDER; do
        load_component "$name"
        printf '%-14s %-5s %s\n' "$COMPONENT_NAME" "$COMPONENT_DEFAULT" "$COMPONENT_DESC"
    done
}

# Generically expand the requested set with transitive
# COMPONENT_REQUIRES_COMPONENTS until a fixpoint, so selecting a component pulls
# in everything it needs (e.g. daemons -> core-runtime -> kernel). Operates on
# the `requested` variable set by resolve_components. Terminates: every pass
# that adds a dependency adds a name from the finite COMPONENT_ORDER, and a
# pass that adds nothing ends the loop (cycles converge once both members are
# present).
expand_requires() {
    changed=1
    while [ "$changed" = "1" ]; do
        changed=0
        for name in $requested; do
            load_component "$name"
            for dep in $COMPONENT_REQUIRES_COMPONENTS; do
                if ! contains_word "$dep" "$requested"; then
                    contains_word "$dep" "$COMPONENT_ORDER" \
                        || die "component '$name' requires unknown component '$dep'"
                    requested="$requested $dep"
                    changed=1
                fi
            done
        done
    done
}

resolve_components() {
    if [ -n "$REQUESTED_COMPONENTS" ]; then
        requested="$(printf '%s' "$REQUESTED_COMPONENTS" | tr ',' ' ')"
    elif [ -n "${SOLAR_COMPONENTS:-}" ]; then
        requested="$(printf '%s' "$SOLAR_COMPONENTS" | tr ',' ' ')"
    else
        requested="kernel harness autosci"
        if command -v bun >/dev/null 2>&1; then
            requested="$requested core-runtime"
        fi
    fi

    for name in $requested; do
        contains_word "$name" "$COMPONENT_ORDER" \
            || die "unknown component: $name (known: $(printf '%s' "$COMPONENT_ORDER" | tr ' ' ','))"
    done

    expand_requires

    selected=""
    for name in $COMPONENT_ORDER; do
        if contains_word "$name" "$requested"; then
            load_component "$name"
            if [ -n "$COMPONENT_PLATFORMS" ]; then
                norm="$OS_KIND"; [ "$norm" = "wsl" ] && norm="linux"
                if ! contains_word "$OS_KIND" "$COMPONENT_PLATFORMS" \
                    && ! contains_word "$norm" "$COMPONENT_PLATFORMS"; then
                    die "component '$name' is not supported on $OS_KIND (platforms: $COMPONENT_PLATFORMS)"
                fi
            fi
            for bin in $COMPONENT_REQUIRES_BINS; do
                require_bin "$bin" "Install it or remove '$name' from --components."
            done
            selected="$selected $name"
        fi
    done
    SELECTED_COMPONENTS="$(printf '%s\n' "$selected" | awk '{$1=$1; print}')"
    [ -n "$SELECTED_COMPONENTS" ] || die "no components selected"
    export SELECTED_COMPONENTS
}

install_components() {
    for name in $COMPONENT_ORDER; do
        if contains_word "$name" "$SELECTED_COMPONENTS"; then
            load_component "$name"
            info "install component: $COMPONENT_NAME"
            component_install
            if [ "$DRY_RUN" != "true" ]; then
                component_verify
            fi
        fi
    done
}
