#!/usr/bin/env bash

COMPONENT_ORDER="kernel core-runtime harness skills-md skills-office skills-obsidian skills-calendar skills-browser codex-bridge mempalace daemons"

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

resolve_components() {
    if [ -n "$REQUESTED_COMPONENTS" ]; then
        requested="$(printf '%s' "$REQUESTED_COMPONENTS" | tr ',' ' ')"
    elif [ -n "${SOLAR_COMPONENTS:-}" ]; then
        requested="$(printf '%s' "$SOLAR_COMPONENTS" | tr ',' ' ')"
    else
        requested="kernel harness"
        if command -v bun >/dev/null 2>&1; then
            requested="$requested core-runtime"
        fi
    fi

    for name in $requested; do
        contains_word "$name" "$COMPONENT_ORDER" \
            || die "unknown component: $name (known: $(printf '%s' "$COMPONENT_ORDER" | tr ' ' ','))"
    done

    if contains_word "harness" "$requested" && ! contains_word "kernel" "$requested"; then
        requested="kernel $requested"
    fi
    if contains_word "core-runtime" "$requested" && ! contains_word "kernel" "$requested"; then
        requested="kernel $requested"
    fi

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
