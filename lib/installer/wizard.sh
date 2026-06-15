#!/usr/bin/env bash

SOLAR_CANCEL_EXIT=130
WIZARD_PANEL_DEFAULT_WIDTH=64
WIZARD_PANEL_MIN_WIDTH=40

cancel_install() {
    printf 'cancelled\n' >&2
    exit "$SOLAR_CANCEL_EXIT"
}

# True when we may interactively prompt the user.
#
# The interactive surfaces (wizard_read) talk to /dev/tty directly, so a real
# terminal is reachable even when stdin is a pipe -- which is exactly the
# `curl -fsSL ... | bash` case. Testing `[ -t 0 ]` there is wrong: stdin is the
# curl pipe, so the wizard self-skips and the install dies asking for --yes.
# We instead test whether /dev/tty itself can be opened, and honor explicit
# non-interactive signals first so CI/automation never blocks:
#   CI (any non-empty value, set by GitHub Actions et al.) -> non-interactive
#   SOLAR_NONINTERACTIVE=true                               -> non-interactive
#   /dev/tty not openable (cron, no controlling terminal)   -> non-interactive
solar_can_prompt() {
    [ -n "${CI:-}" ] && return 1
    [ "${SOLAR_NONINTERACTIVE:-false}" = "true" ] && return 1
    ( exec </dev/tty ) 2>/dev/null
}

wizard_read() {
    prompt="$1"
    WIZARD_ANSWER=""
    printf '%s' "$prompt" >/dev/tty
    IFS= read -r WIZARD_ANSWER </dev/tty || WIZARD_ANSWER=""
}

wizard_terminal_width() {
    case "${COLUMNS:-}" in
        ''|*[!0-9]*) ;;
        *) [ "$COLUMNS" -gt 0 ] && { printf '%s' "$COLUMNS"; return 0; } ;;
    esac

    cols="$(tput cols 2>/dev/null || true)"
    case "$cols" in
        ''|*[!0-9]*) printf '80' ;;
        *) [ "$cols" -gt 0 ] && printf '%s' "$cols" || printf '80' ;;
    esac
}

wizard_panel_width() {
    cols="$(wizard_terminal_width)"
    width="$WIZARD_PANEL_DEFAULT_WIDTH"
    if [ "$cols" -lt "$width" ]; then
        width="$cols"
    fi
    if [ "$width" -lt "$WIZARD_PANEL_MIN_WIDTH" ]; then
        width="$WIZARD_PANEL_MIN_WIDTH"
    fi
    printf '%s' "$width"
}

wizard_repeat() {
    char="$1"
    count="$2"
    out=""
    while [ "$count" -gt 0 ]; do
        out="$out$char"
        count=$((count - 1))
    done
    printf '%s' "$out"
}

wizard_fit_text() {
    text="$1"
    width="$2"
    [ "$width" -gt 0 ] || return 0
    if [ "${#text}" -le "$width" ]; then
        printf '%s' "$text"
    elif [ "$width" -le 3 ]; then
        printf '%s' "${text:0:$width}"
    else
        printf '%s...' "${text:0:$((width - 3))}"
    fi
}

wizard_line() {
    content="$(wizard_fit_text "$1" "$(( $(wizard_panel_width) - 2 ))")"
    pad_count=$(( $(wizard_panel_width) - 2 - ${#content} ))
    printf '│%s%s│\n' "$content" "$(wizard_repeat ' ' "$pad_count")" >&2
}

wizard_top() {
    printf '╭%s╮\n' "$(wizard_repeat '─' "$(( $(wizard_panel_width) - 2 ))")" >&2
}

wizard_rule() {
    inner_width=$(( $(wizard_panel_width) - 2 ))
    wizard_line "  $(wizard_repeat '─' "$((inner_width - 4))")  "
}

wizard_heading() {
    title="$1"
    inner_width=$(( $(wizard_panel_width) - 2 ))
    title="$(wizard_fit_text "$title" "$((inner_width - 4))")"
    rule_count=$((inner_width - ${#title} - 3))
    printf '\n' >&2
    printf '╭─ %s %s╮\n' "$title" "$(wizard_repeat '─' "$rule_count")" >&2
}

wizard_footer() {
    printf '╰%s╯\n' "$(wizard_repeat '─' "$(( $(wizard_panel_width) - 2 ))")" >&2
}

wizard_kv() {
    label="$1"
    value="$2"
    wizard_line "$(printf '  %-11s %s' "$label" "$value")"
}

wizard_status_line() {
    item="$1"
    status="$2"
    detail="$3"
    wizard_line "$(printf '  %-10s %-9s%s' "$item" "$status" "$detail")"
}

wizard_tool_line() {
    tool="$1"
    note="$2"
    path="$(command_path "$tool")"
    if [ -n "$path" ]; then
        wizard_status_line "$tool" "ok" "$path"
    else
        wizard_status_line "$tool" "missing" "$note"
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
    wizard_top
    wizard_line ""
    wizard_line "    ☀  S O L A R        ·        OpenJiuwen Solar"
    wizard_line ""
    wizard_line "    component runtime   ·   Claude overlay   ·   harness"
    wizard_line ""
    wizard_footer
}

wizard_preflight_summary() {
    wizard_heading "Preflight"
    wizard_kv "OS" "$OS_KIND"
    wizard_kv "Source" "$SOURCE_DIR"
    wizard_kv "Solar home" "$SOLAR_HOME"
    wizard_kv "Claude dir" "$CLAUDE_DIR"
    wizard_kv "Python" "${SOLAR_PYTHON:-python3} ${SOLAR_PYTHON_VERSION:-}"
    wizard_footer

    wizard_heading "Tools"
    wizard_tool_line python3 "required: Python 3.11+"
    wizard_tool_line tmux "harness dependency"
    wizard_tool_line jq "harness dependency"
    if bash4_path="$(find_bash4 2>/dev/null)"; then
        wizard_status_line "bash>=4" "ok" "$bash4_path"
    else
        wizard_status_line "bash>=4" "missing" "harness dependency"
    fi
    wizard_tool_line git "optional receipt metadata"
    wizard_tool_line bun "enables core-runtime"
    wizard_tool_line cargo "enables skills-browser"
    wizard_tool_line claude "optional MCP registration"
    wizard_footer
}

wizard_component_summary() {
    title="$1"
    wizard_heading "$title"
    wizard_line "  $SELECTED_COMPONENTS"
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
        wizard_line "$(printf '  %2s. [%s] %-15s default=%-4s platforms=%-16s requires=%s' \
            "$idx" "$mark" "$COMPONENT_NAME" "$COMPONENT_DEFAULT" "$platforms" "$req_bins")"
        wizard_line "      $COMPONENT_DESC"
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
    solar_can_prompt || return 0

    wizard_banner
    wizard_preflight_summary
    wizard_component_summary "Default components"

    while :; do
        wizard_heading "Choose an option"
        wizard_line "  1. Proceed"
        wizard_line "  2. Customize"
        wizard_line "  3. Cancel"
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
