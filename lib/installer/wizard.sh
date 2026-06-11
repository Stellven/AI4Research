#!/usr/bin/env bash

SOLAR_CANCEL_EXIT=130

cancel_install() {
    printf 'cancelled\n' >&2
    exit "$SOLAR_CANCEL_EXIT"
}

wizard_read() {
    prompt="$1"
    WIZARD_ANSWER=""
    printf '%s' "$prompt" >/dev/tty
    IFS= read -r WIZARD_ANSWER </dev/tty || WIZARD_ANSWER=""
}

wizard_rule() {
    printf '│  ──────────────────────────────────────────────────────────  │\n' >&2
}

wizard_heading() {
    title="$1"
    printf '\n' >&2
    printf '╭─ %s ─────────────────────────────────────────────────────╮\n' "$title" >&2
}

wizard_footer() {
    printf '╰──────────────────────────────────────────────────────────────╯\n' >&2
}

wizard_kv() {
    label="$1"
    value="$2"
    printf '│  %-11s %s\n' "$label" "$value" >&2
}

wizard_tool_line() {
    tool="$1"
    note="$2"
    path="$(command_path "$tool")"
    if [ -n "$path" ]; then
        printf '│  %-10s ok       %s\n' "$tool" "$path" >&2
    else
        printf '│  %-10s missing  %s\n' "$tool" "$note" >&2
    fi
}

wizard_banner() {
    printf '\n' >&2
    printf '  ██████╗  ██████╗ ██╗      █████╗ ██████╗\n' >&2
    printf '  ██╔════╝ ██╔═══██╗██║     ██╔══██╗██╔══██╗\n' >&2
    printf '  ███████╗ ██║   ██║██║     ███████║██████╔╝\n' >&2
    printf '  ╚════██║ ██║   ██║██║     ██╔══██║██╔══██╗\n' >&2
    printf '  ██████╔╝ ╚██████╔╝███████╗██║  ██║██║  ██║\n' >&2
    printf '  ╚═════╝   ╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝\n' >&2
    printf '\n' >&2
    printf '╭──────────────────────────────────────────────────────────────╮\n' >&2
    printf '│                                                              │\n' >&2
    printf '│    ☀  S O L A R        ·        OpenJiuwen Solar            │\n' >&2
    printf '│                                                              │\n' >&2
    printf '│    component runtime   ·   Claude overlay   ·   harness     │\n' >&2
    printf '│                                                              │\n' >&2
    printf '╰──────────────────────────────────────────────────────────────╯\n' >&2
}

wizard_preflight_summary() {
    wizard_heading "Preflight"
    wizard_kv "OS" "$OS_KIND"
    wizard_kv "Source" "$SOURCE_DIR"
    wizard_kv "Solar home" "$SOLAR_HOME"
    wizard_kv "Claude dir" "$CLAUDE_DIR"
    wizard_footer

    wizard_heading "Tools"
    wizard_tool_line python3 "required"
    wizard_tool_line git "optional receipt metadata"
    wizard_tool_line bun "enables core-runtime"
    wizard_tool_line cargo "enables skills-browser"
    wizard_tool_line claude "optional MCP registration"
    wizard_footer
}

wizard_component_summary() {
    title="$1"
    wizard_heading "$title"
    printf '│  %s\n' "$SELECTED_COMPONENTS" >&2
    wizard_footer
}

wizard_component_by_number() {
    want="$1"
    idx=1
    for name in $COMPONENT_ORDER; do
        if [ "$idx" = "$want" ]; then
            printf '%s' "$name"
            return 0
        fi
        idx=$((idx + 1))
    done
    return 1
}

wizard_show_available_components() {
    idx=1
    wizard_heading "Available components"
    for name in $COMPONENT_ORDER; do
        load_component "$name"
        mark=" "
        contains_word "$name" "$SELECTED_COMPONENTS" && mark="*"
        platforms="${COMPONENT_PLATFORMS:-all}"
        req_bins="${COMPONENT_REQUIRES_BINS:-none}"
        printf '│  %2s. [%s] %-15s default=%-4s platforms=%-16s requires=%s\n' \
            "$idx" "$mark" "$COMPONENT_NAME" "$COMPONENT_DEFAULT" "$platforms" "$req_bins" >&2
        printf '│      %s\n' "$COMPONENT_DESC" >&2
        idx=$((idx + 1))
    done
    wizard_footer
}

wizard_parse_component_selection() {
    input="$(printf '%s' "$1" | tr ',' ' ')"
    WIZARD_SELECTED=""
    for token in $input; do
        case "$token" in
            c|C|cancel|Cancel|CANCEL) cancel_install ;;
        esac
        case "$token" in
            *[!0-9]*)
                comp="$token"
                ;;
            *)
                comp="$(wizard_component_by_number "$token")" || comp=""
                ;;
        esac
        if ! contains_word "$comp" "$COMPONENT_ORDER"; then
            printf 'unknown component selection: %s\n' "$token" >&2
            return 1
        fi
        if ! contains_word "$comp" "$WIZARD_SELECTED"; then
            WIZARD_SELECTED="$WIZARD_SELECTED $comp"
        fi
    done
    WIZARD_SELECTED="$(printf '%s\n' "$WIZARD_SELECTED" | awk '{$1=$1; print}')"
    [ -n "$WIZARD_SELECTED" ]
}

wizard_customize_components() {
    while :; do
        wizard_show_available_components
        printf '\n  Enter numbers or names separated by commas/spaces.\n' >&2
        printf '  Press Enter to keep the default selection, or type cancel.\n' >&2
        wizard_read "Selection: "
        [ -n "$WIZARD_ANSWER" ] || {
            wizard_component_summary "Keeping default components"
            return 0
        }
        if wizard_parse_component_selection "$WIZARD_ANSWER"; then
            REQUESTED_COMPONENTS="$WIZARD_SELECTED"
            export REQUESTED_COMPONENTS
            resolve_components
            wizard_component_summary "Selected components"
            return 0
        fi
    done
}

run_component_wizard_if_needed() {
    [ "$YES" = "true" ] && return 0
    [ -n "$REQUESTED_COMPONENTS" ] && return 0
    [ -t 0 ] || return 0

    wizard_banner
    wizard_preflight_summary
    wizard_component_summary "Default components"

    while :; do
        wizard_heading "Choose an option"
        printf '│  1. Proceed\n' >&2
        printf '│  2. Customize\n' >&2
        printf '│  3. Cancel\n' >&2
        wizard_rule
        wizard_footer
        wizard_read "Choice [1-3]: "
        case "$WIZARD_ANSWER" in
            1|p|P|proceed|Proceed|PROCEED)
                return 0
                ;;
            2|c|C|customize|Customize|CUSTOMIZE)
                wizard_customize_components
                return 0
                ;;
            3|q|Q|cancel|Cancel|CANCEL)
                cancel_install
                ;;
            *)
                printf 'enter 1, 2, or 3\n' >&2
                ;;
        esac
    done
}

print_final_summary() {
    wizard_heading "Final summary"
    wizard_kv "Components" "$SELECTED_COMPONENTS"
    wizard_kv "Solar home" "$SOLAR_HOME"
    wizard_kv "Claude dir" "$CLAUDE_DIR"
    if [ "$DRY_RUN" = "true" ]; then
        wizard_kv "Mode" "dry-run (zero writes)"
    else
        wizard_kv "Mode" "install"
    fi
    wizard_footer
}
